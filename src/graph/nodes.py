"""The ten pipeline nodes per spec/agent.md.

LLM nodes (understand, extract, the review memo narration, and the finalize
suggestions call) orchestrate and narrate; every engineering computation is
deterministic. Phase 2: analyse runs the full IRS engine (sizing + load cases
+ frame analysis), check runs the IRS CBC member checks and streams the calc
sheet, review runs the automatic proof-check (FE cross-check, 12-item
checklist, grounded memo). Phase 3: model3d builds the real GLB + STEP solid
(NON-FATAL — any failure is a warning and the 2D artefacts stand) and finalize
adds ONE Gemini call for 2–3 refinement suggestions (also non-fatal: swallowed,
log only). Every other node body is wrapped — exceptions set state["error"]
and route to handle_error (clarify/finalize/handle_error propagate to the
runner's catch-all).
"""

import functools
import time
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from config.settings import get_settings
from domain.culvert import (
    AnalysisResult,
    Assumption,
    BoxGeometry,
    CalcStep,
    CulvertParams,
    unusual_value_warnings,
)
from engine import size_culvert
from engine.analysis import analyse_frame
from engine.calcsheet import compose_calc_sheet
from engine.checks import MEMBER_LABELS, CheckResult, run_member_checks
from graph import persistence
from graph.accounting import compute_cost_usd, run_totals
from graph.extraction import (
    ExtractionResult,
    merge_params,
    select_clarification,
    validation_error_message,
)
from graph.state import AgentState
from graph.steps import StepTracker, duration_ms
from graph.suggestions import SuggestionsResult, run_summary, sanitize_suggestions
from llm.client import LLMClient, LLMResult
from observability.events import get_logger
from observability.progress import publish

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

_ARTIFACT_MIME = {
    "ga_dxf": "image/vnd.dxf",
    "ga_svg": "image/svg+xml",
    "calc_sheet": "application/json",
    "compliance": "application/json",
    "proof_memo": "text/markdown",
    "bmd_svg": "image/svg+xml",
    "sfd_svg": "image/svg+xml",
    "model_glb": "model/gltf-binary",
    "model_step": "application/step",
}
_ARTIFACT_ORDER = ("ga_dxf", "ga_svg")

# The spec/api.md `checks[]` row shape — exactly these keys are persisted.
_CHECK_ROW_KEYS = ("clause", "requirement", "computed", "limit", "status")


class UnderstandResult(BaseModel):
    """Structured output of the scope gate + plan (understand.md)."""

    in_scope: bool = Field(
        description="True only for designing/refining a single-cell RCC box culvert "
        "or answering a pending clarification about one."
    )
    scope_message: str | None = Field(
        default=None,
        description="Graceful one-paragraph scope statement — set ONLY when in_scope is false.",
    )
    plan: str = Field(
        default="",
        description="Plain-language design plan (2–4 short sentences) — set ONLY when in_scope is true.",
    )


def _load_prompt(name: str) -> str:
    return (_PROMPT_DIR / name).read_text(encoding="utf-8").strip()


def _log(state: AgentState, node: str):
    return get_logger("agent.graph").bind(run_id=state.get("run_id"), node=node)


def _node(fn):
    """Log node enter/exit with duration — one structlog line each way."""

    @functools.wraps(fn)
    def wrapper(state: AgentState) -> dict:
        log = _log(state, fn.__name__)
        log.info("node_entered")
        started = time.monotonic()
        updates = fn(state)
        log.info(
            "node_exited",
            node_ms=int((time.monotonic() - started) * 1000),
            error=updates.get("error"),
        )
        return updates

    return wrapper


def _conversation(state: AgentState) -> str:
    """The extraction/scoping context: prior turns + this turn's request."""
    lines: list[str] = []
    messages = state.get("messages") or []
    if messages:
        lines.append("Conversation so far:")
        lines.extend(f"{m['role']}: {m['content']}" for m in messages)
        lines.append("")
    lines.append(f"Current request: {state['user_prompt']}")
    return "\n".join(lines)


