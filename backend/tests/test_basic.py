from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok_and_has_request_id():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "x-request-id" in r.headers


def test_llm_check_rejects_missing_token():
    r = client.post("/api/v1/llm/check")
    assert r.status_code in (401, 503)
