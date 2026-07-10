# Project Layout — Canonical Structure

All agents built from this boilerplate must follow this layout exactly. The sales-agent repo (`smallTechOrg/sales-agent`) is the canonical reference.

---

## README Requirements (Mandatory)

Every generated project **must** have a README that:

1. **States "all commands run from the repo root"** — the repo root IS the project (no subdirectory to cd into). Put this as a blockquote or bold warning at the very top, before any other content.
2. **Prefixes all commands with `uv run`** — never bare `alembic`, `pytest`, or `python`. Bare commands fail unless the venv is manually activated.
3. **Includes `uv run alembic current` after `upgrade head`** — so the user can verify tables were actually created (blank output = silent failure).
4. **Stays accurate** — every README command must be tested before a phase is marked complete. If a command fails, fix the README before claiming the phase is done.

The README is the first thing a user touches. A wrong README fails the entire build regardless of whether the code works.

---

## Source Code Rule (Non-Negotiable)

**All application source code must live inside `src/`.** Never place HTML, CSS, JavaScript, Python packages, templates, or data files at the repo root.

The repo root is for project-level config only: `pyproject.toml`, `alembic.ini`, `README.md`, `.env.example`, and boilerplate infrastructure (`spec/`, `harness/`, `CLAUDE.md`). If you are about to create an application file at the root, stop and put it in `src/` instead.

This applies to all project types — Python packages, static web apps, TypeScript projects, and any other stack.

---

## Directory Tree

The repo root **is** the agent project. There is no `<agent-slug>/` subdirectory — boilerplate files (`spec/`, `harness/`, `CLAUDE.md`) coexist with project files at the root.

**One package only.** The skeleton ships `src/agent/`. If the spec needs a different package name (e.g. `xyz_agent`), **rename `src/agent/` in place** — never create a second package beside it. `src/xyz/` sitting next to `src/agent/` is always wrong: it duplicates the wired-up baseline instead of extending it, leaving dead code and two sources of truth.

```
<repo root>                           ← repo root IS the agent project
├── src/
│   └── <package>/                    ← Python package (snake_case matches slug)
│       ├── __init__.py               ← __version__ = "0.1.0"
│       ├── api/                      ← FastAPI routers
│       │   ├── __init__.py           ← create_app() factory + lifespan
│       │   ├── _common.py            ← ok(), api_error()
│       │   └── <resource>.py         ← one router per domain entity
│       ├── config/
│       │   ├── __init__.py
│       │   └── settings.py           ← Pydantic BaseSettings with env prefix
│       ├── db/
│       │   ├── __init__.py
│       │   ├── models.py             ← SQLAlchemy 2.0 declarative (Mapped types)
│       │   └── session.py            ← engine + sessionmaker + init_db
│       ├── domain/
│       │   ├── __init__.py           ← re-exports all domain models
│       │   └── <entity>.py           ← Pydantic BaseModel per entity
│       ├── graph/
│       │   ├── __init__.py
│       │   ├── agent.py              ← StateGraph compiled once at startup
│       │   ├── nodes.py              ← node functions: (state) → state
│       │   ├── edges.py              ← conditional routing functions
│       │   ├── state.py              ← AgentState TypedDict
│       │   └── runner.py             ← run_agent() entry point
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── client.py             ← LLMClient wrapper
│       │   └── providers/
│       │       ├── base.py           ← abstract LLMProvider
│       │       ├── factory.py        ← create_llm_client()
│       │       └── anthropic.py      ← default provider
│       ├── tools/                    ← pure functions: (inputs) → domain models
│       │   └── <tool>.py
│       ├── prompts/                  ← LLM prompt templates (.md files)
│       │   └── <name>.md
│       └── observability/
│           ├── __init__.py
│           └── events.py             ← structlog configuration
├── tests/                            ← tests at repo root, NOT inside src/
│   ├── conftest.py                   ← settings singleton reset fixture
│   ├── unit/
│   │   ├── test_smoke.py             ← import pkg; assert __version__
│   │   ├── config/test_settings.py
│   │   ├── db/test_models.py
│   │   ├── domain/test_models.py
│   │   └── graph/test_agent.py       ← graph compiles without env vars
│   ├── integration/
│   │   └── test_pipeline.py          ← real-provider run end-to-end, one DB record, status=completed (+ edge cases / error paths)
│   ├── e2e/                          ← full primary journey against the real LLM/API + live server
│   └── ui/                           ← UI-only projects: rendered content + empty/loading/error states
├── alembic/
│   ├── env.py                        ← reads DB URL from settings; sets target_metadata = Base.metadata
│   ├── script.py.mako                ← REQUIRED — standard mako template; alembic revision fails without it
│   └── versions/0001_initial.py      ← generated by: uv run alembic revision --autogenerate -m "initial"
├── spec/                             ← agent spec files (preserved from boilerplate)
├── harness/                          ← engineering harness (preserved from boilerplate)
├── CLAUDE.md                         ← preserved from boilerplate
├── pyproject.toml
├── alembic.ini
├── .env.example
└── README.md                         ← replaces the boilerplate README
```

