"""Slice (e) backend wiring — _ARTIFACT_MIME registry, the model3d emit-loop over
the returned dict, and the guarded, non-fatal review-stage compose hook.

These pin MY wiring policy only: the model3d node emits WHATEVER keys the module
returns (byte-identical for components that return only the fixed pair); the
review node runs an M-00004-only `module.compose` hook guarded by getattr, inside
its own non-fatal try/except (a raising hook logs + one `warning`, never `error`,
verdict unaffected). The real compose/model3d behaviour is pinned by the
component's own unit suite and the integration gate.
"""

import time
from pathlib import Path
from uuid import uuid4

import pytest

import graph.nodes as nodes_module
from graph.nodes import _ARTIFACT_MIME, model3d, review
from graph.steps import initial_steps
from observability import progress

# The 26 new M-00004 Phase-2 kinds -> mime (capability doc Phase 2 table, normative).
NEW_KINDS = {
    "elevation_dxf": "image/vnd.dxf",
    "elevation_svg": "image/svg+xml",
    "cross_section_dxf": "image/vnd.dxf",
    "cross_section_svg": "image/svg+xml",
    "plan_dxf": "image/vnd.dxf",
    "plan_svg": "image/svg+xml",
    "curtain_wall_dxf": "image/vnd.dxf",
    "curtain_wall_svg": "image/svg+xml",
    "typical_details_dxf": "image/vnd.dxf",
    "typical_details_svg": "image/svg+xml",
    "return_wall_dxf": "image/vnd.dxf",
    "return_wall_svg": "image/svg+xml",
    "bar_shape_table_dxf": "image/vnd.dxf",
    "bar_shape_table_svg": "image/svg+xml",
    "notations_dxf": "image/vnd.dxf",
    "notations_svg": "image/svg+xml",
    "notes_dxf": "image/vnd.dxf",
    "notes_svg": "image/svg+xml",
    "haunch_table_dxf": "image/vnd.dxf",
    "haunch_table_svg": "image/svg+xml",
    "assembly_step": "application/step",
    "box_step": "application/step",
    "curtain_wall_step": "application/step",
    "return_wall_step": "application/step",
    "m00004_ga_sheet": "application/pdf",
    "m00004_bundle": "application/zip",
}


def test_artifact_mime_registers_all_26_new_kinds():
    assert len(NEW_KINDS) == 26
    for kind, mime in NEW_KINDS.items():
        assert kind in _ARTIFACT_MIME, kind
        assert _ARTIFACT_MIME[kind] == mime, kind
    # Phase-1 kinds untouched.
    assert _ARTIFACT_MIME["model_glb"] == "model/gltf-binary"
    assert _ARTIFACT_MIME["m00004_sheet"] == "application/pdf"


def _drain(run_id: str) -> list[dict]:
    progress.publish(run_id, "done", {"status": "completed", "verdict": None})
    return list(progress.stream(run_id))


def _artifact_rows(run_id: str) -> list:
    from db.models import ArtifactRow
    from db.session import create_db_session

    with create_db_session() as session:
        rows = session.query(ArtifactRow).filter(ArtifactRow.run_id == run_id).all()
        return [{"kind": r.kind, "filename": r.filename, "mime": r.mime} for r in rows]


