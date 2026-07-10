"""The ten pipeline nodes per spec/agent.md — component-agnostic dispatch.

From the Component-Registry expansion on, every engineering node dispatches to
the selected Component Module via `registry.get(state["component_type"])`
instead of importing a component-specific engine directly. `understand`
classifies the component type (or honours the picker's `requested_component`);
`extract` uses the selected component's extraction schema and critical fields;
`analyse`/`check`/`draw`/`model3d`/`review` call the module's interface methods.
Adding a component type changes NO node — only the registry.

LLM nodes (understand, extract, the review memo narration, the finalize
suggestions call) orchestrate and narrate; every engineering computation is
deterministic. Every node body is wrapped — exceptions set state["error"] and
route to handle_error (clarify/finalize/handle_error propagate to the runner's
catch-all).
"""

import functools
import time
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from config.settings import get_settings
from domain.culvert import Assumption
from graph import persistence
from graph.accounting import compute_cost_usd, run_totals
from graph.extraction import merge_params, validation_error_message
from graph.state import AgentState
from graph.steps import StepTracker, duration_ms
from graph.suggestions import SuggestionsResult, run_summary, sanitize_suggestions
from llm.client import LLMClient, LLMResult
from observability.events import get_logger
from observability.progress import publish

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

_DEFAULT_COMPONENT = "box_culvert"

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

VERDICT_APPROVAL = "recommended_for_approval"


class UnderstandResult(BaseModel):
    """Structured output of the scope gate + component classification + plan."""

    in_scope: bool = Field(
        description="True only for designing/refining a component the platform currently "
        "supports (status='available'), or answering a pending clarification about one."
    )
    component_type: str | None = Field(
        default=None,
        description="The registry type_id of the component this request maps to — set "
        "ONLY when in_scope is true; must be one of the available type_ids listed in the "
        "system prompt.",
    )
    scope_message: str | None = Field(
        default=None,
        description="Graceful one-paragraph scope statement — set ONLY when in_scope is "
        "false (out of scope, or a recognised-but-coming_soon component).",
    )
    plan: str = Field(
        default="",
        description="Plain-language design plan (2–4 short sentences) — set ONLY when in_scope is true.",
    )


def _registry():
    """Lazy registry accessor — importing `components` populates it at first use."""
    from components import registry

    return registry


def _component_type(state: AgentState) -> str:
    return state.get("component_type") or _DEFAULT_COMPONENT


def _module(state: AgentState):
    """The Component Module for this run — dispatch target for every engineering node."""
    return _registry().get(_component_type(state))


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


def _components_catalogue_text() -> str:
    """The available/coming-soon component catalogue the LLM classifies against."""
    lines: list[str] = []
    for meta in _registry().classify_metadata():
        status = "AVAILABLE" if meta["status"] == "available" else "COMING SOON"
        lines.append(f"- type_id: {meta['type_id']}  [{status}]")
        lines.append(f"  name: {meta['display_name']}")
        lines.append(f"  summary: {meta['summary']}")
        if meta["scope_examples"]:
            lines.append("  example phrasings:")
            lines.extend(f"    * {ex}" for ex in meta["scope_examples"])
    return "\n".join(lines)


