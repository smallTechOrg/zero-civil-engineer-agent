"""Full-pipeline runs — real Gemini, tmp DB, real artefacts on disk.

Phase 2: the canonical run exercises the WHOLE pipeline (sizing, frame
analysis, IRS CBC checks + calc sheet, GA drawing, FE cross-check, 12-item
proof-check, grounded memo, verdict) and the under-design demo act proves the
user-triggered design → review → revise loop. Phase 3 adds the real 3D solid
(model.glb + model.step, non-fatal) and the finalize refinement suggestions.
"""

import json
import re
from pathlib import Path

import ezdxf

CANONICAL_PROMPT = (
    "single box culvert, 4 m clear span, 3 m height, 2.5 m cushion, "
    "BG single line, 25t loading"
)
UNDER_DESIGN_PROMPT = (
    "single box culvert, 4 m clear span, 3 m height, 2.5 m cushion, "
    "BG single line, 25t loading, top slab only 200 mm"
)

VERDICTS = {"recommended_for_approval", "return_for_revision"}
# spec/api.md checks[] row shape — exactly these keys are persisted.
CHECK_ROW_KEYS = {"clause", "requirement", "computed", "limit", "status"}
# The pinned full checklist item shape (frontend pre-paints its matrix from these).
CHECKLIST_ITEM_KEYS = {
    "item", "title", "clause", "requirement", "computed", "limit", "severity", "detail",
}
PHASE2_ARTEFACTS = (
    "ga.dxf", "ga.svg", "calc_sheet.json", "compliance.json",
    "proof_memo.md", "bmd.svg", "sfd.svg",
)
PHASE3_ARTEFACTS = PHASE2_ARTEFACTS + ("model.glb", "model.step")
ARTIFACT_KINDS = {
    "ga_dxf", "ga_svg", "calc_sheet", "compliance", "proof_memo",
    "bmd_svg", "sfd_svg", "model_glb", "model_step",
}


def _assert_suggestions_valid(row: dict) -> list[str]:
    """2–3 persisted chips, each non-empty, ≤160 chars, no list prefix — the
    deterministic contract only; LLM prose is never over-asserted."""
    assert row["suggestions_json"], "completed run has no suggestions_json"
    suggestions = json.loads(row["suggestions_json"])
    assert 2 <= len(suggestions) <= 3, suggestions
    for chip in suggestions:
        assert isinstance(chip, str) and chip.strip(), suggestions
        assert len(chip) <= 160, chip
        assert not re.match(r"^\s*(?:[-*•]|\(\d+\)|\d+\s*[.)\]:])", chip), chip
    return suggestions


def _params(row: dict) -> dict:
    assert row["params_json"], f"run {row['id']} has no params_json"
    return json.loads(row["params_json"])


def _steps(row: dict) -> dict:
    return {s["name"]: s["status"] for s in json.loads(row["steps_json"])}


def _artifact_dir(settings, run_id: str) -> Path:
    return Path(settings.artifacts_dir) / run_id


def _assert_memo_is_grounded(row: dict, art_dir: Path) -> None:
    """The memo on disk passes the grounding validator against the STORED
    checklist — end-to-end proof that no LLM-invented number reached the memo."""
    from domain.culvert import Assumption, CulvertParams
    from engine import size_culvert
    from proofcheck import memo_facts, validate_narration
    from proofcheck.checklist import ChecklistItem, ProofCheckResult, reference_lines

    params = CulvertParams(**_params(row))
    geometry = size_culvert(params).geometry  # deterministic — same as the run's
    compliance = json.loads((art_dir / "compliance.json").read_text(encoding="utf-8"))
    result = ProofCheckResult(
        items=[ChecklistItem(**item) for item in json.loads(row["checklist_json"])],
        verdict=row["verdict"],
        fe_agreement_pct=compliance["fe_agreement_pct"],
        grounding_text="\n".join(reference_lines(params, geometry)),
    )
    facts = memo_facts(
        result,
        params=params,
        geometry=geometry,
        warnings=json.loads(row["warnings_json"] or "[]"),
        assumptions=[Assumption(**a) for a in json.loads(row["assumptions_json"] or "[]")],
    )
    memo = (art_dir / "proof_memo.md").read_text(encoding="utf-8")
    problems = validate_narration(memo, result, extra_facts=facts)
    assert problems == [], f"memo failed grounding: {problems}"


