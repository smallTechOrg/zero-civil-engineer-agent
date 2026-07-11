"""Liveness + envelope shape — coverage moved from the deleted skeleton test_api.py."""


def test_health(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["status"] == "ok"
    assert body["error"] is None


def test_legacy_runs_route_is_gone(api_client):
    assert api_client.post("/runs", json={"input_text": "x"}).status_code in (404, 405)
    assert api_client.get("/runs/abc").status_code == 404


def test_root_redirects_to_app(api_client):
    """Bare domain → the SPA at /app/ (for the custom-domain / load-balancer setup)."""
    r = api_client.get("/", follow_redirects=False)
    assert r.status_code in (307, 308)
    assert r.headers["location"] == "/app/"
