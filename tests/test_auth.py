import sqlite3
import time
import unicodedata

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.auth import LOGIN_WINDOW_SECONDS, MAX_LOGIN_ATTEMPTS, SESSION_SECONDS, password_hash


@pytest.fixture
def auth_app(tmp_path):
    return create_app(tmp_path)


@pytest.fixture
def browser(auth_app):
    with TestClient(auth_app, base_url="http://localhost") as client:
        yield client


@pytest.mark.parametrize("path", ["/api/bootstrap", "/api/state", "/api/capabilities", "/api/templates", "/api/projects/private/tree", "/api/projects/private/image", "/api/projects/private/video", "/api/projects/private/artifacts"])
def test_platform_requires_login(browser, auth_app, path):
    response = browser.get(path)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert "set-cookie" not in response.headers
    assert auth_app.state.store.all("SELECT * FROM sessions") == []
    assert browser.post("/api/organizations", json={"name": "Private"}).status_code == 401
    assert browser.get("/api/health").status_code == 200


def test_login_sets_private_cookie_and_bootstrap_reuses_session(browser, auth_app, login, login_data):
    response = login(browser)
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert f"Max-Age={SESSION_SECONDS}" in cookie and "Path=/" in cookie
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["user"] == {"id": "local-owner", "name": login_data["username"]}
    assert login_data["password"] not in response.text
    token = browser.cookies["hapic_session"]
    assert token not in response.text
    bootstrap = browser.get("/api/bootstrap")
    assert bootstrap.json() == response.json()
    assert "set-cookie" not in bootstrap.headers
    assert len(auth_app.state.store.all("SELECT * FROM sessions")) == 1
    assert browser.get("/api/state").status_code == 200
    assert browser.post("/api/organizations", json={"name": "Estudio"}).status_code == 201


@pytest.mark.parametrize("overrides", [{"password": "incorrect"}, {"username": "unknown"}, {"username": "nortenos"}])
def test_invalid_credentials_never_create_a_session(browser, auth_app, login_data, overrides):
    response = browser.post("/api/auth/login", json={**login_data, **overrides})
    assert response.status_code == 401
    assert response.json()["detail"] == "Usuario o contraseña incorrectos."
    assert "set-cookie" not in response.headers
    assert auth_app.state.store.all("SELECT * FROM sessions") == []


def test_username_supports_composed_and_decomposed_enye(browser, login, login_data):
    login(browser, username=unicodedata.normalize("NFD", login_data["username"]))
    assert browser.get("/api/bootstrap").json()["user"]["name"] == "norteños"


def test_login_rejects_cross_origin_requests(browser, login_data):
    for headers in ({"Origin": "https://attacker.example"}, {"Origin": "http://localhost:9999"}, {"Sec-Fetch-Site": "cross-site"}):
        assert browser.post("/api/auth/login", json=login_data, headers=headers).status_code == 403
    assert browser.post("/api/auth/login", json=login_data, headers={"Origin": "http://localhost"}).status_code == 200


def test_invalid_login_payload_does_not_echo_password(browser):
    secret = "do-not-echo-this-password" * 20
    response = browser.post("/api/auth/login", json={"username": "owner", "password": secret})
    assert response.status_code == 422 and secret not in response.text


def test_login_limits_guesses_then_allows_retry(browser, auth_app, login_data, monkeypatch):
    clock = 1000.0
    monkeypatch.setattr("backend.auth.monotonic", lambda: clock)
    for _ in range(MAX_LOGIN_ATTEMPTS):
        assert browser.post("/api/auth/login", json={**login_data, "password": "wrong"}).status_code == 401
    response = browser.post("/api/auth/login", json=login_data)
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) == LOGIN_WINDOW_SECONDS
    assert auth_app.state.store.all("SELECT * FROM sessions") == []
    clock += LOGIN_WINDOW_SECONDS + 1
    assert browser.post("/api/auth/login", json=login_data).status_code == 200


