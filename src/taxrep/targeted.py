from __future__ import annotations

import json
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any

import krippendorff  # type: ignore[import-untyped]
import numpy as np
import orjson
import pandas as pd  # type: ignore[import-untyped]

from taxrep.call_budget import CompletionCallBudget
from taxrep.constants import LABELS, PROJECT_ROOT
from taxrep.data import load_processed, select_stratified_sample
from taxrep.metrics import INVALID_LABEL, classification_metrics
from taxrep.providers.opencode_go import OpenCodeGoProvider
from taxrep.public_artifact import artifact_hash_match, commit_is_ancestor_or_public_snapshot
from taxrep.runs import canonicalize_prediction_records, ensure_run_type
from taxrep.utils import (
    git_commit,
    load_yaml,
    read_jsonl,
    sha256_bytes,
    sha256_file,
    sha256_text,
    utc_now_iso,
    write_json,
)

TARGETED_RUN_TYPE = "targeted-t3-repeat"
TARGETED_PROTOCOL_YAML = PROJECT_ROOT / "experiment" / "targeted_t3_repeat_extension.yaml"
TARGETED_SAMPLE = PROJECT_ROOT / "experiment" / "targeted_t3_repeat_sample.json"
TARGETED_HASHES = PROJECT_ROOT / "experiment" / "targeted_t3_repeat_extension_hashes.json"
TARGETED_PREFLIGHT = (
    PROJECT_ROOT / "results" / "run_manifests" / "targeted_t3_repeat_preflight.json"
)
TARGETED_RESULTS_DIR = PROJECT_ROOT / "results" / "tables"
TARGETED_STATS_DIR = PROJECT_ROOT / "results" / "statistics"
MODELS = ["deepseek-v4-flash", "kimi-k2.7-code", "glm-5.2"]
CONDITIONS = ["T0", "T3"]
REPEATS = [1, 2, 3]
EXPECTED_TASKS = 2_700


def _canonical_json_hash(payload: Any) -> str:
    return sha256_bytes(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS))


def _raw_records(pattern: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((PROJECT_ROOT / "results" / "raw_predictions").glob(pattern)):
        rows.extend(read_jsonl(path))
    return canonicalize_prediction_records(rows)


def generate_targeted_sample_manifest() -> dict[str, Any]:
    gold = load_processed("test", include_label=True)
    selected = select_stratified_sample(
        gold,
        per_project_label=10,
        seed=20260704,
    )
    issue_ids = selected["issue_id"].astype(str).tolist()
    robustness = ensure_run_type(pd.DataFrame.from_records(_raw_records("robustness-*.jsonl")))
    if robustness.empty:
        raise RuntimeError("The frozen robustness rows are unavailable")
    robustness_ids = set(robustness["issue_id"].astype(str))
    if robustness_ids != set(issue_ids) or len(robustness_ids) != 150:
        raise RuntimeError("Reconstructed sample does not match the frozen robustness issue set")
    strata = (
        selected.groupby(["repository", "label"], sort=True)
        .size()
        .rename("count")
        .reset_index()
    )
    if set(strata["count"].tolist()) != {10} or len(strata) != 15:
        raise RuntimeError("The frozen sample is not balanced across the 15 strata")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "source_run_type": "robustness",
        "source_config": "configs/robustness.yaml",
        "selection_status": "existing prespecified robustness sample; not reselected",
        "selection_seed": 20260704,
        "per_repository_gold_label": 10,
        "issue_count": len(issue_ids),
        "ordered_issue_id_sha256": sha256_text("\n".join(issue_ids)),
        "set_issue_id_sha256": sha256_text("\n".join(sorted(issue_ids))),
        "repository_counts": selected["repository"].value_counts().sort_index().to_dict(),
        "strata_counts": strata.to_dict(orient="records"),
        "issue_ids": issue_ids,
    }
    write_json(TARGETED_SAMPLE, payload)
    return payload


