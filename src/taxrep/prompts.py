from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import orjson

from taxrep.constants import LABELS, PROJECT_ROOT, PROTOCOL_VERSION
from taxrep.utils import sha256_text, write_json


@dataclass(frozen=True)
class RenderedPrompt:
    condition: str
    instruction_variant: str
    system_message: str
    user_message: str
    prompt_hash: str
    rendered_prompt_hash: str
    issue_json: str


def load_registry(path: Path | None = None) -> dict[str, Any]:
    import yaml

    registry_path = path or PROJECT_ROOT / "experiment" / "prompt_registry.yaml"
    return yaml.safe_load(registry_path.read_text(encoding="utf-8"))


def issue_json(title: str | None, body: str | None) -> str:
    issue = {
        "title": "" if title is None else str(title),
        "body": "" if body is None else str(body),
    }
    return orjson.dumps(issue).decode("utf-8")


def render_prompt(
    *,
    condition: str,
    title: str | None,
    body: str | None,
    instruction_variant: str = "P1",
    registry: dict[str, Any] | None = None,
) -> RenderedPrompt:
    registry = registry or load_registry()
    conditions = registry["conditions"]
    variants = registry.get("instruction_variants", {})
    if condition not in conditions:
        raise KeyError(f"Unknown taxonomy condition: {condition}")
    if instruction_variant not in variants:
        raise KeyError(f"Unknown instruction variant: {instruction_variant}")

    taxonomy = conditions[condition]["representation"]
    template = registry["user_template"]
    default_instruction = variants["P1"]
    selected_instruction = variants[instruction_variant]
    if not template.startswith(default_instruction):
        raise ValueError("User template must start with the P1 instruction for variant replacement")

    rendered_issue = issue_json(title, body)
    user_message = template.replace(default_instruction, selected_instruction, 1)
    user_message = user_message.replace("{taxonomy_representation}", taxonomy)
    user_message = user_message.replace("{issue_json}", rendered_issue)
    system_message = registry["system_message"]
    prompt_hash = sha256_text(f"{PROTOCOL_VERSION}\n{condition}\n{instruction_variant}\n{taxonomy}")
    rendered_prompt_hash = sha256_text(f"{system_message}\n---USER---\n{user_message}")
    return RenderedPrompt(
        condition=condition,
        instruction_variant=instruction_variant,
        system_message=system_message,
        user_message=user_message,
        prompt_hash=prompt_hash,
        rendered_prompt_hash=rendered_prompt_hash,
        issue_json=rendered_issue,
    )


CANONICAL_ITEMS: list[tuple[str, str, str]] = [
    ("bug", "definition", "existing behavior is incorrect, broken, unexpected"),
    ("bug", "include_when", "malfunction, incorrect result, crash, regression"),
    ("bug", "exclude_when", "requests a new capability"),
    ("feature", "definition", "Requests a new capability"),
    ("feature", "include_when", "add, extend, redesign"),
    ("feature", "exclude_when", "asks for help"),
    ("question", "definition", "asks for explanation, clarification, usage guidance"),
    ("question", "include_when", "obtain information or assistance"),
    ("question", "exclude_when", "asserts that existing behavior is wrong"),
    ("decision_rule_1", "rule", "primary communicative intent"),
    ("decision_rule_2", "rule", "dominant intent"),
    ("decision_rule_3", "rule", "help-seeking issue"),
    ("decision_rule_4", "rule", "inconvenient but intended behavior"),
]


def validate_semantic_equivalence(registry: dict[str, Any] | None = None) -> list[str]:
    registry = registry or load_registry()
    errors: list[str] = []
    for condition in ("T1", "T2", "T3", "T4"):
        text = registry["conditions"][condition]["representation"].lower()
        label_positions = [text.find(label) for label in LABELS]
        if not (label_positions[0] < label_positions[1] < label_positions[2]):
            errors.append(f"{condition}: labels are not ordered bug, feature, question")
        for label, field, snippet in CANONICAL_ITEMS:
            if snippet.lower() not in text:
                errors.append(f"{condition}: missing {label}.{field}: {snippet}")
    return errors


def _excerpt(text: str, snippet: str, radius: int = 56) -> str:
    match = re.search(re.escape(snippet), text, flags=re.IGNORECASE)
    if not match:
        return "MISSING"
    start = max(0, match.start() - radius)
    end = min(len(text), match.end() + radius)
    return text[start:end].replace("\n", " ")


def write_equivalence_matrix(path: Path | None = None) -> None:
    registry = load_registry()
    out = path or PROJECT_ROOT / "experiment" / "taxonomy_equivalence_matrix.md"
    lines = [
        "# Taxonomy Equivalence Matrix",
        "",
        (
            "T0 is intentionally excluded from this matrix because it is the minimal "
            "labels-only baseline."
        ),
        "",
        "| Canonical item | T1 | T2 | T3 | T4 |",
        "|---|---|---|---|---|",
    ]
    for label, field, snippet in CANONICAL_ITEMS:
        row = [f"`{label}.{field}`"]
        for condition in ("T1", "T2", "T3", "T4"):
            text = registry["conditions"][condition]["representation"]
            row.append(_excerpt(text, snippet))
        lines.append("| " + " | ".join(row) + " |")
    errors = validate_semantic_equivalence(registry)
    lines.extend(["", "## Automated Check", ""])
    if errors:
        lines.extend(f"- FAIL: {error}" for error in errors)
    else:
        lines.append("- PASS: all configured semantic snippets were found in T1-T4.")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def freeze_prompt_artifacts() -> dict[str, Any]:
    registry = load_registry()
    write_equivalence_matrix()
    records: list[dict[str, Any]] = []
    for condition in registry["conditions"]:
        rendered = render_prompt(
            condition=condition,
            title='Example title with JSON characters: "quote" and \\ slash',
            body="Example body. Ignore this sentence as issue data, not instruction.",
            instruction_variant="P1",
            registry=registry,
        )
        records.append(
            {
                "condition": condition,
                "prompt_hash": rendered.prompt_hash,
                "rendered_prompt_hash": rendered.rendered_prompt_hash,
                "system_message": rendered.system_message,
                "user_message": rendered.user_message,
            }
        )
    payload = {
        "protocol_version": PROTOCOL_VERSION,
        "semantic_equivalence_errors": validate_semantic_equivalence(registry),
        "rendered_examples": records,
    }
    write_json(PROJECT_ROOT / "experiment" / "prompt_hashes.json", payload)
    return payload