def test_canonical_prompt_completes_end_to_end(
    require_gemini, drawing_ready, make_session, run_and_wait, get_run,
    get_artifacts, _integration_settings,
):
    session_id = make_session()

    run_id, events = run_and_wait(session_id, CANONICAL_PROMPT)

    # Terminal event carries the rule-computed verdict (spec/api.md `done`)
    assert events[-1]["event"] == "done", f"events: {[e['event'] for e in events]}"
    assert events[-1]["data"] == {
        "status": "completed", "verdict": "recommended_for_approval",
    }
    row = get_run(run_id)
    assert row["status"] == "completed"
    assert row["verdict"] == "recommended_for_approval"

    # Extraction: the canonical parameters, exactly
    params = _params(row)
    assert params["clear_span_m"] == 4.0
    assert params["clear_height_m"] == 3.0
    assert params["cushion_m"] == 2.5
    assert params["gauge"] == "BG"
    assert params["loading_standard"] == "25t-2008"

    # Accounting: 4 real LLM calls (understand + extract + review memo + suggestions)
    assert row["prompt_tokens"] > 0
    assert row["cost_usd"] > 0
    assert row["completed_at"] is not None
    token_events = [e["data"] for e in events if e["event"] == "tokens"]
    assert len(token_events) >= 5  # understand + extract + review + suggestions + finalize total
    assert token_events[-1]["cost_usd"] > 0
    assert token_events[-1]["session_total_cost_usd"] >= token_events[-1]["cost_usd"]

    # The 60 s budget (spec/roadmap.md success criterion)
    print(f"\ncanonical full-run duration: {row['duration_ms']} ms")
    assert 0 < row["duration_ms"] < 60_000

    # Step tracker: every real step done; the Phase-2 'Draw skipped' tag is GONE
    steps = _steps(row)
    for name in ("Understand", "Extract", "Analyse", "Check", "Draw", "Review"):
        assert steps[name] == "done", f"{name}: {steps[name]}"
    step_events = [e["data"] for e in events if e["event"] == "step"]
    assert not any(s["status"] == "skipped" for s in step_events), step_events

    # Artefacts on disk: the full Phase-3 set; the DXF still audits clean
    art_dir = _artifact_dir(_integration_settings, run_id)
    for filename in PHASE3_ARTEFACTS:
        path = art_dir / filename
        assert path.exists() and path.stat().st_size > 0, filename
    auditor = ezdxf.readfile(art_dir / "ga.dxf").audit()
    assert not auditor.has_errors, [str(e) for e in auditor.errors]

    # The 3D artefacts are genuine: binary glTF magic + STEP ISO-10303-21 header
    assert (art_dir / "model.glb").read_bytes()[:4] == b"glTF"
    step_head = (art_dir / "model.step").read_text(encoding="utf-8", errors="replace")
    assert step_head.startswith("ISO-10303-21")

    # Artefact DB rows + SSE events with the API-contract URL shape
    artifacts = get_artifacts(run_id)
    assert {a["kind"] for a in artifacts} == ARTIFACT_KINDS
    assert all(a["size_bytes"] > 0 for a in artifacts)
    mimes = {a["kind"]: a["mime"] for a in artifacts}
    assert mimes["model_glb"] == "model/gltf-binary"
    assert mimes["model_step"] == "application/step"
    artefact_events = [e["data"] for e in events if e["event"] == "artefact"]
    for data in artefact_events:
        assert data["url"] == f"/api/designs/{run_id}/artifacts/{data['filename']}"

    # SSE ordering: the calc sheet streams BEFORE the drawing, then the 3D pair,
    # then the proof-check outputs (calc-sheet.md success criterion)
    kinds = [a["kind"] for a in artefact_events]
    assert kinds == [
        "calc_sheet", "ga_dxf", "ga_svg", "model_glb", "model_step",
        "bmd_svg", "sfd_svg", "compliance", "proof_memo",
    ]
    assert kinds.index("calc_sheet") < kinds.index("ga_svg") < kinds.index("compliance")

    # Phase 3: 2–3 valid refinement suggestions persisted AND served in the snapshot
    suggestions = _assert_suggestions_valid(row)
    from fastapi.testclient import TestClient

    from api import app

    with TestClient(app) as client:
        snapshot = client.get(f"/api/designs/{run_id}").json()["data"]
    assert snapshot["suggestions"] == suggestions
    assert {a["kind"] for a in snapshot["artefacts"]} == ARTIFACT_KINDS
    # `done` itself stays the exact spec/api.md payload (no suggestions field)
    assert set(events[-1]["data"]) == {"status", "verdict"}

    # checks_json: 13 IRS CBC rows, all PASS, exactly the api.md keys
    checks = json.loads(row["checks_json"])
    assert len(checks) == 13
    for check_row in checks:
        assert set(check_row) == CHECK_ROW_KEYS
        assert check_row["status"] == "PASS"
        assert check_row["clause"] and check_row["computed"] and check_row["limit"]

    # checklist_json: the 12 pinned full-field items; sound design ⇒ no non-conformity
    checklist = json.loads(row["checklist_json"])
    assert [item["item"] for item in checklist] == list(range(1, 13))
    for item in checklist:
        assert set(item) == CHECKLIST_ITEM_KEYS
        assert item["severity"] in {"PASS", "OBSERVATION"}

    # calc sheet: four sections, member-check lines carry status
    sheet = json.loads((art_dir / "calc_sheet.json").read_text(encoding="utf-8"))
    assert [s["id"] for s in sheet["sections"]] == [
        "design_basis", "loading", "analysis", "member_checks",
    ]

    # Memo grounding, end to end against the STORED run record
    _assert_memo_is_grounded(row, art_dir)

    # The design plan still streams before extraction completes (Phase-1 regression)
    event_kinds = [
        (e["event"], e["data"].get("step"), e["data"].get("status")) for e in events
    ]
    first_narration = next(i for i, e in enumerate(events) if e["event"] == "narration")
    extract_done = next(
        i for i, k in enumerate(event_kinds) if k == ("step", "Extract", "done")
    )
    assert first_narration < extract_done


