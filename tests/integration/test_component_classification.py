"""Component classification — real Gemini auto-detect + snapshot exposure.

Expansion Phase 1: `understand` classifies the prompt against the registered
components. The canonical culvert prompt must classify `box_culvert`, the run
must persist it, and the snapshot endpoint must expose `component_type` +
`type_summary` (spec/api.md GET /api/designs/{run_id}). The out-of-scope and
picker-override / unknown-type paths are covered by test_guardrails.py and the
unit API suite; this pins the auto-detect happy path end to end.
"""

from fastapi.testclient import TestClient

CULVERT_PROMPT = (
    "single box culvert, 4 m clear span, 3 m height, 2.5 m cushion, "
    "BG single line, 25t loading"
)

# The canonical retaining-wall prompt (retaining-wall.md SC) — SBC + backfill φ +
# track surcharge are unambiguous retaining-wall vocabulary, NOT culvert.
RETAINING_WALL_PROMPT = (
    "design a 5 m high RCC cantilever retaining wall, SBC 200 kN/m2, "
    "BG single-line track surcharge, backfill phi 30 degrees"
)


def test_culvert_prompt_auto_detects_box_culvert_and_snapshot_exposes_it(
    require_gemini, drawing_ready, make_session, run_and_wait, get_run,
):
    session_id = make_session()

    run_id, events = run_and_wait(session_id, CULVERT_PROMPT)

    assert events[-1]["data"]["status"] == "completed"

    # DB audit trail records the classified component type.
    row = get_run(run_id)
    assert row["status"] == "completed"

    from db.models import DesignRunRow
    from db.session import create_db_session

    with create_db_session() as session:
        design = session.get(DesignRunRow, run_id)
        assert design.component_type == "box_culvert"
        assert design.type_summary_json is not None  # member-check summary persisted

    # The snapshot exposes component_type + the component's type_summary.
    from api import app

    with TestClient(app) as client:
        snapshot = client.get(f"/api/designs/{run_id}").json()["data"]
    assert snapshot["component_type"] == "box_culvert"
    assert snapshot["type_summary"]["kind"] == "member_check"
    assert snapshot["type_summary"]["verdict"] in {
        "recommended_for_approval", "return_for_revision",
    }


def test_retaining_wall_prompt_auto_detects_rcc_cantilever_retaining_wall(
    require_gemini, drawing_ready, make_session, run_and_wait, get_run,
):
    """The canonical RW prompt must classify rcc_cantilever_retaining_wall — the
    silent box_culvert misclassification regression (understand discriminator)."""
    session_id = make_session()

    run_id, events = run_and_wait(session_id, RETAINING_WALL_PROMPT)

    assert events[-1]["data"]["status"] == "completed"

    from db.models import DesignRunRow
    from db.session import create_db_session

    with create_db_session() as session:
        design = session.get(DesignRunRow, run_id)
        # The heart of the fix: NOT silently classified/defaulted to box_culvert.
        assert design.component_type == "rcc_cantilever_retaining_wall"
