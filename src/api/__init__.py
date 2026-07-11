from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles


@asynccontextmanager
async def _lifespan(app: FastAPI):
    from config.settings import get_settings
    from db.session import init_db
    from observability.events import get_logger

    settings = get_settings()
    artifacts_dir = Path(settings.artifacts_dir)
    try:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(
            f"Artifacts directory '{artifacts_dir}' is not creatable ({exc}). "
            "Set AGENT_ARTIFACTS_DIR to a writable path."
        ) from exc
    init_db()
    get_logger("agent.api").info(
        "app_started",
        port=settings.port,
        artifacts_dir=str(artifacts_dir),
        llm_model=settings.llm_model,
        gemini_key_present=bool(settings.gemini_api_key),  # presence only — never the value
    )
    yield


def create_app() -> FastAPI:
    from config.settings import get_settings
    from observability.events import configure_logging

    # Structured JSON logging for every request/node/LLM call — wired at startup
    # (idempotent; the graph runner also guards its own thread path).
    configure_logging(get_settings().log_level)

    app = FastAPI(
        title="IR Box Culvert Design & Proof-Check Agent", version="0.1.0", lifespan=_lifespan
    )
    from api import components, designs, health, presets, sessions

    app.include_router(health.router)
    app.include_router(sessions.router)
    app.include_router(designs.router)
    app.include_router(presets.router)
    app.include_router(components.router)

    # Bare domain → the SPA. The UI lives under /app (Next.js basePath), so a
    # visitor hitting the root (e.g. https://zero-rail-agent.smalltech.in/)
    # is redirected to the app instead of getting a 404.
    @app.get("/", include_in_schema=False)
    def _root_redirect() -> RedirectResponse:
        return RedirectResponse(url="/app/")

    # Serve the built Next.js static export at /app
    # Run `cd frontend && pnpm build` to generate frontend/out/ before starting.
    # Server starts fine without it (API-only mode when out/ doesn't exist).
    # __file__ = src/api/__init__.py → 3 parents up = repo root
    frontend_out = Path(__file__).resolve().parent.parent.parent / "frontend" / "out"
    if frontend_out.exists():
        app.mount("/app", StaticFiles(directory=str(frontend_out), html=True), name="frontend")

    return app


app = create_app()
