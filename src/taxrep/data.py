from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pandas as pd

from taxrep.constants import DATASET_COMMIT, DATASET_FILES, DATASET_REPO, LABELS, PROJECT_ROOT
from taxrep.utils import sha256_file, sha256_text, utc_now_iso, write_json


def raw_url(relative_path: str) -> str:
    return (
        "https://raw.githubusercontent.com/nlbse2024/issue-report-classification/"
        f"{DATASET_COMMIT}/{relative_path}"
    )


def download_dataset(force: bool = False) -> dict[str, Any]:
    raw_dir = PROJECT_ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    frozen_manifest_path = (
        PROJECT_ROOT / "data" / "manifests" / "dataset_download_manifest.json"
    )
    frozen_files: dict[str, Any] = {}
    if frozen_manifest_path.exists():
        frozen_manifest = json.loads(frozen_manifest_path.read_text(encoding="utf-8"))
        if frozen_manifest.get("source_commit") == DATASET_COMMIT:
            frozen_files = dict(frozen_manifest.get("files", {}))
    manifest: dict[str, Any] = {
        "downloaded_at_utc": utc_now_iso(),
        "source_repository": DATASET_REPO,
        "source_commit": DATASET_COMMIT,
        "files": {},
    }
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        for split, relative_path in DATASET_FILES.items():
            target = raw_dir / Path(relative_path).name
            if target.exists() and not force:
                status = "existing"
            else:
                response = client.get(raw_url(relative_path))
                response.raise_for_status()
                target.write_bytes(response.content)
                status = "downloaded"
            digest = sha256_file(target)
            expected = frozen_files.get(split, {})
            expected_digest = expected.get("sha256")
            expected_bytes = expected.get("bytes")
            if expected_digest and digest != expected_digest:
                raise ValueError(
                    f"{split}: downloaded dataset SHA-256 does not match the frozen manifest"
                )
            if expected_bytes is not None and target.stat().st_size != int(expected_bytes):
                raise ValueError(
                    f"{split}: downloaded dataset byte size does not match the frozen manifest"
                )
            manifest["files"][split] = {
                "relative_path": str(target.relative_to(PROJECT_ROOT)),
                "source_path": relative_path,
                "source_url": raw_url(relative_path),
                "status": status,
                "sha256": digest,
                "bytes": target.stat().st_size,
            }
    write_json(PROJECT_ROOT / "data" / "manifests" / "dataset_download_manifest.json", manifest)
    return manifest


def read_raw_split(split: str) -> pd.DataFrame:
    if split not in DATASET_FILES:
        raise KeyError(f"Unknown split: {split}")
    path = PROJECT_ROOT / "data" / "raw" / Path(DATASET_FILES[split]).name
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}; run `taxrep data download` first")
    return pd.read_csv(path)


def normalize_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def add_issue_ids(df: pd.DataFrame, split: str) -> pd.DataFrame:
    out = df.copy()
    ids: list[str] = []
    for index, row in out.iterrows():
        basis = "\n".join(
            [
                split,
                str(index),
                str(row.get("repo", "")),
                str(row.get("created_at", "")),
                str(row.get("title", "")),
                str(row.get("body", "")),
            ]
        )
        ids.append(f"{split}-{index:04d}-{sha256_text(basis)[:10]}")
    out.insert(0, "issue_id", ids)
    out = out.rename(columns={"repo": "repository"})
    return out


def _control_char_count(series: pd.Series) -> int:
    pattern = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
    return int(series.fillna("").astype(str).map(lambda value: len(pattern.findall(value))).sum())


def _prompt_injection_count(series: pd.Series) -> int:
    pattern = re.compile(
        r"(ignore (all )?(previous|above) instructions|system prompt|you are chatgpt|"
        r"return exactly|output_schema|developer message)",
        flags=re.IGNORECASE,
    )
    return int(series.fillna("").astype(str).map(lambda value: bool(pattern.search(value))).sum())


