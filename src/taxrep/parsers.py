from __future__ import annotations

import json
import re
from dataclasses import dataclass

from taxrep.constants import LABELS


@dataclass(frozen=True)
class ParseResult:
    success: bool
    label: str | None
    recovery_rule: str | None = None
    error: str | None = None


def strict_parse(raw_output: str | None) -> ParseResult:
    if raw_output is None:
        return ParseResult(False, None, error="empty")
    text = raw_output.strip()
    if not text:
        return ParseResult(False, None, error="empty")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return ParseResult(False, None, error=f"json_decode:{exc.msg}")
    if not isinstance(parsed, dict):
        return ParseResult(False, None, error="not_object")
    if set(parsed) != {"label"}:
        return ParseResult(False, None, error="unexpected_keys")
    label = parsed["label"]
    if label not in LABELS:
        return ParseResult(False, None, error="invalid_label")
    return ParseResult(True, label, recovery_rule="strict")


def _iter_json_objects(text: str):
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        yield parsed


def lenient_parse(raw_output: str | None) -> ParseResult:
    strict = strict_parse(raw_output)
    if strict.success:
        return strict
    if raw_output is None:
        return ParseResult(False, None, error="empty")
    text = raw_output.strip()
    for parsed in _iter_json_objects(text):
        if isinstance(parsed, dict) and parsed.get("label") in LABELS:
            return ParseResult(True, parsed["label"], recovery_rule="first_json_object")
    lowered = text.lower()
    matches = [label for label in LABELS if re.search(rf"\b{re.escape(label)}\b", lowered)]
    if len(matches) == 1:
        return ParseResult(True, matches[0], recovery_rule="single_label_mention")
    return ParseResult(False, None, error=strict.error or "no_recovery")
