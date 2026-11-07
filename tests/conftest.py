import pytest

from backend.auth import password_hash


TEST_USERNAME = "norteños"
TEST_PASSWORD = "test-only-platform-password"
TEST_PASSWORD_HASH = password_hash(TEST_PASSWORD)


@pytest.fixture(autouse=True)
def configure_login(monkeypatch):
    # Tests use their own credentials, never the platform owner's password.
    monkeypatch.setenv("HAPIC_LOGIN_USERNAME", TEST_USERNAME)
    monkeypatch.setenv("HAPIC_LOGIN_PASSWORD_HASH", TEST_PASSWORD_HASH)


@pytest.fixture
def login_data():
    return {"username": TEST_USERNAME, "password": TEST_PASSWORD}


@pytest.fixture
def login(login_data):
    def sign_in(client, **overrides):
        response = client.post("/api/auth/login", json={**login_data, **overrides})
        assert response.status_code == 200, response.text
        client.headers["X-Hapic-CSRF"] = response.json()["csrf"]
        return response
    return sign_in
