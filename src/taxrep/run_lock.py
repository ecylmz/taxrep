from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from taxrep.utils import utc_now_iso, write_json


@dataclass
class RunLock:
    path: Path
    payload: dict

    def __enter__(self) -> RunLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            fd = os.open(self.path, flags)
        except FileExistsError as exc:
            raise RuntimeError(f"Run lock already exists: {self.path}") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            write_payload = dict(self.payload)
            write_payload["created_at_utc"] = utc_now_iso()
            handle.write(__import__("json").dumps(write_payload, indent=2, sort_keys=True))
            handle.write("\n")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.path.exists():
            self.path.unlink()


def write_manifest(path: Path, payload: dict) -> None:
    write_json(path, payload)
