from __future__ import annotations

import random
import threading
import time
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from taxrep.call_budget import CompletionCallBudget, CompletionCallBudgetExceeded
from taxrep.constants import PROJECT_ROOT, PROTOCOL_VERSION
from taxrep.data import load_processed, select_stratified_sample
from taxrep.gates import assert_freeze_approved
from taxrep.parsers import lenient_parse, strict_parse
from taxrep.prompts import render_prompt
from taxrep.providers.opencode_go import OpenCodeGoProvider
from taxrep.run_lock import RunLock
from taxrep.runs import (
    canonicalize_prediction_records,
    derive_run_type,
    ensure_run_type,
    prediction_task_key,
)
from taxrep.utils import (
    append_jsonl,
    environment_snapshot,
    git_commit,
    load_yaml,
    read_jsonl,
    sha256_text,
    utc_now_iso,
    write_json,
)

_THREAD_LOCAL = threading.local()


def load_models(path: Path | None = None) -> list[str]:
    config_path = path or PROJECT_ROOT / "configs" / "models.yaml"
    raw = load_yaml(config_path)
    return [item["id"] for item in raw["models"]]


def load_experiment_config(path: Path) -> dict[str, Any]:
    return load_yaml(path)


def select_issues(config: dict[str, Any]) -> pd.DataFrame:
    split = config["dataset_split"]
    sample = config.get("sample", {"strategy": "all"})
    if sample["strategy"] == "all":
        return load_processed(split, include_label=False)
    if sample["strategy"] == "first_n":
        frame = load_processed(split, include_label=False).head(int(sample["n"])).copy()
        if config["run_type"] == "technical-pretest":
            write_json(
                PROJECT_ROOT / "data" / "manifests" / "technical_pretest_issue_ids.json",
                {
                    "run_type": config["run_type"],
                    "dataset_split": split,
                    "issue_ids": frame["issue_id"].tolist(),
                },
            )
        return frame
    if sample["strategy"] == "stratified_project_label":
        gold = load_processed(split, include_label=True)
        exclude_ids: set[str] = set()
        manifest = sample.get("exclude_issue_manifest")
        if manifest:
            manifest_path = PROJECT_ROOT / manifest
            if manifest_path.exists():
                exclude_ids = set(load_yaml(manifest_path).get("issue_ids", []))
        selected = select_stratified_sample(
            gold,
            per_project_label=int(sample["per_project_label"]),
            seed=int(sample["seed"]),
            exclude_issue_ids=exclude_ids,
        )
        return selected.drop(columns=["label"])
    if sample["strategy"] == "issue_id_manifest":
        import orjson

        manifest_path = PROJECT_ROOT / str(sample["manifest"])
        payload = orjson.loads(manifest_path.read_bytes())
        issue_ids = [str(issue_id) for issue_id in payload["issue_ids"]]
        if len(issue_ids) != len(set(issue_ids)):
            raise ValueError("Issue-id sample manifest contains duplicate ids")
        expected_count = int(sample.get("expected_count", len(issue_ids)))
        if len(issue_ids) != expected_count:
            raise ValueError(
                f"Issue-id sample count mismatch: {len(issue_ids)} != {expected_count}"
            )
        frame = load_processed(split, include_label=False)
        by_id = frame.set_index("issue_id", drop=False)
        missing = sorted(set(issue_ids) - set(by_id.index))
        if missing:
            raise ValueError(f"Issue-id sample manifest contains {len(missing)} unknown ids")
        return by_id.loc[issue_ids].reset_index(drop=True)
    raise ValueError(f"Unknown sample strategy: {sample['strategy']}")


