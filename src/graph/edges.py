"""Conditional-edge routers per spec/agent.md — pure functions on state."""

from collections.abc import Callable

from graph.state import AgentState


def route_entry(state: AgentState) -> str:
    """Conditional entry point: params-direct forms bypass the LLM intake.

    A typed parameter-form submission (`params_direct`) is seeded straight from
    the validated params — it routes to the deterministic `seed_params` node and
    never runs `understand`/`extract`. Every natural-language run routes to
    `understand`, byte-identical to the pre-params-direct graph.
    """
    return "seed_params" if state.get("params_direct") else "understand"


def route_understand(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    if not state.get("in_scope", True):
        return "finalize"
    return "extract"


def route_extract(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    # Missing critical fields OR extracted-but-invalid values both become a
    # clarification the user can answer/refine — never a hard failure.
    if state.get("missing_critical") or state.get("invalid_fields"):
        return "clarify"
    return "analyse"


def route_on_error(next_node: str) -> Callable[[AgentState], str]:
    """Error → handle_error, else continue to `next_node`."""

    def _route(state: AgentState) -> str:
        return "handle_error" if state.get("error") else next_node

    _route.__name__ = f"route_on_error_to_{next_node}"
    return _route