def _record_llm_call(state: AgentState, node: str, result: LLMResult) -> list[dict]:
    """Append usage to state, publish the running `tokens` event, log the call."""
    token_usage = list(state.get("token_usage") or []) + [
        {
            "node": node,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "latency_ms": result.latency_ms,
        }
    ]
    prompt_tokens, completion_tokens = run_totals(token_usage)
    cost_usd = compute_cost_usd(prompt_tokens, completion_tokens)
    session_total = persistence.session_cost_sum(state["session_id"]) + cost_usd
    publish(
        state["run_id"],
        "tokens",
        {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": round(cost_usd, 6),
            "session_total_cost_usd": round(session_total, 6),
        },
    )
    _log(state, node).info(
        "llm_call",
        model=get_settings().llm_model,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        latency_ms=result.latency_ms,
    )
    return token_usage


def _narrate(state: AgentState, text: str) -> None:
    publish(state["run_id"], "narration", {"text": text})


def _artifacts_dir(state: AgentState) -> Path:
    out_dir = Path(get_settings().artifacts_dir) / state["run_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _emit_artifact(
    state: AgentState, artefacts: list[dict], kind: str, path: Path, node: str
) -> None:
    """Record the artifact DB row, publish the `artefact` SSE event, log it.

    Called the moment each file is written — artefact delivery is incremental
    (the calc sheet streams before draw/review complete by node order).
    """
    run_id = state["run_id"]
    size_bytes = path.stat().st_size
    persistence.record_artifact(run_id, kind, path.name, _ARTIFACT_MIME[kind], size_bytes)
    publish(
        run_id,
        "artefact",
        {
            "kind": kind,
            "filename": path.name,
            "url": f"/api/designs/{run_id}/artifacts/{path.name}",
        },
    )
    artefacts.append({"kind": kind, "filename": path.name})
    _log(state, node).info(
        "artefact_written", kind=kind, filename=path.name, size_bytes=size_bytes
    )


# --------------------------------------------------------------------------- nodes


@_node
def understand(state: AgentState) -> dict:
    tracker = StepTracker(state)
    tracker.mark("Understand", "active", detail="Reading the request")
    try:
        result = LLMClient().generate(
            _conversation(state),
            system=_load_prompt("understand.md"),
            schema=UnderstandResult,
            temperature=0.2,
        )
        token_usage = _record_llm_call(state, "understand", result)
        parsed: UnderstandResult = result.parsed
        if not parsed.in_scope:
            scope_message = parsed.scope_message or (
                "This demonstrator designs and proof-checks single-cell RCC box "
                "culverts to IRS codes — that request is outside its scope."
            )
            _narrate(state, scope_message)
            tracker.mark("Understand", "done", detail="Out of scope")
            return {
                "in_scope": False,
                "scope_message": scope_message,
                "plan_text": "",
                "token_usage": token_usage,
                "steps": tracker.steps,
            }
        _narrate(state, parsed.plan)
        tracker.mark("Understand", "done")
        return {
            "in_scope": True,
            "scope_message": None,
            "plan_text": parsed.plan,
            "token_usage": token_usage,
            "steps": tracker.steps,
        }
    except Exception as exc:
        tracker.mark("Understand", "failed", detail=str(exc))
        return {
            "steps": tracker.steps,
            "error": f"Understanding the request failed (Gemini scope gate): {exc}",
        }


@_node
def extract(state: AgentState) -> dict:
    tracker = StepTracker(state)
    tracker.mark("Extract", "active", detail="Extracting design parameters")
    try:
        result = LLMClient().generate(
            _conversation(state),
            system=_load_prompt("extract.md"),
            schema=ExtractionResult,
            temperature=0.0,
        )
        token_usage = _record_llm_call(state, "extract", result)
        extracted = {k: v for k, v in result.parsed.model_dump().items() if v is not None}
        outcome = merge_params(
            extracted, state.get("prior_params"), state.get("preset_values") or {}
        )
        if outcome.missing_critical:
            # Clarify (still the Extract UI step) publishes the question and closes the run.
            return {
                "params": None,
                "missing_critical": outcome.missing_critical,
                "token_usage": token_usage,
                "steps": tracker.steps,
            }
        try:
            params = CulvertParams(**outcome.merged)
        except ValidationError as exc:
            message = validation_error_message(exc)
            tracker.mark("Extract", "failed", detail=message)
            return {
                "token_usage": token_usage,
                "steps": tracker.steps,
                "error": f"Parameter validation failed: {message}",
            }
        warnings = unusual_value_warnings(params)
        for warning in warnings:
            publish(state["run_id"], "warning", {"message": warning})
        preset_assumptions = [
            Assumption(
                field=field,
                value=outcome.merged[field],
                source="preset",
                note="Applied from the defaults preset — not stated by the user.",
            ).model_dump()
            for field in outcome.preset_fields
        ]
        tracker.mark(
            "Extract",
            "done",
            detail=(
                f"{params.clear_span_m:g} × {params.clear_height_m:g} m box, "
                f"cushion {params.cushion_m:g} m"
            ),
        )
        return {
            "params": params.model_dump(mode="json"),
            "missing_critical": [],
            "warnings": list(state.get("warnings") or []) + warnings,
            "assumptions": list(state.get("assumptions") or []) + preset_assumptions,
            "token_usage": token_usage,
            "steps": tracker.steps,
        }
    except Exception as exc:
        tracker.mark("Extract", "failed", detail=str(exc))
        return {
            "steps": tracker.steps,
            "error": f"Parameter extraction failed (Gemini structured output): {exc}",
        }