def validate_dataset() -> dict[str, Any]:
    raw = {split: read_raw_split(split) for split in ("train", "test")}
    processed = {split: add_issue_ids(frame, split) for split, frame in raw.items()}
    report: dict[str, Any] = {
        "validated_at_utc": utc_now_iso(),
        "expected_columns": ["repo", "created_at", "label", "title", "body"],
        "splits": {},
        "cross_split": {},
        "errors": [],
        "warnings": [],
    }

    for split, frame in raw.items():
        missing_columns = sorted(set(report["expected_columns"]) - set(frame.columns))
        extra_columns = sorted(set(frame.columns) - set(report["expected_columns"]))
        if missing_columns:
            report["errors"].append(f"{split}: missing columns {missing_columns}")
        unknown_labels = sorted(set(frame.get("label", [])) - set(LABELS))
        if unknown_labels:
            report["errors"].append(f"{split}: unknown labels {unknown_labels}")

        text = frame["title"].fillna("").astype(str) + "\n" + frame["body"].fillna("").astype(str)
        normalized_text = text.map(normalize_text)
        text_lengths = text.str.len()
        duplicate_count = int(normalized_text.duplicated().sum())
        conflicting = (
            pd.DataFrame({"text": normalized_text, "label": frame["label"]})
            .drop_duplicates()
            .groupby("text")["label"]
            .nunique()
        )
        conflicting_count = int((conflicting > 1).sum())
        body_missing = int(
            (
                frame["body"].isna()
                | frame["body"].fillna("").astype(str).str.len().eq(0)
            ).sum()
        )
        split_record = {
            "rows": int(len(frame)),
            "columns": list(frame.columns),
            "missing_columns": missing_columns,
            "extra_columns": extra_columns,
            "repositories": frame["repo"].value_counts().sort_index().to_dict(),
            "labels": frame["label"].value_counts().sort_index().to_dict(),
            "project_label_distribution": (
                frame.groupby(["repo", "label"], observed=True)
                .size()
                .unstack(fill_value=0)
                .to_dict()
            ),
            "missing_title_count": int(frame["title"].isna().sum()),
            "missing_or_empty_body_count": body_missing,
            "exact_normalized_duplicate_count": duplicate_count,
            "conflicting_label_same_text_count": conflicting_count,
            "text_length_chars": {
                "min": int(text_lengths.min()),
                "median": float(text_lengths.median()),
                "p95": float(text_lengths.quantile(0.95)),
                "max": int(text_lengths.max()),
            },
            "context_window_risk_over_100k_chars": int((text_lengths > 100_000).sum()),
            "control_char_count": _control_char_count(text),
            "html_like_record_count": int(
                text.str.contains(r"<[^>]+>", regex=True, na=False).sum()
            ),
            "prompt_injection_like_record_count": _prompt_injection_count(text),
        }
        report["splits"][split] = split_record

    train_norm = (
        raw["train"]["title"].fillna("").astype(str)
        + "\n"
        + raw["train"]["body"].fillna("").astype(str)
    ).map(normalize_text)
    test_norm = (
        raw["test"]["title"].fillna("").astype(str)
        + "\n"
        + raw["test"]["body"].fillna("").astype(str)
    ).map(normalize_text)
    train_set = set(train_norm)
    test_set = set(test_norm)
    overlap = train_set & test_set
    report["cross_split"] = {
        "normalized_exact_duplicate_texts": len(overlap),
        "train_rows_in_overlap": int(train_norm.isin(overlap).sum()),
        "test_rows_in_overlap": int(test_norm.isin(overlap).sum()),
    }

    processed_dir = PROJECT_ROOT / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    for split, frame in processed.items():
        keep = ["issue_id", "repository", "created_at", "label", "title", "body"]
        gold = frame[keep].copy()
        gold_path = processed_dir / f"{split}_gold.parquet"
        inference_path = processed_dir / f"{split}_inference.parquet"
        gold.to_parquet(gold_path, index=False)
        inference = gold.drop(columns=["label"])
        inference.to_parquet(inference_path, index=False)
        label_manifest = {
            "split": split,
            "gold_file": f"data/processed/{split}_gold.parquet",
            "inference_file": f"data/processed/{split}_inference.parquet",
            "gold_sha256": sha256_file(gold_path),
            "inference_sha256": sha256_file(inference_path),
            "label_removed_from_inference": "label" not in inference.columns,
        }
        manifest_path = PROJECT_ROOT / "data" / "manifests" / f"{split}_processed_manifest.json"
        write_json(manifest_path, label_manifest)

    write_json(PROJECT_ROOT / "data" / "manifests" / "data_audit.json", report)
    write_audit_markdown(report)
    return report


