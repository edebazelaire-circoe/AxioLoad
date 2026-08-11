from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from pallet_optimizer.admin_service import PERMISSION_KEYS, SUPER_ADMIN_USER_ID
from pallet_optimizer.api import create_app
from pallet_optimizer.fixed_test_accounts import (
    TEST_COMPANY_NAME,
    TEST_TENANT_ID,
    TEST_USER_ID,
)
from pallet_optimizer.persistence import _connect, _hash_secret, utc_now


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "pallet_optimizer" / "static"
SUPER_ADMIN_EMAIL = "b.olivier@circoe.com"
TEST_USER_EMAIL = "olivierbaptiste6@gmail.com"
TEST_PASSWORD = "0123456789"


def _enable_fixed_accounts(monkeypatch) -> None:
    monkeypatch.setenv("PLO_TEST_ACCOUNTS_ONLY", "1")
    monkeypatch.setenv("PLO_SUPER_ADMIN_EMAIL", SUPER_ADMIN_EMAIL)
    monkeypatch.setenv("PLO_SUPER_ADMIN_USERNAME", "superadmn")
    monkeypatch.setenv("PLO_SUPER_ADMIN_PASSWORD", TEST_PASSWORD)
    monkeypatch.setenv("PLO_TEST_USER_EMAIL", TEST_USER_EMAIL)
    monkeypatch.setenv("PLO_TEST_USER_PASSWORD", TEST_PASSWORD)


def test_fixed_mode_keeps_exactly_two_active_accounts(tmp_path, monkeypatch) -> None:
    _enable_fixed_accounts(monkeypatch)
    client = TestClient(create_app(tmp_path))

    with _connect(client.app.state.registry.registry_path) as db:
        rows = db.execute(
            "SELECT id,tenant_id,email,role,status,active FROM company_users ORDER BY id"
        ).fetchall()
        invitation_count = db.execute("SELECT COUNT(*) FROM invitations").fetchone()[0]

    assert len(rows) == 2
    assert {str(row["id"]) for row in rows} == {SUPER_ADMIN_USER_ID, TEST_USER_ID}
    assert {str(row["email"]) for row in rows} == {SUPER_ADMIN_EMAIL, TEST_USER_EMAIL}
    assert all(str(row["status"]) == "active" and int(row["active"]) == 1 for row in rows)

    super_admin = next(row for row in rows if row["id"] == SUPER_ADMIN_USER_ID)
    company_admin = next(row for row in rows if row["id"] == TEST_USER_ID)
    assert super_admin["tenant_id"] == "local"
    assert super_admin["role"] == "super_admin"
    assert company_admin["tenant_id"] == TEST_TENANT_ID
    assert company_admin["role"] == "primary"
    assert invitation_count == 0

    company = client.app.state.admin.get_company(TEST_TENANT_ID)
    assert company["name"] == TEST_COMPANY_NAME
    assert all(company["permissions"].get(key) is True for key in PERMISSION_KEYS)


def test_unauthenticated_browser_starts_on_login_page(tmp_path, monkeypatch) -> None:
    _enable_fixed_accounts(monkeypatch)
    client = TestClient(create_app(tmp_path))

    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"

    protected_api = client.get("/api/company/context")
    assert protected_api.status_code == 401
    assert protected_api.json()["detail"] == "Connexion requise"


def test_login_page_exposes_exactly_the_two_requested_profiles(tmp_path, monkeypatch) -> None:
    _enable_fixed_accounts(monkeypatch)
    client = TestClient(create_app(tmp_path))

    page = client.get("/login")
    assert page.status_code == 200
    assert page.text.count('/static/fixed_test_accounts_ui.js?v=0.19.5') == 1
    assert page.text.count('/static/fixed_test_accounts.css?v=0.19.5') == 1

    response = client.get("/api/auth/test-accounts")
    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is True
    assert len(payload["accounts"]) == 2

    super_admin, company_admin = payload["accounts"]
    assert super_admin == {
        "key": "super_admin",
        "mode": "super_admin",
        "label": "Super administrateur",
        "description": "Vision globale : entreprises, utilisateurs et configuration générale.",
        "identifier": SUPER_ADMIN_EMAIL,
        "username": "superadmn",
        "password": TEST_PASSWORD,
    }
    assert company_admin == {
        "key": "company_admin",
        "mode": "user",
        "label": "Administrateur principal d’entreprise",
        "description": "Vision complète de sa propre entreprise, sans accès au Centre de gestion.",
        "tenant_id": TEST_TENANT_ID,
        "company_name": TEST_COMPANY_NAME,
        "identifier": TEST_USER_EMAIL,
        "password": TEST_PASSWORD,
    }


def test_both_fixed_accounts_can_login_without_activation_link(tmp_path, monkeypatch) -> None:
    _enable_fixed_accounts(monkeypatch)
    client = TestClient(create_app(tmp_path))

    admin_login = client.post(
        "/api/auth/super-admin-login",
        json={"identifier": SUPER_ADMIN_EMAIL, "password": TEST_PASSWORD},
    )
    assert admin_login.status_code == 200, admin_login.text
    assert admin_login.json()["mode"] == "super_admin"
    assert "session_token" not in admin_login.json()
    assert client.cookies.get("axioload_session")

    admin_context = client.get("/api/company/context")
    assert admin_context.status_code == 200
    assert admin_context.json()["mode"] == "assistance"
    assert admin_context.json()["company"]["id"] == "local"

    assert client.post("/api/auth/logout").status_code == 204

    user_login = client.post(
        "/api/auth/login",
        json={
            "tenant_id": TEST_TENANT_ID,
            "email": TEST_USER_EMAIL,
            "password": TEST_PASSWORD,
        },
    )
    assert user_login.status_code == 200, user_login.text
    payload = user_login.json()
    assert payload["user"]["email"] == TEST_USER_EMAIL
    assert payload["user"]["role"] == "primary"
    assert payload["tenant_id"] == TEST_TENANT_ID
    assert "session_token" not in payload
    assert client.cookies.get("axioload_session")

    context = client.get("/api/company/context")
    assert context.status_code == 200
    body = context.json()
    assert body["mode"] == "user"
    assert body["company"]["id"] == TEST_TENANT_ID
    assert body["company"]["name"] == TEST_COMPANY_NAME
    assert body["user"]["email"] == TEST_USER_EMAIL
    assert body["user"]["role"] == "primary"
    assert all(body["permissions"].get(key) is True for key in PERMISSION_KEYS)