@_node
def clarify(state: AgentState) -> dict:
    """Deterministic: ONE pointed question, run ends at needs_input (terminal)."""
    tracker = StepTracker(state)
    field, question = select_clarification(state["missing_critical"])
    publish(
        state["run_id"], "clarification", {"question": question, "missing_param": field}
    )
    tracker.mark("Extract", "done", detail=f"Needs input — asked for {field}")

    prompt_tokens, completion_tokens = run_totals(state.get("token_usage") or [])
    cost_usd = compute_cost_usd(prompt_tokens, completion_tokens)
    persistence.finish_run(
        state["run_id"],
        status="needs_input",
        clarification_question=question,
        plan_text=state.get("plan_text"),
        steps=tracker.steps,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
        duration_ms=duration_ms(state),
    )
    publish(
        state["run_id"],
        "tokens",
        {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": round(cost_usd, 6),
            "session_total_cost_usd": round(
                persistence.session_cost_sum(state["session_id"]), 6
            ),
        },
    )
    publish(state["run_id"], "done", {"status": "needs_input", "verdict": None})
    _log(state, "clarify").info("run_outcome", status="needs_input", missing_param=field)
    return {
        "status": "needs_input",
        "clarification_question": question,
        "steps": tracker.steps,
    }


@_node
def analyse(state: AgentState) -> dict:
    """Deterministic IRS engine: sizing, then load cases + rigid-frame analysis."""
    tracker = StepTracker(state)
    tracker.mark("Analyse", "active", detail="Running the IRS engine")
    try:
        params = CulvertParams(**state["params"])
        _narrate(state, f"Sizing members for {params.clear_span_m:g} m span…")
        sizing = size_culvert(params)
        for warning in sizing.warnings:
            publish(state["run_id"], "warning", {"message": warning})
        geometry = sizing.geometry

        analysis = analyse_frame(params, geometry)
        _narrate(
            state,
            f"Analysing {len(analysis.load_cases)} load cases across "
            f"{len(analysis.combinations)} combinations…",
        )
        tracker.mark(
            "Analyse",
            "done",
            detail=(
                f"{len(analysis.load_cases)} load cases, "
                f"{len(analysis.combinations)} combinations; top slab "
                f"{geometry.top_slab_thickness_mm:g} mm, walls "
                f"{geometry.wall_thickness_mm:g} mm"
            ),
        )
        return {
            "geometry": geometry.model_dump(),
            "analysis": analysis.model_dump(),
            "assumptions": list(state.get("assumptions") or [])
            + [a.model_dump() for a in sizing.assumptions]
            + [a.model_dump() for a in analysis.assumptions],
            # Engine-ordered trail segments retained for the calc-sheet composer.
            "trail_segments": [
                [step.model_dump() for step in sizing.trail],
                [step.model_dump() for step in analysis.trail],
            ],
            "warnings": list(state.get("warnings") or []) + sizing.warnings,
            "steps": tracker.steps,
        }
    except Exception as exc:
        tracker.mark("Analyse", "failed", detail=str(exc))
        return {"steps": tracker.steps, "error": f"IRS engine analysis failed: {exc}"}