**Critical:** `tests/` is at the repo root — **not** inside `src/`. The `pyproject.toml` must have `testpaths = ["tests"]` (not `["src/tests"]`).

---

## Exact File Shapes

### alembic/script.py.mako

This file **must be created manually** — it is not generated by anything. Without it, `alembic revision --autogenerate` fails with `FileNotFoundError`.

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

### Phase 1 alembic sequence (mandatory, in order)

All commands run from the **repo root** (where `alembic.ini` and `pyproject.toml` live).

```bash
# 1. Create the alembic/ directory and files (env.py, alembic.ini, script.py.mako)
# 2. Define all SQLAlchemy models in src/<package>/db/models.py
# 3. Generate the initial migration — requires the DB to be reachable and DATABASE_URL to be set:
uv run alembic revision --autogenerate -m "initial"
# 4. Apply the migration:
uv run alembic upgrade head
# 5. Verify — this command must show the revision hash, not blank output:
uv run alembic current
```

**Phase 1 is not complete until `alembic current` shows a revision.** Blank output from `alembic current` means no migration was applied.

### config/settings.py

```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",   # replace APP_ with your agent's prefix
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(...)
    # Filled from .env (the single manual user step, requested at intake) and
    # required for the real-provider gate; fail fast at startup if it is absent.
    anthropic_api_key: str = Field(default="")
    llm_model: str = Field(default="claude-sonnet-4-6")
    log_level: str = Field(default="INFO")

_settings: Settings | None = None

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
```

### db/session.py

```python
from contextlib import contextmanager
from collections.abc import Generator
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None

def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        from <package>.config.settings import get_settings
        _engine = create_engine(get_settings().database_url, echo=False)
    return _engine

def _get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=_get_engine(), autoflush=False, autocommit=False)
    return _SessionLocal

def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency."""
    with _get_session_factory()() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

@contextmanager
def create_db_session() -> Generator[Session, None, None]:
    """Standalone — for graph nodes, CLI, scripts."""
    with _get_session_factory()() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

def init_db() -> None:
    from <package>.db.models import Base
    Base.metadata.create_all(bind=_get_engine())
```

### db/models.py

```python
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Text, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

def _uuid() -> str:
    return str(uuid4())

def _now() -> datetime:
    return datetime.now(timezone.utc)

class Base(DeclarativeBase):
    pass

class RunRow(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, default=_now, onupdate=_now)
```

### graph/state.py

```python
from typing import TypedDict

class AgentState(TypedDict, total=False):
    run_id: str
    error: str | None
    # add domain fields here
```

### graph/nodes.py (Phase 1 placeholder shape)

```python
from <package>.graph.state import AgentState

STUB_RESULT = {"stub": True}  # placeholder — replaced by real provider calls before the Phase 2 gate

def fetch_data(state: AgentState) -> AgentState:
    return {**state, "data": STUB_RESULT}

def process(state: AgentState) -> AgentState:
    return {**state, "processed": True}

def handle_error(state: AgentState) -> AgentState:
    return {**state, "status": "failed"}

def finalize(state: AgentState) -> AgentState:
    return {**state, "status": "completed"}
```

### graph/edges.py

```python
from <package>.graph.state import AgentState

def after_fetch(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "process"

def after_process(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "finalize"
```

### graph/agent.py

```python
from langgraph.graph import StateGraph, END
from <package>.graph.state import AgentState
from <package>.graph.nodes import fetch_data, process, handle_error, finalize
from <package>.graph.edges import after_fetch, after_process

def _build_graph() -> StateGraph:
    g = StateGraph(AgentState)
    g.add_node("fetch_data", fetch_data)
    g.add_node("process", process)
    g.add_node("handle_error", handle_error)
    g.add_node("finalize", finalize)
    g.set_entry_point("fetch_data")
    g.add_conditional_edges("fetch_data", after_fetch, {"process": "process", "handle_error": "handle_error"})
    g.add_conditional_edges("process", after_process, {"finalize": "finalize", "handle_error": "handle_error"})
    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)
    return g.compile()

agentic_ai = _build_graph()
```

