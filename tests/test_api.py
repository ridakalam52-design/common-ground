import json

from fastapi.testclient import TestClient

from app.main import app

from .conftest import EXAMPLE

client = TestClient(app)


def test_health_and_index():
    h = client.get("/api/health").json()
    assert h["ok"] and h["mode"] == "mock" and h["planner"] == "scripted"
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200


def test_example():
    assert client.get("/api/example").json() == EXAMPLE


def test_plan_endpoint():
    r = client.post("/api/plan", json=EXAMPLE)
    assert r.status_code == 200
    body = r.json()
    assert body["plan"]["slots"]["dinner"]["pick"]["why"]
    assert any(ev["type"] == "http" for ev in body["trace"])


def test_plan_validation():
    assert client.post("/api/plan", json={"friends": [{"name": "A", "picks": ["x"]}]}).status_code == 422
    dup = {"friends": [{"name": "A", "picks": ["x"]}, {"name": "a", "picks": ["y"]}]}
    assert client.post("/api/plan", json=dup).status_code == 422


def test_plan_stream():
    with client.stream("POST", "/api/plan/stream", json=EXAMPLE) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        text = "".join(r.iter_text())
    events = [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ") and line != "data: {}"]
    types = [e["type"] for e in events]
    assert types[0] == "start" and types[-1] == "plan"
    assert "step" in types and "http" in types
    assert text.rstrip().endswith("event: done\ndata: {}")