@_node
def check(state: AgentState) -> dict:
    """IRS CBC member checks + the clause-cited calc sheet (streams immediately).

    FAIL rows never fail the run — they flow to the proof-check, which grades
    them (the deliberate under-design demo case depends on this).
    """
    tracker = StepTracker(state)
    tracker.mark("Check", "active", detail="IRS CBC member checks")
    try:
        params = CulvertParams(**state["params"])
        geometry = BoxGeometry(**state["geometry"])
        analysis = AnalysisResult(**state["analysis"])
        _narrate(
            state,
            "Checking members to IRS CBC — flexure, shear, minimum steel, "
            "cover, crack control…",
        )
        output = run_member_checks(analysis, geometry, params)

        assumptions = list(state.get("assumptions") or []) + [
            a.model_dump() for a in output.assumptions
        ]
        segments = [
            [CalcStep(**step) for step in segment]
            for segment in (state.get("trail_segments") or [])
        ] + [output.trail]
        sheet_path = compose_calc_sheet(
            trail=segments,
            checks=output.checks,
            assumptions=[Assumption(**a) for a in assumptions],
            warnings=list(state.get("warnings") or []),
            params=params,
            geometry=geometry,
            out_dir=_artifacts_dir(state),
        )
        artefacts = list(state.get("artefacts") or [])
        # The calc sheet streams BEFORE draw/review by node order (calc-sheet.md).
        _emit_artifact(state, artefacts, "calc_sheet", sheet_path, "check")

        failing = [row for row in output.checks if row.status != "PASS"]
        if failing:
            members = ", ".join(
                sorted({MEMBER_LABELS.get(row.member, row.member) for row in failing})
            )
            _narrate(
                state,
                f"{len(failing)} of {len(output.checks)} checks FAIL ({members}) — "
                "the proof-check will grade them.",
            )
            detail = f"{len(failing)} of {len(output.checks)} checks FAIL ({members})"
        else:
            detail = f"All {len(output.checks)} checks PASS"
        tracker.mark("Check", "done", detail=detail)
        return {
            "checks": [row.model_dump() for row in output.checks],
            "assumptions": assumptions,
            "artefacts": artefacts,
            "steps": tracker.steps,
        }
    except Exception as exc:
        tracker.mark("Check", "failed", detail=str(exc))
        return {"steps": tracker.steps, "error": f"IRS CBC member checks failed: {exc}"}


@_node
def draw(state: AgentState) -> dict:
    tracker = StepTracker(state)
    tracker.mark("Draw", "active", detail="Drawing the GA sheet")
    try:
        from drawing.ga import generate_ga  # deterministic sibling slice — pinned contract

        run_id = state["run_id"]
        geometry = BoxGeometry(**state["geometry"])
        params = CulvertParams(**state["params"])
        out_dir = _artifacts_dir(state)
        _narrate(state, "Drawing the GA sheet — plan, sections, dimensions…")

        paths = generate_ga(geometry, params, out_dir, run_id=run_id)

        artefacts = list(state.get("artefacts") or [])
        for kind in _ARTIFACT_ORDER:
            _emit_artifact(state, artefacts, kind, paths[kind], "draw")
        tracker.mark("Draw", "done", detail="GA drawing ready (DXF + SVG)")
        return {"artefacts": artefacts, "steps": tracker.steps}
    except Exception as exc:
        tracker.mark("Draw", "failed", detail=str(exc))
        return {"steps": tracker.steps, "error": f"GA drawing generation failed: {exc}"}


@_node
def model3d(state: AgentState) -> dict:
    """Phase 3: build123d solid → model.glb + model.step from the SAME BoxGeometry.

    NON-FATAL BY DESIGN (spec/agent.md): on ANY failure — structlog error, one
    `warning` event, and the run continues to review with no model artefacts;
    the 2D artefacts stand alone and the verdict/status are unaffected. The
    Draw UI step is already 'done' from the draw node, so success publishes NO
    extra step event (the Phase-2 skipped tag is gone).
    """
    artefacts = list(state.get("artefacts") or [])
    try:
        from model3d import generate_solid  # heavy CAD kernel loads lazily

        geometry = BoxGeometry(**state["geometry"])
        out_dir = _artifacts_dir(state)
        _narrate(state, "Building the 3D solid — GLB for the viewer, STEP for CAD…")
        paths = generate_solid(geometry, out_dir)
        for kind in ("model_glb", "model_step"):
            _emit_artifact(state, artefacts, kind, paths[kind], "model3d")
        return {"artefacts": artefacts}
    except Exception as exc:  # never fatal, never an `error` state
        _log(state, "model3d").error("model3d_failed", error=str(exc))
        publish(
            state["run_id"],
            "warning",
            {
                "message": (
                    "3D model generation failed — the 2D artefacts stand "
                    f"alone: {exc}"
                )
            },
        )
        return {"artefacts": artefacts}