def build_tasks(config: dict[str, Any], *, model_ids: list[str]) -> list[dict[str, Any]]:
    issues = select_issues(config)
    tasks: list[dict[str, Any]] = []
    repeat_seeds = config.get("repeat_seeds")
    for model_id in model_ids:
        for _, issue in issues.iterrows():
            for condition in config["taxonomy_conditions"]:
                for instruction_variant in config["instruction_variants"]:
                    for repeat_id in range(1, int(config["repeats"]) + 1):
                        seed = None
                        if repeat_seeds:
                            seed = int(repeat_seeds[repeat_id - 1])
                        elif config.get("seed") is not None:
                            seed = int(config["seed"])
                        tasks.append(
                            {
                                "run_type": config["run_type"],
                                "dataset_split": config["dataset_split"],
                                "issue_id": issue["issue_id"],
                                "repository": issue["repository"],
                                "title": issue["title"],
                                "body": issue["body"],
                                "model_id": model_id,
                                "taxonomy_condition": condition,
                                "instruction_variant": instruction_variant,
                                "repeat_id": repeat_id,
                                "seed": seed,
                                "temperature": float(config["temperature"]),
                                "top_p": float(config["top_p"]),
                                "max_new_tokens": int(config["max_new_tokens"]),
                            }
                        )
    execution_order = config.get("execution_order", "nested")
    if execution_order == "deterministic_shuffle":
        execution_seed = int(config.get("execution_seed", config.get("seed", 0)))
        random.Random(execution_seed).shuffle(tasks)
    elif execution_order != "nested":
        raise ValueError(f"Unknown execution_order: {execution_order}")
    for planned_task_index, task in enumerate(tasks, start=1):
        task["planned_task_index"] = planned_task_index
    return tasks


def concurrency_limits(config: dict[str, Any], model_ids: list[str]) -> dict[str, Any]:
    raw = config.get("concurrency", {})
    by_model = raw.get("by_model", {})
    model_limits = {model_id: max(1, int(by_model.get(model_id, 1))) for model_id in model_ids}
    global_limit = max(1, int(raw.get("global", sum(model_limits.values()))))
    return {
        "global": min(global_limit, sum(model_limits.values())),
        "by_model": model_limits,
    }


def _completed_keys(path: Path) -> set[tuple[Any, ...]]:
    completed: set[tuple[Any, ...]] = set()
    for record in read_jsonl(path):
        if not record.get("technical_error"):
            completed.add(prediction_task_key(record))
    return completed


def _completed_keys_from_paths(paths: list[Path]) -> set[tuple[Any, ...]]:
    completed: set[tuple[Any, ...]] = set()
    for path in paths:
        completed.update(_completed_keys(path))
    return completed


def _select_pending_tasks(
    tasks: list[dict[str, Any]],
    *,
    historical_completed: set[tuple[Any, ...]],
    checkpoint_completed: set[tuple[Any, ...]],
) -> list[dict[str, Any]]:
    planned_keys = {prediction_task_key(task) for task in tasks}
    unknown_completed = (checkpoint_completed | historical_completed) - planned_keys
    if unknown_completed:
        raise RuntimeError("Completed checkpoint contains task keys outside the frozen plan")
    overlap = checkpoint_completed & historical_completed
    if overlap:
        raise RuntimeError(
            "Recovery checkpoint repeats a task already successful in the stopped segment"
        )
    completed = checkpoint_completed | historical_completed
    return [task for task in tasks if prediction_task_key(task) not in completed]


def _checkpoint_to_parquet(jsonl_path: Path, parquet_path: Path) -> None:
    records = [
        {key: value for key, value in record.items() if key != "response_headers"}
        for record in canonicalize_prediction_records(read_jsonl(jsonl_path))
    ]
    if not records:
        return
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    ensure_run_type(pd.DataFrame.from_records(records)).to_parquet(parquet_path, index=False)


def _thread_provider(timeout_seconds: int) -> OpenCodeGoProvider:
    provider = getattr(_THREAD_LOCAL, "provider", None)
    if provider is None:
        provider = OpenCodeGoProvider.from_models_config(timeout_seconds=timeout_seconds)
        _THREAD_LOCAL.provider = provider
    return provider


