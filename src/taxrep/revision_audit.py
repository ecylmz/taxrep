from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd  # type: ignore[import-untyped]
from sklearn.metrics import f1_score  # type: ignore[import-untyped]

from taxrep.constants import LABELS, PROJECT_ROOT
from taxrep.metrics import normalize_predictions
from taxrep.runs import PREDICTION_TASK_KEYS, derive_run_type, ensure_run_type
from taxrep.utils import read_jsonl, sha256_file, write_json

CONDITIONS = ("T0", "T1", "T2", "T3", "T4")
ENRICHED_CONDITIONS = CONDITIONS[1:]
GLM_MODEL_ID = "glm-5.2"
ACCESS_WINDOW_HOURS = 6
AUDIT_STATUS = "post-result operational audit from frozen predictions; no new inference"
DESCRIPTIVE_STATUS = (
    "post-result descriptive sensitivity; no causal or population-inference claim"
)
ACCESS_WINDOW_RULE = (
    "fixed six-hour UTC calendar windows using successful-call start_timestamp; "
    "boundaries are [00:00,06:00), [06:00,12:00), [12:00,18:00), and "
    "[18:00,24:00) UTC"
)
PROVENANCE_RULE = (
    "chronological ordinal within system of the legacy hardware_snapshot_id invocation "
    "marker; raw marker values are suppressed and no account identity is inferred"
)
PAIRING_RULE = (
    "each Tj-T0 contrast uses its own issue-id intersection within the same provenance "
    "subset; no five-condition intersection is required"
)

TASK_AUDIT_COLUMNS = [
    "system_id",
    "taxonomy_condition",
    "canonical_task_count",
    "unique_raw_task_count",
    "raw_checkpoint_record_count",
    "terminal_error_checkpoint_record_count",
    "unique_terminal_error_task_count",
    "recovered_after_terminal_error_task_count",
    "unresolved_raw_task_count",
    "canonical_invalid_output_count",
    "canonical_empty_response_count",
    "first_success_start_utc",
    "last_success_end_utc",
    "analysis_status",
]
RESPONSE_MODEL_COLUMNS = [
    "system_id",
    "taxonomy_condition",
    "provider_response_model",
    "canonical_task_count",
    "share_within_system_condition",
    "analysis_status",
]
PROVENANCE_COLUMNS = [
    "system_id",
    "invocation_segment",
    "taxonomy_condition",
    "segment_first_start_utc",
    "segment_last_end_utc",
    "raw_checkpoint_record_count",
    "unique_raw_task_count",
    "terminal_error_checkpoint_record_count",
    "unique_terminal_error_task_count",
    "canonical_successful_task_count",
    "canonical_condition_share_within_segment",
    "provenance_basis",
    "raw_marker_exposed",
    "analysis_status",
]
ACCESS_WINDOW_COLUMNS = [
    "system_id",
    "access_window_start_utc",
    "access_window_end_exclusive_utc",
    "taxonomy_condition",
    "canonical_task_count",
    "total_system_window_tasks",
    "condition_share_within_system_window",
    "equal_share_reference",
    "share_deviation_from_equal",
    "exact_macro_f1_descriptive",
    "invalid_rate_descriptive",
    "gold_bug_count",
    "gold_feature_count",
    "gold_question_count",
    "window_rule",
    "analysis_status",
]
GLM_PAIRWISE_COLUMNS = [
    "system_id",
    "provenance_dimension",
    "provenance_subset",
    "comparison",
    "taxonomy_condition",
    "matched_issue_count",
    "matched_repository_count",
    "minimum_matched_issues_per_repository",
    "maximum_matched_issues_per_repository",
    "t0_exact_macro_f1_pooled",
    "condition_exact_macro_f1_pooled",
    "pooled_delta_macro_f1",
    "equal_repository_mean_delta_macro_f1",
    "negative_repository_delta_count",
    "pairing_rule",
    "analysis_status",
]
LEAVE_ONE_REPOSITORY_COLUMNS = [
    "excluded_repository",
    "comparison",
    "observed_delta_macro_f1",
    "negative_repository_system_cell_count",
    "remaining_repository_system_cell_count",
    "remaining_repository_count",
    "remaining_system_count",
    "interval_method",
    "analysis_status",
]
LEAVE_ONE_SYSTEM_COLUMNS = [
    "excluded_system",
    "comparison",
    "observed_delta_macro_f1",
    "negative_repository_system_cell_count",
    "remaining_repository_system_cell_count",
    "remaining_repository_count",
    "remaining_system_count",
    "interval_method",
    "analysis_status",
]
ROBUSTNESS_SAMPLE_COLUMNS = [
    "source",
    "comparison",
    "observed_delta_macro_f1",
    "median_repository_system_cell_delta_macro_f1",
    "negative_repository_system_cell_count",
    "repository_system_cell_count",
    "sample_issue_count",
    "interval_method",
    "analysis_status",
]


