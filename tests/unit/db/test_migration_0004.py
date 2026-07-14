"""Migration 0004 — adds root_run_id (refinement lineage) to design_runs.

`root_run_id` is a nullable self-referential FK: NULL means the run is its own
record root; a refinement stores the record root's run_id. The chain must reach
0004, existing rows keep root_run_id NULL, and downgrade drops the column while
leaving design_runs intact.
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
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    yield engine, cfg
    engine.dispose()


def _design_run_columns(engine) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns("design_runs")}


def test_upgrade_head_reaches_0004_with_root_run_id(migrated_db):
    engine, cfg = migrated_db
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0004"

    assert "root_run_id" in _design_run_columns(engine)
    tables = set(inspect(engine).get_table_names())
    assert {"sessions", "design_runs", "artifacts", "presets"} <= tables


def test_pre_existing_rows_keep_root_run_id_null(tmp_path, monkeypatch):
    """A row that existed at revision 0003 stays its own record root (NULL)."""
    db_path = tmp_path / "backfill.db"
    monkeypatch.setenv("AGENT_DATABASE_URL", f"sqlite:///{db_path}")
    import config.settings as settings_module

    settings_module._settings = None
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))

    command.upgrade(cfg, "0003")
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        assert "root_run_id" not in _design_run_columns(engine)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO sessions (id, title, created_at, updated_at) "
                              "VALUES ('s1', 't', '2026-01-01', '2026-01-01')"))
            conn.execute(text(
                "INSERT INTO design_runs (id, session_id, prompt, status, component_type, "
                "prompt_tokens, completion_tokens, cost_usd, started_at) "
                "VALUES ('r1', 's1', 'p', 'completed', 'box_culvert', 0, 0, 0.0, '2026-01-01')"
            ))

        command.upgrade(cfg, "0004")
        with engine.connect() as conn:
            value = conn.execute(
                text("SELECT root_run_id FROM design_runs WHERE id = 'r1'")
            ).scalar_one()
        assert value is None
    finally:
        engine.dispose()


def test_downgrade_removes_root_run_id(migrated_db):
    engine, cfg = migrated_db
    command.downgrade(cfg, "0003")
    assert "root_run_id" not in _design_run_columns(engine)
    assert "design_runs" in inspect(engine).get_table_names()
