from __future__ import annotations

import csv
import hashlib
import os
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def today_yyyymmdd() -> str:
    return datetime.now(UTC).strftime("%Y%m%d")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS))
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS))
        handle.write(b"\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("rb") as handle:
        for line in handle:
            if line.strip():
                records.append(orjson.loads(line))
    return records


def load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))

    def public_path(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: public_path(item) for key, item in value.items()}
        if isinstance(value, list):
            return [public_path(item) for item in value]
        if isinstance(value, str) and value.startswith("protocol/"):
            return "experiment/" + value.removeprefix("protocol/")
        return value

    return public_path(payload)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def command_output(args: list[str]) -> str | None:
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def git_commit(root: Path) -> str | None:
    return command_output(["git", "-C", str(root), "rev-parse", "HEAD"])


def environment_snapshot(root: Path) -> dict[str, Any]:
    return {
        "captured_at_utc": utc_now_iso(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "uv_version": command_output(["uv", "--version"]),
        "git_commit": git_commit(root),
    }
