"""Graph assembly per spec/agent.md — the fixed ten-node pipeline, no checkpointer."""

from langgraph.graph import END, StateGraph

from graph.edges import route_extract, route_on_error, route_understand
from graph.nodes import (
    analyse,
    check,
    clarify,
    draw,
    extract,
    finalize,
    handle_error,
    model3d,
    review,
    understand,
)
from graph.state import AgentState


def _build_graph():
    graph = StateGraph(AgentState)

    for name, fn in [
        ("understand", understand),
        ("extract", extract),
        ("clarify", clarify),
        ("analyse", analyse),
        ("check", check),
        ("draw", draw),
        ("model3d", model3d),
        ("review", review),
        ("finalize", finalize),
        ("handle_error", handle_error),
    ]:
        graph.add_node(name, fn)

    graph.set_entry_point("understand")

    graph.add_conditional_edges(
        "understand",
        route_understand,
        {"handle_error": "handle_error", "finalize": "finalize", "extract": "extract"},
    )
    graph.add_conditional_edges(
        "extract",
        route_extract,
        {"handle_error": "handle_error", "clarify": "clarify", "analyse": "analyse"},
    )
    graph.add_conditional_edges(
        "analyse", route_on_error("check"), {"handle_error": "handle_error", "check": "check"}
    )
    graph.add_conditional_edges(
        "check", route_on_error("draw"), {"handle_error": "handle_error", "draw": "draw"}
    )
    graph.add_conditional_edges(
        "draw",
        route_on_error("model3d"),
        {"handle_error": "handle_error", "model3d": "model3d"},
    )
    graph.add_edge("model3d", "review")  # non-fatal: model3d never errors the run
    graph.add_conditional_edges(
        "review",
        route_on_error("finalize"),
        {"handle_error": "handle_error", "finalize": "finalize"},
    )

    graph.add_edge("clarify", END)
    graph.add_edge("finalize", END)
    graph.add_edge("handle_error", END)

    return graph.compile()  # no checkpointer — clarify is a terminal needs_input run


compiled_graph = _build_graph()
