from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(default="sqlite:///./data/agent.db")
    log_level: str = Field(default="INFO")

    # Server bind port for `uv run python -m src` (host stays 127.0.0.1).
    port: int = Field(default=8001)

    # Artefact files (DXF/SVG/JSON/...) live under <artifacts_dir>/<run_id>/.
    artifacts_dir: str = Field(default="data/artifacts")

    # LLM model — Gemini is the sole provider for ALL agent steps
    # (hardcoded in src/llm/client.py per spec/architecture.md).
    llm_model: str = Field(default="gemini-2.5-pro")

    # Gemini API key — required at runtime; lives only in .env (never in code).
    gemini_api_key: str = Field(default="")

    # Gemini 2.5 Pro pricing per million tokens (USD) — env-overridable so a
    # price change never needs a code change (spec/architecture.md).
    gemini_input_cost_per_mtok: float = Field(default=1.25)
    gemini_output_cost_per_mtok: float = Field(default=10.0)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
