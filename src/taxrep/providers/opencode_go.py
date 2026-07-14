from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from openai import OpenAI

from taxrep.constants import PROJECT_ROOT
from taxrep.utils import sha256_file, today_yyyymmdd, utc_now_iso, write_json

SAFE_RESPONSE_HEADERS = {
    "content-type",
    "date",
    "x-request-id",
    "request-id",
    "cf-ray",
    "retry-after",
    "x-ratelimit-limit-requests",
    "x-ratelimit-remaining-requests",
    "x-ratelimit-reset-requests",
}


@dataclass(frozen=True)
class ProviderConfig:
    base_url: str
    api_key_env: str = "OPENCODE_GO_KEY"
    fallback_api_key_env: str = "OPENCODE_API_KEY"
    request_overrides: dict[str, dict[str, Any]] | None = None


@dataclass(frozen=True)
class ProviderResponse:
    raw_output: str
    response_model: str | None
    finish_reason: str | None
    system_fingerprint: str | None
    usage: dict[str, Any]
    response_headers: dict[str, str]
    request_id: str | None
    request_parameters: dict[str, Any]


def load_dotenv(path: Path | None = None) -> None:
    env_path = path or PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def _safe_headers(headers: httpx.Headers | dict[str, str]) -> dict[str, str]:
    return {
        key: value for key, value in dict(headers).items() if key.lower() in SAFE_RESPONSE_HEADERS
    }


