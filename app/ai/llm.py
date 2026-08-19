"""LLM access layer.

Two providers are supported — any OpenAI-compatible endpoint (OpenAI, OpenRouter,
vLLM, Ollama, llama.cpp) and Anthropic — because a hackathon judge may run this
on a laptop with a local model and no internet.

The layer is **optional by design**: ``ask_model`` returns ``None`` on every
failure path (disabled, timeout, malformed JSON, schema mismatch) and the
planner keeps working deterministically. That is what makes the app stable.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import Settings

logger = logging.getLogger(__name__)

TModel = TypeVar("TModel", bound=BaseModel)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def extract_json(text: str) -> dict[str, Any] | None:
    """Pull a JSON object out of a model reply that may be wrapped in prose."""
    if not text:
        return None
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", stripped).strip()
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    match = _JSON_BLOCK.search(stripped)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


class LLMClient:
    """Thin, provider-agnostic JSON-mode client."""

    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None):
        self._settings = settings
        self._own_http = http is None
        self._http = http or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.llm_timeout_s, connect=5.0)
        )
        self.calls = 0
        self.failures = 0

    @property
    def enabled(self) -> bool:
        return self._settings.llm_ready

    async def aclose(self) -> None:
        if self._own_http:
            await self._http.aclose()

    async def ask_model(
        self,
        *,
        system: str,
        user: str,
        schema: type[TModel],
        temperature: float | None = None,
    ) -> TModel | None:
        """Ask for JSON and validate it. ``None`` means 'carry on without me'."""
        if not self.enabled:
            return None
        self.calls += 1
        try:
            raw = await self._complete(system, user, temperature)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            self.failures += 1
            logger.warning("llm transport failure", extra={"error": str(exc)})
            return None
        except Exception as exc:  # pragma: no cover - provider quirks
            self.failures += 1
            logger.warning("llm call failed", extra={"error": str(exc)})
            return None

        payload = extract_json(raw or "")
        if payload is None:
            self.failures += 1
            logger.warning("llm returned no parsable json")
            return None
        try:
            return schema.model_validate(payload)
        except ValidationError as exc:
            self.failures += 1
            logger.warning(
                "llm output failed validation",
                extra={"schema": schema.__name__, "errors": exc.error_count()},
            )
            return None

    # -- providers -------------------------------------------------------

    async def _complete(self, system: str, user: str, temperature: float | None) -> str:
        settings = self._settings
        temp = settings.llm_temperature if temperature is None else temperature
        if settings.llm_provider == "anthropic":
            return await self._anthropic(system, user, temp)
        return await self._openai(system, user, temp)

    async def _openai(self, system: str, user: str, temperature: float) -> str:
        settings = self._settings
        response = await self._http.post(
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.llm_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.llm_model,
                "max_tokens": settings.llm_max_tokens,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def _anthropic(self, system: str, user: str, temperature: float) -> str:
        settings = self._settings
        base = settings.llm_base_url.rstrip("/")
        if "anthropic" not in base:
            base = "https://api.anthropic.com/v1"
        response = await self._http.post(
            f"{base}/messages",
            headers={
                "x-api-key": settings.llm_api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.llm_model,
                "max_tokens": settings.llm_max_tokens,
                "temperature": temperature,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        response.raise_for_status()
        data = response.json()
        return "".join(
            block.get("text", "") for block in data.get("content", []) if isinstance(block, dict)
        )
