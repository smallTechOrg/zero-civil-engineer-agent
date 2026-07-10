# Tech-Stack Rules

Generic engineering rules that hold for **every** project, whatever stack is chosen. The project's *chosen* stack (language, framework, LLM provider/model, database, libraries) is recorded in `spec/architecture.md` under `## Stack`. This file is the permanent doctrine the spec-writer (filling the `## Stack`) and the frontend/code-generators (implementing against it) follow — it is not edited per project.

---

## Default Dev Port

All generated projects **must** use **port 8001** as the default development port (not 8000).

Reason: port 8000 is commonly occupied by other local services (FastAPI apps, Django, `http.server`, etc.). Using 8001 avoids startup failures with no code change needed.

- `__main__.py` must hard-code `port=8001` (not 8000) unless overridden by an env var
- README must reference `http://localhost:8001`
- `.env.example` should include `PORT=8001` if the port is configurable

## Frontend Static-Export & Styling Rule

When the frontend is a **Next.js static export served by the backend** (the skeleton's model: `output: 'export'`, `basePath: '/app'`, mounted by FastAPI at `/app`), three things are mandatory — each was a real first-build failure:

- **Single-origin is the canonical run + test path.** The user (and the gate) runs **one** server: `cd frontend && pnpm build` → `uv run python -m src`, then opens **`http://localhost:8001/app/`** (note the port `8001`, the `/app/`, and the trailing slash). Do **not** hand the user the two-server `pnpm dev` (`:3000`) flow as the test path — with `basePath: '/app'`, `localhost:3000/` 404s and the API origin differs, which reads as "nothing loads". `pnpm dev` is for inner-loop dev only.
- **Tailwind v4 requires `postcss.config.mjs` (plugin: `@tailwindcss/postcss`) and `@source "../";` in the global CSS file.** Without both, the built CSS has no utility classes — the UI renders unstyled even though the build exits 0. **Code-generators must never replace or omit these two files** — extend `globals.css` below the `@source` line, never overwrite the first two lines. The gate must verify the built CSS contains real utility selectors, not just check HTTP 200.
- **Node-version safety.** Node ≥25 exposes a broken global `localStorage` unless `--localstorage-file` is set, which crashes Next SSR (`localStorage.getItem is not a function` → every page 500s). The frontend `dev`/`build`/`start` scripts must carry `NODE_OPTIONS=--no-experimental-webstorage` (or the project must pin a supported Node LTS via `.nvmrc`/`engines`).
- **Playwright E2E (required for any project with a frontend).** Every frontend build must include a `tests/e2e/` directory with Playwright smoke tests. Install via `pnpm add -D @playwright/test && npx playwright install --with-deps chromium` (chromium only is sufficient for the gate). The Phase 1 smoke must cover: page loads and is styled, primary input works, real output appears (not a spinner or error state). Gate command: `npx playwright test tests/e2e/ --reporter=line`. **A frontend gate that only checks HTTP 200 or CSS selectors is not a gate — Playwright must also pass.**

## LLM Model Name Rule

**Always use a current, verified model name — never a deprecated or guessed one.**

- Model names change. Before hardcoding any model identifier, verify it exists by calling the provider's `ListModels` API or checking current documentation.
- The model name must be configurable via an env var (e.g. `APPNAME_LLM_MODEL`) so it can be changed without a code deployment.
- A 404 NOT_FOUND from the LLM API almost always means the model name is wrong — check the name first before debugging anything else.

Current safe defaults (as of 2026):

| Provider | Default model | Notes |
|----------|---------------|-------|
| Anthropic | `claude-sonnet-4-6` | matches `.env.example`; verify against current docs before pinning |
| OpenRouter | `anthropic/claude-sonnet-4-6` | provider-prefixed; routes to the underlying model |
| Google Gemini | `gemini-3.1-pro` | default; `gemini-2.5-flash` is the fast/cheap alternative for latency-sensitive nodes. `gemini-2.0-flash`/`gemini-1.5-flash` are unavailable for new users |
| OpenAI | `gpt-4o-mini` | |

## DB Driver Rule

The database driver (e.g. `psycopg2-binary` for PostgreSQL, `asyncpg` for async PostgreSQL) **must be declared in the main `[project.dependencies]` block**, never in `[dependency-groups.dev]` or equivalent dev-only groups.

Reason: Alembic migrations run at deploy/setup time, not just in tests. If the driver is dev-only, `alembic upgrade head` fails in any environment that didn't install dev deps.

## Test Environment Rule

**Tests must use the same database driver as production.** If the production DB is PostgreSQL, tests run against PostgreSQL — not SQLite.

- Tests that pass on SQLite but were never run against PostgreSQL are **not a passing gate**.
- The test database must be set up automatically. Use `conftest.py` to create and tear down the test database — no manual steps.
- The test DB URL is provided via env var (e.g. `TEST_DATABASE_URL`, or reuse `DATABASE_URL` pointing at a `_test` database). The `conftest.py` session fixture creates all tables before tests and drops them after.
- A `.env.test` file (gitignored) or CI environment variable provides the test DB URL. The README must document this.

Example `conftest.py` pattern for PostgreSQL + SQLAlchemy (sync):

```python
import pytest
from sqlalchemy import create_engine
from yourapp.db.models import Base
from yourapp.config.settings import get_settings

@pytest.fixture(scope="session", autouse=True)
def _setup_test_db():
    settings = get_settings()
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()
```

The `DATABASE_URL` in `.env` (or `.env.test`) must point at a real PostgreSQL test database before running tests.

## LLM / API Test Rule

**Tests and evals run against the real LLM/API using keys loaded from `.env`.** There is no offline-passing requirement; real-key execution is the default and required path for every gate, against the production DB driver (never SQLite if production is PostgreSQL). A stub provider MAY exist as an optional local fallback when a key is genuinely absent, but it is never the gate. The quality bar is perfect, zero errors — edge-case, end-to-end, and UI tests are required, not optional.

- The build and tests load keys programmatically from `.env` (gitignored); confirm a key by presence (bool) only — never echo, print, paste, or commit a secret value.
- A stub is permitted only for an integration whose external system isn't built yet — never as a substitute for the real provider on a path that exists.
- **CI contract:** a runner without secrets cannot pass the real-key gate. Either inject the keys from a secret store, or guard the real-key tests with `pytest.skip` when keys are unset. Skipped is not passed: the Phase 2+ gate is BLOCKED if a required key is missing locally.
