from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("PLO_SUPER_ADMIN_EMAIL", "b.olivier@circoe.com")
    monkeypatch.setenv("PLO_SUPER_ADMIN_USERNAME", "superadmn")
    monkeypatch.setenv("PLO_SUPER_ADMIN_PASSWORD", "1234")
    return TestClient(create_app(tmp_path))


@pytest.mark.parametrize("identifier", ["superadmn", "b.olivier@circoe.com"])
def test_super_admin_can_login_with_username_or_email(client: TestClient, identifier: str) -> None:
    response = client.post(
        "/api/auth/super-admin-login",
        json={"identifier": identifier, "password": "1234"},
    )
    assert response.status_code == 200
    assert response.json()["mode"] == "super_admin"
    assert response.json()["user"]["email"] == "b.olivier@circoe.com"
    assert client.cookies.get("axioload_session")

    context = client.get("/api/company/context")
    assert context.status_code == 200
    assert context.json()["actor"] == "b.olivier@circoe.com"

    bootstrap = client.get("/api/admin/bootstrap")
    assert bootstrap.status_code == 200
    assert bootstrap.json()["actor"] == "b.olivier@circoe.com"


def test_super_admin_rejects_invalid_password(client: TestClient) -> None:
    response = client.post(
        "/api/auth/super-admin-login",
        json={"identifier": "superadmn", "password": "incorrect"},
    )
    assert response.status_code == 401


def test_logout_ends_super_admin_session(client: TestClient) -> None:
    assert client.post(
        "/api/auth/super-admin-login",
        json={"identifier": "superadmn", "password": "1234"},
    ).status_code == 200
    assert client.get("/api/admin/bootstrap").status_code == 200

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 204
    assert client.get("/api/admin/bootstrap").status_code == 401


def test_authentication_assets_are_injected(client: TestClient) -> None:
    home = client.get("/")
    login = client.get("/login?mode=super_admin")
    assert home.status_code == 200
    assert login.status_code == 200
    for response in (home, login):
        assert response.text.count("/static/auth_experience.css?v=0.19.3") == 1
        assert response.text.count("/static/auth_experience.js?v=0.19.3") == 1
        assert response.text.count("/static/password_reset.css?v=0.19.1") == 1
        assert response.text.count("/static/password_reset.js?v=0.19.1") == 1
        assert "auth_experience.js?v=0.19.1" not in response.text
        assert "auth_experience.js?v=0.18.0" not in response.text
        assert "password_reset.js?v=0.18.0" not in response.text