def understand_system_prompt() -> str:
    """`understand.md` with the live registry catalogue rendered into {{COMPONENTS}}.

    The node and the LLM-provider tests both build the scope/classification prompt
    through this one function, so they never drift.
    """
    return _load_prompt("understand.md").replace(
        "{{COMPONENTS}}", _components_catalogue_text()
    )


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
    """Scope gate + component classification + plan.

    An explicit picker choice (`requested_component`) forces `component_type`;
    the LLM then only validates scope + produces a type-aware plan. Otherwise the
    LLM classifies the prompt against the registered `available` components. A
    recognised-but-`coming_soon` type or a non-railway/non-engineering request →
    `in_scope=false` with a graceful scope statement.
    """
    tracker = StepTracker(state)
    tracker.mark("Understand", "active", detail="Reading the request")
    requested = state.get("requested_component")
    try:
        system = understand_system_prompt()
        conversation = _conversation(state)
        if requested:
            conversation = (
                f"{conversation}\n\n"
                f"The user explicitly selected the component type '{requested}' from the "
                "picker. Treat that as the component_type (do not re-classify); still "
                "validate that the request is in scope and produce a type-aware plan."
            )
        result = LLMClient().generate(
            conversation, system=system, schema=UnderstandResult, temperature=0.2
        )
        token_usage = _record_llm_call(state, "understand", result)
        parsed: UnderstandResult = result.parsed
        if not parsed.in_scope:
            scope_message = parsed.scope_message or (
                "This platform designs and proof-checks Indian Railways structural "
                "components to IRS codes — that request is outside its current scope."
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

        # An explicit picker choice always wins. Otherwise the classifier MUST
        # resolve the component — a null/unknown classification for an in-scope
        # request is NOT silently defaulted to the culvert (that masks a
        # classification failure as a culvert run). Per component-registry.md the
        # classify call is "1 retry, then fatal (transparent error)": we fail
        # transparently, naming the available components, rather than guessing.
        component_type = requested or parsed.component_type
        if not component_type:
            available = ", ".join(
                meta["type_id"]
                for meta in _registry().classify_metadata()
                if meta["status"] == "available"
            )
            message = (
                "The request is in scope but the platform could not confidently "
                "determine which component to design. Please name the component "
                f"explicitly — the available components are: {available}."
            )
            tracker.mark(
                "Understand", "failed", detail="Unresolved component classification"
            )
            return {
                "steps": tracker.steps,
                "token_usage": token_usage,
                "error": message,
            }
        if not _registry().is_available(component_type):
            # Defensive: an unavailable/unknown classification is out of scope, not a crash.
            scope_message = (
                f"'{component_type}' is not a component this platform currently offers. "
                "It designs and proof-checks the available components listed in the studio."
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
            "component_type": component_type,
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
        module = _module(state)
        param_model = module.param_model
        result = LLMClient().generate(
            _conversation(state),
            system=_load_prompt("extract.md"),
            schema=module.extraction_schema(),
            temperature=0.0,
        )
        token_usage = _record_llm_call(state, "extract", result)
        extracted = {k: v for k, v in result.parsed.model_dump().items() if v is not None}
        outcome = merge_params(
            extracted,
            state.get("prior_params"),
            state.get("preset_values") or {},
            known_fields=frozenset(param_model.model_fields),
            critical_fields=tuple(module.critical_fields),
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
            params = param_model(**outcome.merged)
        except ValidationError as exc:
            message = validation_error_message(exc)
            tracker.mark("Extract", "failed", detail=message)
            return {
                "token_usage": token_usage,
                "steps": tracker.steps,
                "error": f"Parameter validation failed: {message}",
            }
        warnings = module.unusual_value_warnings(params)
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
        tracker.mark("Extract", "done", detail=_extract_detail(params))
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


def _extract_detail(params: BaseModel) -> str:
    """A short, component-neutral 'done' detail from the critical fields."""
    data = params.model_dump()
    # Culvert-friendly summary when the classic fields are present; generic otherwise.
    if {"clear_span_m", "clear_height_m", "cushion_m"} <= set(data):
        return (
            f"{data['clear_span_m']:g} × {data['clear_height_m']:g} m box, "
            f"cushion {data['cushion_m']:g} m"
        )
    return "Parameters extracted"


@_node
def clarify(state: AgentState) -> dict:
    """Deterministic: ONE pointed question, run ends at needs_input (terminal)."""
    tracker = StepTracker(state)
    module = _module(state)
    missing = state["missing_critical"]
    field = next((f for f in module.critical_fields if f in missing), missing[0])
    question = module.clarify_question(field)
    publish(
        state["run_id"], "clarification", {"question": question, "missing_param": field}
    )
    tracker.mark("Extract", "done", detail=f"Needs input — asked for {field}")

    prompt_tokens, completion_tokens = run_totals(state.get("token_usage") or [])
    cost_usd = compute_cost_usd(prompt_tokens, completion_tokens)
    persistence.finish_run(
        state["run_id"],
        status="needs_input",
        component_type=_component_type(state),
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
    """Deterministic engine via the module: sizing, then analysis."""
    tracker = StepTracker(state)
    tracker.mark("Analyse", "active", detail="Running the deterministic engine")
    try:
        module = _module(state)
        _narrate(state, f"Sizing the {module.display_name.lower()}…")
        sizing = module.size(state["params"])
        for warning in sizing.warnings:
            publish(state["run_id"], "warning", {"message": warning})
        geometry = sizing.geometry

        analysis_out = module.analyse(state["params"], geometry)
        analysis = analysis_out.analysis
        _narrate(state, "Running the deterministic engineering analysis…")
        tracker.mark("Analyse", "done", detail="Sizing + analysis complete")
        return {
            "geometry": geometry.model_dump(),
            "analysis": analysis.model_dump(),
            "assumptions": list(state.get("assumptions") or [])
            + [a.model_dump() for a in sizing.assumptions]
            + [a.model_dump() for a in analysis_out.assumptions],
            # Engine-ordered trail segments retained for the calc-sheet composer.
            "trail_segments": [
                [step.model_dump() for step in sizing.trail],
                [step.model_dump() for step in analysis_out.trail],
            ],
            "warnings": list(state.get("warnings") or []) + sizing.warnings,
            "steps": tracker.steps,
        }
    except Exception as exc:
        tracker.mark("Analyse", "failed", detail=str(exc))
        return {"steps": tracker.steps, "error": f"Engine analysis failed: {exc}"}


@_node
def check(state: AgentState) -> dict:
    """Code-checks + the clause-cited calc sheet (streams immediately).

    FAIL rows never fail the run — they flow to the proof-check, which grades
    them (the deliberate under-design demo case depends on this).
    """
    tracker = StepTracker(state)
    tracker.mark("Check", "active", detail="Running code checks")
    try:
        module = _module(state)
        _narrate(state, "Checking members to the component's code set…")
        output = module.run_checks(state["params"], state["geometry"], state["analysis"])

        assumptions = list(state.get("assumptions") or []) + [
            a.model_dump() for a in output.assumptions
        ]
        trail_segments = list(state.get("trail_segments") or []) + [
            [step.model_dump() for step in output.trail]
        ]
        sheet_path = module.compose_calc_sheet(
            params=state["params"],
            geometry=state["geometry"],
            analysis=state["analysis"],
            checks=[row.model_dump() for row in output.checks],
            assumptions=assumptions,
            warnings=list(state.get("warnings") or []),
            trail_segments=trail_segments,
            out_dir=_artifacts_dir(state),
        )
        artefacts = list(state.get("artefacts") or [])
        # The calc sheet streams BEFORE draw/review by node order (calc-sheet.md).
        _emit_artifact(state, artefacts, "calc_sheet", sheet_path, "check")

        failing = [row for row in output.checks if row.status != "PASS"]
        if failing:
            members = _failing_members(module, failing)
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
        return {"steps": tracker.steps, "error": f"Member checks (check node) failed: {exc}"}


def _failing_members(module, failing: list) -> str:
    """Human-readable member list for the FAIL narration.

    Component-agnostic: member labels come from the dispatched module
    (`module.member_labels`), NOT from a direct `engine.checks` import — a shared
    node must never import a component-specific engine (component-registry SC#6).
    A module that declares no labels falls back to the raw member key.
    """
    labels = getattr(module, "member_labels", {}) or {}
    return ", ".join(
        sorted(
            {
                labels.get(getattr(row, "member", ""), getattr(row, "member", ""))
                for row in failing
            }
        )
    )


@_node
def draw(state: AgentState) -> dict:
    tracker = StepTracker(state)
    tracker.mark("Draw", "active", detail="Drawing the GA sheet")
    try:
        module = _module(state)
        run_id = state["run_id"]
        out_dir = _artifacts_dir(state)
        _narrate(state, "Drawing the GA sheet — plan, sections, dimensions…")

        paths = module.draw(state["params"], state["geometry"], out_dir, run_id)

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
    """build123d solid → model.glb + model.step via the module.

    NON-FATAL BY DESIGN (spec/agent.md): on ANY failure — structlog error, one
    `warning` event, and the run continues to review with no model artefacts;
    the 2D artefacts stand alone and the verdict/status are unaffected.
    """
    artefacts = list(state.get("artefacts") or [])
    try:
        module = _module(state)
        out_dir = _artifacts_dir(state)
        _narrate(state, "Building the 3D solid — GLB for the viewer, STEP for CAD…")
        paths = module.model3d(state["geometry"], out_dir)
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
    """The automatic proof-check: module.proof_check → memo narration → type summary.

    The module runs the deterministic FE/independent cross-check and checklist
    and writes its diagram/compliance artefacts. ONE Gemini call narrates the
    memo from the deterministic facts using the module's `memo_prompt()` (1 retry
    with backoff inside the provider, then the run fails transparently). A
    narration that fails the module's grounding validator is NOT fatal — the
    memo falls back to the fully deterministic composition. The verdict is
    computed by rule inside the module, never by the LLM.
    """
    tracker = StepTracker(state)
    tracker.mark("Review", "active", detail="Independent proof-check")
    try:
        module = _module(state)
        out_dir = _artifacts_dir(state)
        artefacts = list(state.get("artefacts") or [])

        _narrate(state, "Re-solving the structure independently (FE cross-check)…")
        proof = module.proof_check(
            params=state["params"],
            geometry=state["geometry"],
            analysis=state["analysis"],
            checks=state.get("checks") or [],
            ga_dxf_path=out_dir / "ga.dxf",
            out_dir=out_dir,
        )
        for kind, filename in proof.artefacts:
            _emit_artifact(state, artefacts, kind, out_dir / filename, "review")

        _narrate(state, "Drafting the proof-check memo…")
        llm = LLMClient().generate(
            proof.memo_facts, system=module.memo_prompt(), temperature=0.2
        )
        token_usage = _record_llm_call(state, "review", llm)
        narration: str | None = (llm.text or "").strip()
        problems = proof.validate_narration(narration)
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
        memo_md = proof.render_memo(narration)
        memo_path = out_dir / proof.memo_filename
        memo_path.write_text(memo_md, encoding="utf-8")
        _emit_artifact(state, artefacts, proof.memo_kind, memo_path, "review")

        type_summary = module.type_summary(
            params=state["params"],
            geometry=state["geometry"],
            analysis=state["analysis"],
            checks=state.get("checks") or [],
            proof=proof,
        )

        if proof.verdict == VERDICT_APPROVAL:
            detail = (
                f"Recommended for approval — FE agreement {proof.fe_agreement_pct:g}%"
            )
        else:
            detail = "Return for revision — major non-conformities found"
        tracker.mark("Review", "done", detail=detail)
        return {
            "fe_comparison": proof.fe_comparison.model_dump() if proof.fe_comparison else None,
            "checklist": list(proof.checklist),
            "verdict": proof.verdict,
            "type_summary": type_summary,
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
    # An out-of-scope run designs NOTHING — it must not carry a *designed*
    # component_type (architecture.md). The `component_type` column is
    # non-nullable with a `box_culvert` default (the schema's neutral "no
    # designed component" sentinel; migrations are out of scope here), so an
    # out-of-scope run resets to that sentinel rather than persisting the
    # picker-seeded type it never designed. Only a completed design persists its
    # own component_type.
    persistence.finish_run(
        state["run_id"],
        status=status,
        component_type=(
            _component_type(state) if status == "completed" else _DEFAULT_COMPONENT
        ),
        plan_text=state.get("plan_text") or None,
        scope_message=state.get("scope_message"),
        params=state.get("params"),
        assumptions=state.get("assumptions"),
        warnings=state.get("warnings"),
        steps=state.get("steps"),
        checks=check_rows or None,
        checklist=state.get("checklist") or None,
        verdict=verdict,
        type_summary=state.get("type_summary"),
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
        component_type=_component_type(state),
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
        component_type=_component_type(state),
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