def _execute_task(
    task: dict[str, Any],
    *,
    max_attempts: int,
    timeout_seconds: int,
    hardware_snapshot_id: str,
    model_semaphore: threading.Semaphore,
    call_budget: CompletionCallBudget | None = None,
    invocation_id: str | None = None,
    provenance_segment: str | None = None,
    response_model_rules: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    rendered = render_prompt(
        condition=task["taxonomy_condition"],
        title=task["title"],
        body=task["body"],
        instruction_variant=task["instruction_variant"],
    )
    start = utc_now_iso()
    start_time = time.perf_counter()
    technical_error: str | None = None
    raw_output = ""
    response_model = None
    usage: dict[str, Any] = {}
    response_headers: dict[str, Any] = {}
    request_parameters: dict[str, Any] = {}
    provider_request_id: str | None = None
    finish_reason: str | None = None
    system_fingerprint: str | None = None
    completion_call_ordinals: list[int] = []
    route_compatible: bool | None = None
    fatal_stop_reason: str | None = None
    retry_count = 0
    with model_semaphore:
        provider = _thread_provider(timeout_seconds)
        for attempt in range(1, max_attempts + 1):
            try:
                if call_budget is not None:
                    task_key = "\n".join(str(value) for value in prediction_task_key(task))
                    completion_call_ordinals.append(
                        call_budget.reserve(
                            kind="targeted_inference",
                            model_id=str(task["model_id"]),
                            run_id=str(task["run_id"]),
                            task_key=task_key,
                            attempt=attempt,
                        )
                    )
                response = provider.chat_completion(
                    model_id=task["model_id"],
                    system_message=rendered.system_message,
                    user_message=rendered.user_message,
                    temperature=task["temperature"],
                    top_p=task["top_p"],
                    max_new_tokens=task["max_new_tokens"],
                    seed=task["seed"],
                )
                raw_output = response.raw_output
                response_model = response.response_model
                usage = response.usage
                response_headers = response.response_headers
                request_parameters = response.request_parameters
                provider_request_id = response.request_id
                finish_reason = response.finish_reason
                system_fingerprint = response.system_fingerprint
                technical_error = None
                retry_count = attempt - 1
                break
            except CompletionCallBudgetExceeded:
                raise
            except Exception as exc:
                technical_error = f"{type(exc).__name__}: {str(exc)[:500]}"
                retry_count = attempt - 1
                if attempt < max_attempts:
                    time.sleep(min(60, 2**attempt))
    allowed = (response_model_rules or {}).get(str(task["model_id"]), [])
    if technical_error is None and response_model and allowed:
        route_compatible = any(
            token.casefold() in str(response_model).casefold() for token in allowed
        )
        if not route_compatible:
            fatal_stop_reason = (
                "Provider response model is incompatible with the frozen alias rule for "
                f"{task['model_id']}"
            )
            technical_error = fatal_stop_reason
    end = utc_now_iso()
    latency_ms = int((time.perf_counter() - start_time) * 1000)
    strict = strict_parse(raw_output)
    lenient = lenient_parse(raw_output)
    input_char_count = len(rendered.user_message) + len(rendered.system_message)
    return {
        "run_id": task["run_id"],
        "invocation_id": invocation_id,
        "protocol_version": PROTOCOL_VERSION,
        "run_type": task["run_type"],
        "dataset_split": task["dataset_split"],
        "issue_id": task["issue_id"],
        "repository": task["repository"],
        "gold_label_hidden_at_inference": True,
        "model_id": task["model_id"],
        "model_revision": response_model,
        "response_model": response_model,
        "route_compatible": route_compatible,
        "taxonomy_condition": task["taxonomy_condition"],
        "instruction_variant": task["instruction_variant"],
        "repeat_id": task["repeat_id"],
        "planned_task_index": task["planned_task_index"],
        "seed": task["seed"],
        "temperature": task["temperature"],
        "top_p": task["top_p"],
        "max_new_tokens": task["max_new_tokens"],
        "api_max_tokens": request_parameters.get("api_max_tokens"),
        "temperature_sent": request_parameters.get("temperature_sent"),
        "top_p_sent": request_parameters.get("top_p_sent"),
        "seed_sent": request_parameters.get("seed_sent"),
        "prompt_hash": rendered.prompt_hash,
        "rendered_prompt_hash": rendered.rendered_prompt_hash,
        "input_char_count": input_char_count,
        "input_token_count": usage.get("prompt_tokens"),
        "was_truncated": False,
        "start_timestamp": start,
        "end_timestamp": end,
        "latency_ms": latency_ms,
        "output_token_count": usage.get("completion_tokens"),
        "provider_usage": usage,
        "finish_reason": finish_reason,
        "system_fingerprint": system_fingerprint,
        "provider_request_id": provider_request_id,
        "effective_request_parameters": request_parameters,
        "provider_provenance_segment": provenance_segment,
        "completion_call_ordinals": completion_call_ordinals,
        "raw_output": raw_output,
        "strict_parse_success": strict.success,
        "strict_label": strict.label,
        "lenient_parse_success": lenient.success,
        "lenient_label": lenient.label,
        "recovery_rule": lenient.recovery_rule,
        "technical_error": technical_error,
        "fatal_stop_reason": fatal_stop_reason,
        "retry_count": retry_count,
        "hardware_snapshot_id": hardware_snapshot_id,
        "response_headers": response_headers,
    }


def run_inference(config_path: Path, *, model_id: str | None = None) -> dict[str, Any]:
    if not config_path.is_absolute():
        config_path = (PROJECT_ROOT / config_path).resolve()
    config = load_experiment_config(config_path)
    assert_freeze_approved(config["run_type"])
    recovery_history: list[Path] = []
    is_targeted_recovery = False
    recovery_budget_metadata: dict[str, int] = {}
    if config["run_type"] == "targeted-t3-repeat":
        if model_id is not None:
            raise RuntimeError(
                "The targeted extension must run all three systems in one interleaved queue"
            )
        from taxrep.targeted_recovery import (
            HISTORICAL_HTTP_ATTEMPT_UPPER_BOUND,
            REVISION_HTTP_ATTEMPT_HARD_CAP,
            TARGETED_RECOVERY_PROTOCOL_YAML,
            assert_targeted_recovery_preflight_ready,
            recovery_history_paths,
            verify_targeted_recovery_freeze,
        )

        is_targeted_recovery = (
            config_path.resolve() == TARGETED_RECOVERY_PROTOCOL_YAML.resolve()
        )
        if is_targeted_recovery:
            verify_targeted_recovery_freeze(config_path)
            assert_targeted_recovery_preflight_ready()
            recovery_history = recovery_history_paths(config_path)
            recovery_budget_metadata = {
                "historical_http_attempt_upper_bound": (
                    HISTORICAL_HTTP_ATTEMPT_UPPER_BOUND
                ),
                "revision_http_attempt_hard_cap": REVISION_HTTP_ATTEMPT_HARD_CAP,
            }
        else:
            from taxrep.targeted import (
                assert_targeted_preflight_ready,
                verify_targeted_extension_freeze,
            )

            verify_targeted_extension_freeze(config_path)
            assert_targeted_preflight_ready()
    model_ids = [model_id] if model_id else load_models()
    tasks = build_tasks(config, model_ids=model_ids)
    run_fingerprint = sha256_text(
        f"{config_path.name}\n{config}\n{','.join(model_ids)}\n{PROTOCOL_VERSION}"
    )[:16]
    run_id = f"{config['run_type']}-{run_fingerprint}"
    if model_id:
        run_id = f"{config['run_type']}-{model_id}-{run_fingerprint}"
    checkpoint_path = PROJECT_ROOT / "results" / "raw_predictions" / f"{run_id}.jsonl"
    parquet_path = PROJECT_ROOT / "results" / "raw_predictions" / f"{run_id}.parquet"
    manifest_path = PROJECT_ROOT / "results" / "run_manifests" / f"{run_id}.json"
    lock_path = PROJECT_ROOT / "results" / "run_manifests" / f"{run_id}.lock"
    checkpoint_completed = _completed_keys(checkpoint_path)
    historical_completed = _completed_keys_from_paths(recovery_history)
    planned_keys = {prediction_task_key(task) for task in tasks}
    completed = checkpoint_completed | historical_completed
    pending = _select_pending_tasks(
        tasks,
        historical_completed=historical_completed,
        checkpoint_completed=checkpoint_completed,
    )
    limits = concurrency_limits(config, model_ids)
    started_at_utc = utc_now_iso()
    invocation_id = f"{run_id}-{started_at_utc.replace(':', '').replace('+', '_')}"
    provenance_segment = config.get("provenance_segment")
    call_budget = None
    if config.get("completion_call_budget"):
        call_budget = CompletionCallBudget.from_config(
            PROJECT_ROOT, config["completion_call_budget"]
        )
        call_budget.initialize()
    manifest = {
        "run_id": run_id,
        "protocol_version": PROTOCOL_VERSION,
        "config_path": str(config_path.relative_to(PROJECT_ROOT)),
        "model_ids": model_ids,
        "task_count_total": len(tasks),
        "task_count_completed_before_start": len(completed),
        "task_count_historical_successful": len(historical_completed),
        "task_count_checkpoint_successful_before_start": len(checkpoint_completed),
        "task_count_pending_before_start": len(pending),
        "historical_checkpoint_paths": [
            path.relative_to(PROJECT_ROOT).as_posix() for path in recovery_history
        ],
        "started_at_utc": started_at_utc,
        "invocation_id": invocation_id,
        "provider_provenance_segment": provenance_segment,
        "git_commit": git_commit(PROJECT_ROOT),
        "environment": environment_snapshot(PROJECT_ROOT),
        "concurrency": limits,
        "completion_call_budget": call_budget.snapshot() if call_budget else None,
        "recovery_budget": recovery_budget_metadata or None,
    }
    max_attempts = int(config.get("retry", {}).get("max_attempts", 3))
    timeout_seconds = int(config.get("retry", {}).get("timeout_seconds", 120))
    for task in pending:
        task["run_id"] = run_id
    model_semaphores = {
        model: threading.Semaphore(limit) for model, limit in limits["by_model"].items()
    }
    raw_records = read_jsonl(checkpoint_path)
    current_successful_keys = {
        prediction_task_key(record) for record in raw_records if not record.get("technical_error")
    }
    unresolved_keys = {
        prediction_task_key(record) for record in raw_records if record.get("technical_error")
    } - current_successful_keys
    stop_rules = config.get("stop_rules", {})
    max_error_fraction = stop_rules.get("max_unresolved_technical_error_fraction")
    max_unresolved = (
        int(len(tasks) * float(max_error_fraction))
        if max_error_fraction is not None
        else None
    )
    fatal_stop_reason: str | None = None
    with RunLock(lock_path, manifest):
        with ThreadPoolExecutor(max_workers=limits["global"]) as executor:
            futures = [
                executor.submit(
                    _execute_task,
                    task,
                    max_attempts=max_attempts,
                    timeout_seconds=timeout_seconds,
                    hardware_snapshot_id=manifest["environment"]["captured_at_utc"],
                    model_semaphore=model_semaphores[task["model_id"]],
                    call_budget=call_budget,
                    invocation_id=invocation_id,
                    provenance_segment=str(provenance_segment) if provenance_segment else None,
                    response_model_rules=config.get("response_model_compatibility"),
                )
                for task in pending
            ]
            for future in as_completed(futures):
                if future.cancelled():
                    continue
                try:
                    record = future.result()
                except CancelledError:
                    continue
                except CompletionCallBudgetExceeded as exc:
                    fatal_stop_reason = str(exc)
                    for other in futures:
                        other.cancel()
                    continue
                append_jsonl(checkpoint_path, record)
                key = prediction_task_key(record)
                if record.get("technical_error"):
                    unresolved_keys.add(key)
                else:
                    unresolved_keys.discard(key)
                if record.get("fatal_stop_reason"):
                    fatal_stop_reason = str(record["fatal_stop_reason"])
                if max_unresolved is not None and len(unresolved_keys) > max_unresolved:
                    fatal_stop_reason = (
                        f"Unresolved technical errors exceeded {max_unresolved} "
                        f"of {len(tasks)} canonical tasks"
                    )
                if fatal_stop_reason:
                    for other in futures:
                        other.cancel()
        _checkpoint_to_parquet(checkpoint_path, parquet_path)
    final_checkpoint_completed = _completed_keys(checkpoint_path)
    final_completed = historical_completed | final_checkpoint_completed
    if final_completed - planned_keys:
        fatal_stop_reason = "Canonical successful task union contains unknown task keys"
    final_missing = len(tasks) - len(final_completed)
    if final_missing < 0:
        fatal_stop_reason = "Canonical successful task union exceeds the frozen task plan"
    final_status = "completed"
    if fatal_stop_reason:
        final_status = "stopped"
    elif final_missing or unresolved_keys:
        final_status = "incomplete"
    budget_snapshot = call_budget.snapshot() if call_budget else None
    if is_targeted_recovery and budget_snapshot is not None:
        recovery_budget_metadata = {
            **recovery_budget_metadata,
            "recovery_http_attempts_reserved": int(budget_snapshot["used"]),
            "conservative_revision_http_attempt_upper_bound": (
                int(recovery_budget_metadata["historical_http_attempt_upper_bound"])
                + int(budget_snapshot["used"])
            ),
        }
    manifest.update(
        {
            "completed_at_utc": utc_now_iso(),
            "checkpoint_path": str(checkpoint_path.relative_to(PROJECT_ROOT)),
            "parquet_path": str(parquet_path.relative_to(PROJECT_ROOT)),
            "task_count_completed_after_run": len(final_completed),
            "task_count_checkpoint_successful_after_run": len(final_checkpoint_completed),
            "task_count_missing_after_run": final_missing,
            "task_count_total": len(tasks),
            "unresolved_technical_error_tasks": len(unresolved_keys),
            "fatal_stop_reason": fatal_stop_reason,
            "status": final_status,
            "completion_call_budget": budget_snapshot,
            "recovery_budget": recovery_budget_metadata or None,
        }
    )
    write_json(manifest_path, manifest)
    if fatal_stop_reason:
        raise RuntimeError(f"Inference stopped by frozen rule: {fatal_stop_reason}")
    if is_targeted_recovery and final_status != "completed":
        raise RuntimeError(
            "Targeted recovery remains incomplete: "
            f"missing={final_missing}, unresolved={len(unresolved_keys)}"
        )
    return manifest


def parse_raw_predictions() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    excluded_targeted_rows = 0
    for path in sorted((PROJECT_ROOT / "results" / "raw_predictions").glob("*.jsonl")):
        if derive_run_type(path.stem) == "targeted-t3-repeat":
            # Keep the stopped checkpoint out of the generic parser without even
            # deserializing its model-output records.  The dedicated targeted path
            # owns both completed-result integrity checks and repeat-aware analysis.
            with path.open("rb") as handle:
                excluded_targeted_rows += sum(1 for line in handle if line.strip())
            continue
        for record in read_jsonl(path):
            run_type = record.get("run_type") or derive_run_type(
                str(record.get("run_id", ""))
            )
            if run_type == "targeted-t3-repeat":
                excluded_targeted_rows += 1
                continue
            rows.append({key: value for key, value in record.items() if key != "response_headers"})
    rows = canonicalize_prediction_records(rows)
    if not rows:
        raise RuntimeError(
            "No generic-analysis prediction rows remain after excluding "
            f"{excluded_targeted_rows} targeted-t3-repeat rows; refusing to leave a "
            "stale global parsed artifact as a successful parse result"
        )
    frame = ensure_run_type(pd.DataFrame.from_records(rows))
    out = PROJECT_ROOT / "results" / "parsed_predictions" / "parsed_predictions.parquet"
    frame.to_parquet(out, index=False)
    return {
        "parsed_files": 1,
        "rows": len(frame),
        "path": str(out),
        "excluded_targeted_rows": excluded_targeted_rows,
    }


def dataclass_to_dict(obj: Any) -> dict[str, Any]:
    return asdict(obj)