def targeted_task_plan(config_path: Path = TARGETED_PROTOCOL_YAML) -> dict[str, Any]:
    from taxrep.inference import build_tasks

    config = load_yaml(config_path)
    tasks = build_tasks(config, model_ids=MODELS)
    descriptors = [
        {
            "planned_task_index": int(task["planned_task_index"]),
            "issue_id": str(task["issue_id"]),
            "repository": str(task["repository"]),
            "model_id": str(task["model_id"]),
            "taxonomy_condition": str(task["taxonomy_condition"]),
            "instruction_variant": str(task["instruction_variant"]),
            "repeat_id": int(task["repeat_id"]),
            "seed": int(task["seed"]),
        }
        for task in tasks
    ]
    cells = Counter(
        (
            row["model_id"],
            row["taxonomy_condition"],
            row["instruction_variant"],
            row["repeat_id"],
        )
        for row in descriptors
    )
    expected_cells = len(MODELS) * len(CONDITIONS) * len(REPEATS)
    if len(tasks) != EXPECTED_TASKS:
        raise RuntimeError(f"Targeted task count mismatch: {len(tasks)} != {EXPECTED_TASKS}")
    if len(cells) != expected_cells or set(cells.values()) != {150}:
        raise RuntimeError("Targeted system-condition-repeat cells are unbalanced")
    if {row["instruction_variant"] for row in descriptors} != {"P1"}:
        raise RuntimeError("Targeted plan contains a non-P1 instruction")
    return {
        "task_count": len(descriptors),
        "task_order_sha256": _canonical_json_hash(descriptors),
        "cell_count": len(cells),
        "rows_per_cell": 150,
        "models": MODELS,
        "conditions": CONDITIONS,
        "repeat_ids": REPEATS,
        "repeat_seeds": [4409, 5501, 6607],
        "execution_seed": int(config["execution_seed"]),
        "cell_counts": [
            {
                "model_id": key[0],
                "taxonomy_condition": key[1],
                "instruction_variant": key[2],
                "repeat_id": key[3],
                "count": count,
            }
            for key, count in sorted(cells.items())
        ],
    }


def _latest_provider_artifacts() -> list[str]:
    artifacts: list[str] = []
    for pattern in (
        "provider_catalog_snapshot_*.json",
        "provider_limits_snapshot_*.md",
        "provider_snapshot_summary_*.json",
    ):
        matches = sorted((PROJECT_ROOT / "experiment").glob(pattern))
        if matches:
            artifacts.append(str(matches[-1].relative_to(PROJECT_ROOT)))
    return artifacts


def freeze_targeted_extension(*, protocol_commit: str | None = None) -> dict[str, Any]:
    sample = generate_targeted_sample_manifest()
    task_plan = targeted_task_plan()
    artifact_paths = [
        "experiment/targeted_t3_repeat_extension.md",
        "experiment/targeted_t3_repeat_extension.yaml",
        "experiment/targeted_t3_repeat_sample.json",
        "experiment/prompt_registry.yaml",
        "experiment/prompt_hashes.json",
        "experiment/model_registry.csv",
        "configs/models.yaml",
        "data/manifests/test_processed_manifest.json",
        "results/run_manifests/main_results_freeze.json",
        "src/taxrep/call_budget.py",
        "src/taxrep/inference.py",
        "src/taxrep/parsers.py",
        "src/taxrep/providers/opencode_go.py",
        "src/taxrep/runs.py",
        "src/taxrep/targeted.py",
        "scripts/freeze_targeted_extension.py",
        "scripts/tmux/start_targeted_t3_repeat.sh",
    ] + _latest_provider_artifacts()
    hashes = []
    for relative in artifact_paths:
        path = PROJECT_ROOT / relative
        if not path.exists():
            raise FileNotFoundError(f"Missing targeted freeze artifact: {relative}")
        hashes.append({"path": relative, "sha256": sha256_file(path)})
    prompt_payload = json.loads(
        (PROJECT_ROOT / "experiment" / "prompt_hashes.json").read_text(encoding="utf-8")
    )
    prompts = {
        row["condition"]: {
            "prompt_hash": row["prompt_hash"],
            "rendered_example_hash": row["rendered_prompt_hash"],
        }
        for row in prompt_payload["rendered_examples"]
        if row["condition"] in CONDITIONS
    }
    payload = {
        "schema_version": 1,
        "generated_at_utc": utc_now_iso(),
        "scientific_status": (
            "post-result, budget-constrained, targeted robustness extension"
        ),
        "protocol_commit": protocol_commit,
        "current_generation_commit": git_commit(PROJECT_ROOT),
        "artifact_hashes": hashes,
        "sample": {
            "issue_count": sample["issue_count"],
            "ordered_issue_id_sha256": sample["ordered_issue_id_sha256"],
            "set_issue_id_sha256": sample["set_issue_id_sha256"],
        },
        "prompts": prompts,
        "task_plan": task_plan,
        "completion_call_hard_cap": 3000,
        "planned_health_calls": 3,
        "planned_canonical_calls": EXPECTED_TASKS,
    }
    write_json(TARGETED_HASHES, payload)
    return payload


