from __future__ import annotations

from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import friedmanchisquare, rankdata, wilcoxon
from statsmodels.stats.multitest import multipletests

from taxrep.constants import PROJECT_ROOT
from taxrep.data import load_processed
from taxrep.metrics import classification_metrics
from taxrep.runs import ensure_run_type
from taxrep.utils import write_json

CONDITIONS = ["T0", "T1", "T2", "T3", "T4"]


def _validate_resampling_matrix(
    observed: np.ndarray,
    draws: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    observed_array = np.asarray(observed, dtype=float)
    draw_array = np.asarray(draws, dtype=float)
    if observed_array.ndim != 1:
        raise ValueError("observed must be a one-dimensional array")
    if draw_array.ndim != 2:
        raise ValueError("draws must be a two-dimensional array")
    if draw_array.shape[0] == 0:
        raise ValueError("draws must contain at least one resampling draw")
    if draw_array.shape[1] != observed_array.shape[0]:
        raise ValueError("draw columns must match the observed contrasts")
    if not np.isfinite(observed_array).all() or not np.isfinite(draw_array).all():
        raise ValueError("observed and draws must contain only finite values")
    return observed_array, draw_array


def permutation_p_values(
    observed: np.ndarray,
    null_draws: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return marginal and max-statistic-adjusted two-sided permutation p-values."""

    observed_array, draw_array = _validate_resampling_matrix(observed, null_draws)
    absolute_observed = np.abs(observed_array)
    absolute_draws = np.abs(draw_array)
    denominator = draw_array.shape[0] + 1
    marginal = (1 + np.sum(absolute_draws >= absolute_observed, axis=0)) / denominator
    max_statistics = np.max(absolute_draws, axis=1)
    adjusted = (
        1
        + np.sum(
            max_statistics[:, np.newaxis] >= absolute_observed[np.newaxis, :],
            axis=0,
        )
    ) / denominator
    return marginal.astype(float), adjusted.astype(float)


def simultaneous_max_deviation_intervals(
    observed: np.ndarray,
    bootstrap_draws: np.ndarray,
    *,
    coverage: float,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Construct unstudentized simultaneous intervals from centered max deviations."""

    if not 0.0 < coverage < 1.0:
        raise ValueError("coverage must be strictly between zero and one")
    observed_array, draw_array = _validate_resampling_matrix(observed, bootstrap_draws)
    max_deviations = np.max(np.abs(draw_array - observed_array), axis=1)
    critical_value = float(np.quantile(max_deviations, coverage))
    return (
        observed_array - critical_value,
        observed_array + critical_value,
        critical_value,
    )


def _matched_pairs_rank_biserial(values: np.ndarray) -> float:
    nonzero = np.asarray(values, dtype=float)
    nonzero = nonzero[~np.isclose(nonzero, 0.0)]
    if nonzero.size == 0:
        return float("nan")
    ranks = rankdata(np.abs(nonzero), method="average")
    positive = float(ranks[nonzero > 0].sum())
    negative = float(ranks[nonzero < 0].sum())
    return (positive - negative) / (positive + negative)


def _load_main_predictions() -> pd.DataFrame:
    frames = [
        pd.read_parquet(path)
        for path in sorted((PROJECT_ROOT / "results" / "raw_predictions").glob("*.parquet"))
    ]
    if not frames:
        raise FileNotFoundError("No prediction parquet files found")
    predictions = ensure_run_type(pd.concat(frames, ignore_index=True))
    return predictions[
        (predictions["dataset_split"] == "test") & (predictions["run_type"] == "main")
    ]


def block_metrics() -> pd.DataFrame:
    predictions = _load_main_predictions()
    gold = load_processed("test", include_label=True)[["issue_id", "label"]]
    merged = predictions.merge(gold, on="issue_id", how="inner", validate="many_to_one")
    rows: list[dict[str, Any]] = []
    for (model_id, repository, condition), group in merged.groupby(
        ["model_id", "repository", "taxonomy_condition"], sort=True
    ):
        metrics = classification_metrics(group["label"].tolist(), group["strict_label"].tolist())
        rows.append(
            {
                "model_id": model_id,
                "repository": repository,
                "taxonomy_condition": condition,
                "macro_f1": metrics["macro_f1"],
                "mcc": metrics["mcc"],
                "balanced_accuracy": metrics["balanced_accuracy"],
                "invalid_rate": metrics["invalid_rate"],
                "n": metrics["n"],
            }
        )
    frame = pd.DataFrame(rows)
    frame.to_csv(PROJECT_ROOT / "results" / "tables" / "block_metrics.csv", index=False)
    return frame


def run_statistics() -> dict[str, Any]:
    blocks = block_metrics()
    pivot = blocks.pivot_table(
        index=["model_id", "repository"],
        columns="taxonomy_condition",
        values="macro_f1",
        aggfunc="first",
    )[CONDITIONS]
    statistic, p_value = friedmanchisquare(
        *[pivot[condition].to_numpy() for condition in CONDITIONS]
    )
    comparisons: list[dict[str, Any]] = []
    p_values: list[float] = []
    for condition in ["T1", "T2", "T3", "T4"]:
        diffs = pivot[condition] - pivot["T0"]
        result = wilcoxon(diffs, zero_method="wilcox", alternative="two-sided", method="auto")
        comparisons.append(
            {
                "comparison": f"{condition}-T0",
                "mean_delta_macro_f1": float(diffs.mean()),
                "median_delta_macro_f1": float(diffs.median()),
                "wilcoxon_statistic": float(result.statistic),
                "p_value": float(result.pvalue),
                "matched_pairs_rank_biserial": _matched_pairs_rank_biserial(
                    diffs.to_numpy()
                ),
                "n_blocks": int(len(diffs)),
            }
        )
        p_values.append(float(result.pvalue))
    if p_values:
        _reject, adjusted, _sidak, _bonf = multipletests(p_values, method="holm")
        for row, adjusted_p in zip(comparisons, adjusted, strict=True):
            row["holm_adjusted_p"] = float(adjusted_p)
    exploratory_pairs: list[dict[str, Any]] = []
    for left, right in combinations(CONDITIONS, 2):
        diffs = pivot[left] - pivot[right]
        exploratory_pairs.append(
            {
                "comparison": f"{left}-{right}",
                "mean_delta_macro_f1": float(np.mean(diffs)),
                "median_delta_macro_f1": float(np.median(diffs)),
            }
        )
    payload = {
        "analysis_status": (
            "historical protocol output retained for audit; the crossed "
            "repository-by-system cells are not treated as independent "
            "inferential units"
        ),
        "legacy_filename_notice": (
            "The filename confirmatory_statistics.json predates the "
            "crossed-dependence audit and does not confer confirmatory status."
        ),
        "friedman": {
            "statistic": float(statistic),
            "p_value": float(p_value),
            "n_blocks": int(len(pivot)),
        },
        "historical_wilcoxon_holm": comparisons,
        "exploratory_pair_deltas": exploratory_pairs,
    }
    write_json(PROJECT_ROOT / "results" / "statistics" / "confirmatory_statistics.json", payload)
    return payload
