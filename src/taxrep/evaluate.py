from __future__ import annotations

from typing import Any

import pandas as pd

from taxrep.constants import PROJECT_ROOT
from taxrep.data import load_processed
from taxrep.metrics import classification_metrics
from taxrep.runs import ensure_run_type
from taxrep.utils import write_json


def _prediction_frame() -> pd.DataFrame:
    parsed = PROJECT_ROOT / "results" / "parsed_predictions" / "parsed_predictions.parquet"
    if parsed.exists():
        return ensure_run_type(pd.read_parquet(parsed))
    frames = [
        pd.read_parquet(path)
        for path in sorted((PROJECT_ROOT / "results" / "raw_predictions").glob("*.parquet"))
    ]
    if not frames:
        raise FileNotFoundError("No parsed or raw prediction parquet files found")
    return ensure_run_type(pd.concat(frames, ignore_index=True))


def evaluate_predictions() -> dict[str, Any]:
    predictions = _prediction_frame()
    targeted_mask = predictions["run_type"].eq("targeted-t3-repeat")
    excluded_targeted_rows = int(targeted_mask.sum())
    predictions = predictions.loc[~targeted_mask].copy()
    if predictions.empty:
        raise RuntimeError(
            "No generic-analysis prediction rows remain after excluding "
            f"{excluded_targeted_rows} targeted-t3-repeat rows; use the dedicated "
            "targeted result-freeze and analysis commands for a completed extension"
        )
    metrics_rows: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    for (run_type, split), split_predictions in predictions.groupby(
        ["run_type", "dataset_split"],
        sort=True,
    ):
        gold = load_processed(str(split), include_label=True)[["issue_id", "label"]]
        merged = split_predictions.merge(gold, on="issue_id", how="left", validate="many_to_one")
        if merged["label"].isna().any():
            raise ValueError(f"{split}: prediction-gold join produced missing labels")
        for keys, group in merged.groupby(["model_id", "taxonomy_condition"], sort=True):
            model_id, condition = keys
            strict = classification_metrics(group["label"].tolist(), group["strict_label"].tolist())
            lenient = classification_metrics(
                group["label"].tolist(), group["lenient_label"].tolist()
            )
            row = {
                "dataset_split": split,
                "run_type": run_type,
                "model_id": model_id,
                "taxonomy_condition": condition,
                "n": strict["n"],
                "strict_macro_f1": strict["macro_f1"],
                "strict_mcc": strict["mcc"],
                "strict_balanced_accuracy": strict["balanced_accuracy"],
                "strict_accuracy": strict["accuracy"],
                "strict_invalid_rate": strict["invalid_rate"],
                "lenient_macro_f1": lenient["macro_f1"],
                "lenient_invalid_rate": lenient["invalid_rate"],
            }
            metrics_rows.append(row)
            details[f"{run_type}/{split}/{model_id}/{condition}"] = {
                "strict": strict,
                "lenient": lenient,
            }
    metrics = {"rows": metrics_rows, "details": details}
    out_json = PROJECT_ROOT / "results" / "metrics" / "classification_metrics.json"
    out_csv = PROJECT_ROOT / "results" / "metrics" / "classification_metrics.csv"
    write_json(out_json, metrics)
    pd.DataFrame(metrics_rows).to_csv(out_csv, index=False)
    return {
        "json": str(out_json),
        "csv": str(out_csv),
        "rows": len(metrics_rows),
        "excluded_targeted_rows": excluded_targeted_rows,
    }


def evaluate_tfidf_svm_baseline() -> dict[str, Any]:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.pipeline import make_pipeline
    from sklearn.svm import LinearSVC

    train = load_processed("train", include_label=True)
    test = load_processed("test", include_label=True)
    train_text = (train["title"].fillna("") + "\n" + train["body"].fillna("")).tolist()
    test_text = (test["title"].fillna("") + "\n" + test["body"].fillna("")).tolist()
    pipeline = make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=100_000),
        LinearSVC(C=1.0, random_state=20260704),
    )
    pipeline.fit(train_text, train["label"].tolist())
    predicted = pipeline.predict(test_text).tolist()
    metrics = classification_metrics(test["label"].tolist(), predicted)
    payload = {
        "baseline": "TF-IDF + Linear SVM",
        "training_rows": int(len(train)),
        "test_rows": int(len(test)),
        "metrics": metrics,
    }
    path = PROJECT_ROOT / "results" / "metrics" / "baseline_tfidf_linear_svm.json"
    write_json(path, payload)
    return {"path": str(path), "macro_f1": metrics["macro_f1"]}
