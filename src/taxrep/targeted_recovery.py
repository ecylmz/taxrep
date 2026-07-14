from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import orjson

from taxrep.call_budget import CompletionCallBudget
from taxrep.constants import PROJECT_ROOT
from taxrep.providers.opencode_go import OpenCodeGoProvider, catalog_model_ids
from taxrep.public_artifact import artifact_hash_match, commit_is_ancestor_or_public_snapshot
from taxrep.runs import canonicalize_prediction_records, prediction_task_key
from taxrep.targeted import (
    EXPECTED_TASKS,
    MODELS,
    TARGETED_HASHES,
    targeted_task_plan,
)
from taxrep.utils import (
    git_commit,
    load_yaml,
    read_jsonl,
    sha256_bytes,
    sha256_file,
    utc_now_iso,
    write_json,
)

TARGETED_RECOVERY_PROTOCOL_YAML = (
    PROJECT_ROOT / "experiment" / "targeted_t3_repeat_recovery.yaml"
)
TARGETED_RECOVERY_HASHES = (
    PROJECT_ROOT / "experiment" / "targeted_t3_repeat_recovery_hashes.json"
)
TARGETED_RECOVERY_PREFLIGHT = (
    PROJECT_ROOT
    / "results"
    / "run_manifests"
    / "targeted_t3_repeat_recovery_preflight.json"
)
TARGETED_RECOVERY_CATALOG = (
    PROJECT_ROOT
    / "experiment"
    / "provider_catalog_snapshot_20260712_targeted_recovery.json"
)
TARGETED_RECOVERY_HEALTH = (
    PROJECT_ROOT / "experiment" / "provider_health_20260712_targeted_recovery.json"
)
STOPPED_ARTIFACTS = (
    PROJECT_ROOT
    / "results"
    / "run_manifests"
    / "targeted_t3_repeat_stopped_artifacts.json"
)

EXPECTED_PRIOR_SUCCESS = 1_640
EXPECTED_MISSING = 1_060
HISTORICAL_HTTP_ATTEMPT_UPPER_BOUND = 4_938
RECOVERY_HTTP_ATTEMPT_HARD_CAP = 1_360
REVISION_HTTP_ATTEMPT_HARD_CAP = 6_298


def _canonical_hash(payload: Any) -> str:
    return sha256_bytes(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS))


def _commit_is_ancestor(commit: str) -> bool:
    return commit_is_ancestor_or_public_snapshot(commit, root=PROJECT_ROOT)


def _relative_path(value: str) -> Path:
    path = (PROJECT_ROOT / value).resolve()
    try:
        path.relative_to(PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise RuntimeError(f"Recovery path escapes the repository: {value}") from exc
    return path


def recovery_history_paths(
    config_path: Path = TARGETED_RECOVERY_PROTOCOL_YAML,
) -> list[Path]:
    config = load_yaml(config_path)
    paths = [
        _relative_path(str(value))
        for value in config.get("recovery", {}).get("successful_checkpoint_paths", [])
    ]
    if not paths:
        raise RuntimeError("Recovery protocol has no historical checkpoint path")
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Recovery historical checkpoint is missing: "
            + ", ".join(path.relative_to(PROJECT_ROOT).as_posix() for path in missing)
        )
    return paths


def _task_descriptor(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "planned_task_index": int(task["planned_task_index"]),
        "issue_id": str(task["issue_id"]),
        "repository": str(task["repository"]),
        "model_id": str(task["model_id"]),
        "taxonomy_condition": str(task["taxonomy_condition"]),
        "instruction_variant": str(task["instruction_variant"]),
        "repeat_id": int(task["repeat_id"]),
        "seed": int(task["seed"]),
    }