def _commit_is_ancestor(commit: str) -> bool:
    return commit_is_ancestor_or_public_snapshot(commit, root=PROJECT_ROOT)


def verify_targeted_extension_freeze(
    config_path: Path = TARGETED_PROTOCOL_YAML,
) -> dict[str, Any]:
    if config_path.resolve() != TARGETED_PROTOCOL_YAML.resolve():
        raise RuntimeError("Targeted inference must use the frozen protocol YAML")
    if not TARGETED_HASHES.exists():
        raise RuntimeError("Targeted extension hashes are not frozen")
    payload = orjson.loads(TARGETED_HASHES.read_bytes())
    protocol_commit = payload.get("protocol_commit")
    if not protocol_commit or not _commit_is_ancestor(str(protocol_commit)):
        raise RuntimeError("Targeted protocol commit is missing or is not an ancestor of HEAD")
    mismatches: list[str] = []
    for item in payload["artifact_hashes"]:
        if artifact_hash_match(item["path"], item["sha256"], root=PROJECT_ROOT) is None:
            mismatches.append(str(item["path"]))
    sample = orjson.loads(TARGETED_SAMPLE.read_bytes())
    if sample["issue_count"] != 150:
        mismatches.append("targeted sample count")
    if sample["ordered_issue_id_sha256"] != payload["sample"]["ordered_issue_id_sha256"]:
        mismatches.append("targeted ordered sample hash")
    current_plan = targeted_task_plan(config_path)
    if current_plan != payload["task_plan"]:
        mismatches.append("targeted task plan")
    if mismatches:
        raise RuntimeError("Targeted freeze mismatch: " + ", ".join(mismatches))
    return {
        "ok": True,
        "protocol_commit": protocol_commit,
        "artifact_count": len(payload["artifact_hashes"]),
        "task_count": current_plan["task_count"],
        "task_order_sha256": current_plan["task_order_sha256"],
    }


def targeted_provider_preflight(
    config_path: Path = TARGETED_PROTOCOL_YAML,
) -> dict[str, Any]:
    freeze = verify_targeted_extension_freeze(config_path)
    if TARGETED_PREFLIGHT.exists():
        existing = orjson.loads(TARGETED_PREFLIGHT.read_bytes())
        if existing.get("status") == "passed":
            return existing
        raise RuntimeError("A targeted provider preflight exists but did not pass")
    config = load_yaml(config_path)
    budget = CompletionCallBudget.from_config(PROJECT_ROOT, config["completion_call_budget"])
    budget.initialize()
    if int(budget.snapshot()["used"]) != 0:
        raise RuntimeError("Targeted call budget is not empty before first provider preflight")
    provider = OpenCodeGoProvider.from_models_config()
    result = provider.health_check(
        MODELS,
        call_budget=budget,
        run_id="targeted-t3-repeat-provider-health",
    )
    rules = config["response_model_compatibility"]
    checks = []
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
    budget_snapshot = budget.snapshot()
    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": "passed" if passed else "failed",
        "completed_at_utc": utc_now_iso(),
        "freeze": freeze,
        "checks": checks,
        "provider_health_artifact": str(Path(result["path"]).relative_to(PROJECT_ROOT)),
        "completion_call_budget": budget_snapshot,
    }
    write_json(TARGETED_PREFLIGHT, payload)
    if not passed or int(budget_snapshot["used"]) != 3:
        raise RuntimeError("Targeted provider preflight did not pass all three frozen routes")
    return payload


def assert_targeted_preflight_ready() -> dict[str, Any]:
    if not TARGETED_PREFLIGHT.exists():
        raise RuntimeError("Run the targeted provider preflight before inference")
    payload = orjson.loads(TARGETED_PREFLIGHT.read_bytes())
    if payload.get("status") != "passed":
        raise RuntimeError("Targeted provider preflight is not passed")
    if int(payload.get("completion_call_budget", {}).get("used", -1)) != 3:
        raise RuntimeError("Targeted provider preflight call count is not exactly three")
    return payload


