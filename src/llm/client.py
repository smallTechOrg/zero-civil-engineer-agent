"""LLM access for graph nodes — nodes call `LLMClient.generate()`, never the SDK.

Gemini only: spec/architecture.md pins `gemini-2.5-pro` for ALL agent nodes.
The key comes from `.env` (`AGENT_GEMINI_API_KEY`) via settings.
"""

from typing import Any

from pydantic import BaseModel

from config.settings import get_settings


class LLMResult(BaseModel):
    """One LLM call's outcome: text or parsed schema instance, plus usage."""

    text: str
    parsed: Any | None = None       # schema instance when a response schema was given
    prompt_tokens: int
    completion_tokens: int          # includes thinking tokens (they are billed as output)
    latency_ms: int


class LLMClient:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.gemini_api_key:
            raise RuntimeError(
                "AGENT_GEMINI_API_KEY is not set in .env — the agent requires a "
                "Gemini API key (see .env.example)."
            )
        from llm.providers.gemini import GeminiProvider

        self._provider = GeminiProvider(
            api_key=settings.gemini_api_key,
            model=settings.llm_model or GeminiProvider.DEFAULT_MODEL,
        )

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        schema: type[BaseModel] | None = None,
        temperature: float | None = None,
    ) -> LLMResult:
        """Run one Gemini call; with `schema`, returns the parsed model in `.parsed`."""
        return self._provider.generate(
            prompt, system=system, schema=schema, temperature=temperature
        )
