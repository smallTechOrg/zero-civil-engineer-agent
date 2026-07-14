"""Graph assembly — compiles without DB/keys; topology matches spec/agent.md."""

EXPECTED_NODES = {
    "understand", "seed_params", "extract", "clarify", "analyse", "check",
    "draw", "model3d", "review", "finalize", "handle_error",
}


def test_graph_compiles_without_env():
    from graph.agent import compiled_graph
    assert compiled_graph is not None


def test_graph_has_exactly_the_spec_nodes():
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


def test_conditional_entry_routes_nl_to_understand_and_params_to_seed_params():
    from graph.agent import compiled_graph
    edges = {(e.source, e.target) for e in compiled_graph.get_graph().edges}
    # NL runs enter `understand` (byte-identical); params-direct enter `seed_params`.
    assert ("__start__", "understand") in edges
    assert ("__start__", "seed_params") in edges


def test_seed_params_flows_to_analyse():
    from graph.agent import compiled_graph
    edges = {
        (e.source, e.target)
        for e in compiled_graph.get_graph().edges
        if not e.conditional
    }
    assert ("seed_params", "analyse") in edges
