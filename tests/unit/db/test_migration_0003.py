"""Migration 0003 — adds component_type + type_summary_json to design_runs.

Expansion Phase 1: the schema stays component-agnostic; existing rows backfill
`component_type` to `box_culvert`. No table is dropped. The chain must reach
0003 and round-trip on downgrade.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def migrated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "migration.db"
    monkeypatch.setenv("AGENT_DATABASE_URL", f"sqlite:///{db_path}")

    import config.settings as settings_module

    settings_module._settings = None

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    # Pin to 0003: this suite asserts the state AT revision 0003 specifically
    # (later migrations advance `head`, e.g. 0004 refinement lineage).
    command.upgrade(cfg, "0003")

    engine = create_engine(f"sqlite:///{db_path}")
    yield engine, cfg
    engine.dispose()


def _design_run_columns(engine) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns("design_runs")}


def test_upgrade_head_reaches_0003_with_new_columns(migrated_db):
    engine, cfg = migrated_db
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0003"

    columns = _design_run_columns(engine)
    assert {"component_type", "type_summary_json"} <= columns
    # The rest of the schema is untouched (no table dropped).
    tables = set(inspect(engine).get_table_names())
    assert {"sessions", "design_runs", "artifacts", "presets"} <= tables


def test_component_type_backfills_pre_existing_rows_to_box_culvert(tmp_path, monkeypatch):
    """A legacy row that existed at revision 0002 (before the component column)
    is backfilled to box_culvert by the 0003 upgrade."""
    db_path = tmp_path / "backfill.db"
    monkeypatch.setenv("AGENT_DATABASE_URL", f"sqlite:///{db_path}")
    import config.settings as settings_module

    settings_module._settings = None
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))

    # Stop at 0002 (no component_type column yet) and seed a legacy run.
    command.upgrade(cfg, "0002")
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        assert "component_type" not in _design_run_columns(engine)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO sessions (id, title, created_at, updated_at) "
                              "VALUES ('s1', 't', '2026-01-01', '2026-01-01')"))
            conn.execute(text(
                "INSERT INTO design_runs (id, session_id, prompt, status, prompt_tokens, "
                "completion_tokens, cost_usd, started_at) "
                "VALUES ('r1', 's1', 'p', 'completed', 0, 0, 0.0, '2026-01-01')"
            ))

        # Now upgrade to 0003 — the add-column server_default backfills the row.
        command.upgrade(cfg, "0003")
        with engine.connect() as conn:
            value = conn.execute(
                text("SELECT component_type FROM design_runs WHERE id = 'r1'")
            ).scalar_one()
        assert value == "box_culvert"
    finally:
        engine.dispose()


def test_downgrade_removes_the_two_columns(migrated_db):
    engine, cfg = migrated_db
    command.downgrade(cfg, "0002")
    columns = _design_run_columns(engine)
    assert "component_type" not in columns
    assert "type_summary_json" not in columns
    # design_runs itself survives (only the two columns are dropped).
    assert "design_runs" in inspect(engine).get_table_names()
