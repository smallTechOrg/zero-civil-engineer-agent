import pytest


@pytest.fixture(autouse=True)
def _reset_settings_singleton():
    import config.settings as m
    m._settings = None
    yield
    m._settings = None


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from db.models import Base
    import db.session as session_module

    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(session_module, "_engine", engine)
    monkeypatch.setattr(session_module, "_SessionLocal", factory)
    monkeypatch.setattr(session_module, "init_db", lambda: None)
    yield engine
    engine.dispose()


@pytest.fixture
def _require_llm_key():
    """Skip if the Gemini key is not set — the project's only LLM provider."""
    from config.settings import get_settings
    if not get_settings().gemini_api_key:
        pytest.skip("No LLM key set in .env (AGENT_GEMINI_API_KEY)")


@pytest.fixture
def artifacts_dir(tmp_path, monkeypatch):
    """Isolated artefact root — the lifespan and artifact routes read it from settings."""
    root = tmp_path / "artifacts"
    monkeypatch.setenv("AGENT_ARTIFACTS_DIR", str(root))
    return root


@pytest.fixture
def api_client(_isolated_db, artifacts_dir):
    """FastAPI test client with isolated DB and artefact dir."""
    from fastapi.testclient import TestClient
    from api import app
    with TestClient(app) as client:
        yield client
