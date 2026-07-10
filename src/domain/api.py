"""Request/response DTOs for the REST API — the wire shapes from spec/api.md.

Timestamps are ISO-8601 strings on the wire; `*_json` DB columns are parsed
into the typed fields here at the API boundary.
"""

from typing import Any

from pydantic import BaseModel, Field


# --- Requests -----------------------------------------------------------------


class SessionCreateRequest(BaseModel):
    title: str | None = None


class DesignSubmitRequest(BaseModel):
    # Default "" so a missing prompt takes the same EMPTY_PROMPT path as a blank one.
    prompt: str = ""
    preset_id: str | None = None


# --- Responses ----------------------------------------------------------------


class SessionCreated(BaseModel):
    session_id: str
    title: str
    created_at: str


class SessionSummary(BaseModel):
    session_id: str
    title: str
    created_at: str
    run_count: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_cost_usd: float


class DesignSubmitted(BaseModel):
    run_id: str
    status: str
    events_url: str
    snapshot_url: str


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0


class ArtefactInfo(BaseModel):
    kind: str
    filename: str
    url: str
    size_bytes: int


class RunSnapshot(BaseModel):
    run_id: str
    session_id: str
    prompt: str
    status: str
    plan_text: str | None = None
    scope_message: str | None = None
    clarification_question: str | None = None
    params: dict[str, Any] | None = None
    assumptions: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    checks: list[dict[str, Any]] = Field(default_factory=list)
    checklist: list[dict[str, Any]] = Field(default_factory=list)
    verdict: str | None = None
    suggestions: list[str] = Field(default_factory=list)
    artefacts: list[ArtefactInfo] = Field(default_factory=list)
    tokens: TokenUsage = Field(default_factory=TokenUsage)
    error_message: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None


class RunListItem(BaseModel):
    run_id: str
    session_id: str
    prompt: str
    status: str
    verdict: str | None = None
    params_summary: str
    cost_usd: float
    started_at: str | None = None
    duration_ms: int | None = None


class PresetInfo(BaseModel):
    preset_id: str
    name: str
    is_default: bool
    values: dict[str, Any]
