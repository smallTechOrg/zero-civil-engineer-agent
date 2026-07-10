# Code Style

> Generic code conventions that apply to **every** project — harness doctrine the code-generator and code-generator follow, not a per-project file. The language-specific sections are reference; this project's chosen language/stack is in `spec/architecture.md` (`## Stack`).

---

## Universal Rules

These apply regardless of language or framework:

1. **Types at boundaries** — every function that crosses a module boundary must use typed inputs and outputs (Pydantic, TypeScript interfaces, Go structs, etc.) — never raw dicts or `any`
2. **One responsibility per file** — a file does one thing; if it's doing two things, split it
3. **No comments explaining WHAT** — code should be self-documenting via names; only comment WHY something non-obvious is done
4. **No dead code** — remove unused imports, functions, and variables immediately; don't comment them out
5. **Fail loudly at startup** — validate all required config/env vars at startup; don't fail silently at runtime
6. **No hardcoding** — values that could change (URLs, limits, credentials) go in config or environment variables

## Naming Conventions

<!-- FILL IN: Filled in by spec-writer based on language choice. -->

## File Organization

<!-- FILL IN: Filled in by spec-writer. How are files grouped — by layer, by feature, by type? -->

## Error Handling Pattern

<!-- FILL IN: Filled in by spec-writer. How are errors represented and propagated? -->

## Logging Pattern

<!-- FILL IN: Filled in by spec-writer. Structured vs. unstructured? What fields are always included? -->

## Testing Conventions

<!-- FILL IN: Filled in by spec-writer. Unit test location, naming, runner. -->

## What NOT to Do

<!-- FILL IN: Anti-patterns specific to this tech stack. Filled in by spec-writer. -->

---

## Test Environment Rules

These apply to all projects. No exceptions.

1. **Same DB as production** — if the app uses PostgreSQL, tests use PostgreSQL. SQLite is not a substitute. A test suite that only passes on SQLite tells you nothing about whether migrations and queries work against the real database.

2. **Automated setup — no manual steps** — the `conftest.py` (or equivalent test setup) must create all required tables and tear them down automatically. The test runner must work with a single command (`uv run pytest`, `bun test`, etc.) after setting the test DB URL.

3. **Isolated test database** — use a dedicated database (e.g. `myapp_test`, not `myapp`). Never run tests against the development or production database.

4. **Test DB URL via environment** — expose the test database URL through the same env var mechanism as the app (e.g. `DATABASE_URL` pointing at the test DB, or a `TEST_DATABASE_URL` that the conftest reads). Document this in the README.

5. **DB URL and API keys in `.env.example`** — the `.env.example` file must include the test DB URL and every required LLM/API key with clear placeholders (e.g. `APPNAME_ANTHROPIC_API_KEY=`) so the user knows what to fill in. Filling `.env` with real keys is the only manual user step, requested at intake; tests and evals load these keys programmatically and confirm them by presence only.

6. **`alembic upgrade head` in CI / README** — the README must include `alembic upgrade head` as an explicit step before running the app or tests. Never rely on auto-create from SQLAlchemy metadata alone in production.

---

## Framework Gotchas (keep up to date — known footguns)

### Starlette ≥ 1.0 `TemplateResponse` signature

Starlette 1.0 and FastAPI 0.115+ require the **new** `TemplateResponse` call signature:

```python
# CORRECT (Starlette ≥ 1.0)
return templates.TemplateResponse(request, "page.html", {"foo": bar})

# WRONG (pre-1.0 form) — fails with TypeError: unhashable type: 'dict'
return templates.TemplateResponse("page.html", {"request": request, "foo": bar})
```

A small helper in the routes module keeps call sites tidy:

```python
def render(request: Request, name: str, **ctx):
    return templates.TemplateResponse(request, name, ctx)
```

### LLM provider selection and stubs

**Tests and evals run against the real provider using keys loaded from `.env`** (edge-case, end-to-end, and UI tests are required, not optional). The real provider is the default and required path; the stub below is an optional local fallback only.

Any project with an LLM dependency must follow these patterns:

