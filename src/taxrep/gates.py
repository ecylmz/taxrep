from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from taxrep.constants import PROJECT_ROOT, PROTOCOL_VERSION
from taxrep.reports import summarize_run_type
from taxrep.utils import read_jsonl, sha256_file, utc_now_iso, write_csv, write_json

FREEZE_FILES = [
    "experiment/prompt_registry.yaml",
    "experiment/prompt_hashes.json",
    "experiment/taxonomy_equivalence_matrix.md",
    "experiment/model_registry.csv",
    "experiment/provider_catalog_snapshot_20260704.json",
    "experiment/provider_limits_snapshot_20260704.md",
    "experiment/provider_health_20260704.json",
    "configs/models.yaml",
    "configs/pilot.yaml",
    "configs/main.yaml",
    "configs/train_selection.yaml",
    "configs/robustness.yaml",
    "configs/technical_pretest.yaml",
    "pyproject.toml",
    "uv.lock",
    "src/taxrep/cli.py",
    "src/taxrep/data.py",
    "src/taxrep/inference.py",
    "src/taxrep/providers/opencode_go.py",
    "src/taxrep/prompts.py",
    "src/taxrep/parsers.py",
    "src/taxrep/metrics.py",
    "src/taxrep/gates.py",
    "src/taxrep/runs.py",
    "src/taxrep/reports.py",
    "data/manifests/dataset_download_manifest.json",
    "data/manifests/train_processed_manifest.json",
    "data/manifests/test_processed_manifest.json",
    "data/manifests/data_audit.json",
    "results/data_audit.md",
]

FREEZE_REQUIRED_RUN_TYPES = {
    "pilot",
    "main",
    "train-selection",
    "robustness",
    "targeted-t3-repeat",
}
MAIN_RESULTS_REQUIRED_COMMANDS = {"evaluate", "held-out", "statistics", "figures"}


def technical_pretest_summary() -> dict[str, Any]:
    paths = sorted((PROJECT_ROOT / "results" / "raw_predictions").glob("technical-pretest-*.jsonl"))
    if not paths:
        return {"status": "missing", "rows": 0}
    rows = []
    for path in paths:
        rows.extend(read_jsonl(path))
    frame = pd.DataFrame(rows)
    return {
        "status": "present",
        "files": [str(path.relative_to(PROJECT_ROOT)) for path in paths],
        "rows": int(len(frame)),
        "technical_errors": int(frame["technical_error"].notna().sum()),
        "strict_parse_successes": int(frame["strict_parse_success"].sum()),
        "strict_parse_rate": float(frame["strict_parse_success"].mean()),
        "by_model": frame.groupby("model_id")["strict_parse_success"]
        .agg(["sum", "count"])
        .to_dict(orient="index"),
    }


def write_freeze_manifest(
    status: str = "awaiting_human_approval",
    *,
    approved_by: str | None = None,
    approved_at_utc: str | None = None,
) -> dict[str, Any]:
    artifacts = []
    for rel in FREEZE_FILES:
        path = PROJECT_ROOT / rel
        artifacts.append(
            {
                "path": rel,
                "sha256": sha256_file(path) if path.exists() else None,
                "exists": path.exists(),
            }
        )
    payload = {
        "protocol_version": PROTOCOL_VERSION,
        "generated_at_utc": utc_now_iso(),
        "status": status,
        "approved_by": approved_by,
        "approved_at_utc": approved_at_utc,
        "gate": "Gate 2 - Prompt and model freeze",
        "required_human_review_items": [
            "T1-T4 semantic equivalence matrix",
            "model registry and provider health records",
            "protocol deviations DEV-2026-07-04-01..06",
            "technical pretest completion summary",
        ],
        "model_ids": ["deepseek-v4-flash", "kimi-k2.7-code", "glm-5.2"],
        "technical_pretest": technical_pretest_summary(),
        "artifact_hashes": artifacts,
    }
    write_json(PROJECT_ROOT / "experiment" / "freeze_manifest.json", payload)
    write_gate2_status(payload)
    return payload


def load_freeze_manifest() -> dict[str, Any]:
    path = PROJECT_ROOT / "experiment" / "freeze_manifest.json"
    if not path.exists():
        return {}
    import orjson

    return orjson.loads(path.read_bytes())


def is_freeze_approved(manifest: dict[str, Any] | None = None) -> bool:
    manifest = manifest if manifest is not None else load_freeze_manifest()
    return manifest.get("status") == "approved" and bool(manifest.get("approved_by"))


def assert_freeze_approved(run_type: str) -> None:
    if run_type not in FREEZE_REQUIRED_RUN_TYPES:
        return
    if not is_freeze_approved():
        raise RuntimeError(
            f"Gate 2 is not approved; refusing to start `{run_type}` inference. "
            "Review experiment/freeze_manifest.json and run "
            "`uv run taxrep gates approve-freeze --approved-by <name>` after human approval."
        )


