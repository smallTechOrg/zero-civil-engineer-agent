"""Migration 0002 — creates the culvert schema, drops legacy runs, seeds the default preset."""

import json
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


def test_upgrade_creates_culvert_tables_and_drops_runs(migrated_db):
    engine, _ = migrated_db
    tables = set(inspect(engine).get_table_names())
    assert {"sessions", "design_runs", "artifacts", "presets"} <= tables
    assert "runs" not in tables


def test_upgrade_seeds_default_preset(migrated_db):
    engine, _ = migrated_db
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT name, is_default, values_json FROM presets")
        ).fetchall()
    assert len(rows) == 1
    name, is_default, values_json = rows[0]
    assert name == "IR standard defaults"
    assert bool(is_default) is True
    assert json.loads(values_json) == {
        "concrete_grade": "M30",
        "steel_grade": "Fe500",
        "clear_cover_mm": 50,
        "soil_unit_weight_kn_m3": 18.0,
        "angle_of_friction_deg": 30.0,
        "formation_width_m": 6.85,
        "side_slope_h_per_v": 2.0,
        "haunch_mm": 150,
    }


def test_downgrade_restores_legacy_schema(migrated_db):
    engine, cfg = migrated_db
    command.downgrade(cfg, "0001")
    tables = set(inspect(engine).get_table_names())
    assert "runs" in tables
    assert not {"sessions", "design_runs", "artifacts", "presets"} & tables
