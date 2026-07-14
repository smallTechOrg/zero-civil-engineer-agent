"""Design-run endpoints: submit, snapshot, SSE progress stream, artefact files, library listing.

The graph runner and the progress bus are imported lazily through the accessor
functions below — the API stays importable (and unit-testable) without them,
and tests patch the accessors directly.
"""

import json
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api._common import api_error, iso, ok
from config.settings import get_settings
from db.models import ArtifactRow, DesignRunRow, SessionRow
from db.session import get_session
from domain.api import (
    ArtefactInfo,
    DesignSubmitRequest,
    DesignSubmitted,
    RunListItem,
    RunSnapshot,
    TokenUsage,
)

router = APIRouter(prefix="/api")

SESSION_TITLE_MAX_CHARS = 60

# The fixed artefact set per spec/data.md — whitelisting makes path traversal impossible.
ARTIFACT_FILES: dict[str, tuple[str, str]] = {
    "ga.dxf": ("image/vnd.dxf", "attachment"),
    "ga.svg": ("image/svg+xml", "inline"),
    "calc_sheet.json": ("application/json", "inline"),
    "compliance.json": ("application/json", "inline"),
    "proof_memo.md": ("text/markdown", "inline"),
    "bmd.svg": ("image/svg+xml", "inline"),
    "sfd.svg": ("image/svg+xml", "inline"),
    "model.glb": ("model/gltf-binary", "attachment"),
    "model.step": ("application/step", "attachment"),
    # Standard-driven components (M-00004) emit one extra artefact: the reportlab
    # drawing sheet, served inline so the browser can open the PDF.
    "m00004_sheet.pdf": ("application/pdf", "inline"),
}


# --- Lazy accessors for the graph slice's surfaces (patched in unit tests) -----


def _start_design_run(
    session_id: str,
    prompt: str,
    preset_id: str | None = None,
    requested_component: str | None = None,
    params: dict | None = None,
) -> str:
    from graph.runner import start_design_run

    return start_design_run(
        session_id,
        prompt,
        preset_id=preset_id,
        requested_component=requested_component,
        params=params,
    )


def _component_is_available(type_id: str) -> bool:
    from components import registry

    return registry.is_available(type_id)


def _resolve_component(type_id: str):
    """The registered module for `type_id` (for synchronous params validation)."""
    from components import registry

    return registry.get(type_id)


def _progress_is_active(run_id: str) -> bool:
    from observability.progress import is_active

    return is_active(run_id)


def _progress_stream(run_id: str) -> Iterator[dict]:
    from observability.progress import stream

    return stream(run_id)


# --- Snapshot assembly ----------------------------------------------------------


def _loads(raw: str | None, default: Any) -> Any:
    return json.loads(raw) if raw else default


def _snapshot_from_row(row: DesignRunRow, artifact_rows: list[ArtifactRow]) -> RunSnapshot:
    return RunSnapshot(
        run_id=row.id,
        session_id=row.session_id,
        prompt=row.prompt,
        component_type=row.component_type,
        status=row.status,
        plan_text=row.plan_text,
        scope_message=row.scope_message,
        clarification_question=row.clarification_question,
        type_summary=_loads(row.type_summary_json, None),
        params=_loads(row.params_json, None),
        assumptions=_loads(row.assumptions_json, []),
        warnings=_loads(row.warnings_json, []),
        steps=_loads(row.steps_json, []),
        checks=_loads(row.checks_json, []),
        checklist=_loads(row.checklist_json, []),
        verdict=row.verdict,
        suggestions=_loads(row.suggestions_json, []),
        artefacts=[
            ArtefactInfo(
                kind=a.kind,
                filename=a.filename,
                url=f"/api/designs/{row.id}/artifacts/{a.filename}",
                size_bytes=a.size_bytes,
            )
            for a in artifact_rows
        ],
        tokens=TokenUsage(
            prompt_tokens=row.prompt_tokens,
            completion_tokens=row.completion_tokens,
            cost_usd=row.cost_usd,
        ),
        error_message=row.error_message,
        started_at=iso(row.started_at),
        completed_at=iso(row.completed_at),
        duration_ms=row.duration_ms,
    )


def _artifact_rows(session: Session, run_id: str) -> list[ArtifactRow]:
    return list(
        session.execute(
            select(ArtifactRow)
            .where(ArtifactRow.run_id == run_id)
            .order_by(ArtifactRow.created_at, ArtifactRow.id)
        ).scalars()
    )


# --- Endpoints --------------------------------------------------------------------


