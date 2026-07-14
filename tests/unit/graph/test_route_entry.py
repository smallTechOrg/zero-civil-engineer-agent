"""The conditional entry router — params-direct vs natural-language."""

from graph.edges import route_entry


def test_params_direct_routes_to_seed_params():
    assert route_entry({"params_direct": True}) == "seed_params"


def test_natural_language_routes_to_understand():
    assert route_entry({"params_direct": False}) == "understand"


def test_missing_flag_defaults_to_understand():
    # A run with no params_direct flag is a normal NL run — byte-identical entry.
    assert route_entry({}) == "understand"