def _load_targeted_predictions() -> pd.DataFrame:
    records = _raw_records("targeted-t3-repeat-*.jsonl")
    if not records:
        raise FileNotFoundError("Targeted extension JSONL is missing")
    frame = ensure_run_type(pd.DataFrame.from_records(records))
    frame = frame[frame["run_type"] == TARGETED_RUN_TYPE].copy()
    if len(frame) != EXPECTED_TASKS or frame["technical_error"].notna().any():
        raise RuntimeError("Targeted extension is incomplete or has unresolved technical errors")
    task_columns = [
        "issue_id",
        "model_id",
        "taxonomy_condition",
        "instruction_variant",
        "repeat_id",
    ]
    if frame.duplicated(task_columns).any():
        raise RuntimeError("Targeted canonical task keys are not unique")
    expected = targeted_task_plan()
    if len(frame) != expected["task_count"]:
        raise RuntimeError("Targeted canonical rows do not match the frozen task plan")
    gold = load_processed("test", include_label=True)[["issue_id", "label"]]
    merged = frame.merge(gold, on="issue_id", how="left", validate="many_to_one")
    if merged["label"].isna().any():
        raise RuntimeError("Targeted prediction-to-gold join is incomplete")
    return merged


def _macro_f1(gold: pd.Series, predicted: pd.Series) -> float:
    return float(classification_metrics(gold.tolist(), predicted.tolist())["macro_f1"])


