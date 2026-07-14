"""Conditional-edge routing per spec/agent.md — fake states, no LLM, no DB."""

from graph.edges import route_extract, route_on_error, route_understand


def test_happy_path_routes_through_the_full_pipeline_in_order():
    clean = {"in_scope": True, "missing_critical": [], "error": None}
    assert route_understand(clean) == "extract"
    assert route_extract(clean) == "analyse"
    assert route_on_error("check")(clean) == "check"
    assert route_on_error("draw")(clean) == "draw"
    assert route_on_error("model3d")(clean) == "model3d"
    assert route_on_error("finalize")(clean) == "finalize"


def test_understand_error_routes_to_handle_error():
    assert route_understand({"error": "gemini down", "in_scope": True}) == "handle_error"


def test_understand_out_of_scope_routes_to_finalize():
    assert route_understand({"in_scope": False, "error": None}) == "finalize"


def test_extract_error_routes_to_handle_error():
    assert route_extract({"error": "bad json", "missing_critical": []}) == "handle_error"


def test_extract_missing_critical_routes_to_clarify():
    state = {"error": None, "missing_critical": ["clear_span_m"]}
    assert route_extract(state) == "clarify"


def test_error_beats_missing_critical_in_extract_routing():
    state = {"error": "boom", "missing_critical": ["clear_span_m"]}
    assert route_extract(state) == "handle_error"


def test_extract_invalid_fields_routes_to_clarify():
    # Out-of-range / invalid-enum values become a clarification, not a failure.
    state = {"error": None, "missing_critical": [], "invalid_fields": ["span_m"]}
    assert route_extract(state) == "clarify"


def test_error_beats_invalid_fields_in_extract_routing():
    state = {"error": "boom", "invalid_fields": ["span_m"]}
    assert route_extract(state) == "handle_error"


def test_route_on_error_sends_any_error_to_handle_error():
    assert route_on_error("draw")({"error": "sizing failed"}) == "handle_error"