@pytest.fixture
def run_id(tmp_path, monkeypatch) -> str:
    monkeypatch.setenv("AGENT_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    rid = f"test-{uuid4()}"
    progress.register(rid)
    return rid


# --------------------------------------------------------------------------- model3d loop


class _FakeModel3dModule:
    """Returns the full M-00004 STEP set — the node must emit EVERY key."""

    def model3d(self, geometry, out_dir):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        paths = {}
        for kind, name in (
            ("model_glb", "model.glb"),
            ("model_step", "model.step"),
            ("assembly_step", "assembly.step"),
            ("box_step", "box.step"),
            ("curtain_wall_step", "curtain_wall.step"),
            ("return_wall_step", "return_wall.step"),
        ):
            p = out_dir / name
            p.write_bytes(b"solid-bytes")
            paths[kind] = p
        return paths


def test_model3d_node_emits_every_returned_key(run_id, monkeypatch):
    monkeypatch.setattr(nodes_module, "_module", lambda state: _FakeModel3dModule())
    state = {"run_id": run_id, "session_id": "s", "geometry": {}, "artefacts": []}

    updates = model3d(state)

    assert updates.get("error") is None
    emitted = {a["kind"] for a in updates["artefacts"]}
    assert emitted == {
        "model_glb",
        "model_step",
        "assembly_step",
        "box_step",
        "curtain_wall_step",
        "return_wall_step",
    }
    rows = {r["kind"]: r for r in _artifact_rows(run_id)}
    assert rows["assembly_step"]["mime"] == "application/step"
    assert rows["assembly_step"]["filename"] == "assembly.step"


class _MinimalModel3dModule:
    """Legacy contract — only the fixed pair; must stay byte-identical."""

    def model3d(self, geometry, out_dir):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        glb = out_dir / "model.glb"
        glb.write_bytes(b"glTF")
        step = out_dir / "model.step"
        step.write_bytes(b"ISO-10303-21;")
        return {"model_glb": glb, "model_step": step}


def test_model3d_loop_is_byte_identical_for_legacy_two_key_modules(run_id, monkeypatch):
    monkeypatch.setattr(nodes_module, "_module", lambda state: _MinimalModel3dModule())
    state = {"run_id": run_id, "session_id": "s", "geometry": {}, "artefacts": []}

    updates = model3d(state)

    assert [a["kind"] for a in updates["artefacts"]] == ["model_glb", "model_step"]


# --------------------------------------------------------------------------- review compose hook


class _FakeProof:
    verdict = "recommended_for_approval"
    fe_agreement_pct = 100.0
    fe_comparison = None
    checklist: list = []
    artefacts: list = []  # keep empty — no on-disk compliance file needed
    memo_kind = "proof_memo"
    memo_filename = "proof_memo.md"
    memo_facts = "facts"

    @staticmethod
    def validate_narration(narration):
        return []

    @staticmethod
    def render_memo(narration):
        return "DETERMINISTIC MEMO"


class _FakeReviewModule:
    """Minimal module the review node drives, WITH an M-00004-style compose hook."""

    def __init__(self, compose_impl):
        self._compose_impl = compose_impl

    def proof_check(self, **kwargs):
        return _FakeProof()

    def memo_prompt(self):
        return "prompt"

    def type_summary(self, **kwargs):
        return {"ok": True}

    def compose(self, params, geometry, out_dir, run_id):
        return self._compose_impl(out_dir, run_id)


class _FakeLLMClient:
    def __init__(self):
        pass

    def generate(self, prompt, *, system=None, schema=None, temperature=None):
        from llm.client import LLMResult

        return LLMResult(
            text="", parsed=None, prompt_tokens=1, completion_tokens=1, latency_ms=1
        )


def _review_state(run_id, tmp_path):
    out_dir = tmp_path / "artifacts" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    return {
        "run_id": run_id,
        "session_id": "s",
        "params": {},
        "geometry": {},
        "analysis": {},
        "checks": [],
        "artefacts": [],
        "token_usage": [],
        "steps": initial_steps(),
        "started_monotonic": time.monotonic(),
    }


def test_review_runs_compose_hook_and_emits_ga_sheet_and_bundle(
    run_id, tmp_path, monkeypatch
):
    def good_compose(out_dir, rid):
        out_dir = Path(out_dir)
        pdf = out_dir / "m00004_ga_sheet.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        zip_ = out_dir / "m00004_bundle.zip"
        zip_.write_bytes(b"PK\x03\x04")
        return {"m00004_ga_sheet": pdf, "m00004_bundle": zip_}

    module = _FakeReviewModule(good_compose)
    monkeypatch.setattr(nodes_module, "_module", lambda state: module)
    monkeypatch.setattr(nodes_module, "LLMClient", _FakeLLMClient)

    updates = review(_review_state(run_id, tmp_path))

    assert updates.get("error") is None
    assert updates["verdict"] == "recommended_for_approval"
    kinds = [a["kind"] for a in updates["artefacts"]]
    assert "m00004_ga_sheet" in kinds
    assert "m00004_bundle" in kinds
    # ordered after the deterministic memo, at review
    rows = {r["kind"]: r for r in _artifact_rows(run_id)}
    assert rows["m00004_ga_sheet"]["mime"] == "application/pdf"
    assert rows["m00004_bundle"]["mime"] == "application/zip"


def test_review_compose_failure_is_nonfatal_one_warning_no_error(
    run_id, tmp_path, monkeypatch
):
    def boom_compose(out_dir, rid):
        raise RuntimeError("matplotlib backend blew up")

    module = _FakeReviewModule(boom_compose)
    monkeypatch.setattr(nodes_module, "_module", lambda state: module)
    monkeypatch.setattr(nodes_module, "LLMClient", _FakeLLMClient)

    updates = review(_review_state(run_id, tmp_path))

    # NON-FATAL: verdict/type_summary stand, the proof-check is unaffected.
    assert updates.get("error") is None
    assert updates["verdict"] == "recommended_for_approval"
    assert updates["type_summary"] == {"ok": True}
    kinds = [a["kind"] for a in updates["artefacts"]]
    assert "m00004_ga_sheet" not in kinds
    assert "m00004_bundle" not in kinds

    events = _drain(run_id)
    warnings = [e["data"]["message"] for e in events if e["event"] == "warning"]
    compose_warnings = [w for w in warnings if "Composed GA sheet" in w]
    assert len(compose_warnings) == 1
    assert "matplotlib backend blew up" in compose_warnings[0]


class _NoComposeModule:
    """A component WITHOUT a compose hook — the getattr guard must skip it."""

    def proof_check(self, **kwargs):
        return _FakeProof()

    def memo_prompt(self):
        return "prompt"

    def type_summary(self, **kwargs):
        return {"ok": True}


def test_review_skips_compose_for_modules_without_the_hook(run_id, tmp_path, monkeypatch):
    module = _NoComposeModule()
    monkeypatch.setattr(nodes_module, "_module", lambda state: module)
    monkeypatch.setattr(nodes_module, "LLMClient", _FakeLLMClient)

    updates = review(_review_state(run_id, tmp_path))

    assert updates.get("error") is None
    kinds = [a["kind"] for a in updates["artefacts"]]
    assert "m00004_ga_sheet" not in kinds
    assert "m00004_bundle" not in kinds
    events = _drain(run_id)
    warnings = [e["data"]["message"] for e in events if e["event"] == "warning"]
    assert not any("Composed GA sheet" in w for w in warnings)