def test_under_design_is_caught_then_revised_to_approval(
    require_gemini, drawing_ready, make_session, run_and_wait, get_run,
    _integration_settings,
):
    """The demo money-shot: thin top slab → return_for_revision naming the top
    slab; the user-triggered revise turn recovers the verdict (proof-check.md)."""
    session_id = make_session()

    run_id, events = run_and_wait(session_id, UNDER_DESIGN_PROMPT)

    # Completed WITH warnings — an under-design is graded, never silently fixed
    assert events[-1]["data"] == {
        "status": "completed", "verdict": "return_for_revision",
    }
    row = get_run(run_id)
    assert row["status"] == "completed"
    assert row["verdict"] == "return_for_revision"
    assert _params(row)["top_slab_thickness_mm"] == 200.0

    warnings = json.loads(row["warnings_json"])
    assert any("thinner" in w.lower() for w in warnings)
    warning_events = [e["data"]["message"] for e in events if e["event"] == "warning"]
    assert any("thinner" in message.lower() for message in warning_events)

    # FAIL check rows name the top slab (api.md keys only — member is in the text)
    checks = json.loads(row["checks_json"])
    failing = [c for c in checks if c["status"] == "FAIL"]
    assert failing
    assert all("Top slab" in c["requirement"] for c in failing)

    # Flexure/shear graded MAJOR; the memo names the failing member
    checklist = {item["item"]: item for item in json.loads(row["checklist_json"])}
    assert checklist[7]["severity"] == "NON_CONFORMITY_MAJOR"
    assert checklist[8]["severity"] == "NON_CONFORMITY_MAJOR"
    art_dir = _artifact_dir(_integration_settings, run_id)
    memo = (art_dir / "proof_memo.md").read_text(encoding="utf-8")
    assert "RETURN FOR REVISION" in memo
    assert "top slab" in memo.lower()
    _assert_memo_is_grounded(row, art_dir)

    # A return_for_revision run still gets its chips (content not over-asserted —
    # suggest.md steers the first one at the failing member).
    _assert_suggestions_valid(row)

    # The revise loop: a corrective refinement in the SAME session recovers
    revise_id, revise_events = run_and_wait(session_id, "increase the top slab to 450 mm")

    assert revise_events[-1]["data"] == {
        "status": "completed", "verdict": "recommended_for_approval",
    }
    revise_row = get_run(revise_id)
    revise_params = _params(revise_row)
    assert revise_params["top_slab_thickness_mm"] == 450.0
    assert revise_params["clear_span_m"] == 4.0     # carried forward
    assert revise_params["cushion_m"] == 2.5        # carried forward
    assert all(
        c["status"] == "PASS" for c in json.loads(revise_row["checks_json"])
    )
    revise_memo = (
        _artifact_dir(_integration_settings, revise_id) / "proof_memo.md"
    ).read_text(encoding="utf-8")
    assert "RECOMMENDED FOR APPROVAL" in revise_memo


