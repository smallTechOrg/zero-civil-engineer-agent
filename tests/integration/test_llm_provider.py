"""Real-Gemini provider tests — structured output, usage capture, prompt quality.

These hit the live API with the key from .env and need neither the DB nor the
drawing slice, so they gate the LLM extension independently.
"""

from graph.extraction import ExtractionResult
from graph.nodes import UnderstandResult, _load_prompt
from llm.client import LLMClient

CANONICAL_PROMPT = (
    "single box culvert, 4 m clear span, 3 m height, 2.5 m cushion, "
    "BG single line, 25t loading"
)


def test_structured_extraction_parses_the_canonical_prompt(require_gemini):
    result = LLMClient().generate(
        f"Current request: {CANONICAL_PROMPT}",
        system=_load_prompt("extract.md"),
        schema=ExtractionResult,
        temperature=0.0,
    )

    parsed = result.parsed
    assert isinstance(parsed, ExtractionResult)
    assert parsed.clear_span_m == 4.0
    assert parsed.clear_height_m == 3.0
    assert parsed.cushion_m == 2.5
    assert parsed.gauge == "BG"
    assert parsed.tracks == 1
    assert parsed.loading_standard == "25t-2008"
    # Usage capture — the token/cost display depends on these being real.
    assert result.prompt_tokens > 0
    assert result.completion_tokens > 0
    assert result.latency_ms > 0


def test_scope_gate_accepts_the_canonical_prompt_with_a_plan(require_gemini):
    result = LLMClient().generate(
        f"Current request: {CANONICAL_PROMPT}",
        system=_load_prompt("understand.md"),
        schema=UnderstandResult,
        temperature=0.2,
    )

    parsed = result.parsed
    assert parsed.in_scope is True
    assert parsed.plan and len(parsed.plan) > 20


def test_scope_gate_rejects_a_suspension_bridge_gracefully(require_gemini):
    result = LLMClient().generate(
        "Current request: design a suspension bridge",
        system=_load_prompt("understand.md"),
        schema=UnderstandResult,
        temperature=0.2,
    )

    parsed = result.parsed
    assert parsed.in_scope is False
    assert parsed.scope_message and "culvert" in parsed.scope_message.lower()
