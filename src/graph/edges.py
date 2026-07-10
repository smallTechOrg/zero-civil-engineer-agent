"""Conditional-edge routers per spec/agent.md — pure functions on state."""

from collections.abc import Callable

from graph.state import AgentState


def route_understand(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    if not state.get("in_scope", True):
        return "finalize"
    return "extract"


def route_extract(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    if state.get("missing_critical"):
        return "clarify"
    return "analyse"


def route_on_error(next_node: str) -> Callable[[AgentState], str]:
    """Error → handle_error, else continue to `next_node`."""

    def _route(state: AgentState) -> str:
        return "handle_error" if state.get("error") else next_node

    _route.__name__ = f"route_on_error_to_{next_node}"
    return _route