@_node
def review(state: AgentState) -> dict:
    """The automatic proof-check: FE cross-check → 12-item checklist → memo.

    ONE Gemini call narrates the memo from the deterministic facts (1 retry
    with backoff inside the provider, then the run fails transparently). A
    narration that fails the grounding validator is NOT fatal — the memo falls
    back to the fully deterministic composition. The verdict is computed by
    rule in `run_checklist`, never by the LLM.
    """
    tracker = StepTracker(state)
    tracker.mark("Review", "active", detail="Independent proof-check")
    try:
        # Heavy deterministic deps (anastruct/matplotlib/ezdxf) load lazily here.
        from engine.fe_check import BMD_FILENAME, SFD_FILENAME, cross_check
        from proofcheck import (
            COMPLIANCE_FILENAME,
            PROOF_MEMO_FILENAME,
            VERDICT_APPROVAL,
            memo_facts,
            render_memo,
            run_checklist,
            validate_narration,
        )
        from proofcheck.checklist import SEVERITY_MAJOR

        params = CulvertParams(**state["params"])
        geometry = BoxGeometry(**state["geometry"])
        analysis = AnalysisResult(**state["analysis"])
        checks = [CheckResult(**row) for row in (state.get("checks") or [])]
        warnings = list(state.get("warnings") or [])
        assumptions = [Assumption(**a) for a in (state.get("assumptions") or [])]
        out_dir = _artifacts_dir(state)
        artefacts = list(state.get("artefacts") or [])

        _narrate(state, "Re-solving the frame independently (anaStruct FE cross-check)…")
        fe = cross_check(params, geometry, analysis, out_dir)
        _emit_artifact(state, artefacts, "bmd_svg", out_dir / BMD_FILENAME, "review")
        _emit_artifact(state, artefacts, "sfd_svg", out_dir / SFD_FILENAME, "review")

        _narrate(state, "Evaluating the 12-item proof-check checklist…")
        result = run_checklist(
            params=params,
            geometry=geometry,
            analysis=analysis,
            checks=checks,
            fe=fe,
            ga_dxf_path=out_dir / "ga.dxf",
            out_dir=out_dir,
        )
        _emit_artifact(
            state, artefacts, "compliance", out_dir / COMPLIANCE_FILENAME, "review"
        )

        _narrate(state, "Drafting the proof-check memo…")
        facts = memo_facts(
            result,
            params=params,
            geometry=geometry,
            warnings=warnings,
            assumptions=assumptions,
        )
        llm = LLMClient().generate(
            facts, system=_load_prompt("memo.md"), temperature=0.2
        )
        token_usage = _record_llm_call(state, "review", llm)
        narration: str | None = (llm.text or "").strip()
        problems = validate_narration(narration, result, extra_facts=facts)
        if problems:
            # Rejection is never fatal — the memo stands fully deterministic.
            publish(
                state["run_id"],
                "warning",
                {
                    "message": "The LLM memo narration failed the deterministic "
                    "grounding validation and was discarded — the memo is fully "
                    "deterministic."
                },
            )
            _log(state, "review").warning("memo_narration_rejected", problems=problems)
            narration = None
        memo_md = render_memo(
            result,
            narration,
            params=params,
            geometry=geometry,
            warnings=warnings,
            assumptions=assumptions,
        )
        memo_path = out_dir / PROOF_MEMO_FILENAME
        memo_path.write_text(memo_md, encoding="utf-8")
        _emit_artifact(state, artefacts, "proof_memo", memo_path, "review")

        if result.verdict == VERDICT_APPROVAL:
            detail = (
                f"Recommended for approval — FE agreement {result.fe_agreement_pct:g}%"
            )
        else:
            majors = sum(1 for item in result.items if item.severity == SEVERITY_MAJOR)
            detail = f"Return for revision — {majors} major non-conformities"
        tracker.mark("Review", "done", detail=detail)
        return {
            "fe_comparison": fe.model_dump(),
            "checklist": [item.model_dump() for item in result.items],
            "verdict": result.verdict,
            "artefacts": artefacts,
            "token_usage": token_usage,
            "steps": tracker.steps,
        }
    except Exception as exc:
        tracker.mark("Review", "failed", detail=str(exc))
        return {"steps": tracker.steps, "error": f"The automatic proof-check failed: {exc}"}


