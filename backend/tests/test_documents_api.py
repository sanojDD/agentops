from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.graph import nodes
from app.main import app

H = {"X-Admin-Token": "test-token"}
TEXT = b"Customers may return any product within 30 days of purchase for a full refund."


def make_client():
    app.dependency_overrides[get_settings] = lambda: Settings(admin_token="test-token")
    return TestClient(app)


def test_documents_require_token():
    c = make_client()
    try:
        assert c.get("/api/v1/documents").status_code == 401
        assert c.post("/api/v1/documents", files={"file": ("a.txt", TEXT)}).status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_upload_list_delete_and_validation():
    c = make_client()
    try:
        r = c.post("/api/v1/documents", files={"file": ("policy.txt", TEXT, "text/plain")}, headers=H)
        assert r.status_code == 201
        doc = r.json()
        assert doc["name"] == "policy.txt" and doc["chunks"] == 1

        listing = c.get("/api/v1/documents", headers=H).json()
        assert listing["total_chunks"] == 1

        bad = c.post("/api/v1/documents", files={"file": ("evil.exe", b"MZ")}, headers=H)
        assert bad.status_code == 415

        assert c.delete(f"/api/v1/documents/{doc['doc_id']}", headers=H).status_code == 204
        assert c.delete(f"/api/v1/documents/{doc['doc_id']}", headers=H).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_upload_then_chat_returns_sources(monkeypatch):
    async def fake(prompt, *, model, max_tokens=64):
        return {"content": "Return products within 30 days of purchase for a full refund [1].",
                "model": "fake", "usage": None}

    monkeypatch.setattr(nodes, "complete", fake)
    c = make_client()
    try:
        c.post("/api/v1/documents", files={"file": ("policy.txt", TEXT)}, headers=H)
        r = c.post("/api/v1/chat", json={"question": "What is the refund policy for returns?"}, headers=H)
        assert r.status_code == 200
        data = r.json()
        assert data["fallback"] is False
        assert data["sources"][0]["doc_name"] == "policy.txt"
        assert data["run_id"]
    finally:
        app.dependency_overrides.clear()