def _require_columns(frame: pd.DataFrame, columns: Iterable[str], *, name: str) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"{name} is missing required columns: {', '.join(missing)}")


def _task_key(record: dict[str, Any] | pd.Series) -> tuple[Any, ...]:
    return tuple(record.get(field) for field in PREDICTION_TASK_KEYS)


def _is_technical_error(value: Any) -> bool:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return False
    return bool(str(value).strip())


def _normalize_segment_marker(value: Any) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "__missing_invocation_marker__"
    text = str(value).strip()
    return text or "__missing_invocation_marker__"


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


def _load_canonical(paths: list[Path], *, run_type: str) -> pd.DataFrame:
    if not paths:
        raise FileNotFoundError(f"No {run_type} canonical Parquet files found")
    frame = ensure_run_type(
        pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True)
    )
    frame = frame[frame["run_type"].eq(run_type)].copy()
    if frame.empty:
        raise ValueError(f"No canonical rows remained for run_type={run_type}")
    return frame


def _load_main_raw(paths: list[Path]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    event_sequence = 0
    for path in paths:
        for record in read_jsonl(path):
            record_run_type = record.get("run_type") or derive_run_type(
                str(record.get("run_id", ""))
            )
            if record_run_type != "main":
                continue
            event_sequence += 1
            rows.append(
                {
                    **{field: record.get(field) for field in PREDICTION_TASK_KEYS},
                    "start_timestamp": record.get("start_timestamp"),
                    "end_timestamp": record.get("end_timestamp"),
                    "technical_error_present": _is_technical_error(
                        record.get("technical_error")
                    ),
                    "hardware_snapshot_id": record.get("hardware_snapshot_id"),
                    "event_sequence": event_sequence,
                }
            )
    if not rows:
        raise FileNotFoundError("No main raw JSONL records found")
    frame = pd.DataFrame(rows)
    _require_columns(
        frame,
        [*PREDICTION_TASK_KEYS, "technical_error_present", "event_sequence"],
        name="main raw history",
    )
    frame["start_dt"] = pd.to_datetime(frame["start_timestamp"], utc=True, errors="coerce")
    frame["end_dt"] = pd.to_datetime(frame["end_timestamp"], utc=True, errors="coerce")
    return frame


def _validate_main_canonical(frame: pd.DataFrame) -> None:
    _require_columns(
        frame,
        [
            *PREDICTION_TASK_KEYS,
            "repository",
            "strict_label",
            "strict_parse_success",
            "raw_output",
            "start_timestamp",
            "end_timestamp",
            "hardware_snapshot_id",
        ],
        name="main canonical predictions",
    )
    duplicated = frame.duplicated(list(PREDICTION_TASK_KEYS), keep=False)
    if duplicated.any():
        raise ValueError(
            "Main canonical predictions contain duplicate prediction task keys: "
            f"{int(duplicated.sum())} rows"
        )
    if "technical_error" in frame.columns:
        unresolved = frame["technical_error"].map(_is_technical_error)
        if unresolved.any():
            raise ValueError(
                "Main canonical predictions contain unresolved technical errors: "
                f"{int(unresolved.sum())}"
            )
    observed_conditions = set(frame["taxonomy_condition"].astype(str))
    if observed_conditions != set(CONDITIONS):
        raise ValueError(
            "Main canonical predictions do not contain exactly T0-T4: "
            f"{sorted(observed_conditions)}"
        )
    instruction_variants = set(frame["instruction_variant"].astype(str))
    if instruction_variants != {"P1"}:
        raise ValueError(
            "Canonical main-prompt audit requires only P1, observed: "
            f"{sorted(instruction_variants)}"
        )
    repeat_ids = set(pd.to_numeric(frame["repeat_id"], errors="raise").astype(int))
    if repeat_ids != {1}:
        raise ValueError(
            "Canonical main-prompt audit requires only repeat 1, observed: "
            f"{sorted(repeat_ids)}"
        )


def _attach_gold(frame: pd.DataFrame, gold_path: Path) -> pd.DataFrame:
    gold = pd.read_parquet(gold_path, columns=["issue_id", "label"])
    if gold["issue_id"].duplicated().any():
        raise ValueError("Gold data contain duplicate issue_id values")
    merged = frame.merge(gold, on="issue_id", how="left", validate="many_to_one")
    if merged["label"].isna().any():
        raise ValueError(
            "Canonical prediction-gold join produced missing labels: "
            f"{int(merged['label'].isna().sum())}"
        )
    return merged


def _provider_response_model(frame: pd.DataFrame) -> pd.Series:
    if "response_model" in frame.columns and "model_revision" in frame.columns:
        values = frame["response_model"].where(
            frame["response_model"].notna(), frame["model_revision"]
        )
    elif "response_model" in frame.columns:
        values = frame["response_model"]
    elif "model_revision" in frame.columns:
        values = frame["model_revision"]
    else:
        values = pd.Series(index=frame.index, dtype=object)
    return values.fillna("__missing__").astype(str)


def _task_history_audit(canonical: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    states: dict[tuple[Any, ...], dict[str, list[int]]] = {}
    for record in raw.to_dict(orient="records"):
        state = states.setdefault(_task_key(record), {"errors": [], "successes": []})
        target = "errors" if record["technical_error_present"] else "successes"
        state[target].append(int(record["event_sequence"]))

    rows: list[dict[str, Any]] = []
    systems = sorted(canonical["model_id"].astype(str).unique())
    for system_id in systems:
        for condition in CONDITIONS:
            group = canonical[
                canonical["model_id"].eq(system_id)
                & canonical["taxonomy_condition"].eq(condition)
            ]
            raw_group = raw[
                raw["model_id"].eq(system_id)
                & raw["taxonomy_condition"].eq(condition)
            ]
            matching_states = [
                state
                for key, state in states.items()
                if str(key[3]) == system_id and str(key[4]) == condition
            ]
            recovered = sum(
                bool(state["errors"])
                and bool(state["successes"])
                and min(state["successes"]) > min(state["errors"])
                for state in matching_states
            )
            first_start = pd.to_datetime(
                group["start_timestamp"], utc=True, errors="coerce"
            ).min()
            last_end = pd.to_datetime(
                group["end_timestamp"], utc=True, errors="coerce"
            ).max()
            rows.append(
                {
                    "system_id": system_id,
                    "taxonomy_condition": condition,
                    "canonical_task_count": int(group.shape[0]),
                    "unique_raw_task_count": len(matching_states),
                    "raw_checkpoint_record_count": int(raw_group.shape[0]),
                    "terminal_error_checkpoint_record_count": int(
                        raw_group["technical_error_present"].sum()
                    ),
                    "unique_terminal_error_task_count": sum(
                        bool(state["errors"]) for state in matching_states
                    ),
                    "recovered_after_terminal_error_task_count": recovered,
                    "unresolved_raw_task_count": sum(
                        bool(state["errors"]) and not state["successes"]
                        for state in matching_states
                    ),
                    "canonical_invalid_output_count": int(
                        (~group["strict_parse_success"].fillna(False).astype(bool)).sum()
                    ),
                    "canonical_empty_response_count": int(
                        group["raw_output"].fillna("").astype(str).str.strip().eq("").sum()
                    ),
                    "first_success_start_utc": _iso_or_empty(first_start),
                    "last_success_end_utc": _iso_or_empty(last_end),
                    "analysis_status": AUDIT_STATUS,
                }
            )
    return pd.DataFrame(rows, columns=TASK_AUDIT_COLUMNS)


def _response_model_audit(canonical: pd.DataFrame) -> pd.DataFrame:
    frame = canonical.copy()
    frame["provider_response_model"] = _provider_response_model(frame)
    rows: list[dict[str, Any]] = []
    for (system_id, condition), group in frame.groupby(
        ["model_id", "taxonomy_condition"], sort=True
    ):
        counts = group["provider_response_model"].value_counts().sort_index()
        for response_model, count in counts.items():
            rows.append(
                {
                    "system_id": str(system_id),
                    "taxonomy_condition": str(condition),
                    "provider_response_model": str(response_model),
                    "canonical_task_count": int(count),
                    "share_within_system_condition": float(count / group.shape[0]),
                    "analysis_status": AUDIT_STATUS,
                }
            )
    return pd.DataFrame(rows, columns=RESPONSE_MODEL_COLUMNS)


def _invocation_segment_lookup(
    raw: pd.DataFrame, canonical: pd.DataFrame
) -> dict[tuple[str, str], str]:
    raw_markers = raw[["model_id", "hardware_snapshot_id", "start_dt", "event_sequence"]].copy()
    raw_markers["marker"] = raw_markers["hardware_snapshot_id"].map(
        _normalize_segment_marker
    )
    canonical_markers = canonical[
        ["model_id", "hardware_snapshot_id", "start_timestamp"]
    ].copy()
    canonical_markers["marker"] = canonical_markers["hardware_snapshot_id"].map(
        _normalize_segment_marker
    )
    canonical_markers["start_dt"] = pd.to_datetime(
        canonical_markers["start_timestamp"], utc=True, errors="coerce"
    )

    lookup: dict[tuple[str, str], str] = {}
    systems = sorted(
        set(raw_markers["model_id"].astype(str))
        | set(canonical_markers["model_id"].astype(str))
    )
    for system_id in systems:
        system_raw = raw_markers[raw_markers["model_id"].astype(str).eq(system_id)]
        system_canonical = canonical_markers[
            canonical_markers["model_id"].astype(str).eq(system_id)
        ]
        markers = sorted(set(system_raw["marker"]) | set(system_canonical["marker"]))
        ordering: list[tuple[pd.Timestamp, int, str]] = []
        for marker in markers:
            raw_part = system_raw[system_raw["marker"].eq(marker)]
            canonical_part = system_canonical[system_canonical["marker"].eq(marker)]
            starts = pd.concat(
                [raw_part["start_dt"], canonical_part["start_dt"]], ignore_index=True
            ).dropna()
            first_start = starts.min() if not starts.empty else pd.Timestamp.max.tz_localize("UTC")
            first_sequence = (
                int(raw_part["event_sequence"].min()) if not raw_part.empty else 2**63 - 1
            )
            ordering.append((first_start, first_sequence, marker))
        for index, (_start, _sequence, marker) in enumerate(sorted(ordering), start=1):
            lookup[(system_id, marker)] = f"invocation_{index:03d}"
    return lookup


def _assign_invocation_segments(
    raw: pd.DataFrame, canonical: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    lookup = _invocation_segment_lookup(raw, canonical)
    raw_out = raw.copy()
    canonical_out = canonical.copy()
    raw_out["marker"] = raw_out["hardware_snapshot_id"].map(_normalize_segment_marker)
    canonical_out["marker"] = canonical_out["hardware_snapshot_id"].map(
        _normalize_segment_marker
    )
    raw_out["invocation_segment"] = [
        lookup[(str(system_id), marker)]
        for system_id, marker in zip(raw_out["model_id"], raw_out["marker"], strict=True)
    ]
    canonical_out["invocation_segment"] = [
        lookup[(str(system_id), marker)]
        for system_id, marker in zip(
            canonical_out["model_id"], canonical_out["marker"], strict=True
        )
    ]
    return raw_out, canonical_out


def _provenance_segment_audit(
    raw: pd.DataFrame, canonical: pd.DataFrame
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    segment_keys = (
        raw[["model_id", "invocation_segment"]]
        .drop_duplicates()
        .sort_values(["model_id", "invocation_segment"])
    )
    for segment_key in segment_keys.itertuples(index=False):
        system_id = str(segment_key.model_id)
        segment = str(segment_key.invocation_segment)
        raw_segment = raw[
            raw["model_id"].astype(str).eq(system_id)
            & raw["invocation_segment"].eq(segment)
        ]
        canonical_segment = canonical[
            canonical["model_id"].astype(str).eq(system_id)
            & canonical["invocation_segment"].eq(segment)
        ]
        segment_total = int(canonical_segment.shape[0])
        first_start = raw_segment["start_dt"].min()
        last_end = raw_segment["end_dt"].max()
        for condition in CONDITIONS:
            raw_group = raw_segment[raw_segment["taxonomy_condition"].eq(condition)]
            canonical_group = canonical_segment[
                canonical_segment["taxonomy_condition"].eq(condition)
            ]
            terminal = raw_group[raw_group["technical_error_present"]]
            rows.append(
                {
                    "system_id": system_id,
                    "invocation_segment": segment,
                    "taxonomy_condition": condition,
                    "segment_first_start_utc": _iso_or_empty(first_start),
                    "segment_last_end_utc": _iso_or_empty(last_end),
                    "raw_checkpoint_record_count": int(raw_group.shape[0]),
                    "unique_raw_task_count": int(
                        raw_group[list(PREDICTION_TASK_KEYS)].drop_duplicates().shape[0]
                    ),
                    "terminal_error_checkpoint_record_count": int(terminal.shape[0]),
                    "unique_terminal_error_task_count": int(
                        terminal[list(PREDICTION_TASK_KEYS)].drop_duplicates().shape[0]
                    ),
                    "canonical_successful_task_count": int(canonical_group.shape[0]),
                    "canonical_condition_share_within_segment": (
                        float(canonical_group.shape[0] / segment_total)
                        if segment_total
                        else None
                    ),
                    "provenance_basis": PROVENANCE_RULE,
                    "raw_marker_exposed": False,
                    "analysis_status": AUDIT_STATUS,
                }
            )
    return pd.DataFrame(rows, columns=PROVENANCE_COLUMNS)


def _access_window_audit(canonical: pd.DataFrame) -> pd.DataFrame:
    frame = canonical.copy()
    frame["start_dt"] = pd.to_datetime(
        frame["start_timestamp"], utc=True, errors="raise"
    )
    frame["access_window_start"] = frame["start_dt"].dt.floor(
        f"{ACCESS_WINDOW_HOURS}h"
    )
    rows: list[dict[str, Any]] = []
    for system_id in sorted(frame["model_id"].astype(str).unique()):
        system = frame[frame["model_id"].astype(str).eq(system_id)]
        for window_start in sorted(system["access_window_start"].unique()):
            window = system[system["access_window_start"].eq(window_start)]
            window_total = int(window.shape[0])
            for condition in CONDITIONS:
                group = window[window["taxonomy_condition"].eq(condition)]
                count = int(group.shape[0])
                if count:
                    exact_macro_f1: float | None = _macro_f1(
                        group["label"], group["strict_label"]
                    )
                    invalid_rate: float | None = float(
                        1.0 - group["strict_parse_success"].fillna(False).astype(bool).mean()
                    )
                    gold_counts = group["label"].value_counts()
                else:
                    exact_macro_f1 = None
                    invalid_rate = None
                    gold_counts = pd.Series(dtype=int)
                share = float(count / window_total)
                equal_share = 1.0 / len(CONDITIONS)
                start = pd.Timestamp(window_start)
                rows.append(
                    {
                        "system_id": system_id,
                        "access_window_start_utc": start.isoformat(),
                        "access_window_end_exclusive_utc": (
                            start + pd.Timedelta(hours=ACCESS_WINDOW_HOURS)
                        ).isoformat(),
                        "taxonomy_condition": condition,
                        "canonical_task_count": count,
                        "total_system_window_tasks": window_total,
                        "condition_share_within_system_window": share,
                        "equal_share_reference": equal_share,
                        "share_deviation_from_equal": share - equal_share,
                        "exact_macro_f1_descriptive": exact_macro_f1,
                        "invalid_rate_descriptive": invalid_rate,
                        "gold_bug_count": int(gold_counts.get("bug", 0)),
                        "gold_feature_count": int(gold_counts.get("feature", 0)),
                        "gold_question_count": int(gold_counts.get("question", 0)),
                        "window_rule": ACCESS_WINDOW_RULE,
                        "analysis_status": DESCRIPTIVE_STATUS,
                    }
                )
    return pd.DataFrame(rows, columns=ACCESS_WINDOW_COLUMNS)


def _macro_f1(gold: pd.Series, predicted: pd.Series) -> float:
    return float(
        f1_score(
            gold.tolist(),
            normalize_predictions(predicted.tolist()),
            labels=list(LABELS),
            average="macro",
            zero_division=0,
        )
    )


def _glm_pairwise_provenance_audit(canonical: pd.DataFrame) -> pd.DataFrame:
    glm = canonical[canonical["model_id"].eq(GLM_MODEL_ID)].copy()
    if glm.empty:
        raise ValueError(f"No canonical rows found for required GLM system {GLM_MODEL_ID}")
    glm["provider_response_model"] = _provider_response_model(glm)
    dimensions = {
        "provider_response_model": "provider_response_model",
        "inferred_resume_segment": "invocation_segment",
    }
    rows: list[dict[str, Any]] = []
    for dimension_name, column in dimensions.items():
        for subset_value in sorted(glm[column].astype(str).unique()):
            subset = glm[glm[column].astype(str).eq(subset_value)]
            base = subset[subset["taxonomy_condition"].eq("T0")][
                ["repository", "issue_id", "label", "strict_label"]
            ].rename(columns={"strict_label": "t0_label"})
            for condition in ENRICHED_CONDITIONS:
                other = subset[subset["taxonomy_condition"].eq(condition)][
                    ["repository", "issue_id", "label", "strict_label"]
                ].rename(
                    columns={
                        "label": "condition_gold",
                        "strict_label": "condition_label",
                    }
                )
                matched = base.merge(
                    other,
                    on=["repository", "issue_id"],
                    how="inner",
                    validate="one_to_one",
                )
                if matched.empty:
                    continue
                if not matched["label"].eq(matched["condition_gold"]).all():
                    raise ValueError("GLM pairwise match produced inconsistent gold labels")
                repository_deltas: list[float] = []
                repository_counts: list[int] = []
                for _repository, repository_group in matched.groupby(
                    "repository", sort=True
                ):
                    repository_counts.append(int(repository_group.shape[0]))
                    repository_deltas.append(
                        _macro_f1(
                            repository_group["label"],
                            repository_group["condition_label"],
                        )
                        - _macro_f1(
                            repository_group["label"], repository_group["t0_label"]
                        )
                    )
                t0_pooled = _macro_f1(matched["label"], matched["t0_label"])
                condition_pooled = _macro_f1(
                    matched["label"], matched["condition_label"]
                )
                rows.append(
                    {
                        "system_id": GLM_MODEL_ID,
                        "provenance_dimension": dimension_name,
                        "provenance_subset": subset_value,
                        "comparison": f"{condition}-T0",
                        "taxonomy_condition": condition,
                        "matched_issue_count": int(matched.shape[0]),
                        "matched_repository_count": len(repository_counts),
                        "minimum_matched_issues_per_repository": min(repository_counts),
                        "maximum_matched_issues_per_repository": max(repository_counts),
                        "t0_exact_macro_f1_pooled": t0_pooled,
                        "condition_exact_macro_f1_pooled": condition_pooled,
                        "pooled_delta_macro_f1": condition_pooled - t0_pooled,
                        "equal_repository_mean_delta_macro_f1": float(
                            np.mean(repository_deltas)
                        ),
                        "negative_repository_delta_count": int(
                            np.sum(np.asarray(repository_deltas) < 0)
                        ),
                        "pairing_rule": PAIRING_RULE,
                        "analysis_status": DESCRIPTIVE_STATUS,
                    }
                )
    return pd.DataFrame(rows, columns=GLM_PAIRWISE_COLUMNS).sort_values(
        ["provenance_dimension", "provenance_subset", "taxonomy_condition"],
        ignore_index=True,
    )


def _block_pivot(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (system_id, repository, condition), group in frame.groupby(
        ["model_id", "repository", "taxonomy_condition"], sort=True
    ):
        rows.append(
            {
                "system_id": str(system_id),
                "repository": str(repository),
                "taxonomy_condition": str(condition),
                "macro_f1": _macro_f1(group["label"], group["strict_label"]),
            }
        )
    blocks = pd.DataFrame(rows)
    pivot = blocks.pivot(
        index=["system_id", "repository"],
        columns="taxonomy_condition",
        values="macro_f1",
    ).reindex(columns=list(CONDITIONS))
    if pivot.isna().any().any():
        raise ValueError("A repository-system block is missing one or more T0-T4 conditions")
    return pivot


def _leave_one_contrasts(
    canonical: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    pivot = _block_pivot(canonical)
    repository_rows: list[dict[str, Any]] = []
    system_rows: list[dict[str, Any]] = []
    repositories = sorted(pivot.index.get_level_values("repository").unique())
    systems = sorted(pivot.index.get_level_values("system_id").unique())

    for excluded_repository in repositories:
        subset = pivot[
            pivot.index.get_level_values("repository") != excluded_repository
        ]
        for condition in ENRICHED_CONDITIONS:
            deltas = subset[condition] - subset["T0"]
            repository_rows.append(
                {
                    "excluded_repository": excluded_repository,
                    "comparison": f"{condition}-T0",
                    "observed_delta_macro_f1": float(deltas.mean()),
                    "negative_repository_system_cell_count": int((deltas < 0).sum()),
                    "remaining_repository_system_cell_count": int(deltas.shape[0]),
                    "remaining_repository_count": int(
                        subset.index.get_level_values("repository").nunique()
                    ),
                    "remaining_system_count": int(
                        subset.index.get_level_values("system_id").nunique()
                    ),
                    "interval_method": "none; point-estimate sensitivity only",
                    "analysis_status": DESCRIPTIVE_STATUS,
                }
            )

    for excluded_system in systems:
        subset = pivot[pivot.index.get_level_values("system_id") != excluded_system]
        for condition in ENRICHED_CONDITIONS:
            deltas = subset[condition] - subset["T0"]
            system_rows.append(
                {
                    "excluded_system": excluded_system,
                    "comparison": f"{condition}-T0",
                    "observed_delta_macro_f1": float(deltas.mean()),
                    "negative_repository_system_cell_count": int((deltas < 0).sum()),
                    "remaining_repository_system_cell_count": int(deltas.shape[0]),
                    "remaining_repository_count": int(
                        subset.index.get_level_values("repository").nunique()
                    ),
                    "remaining_system_count": int(
                        subset.index.get_level_values("system_id").nunique()
                    ),
                    "interval_method": "none; point-estimate sensitivity only",
                    "analysis_status": DESCRIPTIVE_STATUS,
                }
            )
    return (
        pd.DataFrame(repository_rows, columns=LEAVE_ONE_REPOSITORY_COLUMNS),
        pd.DataFrame(system_rows, columns=LEAVE_ONE_SYSTEM_COLUMNS),
    )


def _robustness_sample_canonical_deltas(
    main: pd.DataFrame,
    robustness: pd.DataFrame,
    *,
    expected_sample_size: int | None,
) -> pd.DataFrame:
    _require_columns(robustness, ["issue_id"], name="robustness canonical predictions")
    issue_ids = sorted(robustness["issue_id"].astype(str).unique())
    if expected_sample_size is not None and len(issue_ids) != expected_sample_size:
        raise ValueError(
            "Unexpected robustness sample size: "
            f"expected {expected_sample_size}, observed {len(issue_ids)}"
        )
    subset = main[main["issue_id"].astype(str).isin(issue_ids)].copy()
    if subset["issue_id"].astype(str).nunique() != len(issue_ids):
        raise ValueError("Some robustness-sample issue ids are absent from canonical main rows")
    pivot = _block_pivot(subset)
    rows: list[dict[str, Any]] = []
    for condition in ENRICHED_CONDITIONS:
        deltas = pivot[condition] - pivot["T0"]
        rows.append(
            {
                "source": "canonical main P1 repeat 1 on fixed robustness sample",
                "comparison": f"{condition}-T0",
                "observed_delta_macro_f1": float(deltas.mean()),
                "median_repository_system_cell_delta_macro_f1": float(deltas.median()),
                "negative_repository_system_cell_count": int((deltas < 0).sum()),
                "repository_system_cell_count": int(deltas.shape[0]),
                "sample_issue_count": len(issue_ids),
                "interval_method": "none; point-estimate sample sensitivity only",
                "analysis_status": DESCRIPTIVE_STATUS,
            }
        )
    return pd.DataFrame(rows, columns=ROBUSTNESS_SAMPLE_COLUMNS)


def _relative(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def run_revision_audit(
    project_root: Path = PROJECT_ROOT,
    *,
    expected_robustness_sample_size: int | None = 150,
) -> dict[str, Any]:
    """Generate deterministic post-result statistical and provenance audit artifacts."""

    root = Path(project_root).resolve()
    raw_dir = root / "results" / "raw_predictions"
    main_parquet_paths = sorted(raw_dir.glob("main-*.parquet"))
    main_jsonl_paths = sorted(raw_dir.glob("main-*.jsonl"))
    robustness_paths = sorted(raw_dir.glob("robustness-*.parquet"))
    gold_path = root / "data" / "processed" / "test_gold.parquet"
    if not gold_path.exists():
        raise FileNotFoundError(gold_path)

    main = _load_canonical(main_parquet_paths, run_type="main")
    _validate_main_canonical(main)
    main = _attach_gold(main, gold_path)
    raw = _load_main_raw(main_jsonl_paths)
    robustness = _load_canonical(robustness_paths, run_type="robustness")
    raw_segmented, main_segmented = _assign_invocation_segments(raw, main)

    task_history = _task_history_audit(main_segmented, raw_segmented)
    response_models = _response_model_audit(main_segmented)
    provenance_segments = _provenance_segment_audit(raw_segmented, main_segmented)
    access_windows = _access_window_audit(main_segmented)
    glm_pairwise = _glm_pairwise_provenance_audit(main_segmented)
    leave_repository, leave_system = _leave_one_contrasts(main_segmented)
    robustness_sample = _robustness_sample_canonical_deltas(
        main_segmented,
        robustness,
        expected_sample_size=expected_robustness_sample_size,
    )

    table_dir = root / "results" / "tables"
    output_specs = {
        "main_task_history_by_system_condition": (
            table_dir / "revision_main_task_history_by_system_condition.csv",
            task_history,
            TASK_AUDIT_COLUMNS,
        ),
        "response_model_by_system_condition": (
            table_dir / "revision_response_model_by_system_condition.csv",
            response_models,
            RESPONSE_MODEL_COLUMNS,
        ),
        "invocation_provenance_by_system_condition": (
            table_dir / "revision_invocation_provenance_by_system_condition.csv",
            provenance_segments,
            PROVENANCE_COLUMNS,
        ),
        "access_window_sensitivity": (
            table_dir / "revision_access_window_sensitivity.csv",
            access_windows,
            ACCESS_WINDOW_COLUMNS,
        ),
        "glm_pairwise_provenance_sensitivity": (
            table_dir / "revision_glm_pairwise_provenance_sensitivity.csv",
            glm_pairwise,
            GLM_PAIRWISE_COLUMNS,
        ),
        "leave_one_repository_contrasts": (
            table_dir / "revision_leave_one_repository_contrasts.csv",
            leave_repository,
            LEAVE_ONE_REPOSITORY_COLUMNS,
        ),
        "leave_one_system_contrasts": (
            table_dir / "revision_leave_one_system_contrasts.csv",
            leave_system,
            LEAVE_ONE_SYSTEM_COLUMNS,
        ),
        "robustness_sample_canonical_deltas": (
            table_dir / "revision_robustness_sample_canonical_deltas.csv",
            robustness_sample,
            ROBUSTNESS_SAMPLE_COLUMNS,
        ),
    }
    for path, frame, columns in output_specs.values():
        _write_frame(path, frame, columns)

    input_paths = [
        *main_jsonl_paths,
        *main_parquet_paths,
        *robustness_paths,
        gold_path,
    ]
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "analysis_status": AUDIT_STATUS,
        "determinism": (
            "no generated-at timestamp; inputs and outputs are sorted; stochastic resampling "
            "is not used"
        ),
        "access_window_audit": {
            "status": DESCRIPTIVE_STATUS,
            "duration_hours": ACCESS_WINDOW_HOURS,
            "timestamp_field": "start_timestamp",
            "rule": ACCESS_WINDOW_RULE,
            "inference": "none; counts, exact Macro-F1, and invalid rates are descriptive",
        },
        "provenance_audit": {
            "rule": PROVENANCE_RULE,
            "raw_invocation_marker_values_exposed": False,
            "account_identity_available": False,
        },
        "glm_pairwise_audit": {
            "rule": PAIRING_RULE,
            "dimensions": ["provider_response_model", "inferred_resume_segment"],
            "inference": "none; matched-subset point estimates only",
        },
        "historical_crossed_cell_intervals_generated": False,
        "conditions": list(CONDITIONS),
        "main_canonical_task_count": int(main.shape[0]),
        "robustness_sample_issue_count": int(robustness["issue_id"].nunique()),
        "inputs": [
            {"path": _relative(path, root), "sha256": sha256_file(path)}
            for path in sorted(input_paths)
        ],
        "outputs": {},
        "summary_path": "results/statistics/revision_audit.json",
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
