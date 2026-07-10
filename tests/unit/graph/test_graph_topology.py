"""Graph assembly — compiles without DB/keys; topology matches spec/agent.md."""

EXPECTED_NODES = {
    "understand", "extract", "clarify", "analyse", "check",
    "draw", "model3d", "review", "finalize", "handle_error",
}


def test_graph_compiles_without_env():
    from graph.agent import compiled_graph
    assert compiled_graph is not None


def test_graph_has_exactly_the_ten_spec_nodes():
    from graph.agent import compiled_graph
    nodes = set(compiled_graph.get_graph().nodes) - {"__start__", "__end__"}
    assert nodes == EXPECTED_NODES


def test_model3d_flows_unconditionally_to_review():
    from graph.agent import compiled_graph
    edges = {
        (e.source, e.target)
        for e in compiled_graph.get_graph().edges
        if not e.conditional
    }
    assert ("model3d", "review") in edges


def test_terminal_nodes_end_the_graph():
    from graph.agent import compiled_graph
    edges = {(e.source, e.target) for e in compiled_graph.get_graph().edges}
    for terminal in ("clarify", "finalize", "handle_error"):
        assert (terminal, "__end__") in edges


def test_entry_point_is_understand():
    from graph.agent import compiled_graph
    edges = {(e.source, e.target) for e in compiled_graph.get_graph().edges}
    assert ("__start__", "understand") in edges
