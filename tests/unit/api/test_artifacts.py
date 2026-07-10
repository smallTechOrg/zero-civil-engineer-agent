"""GET /api/designs/{run_id}/artifacts/{filename} — whitelist, 404s, MIME + disposition."""

import pytest


@pytest.fixture
def run_with_files(make_session_row, make_run_row, artifacts_dir):
    session_id = make_session_row()
    run_id = make_run_row(session_id, status="completed")
    run_dir = artifacts_dir / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "ga.dxf").write_bytes(b"0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n")
    (run_dir / "ga.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>")
    (run_dir / "calc_sheet.json").write_text('{"sections": []}')
    return run_id


def test_non_whitelisted_filename_400(api_client, run_with_files):
    # Traversal is impossible by construction: only these fixed names are ever served,
    # and multi-segment/dot-segment paths never reach the route.
    for bad in ("evil.txt", "ga.pdf", ".env", "agent.db", "GA.dxf"):
        r = api_client.get(f"/api/designs/{run_with_files}/artifacts/{bad}")
        assert r.status_code == 400, bad
        assert r.json()["detail"]["code"] == "INVALID_FILENAME"


def test_unknown_run_404(api_client):
    r = api_client.get("/api/designs/no-such-run/artifacts/ga.dxf")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_not_yet_generated_404(api_client, run_with_files):
    r = api_client.get(f"/api/designs/{run_with_files}/artifacts/model.glb")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_dxf_served_as_attachment(api_client, run_with_files):
    r = api_client.get(f"/api/designs/{run_with_files}/artifacts/ga.dxf")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/vnd.dxf")
    assert r.headers["content-disposition"] == 'attachment; filename="ga.dxf"'
    assert b"ENTITIES" in r.content


def test_svg_served_inline(api_client, run_with_files):
    r = api_client.get(f"/api/designs/{run_with_files}/artifacts/ga.svg")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert r.headers["content-disposition"] == 'inline; filename="ga.svg"'
    assert "<svg" in r.text


def test_json_served_inline(api_client, run_with_files):
    r = api_client.get(f"/api/designs/{run_with_files}/artifacts/calc_sheet.json")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.headers["content-disposition"] == 'inline; filename="calc_sheet.json"'