def _refinement_suggestions(state: AgentState) -> tuple[list[str], list[dict]]:
    """ONE Gemini call for 2–3 refinement chips — NON-FATAL (spec: swallowed, log only).

    Returns (suggestions, token_usage). The LLM proposes against the compact
    run summary; deterministic sanitisation decides what survives. Any failure
    on this path — transport, schema, validation — degrades to an empty list
    and the run still completes.
    """
    token_usage = list(state.get("token_usage") or [])
    try:
        result = LLMClient().generate(
            run_summary(state),
            system=_load_prompt("suggest.md"),
            schema=SuggestionsResult,
            temperature=0.4,
        )
        token_usage = _record_llm_call(state, "finalize", result)
        suggestions = sanitize_suggestions(result.parsed.suggestions)
        if len(suggestions) < 2:
            _log(state, "finalize").warning(
                "suggestions_below_minimum", kept=len(suggestions)
            )
        return suggestions, token_usage
    except Exception as exc:  # invisible-degrading per session-refinement.md
        _log(state, "finalize").warning("suggestions_failed", error=str(exc))
        return [], token_usage


@_node
def finalize(state: AgentState) -> dict:
    status = "completed" if state.get("in_scope", True) else "out_of_scope"
    verdict = state.get("verdict")
    # Phase 3: refinement suggestions for COMPLETED designs only (out_of_scope
    # runs never get chips; clarify never reaches finalize).
    suggestions: list[str] = []
    token_usage = list(state.get("token_usage") or [])
    if status == "completed":
        suggestions, token_usage = _refinement_suggestions(state)
    prompt_tokens, completion_tokens = run_totals(token_usage)
    cost_usd = compute_cost_usd(prompt_tokens, completion_tokens)
    # checks_json rows carry EXACTLY the spec/api.md keys.
    check_rows = [
        {key: row[key] for key in _CHECK_ROW_KEYS} for row in (state.get("checks") or [])
    ]
    persistence.finish_run(
        state["run_id"],
        status=status,
        plan_text=state.get("plan_text") or None,
        scope_message=state.get("scope_message"),
        params=state.get("params"),
        assumptions=state.get("assumptions"),
        warnings=state.get("warnings"),
        steps=state.get("steps"),
        checks=check_rows or None,
        checklist=state.get("checklist") or None,
        verdict=verdict,
        suggestions=suggestions if status == "completed" else None,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
        duration_ms=duration_ms(state),
    )
    publish(
        state["run_id"],
        "tokens",
        {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": round(cost_usd, 6),
            "session_total_cost_usd": round(
                persistence.session_cost_sum(state["session_id"]), 6
            ),
        },
    )
    # `done` stays exactly the spec/api.md payload — no suggestions field; the
    # frontend re-fetches the snapshot, which carries `suggestions[]`.
    publish(state["run_id"], "done", {"status": status, "verdict": verdict})
    _log(state, "finalize").info(
        "run_outcome",
        status=status,
        verdict=verdict,
        suggestions=len(suggestions),
        duration_ms=duration_ms(state),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=round(cost_usd, 6),
    )
    return {"status": status, "suggestions": suggestions, "token_usage": token_usage}


@_node
def handle_error(state: AgentState) -> dict:
    error = state.get("error") or "Unknown failure — no error detail was recorded."
    prompt_tokens, completion_tokens = run_totals(state.get("token_usage") or [])
    cost_usd = compute_cost_usd(prompt_tokens, completion_tokens)
    persistence.finish_run(
        state["run_id"],
        status="failed",
        error_message=error,
        plan_text=state.get("plan_text") or None,
        steps=state.get("steps"),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
        duration_ms=duration_ms(state),
    )
    publish(state["run_id"], "error", {"code": "RUN_FAILED", "message": error})
    _log(state, "handle_error").error(
        "run_outcome", status="failed", error=error, duration_ms=duration_ms(state)
    )
    return {"status": "failed"}
