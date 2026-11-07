import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.auth import SESSION_SECONDS, password_hash


@pytest.fixture
def auth_app(tmp_path):
    return create_app(tmp_path)


@pytest.fixture
def browser(auth_app):
    with TestClient(auth_app, base_url="http://localhost") as client:
        yield client


@pytest.mark.parametrize("path", ["/api/state", "/api/capabilities", "/api/templates", "/api/projects/private/tree", "/api/projects/private/image", "/api/projects/private/video", "/api/projects/private/artifacts"])
def test_platform_requires_a_local_session(browser, auth_app, path):
    response = browser.get(path)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert "set-cookie" not in response.headers
    assert auth_app.state.store.all("SELECT * FROM sessions") == []
    assert browser.post("/api/organizations", json={"name": "Private"}).status_code == 401
    assert browser.get("/api/health").status_code == 200


def test_bootstrap_opens_a_local_session_without_login(browser, auth_app, login_data):
    response = browser.get("/api/bootstrap")
    cookie = response.headers["set-cookie"]
    assert response.status_code == 200
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert f"Max-Age={SESSION_SECONDS}" in cookie and "Path=/" in cookie
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["user"] == {"id": "local-owner", "name": login_data["username"]}
    assert login_data["password"] not in response.text
    token = browser.cookies["hapic_session"]
    assert token not in response.text
    browser.headers["X-Hapic-CSRF"] = response.json()["csrf"]
    bootstrap = browser.get("/api/bootstrap")
    assert bootstrap.json() == response.json()
    assert "set-cookie" not in bootstrap.headers
    assert len(auth_app.state.store.all("SELECT * FROM sessions")) == 1
    assert browser.get("/api/state").status_code == 200
    assert browser.post("/api/organizations", json={"name": "Estudio"}).status_code == 201


def test_mutations_reject_cross_origin_requests(browser, login):
    login(browser)
    for headers in ({"Origin": "https://attacker.example"}, {"Origin": "http://localhost:9999"}, {"Sec-Fetch-Site": "cross-site"}):
        assert browser.post("/api/organizations", json={"name": "Ajena"}, headers=headers).status_code == 403
    assert browser.post("/api/organizations", json={"name": "Local"}, headers={"Origin": "http://localhost"}).status_code == 201


def test_expired_session_is_replaced_on_bootstrap(browser, auth_app, login):
    login(browser)
    previous = browser.cookies["hapic_session"]
    auth_app.state.store.execute("UPDATE sessions SET expires_at=?", (int(time.time()) - 1,))
    assert browser.get("/api/state").status_code == 401
    opened = browser.get("/api/bootstrap")
    assert opened.status_code == 200
    assert browser.cookies["hapic_session"] != previous
    browser.headers["X-Hapic-CSRF"] = opened.json()["csrf"]
    assert browser.get("/api/state").status_code == 200


def test_legacy_anonymous_sessions_are_replaced(tmp_path):
    with sqlite3.connect(tmp_path / "platform.db") as db:
        db.execute("CREATE TABLE sessions(token TEXT PRIMARY KEY,csrf TEXT,created_at TEXT)")
        db.execute("INSERT INTO sessions VALUES ('old-anonymous-token','old-csrf','2026-01-01')")
    application = create_app(tmp_path)
    with TestClient(application, base_url="http://localhost") as client:
        client.cookies.set("hapic_session", "old-anonymous-token")
        assert client.get("/api/state").status_code == 401
        opened = client.get("/api/bootstrap")
        assert opened.status_code == 200
        new_token = opened.cookies["hapic_session"]
        assert new_token != "old-anonymous-token"
        client.cookies.clear()
        client.cookies.set("hapic_session", new_token)
        client.headers["X-Hapic-CSRF"] = opened.json()["csrf"]
        assert client.get("/api/state").status_code == 200
        assert application.state.store.one("SELECT * FROM sessions WHERE token='old-anonymous-token'") is None


def test_sessions_survive_restart_and_old_cookies_are_replaced(tmp_path, login, monkeypatch):
    first = create_app(tmp_path)
    with TestClient(first, base_url="http://localhost") as client:
        login(client)
        token = client.cookies["hapic_session"]
    with TestClient(create_app(tmp_path), base_url="http://localhost") as restarted:
        restarted.cookies.set("hapic_session", token)
        assert restarted.get("/api/bootstrap").status_code == 200
        assert "set-cookie" not in restarted.get("/api/bootstrap").headers
    monkeypatch.setenv("HAPIC_LOGIN_PASSWORD_HASH", password_hash("rotated-test-password"))
    with TestClient(create_app(tmp_path), base_url="http://localhost") as rotated:
        rotated.cookies.set("hapic_session", token)
        assert rotated.get("/api/state").status_code == 401
        opened = rotated.get("/api/bootstrap")
        assert opened.status_code == 200
        assert opened.cookies["hapic_session"] != token


def test_https_session_cookie_is_secure(auth_app, login):
    with TestClient(auth_app, base_url="https://localhost") as client:
        assert "Secure" in login(client).headers["set-cookie"]
        assert client.get("/api/state").status_code == 200


def test_mcp_keeps_its_independent_agent_authorization(browser, login):
    login(browser)
    assert browser.post("/mcp/", json={"jsonrpc": "2.0", "method": "tools/list", "id": 1}).status_code == 401