def approve_freeze(approved_by: str) -> dict[str, Any]:
    approved_at = utc_now_iso()
    payload = write_freeze_manifest(
        status="approved",
        approved_by=approved_by,
        approved_at_utc=approved_at,
    )
    registry_path = PROJECT_ROOT / "experiment" / "model_registry.csv"
    if registry_path.exists():
        import pandas as pd

        frame = pd.read_csv(registry_path)
        frame["freeze_date"] = approved_at
        write_csv(registry_path, frame.to_dict(orient="records"), list(frame.columns))
        payload = write_freeze_manifest(
            status="approved",
            approved_by=approved_by,
            approved_at_utc=approved_at,
        )
    return payload


def write_gate2_status(freeze_manifest: dict[str, Any] | None = None) -> Path:
    manifest = freeze_manifest or write_freeze_manifest()
    pretest = manifest["technical_pretest"]
    lines = [
        "# Gate 2 Status",
        "",
        f"- Generated at UTC: `{manifest['generated_at_utc']}`",
        f"- Status: `{manifest['status']}`",
        f"- Models: `{', '.join(manifest['model_ids'])}`",
        f"- Technical pretest rows: `{pretest.get('rows', 0)}`",
        f"- Technical pretest strict parse rate: `{pretest.get('strict_parse_rate', 0):.3f}`",
        f"- Technical pretest technical errors: `{pretest.get('technical_errors', 'n/a')}`",
        "",
        "## Required Human Review",
        "",
    ]
    lines.extend(f"- {item}" for item in manifest["required_human_review_items"])
    lines.extend(["", "## Key Files", ""])
    lines.extend(
        [
            "- `experiment/taxonomy_equivalence_matrix.md`",
            "- `experiment/model_registry.csv`",
            "- `experiment/freeze_manifest.json`",
            "",
        ]
    )
    if manifest["status"] == "approved":
        lines.append("Gate 2 is approved; pilot inference may start under the frozen protocol.")
    else:
        lines.append("Pilot inference must not start until this gate is approved.")
    path = PROJECT_ROOT / "results" / "run_manifests" / "gate2_status.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def evaluate_pilot_gate() -> dict[str, Any]:
    summary = summarize_run_type("pilot")
    expected_rows = 150 * 5 * 3
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    add("pilot_present", summary["status"] == "present", summary["status"])
    add("expected_rows", summary.get("rows", 0) == expected_rows, str(summary.get("rows", 0)))
    add(
        "expected_unique_issues",
        summary.get("unique_issues", 0) == 150,
        str(summary.get("unique_issues", 0)),
    )
    add(
        "expected_models",
        set(summary.get("models", [])) == {"deepseek-v4-flash", "kimi-k2.7-code", "glm-5.2"},
        ", ".join(summary.get("models", [])),
    )
    add(
        "expected_conditions",
        set(summary.get("taxonomy_conditions", [])) == {"T0", "T1", "T2", "T3", "T4"},
        ", ".join(summary.get("taxonomy_conditions", [])),
    )
    completion_rate = summary.get("rows", 0) / expected_rows if expected_rows else 0
    add("completion_rate_at_least_0.99", completion_rate >= 0.99, f"{completion_rate:.3f}")
    add(
        "strict_parse_rate_at_least_0.95",
        summary.get("strict_parse_rate", 0) >= 0.95,
        f"{summary.get('strict_parse_rate', 0):.3f}",
    )
    add(
        "no_technical_errors",
        summary.get("technical_errors", 0) == 0,
        str(summary.get("technical_errors", 0)),
    )
    payload = {
        "gate": "Gate 3 - Pilot",
        "generated_at_utc": utc_now_iso(),
        "expected_rows": expected_rows,
        "summary": summary,
        "checks": checks,
        "pass": all(check["ok"] for check in checks),
    }
    write_json(PROJECT_ROOT / "results" / "run_manifests" / "pilot_gate_report.json", payload)
    write_pilot_gate_markdown(payload)
    return payload


