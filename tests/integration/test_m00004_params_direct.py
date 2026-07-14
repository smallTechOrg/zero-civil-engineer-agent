"""M-00004 params-direct full run + NL regression — real Gemini, real artefacts.

The params-direct half depends on sibling slice (a): the `m00004_box_culvert`
module must be registered. When it is not yet on disk the `m00004_ready` guard
skips those tests. The NL-regression test never depends on slice (a) — it proves
the natural-language culvert run still routes via `understand` unchanged.
"""

import threading
from pathlib import Path

import ezdxf
import pytest

from observability import progress

M00004_TYPE = "m00004_box_culvert"
CANONICAL_PROMPT = (
    "single box culvert, 4 m clear span, 3 m height, 2.5 m cushion, "
    "BG single line, 25t loading"
)


@pytest.fixture
def m00004_ready():
    """Skip until sibling slice (a) registers the standard box-culvert module."""
    import components  # noqa: F401  (populates the registry at import)
    from components import registry

    if not registry.has(M00004_TYPE):
        pytest.skip("m00004_box_culvert not yet registered — pending sibling slice (a)")


def _drain(run_id: str, events: list, timeout: float) -> None:
    consumer = threading.Thread(
        target=lambda: events.extend(progress.stream(run_id)), daemon=True
    )
    consumer.start()
    consumer.join(timeout)
    if consumer.is_alive():
        pytest.fail(
            f"run {run_id} did not finish within {timeout}s — "
            f"events so far: {[e['event'] for e in events]}"
        )


def _run_params_direct(session_id: str, params: dict, timeout: float = 300.0):
    from graph.runner import start_design_run

    run_id = start_design_run(
        session_id,
        "M-00004 standard box culvert 4x4 m, fill 2 m",
        requested_component=M00004_TYPE,
        params=params,
    )
    events: list[dict] = []
    _drain(run_id, events, timeout)
    return run_id, events


def _steps(row: dict) -> dict:
    import json

    return {s["name"]: s for s in json.loads(row["steps_json"])}


def test_params_direct_run_completes_with_zero_llm_intake(
    require_gemini, drawing_ready, m00004_ready, make_session, get_run,
    get_artifacts, _integration_settings, monkeypatch,
):
    # Spy on EVERY LLM call to prove the intake nodes never fire on this path.
    from graph import nodes as graph_nodes
    from llm.client import LLMClient

    seen_systems: list[str] = []
    original_generate = LLMClient.generate

    def spy(self, prompt, *args, system=None, **kwargs):
        seen_systems.append(system or "")
        return original_generate(self, prompt, *args, system=system, **kwargs)

    monkeypatch.setattr(LLMClient, "generate", spy)

    session_id = make_session()
    params = {
        "clear_span_m": 4.0,
        "clear_height_m": 4.0,
        "cushion_m": 2.0,
        "surcharge_kn_m2": 0.0,
    }
    run_id, events = _run_params_direct(session_id, params)

    assert events[-1]["event"] == "done", [e["event"] for e in events]
    assert events[-1]["data"]["status"] == "completed"

    row = get_run(run_id)
    assert row["status"] == "completed"

    # Zero LLM intake: neither the understand nor extract nor suggest system
    # prompt was ever sent (the memo narration may be the only LLM call).
    intake_systems = {
        graph_nodes.understand_system_prompt(),
        graph_nodes._load_prompt("extract.md"),
        graph_nodes._load_prompt("suggest.md"),
    }
    assert not (set(seen_systems) & intake_systems), (
        "an intake/suggestion LLM call fired on the params-direct path"
    )

    # The Understand + Extract steps completed via seed_params (form detail).
    steps = _steps(row)
    assert steps["Understand"]["status"] == "done"
    assert steps["Extract"]["status"] == "done"
    assert "parameter form" in steps["Understand"]["detail"].lower()

    # Config selection: (4, 4, 2, 0) → F2_4x4 (from the run snapshot type_summary).
    from fastapi.testclient import TestClient

    from api import app

    with TestClient(app) as client:
        snapshot = client.get(f"/api/designs/{run_id}").json()["data"]
    assert snapshot["type_summary"]["config_id"] == "F2_4x4", snapshot["type_summary"]

    # Artefacts on disk: the PDF sheet is a real, non-empty PDF; the DXF reopens;
    # the GLB is a valid non-empty binary glTF.
    art_dir = Path(_integration_settings.artifacts_dir) / run_id
    pdf = art_dir / "m00004_sheet.pdf"
    assert pdf.exists() and pdf.stat().st_size > 0
    assert pdf.read_bytes()[:4] == b"%PDF"
    assert ezdxf.readfile(art_dir / "ga.dxf") is not None
    glb = art_dir / "model.glb"
    assert glb.exists() and glb.stat().st_size > 0
    assert glb.read_bytes()[:4] == b"glTF"

    # The PDF artefact is recorded as a first-class artefact row/kind.
    kinds = {a["kind"] for a in get_artifacts(run_id)}
    assert "m00004_sheet" in kinds

    # --- Phase 2 slice (e) wiring: the full GA package flows through the graph ---
    # The ten per-diagram DXF/SVG pairs are deterministic (ezdxf) — always emitted
    # by the draw node via the extra-key auto-emit + _ARTIFACT_MIME registration.
    diagram_kinds = {
        f"{d}_{ext}"
        for d in (
            "elevation", "cross_section", "plan", "curtain_wall", "typical_details",
            "return_wall", "bar_shape_table", "notations", "notes", "haunch_table",
        )
        for ext in ("dxf", "svg")
    }
    assert diagram_kinds <= kinds, diagram_kinds - kinds
    # A couple of the per-diagram DXFs round-trip through ezdxf.
    assert ezdxf.readfile(art_dir / "elevation.dxf") is not None
    assert ezdxf.readfile(art_dir / "cross_section.dxf") is not None

    # The multi-body STEP parts flow through the model3d emit-loop (loops the
    # returned dict, no longer the hardcoded pair).
    step_kinds = {"assembly_step", "box_step", "curtain_wall_step", "return_wall_step"}
    assert step_kinds <= kinds, step_kinds - kinds
    for name in ("assembly.step", "box.step", "curtain_wall.step", "return_wall.step"):
        part = art_dir / name
        assert part.exists() and part.stat().st_size > 0, name
        assert part.read_bytes()[:13] == b"ISO-10303-21;", name

    # The review-stage composed sheet + zip bundle (guarded, non-fatal hook).
    assert {"m00004_ga_sheet", "m00004_bundle"} <= kinds
    ga_pdf = art_dir / "m00004_ga_sheet.pdf"
    assert ga_pdf.exists() and ga_pdf.stat().st_size > 0
    assert ga_pdf.read_bytes()[:4] == b"%PDF"
    bundle = art_dir / "m00004_bundle.zip"
    assert bundle.exists() and bundle.stat().st_size > 0
    import zipfile

    assert zipfile.is_zipfile(bundle)


def test_canonical_nl_culvert_still_routes_via_understand(
    require_gemini, drawing_ready, make_session, run_and_wait, get_run,
):
    """Regression: the natural-language culvert run is byte-identical — it enters
    `understand` (NOT seed_params) and completes."""
    session_id = make_session()
    run_id, events = run_and_wait(session_id, CANONICAL_PROMPT)

    assert events[-1]["data"]["status"] == "completed"
    row = get_run(run_id)
    steps = _steps(row)
    assert steps["Understand"]["status"] == "done"
    # The NL path never carries the params-form detail — it ran the LLM intake.
    detail = (steps["Understand"]["detail"] or "").lower()
    assert "parameter form" not in detail
