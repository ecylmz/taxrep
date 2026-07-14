from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import Annotated

import httpx
import pandas as pd
import typer
from rich.console import Console

from taxrep.constants import PROJECT_ROOT
from taxrep.data import download_dataset, validate_dataset
from taxrep.evaluate import evaluate_predictions, evaluate_tfidf_svm_baseline
from taxrep.figures import build_figures
from taxrep.gates import (
    approve_freeze,
    assert_main_results_frozen,
    evaluate_main_results_gate,
    evaluate_pilot_gate,
    freeze_main_results,
    load_freeze_manifest,
    write_freeze_manifest,
)
from taxrep.held_out import compute_project_held_out
from taxrep.inference import load_models, parse_raw_predictions, run_inference
from taxrep.prompts import freeze_prompt_artifacts
from taxrep.providers.opencode_go import OpenCodeGoProvider
from taxrep.reports import completeness_report, write_run_report
from taxrep.revision_audit import run_revision_audit
from taxrep.statistics import run_statistics
from taxrep.targeted import (
    analyze_targeted_extension,
    freeze_targeted_extension,
    targeted_provider_preflight,
    verify_targeted_extension_freeze,
)
from taxrep.targeted_audit import run_targeted_operational_audit
from taxrep.targeted_recovery import (
    capture_targeted_recovery_catalog,
    freeze_targeted_recovery,
    targeted_recovery_provider_preflight,
    verify_targeted_recovery_freeze,
)
from taxrep.targeted_result_gate import verify_targeted_results_freeze
from taxrep.utils import load_yaml, sha256_file, today_yyyymmdd, utc_now_iso, write_json

console = Console()
app = typer.Typer(no_args_is_help=True)
data_app = typer.Typer(no_args_is_help=True)
prompts_app = typer.Typer(no_args_is_help=True)
provider_app = typer.Typer(no_args_is_help=True)
gates_app = typer.Typer(no_args_is_help=True)
reports_app = typer.Typer(no_args_is_help=True)
targeted_app = typer.Typer(no_args_is_help=True)
DEFAULT_PILOT_CONFIG = PROJECT_ROOT / "configs" / "pilot.yaml"
DEFAULT_MAIN_CONFIG = PROJECT_ROOT / "configs" / "main.yaml"


@data_app.command("download")
def data_download(
    force: Annotated[bool, typer.Option(help="Re-download raw files.")] = False,
) -> None:
    manifest = download_dataset(force=force)
    console.print(manifest)


@data_app.command("validate")
def data_validate() -> None:
    report = validate_dataset()
    if report["errors"]:
        console.print(report)
        raise typer.Exit(code=1)
    console.print(
        {
            "audit": "results/data_audit.md",
            "train_rows": report["splits"]["train"]["rows"],
            "test_rows": report["splits"]["test"]["rows"],
            "errors": len(report["errors"]),
        }
    )


@prompts_app.command("freeze")
def prompts_freeze() -> None:
    payload = freeze_prompt_artifacts()
    if payload["semantic_equivalence_errors"]:
        console.print(payload["semantic_equivalence_errors"])
        raise typer.Exit(code=1)
    console.print({"prompt_hashes": "experiment/prompt_hashes.json", "conditions": 5})


def _limits_snapshot() -> dict[str, str]:
    url = "https://opencode.ai/data/"
    path = PROJECT_ROOT / "experiment" / f"provider_limits_snapshot_{today_yyyymmdd()}.md"
    try:
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            response = client.get(url)
        body = response.text[:40_000]
        content = "\n".join(
            [
                "# OpenCode Go Usage-Limit Snapshot",
                "",
                f"- Captured at UTC: `{utc_now_iso()}`",
                f"- Source URL: `{url}`",
                f"- HTTP status: `{response.status_code}`",
                "",
                (
                    "The source is dynamic; this file stores the visible response "
                    "body at capture time."
                ),
                "",
                "```html",
                body,
                "```",
            ]
        )
    except Exception as exc:
        content = "\n".join(
            [
                "# OpenCode Go Usage-Limit Snapshot",
                "",
                f"- Captured at UTC: `{utc_now_iso()}`",
                f"- Source URL: `{url}`",
                f"- Capture failed: `{type(exc).__name__}: {str(exc)[:300]}`",
            ]
        )
    path.write_text(content + "\n", encoding="utf-8")
    return {"path": str(path), "sha256": sha256_file(path)}


