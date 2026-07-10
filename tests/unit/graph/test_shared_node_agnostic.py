"""Shared-node component-agnosticism guards (component-registry SC#6) + the
out-of-scope tagging fix.

- `_failing_members` must resolve member labels through the dispatched module's
  interface (`module.member_labels`), NOT a direct `engine.checks` import, yet
  still render the culvert's human-readable labels.
- An out-of-scope run designs nothing, so `finalize` must NOT persist the
  picker-seeded `component_type` it never designed (architecture.md); it resets
  to the schema's neutral default sentinel (`box_culvert`, since the column is
  non-nullable) rather than tagging a real designed component like the wall.
"""

import inspect
import time
from types import SimpleNamespace

import components  # noqa: F401 — populates the registry at import
from components import registry
from graph.nodes import _failing_members, finalize
from graph.persistence import create_run_row
from graph.steps import initial_steps
from observability import progress


def test_failing_members_source_has_no_direct_engine_import():
    """SC#6: the shared node must not import a component-specific engine."""
    # Strip the docstring — assert on executable lines only (the docstring
    # legitimately *names* the rule it enforces).
    src = inspect.getsource(_failing_members)
    body = src[src.index('"""', src.index('"""') + 3) + 3 :]
    assert "import engine" not in body
    assert "from engine" not in body
    assert "engine.checks" not in body


def test_failing_members_renders_culvert_labels_via_the_module():
    module = registry.get("box_culvert")
    failing = [
        SimpleNamespace(member="top_slab", status="FAIL"),
        SimpleNamespace(member="wall", status="FAIL"),
    ]

    rendered = _failing_members(module, failing)

    assert rendered == "Top slab, Wall"


def test_failing_members_renders_retaining_wall_labels_via_the_module():
    module = registry.get("rcc_cantilever_retaining_wall")
    failing = [SimpleNamespace(member="stem", status="FAIL")]

    assert _failing_members(module, failing) == "Stem"


def test_out_of_scope_run_does_not_persist_a_component_type():
    session_id = "unit-oos-session"
    run_id = create_run_row(session_id, "design a suspension bridge")
    progress.register(run_id)
    # A picker choice seeded rcc into state, but the request resolved out of scope.
    state = {
        "run_id": run_id,
        "session_id": session_id,
        "component_type": "rcc_cantilever_retaining_wall",
        "in_scope": False,
        "scope_message": "That is outside the platform's current scope.",
        "steps": initial_steps(),
        "started_monotonic": time.monotonic(),
        "token_usage": [],
    }

    updates = finalize(state)

    assert updates["status"] == "out_of_scope"

    from db.models import DesignRunRow
    from db.session import create_db_session

    with create_db_session() as session:
        row = session.get(DesignRunRow, run_id)
        assert row.status == "out_of_scope"
        # Reset to the neutral sentinel — the picker-seeded wall was NEVER
        # designed, so it must not be tagged on an out-of-scope run.
        assert row.component_type != "rcc_cantilever_retaining_wall"
        assert row.component_type == "box_culvert"