def test_logout_requires_csrf_and_revokes_the_session(browser, auth_app, login):
    login(browser)
    token = browser.cookies["hapic_session"]
    csrf = browser.headers["X-Hapic-CSRF"]
    assert browser.post("/api/auth/logout", headers={"X-Hapic-CSRF": "wrong"}).status_code == 403
    assert browser.post("/api/auth/logout", headers={"Origin": "https://attacker.example"}).status_code == 403
    response = browser.post("/api/auth/logout")
    assert response.status_code == 200 and response.json()["logged_out"]
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert "hapic_session" not in browser.cookies
    assert auth_app.state.store.one("SELECT * FROM sessions WHERE token=?", (token,)) is None
    browser.cookies.set("hapic_session", token)
    assert browser.get("/api/state").status_code == 401
    assert browser.post("/api/organizations", json={"name": "Replay"}, headers={"X-Hapic-CSRF": csrf}).status_code == 401


def test_login_rotates_existing_session_and_csrf(browser, auth_app, login):
    first = login(browser).json()
    previous = browser.cookies["hapic_session"]
    second = login(browser).json()
    assert browser.cookies["hapic_session"] != previous and second["csrf"] != first["csrf"]
    assert auth_app.state.store.one("SELECT * FROM sessions WHERE token=?", (previous,)) is None
    assert browser.post("/api/organizations", json={"name": "Old CSRF"}, headers={"X-Hapic-CSRF": first["csrf"]}).status_code == 403


def test_server_enforces_session_expiration(browser, auth_app, login):
    login(browser)
    auth_app.state.store.execute("UPDATE sessions SET expires_at=?", (int(time.time()) - 1,))
    assert browser.get("/api/bootstrap").status_code == 401
    assert browser.get("/api/state").status_code == 401


def test_legacy_anonymous_sessions_are_migrated_and_rejected(tmp_path, login):
    with sqlite3.connect(tmp_path / "platform.db") as db:
        db.execute("CREATE TABLE sessions(token TEXT PRIMARY KEY,csrf TEXT,created_at TEXT)")
        db.execute("INSERT INTO sessions VALUES ('old-anonymous-token','old-csrf','2026-01-01')")
    application = create_app(tmp_path)
    with TestClient(application, base_url="http://localhost") as client:
        client.cookies.set("hapic_session", "old-anonymous-token")
        assert client.get("/api/bootstrap").status_code == 401
        assert client.get("/api/state").status_code == 401
        login(client)
        assert client.get("/api/state").status_code == 200
        assert application.state.store.one("SELECT * FROM sessions WHERE token='old-anonymous-token'") is None


def test_sessions_survive_restart_and_expire_on_credential_rotation(tmp_path, login, monkeypatch):
    first = create_app(tmp_path)
    with TestClient(first, base_url="http://localhost") as client:
        login(client)
        token = client.cookies["hapic_session"]
    with TestClient(create_app(tmp_path), base_url="http://localhost") as restarted:
        restarted.cookies.set("hapic_session", token)
        assert restarted.get("/api/bootstrap").status_code == 200
    monkeypatch.setenv("HAPIC_LOGIN_PASSWORD_HASH", password_hash("rotated-test-password"))
    with TestClient(create_app(tmp_path), base_url="http://localhost") as rotated:
        rotated.cookies.set("hapic_session", token)
        assert rotated.get("/api/bootstrap").status_code == 401
        login(rotated, password="rotated-test-password")


def test_https_login_cookie_is_secure(auth_app, login):
    with TestClient(auth_app, base_url="https://localhost") as client:
        assert "Secure" in login(client).headers["set-cookie"]
        assert client.get("/api/state").status_code == 200


def test_mcp_keeps_its_independent_agent_authorization(browser, login):
    login(browser)
    assert browser.post("/mcp/", json={"jsonrpc": "2.0", "method": "tools/list", "id": 1}).status_code == 401
