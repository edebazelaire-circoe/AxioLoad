from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pallet_optimizer.admin_service import SUPER_ADMIN_USER_ID
from pallet_optimizer.api import create_app
from pallet_optimizer.fixed_test_accounts import TEST_USER_ID
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
            "SELECT id,email,role,status,active FROM company_users ORDER BY id"
        ).fetchall()
        invitation_count = db.execute("SELECT COUNT(*) FROM invitations").fetchone()[0]

    assert len(rows) == 2
    assert {str(row["id"]) for row in rows} == {SUPER_ADMIN_USER_ID, TEST_USER_ID}
    assert {str(row["email"]) for row in rows} == {SUPER_ADMIN_EMAIL, TEST_USER_EMAIL}
    assert all(str(row["status"]) == "active" and int(row["active"]) == 1 for row in rows)
    assert next(row for row in rows if row["id"] == TEST_USER_ID)["role"] == "member"
    assert invitation_count == 0


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

    assert client.post("/api/auth/logout").status_code == 204

    user_login = client.post(
        "/api/auth/login",
        json={"tenant_id": "", "email": TEST_USER_EMAIL, "password": TEST_PASSWORD},
    )
    assert user_login.status_code == 200, user_login.text
    payload = user_login.json()
    assert payload["user"]["email"] == TEST_USER_EMAIL
    assert payload["tenant_id"] == "local"
    assert "session_token" not in payload
    assert client.cookies.get("axioload_session")

    context = client.get("/api/company/context")
    assert context.status_code == 200
    assert context.json()["user"]["email"] == TEST_USER_EMAIL


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
    page = client.get("/")
    assert page.status_code == 200
    assert "/static/fixed_test_accounts_ui.js?v=0.19.2" in page.text

    script = (STATIC / "fixed_test_accounts_ui.js").read_text(encoding="utf-8")
    assert "#admin-create-company" in script
    assert "#admin-add-user" in script
    assert "[data-resend]" in script
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


def test_docker_compose_contains_only_the_requested_test_credentials() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert 'PLO_TEST_ACCOUNTS_ONLY: "1"' in compose
    assert "PLO_SUPER_ADMIN_EMAIL: b.olivier@circoe.com" in compose
    assert 'PLO_SUPER_ADMIN_PASSWORD: "0123456789"' in compose
    assert "PLO_TEST_USER_EMAIL: olivierbaptiste6@gmail.com" in compose
    assert 'PLO_TEST_USER_PASSWORD: "0123456789"' in compose
    assert "1234" not in compose
