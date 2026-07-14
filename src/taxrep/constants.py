from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LABELS = ("bug", "feature", "question")
PROTOCOL_VERSION = "1.2"
DATASET_REPO = "https://github.com/nlbse2024/issue-report-classification"
DATASET_COMMIT = "2927bc67eb42db8affd16eaf3e5a6d74f3063961"
DATASET_FILES = {
    "train": "data/issues_train.csv",
    "test": "data/issues_test.csv",
}
