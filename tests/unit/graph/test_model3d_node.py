"""model3d — the Phase-3 REAL node: GLB + STEP artefacts, NON-FATAL failure policy.

`model3d.generate_solid` itself is faked (its real geometry/export behaviour is
pinned by tests/unit/model3d/ and the integration suite); these tests pin MY
wiring policy: artefact rows + SSE events on success, warning-and-continue on
ANY failure, no `error` state ever, and NO step events either way (the Draw UI
step is already 'done' from the draw node — the Phase-2 skipped tag is gone).
"""

import time
from pathlib import Path
from uuid import uuid4

import pytest

import model3d as model3d_pkg
from domain.culvert import BoxGeometry, CulvertParams
from engine import size_culvert
from graph.nodes import model3d
from graph.steps import initial_steps
from observability import progress

GLB_BYTES = b"glTF" + bytes(60)  # binary glTF magic + padding
STEP_BYTES = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"
PRIOR_ARTEFACTS = [
    {"kind": "calc_sheet", "filename": "calc_sheet.json"},
    {"kind": "ga_dxf", "filename": "ga.dxf"},
    {"kind": "ga_svg", "filename": "ga.svg"},
]


@pytest.fixture
def state(tmp_path, monkeypatch) -> dict:
    monkeypatch.setenv("AGENT_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    geometry = size_culvert(
        CulvertParams(clear_span_m=4.0, clear_height_m=3.0, cushion_m=2.5)
    ).geometry
    steps = initial_steps()
    for step in steps:
        if step["name"] in ("Understand", "Extract", "Analyse", "Check", "Draw"):
            step["status"] = "done"
    run_id = f"test-{uuid4()}"
    progress.register(run_id)
    return {
        "run_id": run_id,
        "session_id": "unit-session",
        "geometry": geometry.model_dump(),
        "artefacts": list(PRIOR_ARTEFACTS),
        "steps": steps,
        "started_monotonic": time.monotonic(),
    }


def _drain(run_id: str) -> list[dict]:
    progress.publish(run_id, "done", {"status": "completed", "verdict": None})
    return list(progress.stream(run_id))


def _artifact_rows(run_id: str) -> list:
    from db.models import ArtifactRow
    from db.session import create_db_session

    with create_db_session() as session:
        rows = session.query(ArtifactRow).filter(ArtifactRow.run_id == run_id).all()
        return [
            {"kind": r.kind, "filename": r.filename, "mime": r.mime, "size_bytes": r.size_bytes}
            for r in rows
        ]


def _fake_generate(calls: list):
    def fake(geometry, out_dir):
        calls.append(geometry)
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        glb = out_dir / "model.glb"
        glb.write_bytes(GLB_BYTES)
        step = out_dir / "model.step"
        step.write_bytes(STEP_BYTES)
        return {"model_glb": glb, "model_step": step}

    return fake


def test_success_records_both_artifact_rows_and_events(state, monkeypatch, tmp_path):
    calls: list = []
    monkeypatch.setattr(model3d_pkg, "generate_solid", _fake_generate(calls))

    updates = model3d(state)

    assert updates.get("error") is None
    # The generator received the run's typed BoxGeometry and the run's artifacts dir
    assert isinstance(calls[0], BoxGeometry)
    assert calls[0].clear_span_m == 4.0
    run_dir = tmp_path / "artifacts" / state["run_id"]
    assert (run_dir / "model.glb").read_bytes().startswith(b"glTF")
    assert (run_dir / "model.step").read_bytes().startswith(b"ISO-10303-21")

    # State: model artefacts appended after the existing 2D set
    assert updates["artefacts"][:3] == PRIOR_ARTEFACTS
    assert updates["artefacts"][3:] == [
        {"kind": "model_glb", "filename": "model.glb"},
        {"kind": "model_step", "filename": "model.step"},
    ]

    # DB rows with the spec/data.md kinds + mimes
    rows = {r["kind"]: r for r in _artifact_rows(state["run_id"])}
    assert set(rows) == {"model_glb", "model_step"}
    assert rows["model_glb"]["filename"] == "model.glb"
    assert rows["model_glb"]["mime"] == "model/gltf-binary"
    assert rows["model_step"]["filename"] == "model.step"
    assert rows["model_step"]["mime"] == "application/step"
    assert all(r["size_bytes"] > 0 for r in rows.values())

    events = _drain(state["run_id"])
    artefact_events = [e["data"] for e in events if e["event"] == "artefact"]
    assert [a["kind"] for a in artefact_events] == ["model_glb", "model_step"]
    for data in artefact_events:
        assert data["url"] == f"/api/designs/{state['run_id']}/artifacts/{data['filename']}"
    assert [e for e in events if e["event"] == "warning"] == []


def test_success_publishes_no_step_event_and_never_touches_steps(state, monkeypatch):
    """The Phase-2 'Draw skipped — coming in Phase 3' tag is GONE: a raw-SSE
    consumer must never see a Draw event after the drawing is done."""
    monkeypatch.setattr(model3d_pkg, "generate_solid", _fake_generate([]))

    updates = model3d(state)

    assert "steps" not in updates  # the node no longer mutates the tracker
    events = _drain(state["run_id"])
    assert [e for e in events if e["event"] == "step"] == []
    assert not any(
        "Phase 3" in str(e["data"]) for e in events if e["event"] != "done"
    )


@pytest.mark.parametrize(
    "exc",
    [
        model3d_pkg.InvalidGeometryError("wall thickness must be positive, got -1"),
        model3d_pkg.SolidVerificationError("solid volume disagrees with analytic value"),
        model3d_pkg.ModelExportError("build123d failed to export binary glTF"),
        RuntimeError("CAD kernel crashed"),
    ],
    ids=["invalid-geometry", "verification", "export", "unexpected"],
)
def test_any_failure_is_nonfatal_warning_and_run_continues(state, monkeypatch, exc):
    def boom(geometry, out_dir):
        raise exc

    monkeypatch.setattr(model3d_pkg, "generate_solid", boom)

    updates = model3d(state)

    assert updates.get("error") is None  # NEVER routes to handle_error
    assert updates["artefacts"] == PRIOR_ARTEFACTS  # 2D artefacts stand, nothing added
    assert _artifact_rows(state["run_id"]) == []

    events = _drain(state["run_id"])
    warnings = [e["data"]["message"] for e in events if e["event"] == "warning"]
    assert len(warnings) == 1
    assert "3D model generation failed" in warnings[0]
    assert "2D artefacts stand" in warnings[0]
    assert str(exc) in warnings[0]  # transparent: the reason is named
    assert [e for e in events if e["event"] == "step"] == []
    assert [e for e in events if e["event"] == "artefact"] == []


def test_failure_keeps_draw_step_done(state, monkeypatch):
    monkeypatch.setattr(
        model3d_pkg, "generate_solid", lambda g, o: (_ for _ in ()).throw(RuntimeError("x"))
    )

    updates = model3d(state)

    assert "steps" not in updates
    draw = next(s for s in state["steps"] if s["name"] == "Draw")
    assert draw["status"] == "done"
    _drain(state["run_id"])