def reconcile_recovery_tasks(
    config_path: Path = TARGETED_RECOVERY_PROTOCOL_YAML,
) -> dict[str, Any]:
    """Reconcile task keys without loading benchmark labels or computing outcomes."""

    from taxrep.inference import build_tasks

    config = load_yaml(config_path)
    tasks = build_tasks(config, model_ids=MODELS)
    if len(tasks) != EXPECTED_TASKS:
        raise RuntimeError(f"Recovery task plan has {len(tasks)} rather than 2,700 tasks")

    planned_by_key = {prediction_task_key(task): task for task in tasks}
    if len(planned_by_key) != EXPECTED_TASKS:
        raise RuntimeError("Recovery task plan contains duplicate task keys")

    records: list[dict[str, Any]] = []
    for path in recovery_history_paths(config_path):
        records.extend(read_jsonl(path))
    canonical = canonicalize_prediction_records(records)
    unresolved = [row for row in canonical if row.get("technical_error")]
    if unresolved:
        raise RuntimeError("Stopped checkpoint has unresolved technical-error task keys")
    successful_keys = {prediction_task_key(row) for row in canonical}
    unknown = successful_keys - set(planned_by_key)
    if unknown:
        raise RuntimeError("Stopped checkpoint contains task keys outside the frozen plan")
    if len(successful_keys) != EXPECTED_PRIOR_SUCCESS:
        raise RuntimeError(
            f"Stopped checkpoint success count is {len(successful_keys)}, expected 1,640"
        )

    completed = [
        _task_descriptor(task)
        for task in tasks
        if prediction_task_key(task) in successful_keys
    ]
    missing = [
        _task_descriptor(task)
        for task in tasks
        if prediction_task_key(task) not in successful_keys
    ]
    if len(missing) != EXPECTED_MISSING:
        raise RuntimeError(f"Recovery missing-task count is {len(missing)}, expected 1,060")

    missing_cells = Counter(
        (
            row["model_id"],
            row["taxonomy_condition"],
            row["repeat_id"],
        )
        for row in missing
    )
    return {
        "planned_tasks": EXPECTED_TASKS,
        "prior_successful_tasks": len(completed),
        "missing_tasks": len(missing),
        "prior_successful_descriptor_sha256": _canonical_hash(completed),
        "missing_descriptor_sha256": _canonical_hash(missing),
        "missing_planned_indices_sha256": _canonical_hash(
            [row["planned_task_index"] for row in missing]
        ),
        "historical_checkpoint_paths": [
            path.relative_to(PROJECT_ROOT).as_posix()
            for path in recovery_history_paths(config_path)
        ],
        "missing_cell_counts": [
            {
                "model_id": key[0],
                "taxonomy_condition": key[1],
                "repeat_id": key[2],
                "count": count,
            }
            for key, count in sorted(missing_cells.items())
        ],
    }


def _load_stopped_artifacts() -> dict[str, Any]:
    if not STOPPED_ARTIFACTS.is_file():
        raise FileNotFoundError("Stopped targeted artifact manifest is missing")
    payload = json.loads(STOPPED_ARTIFACTS.read_text(encoding="utf-8"))
    if payload.get("status") != "stopped_pre_result":
        raise RuntimeError("Historical targeted segment is not marked stopped_pre_result")
    if payload.get("gold_labels_accessed") is not False:
        raise RuntimeError("Historical targeted segment does not prove pre-result handling")
    if int(payload.get("canonical_completed_tasks", -1)) != EXPECTED_PRIOR_SUCCESS:
        raise RuntimeError("Historical stopped count differs from 1,640")
    attempt_range = payload.get("outbound_http_attempt_count_mechanical_range")
    if attempt_range != [1_643, HISTORICAL_HTTP_ATTEMPT_UPPER_BOUND]:
        raise RuntimeError("Historical HTTP-attempt uncertainty range changed")
    return payload


def _verify_historical_checkpoint_hashes(stopped: dict[str, Any]) -> None:
    expected_by_path = {
        str(item["path"]): str(item["sha256"])
        for item in stopped.get("artifacts", [])
        if isinstance(item, dict) and item.get("path") and item.get("sha256")
    }
    required = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in recovery_history_paths()
    ]
    for relative in required:
        expected = expected_by_path.get(relative)
        path = PROJECT_ROOT / relative
        if expected is None or not path.is_file() or sha256_file(path) != expected:
            raise RuntimeError(f"Stopped checkpoint bytes changed: {relative}")


def capture_targeted_recovery_catalog() -> dict[str, Any]:
    if TARGETED_RECOVERY_CATALOG.exists():
        payload = json.loads(TARGETED_RECOVERY_CATALOG.read_text(encoding="utf-8"))
        ids = catalog_model_ids(payload)
        missing = sorted(set(MODELS) - set(ids))
        if missing:
            raise RuntimeError("Frozen recovery catalog lacks routes: " + ", ".join(missing))
        return {
            "path": TARGETED_RECOVERY_CATALOG.relative_to(PROJECT_ROOT).as_posix(),
            "sha256": sha256_file(TARGETED_RECOVERY_CATALOG),
            "model_ids_present": MODELS,
            "existing_immutable_snapshot": True,
        }
    provider = OpenCodeGoProvider.from_models_config()
    result = provider.snapshot_catalog(output_path=TARGETED_RECOVERY_CATALOG)
    missing = sorted(set(MODELS) - set(result["model_ids"]))
    if missing:
        raise RuntimeError("Recovery catalog lacks frozen routes: " + ", ".join(missing))
    return {
        "path": TARGETED_RECOVERY_CATALOG.relative_to(PROJECT_ROOT).as_posix(),
        "sha256": sha256_file(TARGETED_RECOVERY_CATALOG),
        "model_ids_present": MODELS,
        "existing_immutable_snapshot": False,
    }


