"""POST/GET /api/sessions — creation, listing order, derived cost totals."""


def test_create_session_with_title(api_client):
    r = api_client.post("/api/sessions", json={"title": "Bridge 42 culverts"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["session_id"]
    assert data["title"] == "Bridge 42 culverts"
    assert data["created_at"]


def test_create_session_without_title_stores_placeholder(api_client):
    r = api_client.post("/api/sessions", json={})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["title"] == ""


def test_list_sessions_empty(api_client):
    r = api_client.get("/api/sessions")
    assert r.status_code == 200
    assert r.json()["data"]["sessions"] == []


def test_list_sessions_totals_and_order(api_client, make_session_row, make_run_row, utc):
    older = make_session_row(title="older", created_at=utc(0))
    newer = make_session_row(title="newer", created_at=utc(60))
    make_run_row(older, prompt_tokens=1000, completion_tokens=200, cost_usd=0.05)
    make_run_row(older, prompt_tokens=500, completion_tokens=100, cost_usd=0.03)

    r = api_client.get("/api/sessions")
    assert r.status_code == 200
    sessions = r.json()["data"]["sessions"]
    assert [s["title"] for s in sessions] == ["newer", "older"]

    empty, busy = sessions
    assert empty["run_count"] == 0
    assert empty["total_prompt_tokens"] == 0
    assert empty["total_completion_tokens"] == 0
    assert empty["total_cost_usd"] == 0.0

    assert busy["run_count"] == 2
    assert busy["total_prompt_tokens"] == 1500
    assert busy["total_completion_tokens"] == 300
    assert busy["total_cost_usd"] == 0.08
