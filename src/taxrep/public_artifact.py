from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Literal

from taxrep.constants import PROJECT_ROOT
from taxrep.utils import sha256_file

PUBLIC_PROVENANCE_NAME = "PUBLIC_REDACTION_PROVENANCE.json"
SOURCE_SNAPSHOT_NAME = "SOURCE_SNAPSHOT.json"
MANIFEST_NAME = "MANIFEST.sha256"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")
FULL_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
ALLOWED_POINTERS = {
    "/ledger_path",
    "/completion_call_budget/ledger_path",
}
ALLOWED_TRANSFORMATIONS = {
    "repository-root absolute path to repository-relative POSIX path",
    "exact repository-root byte sequence to dot in execution log",
}
HashMatch = Literal["source", "public_view"]


def _safe_relative(relative_path: str) -> bool:
    pure = PurePosixPath(relative_path)
    return bool(
        relative_path
        and not pure.is_absolute()
        and pure.as_posix() == relative_path
        and all(part not in {"", ".", ".."} for part in pure.parts)
    )


def _manifest_hash(relative_path: str, root: Path) -> str | None:
    manifest = root / MANIFEST_NAME
    if not manifest.is_file():
        return None
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if "  " not in line:
            return None
        digest, path = line.split("  ", 1)
        if path == relative_path:
            return digest if SHA256_RE.fullmatch(digest) else None
    return None


def _public_records(root: Path) -> dict[str, dict[str, object]]:
    path = root / PUBLIC_PROVENANCE_NAME
    if not path.is_file() or _manifest_hash(PUBLIC_PROVENANCE_NAME, root) != sha256_file(path):
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or payload.get("raw_prediction_artifacts_transformed") is not False
        or payload.get("scientific_fields_changed") is not False
        or not isinstance(payload.get("records"), list)
    ):
        return {}

    records: dict[str, dict[str, object]] = {}
    for record in payload["records"]:
        if not isinstance(record, dict):
            return {}
        relative = record.get("archive_path")
        pointers = record.get("allowed_json_pointers")
        replacement_count = record.get("replacement_count")
        if (
            not isinstance(relative, str)
            or not _safe_relative(relative)
            or relative in records
            or relative.startswith("results/raw_predictions/")
            or not isinstance(pointers, list)
            or not all(isinstance(value, str) and value in ALLOWED_POINTERS for value in pointers)
            or not isinstance(replacement_count, int)
            or isinstance(replacement_count, bool)
            or replacement_count < 1
            or record.get("transformation") not in ALLOWED_TRANSFORMATIONS
            or not isinstance(record.get("source_sha256"), str)
            or not SHA256_RE.fullmatch(str(record["source_sha256"]))
            or not isinstance(record.get("packaged_sha256"), str)
            or not SHA256_RE.fullmatch(str(record["packaged_sha256"]))
        ):
            return {}
        records[relative] = record
    return records


def artifact_hash_match(
    relative_path: str,
    expected_source_sha256: str,
    *,
    expected_source_bytes: int | None = None,
    root: Path | None = None,
) -> HashMatch | None:
    """Match a frozen source hash or its manifest-authenticated public view."""

    if not _safe_relative(relative_path) or not SHA256_RE.fullmatch(expected_source_sha256):
        return None
    artifact_root = root or PROJECT_ROOT
    path = artifact_root / relative_path
    if not path.is_file() and relative_path.startswith("protocol/"):
        path = artifact_root / "experiment" / relative_path.removeprefix("protocol/")
    if not path.is_file():
        return None
    actual_hash = sha256_file(path)
    if actual_hash == expected_source_sha256 and (
        expected_source_bytes is None or path.stat().st_size == expected_source_bytes
    ):
        return "source"

    record = _public_records(artifact_root).get(relative_path)
    if (
        record is None
        or record["source_sha256"] != expected_source_sha256
        or record["packaged_sha256"] != actual_hash
        or _manifest_hash(relative_path, artifact_root) != actual_hash
    ):
        return None
    return "public_view"


def commit_is_ancestor_or_public_snapshot(commit: str, *, root: Path | None = None) -> bool:
    """Accept Git ancestry or a manifest-authenticated detached public snapshot."""

    if not COMMIT_RE.fullmatch(commit):
        return False
    artifact_root = root or PROJECT_ROOT
    result = subprocess.run(
        ["git", "-C", str(artifact_root), "merge-base", "--is-ancestor", commit, "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return True

    snapshot = artifact_root / SOURCE_SNAPSHOT_NAME
    if not snapshot.is_file() or _manifest_hash(
        SOURCE_SNAPSHOT_NAME, artifact_root
    ) != sha256_file(snapshot):
        return False
    try:
        payload = json.loads(snapshot.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(
        isinstance(payload, dict)
        and payload.get("schema_version") == 1
        and payload.get("artifact_profile")
        in {"github_release_candidate_directory", "public_experiment_code_and_results"}
        and FULL_COMMIT_RE.fullmatch(str(payload.get("source_base_git_commit", "")))
        and payload.get("raw_predictions_transformed") is False
    )