def write_pilot_gate_markdown(payload: dict[str, Any]) -> Path:
    summary = payload["summary"]
    lines = [
        "# Gate 3 Pilot Report",
        "",
        f"- Generated at UTC: `{payload['generated_at_utc']}`",
        f"- Pass: `{payload['pass']}`",
        f"- Rows: `{summary.get('rows', 0)}` / `{payload['expected_rows']}`",
        f"- Unique issues: `{summary.get('unique_issues', 0)}`",
        f"- Strict parse rate: `{summary.get('strict_parse_rate', 0):.3f}`",
        f"- Technical errors: `{summary.get('technical_errors', 0)}`",
        "",
        "## Checks",
        "",
        "| Check | OK | Detail |",
        "|---|---:|---|",
    ]
    for check in payload["checks"]:
        lines.append(f"| {check['name']} | `{check['ok']}` | {check['detail']} |")
    lines.extend(
        [
            "",
            "Human approval is still required before starting the main experiment.",
        ]
    )
    path = PROJECT_ROOT / "results" / "run_manifests" / "pilot_gate_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def evaluate_main_results_gate() -> dict[str, Any]:
    summary = summarize_run_type("main")
    expected_rows = 1500 * 5 * 3
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    add("main_present", summary["status"] == "present", summary["status"])
    add("expected_rows", summary.get("rows", 0) == expected_rows, str(summary.get("rows", 0)))
    add(
        "expected_unique_issues",
        summary.get("unique_issues", 0) == 1500,
        str(summary.get("unique_issues", 0)),
    )
    add(
        "expected_models",
        set(summary.get("models", [])) == {"deepseek-v4-flash", "kimi-k2.7-code", "glm-5.2"},
        ", ".join(summary.get("models", [])),
    )
    add(
        "expected_conditions",
        set(summary.get("taxonomy_conditions", [])) == {"T0", "T1", "T2", "T3", "T4"},
        ", ".join(summary.get("taxonomy_conditions", [])),
    )
    completion_rate = summary.get("rows", 0) / expected_rows if expected_rows else 0
    add("completion_complete", completion_rate == 1.0, f"{completion_rate:.3f}")
    add(
        "no_technical_errors",
        summary.get("technical_errors", 0) == 0,
        str(summary.get("technical_errors", 0)),
    )
    payload = {
        "gate": "Gate 4 - Main Experiment",
        "generated_at_utc": utc_now_iso(),
        "expected_rows": expected_rows,
        "summary": summary,
        "checks": checks,
        "pass": all(check["ok"] for check in checks),
    }
    write_json(
        PROJECT_ROOT / "results" / "run_manifests" / "main_results_gate_report.json", payload
    )
    write_main_results_gate_markdown(payload)
    return payload


def write_main_results_gate_markdown(payload: dict[str, Any]) -> Path:
    summary = payload["summary"]
    lines = [
        "# Gate 4 Main Results Report",
        "",
        f"- Generated at UTC: `{payload['generated_at_utc']}`",
        f"- Pass: `{payload['pass']}`",
        f"- Rows: `{summary.get('rows', 0)}` / `{payload['expected_rows']}`",
        f"- Unique issues: `{summary.get('unique_issues', 0)}`",
        f"- Strict parse rate: `{summary.get('strict_parse_rate', 0):.3f}`",
        f"- Technical errors: `{summary.get('technical_errors', 0)}`",
        "",
        "## Checks",
        "",
        "| Check | OK | Detail |",
        "|---|---:|---|",
    ]
    for check in payload["checks"]:
        lines.append(f"| {check['name']} | `{check['ok']}` | {check['detail']} |")
    lines.extend(
        [
            "",
            "Evaluation commands must not open test labels until main results are frozen.",
        ]
    )
    path = PROJECT_ROOT / "results" / "run_manifests" / "main_results_gate_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main_result_files() -> list[dict[str, Any]]:
    files = []
    for path in sorted((PROJECT_ROOT / "results" / "raw_predictions").glob("main*.jsonl")):
        files.append(
            {
                "path": str(path.relative_to(PROJECT_ROOT)),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    for path in sorted((PROJECT_ROOT / "results" / "raw_predictions").glob("main*.parquet")):
        files.append(
            {
                "path": str(path.relative_to(PROJECT_ROOT)),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    return files


def freeze_main_results(frozen_by: str) -> dict[str, Any]:
    gate = evaluate_main_results_gate()
    if not gate["pass"]:
        raise RuntimeError(
            "Main results cannot be frozen because Gate 4 checks did not pass. "
            "Inspect results/run_manifests/main_results_gate_report.md."
        )
    payload = {
        "status": "frozen",
        "frozen_by": frozen_by,
        "frozen_at_utc": utc_now_iso(),
        "gate_report": "results/run_manifests/main_results_gate_report.json",
        "main_result_files": main_result_files(),
        "gate": gate,
    }
    write_json(PROJECT_ROOT / "results" / "run_manifests" / "main_results_freeze.json", payload)
    return payload


def load_main_results_freeze() -> dict[str, Any]:
    path = PROJECT_ROOT / "results" / "run_manifests" / "main_results_freeze.json"
    if not path.exists():
        return {}
    import orjson

    return orjson.loads(path.read_bytes())


def assert_main_results_frozen(command_name: str) -> None:
    if command_name not in MAIN_RESULTS_REQUIRED_COMMANDS:
        return
    manifest = load_main_results_freeze()
    if manifest.get("status") != "frozen":
        raise RuntimeError(
            f"Main results are not frozen; refusing to run `{command_name}` because it may "
            "open gold labels. Run `uv run taxrep gates freeze-main-results --frozen-by <name>` "
            "after all 22,500 main predictions are complete."
        )
