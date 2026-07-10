"""LangGraph agent state per spec/agent.md — one design run's in-progress data."""

from typing import TypedDict


class AgentState(TypedDict, total=False):
    # Identity
    run_id: str
    session_id: str

    # Input
    user_prompt: str                 # this turn's NL request
    component_type: str              # registry type_id — set by `understand` (classify) or the picker
    requested_component: str | None  # explicit picker choice from the API (overrides auto-detect)
    messages: list[dict]             # session history: [{role, content}] incl. prior clarification Q/A
    prior_params: dict | None        # accepted params from the session's last completed run
    preset_values: dict              # defaults preset applied to this run

    # Understand
    in_scope: bool
    scope_message: str | None
    plan_text: str

    # Extract
    params: dict | None              # validated CulvertParams (merged)
    missing_critical: list[str]
    warnings: list[str]
    clarification_question: str | None

    # Deterministic pipeline (populated progressively)
    geometry: dict | None            # BoxGeometry
    assumptions: list[dict]          # Assumption records (value + source)
    trail_segments: list[list[dict]] # CalcStep segments in engine order (sizing, analysis)
    analysis: dict | None            # AnalysisResult
    checks: list[dict]               # full CheckResult rows (api.md keys + provenance)
    fe_comparison: dict | None       # FeComparison — FE-vs-closed-form diff
    checklist: list[dict]            # 12-item proof-check results (full item dicts)
    verdict: str | None              # "recommended_for_approval" | "return_for_revision"
    type_summary: dict | None        # component-specific summary from module.type_summary
    artefacts: list[dict]            # [{kind, filename}] as written
    suggestions: list[str]           # Phase 3

    # Accounting
    token_usage: list[dict]          # per-LLM-call {node, prompt_tokens, completion_tokens, latency_ms}

    # Step tracker (steps_json audit + SSE step events)
    steps: list[dict]                # per UI step {name, status, detail, started_at, ended_at}
    started_monotonic: float         # time.monotonic() at run start — drives elapsed_ms/duration_ms

    # Control
    status: str                      # running | needs_input | out_of_scope | completed | failed
    error: str | None
