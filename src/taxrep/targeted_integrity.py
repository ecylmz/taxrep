from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import orjson
import pandas as pd  # type: ignore[import-untyped]

from taxrep.constants import PROJECT_ROOT
from taxrep.inference import build_tasks
from taxrep.parsers import lenient_parse, strict_parse
from taxrep.prompts import RenderedPrompt, render_prompt
from taxrep.runs import (
    PREDICTION_TASK_KEYS,
    canonicalize_prediction_records,
    ensure_run_type,
)
from taxrep.targeted import (
    EXPECTED_TASKS,
    MODELS,
    TARGETED_PROTOCOL_YAML,
    targeted_task_plan,
    verify_targeted_extension_freeze,
)
from taxrep.utils import load_yaml, read_jsonl, sha256_bytes, sha256_file, write_json

INTEGRITY_REPORT = (
    PROJECT_ROOT
    / "results"
    / "run_manifests"
    / "targeted_t3_repeat_integrity.json"
)
DESCRIPTOR_FIELDS = (
    "planned_task_index",
    "issue_id",
    "repository",
    "model_id",
    "taxonomy_condition",
    "instruction_variant",
    "repeat_id",
    "seed",
    "temperature",
    "top_p",
    "max_new_tokens",
)
TASK_ORDER_HASH_FIELDS = DESCRIPTOR_FIELDS[:8]


def _exactly_one(root: Path, pattern: str) -> Path:
    matches = sorted(root.glob(pattern))
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one artifact for {pattern}; found {len(matches)}")
    return matches[0]


def _task_key(record: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(record.get(field) for field in PREDICTION_TASK_KEYS)


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and np.isnan(value):
        return True
    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return bool(result) if isinstance(result, (bool, np.bool_)) else False


def _normalize(value: Any) -> Any:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, np.ndarray):
        return [_normalize(item) for item in value.tolist()]
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _normalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if not _missing(item)
        }
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if _missing(value):
        return None
    return value


def _canonical_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    canonical = canonicalize_prediction_records(records)
    frame = ensure_run_type(pd.DataFrame.from_records(canonical))
    return frame[frame["run_type"].eq("targeted-t3-repeat")].copy()


def _compare_raw_and_parquet(raw: pd.DataFrame, parquet: pd.DataFrame) -> list[str]:
    raw_columns = set(raw.columns) - {"response_headers"}
    parquet_columns = set(parquet.columns)
    if raw_columns != parquet_columns:
        missing = sorted(raw_columns - parquet_columns)
        extra = sorted(parquet_columns - raw_columns)
        raise RuntimeError(
            "Targeted canonical Parquet schema differs from raw canonical records; "
            f"missing={missing}; extra={extra}"
        )
    raw_by_key = {
        _task_key(row): row for row in raw.to_dict(orient="records")
    }
    parquet_by_key = {
        _task_key(row): row for row in parquet.to_dict(orient="records")
    }
    if set(raw_by_key) != set(parquet_by_key):
        raise RuntimeError("Targeted raw and canonical Parquet task-key sets differ")
    compared = sorted(raw_columns)
    for key in sorted(raw_by_key, key=lambda item: tuple(str(part) for part in item)):
        raw_row = raw_by_key[key]
        parquet_row = parquet_by_key[key]
        for field in compared:
            if _normalize(raw_row.get(field)) != _normalize(parquet_row.get(field)):
                raise RuntimeError(
                    "Targeted canonical Parquet value differs from raw canonical record "
                    f"for field {field}"
                )
    return compared


