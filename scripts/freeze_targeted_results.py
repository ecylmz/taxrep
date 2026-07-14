from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from taxrep.constants import PROJECT_ROOT
from taxrep.runs import canonicalize_prediction_records, ensure_run_type
from taxrep.targeted import EXPECTED_TASKS, TARGETED_HASHES, verify_targeted_extension_freeze
from taxrep.targeted_recovery import (
    HISTORICAL_HTTP_ATTEMPT_UPPER_BOUND,
    RECOVERY_HTTP_ATTEMPT_HARD_CAP,
    REVISION_HTTP_ATTEMPT_HARD_CAP,
    verify_targeted_recovery_freeze,
)
from taxrep.utils import git_commit, read_jsonl, sha256_file, utc_now_iso, write_json

FREEZE_PATH = (
    PROJECT_ROOT
    / "results"
    / "run_manifests"
    / "targeted_t3_repeat_results_freeze.json"
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _exactly_one(pattern: str) -> Path:
    matches = sorted(PROJECT_ROOT.glob(pattern))
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one artifact for {pattern}; found {len(matches)}")
    return matches[0]


def _artifact(path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(PROJECT_ROOT).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _freeze_recovered_targeted_results(frozen_by: str) -> dict[str, Any]:
    freeze = verify_targeted_recovery_freeze()
    raw_dir = PROJECT_ROOT / "results" / "raw_predictions"
    manifest_dir = PROJECT_ROOT / "results" / "run_manifests"
    raw_jsonls = sorted(raw_dir.glob("targeted-t3-repeat-*.jsonl"))
    run_parquets = sorted(raw_dir.glob("targeted-t3-repeat-*.parquet"))
    run_manifests = sorted(manifest_dir.glob("targeted-t3-repeat-*.json"))
    if len(raw_jsonls) < 2 or len(run_parquets) < 2 or len(run_manifests) < 2:
        raise RuntimeError("Recovered targeted extension lacks both execution segments")

    records: list[dict[str, Any]] = []
    for path in raw_jsonls:
        records.extend(read_jsonl(path))
    canonical = canonicalize_prediction_records(records)
    canonical = [row for row in canonical if row.get("run_type") == "targeted-t3-repeat"]
    if len(canonical) != EXPECTED_TASKS:
        raise RuntimeError(
            f"Recovered targeted canonical union has {len(canonical)} rather than 2,700 tasks"
        )
    if any(row.get("technical_error") for row in canonical):
        raise RuntimeError("Recovered targeted canonical union has unresolved technical errors")
    key_columns = [
        "run_type",
        "dataset_split",
        "issue_id",
        "model_id",
        "taxonomy_condition",
        "instruction_variant",
        "repeat_id",
    ]
    frame = ensure_run_type(
        pd.DataFrame.from_records(
            [
                {key: value for key, value in row.items() if key != "response_headers"}
                for row in canonical
            ]
        )
    )
    if frame.duplicated(key_columns).any():
        raise RuntimeError("Recovered targeted canonical task keys are not unique")
    canonical_parquet = (
        PROJECT_ROOT
        / "results"
        / "parsed_predictions"
        / "targeted_t3_repeat_predictions.parquet"
    )
    canonical_parquet.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(canonical_parquet, index=False)
    if int(pq.ParquetFile(canonical_parquet).metadata.num_rows) != EXPECTED_TASKS:
        raise RuntimeError("Recovered targeted canonical Parquet is not 2,700 rows")

    manifest_payloads = [(path, _load_json(path)) for path in run_manifests]
    completed = [
        (path, payload)
        for path, payload in manifest_payloads
        if payload.get("status") == "completed"
        and int(payload.get("task_count_completed_after_run", -1)) == EXPECTED_TASKS
    ]
    if len(completed) != 1:
        raise RuntimeError("Expected exactly one cleanly completed recovery run manifest")
    completed_manifest_path, completed_manifest = completed[0]
    if completed_manifest.get("fatal_stop_reason"):
        raise RuntimeError("Recovery run manifest has a fatal stop reason")
    if int(completed_manifest.get("task_count_missing_after_run", -1)) != 0:
        raise RuntimeError("Recovery run manifest still reports missing task keys")
    if int(completed_manifest.get("unresolved_technical_error_tasks", -1)) != 0:
        raise RuntimeError("Recovery run manifest has unresolved technical errors")

    completeness_json = manifest_dir / "targeted-t3-repeat_completeness.json"
    completeness_md = manifest_dir / "targeted-t3-repeat_completeness.md"
    report_json = manifest_dir / "targeted-t3-repeat_report.json"
    report_md = manifest_dir / "targeted-t3-repeat_report.md"
    completeness = _load_json(completeness_json)
    if (
        not completeness.get("complete")
        or int(completeness.get("actual_rows", -1)) != EXPECTED_TASKS
        or int(completeness.get("technical_errors", -1)) != 0
    ):
        raise RuntimeError("Recovered targeted completeness report is not complete")

    original_budget_path = manifest_dir / "targeted_t3_repeat_call_budget.json"
    original_ledger_path = manifest_dir / "targeted_t3_repeat_call_ledger.jsonl"
    original_preflight_path = manifest_dir / "targeted_t3_repeat_preflight.json"
    recovery_budget_path = manifest_dir / "targeted_t3_repeat_recovery_call_budget.json"
    recovery_ledger_path = manifest_dir / "targeted_t3_repeat_recovery_call_ledger.jsonl"
    recovery_preflight_path = manifest_dir / "targeted_t3_repeat_recovery_preflight.json"
    stopped_path = manifest_dir / "targeted_t3_repeat_stopped_artifacts.json"
    recovery_hashes = PROJECT_ROOT / "experiment" / "targeted_t3_repeat_recovery_hashes.json"

    original_budget = _load_json(original_budget_path)
    recovery_budget = _load_json(recovery_budget_path)
    original_ledger_rows = sum(
        1 for line in original_ledger_path.read_bytes().splitlines() if line.strip()
    )
    recovery_ledger_rows = sum(
        1 for line in recovery_ledger_path.read_bytes().splitlines() if line.strip()
    )
    if int(original_budget.get("used", -1)) != original_ledger_rows:
        raise RuntimeError("Original stopped budget and ledger disagree")
    if int(recovery_budget.get("used", -1)) != recovery_ledger_rows:
        raise RuntimeError("Recovery budget and ledger disagree")
    if int(recovery_budget.get("hard_cap", -1)) != RECOVERY_HTTP_ATTEMPT_HARD_CAP:
        raise RuntimeError("Recovery hard cap differs from 1,360")
    if recovery_ledger_rows > RECOVERY_HTTP_ATTEMPT_HARD_CAP:
        raise RuntimeError("Recovery HTTP-attempt hard cap was exceeded")
    if int(recovery_budget.get("by_kind", {}).get("provider_health", -1)) != 3:
        raise RuntimeError("Recovery provider-health count is not exactly three")
    if int(recovery_budget.get("by_kind", {}).get("targeted_inference", -1)) < 1_060:
        raise RuntimeError("Recovery inference reservations are below 1,060")
    conservative_upper = HISTORICAL_HTTP_ATTEMPT_UPPER_BOUND + recovery_ledger_rows
    if conservative_upper > REVISION_HTTP_ATTEMPT_HARD_CAP:
        raise RuntimeError("Revision-wide conservative HTTP-attempt cap was exceeded")

    original_preflight = _load_json(original_preflight_path)
    recovery_preflight = _load_json(recovery_preflight_path)
    original_health = PROJECT_ROOT / str(original_preflight["provider_health_artifact"])
    recovery_health = PROJECT_ROOT / str(recovery_preflight["provider_health_artifact"])
    required = [
        completeness_json,
        completeness_md,
        report_json,
        report_md,
        original_budget_path,
        original_ledger_path,
        original_preflight_path,
        recovery_budget_path,
        recovery_ledger_path,
        recovery_preflight_path,
        stopped_path,
        original_health,
        recovery_health,
        PROJECT_ROOT / "results/logs/targeted_t3_repeat/inference.log",
        PROJECT_ROOT / "results/logs/targeted_t3_repeat_recovery/inference.log",
        recovery_hashes,
    ]
    missing = [
        path.relative_to(PROJECT_ROOT).as_posix() for path in required if not path.is_file()
    ]
    if missing:
        raise RuntimeError("Recovered result-freeze artifacts are missing: " + ", ".join(missing))

    preanalysis_outputs = [
        PROJECT_ROOT / "results/statistics/targeted_t3_repeat_results.json",
        PROJECT_ROOT / "results/statistics/targeted_t3_repeat_operational_audit.json",
    ]
    if any(path.exists() for path in preanalysis_outputs):
        raise RuntimeError("Targeted result outputs exist before the raw-result freeze")

    artifacts = sorted(
        {
            *raw_jsonls,
            *run_parquets,
            *run_manifests,
            canonical_parquet,
            *required,
        },
        key=lambda path: path.relative_to(PROJECT_ROOT).as_posix(),
    )
    payload = {
        "schema_version": 2,
        "status": "frozen",
        "scientific_status": (
            "post-result, budget-constrained, targeted robustness extension recovery"
        ),
        "frozen_at_utc": utc_now_iso(),
        "frozen_by": frozen_by,
        "git_commit_before_result_access": git_commit(PROJECT_ROOT),
        "protocol_commit": freeze["protocol_commit"],
        "task_order_sha256": freeze["task_order_sha256"],
        "canonical_tasks": EXPECTED_TASKS,
        "canonical_label_free_parquet": canonical_parquet.relative_to(
            PROJECT_ROOT
        ).as_posix(),
        "raw_checkpoint_records": sum(
            1
            for path in raw_jsonls
            for line in path.read_bytes().splitlines()
            if line.strip()
        ),
        "historical_project_ledger_reservations": original_ledger_rows,
        "historical_http_attempt_upper_bound": HISTORICAL_HTTP_ATTEMPT_UPPER_BOUND,
        "recovery_completion_calls_used": recovery_ledger_rows,
        "recovery_completion_call_hard_cap": RECOVERY_HTTP_ATTEMPT_HARD_CAP,
        "completion_calls_used": recovery_ledger_rows,
        "completion_call_hard_cap": RECOVERY_HTTP_ATTEMPT_HARD_CAP,
        "conservative_revision_http_attempt_upper_bound": conservative_upper,
        "revision_http_attempt_hard_cap": REVISION_HTTP_ATTEMPT_HARD_CAP,
        "completed_recovery_manifest": completed_manifest_path.relative_to(
            PROJECT_ROOT
        ).as_posix(),
        "artifacts": [_artifact(path) for path in artifacts],
        "result_access_rule": (
            "Created before joining any targeted prediction to benchmark labels or "
            "computing targeted performance and agreement results."
        ),
    }
    write_json(FREEZE_PATH, payload)
    return payload


def freeze_targeted_results(frozen_by: str) -> dict[str, Any]:
    if FREEZE_PATH.exists():
        raise RuntimeError("Targeted results are already frozen; refusing to overwrite the freeze")
    recovery_hashes = (
        PROJECT_ROOT / "experiment" / "targeted_t3_repeat_recovery_hashes.json"
    )
    if recovery_hashes.is_file():
        return _freeze_recovered_targeted_results(frozen_by)
    freeze = verify_targeted_extension_freeze()
    raw_jsonl = _exactly_one("results/raw_predictions/targeted-t3-repeat-*.jsonl")
    raw_parquet = _exactly_one("results/raw_predictions/targeted-t3-repeat-*.parquet")
    run_manifest = _exactly_one("results/run_manifests/targeted-t3-repeat-*.json")
    completeness_json = PROJECT_ROOT / "results/run_manifests/targeted-t3-repeat_completeness.json"
    completeness_md = PROJECT_ROOT / "results/run_manifests/targeted-t3-repeat_completeness.md"
    report_json = PROJECT_ROOT / "results/run_manifests/targeted-t3-repeat_report.json"
    report_md = PROJECT_ROOT / "results/run_manifests/targeted-t3-repeat_report.md"
    budget_path = PROJECT_ROOT / "results/run_manifests/targeted_t3_repeat_call_budget.json"
    ledger_path = PROJECT_ROOT / "results/run_manifests/targeted_t3_repeat_call_ledger.jsonl"
    preflight_path = PROJECT_ROOT / "results/run_manifests/targeted_t3_repeat_preflight.json"
    log_path = PROJECT_ROOT / "results/logs/targeted_t3_repeat/inference.log"
    if not preflight_path.is_file():
        raise RuntimeError("Targeted provider preflight artifact is missing")
    preflight = _load_json(preflight_path)
    health_path = PROJECT_ROOT / str(preflight.get("provider_health_artifact", ""))

    required = [
        completeness_json,
        completeness_md,
        report_json,
        report_md,
        budget_path,
        ledger_path,
        preflight_path,
        health_path,
        log_path,
        TARGETED_HASHES,
    ]
    missing = [path.relative_to(PROJECT_ROOT).as_posix() for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"Targeted result-freeze artifacts are missing: {', '.join(missing)}")

    manifest = _load_json(run_manifest)
    completeness = _load_json(completeness_json)
    budget = _load_json(budget_path)
    ledger_rows = sum(1 for line in ledger_path.read_bytes().splitlines() if line.strip())
    parquet_rows = int(pq.ParquetFile(raw_parquet).metadata.num_rows)
    raw_records = sum(1 for line in raw_jsonl.read_bytes().splitlines() if line.strip())

    if manifest.get("status") != "completed" or manifest.get("fatal_stop_reason"):
        raise RuntimeError("Targeted inference manifest is not cleanly completed")
    if int(manifest.get("task_count_total", -1)) != EXPECTED_TASKS:
        raise RuntimeError("Targeted manifest task count differs from the frozen plan")
    if int(manifest.get("task_count_completed_after_run", -1)) != EXPECTED_TASKS:
        raise RuntimeError("Targeted manifest does not contain all canonical tasks")
    if int(manifest.get("unresolved_technical_error_tasks", -1)) != 0:
        raise RuntimeError("Targeted manifest has unresolved technical errors")
    if (
        not completeness.get("complete")
        or int(completeness.get("actual_rows", -1)) != EXPECTED_TASKS
    ):
        raise RuntimeError("Targeted completeness report is not complete")
    if int(completeness.get("technical_errors", -1)) != 0:
        raise RuntimeError("Targeted canonical completeness report contains technical errors")
    if parquet_rows != EXPECTED_TASKS:
        raise RuntimeError("Targeted canonical Parquet row count is not 2,700")
    if raw_records < EXPECTED_TASKS:
        raise RuntimeError("Targeted append-only JSONL has fewer records than canonical tasks")
    if int(budget.get("used", -1)) != ledger_rows:
        raise RuntimeError("Completion budget summary and append-only ledger disagree")
    if int(budget.get("used", -1)) > int(budget.get("hard_cap", -1)):
        raise RuntimeError("Completion-call hard cap was exceeded")
    if int(budget.get("by_kind", {}).get("provider_health", -1)) != 3:
        raise RuntimeError("Targeted provider-health call count is not exactly three")
    if int(budget.get("by_kind", {}).get("targeted_inference", -1)) < EXPECTED_TASKS:
        raise RuntimeError("Targeted inference attempt count is below the canonical task count")

    artifacts = [
        raw_jsonl,
        raw_parquet,
        run_manifest,
        completeness_json,
        completeness_md,
        report_json,
        report_md,
        budget_path,
        ledger_path,
        preflight_path,
        health_path,
        log_path,
        TARGETED_HASHES,
    ]
    payload = {
        "schema_version": 1,
        "status": "frozen",
        "scientific_status": "post-result, budget-constrained, targeted robustness extension",
        "frozen_at_utc": utc_now_iso(),
        "frozen_by": frozen_by,
        "git_commit_before_result_access": git_commit(PROJECT_ROOT),
        "protocol_commit": freeze["protocol_commit"],
        "task_order_sha256": freeze["task_order_sha256"],
        "canonical_tasks": EXPECTED_TASKS,
        "raw_checkpoint_records": raw_records,
        "completion_calls_used": int(budget["used"]),
        "completion_call_hard_cap": int(budget["hard_cap"]),
        "artifacts": [_artifact(path) for path in artifacts],
        "result_access_rule": (
            "Created before joining targeted predictions to benchmark labels or computing "
            "targeted performance and agreement results."
        ),
    }
    write_json(FREEZE_PATH, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Freeze completed targeted prediction artifacts before result analysis."
    )
    parser.add_argument("--frozen-by", required=True)
    args = parser.parse_args()
    payload = freeze_targeted_results(args.frozen_by)
    print(
        {
            "status": payload["status"],
            "canonical_tasks": payload["canonical_tasks"],
            "raw_checkpoint_records": payload["raw_checkpoint_records"],
            "completion_calls_used": payload["completion_calls_used"],
            "artifact_count": len(payload["artifacts"]),
        }
    )


if __name__ == "__main__":
    main()