def test_refinement_turn_carries_params_forward_and_regenerates(
    require_gemini, drawing_ready, make_session, run_and_wait, get_run,
    _integration_settings,
):
    session_id = make_session()
    first_id, first_events = run_and_wait(session_id, CANONICAL_PROMPT)
    assert first_events[-1]["data"]["status"] == "completed"

    second_id, second_events = run_and_wait(session_id, "increase the fill to 4 m")

    done = second_events[-1]["data"]
    assert done["status"] == "completed"
    # Check-governed sizing (Phase-2 audit fix): the engine's own design at
    # 4 m fill passes its own checks (slabs 400 -> 450 mm), so the scripted
    # refinement the user already tested stays green.
    assert done["verdict"] == "recommended_for_approval"
    second = get_run(second_id)
    assert second["verdict"] == "recommended_for_approval"
    params = _params(second)
    assert params["cushion_m"] == 4.0            # the one named change
    assert params["clear_span_m"] == 4.0         # carried forward
    assert params["clear_height_m"] == 3.0       # carried forward

    # Full regeneration: the new run has its own FULL Phase-3 artefact set on disk
    art_dir = _artifact_dir(_integration_settings, second_id)
    for filename in PHASE3_ARTEFACTS:
        assert (art_dir / filename).exists(), filename

    # History intact: both runs keep their own params (audit trail)
    first = get_run(first_id)
    assert _params(first)["cushion_m"] == 2.5

    # Session cost total now spans both persisted runs
    final_tokens = [e["data"] for e in second_events if e["event"] == "tokens"][-1]
    assert final_tokens["session_total_cost_usd"] > final_tokens["cost_usd"]


def test_clarification_answer_completes_the_original_request(
    require_gemini, drawing_ready, make_session, run_and_wait, get_run,
    _integration_settings,
):
    session_id = make_session()
    first_id, first_events = run_and_wait(session_id, "box culvert 3 m height, 2 m cushion")
    assert first_events[-1]["data"] == {"status": "needs_input", "verdict": None}

    second_id, second_events = run_and_wait(session_id, "4.5 m")

    done = second_events[-1]["data"]
    assert done["status"] == "completed"
    assert done["verdict"] in VERDICTS
    params = _params(get_run(second_id))
    assert params["clear_span_m"] == 4.5         # the answer
    assert params["clear_height_m"] == 3.0       # from the original request
    assert params["cushion_m"] == 2.0            # from the original request
    assert (_artifact_dir(_integration_settings, second_id) / "ga.dxf").exists()
    assert (_artifact_dir(_integration_settings, second_id) / "proof_memo.md").exists()


def test_model3d_failure_is_nonfatal_and_2d_artefacts_stand(
    require_gemini, drawing_ready, make_session, run_and_wait, get_run,
    get_artifacts, _integration_settings, monkeypatch,
):
    """model-3d.md hard case: simulated export failure → warning event, run
    completes with verdict intact, NO model rows, Drawing/Calc/Proof-Check and
    the suggestions all unaffected."""
    import model3d as model3d_pkg

    def boom(geometry, out_dir):
        raise model3d_pkg.ModelExportError("simulated export failure (injected by test)")

    monkeypatch.setattr(model3d_pkg, "generate_solid", boom)
    session_id = make_session()

    run_id, events = run_and_wait(session_id, CANONICAL_PROMPT)

    # The run's status and rule-computed verdict are untouched by the 3D failure
    assert events[-1]["data"] == {
        "status": "completed", "verdict": "recommended_for_approval",
    }
    row = get_run(run_id)
    assert row["status"] == "completed"
    assert row["verdict"] == "recommended_for_approval"
    assert row["error_message"] is None

    # Exactly the non-fatal warning, naming the reason
    warning_events = [e["data"]["message"] for e in events if e["event"] == "warning"]
    failures = [m for m in warning_events if "3D model generation failed" in m]
    assert len(failures) == 1
    assert "2D artefacts stand" in failures[0]
    assert "simulated export failure" in failures[0]

    # No model rows, no model files — the 2D set stands complete
    kinds = {a["kind"] for a in get_artifacts(run_id)}
    assert kinds == ARTIFACT_KINDS - {"model_glb", "model_step"}
    art_dir = _artifact_dir(_integration_settings, run_id)
    for filename in PHASE2_ARTEFACTS:
        assert (art_dir / filename).exists(), filename
    assert not (art_dir / "model.glb").exists()
    assert not (art_dir / "model.step").exists()

    # Finalize still ran its suggestions call — the run is fully completed
    _assert_suggestions_valid(row)


def test_abnormally_high_cushion_is_flagged_and_run_proceeds(
    require_gemini, drawing_ready, make_session, run_and_wait, get_run,
    _integration_settings,
):
    session_id = make_session()

    run_id, events = run_and_wait(
        session_id, "box culvert 4000 mm clear span, 3 m height, 9 m cushion"
    )

    done = events[-1]["data"]
    assert done["status"] == "completed"
    assert done["verdict"] in VERDICTS  # flagged and graded — never blocked
    row = get_run(run_id)
    params = _params(row)
    assert params["clear_span_m"] == 4.0         # mm → m conversion
    assert params["cushion_m"] == 9.0

    warning_events = [e["data"]["message"] for e in events if e["event"] == "warning"]
    assert any("ushion" in message for message in warning_events)
    warnings = json.loads(row["warnings_json"])
    assert any("ushion" in message for message in warnings)
    assert (_artifact_dir(_integration_settings, run_id) / "ga.dxf").exists()