@provider_app.command("snapshot")
def provider_snapshot() -> None:
    provider = OpenCodeGoProvider.from_models_config()
    catalog = provider.snapshot_catalog()
    limits = _limits_snapshot()
    required = set(load_models())
    missing = sorted(required - set(catalog["model_ids"]))
    payload = {"catalog": catalog, "limits": limits, "required_missing": missing}
    summary_path = (
        PROJECT_ROOT
        / "experiment"
        / f"provider_snapshot_summary_{today_yyyymmdd()}.json"
    )
    write_json(summary_path, payload)
    console.print(payload)
    if missing:
        raise typer.Exit(code=1)


def _latest_matching(pattern: str) -> Path | None:
    matches = sorted((PROJECT_ROOT / "experiment").glob(pattern))
    return matches[-1] if matches else None


def _update_model_registry(health_records: list[dict]) -> None:
    models_config = load_yaml(PROJECT_ROOT / "configs" / "models.yaml")
    catalog = _latest_matching("provider_catalog_snapshot_*.json")
    limits = _latest_matching("provider_limits_snapshot_*.md")
    rows: list[dict] = []
    by_model = {record["model_id"]: record for record in health_records}
    for model in models_config["models"]:
        record = by_model.get(model["id"], {})
        rows.append(
            {
                "provider": "OpenCode Go",
                "endpoint": models_config["provider"]["base_url"],
                "model_id": model["id"],
                "model_family": model["family"],
                "catalog_snapshot_file": str(catalog.relative_to(PROJECT_ROOT)) if catalog else "",
                "catalog_snapshot_sha256": sha256_file(catalog) if catalog else "",
                "limits_snapshot_file": str(limits.relative_to(PROJECT_ROOT)) if limits else "",
                "access_date_utc": utc_now_iso(),
                "api_type": "openai-chat-completions",
                "reasoning_requested": "false",
                "reasoning_observed": str(record.get("reasoning_observed", "unknown")).lower(),
                "temperature_supported": str(
                    record.get("temperature_supported", "unknown")
                ).lower(),
                "seed_supported": str(record.get("seed_supported", "unknown")).lower(),
                "system_role_supported": str(
                    record.get("system_role_supported", "unknown")
                ).lower(),
                "max_tokens_field": "max_tokens",
                "python_client_version": importlib.metadata.version("openai"),
                "selection_reason": (
                    "Pre-specified by protocol v1.2; not selected from test performance."
                ),
                "freeze_date": "",
            }
        )
    path = PROJECT_ROOT / "experiment" / "model_registry.csv"
    pd.DataFrame(rows).to_csv(path, index=False, lineterminator="\n")


@provider_app.command("health-check")
def provider_health_check() -> None:
    provider = OpenCodeGoProvider.from_models_config()
    result = provider.health_check(load_models())
    _update_model_registry(result["records"])
    console.print(result)
    if not all(record.get("ok") for record in result["records"]):
        raise typer.Exit(code=1)


@gates_app.command("freeze-manifest")
def gates_freeze_manifest() -> None:
    current = load_freeze_manifest()
    status = current.get("status", "awaiting_human_approval")
    payload = write_freeze_manifest(
        status=status,
        approved_by=current.get("approved_by"),
        approved_at_utc=current.get("approved_at_utc"),
    )
    console.print(
        {
            "status": payload["status"],
            "artifact_count": len(payload["artifact_hashes"]),
            "technical_pretest": payload["technical_pretest"],
        }
    )


@gates_app.command("approve-freeze")
def gates_approve_freeze(
    approved_by: Annotated[str, typer.Option(help="Human approver name or initials.")],
) -> None:
    payload = approve_freeze(approved_by)
    console.print(
        {
            "status": payload["status"],
            "approved_by": payload["approved_by"],
            "approved_at_utc": payload["approved_at_utc"],
            "artifact_count": len(payload["artifact_hashes"]),
        }
    )


@gates_app.command("pilot-report")
def gates_pilot_report() -> None:
    payload = evaluate_pilot_gate()
    console.print(
        {
            "pass": payload["pass"],
            "rows": payload["summary"].get("rows", 0),
            "strict_parse_rate": payload["summary"].get("strict_parse_rate", 0),
            "technical_errors": payload["summary"].get("technical_errors", 0),
        }
    )


@gates_app.command("main-report")
def gates_main_report() -> None:
    payload = evaluate_main_results_gate()
    console.print(
        {
            "pass": payload["pass"],
            "rows": payload["summary"].get("rows", 0),
            "strict_parse_rate": payload["summary"].get("strict_parse_rate", 0),
            "technical_errors": payload["summary"].get("technical_errors", 0),
        }
    )