def _paired_metric_cells(frame: pd.DataFrame, mode: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    grouping = ["repository", "model_id", "repeat_id"]
    for keys, group in frame.groupby(grouping, sort=True):
        by_condition = {
            condition: part.copy()
            for condition, part in group.groupby("taxonomy_condition")
        }
        if set(by_condition) != set(CONDITIONS):
            raise RuntimeError("A targeted metric cell is missing T0 or T3")
        if mode == "both_valid":
            left = by_condition["T0"][["issue_id", "label", "strict_label", "strict_parse_success"]]
            right = by_condition["T3"][["issue_id", "strict_label", "strict_parse_success"]]
            paired = left.merge(
                right,
                on="issue_id",
                suffixes=("_t0", "_t3"),
                validate="one_to_one",
            )
            paired = paired[paired["strict_parse_success_t0"] & paired["strict_parse_success_t3"]]
            t0 = _macro_f1(paired["label"], paired["strict_label_t0"])
            t3 = _macro_f1(paired["label"], paired["strict_label_t3"])
            n = len(paired)
        else:
            prediction_column = "strict_label" if mode == "exact" else "lenient_label"
            t0_group = by_condition["T0"]
            t3_group = by_condition["T3"]
            t0 = _macro_f1(t0_group["label"], t0_group[prediction_column])
            t3 = _macro_f1(t3_group["label"], t3_group[prediction_column])
            n = len(t0_group)
        rows.append(
            {
                "repository": keys[0],
                "model_id": keys[1],
                "repeat_id": int(keys[2]),
                "mode": mode,
                "n_issues": int(n),
                "t0_macro_f1": t0,
                "t3_macro_f1": t3,
                "delta_t3_minus_t0": t3 - t0,
            }
        )
    return pd.DataFrame(rows)


def _direction_tables(exact_cells: pd.DataFrame) -> dict[str, pd.DataFrame]:
    repeat = (
        exact_cells.groupby("repeat_id", sort=True)["delta_t3_minus_t0"]
        .mean()
        .rename("delta_t3_minus_t0")
        .reset_index()
    )
    system = (
        exact_cells.groupby("model_id", sort=True)["delta_t3_minus_t0"]
        .mean()
        .rename("delta_t3_minus_t0")
        .reset_index()
    )
    repository = (
        exact_cells.groupby("repository", sort=True)["delta_t3_minus_t0"]
        .mean()
        .rename("delta_t3_minus_t0")
        .reset_index()
    )
    system_repeat = (
        exact_cells.groupby(["model_id", "repeat_id"], sort=True)["delta_t3_minus_t0"]
        .mean()
        .rename("delta_t3_minus_t0")
        .reset_index()
    )
    return {
        "repeat": repeat,
        "system": system,
        "repository": repository,
        "system_repeat": system_repeat,
    }


def _agreement_table(frame: pd.DataFrame) -> pd.DataFrame:
    state_order = list(LABELS) + [INVALID_LABEL]
    state_codes = {state: index for index, state in enumerate(state_order)}
    working = frame.copy()
    working["contract_state"] = working["strict_label"].where(
        working["strict_parse_success"], INVALID_LABEL
    )
    rows: list[dict[str, Any]] = []
    for condition in CONDITIONS:
        condition_frame = working[working["taxonomy_condition"] == condition]
        scopes: list[tuple[str, pd.DataFrame]] = [("all_systems", condition_frame)]
        scopes.extend(
            (str(model_id), group)
            for model_id, group in condition_frame.groupby("model_id", sort=True)
        )
        for scope, group in scopes:
            pivot = group.pivot(
                index=["issue_id", "model_id"],
                columns="repeat_id",
                values="contract_state",
            )[REPEATS]
            if pivot.isna().any().any():
                raise RuntimeError("Targeted agreement matrix is incomplete")
            pair_flip_rates = [
                float((pivot[left] != pivot[right]).mean())
                for left, right in combinations(REPEATS, 2)
            ]
            codes = pivot.replace(state_codes).to_numpy(dtype=float).T
            alpha = float(
                krippendorff.alpha(reliability_data=codes, level_of_measurement="nominal")
            )
            rows.append(
                {
                    "taxonomy_condition": condition,
                    "scope": scope,
                    "unit_count": int(len(pivot)),
                    "mean_pairwise_repeat_flip_rate": float(np.mean(pair_flip_rates)),
                    "prediction_stability": 1.0 - float(np.mean(pair_flip_rates)),
                    "unanimous_repeat_rate": float(pivot.nunique(axis=1).eq(1).mean()),
                    "krippendorff_alpha_nominal_four_state": alpha,
                }
            )
    return pd.DataFrame(rows)


def _macro_f1_draws(gold: np.ndarray, predicted: np.ndarray) -> np.ndarray:
    scores = []
    for label in LABELS:
        true_label = gold == label
        pred_label = predicted == label
        tp = np.sum(true_label & pred_label, axis=1)
        fp = np.sum(~true_label & pred_label, axis=1)
        fn = np.sum(true_label & ~pred_label, axis=1)
        denominator = 2 * tp + fp + fn
        scores.append(
            np.divide(
                2 * tp,
                denominator,
                out=np.zeros_like(tp, dtype=float),
                where=denominator != 0,
            )
        )
    return np.mean(np.vstack(scores), axis=0)


def _targeted_bootstrap(frame: pd.DataFrame, *, draws: int, seed: int) -> dict[str, Any]:
    working = frame.copy()
    working["contract_state"] = working["strict_label"].where(
        working["strict_parse_success"], INVALID_LABEL
    )
    pivot = working.pivot(
        index=["repository", "issue_id", "label"],
        columns=["model_id", "repeat_id", "taxonomy_condition"],
        values="contract_state",
    )
    expected_columns = pd.MultiIndex.from_product([MODELS, REPEATS, CONDITIONS])
    pivot = pivot.reindex(columns=expected_columns)
    if pivot.isna().any().any():
        raise RuntimeError("Targeted bootstrap matrix is incomplete")
    rng = np.random.default_rng(seed)
    total = np.zeros(draws, dtype=float)
    cell_count = 0
    for repository in sorted(pivot.index.get_level_values("repository").unique()):
        repo = pivot.xs(repository, level="repository")
        gold = repo.index.get_level_values("label").to_numpy(dtype=object)
        indices = rng.integers(0, len(repo), size=(draws, len(repo)))
        sampled_gold = gold[indices]
        for model_id in MODELS:
            for repeat_id in REPEATS:
                t0 = repo[(model_id, repeat_id, "T0")].to_numpy(dtype=object)[indices]
                t3 = repo[(model_id, repeat_id, "T3")].to_numpy(dtype=object)[indices]
                total += _macro_f1_draws(sampled_gold, t3) - _macro_f1_draws(
                    sampled_gold, t0
                )
                cell_count += 1
    bootstrap_draws = total / cell_count
    exact_cells = _paired_metric_cells(frame, "exact")
    observed = float(exact_cells["delta_t3_minus_t0"].mean())
    low, high = np.quantile(bootstrap_draws, [0.025, 0.975])
    return {
        "contrast": "T3-T0",
        "observed_delta": observed,
        "ci_level": 0.95,
        "ci_low": float(low),
        "ci_high": float(high),
        "draws": int(draws),
        "seed": int(seed),
        "resampling_unit": "issue_id within fixed repository",
        "joint_fields": "condition x system x repeat",
        "repository_system_weighting": "equal",
        "repeat_aggregation": "arithmetic mean after repeat-specific contrasts",
        "multiplicity_adjustment": "none; one frozen contrast",
    }


def _main_comparison(frame: pd.DataFrame, repeat: pd.DataFrame) -> pd.DataFrame:
    main_records = _raw_records("main-*.jsonl")
    main = ensure_run_type(pd.DataFrame.from_records(main_records))
    main = main[(main["run_type"] == "main") & (main["dataset_split"] == "test")].copy()
    gold = load_processed("test", include_label=True)[["issue_id", "label"]]
    main = main.merge(gold, on="issue_id", validate="many_to_one")
    sample_ids = set(frame["issue_id"])

    def main_delta(source: pd.DataFrame) -> float:
        rows = []
        for (_repository, _model), group in source.groupby(["repository", "model_id"]):
            values = {}
            for condition in CONDITIONS:
                part = group[group["taxonomy_condition"] == condition]
                values[condition] = _macro_f1(part["label"], part["strict_label"])
            rows.append(values["T3"] - values["T0"])
        return float(np.mean(rows))

    rows = [
        {
            "evidence": "full_main_1500",
            "issue_count": 1500,
            "repeat_id": None,
            "delta_t3_minus_t0": main_delta(main),
            "interpretation": "full fixed main benchmark",
        },
        {
            "evidence": "main_p1_same_150_issue_sample",
            "issue_count": 150,
            "repeat_id": None,
            "delta_t3_minus_t0": main_delta(main[main["issue_id"].isin(sample_ids)]),
            "interpretation": "sampling plus original execution on the fixed robustness sample",
        },
    ]
    for row in repeat.to_dict(orient="records"):
        rows.append(
            {
                "evidence": "targeted_new_repeat",
                "issue_count": 150,
                "repeat_id": int(row["repeat_id"]),
                "delta_t3_minus_t0": float(row["delta_t3_minus_t0"]),
                "interpretation": "new repeated execution on the same fixed sample",
            }
        )
    rows.append(
        {
            "evidence": "targeted_repeat_average",
            "issue_count": 150,
            "repeat_id": None,
            "delta_t3_minus_t0": float(repeat["delta_t3_minus_t0"].mean()),
            "interpretation": "arithmetic mean of the three frozen new repeats",
        }
    )
    return pd.DataFrame(rows)


def _provider_tables(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    response_column = "response_model" if "response_model" in frame else "model_revision"
    response = (
        frame.groupby(["model_id", "taxonomy_condition", response_column], dropna=False)
        .size()
        .rename("count")
        .reset_index()
        .rename(columns={response_column: "response_model"})
    )
    finish = (
        frame.groupby(["model_id", "taxonomy_condition", "finish_reason"], dropna=False)
        .size()
        .rename("count")
        .reset_index()
    )
    provenance = (
        frame.groupby(
            ["provider_provenance_segment", "model_id", "taxonomy_condition"],
            dropna=False,
        )
        .agg(
            canonical_tasks=("issue_id", "size"),
            first_success_utc=("start_timestamp", "min"),
            last_success_utc=("end_timestamp", "max"),
            invalid_outputs=("strict_parse_success", lambda values: int((~values).sum())),
            empty_outputs=("raw_output", lambda values: int(values.fillna("").eq("").sum())),
        )
        .reset_index()
    )
    parameters = (
        frame.groupby(
            [
                "model_id",
                "taxonomy_condition",
                "api_max_tokens",
                "temperature_sent",
                "top_p_sent",
                "seed_sent",
            ],
            dropna=False,
        )
        .size()
        .rename("count")
        .reset_index()
    )
    return {
        "response_model": response,
        "finish_reason": finish,
        "provenance": provenance,
        "parameters": parameters,
    }


def analyze_targeted_extension() -> dict[str, Any]:
    frame = _load_targeted_predictions()
    config = load_yaml(TARGETED_PROTOCOL_YAML)
    exact_cells = _paired_metric_cells(frame, "exact")
    lenient_cells = _paired_metric_cells(frame, "lenient")
    both_valid_cells = _paired_metric_cells(frame, "both_valid")
    directions = _direction_tables(exact_cells)
    agreement = _agreement_table(frame)
    bootstrap = _targeted_bootstrap(
        frame,
        draws=int(config["analysis"]["bootstrap_draws"]),
        seed=int(config["analysis"]["bootstrap_seed"]),
    )
    comparison = _main_comparison(frame, directions["repeat"])
    invalid = (
        frame.groupby(["taxonomy_condition", "model_id", "repeat_id"], sort=True)
        .agg(
            n=("issue_id", "size"),
            invalid_outputs=("strict_parse_success", lambda values: int((~values).sum())),
            empty_outputs=("raw_output", lambda values: int(values.fillna("").eq("").sum())),
        )
        .reset_index()
    )
    invalid["invalid_rate"] = invalid["invalid_outputs"] / invalid["n"]
    provider = _provider_tables(frame)

    TARGETED_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    TARGETED_STATS_DIR.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, pd.DataFrame] = {
        "targeted_t3_repeat_exact_cells.csv": exact_cells,
        "targeted_t3_repeat_lenient_cells.csv": lenient_cells,
        "targeted_t3_repeat_both_valid_cells.csv": both_valid_cells,
        "targeted_t3_repeat_repeat_deltas.csv": directions["repeat"],
        "targeted_t3_repeat_system_deltas.csv": directions["system"],
        "targeted_t3_repeat_repository_deltas.csv": directions["repository"],
        "targeted_t3_repeat_system_repeat_deltas.csv": directions["system_repeat"],
        "targeted_t3_repeat_invalid_rates.csv": invalid,
        "targeted_t3_repeat_agreement.csv": agreement,
        "targeted_t3_repeat_comparison.csv": comparison,
        "targeted_t3_repeat_response_models.csv": provider["response_model"],
        "targeted_t3_repeat_finish_reasons.csv": provider["finish_reason"],
        "targeted_t3_repeat_provenance.csv": provider["provenance"],
        "targeted_t3_repeat_effective_parameters.csv": provider["parameters"],
    }
    for filename, table in outputs.items():
        table.to_csv(TARGETED_RESULTS_DIR / filename, index=False, lineterminator="\n")
    pd.DataFrame([bootstrap]).to_csv(
        TARGETED_RESULTS_DIR / "targeted_t3_repeat_bootstrap.csv",
        index=False,
        lineterminator="\n",
    )

    parsing_summary = []
    for mode, cells in (
        ("exact", exact_cells),
        ("lenient", lenient_cells),
        ("both_valid", both_valid_cells),
    ):
        parsing_summary.append(
            {
                "mode": mode,
                "repeat_averaged_delta_t3_minus_t0": float(
                    cells["delta_t3_minus_t0"].mean()
                ),
                "minimum_cell_n": int(cells["n_issues"].min()),
            }
        )
    parsing_frame = pd.DataFrame(parsing_summary)
    parsing_frame.to_csv(
        TARGETED_RESULTS_DIR / "targeted_t3_repeat_parsing_summary.csv",
        index=False,
        lineterminator="\n",
    )

    result = {
        "schema_version": 1,
        "generated_at_utc": utc_now_iso(),
        "scientific_status": (
            "post-result, budget-constrained, targeted robustness extension"
        ),
        "canonical_tasks": int(len(frame)),
        "unique_issues": int(frame["issue_id"].nunique()),
        "repeat_averaged_exact_delta_t3_minus_t0": float(
            exact_cells["delta_t3_minus_t0"].mean()
        ),
        "negative_system_repeat_cells": int(
            (directions["system_repeat"]["delta_t3_minus_t0"] < 0).sum()
        ),
        "system_repeat_cells": int(len(directions["system_repeat"])),
        "bootstrap": bootstrap,
        "parsing_summary": parsing_summary,
        "output_files": sorted(outputs) + [
            "targeted_t3_repeat_bootstrap.csv",
            "targeted_t3_repeat_parsing_summary.csv",
        ],
    }
    write_json(TARGETED_STATS_DIR / "targeted_t3_repeat_results.json", result)
    return result
