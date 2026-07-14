from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import openai

from taxrep.constants import PROJECT_ROOT
from taxrep.inference import _checkpoint_to_parquet
from taxrep.runs import canonicalize_prediction_records
from taxrep.utils import read_jsonl, sha256_file, utc_now_iso, write_json

EXPECTED_TASKS = 2_700
SDK_MAX_RETRIES_AT_EXECUTION = 2
STOP_CODE = "unmetered_sdk_internal_retries"


def _exactly_one(pattern: str) -> Path:
    matches = sorted(PROJECT_ROOT.glob(pattern))
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one artifact for {pattern}; found {len(matches)}")
    return matches[0]


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact(path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(PROJECT_ROOT).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def finalize_stopped_run() -> dict[str, Any]:
    if subprocess.run(
        ["tmux", "has-session", "-t", "taxrep-t3-repeat"],
        capture_output=True,
        check=False,
    ).returncode == 0:
        raise RuntimeError("Refusing to finalize while taxrep-t3-repeat is still running")

    checkpoint = _exactly_one("results/raw_predictions/targeted-t3-repeat-*.jsonl")
    active_lock = _exactly_one("results/run_manifests/targeted-t3-repeat-*.lock")
    run_id = checkpoint.stem
    parquet = checkpoint.with_suffix(".parquet")
    manifest_path = PROJECT_ROOT / "results/run_manifests" / f"{run_id}.json"
    stopped_freeze_path = (
        PROJECT_ROOT
        / "results/run_manifests/targeted_t3_repeat_stopped_artifacts.json"
    )
    if manifest_path.exists() or stopped_freeze_path.exists():
        raise RuntimeError("Stopped targeted run was already finalized")

    initial = _load(active_lock)
    records = [
        record
        for record in read_jsonl(checkpoint)
        if record.get("run_type") == "targeted-t3-repeat"
    ]
    canonical = canonicalize_prediction_records(records)
    successful = [record for record in canonical if not record.get("technical_error")]
    technical_errors = sum(bool(record.get("technical_error")) for record in canonical)
    fatal_stops = sum(bool(record.get("fatal_stop_reason")) for record in canonical)
    incompatible = sum(record.get("route_compatible") is False for record in canonical)
    if technical_errors or fatal_stops or incompatible:
        raise RuntimeError("Stopped checkpoint contains an unexpected terminal error signal")
    if len(successful) >= EXPECTED_TASKS:
        raise RuntimeError("Stopped-run finalizer is only for an incomplete checkpoint")

    budget_path = PROJECT_ROOT / "results/run_manifests/targeted_t3_repeat_call_budget.json"
    ledger_path = PROJECT_ROOT / "results/run_manifests/targeted_t3_repeat_call_ledger.jsonl"
    preflight_path = PROJECT_ROOT / "results/run_manifests/targeted_t3_repeat_preflight.json"
    health_path = PROJECT_ROOT / "experiment/provider_health_20260712.json"
    log_path = PROJECT_ROOT / "results/logs/targeted_t3_repeat/inference.log"
    budget = _load(budget_path)
    ledger_count = sum(1 for line in ledger_path.read_bytes().splitlines() if line.strip())
    if int(budget.get("used", -1)) != ledger_count:
        raise RuntimeError("Budget summary and append-only ledger disagree")
    if int(budget.get("by_kind", {}).get("provider_health", -1)) != 3:
        raise RuntimeError("Provider-health reservation count differs from three")

    _checkpoint_to_parquet(checkpoint, parquet)
    lower_http_attempts = len(successful) + 3
    upper_http_attempts = ledger_count * (1 + SDK_MAX_RETRIES_AT_EXECUTION)
    completed_at = utc_now_iso()
    manifest = {
        **initial,
        "status": "stopped_pre_result",
        "completed_at_utc": completed_at,
        "checkpoint_path": checkpoint.relative_to(PROJECT_ROOT).as_posix(),
        "parquet_path": parquet.relative_to(PROJECT_ROOT).as_posix(),
        "task_count_total": EXPECTED_TASKS,
        "task_count_completed_after_run": len(successful),
        "task_count_missing_after_stop": EXPECTED_TASKS - len(successful),
        "unresolved_technical_error_tasks": technical_errors,
        "fatal_stop_reason": (
            "The installed OpenAI-compatible SDK retained two unmetered internal "
            "retries, so the project ledger could not prove the 3,000-attempt cap."
        ),
        "stop_reason_code": STOP_CODE,
        "result_eligibility": (
            "ineligible: incomplete checkpoint; do not join to gold labels or analyze "
            "as an experimental subset"
        ),
        "completion_call_budget": budget,
        "project_level_ledger_reservations": ledger_count,
        "completed_targeted_response_records": len(successful),
        "outer_retry_count_total": sum(int(record.get("retry_count") or 0) for record in records),
        "sdk_internal_retry_events_retained": False,
        "sdk_max_retries_at_execution": SDK_MAX_RETRIES_AT_EXECUTION,
        "outbound_http_attempt_count_status": "not reconstructible",
        "outbound_http_attempt_count_mechanical_lower_bound": lower_http_attempts,
        "outbound_http_attempt_count_mechanical_upper_bound": upper_http_attempts,
        "openai_sdk_version": openai.__version__,
        "deviation": "experiment/deviations.md#dev-2026-07-12-07",
    }
    write_json(manifest_path, manifest)

    archived_lock = (
        PROJECT_ROOT
        / "results/run_manifests/stale_locks"
        / f"{run_id}.stopped.lock.json"
    )
    archived_lock.parent.mkdir(parents=True, exist_ok=True)
    os.replace(active_lock, archived_lock)

    frozen_artifacts = [
        checkpoint,
        parquet,
        manifest_path,
        archived_lock,
        budget_path,
        ledger_path,
        preflight_path,
        health_path,
        log_path,
        PROJECT_ROOT / "src/taxrep/providers/opencode_go.py",
        PROJECT_ROOT / "uv.lock",
    ]
    stopped_payload = {
        "schema_version": 1,
        "status": "stopped_pre_result",
        "stopped_at_utc": completed_at,
        "stop_reason_code": STOP_CODE,
        "scientific_result_eligible": False,
        "gold_labels_accessed": False,
        "canonical_completed_tasks": len(successful),
        "planned_tasks": EXPECTED_TASKS,
        "missing_tasks": EXPECTED_TASKS - len(successful),
        "project_level_ledger_reservations": ledger_count,
        "outbound_http_attempt_count_status": "not reconstructible",
        "outbound_http_attempt_count_mechanical_range": [
            lower_http_attempts,
            upper_http_attempts,
        ],
        "artifacts": [_artifact(path) for path in frozen_artifacts],
        "handling_rule": (
            "Preserve append-only for audit; do not compute partial performance, "
            "agreement, or prompt-selection results."
        ),
    }
    write_json(stopped_freeze_path, stopped_payload)
    return stopped_payload


if __name__ == "__main__":
    result = finalize_stopped_run()
    print(
        {
            "status": result["status"],
            "canonical_completed_tasks": result["canonical_completed_tasks"],
            "missing_tasks": result["missing_tasks"],
            "project_level_ledger_reservations": result[
                "project_level_ledger_reservations"
            ],
            "scientific_result_eligible": result["scientific_result_eligible"],
        }
    )