@gates_app.command("freeze-main-results")
def gates_freeze_main_results(
    frozen_by: Annotated[str, typer.Option(help="Human freezer name or initials.")],
) -> None:
    try:
        payload = freeze_main_results(frozen_by)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(
        {
            "status": payload["status"],
            "frozen_by": payload["frozen_by"],
            "frozen_at_utc": payload["frozen_at_utc"],
            "file_count": len(payload["main_result_files"]),
        }
    )


@reports_app.command("run")
def reports_run(run_type: Annotated[str, typer.Argument(help="Run type to summarize.")]) -> None:
    console.print(write_run_report(run_type))


@reports_app.command("completeness")
def reports_completeness(
    run_type: Annotated[str, typer.Argument(help="Run type to check for missing raw cells.")],
) -> None:
    console.print(completeness_report(run_type))


@targeted_app.command("freeze")
def targeted_freeze(
    protocol_commit: Annotated[
        str | None,
        typer.Option(help="Committed protocol revision recorded in the hash manifest."),
    ] = None,
) -> None:
    payload = freeze_targeted_extension(protocol_commit=protocol_commit)
    console.print(
        {
            "protocol_commit": payload["protocol_commit"],
            "task_count": payload["task_plan"]["task_count"],
            "task_order_sha256": payload["task_plan"]["task_order_sha256"],
        }
    )


@targeted_app.command("verify-freeze")
def targeted_verify_freeze() -> None:
    console.print(verify_targeted_extension_freeze())


@targeted_app.command("preflight")
def targeted_preflight() -> None:
    console.print(targeted_provider_preflight())


@targeted_app.command("recovery-catalog")
def targeted_recovery_catalog() -> None:
    console.print(capture_targeted_recovery_catalog())


@targeted_app.command("freeze-recovery")
def targeted_freeze_recovery(
    protocol_commit: Annotated[
        str,
        typer.Option(help="Committed recovery protocol revision recorded in the hash manifest."),
    ],
) -> None:
    payload = freeze_targeted_recovery(protocol_commit=protocol_commit)
    console.print(
        {
            "protocol_commit": payload["protocol_commit"],
            "prior_successful_tasks": payload["reconciliation"][
                "prior_successful_tasks"
            ],
            "missing_tasks": payload["reconciliation"]["missing_tasks"],
            "revision_http_attempt_hard_cap": payload["budget"][
                "revision_http_attempt_hard_cap"
            ],
        }
    )


@targeted_app.command("verify-recovery-freeze")
def targeted_verify_recovery_freeze() -> None:
    console.print(verify_targeted_recovery_freeze())


@targeted_app.command("recovery-preflight")
def targeted_recovery_preflight() -> None:
    console.print(targeted_recovery_provider_preflight())


@targeted_app.command("analyze")
def targeted_analyze() -> None:
    verify_targeted_results_freeze()
    console.print(analyze_targeted_extension())


@targeted_app.command("audit")
def targeted_audit() -> None:
    verify_targeted_results_freeze()
    console.print(run_targeted_operational_audit())


@app.command("revision-audit")
def revision_audit() -> None:
    console.print(run_revision_audit())


@app.command()
def pilot(
    config: Annotated[Path, typer.Option(help="Pilot config path.")] = DEFAULT_PILOT_CONFIG,
) -> None:
    try:
        manifest = run_inference(config)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(manifest)


@app.command()
def infer(
    config: Annotated[Path, typer.Option(help="Inference config path.")] = DEFAULT_MAIN_CONFIG,
    model: Annotated[str | None, typer.Option(help="Optional single model id.")] = None,
) -> None:
    try:
        manifest = run_inference(config, model_id=model)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(manifest)


@app.command()
def parse() -> None:
    console.print(parse_raw_predictions())


@app.command()
def evaluate() -> None:
    try:
        assert_main_results_frozen("evaluate")
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    results = {"llm": None, "baseline": None}
    try:
        results["llm"] = evaluate_predictions()
    except FileNotFoundError as exc:
        results["llm"] = {"skipped": str(exc)}
    results["baseline"] = evaluate_tfidf_svm_baseline()
    console.print(results)


@app.command("held-out")
def held_out() -> None:
    try:
        assert_main_results_frozen("held-out")
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(compute_project_held_out())


@app.command()
def statistics() -> None:
    try:
        assert_main_results_frozen("statistics")
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(run_statistics())


@app.command()
def figures() -> None:
    try:
        assert_main_results_frozen("figures")
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(build_figures())


app.add_typer(data_app, name="data")
app.add_typer(prompts_app, name="prompts")
app.add_typer(provider_app, name="provider")
app.add_typer(gates_app, name="gates")
app.add_typer(reports_app, name="reports")
app.add_typer(targeted_app, name="targeted")


if __name__ == "__main__":
    app()