def test_fixed_mode_removes_previous_accounts_and_pending_invitations(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PLO_TEST_ACCOUNTS_ONLY", "0")
    first_app = create_app(tmp_path)
    registry_path = first_app.state.registry.registry_path
    salt, digest = _hash_secret("temporary-password")
    extra_user_id = str(uuid.uuid4())
    now = utc_now()

    with _connect(registry_path) as db:
        db.execute(
            """INSERT INTO company_users(
                   id,tenant_id,first_name,last_name,email,role,status,active,
                   password_salt,password_digest,created_at,activated_at
               ) VALUES (?, 'local','Compte','Supplémentaire','extra@example.com',
                         'member','active',1,?,?,?,?)""",
            (extra_user_id, salt, digest, now, now),
        )
        db.execute(
            """INSERT INTO invitations(
                   id,tenant_id,user_id,prefix,salt,digest,expires_at,created_at
               ) VALUES (?, 'local',?,?,?,?,?,?)""",
            (str(uuid.uuid4()), extra_user_id, "legacy", salt, digest, "2099-01-01T00:00:00+00:00", now),
        )

    _enable_fixed_accounts(monkeypatch)
    second_app = create_app(tmp_path)
    with _connect(second_app.state.registry.registry_path) as db:
        account_ids = {
            str(row["id"])
            for row in db.execute("SELECT id FROM company_users").fetchall()
        }
        invitation_count = db.execute("SELECT COUNT(*) FROM invitations").fetchone()[0]

    assert account_ids == {SUPER_ADMIN_USER_ID, TEST_USER_ID}
    assert invitation_count == 0


def test_fixed_mode_blocks_creation_of_a_third_account(tmp_path, monkeypatch) -> None:
    _enable_fixed_accounts(monkeypatch)
    client = TestClient(create_app(tmp_path))
    login = client.post(
        "/api/auth/super-admin-login",
        json={"identifier": "superadmn", "password": TEST_PASSWORD},
    )
    assert login.status_code == 200

    response = client.post(
        "/api/admin/companies",
        json={
            "company_name": "Entreprise supplémentaire",
            "email": "third@example.com",
            "first_name": "Compte",
            "last_name": "Interdit",
        },
    )
    assert response.status_code == 403
    assert "deux comptes" in response.json()["detail"]

    with _connect(client.app.state.registry.registry_path) as db:
        assert db.execute("SELECT COUNT(*) FROM company_users").fetchone()[0] == 2


def test_fixed_mode_hides_invitation_actions_without_observer(tmp_path, monkeypatch) -> None:
    _enable_fixed_accounts(monkeypatch)
    client = TestClient(create_app(tmp_path))
    login = client.post(
        "/api/auth/super-admin-login",
        json={"identifier": SUPER_ADMIN_EMAIL, "password": TEST_PASSWORD},
    )
    assert login.status_code == 200

    page = client.get("/")
    assert page.status_code == 200
    assert page.text.count('/static/fixed_test_accounts_ui.js?v=0.19.5') == 1

    script = (STATIC / "fixed_test_accounts_ui.js").read_text(encoding="utf-8")
    assert "#admin-create-company" in script
    assert "#admin-add-user" in script
    assert "[data-resend]" in script
    assert "/api/auth/test-accounts" in script
    assert "requestSubmit" in script
    assert "MutationObserver" not in script

    node = shutil.which("node")
    if node:
        subprocess.run(
            [node, "--check", str(STATIC / "fixed_test_accounts_ui.js")],
            check=True,
            capture_output=True,
            text=True,
        )


def test_fixed_mode_is_not_injected_when_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PLO_TEST_ACCOUNTS_ONLY", "0")
    client = TestClient(create_app(tmp_path))
    assert "/static/fixed_test_accounts_ui.js" not in client.get("/").text
    assert "/static/fixed_test_accounts_ui.js" not in client.get("/login").text
    assert client.get("/api/auth/test-accounts").status_code == 404


def test_docker_compose_uses_secure_externalized_defaults() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert 'PLO_TEST_ACCOUNTS_ONLY: "${PLO_TEST_ACCOUNTS_ONLY:-0}"' in compose
    assert 'PLO_SUPER_ADMIN_PASSWORD: "${PLO_SUPER_ADMIN_PASSWORD:-}"' in compose
    assert 'PLO_TEST_USER_PASSWORD: "${PLO_TEST_USER_PASSWORD:-}"' in compose
    assert 'PLO_COOKIE_SECURE: "${PLO_COOKIE_SECURE:-1}"' in compose
    assert 'PLO_DOCUMENT_SECRET_KEY: "${PLO_DOCUMENT_SECRET_KEY:-}"' in compose
    assert 'PLO_SUPER_ADMIN_PASSWORD: "0123456789"' not in compose
    assert 'PLO_TEST_USER_PASSWORD: "0123456789"' not in compose
    assert 'PLO_TEST_ACCOUNTS_ONLY: "1"' not in compose
