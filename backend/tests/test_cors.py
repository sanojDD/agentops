import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.cors import add_cors, parse_origins

ALLOWED = "https://agentops-web.onrender.com"


def make_app(origins: list[str]) -> TestClient:
    app = FastAPI()

    @app.get("/ping")
    def ping():
        return {"ok": True}

    add_cors(app, origins)
    return TestClient(app)


def test_parse_origins_trims_and_drops_trailing_slashes():
    raw = " https://a.example.com/ , http://localhost:5173 ,, "
    assert parse_origins(raw) == ["https://a.example.com", "http://localhost:5173"]
    assert parse_origins("") == []


def test_wildcard_is_rejected():
    with pytest.raises(ValueError):
        parse_origins("*")
    with pytest.raises(ValueError):
        parse_origins("https://a.example.com, *")


def test_preflight_from_allowed_origin_includes_token_header():
    client = make_app([ALLOWED])
    r = client.options(
        "/ping",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-admin-token,content-type",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == ALLOWED
    assert "x-admin-token" in r.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in r.headers


def test_unlisted_origin_gets_no_access():
    client = make_app([ALLOWED])
    preflight = client.options(
        "/ping",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert preflight.status_code == 400
    simple = client.get("/ping", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in simple.headers


def test_request_id_header_is_exposed():
    client = make_app([ALLOWED])
    r = client.get("/ping", headers={"Origin": ALLOWED})
    assert r.headers["access-control-allow-origin"] == ALLOWED


def test_no_origins_means_no_cors_headers():
    client = make_app([])
    r = client.get("/ping", headers={"Origin": ALLOWED})
    assert "access-control-allow-origin" not in r.headers
