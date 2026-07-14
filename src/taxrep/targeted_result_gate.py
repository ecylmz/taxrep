from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from taxrep.constants import PROJECT_ROOT
from taxrep.public_artifact import artifact_hash_match
from taxrep.targeted import EXPECTED_TASKS, verify_targeted_extension_freeze
from taxrep.targeted_recovery import verify_targeted_recovery_freeze
from taxrep.utils import sha256_file

TARGETED_RESULTS_FREEZE = (
    PROJECT_ROOT
    / "results"
    / "run_manifests"
    / "targeted_t3_repeat_results_freeze.json"
)


def verify_targeted_results_freeze(
    path: Path = TARGETED_RESULTS_FREEZE,
) -> dict[str, Any]:
    recovery_hashes = (
        PROJECT_ROOT / "experiment" / "targeted_t3_repeat_recovery_hashes.json"
    )
    if recovery_hashes.is_file():
        verify_targeted_recovery_freeze()
    else:
        verify_targeted_extension_freeze()
    if not path.is_file():
        raise RuntimeError(
            "Targeted results are not frozen; run the metadata-only result-freeze step "
            "before joining predictions to benchmark labels"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "frozen":
        raise RuntimeError("Targeted result-freeze status is not frozen")
    if int(payload.get("canonical_tasks", -1)) != EXPECTED_TASKS:
        raise RuntimeError("Targeted result-freeze canonical task count is not 2,700")
    if int(payload.get("completion_calls_used", -1)) > int(
        payload.get("completion_call_hard_cap", -1)
    ):
        raise RuntimeError("Targeted result-freeze records a call-budget violation")
    if payload.get("schema_version") == 2 and int(
        payload.get("conservative_revision_http_attempt_upper_bound", -1)
    ) > int(payload.get("revision_http_attempt_hard_cap", -1)):
        raise RuntimeError("Targeted result-freeze records a revision HTTP-cap violation")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise RuntimeError("Targeted result-freeze has no artifact hashes")
    mismatches: list[str] = []
    for item in artifacts:
        relative = str(item.get("path", ""))
        if artifact_hash_match(
            relative, str(item.get("sha256", "")), root=PROJECT_ROOT
        ) is None:
            mismatches.append(relative)
    if mismatches:
        raise RuntimeError(
            "Targeted result-freeze artifact hash mismatch: " + ", ".join(mismatches)
        )
    processed_manifest = json.loads(
        (PROJECT_ROOT / "data/manifests/test_processed_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    for file_key, hash_key in (
        ("inference_file", "inference_sha256"),
        ("gold_file", "gold_sha256"),
    ):
        data_path = PROJECT_ROOT / str(processed_manifest[file_key])
        if not data_path.is_file() or sha256_file(data_path) != processed_manifest[hash_key]:
            raise RuntimeError(f"Targeted analysis input differs from {hash_key}")
    return {
        "ok": True,
        "freeze_path": path.relative_to(PROJECT_ROOT).as_posix(),
        "artifact_count": len(artifacts),
        "canonical_tasks": int(payload["canonical_tasks"]),
        "completion_calls_used": int(payload["completion_calls_used"]),
        "protocol_commit": payload.get("protocol_commit"),
    }
