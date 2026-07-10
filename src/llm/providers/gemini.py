"""Gemini provider — structured output, token-usage capture, one retry with backoff.

Structured output uses `response_mime_type="application/json"` +
`response_schema=<pydantic model>`; usage comes from `response.usage_metadata`.
Retry policy per spec/agent.md: one retry with backoff on timeout/5xx/429, then
a clear, transparent error.
"""

import time

import httpx
from google import genai
from google.genai import types
from pydantic import BaseModel

from llm.client import LLMResult

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_RETRY_DELAY_S = 2.0


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return True
    code = getattr(exc, "code", None)
    if code is None:
        code = getattr(exc, "status_code", None)
    try:
        code = int(code)
    except (TypeError, ValueError):
        return False
    return code in _RETRYABLE_STATUS or code >= 500


class GeminiProvider:
    DEFAULT_MODEL = "gemini-2.5-pro"

    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model or self.DEFAULT_MODEL

    @property
    def model(self) -> str:
        return self._model

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        schema: type[BaseModel] | None = None,
        temperature: float | None = None,
    ) -> LLMResult:
        started = time.monotonic()
        try:
            response = self._generate_once(
                prompt, system=system, schema=schema, temperature=temperature
            )
        except Exception as exc:
            if not _is_retryable(exc):
                raise
            time.sleep(_RETRY_DELAY_S)
            try:
                response = self._generate_once(
                    prompt, system=system, schema=schema, temperature=temperature
                )
            except Exception as retry_exc:
                raise RuntimeError(
                    f"Gemini call failed twice ({self._model}): "
                    f"first attempt: {exc}; retry: {retry_exc}"
                ) from retry_exc
        latency_ms = int((time.monotonic() - started) * 1000)
        return self._to_result(response, schema, latency_ms)

    def _generate_once(
        self,
        prompt: str,
        *,
        system: str | None,
        schema: type[BaseModel] | None,
        temperature: float | None,
    ):
        config_kwargs: dict = {}
        if system is not None:
            config_kwargs["system_instruction"] = system
        if temperature is not None:
            config_kwargs["temperature"] = temperature
        if schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = schema
        config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None
        return self._client.models.generate_content(
            model=self._model, contents=prompt, config=config
        )

    @staticmethod
    def _to_result(response, schema: type[BaseModel] | None, latency_ms: int) -> LLMResult:
        text = response.text or ""
        parsed = None
        if schema is not None:
            parsed = response.parsed
            if parsed is None:
                # SDK parse gap — validate the raw JSON text ourselves (raises clearly).
                parsed = schema.model_validate_json(text)
        usage = response.usage_metadata
        prompt_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
        completion_tokens = int(getattr(usage, "candidates_token_count", 0) or 0) + int(
            getattr(usage, "thoughts_token_count", 0) or 0
        )
        return LLMResult(
            text=text,
            parsed=parsed,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
        )
