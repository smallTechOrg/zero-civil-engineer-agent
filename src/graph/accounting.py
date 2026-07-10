"""Token/cost accounting — env-configured Gemini rates (spec/architecture.md)."""

from config.settings import get_settings


def run_totals(token_usage: list[dict]) -> tuple[int, int]:
    """Sum (prompt_tokens, completion_tokens) over this run's LLM calls."""
    prompt_tokens = sum(int(call.get("prompt_tokens", 0)) for call in token_usage)
    completion_tokens = sum(int(call.get("completion_tokens", 0)) for call in token_usage)
    return prompt_tokens, completion_tokens


def compute_cost_usd(prompt_tokens: int, completion_tokens: int) -> float:
    settings = get_settings()
    return (
        prompt_tokens / 1_000_000 * settings.gemini_input_cost_per_mtok
        + completion_tokens / 1_000_000 * settings.gemini_output_cost_per_mtok
    )
