from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app
from pallet_optimizer.persistence import _connect


SUPER_ADMIN_USERNAME = "security-admin"
SUPER_ADMIN_PASSWORD = "Security-Admin-Password!2026"


def _configure_admin(monkeypatch) -> None:
    monkeypatch.setenv("PLO_LOCAL_MODE", "0")
    monkeypatch.setenv("PLO_TEST_ACCOUNTS_ONLY", "0")
    monkeypatch.setenv("PLO_COOKIE_SECURE", "0")
    monkeypatch.setenv("PLO_SUPER_ADMIN_USERNAME", SUPER_ADMIN_USERNAME)
    monkeypatch.setenv("PLO_SUPER_ADMIN_PASSWORD", SUPER_ADMIN_PASSWORD)


def test_saas_mode_is_fail_closed_without_session(tmp_path, monkeypatch) -> None:
    _configure_admin(monkeypatch)
    client = TestClient(create_app(tmp_path))

    api = client.get("/api/company/context")
    assert api.status_code == 401
    assert api.json()["detail"] == "Connexion requise"

    page = client.get("/", follow_redirects=False)
    assert page.status_code == 303
    assert page.headers["location"] == "/login"


def test_local_mode_requires_explicit_opt_in(tmp_path, monkeypatch) -> None:
    _configure_admin(monkeypatch)
    monkeypatch.setenv("PLO_LOCAL_MODE", "1")
    client = TestClient(create_app(tmp_path))

    response = client.get("/api/company/context")
    assert response.status_code == 200
    assert response.json()["company"]["id"] == "local"


def test_browser_session_token_is_not_stored_in_cleartext(tmp_path, monkeypatch) -> None:
    _configure_admin(monkeypatch)
    app = create_app(tmp_path)
    client = TestClient(app)

    login = client.post(
        "/api/auth/super-admin-login",
        json={"identifier": SUPER_ADMIN_USERNAME, "password": SUPER_ADMIN_PASSWORD},
    )
    assert login.status_code == 200, login.text
    token = client.cookies.get("axioload_session")
    assert token

    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with _connect(app.state.registry.registry_path) as db:
        rows = db.execute("SELECT id FROM user_sessions").fetchall()
        stored = {str(row["id"]) for row in rows}

    assert token not in stored
    assert digest in stored
    assert client.get("/api/company/context").status_code == 200


def test_cross_site_state_change_is_rejected(tmp_path, monkeypatch) -> None:
    _configure_admin(monkeypatch)
    client = TestClient(create_app(tmp_path))
    login = client.post(
        "/api/auth/super-admin-login",
        json={"identifier": SUPER_ADMIN_USERNAME, "password": SUPER_ADMIN_PASSWORD},
    )
    assert login.status_code == 200

    rejected = client.post(
        "/api/auth/logout",
        headers={"Origin": "https://attacker.example", "Sec-Fetch-Site": "cross-site"},
    )
    assert rejected.status_code == 403
    assert rejected.json()["detail"] == "Requête intersite refusée"

    assert client.get("/api/company/context").status_code == 200


def test_session_cookie_is_http_only_strict_and_secure_when_enabled(tmp_path, monkeypatch) -> None:
    _configure_admin(monkeypatch)
    monkeypatch.setenv("PLO_COOKIE_SECURE", "1")
    client = TestClient(create_app(tmp_path))

    response = client.post(
        "/api/auth/super-admin-login",
        json={"identifier": SUPER_ADMIN_USERNAME, "password": SUPER_ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=strict" in cookie


def test_new_password_hashes_use_argon2id(tmp_path, monkeypatch) -> None:
    _configure_admin(monkeypatch)
    app = create_app(tmp_path)
    client = TestClient(app)

    login = client.post(
        "/api/auth/super-admin-login",
        json={"identifier": SUPER_ADMIN_USERNAME, "password": SUPER_ADMIN_PASSWORD},
    )
    assert login.status_code == 200

    with _connect(app.state.registry.registry_path) as db:
        row = db.execute(
            "SELECT password_salt,password_digest FROM company_users WHERE role='super_admin'"
        ).fetchone()

    assert row is not None
    assert row["password_salt"] == "argon2id"
    assert str(row["password_digest"]).startswith("$argon2id$")


def test_deployment_defaults_keep_local_mode_disabled() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (root / ".env.example").read_text(encoding="utf-8")

    assert 'PLO_LOCAL_MODE: "${PLO_LOCAL_MODE:-0}"' in compose
    assert "PLO_LOCAL_MODE=0" in env_example
