from __future__ import annotations

from typing import Any

import pandas as pd

from taxrep.constants import PROJECT_ROOT
from taxrep.runs import canonicalize_prediction_records, ensure_run_type
from taxrep.utils import read_jsonl, write_json

EXPECTED_RUN_SPECS: dict[str, dict[str, Any]] = {
    "targeted-t3-repeat": {
        "issue_count": 150,
        "models": ["deepseek-v4-flash", "kimi-k2.7-code", "glm-5.2"],
        "taxonomy_conditions": ["T0", "T3"],
        "instruction_variants": ["P1"],
        "repeat_ids": [1, 2, 3],
    },
    "technical-pretest": {
        "issue_count": 5,
        "models": ["deepseek-v4-flash", "kimi-k2.7-code", "glm-5.2"],
        "taxonomy_conditions": ["T2"],
        "instruction_variants": ["P1"],
        "repeat_ids": [1],
    },
    "pilot": {
        "issue_count": 150,
        "models": ["deepseek-v4-flash", "kimi-k2.7-code", "glm-5.2"],
        "taxonomy_conditions": ["T0", "T1", "T2", "T3", "T4"],
        "instruction_variants": ["P1"],
        "repeat_ids": [1],
    },
    "main": {
        "issue_count": 1500,
        "models": ["deepseek-v4-flash", "kimi-k2.7-code", "glm-5.2"],
        "taxonomy_conditions": ["T0", "T1", "T2", "T3", "T4"],
        "instruction_variants": ["P1"],
        "repeat_ids": [1],
    },
    "train-selection": {
        "issue_count": 1500,
        "models": ["deepseek-v4-flash", "kimi-k2.7-code", "glm-5.2"],
        "taxonomy_conditions": ["T0", "T1", "T2", "T3", "T4"],
        "instruction_variants": ["P1"],
        "repeat_ids": [1],
    },
    "robustness": {
        "issue_count": 150,
        "models": ["deepseek-v4-flash", "kimi-k2.7-code", "glm-5.2"],
        "taxonomy_conditions": ["T0", "T2", "T4"],
        "instruction_variants": ["P1", "P2", "P3"],
        "repeat_ids": [1, 2, 3],
    },
}


def _raw_prediction_frame() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for path in sorted((PROJECT_ROOT / "results" / "raw_predictions").glob("*.jsonl")):
        rows.extend(read_jsonl(path))
    if not rows:
        return pd.DataFrame()
    return ensure_run_type(pd.DataFrame.from_records(canonicalize_prediction_records(rows)))


def summarize_run_type(run_type: str) -> dict[str, Any]:
    frame = _raw_prediction_frame()
    if frame.empty:
        return {"run_type": run_type, "status": "missing", "rows": 0}
    frame = frame[frame["run_type"] == run_type].copy()
    if frame.empty:
        return {"run_type": run_type, "status": "missing", "rows": 0}
    by_model_condition = (
        frame.groupby(["model_id", "taxonomy_condition"], dropna=False)
        .agg(
            rows=("issue_id", "size"),
            strict_successes=("strict_parse_success", "sum"),
            technical_errors=("technical_error", lambda values: int(values.notna().sum())),
        )
        .reset_index()
    )
    by_model_condition["strict_parse_rate"] = (
        by_model_condition["strict_successes"] / by_model_condition["rows"]
    )
    return {
        "run_type": run_type,
        "status": "present",
        "rows": int(len(frame)),
        "unique_issues": int(frame["issue_id"].nunique()),
        "models": sorted(frame["model_id"].dropna().unique().tolist()),
        "taxonomy_conditions": sorted(frame["taxonomy_condition"].dropna().unique().tolist()),
        "technical_errors": int(frame["technical_error"].notna().sum()),
        "strict_parse_successes": int(frame["strict_parse_success"].sum()),
        "strict_parse_rate": float(frame["strict_parse_success"].mean()),
        "by_model_condition": by_model_condition.to_dict(orient="records"),
    }