### graph/runner.py

```python
from <package>.graph.agent import agentic_ai
from <package>.graph.state import AgentState
from <package>.db.session import create_db_session, init_db
from <package>.db.models import RunRow

def run_agent() -> str:
    init_db()
    with create_db_session() as session:
        run = RunRow()
        session.add(run)
        session.flush()
        run_id = run.id

    initial: AgentState = {"run_id": run_id, "error": None}
    final = agentic_ai.invoke(initial)

    with create_db_session() as session:
        run = session.get(RunRow, run_id)
        run.status = final.get("status", "completed")
        run.error_message = final.get("error")

    return run_id
```

### api/__init__.py

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def _lifespan(app: FastAPI):
    from <package>.db.session import init_db
    init_db()
    yield

def create_app() -> FastAPI:
    app = FastAPI(title="<Agent Name>", version="0.1.0", lifespan=_lifespan)
    from <package>.api import health
    app.include_router(health.router)
    return app

app = create_app()
```

### api/_common.py

```python
from typing import Any
from fastapi import HTTPException

def ok(data: Any) -> dict:
    return {"data": data, "error": None}

def api_error(code: str, message: str, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})
```

### tests/conftest.py

```python
import pytest

@pytest.fixture(autouse=True)
def _reset_settings_singleton():
    """Reset cached settings so env patches take effect in every test."""
    import importlib, <package>.config.settings as m
    m._settings = None
    yield
    m._settings = None
```

### tests/integration/test_pipeline.py

Integration tests run end-to-end against the **real LLM/API** using keys loaded
from `.env` (via `get_settings()`), against an isolated copy of the production DB
driver. Assert on the run's structural result (status, shape, key fields), not on
exact model prose. If a required key is genuinely absent, `pytest.skip` — never
fall back to a stub key as the default path. Integration tests also cover edge
cases and error paths, not just the happy run.

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from <package>.config.settings import get_settings
from <package>.db.models import Base, RunRow
from <package>.db import session as session_module
from <package>.graph.runner import run_agent

@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    # Isolated copy of the production DB driver (use a temp PostgreSQL DB if prod
    # is PostgreSQL — never substitute SQLite for a production DB).
    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(session_module, "_engine", engine)
    monkeypatch.setattr(session_module, "_SessionLocal", factory)
    monkeypatch.setattr(session_module, "init_db", lambda: None)
    yield
    engine.dispose()

@pytest.fixture(autouse=True)
def _real_env(monkeypatch, tmp_path):
    # The provider key is loaded from .env via get_settings(); confirm presence
    # only (bool) — never echo or hardcode the value. Skip (do NOT stub) if absent.
    monkeypatch.setenv("APP_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    if not get_settings().anthropic_api_key:
        pytest.skip("real LLM/API key not set in .env — required for the real-provider run")

def test_pipeline_runs_end_to_end(_isolated_db, _real_env):
    from sqlalchemy.orm import Session
    run_id = run_agent()  # exercises the real provider end-to-end
    assert run_id is not None
    with Session(session_module._engine) as s:
        run = s.get(RunRow, run_id)
        assert run is not None
        assert run.status == "completed"
```

---

## Rules

1. **Agent code goes in `src/<package>/`** — never in the boilerplate root
2. **No repository pattern** — direct SQLAlchemy queries in graph nodes and API handlers
3. **`graph/` not `agent/`** — directory name matches sales-agent convention
4. **TypedDict state** — not dataclass or Pydantic model
5. **Tools are pure functions** — `(inputs) → domain model`, no class instantiation
6. **Prompts are `.md` files** in `<package>/prompts/` — loaded at runtime
7. **LLM abstraction** — `LLMClient` wrapper, never call provider SDK directly in nodes
8. **FastAPI response envelope** — every route returns `ok(data)` or raises `api_error()`
9. **Settings singleton** must be resettable via `monkeypatch.setattr(m, "_settings", None)`
10. **Phase 2 gate runs against real services** — tests and the golden-path smoke hit the real LLM/API using keys loaded from `.env` (requested at intake), against the production DB driver (never SQLite if production is PostgreSQL). A stub provider remains only as an optional fallback when a key is genuinely absent; offline-passing is no longer required, and real-key execution is the default and required path for the gate.