1. **`provider=auto` by default → real when the key is set.** Resolve to the real provider when the API key env var is present in `.env`; the user never flips a flag in addition to setting the key. Add a `resolved_llm_provider` property on `Settings` that encapsulates this. Only when a key is genuinely absent may it fall back to an optional stub.

2. **Tolerate dirty `.env` values.** Config resolution must strip inline `#` comments and surrounding whitespace before comparing enum-like env values (`provider`, `mode`, etc.). A `.env` written months ago with `APPNAME_LLM_PROVIDER=anthropic   # anthropic | openai` must not silently pin the wrong provider. Pydantic-settings does NOT strip inline comments — do it yourself in a `resolved_*` property, never trust the raw field.

**If you keep the optional stub fallback**, it should be credible and self-evident:

- Outputs branch on explicit node tags, not prose keywords. Each node injects a unique tag (`<node:plan>`, `<node:draft>`, ...) and the stub matches those tags, so a draft prompt containing "expand this outline" never triggers the stub's "outline" branch.
- "Draft"-class outputs are shaped like the real thing (paragraphs/headings, not a bare bullet list).
- If the stub is active in dev, label it visibly so its output is never mistaken for real. This is a should-when-used, not a gate: the gate runs against real keys.

---

## Integration Test Patterns

Integration and e2e tests call the **real** LLM provider with keys loaded from `.env` — the call is NOT stubbed. The suite is overly tested: edge cases, error paths, end-to-end journeys, and (for any UI/HTTP surface) UI states are all required. Because real responses are non-deterministic, integration/e2e assertions check stable structural properties (status, shape, key fields) rather than exact prose; unit tests stay fully deterministic (inject the clock, seed randomness). Run against the production DB driver, never SQLite if production is PostgreSQL.

### Replacing an async init function in tests

When your runner calls an async `init_db()` or similar startup function, monkeypatch it with an async noop — not a sync lambda:

```python
# CORRECT
async def _noop(): pass
monkeypatch.setattr("mypackage.agent.runner.init_db", _noop)

# WRONG — breaks await
monkeypatch.setattr("mypackage.agent.runner.init_db", lambda: None)
```

### Replacing the DB session factory in integration tests

```python
@pytest.fixture(autouse=True)
async def _use_test_db(monkeypatch, tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    import mypackage.db.session as s
    monkeypatch.setattr(s, "AsyncSessionLocal", factory)
    monkeypatch.setattr(s, "engine", engine)

    async def _noop(): pass
    monkeypatch.setattr("mypackage.agent.runner.init_db", _noop)
    yield
    await engine.dispose()
```

Use `tmp_path` (not `:memory:`) for integration tests — it avoids shared-state issues across tests. The pattern above is illustrative; if production is PostgreSQL the fixture must point at the real production driver (a `_test` PostgreSQL database), never SQLite.

---

## Pydantic-settings — Always Set `extra="ignore"`

`pydantic-settings` reads **the entire `.env` file** and passes every key to Pydantic for validation. If the `.env` file contains variables the `Settings` model doesn't declare (e.g. `TEST_DATABASE_URL`, `EDITOR`, CI vars), Pydantic will raise:

```
ValidationError: Extra inputs are not permitted [type=extra_forbidden]
```

**Fix:** always set `extra="ignore"` in the `model_config`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APPNAME_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",          # ← required — .env may contain vars we don't own
    )
```

This is mandatory for any project whose `.env` contains variables owned by other tools (test runners, editors, CI, Docker, etc.).

---

## Pipeline Errors — Render an Error Template, Never Raise HTTPException

When an LLM pipeline node fails (provider 4xx/5xx, invalid response, timeout), the failure propagates back to the route via the pipeline state's `error` field. Render an error page — don't re-raise it as an `HTTPException` (a bare JSON body with a 422 status).

```python
if state["error"]:
    # WRONG: raise HTTPException(status_code=422, detail=state["error"])
    log.error("analyze.pipeline_error", error=state["error"])
    return render(request, "error.html", detail=state["error"])  # readable page + "Try again" link
```

`error.html` must always exist and link back to the start page. Every web route that calls `run_pipeline()` (or equivalent) must follow this pattern.
