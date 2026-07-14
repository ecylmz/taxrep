from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import orjson
import pandas as pd  # type: ignore[import-untyped]

from taxrep.constants import PROJECT_ROOT
from taxrep.runs import (
    PREDICTION_TASK_KEYS,
    canonicalize_prediction_records,
    derive_run_type,
    ensure_run_type,
)
from taxrep.utils import read_jsonl, sha256_file, sha256_text, write_json

TARGETED_RUN_TYPE = "targeted-t3-repeat"
TARGETED_MODELS = ("deepseek-v4-flash", "kimi-k2.7-code", "glm-5.2")
TARGETED_CONDITIONS = ("T0", "T3")
TARGETED_REPEATS = (1, 2, 3)
AUDIT_STATUS = (
    "post-result targeted-extension operational audit from frozen records; "
    "no new inference and no gold-label access"
)

TASK_HISTORY_COLUMNS = [
    "system_id",
    "taxonomy_condition",
    "repeat_id",
    "raw_checkpoint_record_count",
    "unique_raw_task_count",
    "terminal_error_checkpoint_record_count",
    "unique_terminal_error_task_count",
    "recovered_after_terminal_error_task_count",
    "unresolved_raw_task_count",
    "canonical_task_count",
    "canonical_successful_task_count",
    "canonical_invalid_output_count",
    "canonical_empty_response_count",
    "canonical_rows_with_in_batch_retry",
    "canonical_in_batch_retry_attempt_count",
    "first_success_start_utc",
    "last_success_end_utc",
    "analysis_status",
]

USAGE_COLUMNS = [
    "system_id",
    "taxonomy_condition",
    "repeat_id",
    "canonical_successful_task_count",
    "provider_usage_record_count",
    "prompt_token_observation_count",
    "prompt_tokens_total",
    "prompt_tokens_median",
    "completion_token_observation_count",
    "completion_tokens_total",
    "completion_tokens_median",
    "completion_tokens_maximum",
    "total_token_observation_count",
    "total_tokens_total",
    "total_tokens_median",
    "visible_output_characters_total",
    "visible_output_characters_median",
    "latency_observation_count",
    "latency_ms_median",
    "rows_with_in_batch_retry",
    "in_batch_retry_attempt_count",
    "analysis_status",
]

PROVENANCE_COLUMNS = [
    "invocation_segment",
    "invocation_id_sha256",
    "provider_provenance_segment",
    "system_id",
    "taxonomy_condition",
    "repeat_id",
    "raw_checkpoint_record_count",
    "terminal_error_checkpoint_record_count",
    "canonical_successful_task_count",
    "canonical_invalid_output_count",
    "canonical_empty_response_count",
    "canonical_share_within_invocation_system",
    "first_call_start_utc",
    "last_call_end_utc",
    "raw_invocation_id_exposed",
    "account_identity_available",
    "analysis_status",
]

CALL_BUDGET_COLUMNS = [
    "ledger_segment",
    "scope_type",
    "scope_value",
    "ledger_reservation_count",
    "summary_reservation_count",
    "counts_match",
    "retry_attempt_reservation_count",
    "unique_task_key_hash_count",
    "minimum_ordinal",
    "maximum_ordinal",
    "ordinals_unique",
    "ordinals_contiguous",
    "hard_cap",
    "summary_used",
    "summary_remaining",
    "expected_remaining",
    "within_hard_cap",
    "raw_target_attempt_ordinal_count",
    "unique_raw_target_attempt_ordinal_count",
    "ledger_targeted_inference_count",
    "raw_target_ordinals_match_ledger",
    "unmatched_ledger_targeted_inference_count",
    "allowed_unmatched_targeted_inference_count",
    "raw_target_ordinals_reconciled",
    "overall_reconciled",
    "analysis_status",
]


def _require_columns(frame: pd.DataFrame, columns: Iterable[str], *, name: str) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"{name} is missing required columns: {', '.join(missing)}")


def _task_key(record: dict[str, Any] | pd.Series) -> tuple[Any, ...]:
    return tuple(record.get(field) for field in PREDICTION_TASK_KEYS)


def _technical_error_present(value: Any) -> bool:
    if value is None:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except (TypeError, ValueError):
        pass
    return bool(str(value).strip())


def _normalize_text(value: Any, *, missing: str) -> str:
    if value is None:
        return missing
    try:
        if bool(pd.isna(value)):
            return missing
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text or missing