def validate_targeted_prediction_integrity(
    project_root: Path = PROJECT_ROOT,
    *,
    expected_tasks: list[dict[str, Any]] | None = None,
    expected_count: int = EXPECTED_TASKS,
    render: Callable[..., RenderedPrompt] = render_prompt,
    report_path: Path | None = None,
) -> dict[str, Any]:
    """Validate frozen task identity and raw-to-Parquet equality without gold labels."""

    root = project_root.resolve()
    processed_manifest_path = root / "data/manifests/test_processed_manifest.json"
    processed_manifest = orjson.loads(processed_manifest_path.read_bytes())
    inference_path = root / str(processed_manifest["inference_file"])
    if sha256_file(inference_path) != processed_manifest.get("inference_sha256"):
        raise RuntimeError("Label-free test inference file differs from its processed manifest")
    raw_path = _exactly_one(root, "results/raw_predictions/targeted-t3-repeat-*.jsonl")
    parquet_path = _exactly_one(root, "results/raw_predictions/targeted-t3-repeat-*.parquet")
    records = [
        record
        for record in read_jsonl(raw_path)
        if record.get("run_type") == "targeted-t3-repeat"
    ]
    history: dict[tuple[Any, ...], list[tuple[int, dict[str, Any]]]] = {}
    for sequence, record in enumerate(records):
        history.setdefault(_task_key(record), []).append((sequence, record))
    for events in history.values():
        completed = [
            sequence
            for sequence, record in events
            if _missing(record.get("technical_error"))
        ]
        if len(completed) != 1:
            raise RuntimeError(
                "Each targeted task must have exactly one completed response record"
            )
        if any(
            sequence > completed[0] and not _missing(record.get("technical_error"))
            for sequence, record in events
        ):
            raise RuntimeError("A targeted technical-error checkpoint follows completion")
    raw = _canonical_frame(records)
    parquet = ensure_run_type(pd.read_parquet(parquet_path))
    parquet = parquet[parquet["run_type"].eq("targeted-t3-repeat")].copy()
    if len(raw) != expected_count or len(parquet) != expected_count:
        raise RuntimeError("Targeted canonical record count differs from the frozen plan")
    if raw.duplicated(list(PREDICTION_TASK_KEYS)).any():
        raise RuntimeError("Targeted raw canonical task keys are not unique")
    if parquet.duplicated(list(PREDICTION_TASK_KEYS)).any():
        raise RuntimeError("Targeted Parquet task keys are not unique")
    if raw["technical_error"].map(lambda value: not _missing(value)).any():
        raise RuntimeError("Targeted canonical records contain unresolved technical errors")

    if expected_tasks is None:
        verify_targeted_extension_freeze()
        config = load_yaml(TARGETED_PROTOCOL_YAML)
        expected_tasks = build_tasks(config, model_ids=MODELS)
        frozen_plan = targeted_task_plan()
    else:
        expected_descriptors = [
            {
                field: _normalize(task.get(field))
                for field in TASK_ORDER_HASH_FIELDS
            }
            for task in sorted(
                expected_tasks, key=lambda item: int(item["planned_task_index"])
            )
        ]
        frozen_plan = {
            "task_order_sha256": sha256_bytes(
                orjson.dumps(expected_descriptors, option=orjson.OPT_SORT_KEYS)
            )
        }
    if len(expected_tasks) != expected_count:
        raise RuntimeError("Expected targeted descriptor count differs from the frozen plan")

    raw_by_key = {
        _task_key(row): row for row in raw.to_dict(orient="records")
    }
    expected_by_key = {_task_key(task): task for task in expected_tasks}
    if len(expected_by_key) != expected_count or set(raw_by_key) != set(expected_by_key):
        raise RuntimeError("Targeted canonical task keys differ from the frozen descriptors")
    planned_indexes = {
        int(record["planned_task_index"]) for record in raw_by_key.values()
    }
    if planned_indexes != set(range(1, expected_count + 1)):
        raise RuntimeError("Targeted planned-task indexes are not exactly 1..N")
    for key, task in expected_by_key.items():
        record = raw_by_key[key]
        for field in DESCRIPTOR_FIELDS:
            if _normalize(record.get(field)) != _normalize(task.get(field)):
                raise RuntimeError(f"Targeted frozen descriptor mismatch for field {field}")
        rendered = render(
            condition=str(task["taxonomy_condition"]),
            title=str(task["title"]),
            body=str(task["body"]),
            instruction_variant=str(task["instruction_variant"]),
        )
        if record.get("prompt_hash") != rendered.prompt_hash:
            raise RuntimeError("Targeted condition prompt hash differs from frozen rendering")
        if record.get("rendered_prompt_hash") != rendered.rendered_prompt_hash:
            raise RuntimeError("Targeted per-issue rendered prompt hash mismatch")
        if record.get("gold_label_hidden_at_inference") is not True:
            raise RuntimeError("Targeted record does not attest label-free inference")
        if record.get("route_compatible") is False:
            raise RuntimeError("Targeted record contains an incompatible provider route")
        strict = strict_parse(str(record.get("raw_output") or ""))
        lenient = lenient_parse(str(record.get("raw_output") or ""))
        stored_parse = (
            bool(record.get("strict_parse_success")),
            _normalize(record.get("strict_label")),
            bool(record.get("lenient_parse_success")),
            _normalize(record.get("lenient_label")),
            _normalize(record.get("recovery_rule")),
        )
        recomputed_parse = (
            strict.success,
            strict.label,
            lenient.success,
            lenient.label,
            lenient.recovery_rule,
        )
        if stored_parse != recomputed_parse:
            raise RuntimeError("Targeted stored parser fields differ from frozen parsers")

    raw_descriptors = [
        {
            field: _normalize(record.get(field))
            for field in TASK_ORDER_HASH_FIELDS
        }
        for record in sorted(
            raw_by_key.values(), key=lambda item: int(item["planned_task_index"])
        )
    ]
    raw_task_order_sha256 = sha256_bytes(
        orjson.dumps(raw_descriptors, option=orjson.OPT_SORT_KEYS)
    )
    if raw_task_order_sha256 != frozen_plan["task_order_sha256"]:
        raise RuntimeError("Targeted raw descriptor order hash differs from the frozen plan")

    compared_fields = _compare_raw_and_parquet(raw, parquet)
    payload = {
        "schema_version": 1,
        "status": "passed",
        "analysis_status": "pre-result no-gold integrity validation",
        "gold_labels_accessed": False,
        "canonical_tasks": int(len(raw)),
        "unique_task_keys": int(len(raw_by_key)),
        "frozen_task_order_sha256": frozen_plan["task_order_sha256"],
        "raw_task_order_sha256": raw_task_order_sha256,
        "descriptor_fields": list(DESCRIPTOR_FIELDS),
        "raw_parquet_compared_fields": compared_fields,
        "raw_jsonl": {
            "path": raw_path.relative_to(root).as_posix(),
            "sha256": sha256_file(raw_path),
        },
        "canonical_parquet": {
            "path": parquet_path.relative_to(root).as_posix(),
            "sha256": sha256_file(parquet_path),
        },
        "label_free_inference": {
            "path": inference_path.relative_to(root).as_posix(),
            "sha256": sha256_file(inference_path),
        },
    }
    destination = report_path or (
        root / "results/run_manifests/targeted_t3_repeat_integrity.json"
    )
    write_json(destination, payload)
    return payload
