from __future__ import annotations

import pandas as pd

RUN_TYPE_PREFIXES = (
    "targeted-t3-repeat",
    "technical-pretest",
    "train-selection",
    "robustness",
    "pilot",
    "main",
)

PREDICTION_TASK_KEYS = (
    "run_type",
    "dataset_split",
    "issue_id",
    "model_id",
    "taxonomy_condition",
    "instruction_variant",
    "repeat_id",
)


def derive_run_type(run_id: str) -> str:
    for prefix in RUN_TYPE_PREFIXES:
        if run_id.startswith(prefix):
            return prefix
    return "unknown"


def ensure_run_type(frame: pd.DataFrame) -> pd.DataFrame:
    if "run_type" in frame.columns:
        return frame
    out = frame.copy()
    out["run_type"] = out["run_id"].map(derive_run_type)
    return out


def prediction_task_key(record: dict) -> tuple:
    return tuple(record.get(key) for key in PREDICTION_TASK_KEYS)


def canonicalize_prediction_records(records: list[dict]) -> list[dict]:
    """Keep one record per prediction task, preferring successful retry rows."""
    by_key: dict[tuple, dict] = {}
    for record in records:
        key = prediction_task_key(record)
        current = by_key.get(key)
        if current is None:
            by_key[key] = record
            continue
        current_failed = bool(current.get("technical_error"))
        record_failed = bool(record.get("technical_error"))
        if (current_failed and not record_failed) or (current_failed == record_failed):
            by_key[key] = record
    return sorted(
        by_key.values(),
        key=lambda record: (
            str(record.get("run_type", "")),
            str(record.get("dataset_split", "")),
            str(record.get("model_id", "")),
            str(record.get("taxonomy_condition", "")),
            str(record.get("instruction_variant", "")),
            int(record.get("repeat_id") or 0),
            int(record.get("planned_task_index") or 0),
            str(record.get("issue_id", "")),
        ),
    )