class OpenCodeGoProvider:
    def __init__(self, config: ProviderConfig, *, timeout_seconds: int = 120) -> None:
        load_dotenv()
        self.config = config
        self.timeout_seconds = timeout_seconds
        self._api_key = self._resolve_api_key()
        self._client = OpenAI(
            api_key=self._api_key,
            base_url=self.config.base_url,
            timeout=timeout_seconds,
            # The project-level retry loop meters every provider attempt before
            # transmission.  SDK-internal retries would bypass that durable
            # ledger, so they are disabled for every project call.
            max_retries=0,
        )

    def _resolve_api_key(self) -> str:
        for env_name in (self.config.api_key_env, self.config.fallback_api_key_env):
            value = os.environ.get(env_name)
            if value:
                return value
        raise RuntimeError(
            "OpenCode Go API key is missing. Set OPENCODE_GO_KEY or OPENCODE_API_KEY in .env."
        )

    @classmethod
    def from_models_config(
        cls,
        path: Path | None = None,
        *,
        timeout_seconds: int = 120,
    ) -> OpenCodeGoProvider:
        import yaml

        config_path = path or PROJECT_ROOT / "configs" / "models.yaml"
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))["provider"]
        return cls(
            ProviderConfig(
                base_url=raw["base_url"],
                api_key_env=raw.get("api_key_env", "OPENCODE_GO_KEY"),
                fallback_api_key_env=raw.get("fallback_api_key_env", "OPENCODE_API_KEY"),
                request_overrides=yaml.safe_load(config_path.read_text(encoding="utf-8")).get(
                    "request_overrides", {}
                ),
            ),
            timeout_seconds=timeout_seconds,
        )

    def _overrides_for(self, model_id: str) -> dict[str, Any]:
        return (self.config.request_overrides or {}).get(model_id, {})

    def snapshot_catalog(self, *, output_path: Path | None = None) -> dict[str, Any]:
        path = output_path or (
            PROJECT_ROOT / "experiment" / f"provider_catalog_snapshot_{today_yyyymmdd()}.json"
        )
        if output_path is not None and path.exists():
            raise FileExistsError(f"Refusing to overwrite provider catalog snapshot: {path}")
        url = f"{self.config.base_url.rstrip('/')}/models"
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.get(url, headers={"Authorization": f"Bearer {self._api_key}"})
            response.raise_for_status()
        payload = {
            "captured_at_utc": utc_now_iso(),
            "endpoint": url,
            "status_code": response.status_code,
            "headers": _safe_headers(response.headers),
            "body": response.json(),
        }
        write_json(path, payload)
        return {
            "path": str(path),
            "sha256": sha256_file(path),
            "model_ids": catalog_model_ids(payload),
        }

    def chat_completion(
        self,
        *,
        model_id: str,
        system_message: str,
        user_message: str,
        temperature: float,
        top_p: float,
        max_new_tokens: int,
        seed: int | None,
    ) -> ProviderResponse:
        overrides = self._overrides_for(model_id)
        api_max_tokens = int(overrides.get("api_max_tokens", max_new_tokens))
        kwargs: dict[str, Any] = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": api_max_tokens,
        }
        if not overrides.get("omit_temperature", False):
            kwargs["temperature"] = temperature
        if not overrides.get("omit_top_p", False):
            kwargs["top_p"] = top_p
        if seed is not None:
            kwargs["seed"] = seed
        raw_response = self._client.chat.completions.with_raw_response.create(**kwargs)
        completion = raw_response.parse()
        content = completion.choices[0].message.content or ""
        headers = _safe_headers(raw_response.headers)
        return ProviderResponse(
            raw_output=content,
            response_model=getattr(completion, "model", None),
            finish_reason=getattr(completion.choices[0], "finish_reason", None),
            system_fingerprint=getattr(completion, "system_fingerprint", None),
            usage=completion.usage.model_dump(mode="json") if completion.usage else {},
            response_headers=headers,
            request_id=headers.get("x-request-id") or headers.get("request-id"),
            request_parameters={
                "api_max_tokens": api_max_tokens,
                "temperature_sent": "temperature" in kwargs,
                "temperature_requested": temperature if "temperature" in kwargs else None,
                "top_p_sent": "top_p" in kwargs,
                "top_p_requested": top_p if "top_p" in kwargs else None,
                "seed_sent": "seed" in kwargs,
                "seed_requested": seed if "seed" in kwargs else None,
            },
        )

    def health_check(
        self,
        model_ids: list[str],
        *,
        call_budget: Any | None = None,
        run_id: str = "provider-health",
        output_path: Path | None = None,
    ) -> dict[str, Any]:
        path = output_path or (
            PROJECT_ROOT / "experiment" / f"provider_health_{today_yyyymmdd()}.json"
        )
        if output_path is not None and path.exists():
            raise FileExistsError(f"Refusing to overwrite provider health artifact: {path}")
        records: list[dict[str, Any]] = []
        for model_id in model_ids:
            started = utc_now_iso()
            record: dict[str, Any] = {
                "model_id": model_id,
                "started_at_utc": started,
                "temperature_supported": None,
                "seed_supported": None,
                "system_role_supported": None,
                "max_tokens_field": "max_tokens",
                "reasoning_requested": False,
                "reasoning_observed": None,
            }
            overrides = self._overrides_for(model_id)
            try:
                if call_budget is not None:
                    call_budget.reserve(
                        kind="provider_health",
                        model_id=model_id,
                        run_id=run_id,
                        task_key=f"provider-health/{model_id}",
                        attempt=1,
                    )
                response = self.chat_completion(
                    model_id=model_id,
                    system_message=(
                        "You are a software issue classification engine. Return exactly "
                        'one JSON object with a single key named "label".'
                    ),
                    user_message=(
                        "Allowed labels: bug, feature, question.\n"
                        "ISSUE_DATA\n"
                        '{"title":"Crash on startup","body":"The app crashes when opened."}\n'
                        "OUTPUT_SCHEMA\n"
                        '{"label":"<one of: bug, feature, question>"}'
                    ),
                    temperature=0.0,
                    top_p=1.0,
                    max_new_tokens=32,
                    seed=20260704,
                )
                record.update(
                    {
                        "ok": True,
                        "completed_at_utc": utc_now_iso(),
                        "response_model": response.response_model,
                        "finish_reason": response.finish_reason,
                        "system_fingerprint": response.system_fingerprint,
                        "request_id": response.request_id,
                        "usage": response.usage,
                        "response_headers": response.response_headers,
                        "raw_output_preview": response.raw_output[:80],
                        "request_parameters": response.request_parameters,
                        "temperature_supported": not overrides.get("omit_temperature", False),
                        "seed_supported": True,
                        "top_p_supported": not overrides.get("omit_top_p", False),
                        "system_role_supported": True,
                    }
                )
                reasoning_tokens = None
                details = response.usage.get("completion_tokens_details")
                if isinstance(details, dict):
                    reasoning_tokens = details.get("reasoning_tokens")
                elif "reasoning_tokens" in response.usage:
                    reasoning_tokens = response.usage.get("reasoning_tokens")
                record["reasoning_observed"] = bool(reasoning_tokens)
            except Exception as exc:
                record.update(
                    {
                        "ok": False,
                        "completed_at_utc": utc_now_iso(),
                        "error_type": type(exc).__name__,
                        "error_message": str(exc)[:500],
                    }
                )
            records.append(record)
        payload = {
            "captured_at_utc": utc_now_iso(),
            "base_url": self.config.base_url,
            "records": records,
        }
        write_json(path, payload)
        return {"path": str(path), "records": records}


def catalog_model_ids(snapshot_payload: dict[str, Any]) -> list[str]:
    body = snapshot_payload.get("body", {})
    data = body.get("data", []) if isinstance(body, dict) else []
    ids: list[str] = []
    for item in data:
        if isinstance(item, dict) and "id" in item:
            ids.append(str(item["id"]))
        elif isinstance(item, str):
            ids.append(item)
    return sorted(ids)
