"""create_run_row refinement-lineage resolution.

An original / new design is its own record root (root_run_id NULL). A refine
(parent_run_id given) joins the parent's RECORD ROOT — so v3 points at v1, never
at v2. An unknown parent_run_id degrades gracefully to a new record (NULL), never
a crash.
"""

from sqlalchemy.orm import Session

from db.models import DesignRunRow, SessionRow
from graph import persistence


def _new_session(engine) -> str:
    with Session(engine) as s:
        row = SessionRow(title="lineage")
        s.add(row)
        s.commit()
        return row.id


def _root_of(engine, run_id: str) -> str | None:
    with Session(engine) as s:
        return s.get(DesignRunRow, run_id).root_run_id


def test_new_design_has_null_root(_isolated_db):
    session_id = _new_session(_isolated_db)
    run_id = persistence.create_run_row(session_id, "design a box culvert")
    assert _root_of(_isolated_db, run_id) is None


def test_refine_points_at_parent_root(_isolated_db):
    session_id = _new_session(_isolated_db)
    v1 = persistence.create_run_row(session_id, "design a box culvert")
    # First refine of an original → root is the original itself.
    v2 = persistence.create_run_row(session_id, "increase cushion", parent_run_id=v1)
    assert _root_of(_isolated_db, v2) == v1
    # Refining v2 (which already belongs to v1's record) still points at v1,
    # keeping every version of the record under a single O(1) root key.
    v3 = persistence.create_run_row(session_id, "add a second cell", parent_run_id=v2)
    assert _root_of(_isolated_db, v3) == v1


def test_unknown_parent_degrades_to_new_record(_isolated_db):
    session_id = _new_session(_isolated_db)
    run_id = persistence.create_run_row(
        session_id, "design a box culvert", parent_run_id="does-not-exist"
    )
    assert _root_of(_isolated_db, run_id) is None