def write_audit_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Data Audit",
        "",
        f"- Validated at UTC: `{report['validated_at_utc']}`",
        f"- Source commit: `{DATASET_COMMIT}`",
        f"- Errors: `{len(report['errors'])}`",
        f"- Warnings: `{len(report['warnings'])}`",
        "",
    ]
    for error in report["errors"]:
        lines.append(f"- ERROR: {error}")
    for split, record in report["splits"].items():
        lines.extend(
            [
                "",
                f"## {split.title()} Split",
                "",
                f"- Rows: `{record['rows']}`",
                f"- Columns: `{', '.join(record['columns'])}`",
                f"- Repositories: `{record['repositories']}`",
                f"- Labels: `{record['labels']}`",
                f"- Missing titles: `{record['missing_title_count']}`",
                f"- Missing or empty bodies: `{record['missing_or_empty_body_count']}`",
                (
                    "- Exact normalized duplicate count: "
                    f"`{record['exact_normalized_duplicate_count']}`"
                ),
                (
                    "- Conflicting label same-text count: "
                    f"`{record['conflicting_label_same_text_count']}`"
                ),
                f"- Text length chars: `{record['text_length_chars']}`",
                (
                    "- Prompt-injection-like records: "
                    f"`{record['prompt_injection_like_record_count']}`"
                ),
            ]
        )
    lines.extend(
        [
            "",
            "## Cross Split",
            "",
            (
                "- Normalized exact duplicate texts: "
                f"`{report['cross_split']['normalized_exact_duplicate_texts']}`"
            ),
            f"- Train rows in overlap: `{report['cross_split']['train_rows_in_overlap']}`",
            f"- Test rows in overlap: `{report['cross_split']['test_rows_in_overlap']}`",
        ]
    )
    (PROJECT_ROOT / "results" / "data_audit.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def load_processed(split: str, include_label: bool = False) -> pd.DataFrame:
    suffix = "gold" if include_label else "inference"
    path = PROJECT_ROOT / "data" / "processed" / f"{split}_{suffix}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}; run `taxrep data validate` first")
    return pd.read_parquet(path)


def select_stratified_sample(
    frame: pd.DataFrame,
    *,
    per_project_label: int,
    seed: int,
    exclude_issue_ids: set[str] | None = None,
) -> pd.DataFrame:
    if "label" not in frame.columns:
        raise ValueError("Stratified sample selection requires labels")
    if exclude_issue_ids:
        frame = frame[~frame["issue_id"].isin(exclude_issue_ids)].copy()
    rng = np.random.default_rng(seed)
    selected_indices: list[int] = []
    for (_repository, _label), group in frame.groupby(["repository", "label"], sort=True):
        if len(group) < per_project_label:
            raise ValueError(
                f"Not enough rows for {_repository}/{_label}: {len(group)} < {per_project_label}"
            )
        selected_indices.extend(
            rng.choice(group.index.to_numpy(), size=per_project_label, replace=False)
        )
    return frame.loc[sorted(selected_indices)].reset_index(drop=True)
