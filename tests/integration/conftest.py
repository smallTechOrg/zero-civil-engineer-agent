"""Integration fixtures — real Gemini key from .env, isolated tmp DB + artifacts dir.

The tmp SQLite DB comes from the root conftest's autouse `_isolated_db` (same
driver as production — SQLite IS production for this local demo). This conftest
adds: settings isolation (tmp artifacts dir), the real-key guard, sibling-slice
guards (db models / drawing), and run helpers.
"""

import importlib.util
import threading

import pytest

import config.settings as settings_module
from observability import progress


@pytest.fixture(autouse=True)
def _integration_settings(tmp_path):
    """Real .env-backed settings with an isolated artifacts dir per test."""
    settings = settings_module.Settings(artifacts_dir=str(tmp_path / "artifacts"))
    settings_module._settings = settings
    yield settings
    settings_module._settings = None


@pytest.fixture
def require_gemini(_integration_settings):
    if not _integration_settings.gemini_api_key:
        pytest.skip("AGENT_GEMINI_API_KEY not set in .env — integration tests call the real Gemini API")


@pytest.fixture
def db_ready():
    """Guard for the concurrently-built p1-api-db slice (db.models per spec/data.md)."""
    import db.models as models

    for name in ("SessionRow", "DesignRunRow", "ArtifactRow", "PresetRow"):
        if not hasattr(models, name):
            pytest.skip(f"db.models.{name} not yet landed — pending the p1-api-db slice")


@pytest.fixture
def drawing_ready():
    """Guard for the concurrently-built p1-drawing slice (drawing.ga.generate_ga)."""
    if importlib.util.find_spec("drawing") is None or importlib.util.find_spec("drawing.ga") is None:
        pytest.skip("drawing.ga not yet landed — pending the p1-drawing slice")


@pytest.fixture
def make_session(db_ready):
    def _make(title: str = "integration test session") -> str:
        from db.models import SessionRow
        from db.session import create_db_session

        with create_db_session() as session:
            row = SessionRow(title=title)
            session.add(row)
            session.flush()
            return row.id

    return _make


@pytest.fixture
def run_and_wait():
    """Start a design run and drain its progress stream until the terminal event."""

    def _run(
        session_id: str, prompt: str, preset_id: str | None = None, timeout: float = 300.0
    ) -> tuple[str, list[dict]]:
        from graph.runner import start_design_run

        run_id = start_design_run(session_id, prompt, preset_id)
        events: list[dict] = []

        def consume() -> None:
            events.extend(progress.stream(run_id))

        consumer = threading.Thread(target=consume, daemon=True)
        consumer.start()
        consumer.join(timeout)
        if consumer.is_alive():
            pytest.fail(
                f"run {run_id} did not finish within {timeout}s — "
                f"events so far: {[e['event'] for e in events]}"
            )
        return run_id, events

    return _run


@pytest.fixture
def get_run():
    def _get(run_id: str) -> dict:
        from db.models import DesignRunRow
        from db.session import create_db_session

        columns = (
            "id", "session_id", "prompt", "status", "plan_text", "scope_message",
            "clarification_question", "params_json", "assumptions_json",
            "warnings_json", "steps_json", "checks_json", "checklist_json",
            "verdict", "suggestions_json", "prompt_tokens", "completion_tokens",
            "cost_usd", "error_message", "started_at", "completed_at", "duration_ms",
        )
        with create_db_session() as session:
            row = session.get(DesignRunRow, run_id)
            assert row is not None, f"run row {run_id} missing"
            return {column: getattr(row, column) for column in columns}

    return _get


@pytest.fixture
def get_artifacts():
    def _get(run_id: str) -> list[dict]:
        from db.models import ArtifactRow
        from db.session import create_db_session

        with create_db_session() as session:
            rows = (
                session.query(ArtifactRow)
                .filter(ArtifactRow.run_id == run_id)
                .order_by(ArtifactRow.created_at.asc())
                .all()
            )
            return [
                {
                    "kind": row.kind,
                    "filename": row.filename,
                    "mime": row.mime,
                    "size_bytes": row.size_bytes,
                }
                for row in rows
            ]

    return _get