def _iso_or_empty(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return pd.Timestamp(value).isoformat()


def _write_frame(path: Path, frame: pd.DataFrame, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.reindex(columns=columns).to_csv(
        path,
        index=False,
        lineterminator="\n",
        float_format="%.17g",
        na_rep="",
    )


def _relative(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def _load_targeted_raw(paths: list[Path]) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    records: list[dict[str, Any]] = []
    event_sequence = 0
    for path in paths:
        for source_record in read_jsonl(path):
            record = dict(source_record)
            run_type = record.get("run_type") or derive_run_type(
                str(record.get("run_id", ""))
            )
            if run_type != TARGETED_RUN_TYPE or record.get("dataset_split") != "test":
                continue
            event_sequence += 1
            record["run_type"] = TARGETED_RUN_TYPE
            record["event_sequence"] = event_sequence
            records.append(record)
    if not records:
        raise FileNotFoundError("No targeted extension raw JSONL records found")
    frame = pd.DataFrame.from_records(records)
    _require_columns(
        frame,
        [
            *PREDICTION_TASK_KEYS,
            "raw_output",
            "strict_parse_success",
            "technical_error",
            "start_timestamp",
            "end_timestamp",
            "invocation_id",
            "provider_provenance_segment",
            "completion_call_ordinals",
            "retry_count",
        ],
        name="targeted raw history",
    )
    frame["technical_error_present"] = frame["technical_error"].map(
        _technical_error_present
    )
    frame["start_dt"] = pd.to_datetime(
        frame["start_timestamp"], utc=True, errors="coerce"
    )
    frame["end_dt"] = pd.to_datetime(frame["end_timestamp"], utc=True, errors="coerce")
    return records, frame


def _canonical_from_raw(records: list[dict[str, Any]]) -> pd.DataFrame:
    clean_records = [
        {key: value for key, value in record.items() if key != "event_sequence"}
        for record in records
    ]
    frame = ensure_run_type(
        pd.DataFrame.from_records(canonicalize_prediction_records(clean_records))
    )
    frame = frame[frame["run_type"].eq(TARGETED_RUN_TYPE)].copy()
    if frame.empty:
        raise ValueError("Targeted raw history produced no canonical records")
    duplicated = frame.duplicated(list(PREDICTION_TASK_KEYS), keep=False)
    if duplicated.any():
        raise ValueError(
            "Targeted canonicalization produced duplicate task keys: "
            f"{int(duplicated.sum())} rows"
        )
    frame["technical_error_present"] = frame["technical_error"].map(
        _technical_error_present
    )
    return frame


def _validate_canonical_parquet(paths: list[Path], canonical: pd.DataFrame) -> pd.DataFrame:
    if not paths:
        raise FileNotFoundError("No targeted extension canonical Parquet file found")
    parquet = ensure_run_type(
        pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True)
    )
    parquet = parquet[parquet["run_type"].eq(TARGETED_RUN_TYPE)].copy()
    if parquet.empty:
        raise ValueError("Targeted canonical Parquet contains no targeted rows")
    duplicated = parquet.duplicated(list(PREDICTION_TASK_KEYS), keep=False)
    if duplicated.any():
        raise ValueError(
            "Targeted canonical Parquet contains duplicate task keys: "
            f"{int(duplicated.sum())} rows"
        )
    raw_keys = {_task_key(record) for record in canonical.to_dict(orient="records")}
    parquet_keys = {_task_key(record) for record in parquet.to_dict(orient="records")}
    if raw_keys != parquet_keys:
        raise ValueError(
            "Targeted canonical Parquet task keys do not match raw-history canonicalization"
        )
    return parquet


def _cell_grid(
    canonical: pd.DataFrame,
    *,
    expected_models: tuple[str, ...],
    expected_conditions: tuple[str, ...],
    expected_repeats: tuple[int, ...],
) -> list[tuple[str, str, int]]:
    models = sorted(set(expected_models) | set(canonical["model_id"].astype(str)))
    conditions = list(expected_conditions)
    conditions.extend(
        sorted(set(canonical["taxonomy_condition"].astype(str)) - set(conditions))
    )
    repeats = sorted(
        set(expected_repeats)
        | set(pd.to_numeric(canonical["repeat_id"], errors="raise").astype(int))
    )
    return [
        (model_id, condition, repeat_id)
        for model_id in models
        for condition in conditions
        for repeat_id in repeats
    ]


def _task_history_audit(
    canonical: pd.DataFrame,
    raw: pd.DataFrame,
    *,
    cells: list[tuple[str, str, int]],
) -> pd.DataFrame:
    states: dict[tuple[Any, ...], dict[str, list[int]]] = {}
    for record in raw.to_dict(orient="records"):
        state = states.setdefault(_task_key(record), {"errors": [], "successes": []})
        target = "errors" if record["technical_error_present"] else "successes"
        state[target].append(int(record["event_sequence"]))

    rows: list[dict[str, Any]] = []
    for system_id, condition, repeat_id in cells:
        canonical_group = canonical[
            canonical["model_id"].astype(str).eq(system_id)
            & canonical["taxonomy_condition"].astype(str).eq(condition)
            & pd.to_numeric(canonical["repeat_id"], errors="coerce").eq(repeat_id)
        ]
        raw_group = raw[
            raw["model_id"].astype(str).eq(system_id)
            & raw["taxonomy_condition"].astype(str).eq(condition)
            & pd.to_numeric(raw["repeat_id"], errors="coerce").eq(repeat_id)
        ]
        matching_states = [
            state
            for key, state in states.items()
            if str(key[3]) == system_id
            and str(key[4]) == condition
            and int(key[6]) == repeat_id
        ]
        successful = canonical_group[
            ~canonical_group["technical_error_present"].astype(bool)
        ]
        retry_counts = pd.to_numeric(
            successful.get("retry_count", pd.Series(dtype=float)), errors="coerce"
        ).fillna(0)
        first_start = pd.to_datetime(
            successful.get("start_timestamp", pd.Series(dtype=object)),
            utc=True,
            errors="coerce",
        ).min()
        last_end = pd.to_datetime(
            successful.get("end_timestamp", pd.Series(dtype=object)),
            utc=True,
            errors="coerce",
        ).max()
        strict_success = successful.get(
            "strict_parse_success", pd.Series(False, index=successful.index)
        ).fillna(False).astype(bool)
        raw_output = successful.get(
            "raw_output", pd.Series("", index=successful.index)
        ).fillna("").astype(str)
        rows.append(
            {
                "system_id": system_id,
                "taxonomy_condition": condition,
                "repeat_id": repeat_id,
                "raw_checkpoint_record_count": int(raw_group.shape[0]),
                "unique_raw_task_count": len(matching_states),
                "terminal_error_checkpoint_record_count": int(
                    raw_group["technical_error_present"].sum()
                ),
                "unique_terminal_error_task_count": sum(
                    bool(state["errors"]) for state in matching_states
                ),
                "recovered_after_terminal_error_task_count": sum(
                    bool(state["errors"])
                    and bool(state["successes"])
                    and max(state["successes"]) > min(state["errors"])
                    for state in matching_states
                ),
                "unresolved_raw_task_count": sum(
                    bool(state["errors"]) and not state["successes"]
                    for state in matching_states
                ),
                "canonical_task_count": int(canonical_group.shape[0]),
                "canonical_successful_task_count": int(successful.shape[0]),
                "canonical_invalid_output_count": int((~strict_success).sum()),
                "canonical_empty_response_count": int(raw_output.str.strip().eq("").sum()),
                "canonical_rows_with_in_batch_retry": int((retry_counts > 0).sum()),
                "canonical_in_batch_retry_attempt_count": int(retry_counts.sum()),
                "first_success_start_utc": _iso_or_empty(first_start),
                "last_success_end_utc": _iso_or_empty(last_end),
                "analysis_status": AUDIT_STATUS,
            }
        )
    return pd.DataFrame(rows, columns=TASK_HISTORY_COLUMNS)


def _usage_value(record: pd.Series, key: str, top_level: str) -> float | None:
    usage = record.get("provider_usage")
    value = usage.get(key) if isinstance(usage, dict) else None
    if value is None:
        value = record.get(top_level)
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(numeric) else float(numeric)


def _numeric_summary(values: list[float]) -> tuple[int, float, float | None, float | None]:
    if not values:
        return 0, 0.0, None, None
    array = np.asarray(values, dtype=float)
    return len(values), float(array.sum()), float(np.median(array)), float(array.max())


def _usage_audit(
    canonical: pd.DataFrame,
    *,
    cells: list[tuple[str, str, int]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for system_id, condition, repeat_id in cells:
        group = canonical[
            canonical["model_id"].astype(str).eq(system_id)
            & canonical["taxonomy_condition"].astype(str).eq(condition)
            & pd.to_numeric(canonical["repeat_id"], errors="coerce").eq(repeat_id)
            & ~canonical["technical_error_present"].astype(bool)
        ]
        prompt_values: list[float] = []
        completion_values: list[float] = []
        total_values: list[float] = []
        for _, record in group.iterrows():
            prompt = _usage_value(record, "prompt_tokens", "input_token_count")
            completion = _usage_value(
                record, "completion_tokens", "output_token_count"
            )
            total = _usage_value(record, "total_tokens", "__missing_total_tokens__")
            if prompt is not None:
                prompt_values.append(prompt)
            if completion is not None:
                completion_values.append(completion)
            if total is not None:
                total_values.append(total)
        prompt_n, prompt_sum, prompt_median, _prompt_max = _numeric_summary(prompt_values)
        completion_n, completion_sum, completion_median, completion_max = (
            _numeric_summary(completion_values)
        )
        total_n, total_sum, total_median, _total_max = _numeric_summary(total_values)
        visible_lengths = (
            group.get("raw_output", pd.Series("", index=group.index))
            .fillna("")
            .astype(str)
            .str.len()
            .to_numpy(dtype=float)
        )
        latency = pd.to_numeric(
            group.get("latency_ms", pd.Series(dtype=float)), errors="coerce"
        ).dropna()
        retry_counts = pd.to_numeric(
            group.get("retry_count", pd.Series(dtype=float)), errors="coerce"
        ).fillna(0)
        provider_usage_count = int(
            group.get("provider_usage", pd.Series(dtype=object)).map(
                lambda value: isinstance(value, dict) and bool(value)
            ).sum()
        )
        rows.append(
            {
                "system_id": system_id,
                "taxonomy_condition": condition,
                "repeat_id": repeat_id,
                "canonical_successful_task_count": int(group.shape[0]),
                "provider_usage_record_count": provider_usage_count,
                "prompt_token_observation_count": prompt_n,
                "prompt_tokens_total": prompt_sum,
                "prompt_tokens_median": prompt_median,
                "completion_token_observation_count": completion_n,
                "completion_tokens_total": completion_sum,
                "completion_tokens_median": completion_median,
                "completion_tokens_maximum": completion_max,
                "total_token_observation_count": total_n,
                "total_tokens_total": total_sum,
                "total_tokens_median": total_median,
                "visible_output_characters_total": float(visible_lengths.sum()),
                "visible_output_characters_median": (
                    float(np.median(visible_lengths)) if len(visible_lengths) else None
                ),
                "latency_observation_count": int(latency.shape[0]),
                "latency_ms_median": float(latency.median()) if not latency.empty else None,
                "rows_with_in_batch_retry": int((retry_counts > 0).sum()),
                "in_batch_retry_attempt_count": int(retry_counts.sum()),
                "analysis_status": AUDIT_STATUS,
            }
        )
    return pd.DataFrame(rows, columns=USAGE_COLUMNS)


def _invocation_lookup(raw: pd.DataFrame) -> dict[str, str]:
    working = raw.copy()
    working["invocation_marker"] = working["invocation_id"].map(
        lambda value: _normalize_text(value, missing="__missing_invocation_id__")
    )
    ordering: list[tuple[pd.Timestamp, int, str]] = []
    for marker, group in working.groupby("invocation_marker", sort=True):
        starts = group["start_dt"].dropna()
        first_start = (
            starts.min() if not starts.empty else pd.Timestamp.max.tz_localize("UTC")
        )
        ordering.append((first_start, int(group["event_sequence"].min()), str(marker)))
    return {
        marker: f"invocation_{index:03d}"
        for index, (_start, _sequence, marker) in enumerate(sorted(ordering), start=1)
    }


def _provenance_audit(canonical: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    lookup = _invocation_lookup(raw)
    raw_working = raw.copy()
    canonical_working = canonical.copy()
    for frame in (raw_working, canonical_working):
        frame["invocation_marker"] = frame["invocation_id"].map(
            lambda value: _normalize_text(value, missing="__missing_invocation_id__")
        )
        frame["invocation_segment"] = frame["invocation_marker"].map(lookup)
        frame["provenance_marker"] = frame["provider_provenance_segment"].map(
            lambda value: _normalize_text(
                value, missing="__missing_provider_provenance_segment__"
            )
        )
    canonical_working = canonical_working[
        ~canonical_working["technical_error_present"].astype(bool)
    ].copy()

    group_columns = [
        "invocation_marker",
        "invocation_segment",
        "provenance_marker",
        "model_id",
        "taxonomy_condition",
        "repeat_id",
    ]
    raw_groups = {keys: group for keys, group in raw_working.groupby(group_columns)}
    canonical_groups = {
        keys: group for keys, group in canonical_working.groupby(group_columns)
    }
    keys_union = sorted(set(raw_groups) | set(canonical_groups))
    denominator = canonical_working.groupby(
        ["invocation_marker", "model_id"], sort=True
    ).size()
    rows: list[dict[str, Any]] = []
    for keys in keys_union:
        marker, segment, provenance, system_id, condition, repeat_id = keys
        raw_group = raw_groups.get(keys, raw_working.iloc[0:0])
        canonical_group = canonical_groups.get(keys, canonical_working.iloc[0:0])
        strict_success = canonical_group.get(
            "strict_parse_success", pd.Series(False, index=canonical_group.index)
        ).fillna(False).astype(bool)
        raw_output = canonical_group.get(
            "raw_output", pd.Series("", index=canonical_group.index)
        ).fillna("").astype(str)
        cell_denominator = int(denominator.get((marker, system_id), 0))
        rows.append(
            {
                "invocation_segment": segment,
                "invocation_id_sha256": sha256_text(str(marker)),
                "provider_provenance_segment": provenance,
                "system_id": system_id,
                "taxonomy_condition": condition,
                "repeat_id": int(repeat_id),
                "raw_checkpoint_record_count": int(raw_group.shape[0]),
                "terminal_error_checkpoint_record_count": int(
                    raw_group.get(
                        "technical_error_present", pd.Series(dtype=bool)
                    ).sum()
                ),
                "canonical_successful_task_count": int(canonical_group.shape[0]),
                "canonical_invalid_output_count": int((~strict_success).sum()),
                "canonical_empty_response_count": int(
                    raw_output.str.strip().eq("").sum()
                ),
                "canonical_share_within_invocation_system": (
                    float(canonical_group.shape[0] / cell_denominator)
                    if cell_denominator
                    else 0.0
                ),
                "first_call_start_utc": _iso_or_empty(raw_group["start_dt"].min()),
                "last_call_end_utc": _iso_or_empty(raw_group["end_dt"].max()),
                "raw_invocation_id_exposed": False,
                "account_identity_available": False,
                "analysis_status": AUDIT_STATUS,
            }
        )
    return pd.DataFrame(rows, columns=PROVENANCE_COLUMNS)


def _ordinal_values(value: Any) -> list[int]:
    if isinstance(value, (list, tuple, np.ndarray)):
        return [int(item) for item in value]
    return []


def _call_budget_audit(
    raw: pd.DataFrame,
    *,
    summary: dict[str, Any],
    ledger: pd.DataFrame,
    ledger_segment: str = "original",
    allowed_unmatched_targeted_inference: int = 0,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    _require_columns(
        ledger,
        ["ordinal", "kind", "model_id", "attempt", "task_key_sha256"],
        name="targeted completion-call ledger",
    )
    ordinals = pd.to_numeric(ledger["ordinal"], errors="raise").astype(int).tolist()
    unique_ordinals = len(set(ordinals)) == len(ordinals)
    maximum_ordinal = max(ordinals, default=0)
    minimum_ordinal = min(ordinals, default=0)
    contiguous = sorted(ordinals) == list(range(1, maximum_ordinal + 1))
    hard_cap = int(summary["hard_cap"])
    summary_used = int(summary["used"])
    summary_remaining = int(summary["remaining"])
    expected_remaining = hard_cap - summary_used
    ledger_by_kind = Counter(ledger["kind"].astype(str))
    ledger_by_model = Counter(ledger["model_id"].astype(str))
    summary_by_kind = {
        str(key): int(value) for key, value in dict(summary.get("by_kind", {})).items()
    }
    summary_by_model = {
        str(key): int(value) for key, value in dict(summary.get("by_model", {})).items()
    }
    raw_target_ordinals = [
        ordinal
        for value in raw["completion_call_ordinals"]
        for ordinal in _ordinal_values(value)
    ]
    ledger_target_ordinals = set(
        pd.to_numeric(
            ledger.loc[ledger["kind"].astype(str).eq("targeted_inference"), "ordinal"],
            errors="raise",
        ).astype(int)
    )
    raw_target_match = set(raw_target_ordinals) == ledger_target_ordinals and len(
        raw_target_ordinals
    ) == len(set(raw_target_ordinals))
    unmatched_ledger_targeted = ledger_target_ordinals - set(raw_target_ordinals)
    unknown_raw_targeted = set(raw_target_ordinals) - ledger_target_ordinals
    raw_target_reconciled = (
        not unknown_raw_targeted
        and len(raw_target_ordinals) == len(set(raw_target_ordinals))
        and len(unmatched_ledger_targeted)
        == int(allowed_unmatched_targeted_inference)
    )
    maps_match = ledger_by_kind == Counter(summary_by_kind) and ledger_by_model == Counter(
        summary_by_model
    )
    overall_reconciled = (
        summary_used == len(ledger)
        and summary_remaining == expected_remaining
        and unique_ordinals
        and contiguous
        and maximum_ordinal == summary_used
        and summary_used <= hard_cap
        and maps_match
        and raw_target_reconciled
    )

    scopes: list[tuple[str, str, pd.DataFrame, int | None]] = [
        ("overall", "all", ledger, summary_used)
    ]
    for kind in sorted(set(ledger_by_kind) | set(summary_by_kind)):
        scopes.append(
            (
                "kind",
                kind,
                ledger[ledger["kind"].astype(str).eq(kind)],
                summary_by_kind.get(kind, 0),
            )
        )
    for model_id in sorted(set(ledger_by_model) | set(summary_by_model)):
        scopes.append(
            (
                "system",
                model_id,
                ledger[ledger["model_id"].astype(str).eq(model_id)],
                summary_by_model.get(model_id, 0),
            )
        )

    rows: list[dict[str, Any]] = []
    for scope_type, scope_value, group, expected in scopes:
        attempts = pd.to_numeric(group["attempt"], errors="coerce").fillna(0)
        rows.append(
            {
                "ledger_segment": ledger_segment,
                "scope_type": scope_type,
                "scope_value": scope_value,
                "ledger_reservation_count": int(group.shape[0]),
                "summary_reservation_count": expected,
                "counts_match": (
                    int(group.shape[0]) == expected if expected is not None else None
                ),
                "retry_attempt_reservation_count": int((attempts > 1).sum()),
                "unique_task_key_hash_count": int(group["task_key_sha256"].nunique()),
                "minimum_ordinal": minimum_ordinal,
                "maximum_ordinal": maximum_ordinal,
                "ordinals_unique": unique_ordinals,
                "ordinals_contiguous": contiguous,
                "hard_cap": hard_cap,
                "summary_used": summary_used,
                "summary_remaining": summary_remaining,
                "expected_remaining": expected_remaining,
                "within_hard_cap": summary_used <= hard_cap,
                "raw_target_attempt_ordinal_count": len(raw_target_ordinals),
                "unique_raw_target_attempt_ordinal_count": len(
                    set(raw_target_ordinals)
                ),
                "ledger_targeted_inference_count": len(ledger_target_ordinals),
                "raw_target_ordinals_match_ledger": raw_target_match,
                "unmatched_ledger_targeted_inference_count": len(
                    unmatched_ledger_targeted
                ),
                "allowed_unmatched_targeted_inference_count": int(
                    allowed_unmatched_targeted_inference
                ),
                "raw_target_ordinals_reconciled": raw_target_reconciled,
                "overall_reconciled": overall_reconciled,
                "analysis_status": AUDIT_STATUS,
            }
        )
    details = {
        "ledger_segment": ledger_segment,
        "hard_cap": hard_cap,
        "used": summary_used,
        "remaining": summary_remaining,
        "ledger_reservations": int(ledger.shape[0]),
        "provider_health_reservations": int(ledger_by_kind.get("provider_health", 0)),
        "targeted_inference_reservations": int(
            ledger_by_kind.get("targeted_inference", 0)
        ),
        "retry_attempt_reservations": int(
            (pd.to_numeric(ledger["attempt"], errors="coerce").fillna(0) > 1).sum()
        ),
        "raw_target_attempt_ordinals": len(raw_target_ordinals),
        "raw_target_ordinals_match_ledger": raw_target_match,
        "unmatched_ledger_targeted_inference_count": len(
            unmatched_ledger_targeted
        ),
        "allowed_unmatched_targeted_inference_count": int(
            allowed_unmatched_targeted_inference
        ),
        "raw_target_ordinals_reconciled": raw_target_reconciled,
        "overall_reconciled": overall_reconciled,
    }
    return pd.DataFrame(rows, columns=CALL_BUDGET_COLUMNS), details


def run_targeted_operational_audit(
    project_root: Path = PROJECT_ROOT,
    *,
    expected_models: tuple[str, ...] = TARGETED_MODELS,
    expected_conditions: tuple[str, ...] = TARGETED_CONDITIONS,
    expected_repeats: tuple[int, ...] = TARGETED_REPEATS,
    expected_tasks_per_cell: int | None = 150,
    require_complete: bool = True,
) -> dict[str, Any]:
    """Audit targeted extension operations without inference or gold-label access."""

    root = Path(project_root).resolve()
    raw_dir = root / "results" / "raw_predictions"
    jsonl_paths = sorted(raw_dir.glob("targeted-t3-repeat-*.jsonl"))
    parquet_paths = sorted(raw_dir.glob("targeted-t3-repeat-*.parquet"))
    original_budget_summary_path = (
        root / "results" / "run_manifests" / "targeted_t3_repeat_call_budget.json"
    )
    original_ledger_path = (
        root / "results" / "run_manifests" / "targeted_t3_repeat_call_ledger.jsonl"
    )
    recovery_budget_summary_path = (
        root
        / "results"
        / "run_manifests"
        / "targeted_t3_repeat_recovery_call_budget.json"
    )
    recovery_ledger_path = (
        root
        / "results"
        / "run_manifests"
        / "targeted_t3_repeat_recovery_call_ledger.jsonl"
    )
    if not original_budget_summary_path.exists():
        raise FileNotFoundError(original_budget_summary_path)
    if not original_ledger_path.exists():
        raise FileNotFoundError(original_ledger_path)

    records, raw = _load_targeted_raw(jsonl_paths)
    canonical = _canonical_from_raw(records)
    parquet = _validate_canonical_parquet(parquet_paths, canonical)
    cells = _cell_grid(
        canonical,
        expected_models=expected_models,
        expected_conditions=expected_conditions,
        expected_repeats=expected_repeats,
    )
    task_history = _task_history_audit(canonical, raw, cells=cells)
    usage = _usage_audit(canonical, cells=cells)
    provenance = _provenance_audit(canonical, raw)
    segment_specs: list[tuple[str, Path, Path, pd.DataFrame, int]] = []
    recovery_present = recovery_budget_summary_path.exists() or recovery_ledger_path.exists()
    if recovery_present and not (
        recovery_budget_summary_path.exists() and recovery_ledger_path.exists()
    ):
        raise FileNotFoundError("Recovery budget summary and ledger must both exist")
    if recovery_present:
        provenance_values = raw.get(
            "provider_provenance_segment", pd.Series("", index=raw.index)
        ).fillna("").astype(str)
        recovery_mask = provenance_values.eq(
            "targeted-t3-repeat-access-window-2-recovery"
        )
        segment_specs.extend(
            [
                (
                    "stopped_access_window_1",
                    original_budget_summary_path,
                    original_ledger_path,
                    raw.loc[~recovery_mask].copy(),
                    3,
                ),
                (
                    "recovery_access_window_2",
                    recovery_budget_summary_path,
                    recovery_ledger_path,
                    raw.loc[recovery_mask].copy(),
                    0,
                ),
            ]
        )
    else:
        segment_specs.append(
            (
                "original",
                original_budget_summary_path,
                original_ledger_path,
                raw,
                0,
            )
        )

    call_budget_frames: list[pd.DataFrame] = []
    segment_details: dict[str, Any] = {}
    budget_input_paths: list[Path] = []
    for segment, summary_path, ledger_path, segment_raw, allowed_unmatched in segment_specs:
        budget_summary = orjson.loads(summary_path.read_bytes())
        if not isinstance(budget_summary, dict):
            raise ValueError("Targeted call-budget summary must contain one JSON object")
        ledger_records = read_jsonl(ledger_path)
        if not ledger_records:
            raise ValueError("Targeted completion-call ledger is empty")
        ledger = pd.DataFrame.from_records(ledger_records)
        budget_frame, details = _call_budget_audit(
            segment_raw,
            summary=budget_summary,
            ledger=ledger,
            ledger_segment=segment,
            allowed_unmatched_targeted_inference=allowed_unmatched,
        )
        call_budget_frames.append(budget_frame)
        segment_details[segment] = details
        budget_input_paths.extend([summary_path, ledger_path])
    call_budget = pd.concat(call_budget_frames, ignore_index=True)
    call_budget_details: dict[str, Any] = {
        "segments": segment_details,
        "overall_reconciled": all(
            bool(details["overall_reconciled"]) for details in segment_details.values()
        ),
        "ledger_reservations": sum(
            int(details["ledger_reservations"]) for details in segment_details.values()
        ),
        "provider_health_reservations": sum(
            int(details["provider_health_reservations"])
            for details in segment_details.values()
        ),
        "targeted_inference_reservations": sum(
            int(details["targeted_inference_reservations"])
            for details in segment_details.values()
        ),
        "retry_attempt_reservations": sum(
            int(details["retry_attempt_reservations"])
            for details in segment_details.values()
        ),
    }
    if recovery_present:
        recovery_used = int(segment_details["recovery_access_window_2"]["used"])
        call_budget_details.update(
            {
                "historical_http_attempt_count_status": "not reconstructible",
                "historical_http_attempt_mechanical_range": [1_643, 4_938],
                "recovery_sdk_max_retries": 0,
                "recovery_outbound_attempt_upper_bound": recovery_used,
                "conservative_revision_http_attempt_upper_bound": 4_938
                + recovery_used,
                "revision_http_attempt_hard_cap": 6_298,
            }
        )

    table_dir = root / "results" / "tables"
    output_specs = {
        "task_history": (
            table_dir / "targeted_t3_repeat_task_history.csv",
            task_history,
            TASK_HISTORY_COLUMNS,
        ),
        "usage": (
            table_dir / "targeted_t3_repeat_usage.csv",
            usage,
            USAGE_COLUMNS,
        ),
        "invocation_provenance": (
            table_dir / "targeted_t3_repeat_invocation_provenance.csv",
            provenance,
            PROVENANCE_COLUMNS,
        ),
        "call_budget_reconciliation": (
            table_dir / "targeted_t3_repeat_call_budget_audit.csv",
            call_budget,
            CALL_BUDGET_COLUMNS,
        ),
    }
    for path, frame, columns in output_specs.values():
        _write_frame(path, frame, columns)

    successful_counts = task_history["canonical_successful_task_count"]
    expected_cell_count = (
        len(expected_models) * len(expected_conditions) * len(expected_repeats)
    )
    expected_total = (
        expected_cell_count * expected_tasks_per_cell
        if expected_tasks_per_cell is not None
        else None
    )
    if require_complete:
        if task_history.shape[0] != expected_cell_count:
            raise ValueError("Targeted audit cell count differs from the frozen 18-cell grid")
        if expected_tasks_per_cell is None:
            raise ValueError("A complete targeted audit requires an expected cell size")
        if not task_history["canonical_task_count"].eq(expected_tasks_per_cell).all():
            raise ValueError("Targeted canonical task counts are not balanced by frozen cell")
        if not successful_counts.eq(expected_tasks_per_cell).all():
            raise ValueError("Targeted audit contains unresolved canonical technical errors")
        if int(canonical.shape[0]) != expected_total:
            raise ValueError("Targeted canonical task total differs from the frozen plan")
        if not call_budget_details["overall_reconciled"]:
            raise ValueError("Targeted completion-call budget does not reconcile")
    input_paths = [
        *jsonl_paths,
        *parquet_paths,
        *budget_input_paths,
    ]
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "analysis_status": AUDIT_STATUS,
        "run_type": TARGETED_RUN_TYPE,
        "gold_labels_accessed": False,
        "inference_calls_made": 0,
        "determinism": (
            "no generated-at timestamp; inputs, groups, and outputs are sorted; "
            "stochastic analysis is not used"
        ),
        "raw_checkpoint_record_count": int(raw.shape[0]),
        "canonical_task_count": int(canonical.shape[0]),
        "canonical_parquet_task_count": int(parquet.shape[0]),
        "canonical_successful_task_count": int(successful_counts.sum()),
        "unique_issue_count": int(canonical["issue_id"].nunique()),
        "expected_cell_count": expected_cell_count,
        "observed_audit_cell_count": int(task_history.shape[0]),
        "expected_tasks_per_cell": expected_tasks_per_cell,
        "expected_canonical_task_count": expected_total,
        "minimum_canonical_tasks_per_cell": int(
            task_history["canonical_task_count"].min()
        ),
        "maximum_canonical_tasks_per_cell": int(
            task_history["canonical_task_count"].max()
        ),
        "minimum_successful_tasks_per_cell": int(successful_counts.min()),
        "maximum_successful_tasks_per_cell": int(successful_counts.max()),
        "terminal_error_checkpoint_record_count": int(
            task_history["terminal_error_checkpoint_record_count"].sum()
        ),
        "unique_terminal_error_task_count": int(
            task_history["unique_terminal_error_task_count"].sum()
        ),
        "recovered_after_terminal_error_task_count": int(
            task_history["recovered_after_terminal_error_task_count"].sum()
        ),
        "unresolved_raw_task_count": int(
            task_history["unresolved_raw_task_count"].sum()
        ),
        "canonical_invalid_output_count": int(
            task_history["canonical_invalid_output_count"].sum()
        ),
        "canonical_empty_response_count": int(
            task_history["canonical_empty_response_count"].sum()
        ),
        "call_budget": call_budget_details,
        "provenance": {
            "raw_invocation_id_values_exposed": False,
            "account_identity_available": False,
            "invocation_ids_represented_by": "chronological ordinal and SHA-256",
        },
        "inputs": [
            {"path": _relative(path, root), "sha256": sha256_file(path)}
            for path in sorted(input_paths)
        ],
        "outputs": {},
        "summary_path": "results/statistics/targeted_t3_repeat_operational_audit.json",
    }
    for name, (path, frame, _columns) in output_specs.items():
        payload["outputs"][name] = {
            "path": _relative(path, root),
            "rows": int(frame.shape[0]),
            "sha256": sha256_file(path),
        }

    summary_path = root / payload["summary_path"]
    write_json(summary_path, payload)
    return payload