def _recovery_artifact_paths() -> list[str]:
    stopped = _load_stopped_artifacts()
    historical = [
        str(item["path"])
        for item in stopped.get("artifacts", [])
        if str(item.get("path", "")).startswith(
            (
                "results/raw_predictions/targeted-t3-repeat-",
                "results/run_manifests/targeted-t3-repeat-",
                "results/run_manifests/targeted_t3_repeat_",
                "results/logs/targeted_t3_repeat/",
                "experiment/provider_health_",
            )
        )
    ]
    fixed = [
        "experiment/targeted_t3_repeat_recovery.md",
        "experiment/targeted_t3_repeat_recovery.yaml",
        "experiment/targeted_t3_repeat_extension.md",
        "experiment/targeted_t3_repeat_extension.yaml",
        "experiment/targeted_t3_repeat_extension_hashes.json",
        "experiment/targeted_t3_repeat_sample.json",
        "experiment/prompt_registry.yaml",
        "experiment/prompt_hashes.json",
        "experiment/model_registry.csv",
        "configs/models.yaml",
        "data/manifests/test_processed_manifest.json",
        "results/run_manifests/main_results_freeze.json",
        "results/run_manifests/targeted_t3_repeat_stopped_artifacts.json",
        TARGETED_RECOVERY_CATALOG.relative_to(PROJECT_ROOT).as_posix(),
        "src/taxrep/call_budget.py",
        "src/taxrep/inference.py",
        "src/taxrep/parsers.py",
        "src/taxrep/providers/opencode_go.py",
        "src/taxrep/runs.py",
        "src/taxrep/targeted.py",
        "src/taxrep/targeted_audit.py",
        "src/taxrep/targeted_recovery.py",
        "src/taxrep/targeted_result_gate.py",
        "scripts/capture_targeted_recovery_catalog.py",
        "scripts/freeze_targeted_recovery.py",
        "scripts/freeze_targeted_results.py",
        "scripts/tmux/start_targeted_t3_repeat_recovery.sh",
    ]
    return sorted(set(fixed + historical))