def write_run_report(run_type: str) -> dict[str, Any]:
    summary = summarize_run_type(run_type)
    out_json = PROJECT_ROOT / "results" / "run_manifests" / f"{run_type}_report.json"
    out_md = PROJECT_ROOT / "results" / "run_manifests" / f"{run_type}_report.md"
    write_json(out_json, summary)
    lines = [
        f"# {run_type.title()} Report",
        "",
        f"- Status: `{summary['status']}`",
        f"- Rows: `{summary.get('rows', 0)}`",
        f"- Unique issues: `{summary.get('unique_issues', 0)}`",
        f"- Strict parse rate: `{summary.get('strict_parse_rate', 0):.3f}`",
        f"- Technical errors: `{summary.get('technical_errors', 0)}`",
        "",
        "## Model x Condition",
        "",
        "| Model | Condition | Rows | Strict Parse Rate | Technical Errors |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in summary.get("by_model_condition", []):
        lines.append(
            "| {model_id} | {taxonomy_condition} | {rows} | {strict:.3f} | {errors} |".format(
                model_id=row["model_id"],
                taxonomy_condition=row["taxonomy_condition"],
                rows=row["rows"],
                strict=row["strict_parse_rate"],
                errors=row["technical_errors"],
            )
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": str(out_json), "markdown": str(out_md), "summary": summary}


def expected_run_rows(run_type: str) -> int:
    spec = EXPECTED_RUN_SPECS[run_type]
    return (
        spec["issue_count"]
        * len(spec["models"])
        * len(spec["taxonomy_conditions"])
        * len(spec["instruction_variants"])
        * len(spec["repeat_ids"])
    )


def expected_cell_frame(run_type: str) -> pd.DataFrame:
    spec = EXPECTED_RUN_SPECS[run_type]
    rows: list[dict[str, Any]] = []
    for model_id in spec["models"]:
        for condition in spec["taxonomy_conditions"]:
            for variant in spec["instruction_variants"]:
                for repeat_id in spec["repeat_ids"]:
                    rows.append(
                        {
                            "model_id": model_id,
                            "taxonomy_condition": condition,
                            "instruction_variant": variant,
                            "repeat_id": repeat_id,
                            "expected_rows": spec["issue_count"],
                        }
                    )
    return pd.DataFrame(rows)


def completeness_report(run_type: str) -> dict[str, Any]:
    if run_type not in EXPECTED_RUN_SPECS:
        raise KeyError(f"Unknown expected run type: {run_type}")
    frame = _raw_prediction_frame()
    expected = expected_cell_frame(run_type)
    if frame.empty:
        actual = pd.DataFrame(
            columns=[
                "model_id",
                "taxonomy_condition",
                "instruction_variant",
                "repeat_id",
                "actual_rows",
                "technical_errors",
                "strict_successes",
            ]
        )
    else:
        frame = frame[frame["run_type"] == run_type].copy()
        actual = (
            frame.groupby(
                ["model_id", "taxonomy_condition", "instruction_variant", "repeat_id"],
                dropna=False,
            )
            .agg(
                actual_rows=("issue_id", "size"),
                technical_errors=("technical_error", lambda values: int(values.notna().sum())),
                strict_successes=("strict_parse_success", "sum"),
            )
            .reset_index()
        )
    merged = expected.merge(
        actual,
        on=["model_id", "taxonomy_condition", "instruction_variant", "repeat_id"],
        how="left",
    ).fillna({"actual_rows": 0, "technical_errors": 0, "strict_successes": 0})
    for column in ("actual_rows", "technical_errors", "strict_successes"):
        merged[column] = merged[column].astype(int)
    merged["missing_rows"] = merged["expected_rows"] - merged["actual_rows"]
    merged["complete"] = (merged["missing_rows"] == 0) & (merged["technical_errors"] == 0)
    expected_rows = expected_run_rows(run_type)
    actual_rows = int(merged["actual_rows"].sum())
    missing_rows = int(merged["missing_rows"].sum())
    technical_errors = int(merged["technical_errors"].sum())
    payload = {
        "run_type": run_type,
        "expected_rows": expected_rows,
        "actual_rows": actual_rows,
        "missing_rows": missing_rows,
        "technical_errors": technical_errors,
        "complete": missing_rows == 0 and technical_errors == 0,
        "cells": merged.to_dict(orient="records"),
    }
    out_json = PROJECT_ROOT / "results" / "run_manifests" / f"{run_type}_completeness.json"
    out_md = PROJECT_ROOT / "results" / "run_manifests" / f"{run_type}_completeness.md"
    write_json(out_json, payload)
    write_completeness_markdown(payload, out_md)
    return {"json": str(out_json), "markdown": str(out_md), "summary": payload}


def write_completeness_markdown(payload: dict[str, Any], path) -> None:
    lines = [
        f"# {payload['run_type'].title()} Completeness",
        "",
        f"- Complete: `{payload['complete']}`",
        f"- Rows: `{payload['actual_rows']}` / `{payload['expected_rows']}`",
        f"- Missing rows: `{payload['missing_rows']}`",
        f"- Technical errors: `{payload['technical_errors']}`",
        "",
        "| Model | Condition | Variant | Repeat | Actual | Expected | Missing | Errors |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload["cells"]:
        lines.append(
            "| {model_id} | {taxonomy_condition} | {instruction_variant} | {repeat_id} | "
            "{actual_rows} | {expected_rows} | {missing_rows} | {technical_errors} |".format(**row)
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
