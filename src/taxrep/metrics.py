from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    matthews_corrcoef,
    precision_recall_fscore_support,
)

from taxrep.constants import LABELS

INVALID_LABEL = "__invalid__"


def normalize_predictions(predictions: list[str | None]) -> list[str]:
    return [prediction if prediction in LABELS else INVALID_LABEL for prediction in predictions]


def classification_metrics(gold: list[str], predicted: list[str | None]) -> dict[str, Any]:
    y_true = list(gold)
    y_pred = normalize_predictions(predicted)
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=list(LABELS),
        zero_division=0,
    )
    per_class = {
        label: {
            "precision": float(precision[index]),
            "recall": float(recall[index]),
            "f1": float(f1[index]),
            "support": int(support[index]),
        }
        for index, label in enumerate(LABELS)
    }
    return {
        "n": len(y_true),
        "macro_f1": float(
            f1_score(y_true, y_pred, labels=list(LABELS), average="macro", zero_division=0)
        ),
        "mcc": float(matthews_corrcoef(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "invalid_rate": float(np.mean([prediction == INVALID_LABEL for prediction in y_pred])),
        "per_class": per_class,
    }