def freeze_targeted_recovery(*, protocol_commit: str) -> dict[str, Any]:
    if not protocol_commit or not _commit_is_ancestor(protocol_commit):
        raise RuntimeError("Recovery protocol commit is missing or is not an ancestor of HEAD")
    if not TARGETED_RECOVERY_CATALOG.is_file():
        raise RuntimeError("Capture the recovery provider catalog before freezing recovery")

    stopped = _load_stopped_artifacts()
    _verify_historical_checkpoint_hashes(stopped)
    original = json.loads(TARGETED_HASHES.read_text(encoding="utf-8"))
    current_plan = targeted_task_plan(TARGETED_RECOVERY_PROTOCOL_YAML)
    if current_plan != original.get("task_plan"):
        raise RuntimeError("Recovery scientific task plan differs from the original freeze")
    reconciliation = reconcile_recovery_tasks()
    config = load_yaml(TARGETED_RECOVERY_PROTOCOL_YAML)
    budget = config.get("completion_call_budget", {})
    recovery = config.get("recovery", {})
    if int(budget.get("hard_cap", -1)) != RECOVERY_HTTP_ATTEMPT_HARD_CAP:
        raise RuntimeError("Recovery ledger cap is not 1,360")
    if int(recovery.get("historical_http_attempt_upper_bound", -1)) != (
        HISTORICAL_HTTP_ATTEMPT_UPPER_BOUND
    ):
        raise RuntimeError("Recovery historical upper bound is not 4,938")
    if int(recovery.get("revision_http_attempt_hard_cap", -1)) != (
        REVISION_HTTP_ATTEMPT_HARD_CAP
    ):
        raise RuntimeError("Revision-wide recovery cap is not 6,298")
    if int(config.get("sdk_max_retries", -1)) != 0:
        raise RuntimeError("Recovery protocol must disable SDK retries")

    hashes: list[dict[str, Any]] = []
    for relative in _recovery_artifact_paths():
        path = PROJECT_ROOT / relative
        if not path.is_file():
            raise FileNotFoundError(f"Missing recovery freeze artifact: {relative}")
        hashes.append(
            {"path": relative, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
        )
    payload = {
        "schema_version": 1,
        "generated_at_utc": utc_now_iso(),
        "scientific_status": (
            "post-result, budget-constrained, targeted robustness extension recovery"
        ),
        "protocol_commit": protocol_commit,
        "current_generation_commit": git_commit(PROJECT_ROOT),
        "original_protocol_commit": original.get("protocol_commit"),
        "original_task_order_sha256": current_plan["task_order_sha256"],
        "artifact_hashes": hashes,
        "reconciliation": reconciliation,
        "budget": {
            "historical_http_attempt_upper_bound": HISTORICAL_HTTP_ATTEMPT_UPPER_BOUND,
            "recovery_http_attempt_hard_cap": RECOVERY_HTTP_ATTEMPT_HARD_CAP,
            "revision_http_attempt_hard_cap": REVISION_HTTP_ATTEMPT_HARD_CAP,
            "planned_recovery_health_calls": 3,
            "planned_missing_canonical_calls": EXPECTED_MISSING,
            "recovery_retry_reserve": 297,
        },
        "result_access_status": (
            "No targeted checkpoint has been joined to benchmark labels and no partial "
            "targeted performance or agreement result has been computed."
        ),
    }
    write_json(TARGETED_RECOVERY_HASHES, payload)
    return payload


def verify_targeted_recovery_freeze(
    config_path: Path = TARGETED_RECOVERY_PROTOCOL_YAML,
) -> dict[str, Any]:
    if config_path.resolve() != TARGETED_RECOVERY_PROTOCOL_YAML.resolve():
        raise RuntimeError("Recovery inference must use the frozen recovery YAML")
    if not TARGETED_RECOVERY_HASHES.is_file():
        raise RuntimeError("Targeted recovery hashes are not frozen")
    payload = json.loads(TARGETED_RECOVERY_HASHES.read_text(encoding="utf-8"))
    protocol_commit = str(payload.get("protocol_commit") or "")
    if not protocol_commit or not _commit_is_ancestor(protocol_commit):
        raise RuntimeError("Recovery protocol commit is missing or is not an ancestor of HEAD")
    mismatches: list[str] = []
    for item in payload.get("artifact_hashes", []):
        relative = str(item.get("path", ""))
        expected_hash = str(item.get("sha256", ""))
        expected_bytes = item.get("bytes")
        match = artifact_hash_match(
            relative,
            expected_hash,
            expected_source_bytes=expected_bytes if isinstance(expected_bytes, int) else None,
            root=PROJECT_ROOT,
        )
        if match is None:
            mismatches.append(relative)
    current_plan = targeted_task_plan(config_path)
    if current_plan["task_order_sha256"] != payload.get("original_task_order_sha256"):
        mismatches.append("original task-order hash")
    reconciliation = reconcile_recovery_tasks(config_path)
    if reconciliation != payload.get("reconciliation"):
        mismatches.append("label-free recovery task reconciliation")
    budget = payload.get("budget", {})
    if (
        int(budget.get("historical_http_attempt_upper_bound", -1))
        + int(budget.get("recovery_http_attempt_hard_cap", -1))
        != int(budget.get("revision_http_attempt_hard_cap", -1))
    ):
        mismatches.append("recovery budget arithmetic")
    if mismatches:
        raise RuntimeError("Targeted recovery freeze mismatch: " + ", ".join(mismatches))
    return {
        "ok": True,
        "protocol_commit": protocol_commit,
        "artifact_count": len(payload.get("artifact_hashes", [])),
        "task_count": current_plan["task_count"],
        "task_order_sha256": current_plan["task_order_sha256"],
        "prior_successful_tasks": reconciliation["prior_successful_tasks"],
        "missing_tasks": reconciliation["missing_tasks"],
        "recovery_http_attempt_hard_cap": RECOVERY_HTTP_ATTEMPT_HARD_CAP,
        "revision_http_attempt_hard_cap": REVISION_HTTP_ATTEMPT_HARD_CAP,
    }


def targeted_recovery_provider_preflight(
    config_path: Path = TARGETED_RECOVERY_PROTOCOL_YAML,
) -> dict[str, Any]:
    freeze = verify_targeted_recovery_freeze(config_path)
    if TARGETED_RECOVERY_PREFLIGHT.exists():
        existing = json.loads(TARGETED_RECOVERY_PREFLIGHT.read_text(encoding="utf-8"))
        if existing.get("status") == "passed":
            return existing
        raise RuntimeError("A recovery provider preflight exists but did not pass")
    config = load_yaml(config_path)
    budget = CompletionCallBudget.from_config(PROJECT_ROOT, config["completion_call_budget"])
    budget.initialize()
    if int(budget.snapshot()["used"]) != 0:
        raise RuntimeError("Recovery call budget is not empty before provider preflight")
    catalog = json.loads(TARGETED_RECOVERY_CATALOG.read_text(encoding="utf-8"))
    missing_routes = sorted(set(MODELS) - set(catalog_model_ids(catalog)))
    if missing_routes:
        raise RuntimeError("Recovery catalog lacks frozen routes: " + ", ".join(missing_routes))
    provider = OpenCodeGoProvider.from_models_config()
    result = provider.health_check(
        MODELS,
        call_budget=budget,
        run_id="targeted-t3-repeat-recovery-provider-health",
        output_path=TARGETED_RECOVERY_HEALTH,
    )
    rules = config["response_model_compatibility"]
    checks: list[dict[str, Any]] = []
    for record in result["records"]:
        response_model = record.get("response_model")
        compatible = bool(response_model) and any(
            token.casefold() in str(response_model).casefold()
            for token in rules[record["model_id"]]
        )
        checks.append(
            {
                "model_id": record["model_id"],
                "health_ok": bool(record.get("ok")),
                "response_model": response_model,
                "response_model_compatible": compatible,
                "finish_reason": record.get("finish_reason"),
            }
        )
    passed = all(row["health_ok"] and row["response_model_compatible"] for row in checks)
    snapshot = budget.snapshot()
    payload = {
        "schema_version": 1,
        "status": "passed" if passed else "failed",
        "completed_at_utc": utc_now_iso(),
        "freeze": freeze,
        "checks": checks,
        "provider_catalog_artifact": TARGETED_RECOVERY_CATALOG.relative_to(
            PROJECT_ROOT
        ).as_posix(),
        "provider_catalog_sha256": sha256_file(TARGETED_RECOVERY_CATALOG),
        "provider_health_artifact": TARGETED_RECOVERY_HEALTH.relative_to(
            PROJECT_ROOT
        ).as_posix(),
        "provider_health_sha256": sha256_file(TARGETED_RECOVERY_HEALTH),
        "completion_call_budget": snapshot,
        "conservative_revision_http_attempt_upper_bound_after_preflight": (
            HISTORICAL_HTTP_ATTEMPT_UPPER_BOUND + int(snapshot["used"])
        ),
    }
    write_json(TARGETED_RECOVERY_PREFLIGHT, payload)
    if not passed or int(snapshot["used"]) != 3:
        raise RuntimeError("Recovery provider preflight did not pass all frozen routes")
    return payload


def assert_targeted_recovery_preflight_ready() -> dict[str, Any]:
    if not TARGETED_RECOVERY_PREFLIGHT.is_file():
        raise RuntimeError("Run the recovery provider preflight before inference")
    payload = json.loads(TARGETED_RECOVERY_PREFLIGHT.read_text(encoding="utf-8"))
    if payload.get("status") != "passed":
        raise RuntimeError("Targeted recovery provider preflight is not passed")
    if int(payload.get("completion_call_budget", {}).get("used", -1)) != 3:
        raise RuntimeError("Recovery preflight call count is not exactly three")
    health_path = PROJECT_ROOT / str(payload.get("provider_health_artifact", ""))
    if not health_path.is_file() or sha256_file(health_path) != payload.get(
        "provider_health_sha256"
    ):
        raise RuntimeError("Recovery provider health artifact changed after preflight")
    config = load_yaml(TARGETED_RECOVERY_PROTOCOL_YAML)
    budget = CompletionCallBudget.from_config(PROJECT_ROOT, config["completion_call_budget"])
    snapshot = budget.snapshot()
    if int(snapshot["used"]) < 3 or int(snapshot["used"]) > RECOVERY_HTTP_ATTEMPT_HARD_CAP:
        raise RuntimeError("Recovery ledger is outside its frozen bounds")
    return payload
