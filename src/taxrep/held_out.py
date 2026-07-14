from __future__ import annotations

from typing import Any

import pandas as pd

from taxrep.constants import LABELS, PROJECT_ROOT
from taxrep.data import load_processed
from taxrep.metrics import classification_metrics
from taxrep.runs import ensure_run_type
from taxrep.utils import write_json

CONDITION_ORDER = ["T0", "T1", "T2", "T3", "T4"]


def _load_predictions() -> pd.DataFrame:
    frames = [
        pd.read_parquet(path)
        for path in sorted((PROJECT_ROOT / "results" / "raw_predictions").glob("*.parquet"))
    ]
    if not frames:
        raise FileNotFoundError("No raw prediction parquet files found")
    return ensure_run_type(pd.concat(frames, ignore_index=True))


def _macro_f1_for(frame: pd.DataFrame) -> float:
    return classification_metrics(frame["label"].tolist(), frame["strict_label"].tolist())[
        "macro_f1"
    ]


def _selection_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for condition in CONDITION_ORDER:
        condition_frame = frame[frame["taxonomy_condition"] == condition]
        project_scores = [
            _macro_f1_for(project_frame)
            for _repository, project_frame in condition_frame.groupby("repository", sort=True)
        ]
        project_invalid_rates = [
            float(1 - project_frame["strict_parse_success"].mean())
            for _repository, project_frame in condition_frame.groupby("repository", sort=True)
        ]
        rows.append(
            {
                "taxonomy_condition": condition,
                "source_repository_count": len(project_scores),
                "project_mean_macro_f1": float(pd.Series(project_scores).mean()),
                "project_mean_invalid_rate": float(pd.Series(project_invalid_rates).mean()),
                "mean_input_token_count": float(condition_frame["input_token_count"].mean()),
            }
        )
    return pd.DataFrame(rows)


def _select_condition(summary: pd.DataFrame) -> str:
    lookup = summary.set_index("taxonomy_condition")
    return sorted(
        CONDITION_ORDER,
        key=lambda condition: (
            -float(lookup.loc[condition, "project_mean_macro_f1"]),
            float(lookup.loc[condition, "project_mean_invalid_rate"]),
            float(lookup.loc[condition, "mean_input_token_count"]),
            CONDITION_ORDER.index(condition),
        ),
    )[0]


def compute_project_held_out() -> dict[str, Any]:
    predictions = _load_predictions()
    train_gold = load_processed("train", include_label=True)[["issue_id", "label", "repository"]]
    test_gold = load_processed("test", include_label=True)[["issue_id", "label", "repository"]]
    train_source = predictions[
        (predictions["run_type"] == "train-selection") & (predictions["dataset_split"] == "train")
    ]
    test_source = predictions[
        (predictions["run_type"] == "main") & (predictions["dataset_split"] == "test")
    ]
    train_preds = train_source.merge(
        train_gold,
        on=["issue_id", "repository"],
        how="inner",
        validate="many_to_one",
    )
    test_preds = test_source.merge(
        test_gold,
        on=["issue_id", "repository"],
        how="inner",
        validate="many_to_one",
    )
    if train_preds.empty or test_preds.empty:
        raise ValueError("Project-held-out requires both train-selection and main test predictions")
    rows: list[dict[str, Any]] = []
    for model_id in sorted(set(train_preds["model_id"]) & set(test_preds["model_id"])):
        model_train = train_preds[train_preds["model_id"] == model_id]
        model_test = test_preds[test_preds["model_id"] == model_id]
        global_summary = _selection_summary(model_train)
        global_selected = _select_condition(global_summary)
        for target_repository in sorted(model_test["repository"].unique()):
            source = model_train[model_train["repository"] != target_repository]
            source_summary = _selection_summary(source)
            selected = _select_condition(source_summary)
            source_lookup = source_summary.set_index("taxonomy_condition")
            target = model_test[model_test["repository"] == target_repository]
            target_scores = {
                condition: _macro_f1_for(target[target["taxonomy_condition"] == condition])
                for condition in CONDITION_ORDER
            }
            oracle_condition = max(CONDITION_ORDER, key=lambda condition: target_scores[condition])
            rows.append(
                {
                    "model_id": model_id,
                    "target_repository": target_repository,
                    "selected_condition": selected,
                    "source_project_mean_macro_f1": float(
                        source_lookup.loc[selected, "project_mean_macro_f1"]
                    ),
                    "source_project_mean_invalid_rate": float(
                        source_lookup.loc[selected, "project_mean_invalid_rate"]
                    ),
                    "source_mean_input_token_count": float(
                        source_lookup.loc[selected, "mean_input_token_count"]
                    ),
                    "selection_rule": (
                        "highest equal-weight source-repository Macro-F1 mean; then lower "
                        "project-mean invalid rate; then lower mean input tokens; then T0-T4"
                    ),
                    "t0_macro_f1": target_scores["T0"],
                    "selected_macro_f1": target_scores[selected],
                    "global_selected_condition": global_selected,
                    "global_selected_macro_f1": target_scores[global_selected],
                    "global_gain_vs_t0": target_scores[global_selected] - target_scores["T0"],
                    "oracle_condition": oracle_condition,
                    "oracle_macro_f1": target_scores[oracle_condition],
                    "gain_vs_t0": target_scores[selected] - target_scores["T0"],
                    "oracle_regret": target_scores[oracle_condition] - target_scores[selected],
                }
            )
    payload = {
        "rows": rows,
        "summary": {
            "folds": len(rows),
            "selected_beats_t0_rate": float(pd.DataFrame(rows)["gain_vs_t0"].gt(0).mean()),
            "selected_equals_oracle_rate": float(
                (
                    pd.DataFrame(rows)["selected_condition"]
                    == pd.DataFrame(rows)["oracle_condition"]
                ).mean()
            ),
        },
        "labels": list(LABELS),
    }
    write_json(PROJECT_ROOT / "results" / "metrics" / "project_held_out.json", payload)
    pd.DataFrame(rows).to_csv(
        PROJECT_ROOT / "results" / "tables" / "project_held_out.csv", index=False
    )
    return payload
