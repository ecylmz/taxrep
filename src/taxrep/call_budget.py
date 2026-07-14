from __future__ import annotations

import fcntl
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import orjson

from taxrep.utils import sha256_text, utc_now_iso


class CompletionCallBudgetExceeded(RuntimeError):
    """Raised before a completion request that would exceed the frozen cap."""


@dataclass(frozen=True)
class CompletionCallBudget:
    summary_path: Path
    ledger_path: Path
    hard_cap: int

    @classmethod
    def from_config(cls, root: Path, config: dict[str, Any]) -> CompletionCallBudget:
        return cls(
            summary_path=root / str(config["summary_path"]),
            ledger_path=root / str(config["ledger_path"]),
            hard_cap=int(config["hard_cap"]),
        )

    @property
    def lock_path(self) -> Path:
        return self.summary_path.with_suffix(self.summary_path.suffix + ".lock")

    def _initial_summary(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "hard_cap": self.hard_cap,
            "used": 0,
            "remaining": self.hard_cap,
            "by_kind": {},
            "by_model": {},
            "created_at_utc": utc_now_iso(),
            "last_reserved_at_utc": None,
            "ledger_path": str(self.ledger_path),
        }

    def _load_summary(self) -> dict[str, Any]:
        if not self.summary_path.exists():
            return self._initial_summary()
        payload = orjson.loads(self.summary_path.read_bytes())
        if int(payload.get("hard_cap", -1)) != self.hard_cap:
            raise RuntimeError(
                "Completion-call budget cap differs from the frozen existing ledger"
            )
        return payload

    @staticmethod
    def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
        temporary.write_bytes(
            orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS) + b"\n"
        )
        os.replace(temporary, path)

    def initialize(self) -> dict[str, Any]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            summary = self._load_summary()
            self._atomic_write(self.summary_path, summary)
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        return summary

    def snapshot(self) -> dict[str, Any]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_SH)
            summary = self._load_summary()
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        return summary

    def reserve(
        self,
        *,
        kind: str,
        model_id: str,
        run_id: str,
        task_key: str,
        attempt: int,
    ) -> int:
        """Durably reserve one provider completion attempt before sending it.

        A crash after reservation can only overcount the budget, which is the
        conservative failure mode required by the hard-cap protocol.
        """

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            summary = self._load_summary()
            used = int(summary["used"])
            if used >= self.hard_cap:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
                raise CompletionCallBudgetExceeded(
                    f"Completion-call hard cap {self.hard_cap} has been reached"
                )
            ordinal = used + 1
            reserved_at = utc_now_iso()
            summary["used"] = ordinal
            summary["remaining"] = self.hard_cap - ordinal
            summary["last_reserved_at_utc"] = reserved_at
            by_kind = dict(summary.get("by_kind", {}))
            by_kind[kind] = int(by_kind.get(kind, 0)) + 1
            summary["by_kind"] = by_kind
            by_model = dict(summary.get("by_model", {}))
            by_model[model_id] = int(by_model.get(model_id, 0)) + 1
            summary["by_model"] = by_model
            self._atomic_write(self.summary_path, summary)

            ledger_record = {
                "ordinal": ordinal,
                "reserved_at_utc": reserved_at,
                "kind": kind,
                "model_id": model_id,
                "run_id": run_id,
                "attempt": int(attempt),
                "task_key_sha256": sha256_text(task_key),
            }
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with self.ledger_path.open("ab") as ledger_handle:
                ledger_handle.write(orjson.dumps(ledger_record, option=orjson.OPT_SORT_KEYS))
                ledger_handle.write(b"\n")
                ledger_handle.flush()
                os.fsync(ledger_handle.fileno())
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        return ordinal
