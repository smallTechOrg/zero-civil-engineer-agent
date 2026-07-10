"""DB layer — roundtrips, defaults, and relationships for the four-table schema."""

import json

from sqlalchemy.orm import Session

from db.models import ArtifactRow, DesignRunRow, PresetRow, SessionRow


def test_session_row_roundtrip(_isolated_db):
    with Session(_isolated_db) as s:
        row = SessionRow(title="Culvert study")
        s.add(row)
        s.commit()
        session_id = row.id

    with Session(_isolated_db) as s:
        fetched = s.get(SessionRow, session_id)
        assert fetched.title == "Culvert study"
        assert fetched.created_at is not None
        assert fetched.updated_at is not None


def test_session_title_defaults_to_empty_placeholder(_isolated_db):
    with Session(_isolated_db) as s:
        row = SessionRow()
        s.add(row)
        s.commit()
        assert row.title == ""


def test_design_run_defaults_and_roundtrip(_isolated_db):
    with Session(_isolated_db) as s:
        sess = SessionRow(title="t")
        s.add(sess)
        s.flush()
        run = DesignRunRow(session_id=sess.id, prompt="4 m box culvert")
        s.add(run)
        s.commit()
        run_id = run.id

    with Session(_isolated_db) as s:
        run = s.get(DesignRunRow, run_id)
        assert run.status == "running"
        assert run.component_type == "box_culvert"  # default (migration 0003)
        assert run.type_summary_json is None
        assert run.prompt_tokens == 0
        assert run.completion_tokens == 0
        assert run.cost_usd == 0.0
        assert run.params_json is None
        assert run.verdict is None
        assert run.started_at is not None
        assert run.completed_at is None
        assert run.duration_ms is None


def test_design_run_records_component_type_and_type_summary(_isolated_db):
    with Session(_isolated_db) as s:
        sess = SessionRow()
        s.add(sess)
        s.flush()
        run = DesignRunRow(
            session_id=sess.id,
            prompt="5 m retaining wall for a cutting",
            component_type="rcc_cantilever_retaining_wall",
            type_summary_json=json.dumps({"fos_overturning": 2.4, "fos_sliding": 1.7}),
        )
        s.add(run)
        s.commit()
        run_id = run.id

    with Session(_isolated_db) as s:
        run = s.get(DesignRunRow, run_id)
        assert run.component_type == "rcc_cantilever_retaining_wall"
        assert json.loads(run.type_summary_json)["fos_overturning"] == 2.4


def test_design_run_json_columns_roundtrip(_isolated_db):
    params = {"clear_span_m": 4.0, "clear_height_m": 3.0, "cushion_m": 2.5}
    with Session(_isolated_db) as s:
        sess = SessionRow()
        s.add(sess)
        s.flush()
        run = DesignRunRow(
            session_id=sess.id,
            prompt="p",
            status="completed",
            params_json=json.dumps(params),
            steps_json=json.dumps([{"name": "Draw", "status": "done"}]),
        )
        s.add(run)
        s.commit()
        run_id = run.id

    with Session(_isolated_db) as s:
        run = s.get(DesignRunRow, run_id)
        assert json.loads(run.params_json) == params
        assert json.loads(run.steps_json)[0]["name"] == "Draw"


def test_artifact_row_belongs_to_run(_isolated_db):
    with Session(_isolated_db) as s:
        sess = SessionRow()
        s.add(sess)
        s.flush()
        run = DesignRunRow(session_id=sess.id, prompt="p")
        s.add(run)
        s.flush()
        art = ArtifactRow(
            run_id=run.id, kind="ga_dxf", filename="ga.dxf", mime="image/vnd.dxf", size_bytes=42
        )
        s.add(art)
        s.commit()
        art_id = art.id
        run_id = run.id

    with Session(_isolated_db) as s:
        art = s.get(ArtifactRow, art_id)
        assert art.run_id == run_id
        assert art.kind == "ga_dxf"
        assert art.size_bytes == 42
        assert art.created_at is not None


def test_preset_row_roundtrip(_isolated_db):
    with Session(_isolated_db) as s:
        row = PresetRow(
            name="IR standard defaults", is_default=True, values_json=json.dumps({"clear_cover_mm": 50})
        )
        s.add(row)
        s.commit()
        preset_id = row.id

    with Session(_isolated_db) as s:
        row = s.get(PresetRow, preset_id)
        assert row.is_default is True
        assert json.loads(row.values_json) == {"clear_cover_mm": 50}


def test_uuid_pks_unique(_isolated_db):
    with Session(_isolated_db) as s:
        rows = [SessionRow() for _ in range(3)]
        s.add_all(rows)
        s.commit()
        ids = [r.id for r in rows]
    assert len(set(ids)) == 3
