from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app


def _login_super_admin(client: TestClient) -> None:
    response = client.post(
        "/api/auth/super-admin-login",
        json={"identifier": "superadmn", "password": "0123456789"},
    )
    assert response.status_code == 200, response.text


def _create_and_activate_company(
    admin_client: TestClient,
    user_client: TestClient,
    *,
    name: str = "Entreprise Portail Test",
    email: str = "portail@example.test",
    password: str = "MotDePasseInitial!2026",
) -> tuple[str, str, str]:
    created = admin_client.post(
        "/api/admin/companies",
        json={
            "company_name": name,
            "first_name": "Alice",
            "last_name": "Martin",
            "email": email,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    tenant_id = body["company"]["id"]
    user_id = body["user"]["id"]
    token = parse_qs(urlparse(body["invitation"]["activation_url"]).query)["token"][0]

    activated = user_client.post(
        "/api/invitations/activate",
        json={"token": token, "password": password},
    )
    assert activated.status_code == 200, activated.text

    profile = user_client.put(
        "/api/company/profile",
        json={
            "legal_name": name,
            "siret": "",
            "address": "10 rue du Port, 76600 Le Havre",
            "country": "France",
            "contact_first_name": "Alice",
            "contact_last_name": "Martin",
            "phone": "+33 2 00 00 00 00",
            "contact_email": email,
        },
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["status"] == "pending_validation"

    approved = admin_client.post(
        f"/api/admin/companies/{tenant_id}/profile-decision",
        json={"decision": "approve", "comment": ""},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "active"
    return tenant_id, user_id, password


def test_company_created_by_superadmin_can_log_in_without_technical_tenant_id(tmp_path):
    app = create_app(tmp_path)
    admin_client = TestClient(app)
    user_client = TestClient(app)
    _login_super_admin(admin_client)
    tenant_id, _user_id, password = _create_and_activate_company(admin_client, user_client)

    logout = user_client.post("/api/auth/logout")
    assert logout.status_code == 204

    login = user_client.post(
        "/api/auth/login",
        json={
            "tenant_id": "",
            "email": "portail@example.test",
            "password": password,
        },
    )
    assert login.status_code == 200, login.text
    assert login.json()["tenant_id"] == tenant_id
    assert login.json()["user"]["tenant_id"] == tenant_id

    context = user_client.get("/api/company/context")
    assert context.status_code == 200, context.text
    assert context.json()["company"]["id"] == tenant_id
    assert context.json()["user"]["email"] == "portail@example.test"


def test_forgot_password_and_superadmin_reset_without_reset_token(tmp_path):
    app = create_app(tmp_path)
    admin_client = TestClient(app)
    user_client = TestClient(app)
    _login_super_admin(admin_client)
    tenant_id, user_id, old_password = _create_and_activate_company(
        admin_client,
        user_client,
        name="Entreprise Réinitialisation",
        email="reset@example.test",
    )

    forgot = TestClient(app).post(
        "/api/auth/forgot-password",
        json={"tenant_id": "", "email": "reset@example.test"},
    )
    assert forgot.status_code == 200, forgot.text
    assert set(forgot.json()) == {"message"}
    assert "token" not in forgot.text.lower()
    assert "lien" not in forgot.text.lower()

    pending = admin_client.get("/api/admin/password-reset-requests?status=pending")
    assert pending.status_code == 200, pending.text
    requests = pending.json()["requests"]
    assert len(requests) == 1
    assert requests[0]["tenant_id"] == tenant_id
    assert requests[0]["user_id"] == user_id

    reset = admin_client.post(f"/api/admin/users/{user_id}/password-reset", json={})
    assert reset.status_code == 200, reset.text
    temporary_password = reset.json()["temporary_password"]
    assert len(temporary_password) >= 10
    assert reset.json()["visible_once"] is True

    old_login = TestClient(app).post(
        "/api/auth/login",
        json={"tenant_id": "", "email": "reset@example.test", "password": old_password},
    )
    assert old_login.status_code == 401

    temporary_client = TestClient(app)
    temporary_login = temporary_client.post(
        "/api/auth/login",
        json={"tenant_id": "", "email": "reset@example.test", "password": temporary_password},
    )
    assert temporary_login.status_code == 200, temporary_login.text
    assert temporary_login.json()["must_change_password"] is True

    changed = temporary_client.post(
        "/api/auth/change-password",
        json={
            "current_password": temporary_password,
            "new_password": "NouveauMotDePasse!2026",
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["user"]["must_change_password"] is False

    assert temporary_client.post("/api/auth/logout").status_code == 204
    final_login = temporary_client.post(
        "/api/auth/login",
        json={
            "tenant_id": "",
            "email": "reset@example.test",
            "password": "NouveauMotDePasse!2026",
        },
    )
    assert final_login.status_code == 200, final_login.text
    assert final_login.json()["must_change_password"] is False


def test_admin_endpoints_reject_header_tokens_and_require_browser_session(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.get(
        "/api/admin/bootstrap",
        headers={"X-AxioLoad-Super-Admin": "not-a-session"},
    )
    assert response.status_code == 401