@router.post("/sessions/{session_id}/designs")
def submit_design(
    session_id: str, req: DesignSubmitRequest, session: Session = Depends(get_session)
) -> dict:
    session_row = session.get(SessionRow, session_id)
    if session_row is None:
        raise api_error("NOT_FOUND", f"Session {session_id} not found", 404)

    active_runs = session.execute(
        select(func.count())
        .select_from(DesignRunRow)
        .where(DesignRunRow.session_id == session_id, DesignRunRow.status == "running")
    ).scalar_one()
    if active_runs:
        raise api_error(
            "RUN_ACTIVE", "A run in this session is still running — wait for it to finish", 409
        )

    prompt = req.prompt.strip()
    requested_component = req.component_type
    params = req.params or None  # an empty dict counts as "no params"

    validated_params: dict | None = None
    if params:
        # --- Params-direct submission (standard-driven component) -------------
        # Requires a component_type; `params` is validated SYNCHRONOUSLY against
        # the module's param_model. On success the run bypasses the LLM intake.
        if not requested_component:
            raise api_error(
                "COMPONENT_REQUIRED",
                "A params-direct submission requires 'component_type'",
                422,
            )
        if not _component_is_available(requested_component):
            raise api_error(
                "UNKNOWN_COMPONENT",
                f"'{requested_component}' is not a registered, available component type",
                422,
            )
        module = _resolve_component(requested_component)
        try:
            validated_params = module.param_model(**params).model_dump(mode="json")
        except ValidationError as exc:
            raise api_error(
                "PARAMS_INVALID",
                f"Parameter validation failed: {_validation_detail(exc)}",
                422,
            ) from exc
        if not prompt:
            prompt = _synth_params_prompt(requested_component, validated_params)
    else:
        # --- Natural-language submission --------------------------------------
        if not prompt:
            raise api_error("EMPTY_PROMPT", "Prompt must not be blank", 422)
        if requested_component is not None:
            if not _component_is_available(requested_component):
                raise api_error(
                    "UNKNOWN_COMPONENT",
                    f"'{requested_component}' is not a registered, available component type",
                    422,
                )
            # A params-direct-only component (e.g. M-00004) is reachable ONLY via
            # the typed form — an NL submit without params is rejected.
            module = _resolve_component(requested_component)
            if getattr(module, "params_direct_only", False):
                raise api_error(
                    "PARAMS_REQUIRED",
                    f"'{requested_component}' requires a typed 'params' object "
                    "(it is a standard-driven, form-only component)",
                    422,
                )

    if not session_row.title:
        session_row.title = prompt[:SESSION_TITLE_MAX_CHARS]
    session_row.updated_at = datetime.now(timezone.utc)
    # Persist before the background run thread opens its own DB session.
    session.commit()

    # Params-direct threads the validated dict; the NL path keeps the legacy
    # 3-arg call (auto-detect) or the picker-forced type, unchanged.
    if validated_params is not None:
        run_id = _start_design_run(
            session_id,
            prompt,
            req.preset_id,
            requested_component=requested_component,
            params=validated_params,
        )
    elif requested_component is None:
        run_id = _start_design_run(session_id, prompt, req.preset_id)
    else:
        run_id = _start_design_run(
            session_id, prompt, req.preset_id, requested_component=requested_component
        )
    return ok(
        DesignSubmitted(
            run_id=run_id,
            status="running",
            events_url=f"/api/designs/{run_id}/events",
            snapshot_url=f"/api/designs/{run_id}",
        ).model_dump()
    )


LIST_LIMIT_MAX = 200


@router.get("/designs")
def list_designs(
    session_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_session),
) -> dict:
    # Clamp rather than reject: limit -> 1..200, offset -> >= 0. Keeps old callers
    # working while ruling out unbounded/negative queries.
    limit = max(1, min(limit, LIST_LIMIT_MAX))
    offset = max(0, offset)
    filters = [DesignRunRow.session_id == session_id] if session_id else []
    total = session.execute(
        select(func.count()).select_from(DesignRunRow).where(*filters)
    ).scalar_one()
    rows = session.execute(
        select(DesignRunRow)
        .where(*filters)
        .order_by(DesignRunRow.started_at.desc(), DesignRunRow.id)
        .limit(limit)
        .offset(offset)
    ).scalars()
    runs = [
        RunListItem(
            run_id=row.id,
            session_id=row.session_id,
            prompt=row.prompt,
            status=row.status,
            verdict=row.verdict,
            params_summary=_params_summary(_loads(row.params_json, None), row.component_type),
            cost_usd=row.cost_usd,
            started_at=iso(row.started_at),
            duration_ms=row.duration_ms,
        ).model_dump()
        for row in rows
    ]
    return ok({"runs": runs, "total": total})


@router.get("/designs/{run_id}")
def get_design(run_id: str, session: Session = Depends(get_session)) -> dict:
    row = session.get(DesignRunRow, run_id)
    if row is None:
        raise api_error("NOT_FOUND", f"Run {run_id} not found", 404)
    return ok(_snapshot_from_row(row, _artifact_rows(session, run_id)).model_dump())


@router.get("/designs/{run_id}/events")
def design_events(run_id: str, session: Session = Depends(get_session)) -> StreamingResponse:
    row = session.get(DesignRunRow, run_id)
    if row is None:
        raise api_error("NOT_FOUND", f"Run {run_id} not found", 404)

    snapshot = _snapshot_from_row(row, _artifact_rows(session, run_id)).model_dump()
    status, verdict, error_message = row.status, row.verdict, row.error_message

    def event_stream() -> Iterator[str]:
        yield _sse_frame("snapshot", snapshot)
        if status == "running":
            if _progress_is_active(run_id):
                for event in _progress_stream(run_id):
                    yield _sse_frame(event["event"], event["data"])
            else:
                yield _sse_frame(
                    "error",
                    {
                        "code": "RUN_FAILED",
                        "message": "Run is no longer active — the server may have restarted "
                        "mid-run. Submit the request again.",
                    },
                )
        elif status == "failed":
            yield _sse_frame(
                "error", {"code": "RUN_FAILED", "message": error_message or "Run failed"}
            )
        else:
            yield _sse_frame("done", {"status": status, "verdict": verdict})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/designs/{run_id}/artifacts/{filename}")
def get_artifact(
    run_id: str, filename: str, session: Session = Depends(get_session)
) -> FileResponse:
    entry = ARTIFACT_FILES.get(filename)
    if entry is None:
        raise api_error("INVALID_FILENAME", f"'{filename}' is not a known artefact filename", 400)
    if session.get(DesignRunRow, run_id) is None:
        raise api_error("NOT_FOUND", f"Run {run_id} not found", 404)

    mime, disposition = entry
    path = Path(get_settings().artifacts_dir) / run_id / filename
    if not path.is_file():
        raise api_error(
            "NOT_FOUND", f"Artefact {filename} has not been generated yet for this run", 404
        )
    return FileResponse(
        path,
        media_type=mime,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


def _sse_frame(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _fmt_num(value: float) -> str:
    text = f"{float(value):.2f}".rstrip("0")
    return text + "0" if text.endswith(".") else text


RETAINING_WALL_TYPE = "rcc_cantilever_retaining_wall"
M00004_TYPE = "m00004_box_culvert"


def _validation_detail(exc: ValidationError) -> str:
    """A compact 'field: message' join of a pydantic ValidationError for the API."""
    return "; ".join(
        f"{'.'.join(str(loc) for loc in err['loc']) or '(root)'}: {err['msg']}"
        for err in exc.errors()
    )


def _synth_params_prompt(component_type: str, params: dict) -> str:
    """A short synthetic audit prompt for a params-direct submit with no prompt."""
    if component_type == M00004_TYPE:
        span = params.get("clear_span_m")
        height = params.get("clear_height_m")
        fill = params.get("cushion_m")
        if span is not None and height is not None and fill is not None:
            return (
                f"M-00004 standard box culvert {_fmt_num(span)}x{_fmt_num(height)} m, "
                f"fill {_fmt_num(fill)} m"
            )
    return f"{component_type} — standard component (parameter form)"


def _params_summary(params: dict | None, component_type: str | None = None) -> str:
    """A one-line params summary for the library row.

    Culvert (default): '4.0 × 3.0 m, cushion 2.5 m, 25t-2008'.
    Retaining wall: '5.0 m retained, SBC 200 kN/m²'.
    M-00004 std box culvert: '4.0 × 4.0 m, fill 2.0 m (M-00004 std)'.
    Empty string when there are no params (e.g. a failed/clarifying run).
    """
    if not params:
        return ""
    if component_type == RETAINING_WALL_TYPE:
        return _retaining_wall_summary(params)
    if component_type == M00004_TYPE:
        return _m00004_summary(params)
    try:
        span, height, cushion = (
            params["clear_span_m"],
            params["clear_height_m"],
            params["cushion_m"],
        )
    except KeyError:
        return ""
    summary = f"{_fmt_num(span)} × {_fmt_num(height)} m, cushion {_fmt_num(cushion)} m"
    loading = params.get("loading_standard")
    return f"{summary}, {loading}" if loading else summary


def _retaining_wall_summary(params: dict) -> str:
    """e.g. '5.0 m retained, SBC 200 kN/m²' — empty when the RW criticals are absent."""
    try:
        height = params["retained_height_m"]
        sbc = params["safe_bearing_capacity_kn_m2"]
    except KeyError:
        return ""
    return f"{_fmt_num(height)} m retained, SBC {_fmt_num(sbc)} kN/m²"


def _m00004_summary(params: dict) -> str:
    """e.g. '4.0 × 4.0 m, fill 2.0 m (M-00004 std)' — empty when criticals absent."""
    try:
        span = params["clear_span_m"]
        height = params["clear_height_m"]
        fill = params["cushion_m"]
    except KeyError:
        return ""
    return (
        f"{_fmt_num(span)} × {_fmt_num(height)} m, fill {_fmt_num(fill)} m (M-00004 std)"
    )
