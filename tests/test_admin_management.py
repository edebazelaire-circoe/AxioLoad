from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app


ADMIN_HEADERS: dict[str, str] = {}


def _create_company(client: TestClient, name: str = "Client Test") -> dict:
    response = client.post(
        "/api/admin/companies",
        headers=ADMIN_HEADERS,
        json={
            "company_name": name,
            "first_name": "Alice",
            "last_name": "Martin",
            "email": "alice@example.test",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _activation_token(invitation: dict) -> str:
    return parse_qs(urlparse(invitation["activation_url"]).query)["token"][0]


def _activate_primary_user(client: TestClient, created: dict) -> None:
    token = _activation_token(created["invitation"])
    preview = client.get("/api/invitations/preview", params={"token": token})
    assert preview.status_code == 200
    assert preview.json()["needs_company_profile"] is True
    activation = client.post(
        "/api/invitations/activate",
        json={"token": token, "password": "UnMotDePasseSolide!2026"},
    )
    assert activation.status_code == 200, activation.text


def _submit_profile(client: TestClient) -> None:
    response = client.put(
        "/api/company/profile",
        json={
            "legal_name": "Client Test SAS",
            "siret": "",
            "address": "10 rue du Port, 76600 Le Havre",
            "country": "France",
            "contact_first_name": "Alice",
            "contact_last_name": "Martin",
            "phone": "+33 2 00 00 00 00",
            "contact_email": "contact@example.test",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "pending_validation"


def test_admin_opens_directly_without_token(tmp_path, monkeypatch):
    monkeypatch.delenv("PLO_SUPER_ADMIN_TOKEN", raising=False)
    monkeypatch.setenv("PLO_SUPER_ADMIN_EMAIL", "admin@axioload.test")
    client = TestClient(create_app(tmp_path))
    response = client.get("/api/admin/bootstrap")
    assert response.status_code == 200, response.text
    assert response.json()["actor"] == "admin@axioload.test"


def test_company_invitation_activation_profile_and_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("PLO_SUPER_ADMIN_EMAIL", "admin@axioload.test")
    client = TestClient(create_app(tmp_path))

    created = _create_company(client)
    assert created["company"]["status"] == "invited"
    assert created["email_delivery"] == "smtp_not_configured"
    assert created["invitation"]["token_visible_once"] is True

    _activate_primary_user(client, created)
    _submit_profile(client)

    tenant_id = created["company"]["id"]
    detail = client.get(f"/api/admin/companies/{tenant_id}", headers=ADMIN_HEADERS)
    assert detail.status_code == 200
    assert detail.json()["company"]["profile"]["pending_validation"] is True

    approved = client.post(
        f"/api/admin/companies/{tenant_id}/profile-decision",
        headers=ADMIN_HEADERS,
        json={"decision": "approve", "comment": ""},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "active"


def test_user_permission_override_api_keys_and_suspension(tmp_path):
    client = TestClient(create_app(tmp_path))
    created = _create_company(client, "Transport Démo")
    tenant_id = created["company"]["id"]
    _activate_primary_user(client, created)
    _submit_profile(client)
    client.post(
        f"/api/admin/companies/{tenant_id}/profile-decision",
        headers=ADMIN_HEADERS,
        json={"decision": "approve", "comment": ""},
    )

    permissions = created["company"]["permissions"]
    permissions["api.use"] = True
    updated = client.put(
        f"/api/admin/companies/{tenant_id}/permissions",
        headers=ADMIN_HEADERS,
        json=permissions,
    )
    assert updated.status_code == 200

    invited = client.post(
        f"/api/admin/companies/{tenant_id}/users",
        headers=ADMIN_HEADERS,
        json={
            "first_name": "Bob",
            "last_name": "Durand",
            "email": "bob@example.test",
            "permissions": {"route.run": "deny", "history.delete": "allow"},
        },
    )
    assert invited.status_code == 201, invited.text
    user = invited.json()["user"]
    assert user["permission_overrides"]["route.run"] == "deny"
    assert user["permission_overrides"]["history.delete"] == "allow"

    key = client.post(
        f"/api/admin/companies/{tenant_id}/api-keys",
        headers=ADMIN_HEADERS,
        json={"label": "ERP production", "scopes": ["results.run"], "expires_at": None},
    )
    assert key.status_code == 201, key.text
    secret = key.json()["secret"]
    assert secret.startswith("axio_")

    detail = client.get(f"/api/admin/companies/{tenant_id}", headers=ADMIN_HEADERS).json()
    assert "secret" not in detail["api_keys"][0]
    assert detail["api_keys"][0]["active"] is True

    suspended = client.post(
        f"/api/admin/companies/{tenant_id}/status",
        headers=ADMIN_HEADERS,
        json={"status": "suspended", "suspension_mode": "block", "reactivate_keys": False},
    )
    assert suspended.status_code == 200
    detail = client.get(f"/api/admin/companies/{tenant_id}", headers=ADMIN_HEADERS).json()
    assert detail["api_keys"][0]["active"] is False

    client.post(
        f"/api/admin/companies/{tenant_id}/status",
        headers=ADMIN_HEADERS,
        json={"status": "active", "suspension_mode": "block", "reactivate_keys": False},
    )
    detail = client.get(f"/api/admin/companies/{tenant_id}", headers=ADMIN_HEADERS).json()
    assert detail["api_keys"][0]["active"] is False

    client.post(
        f"/api/admin/companies/{tenant_id}/status",
        headers=ADMIN_HEADERS,
        json={"status": "active", "suspension_mode": "block", "reactivate_keys": True},
    )
    detail = client.get(f"/api/admin/companies/{tenant_id}", headers=ADMIN_HEADERS).json()
    assert detail["api_keys"][0]["active"] is True


def test_assistance_marks_history_and_freezes_vehicle_dimensions(tmp_path, monkeypatch, base_payload):
    monkeypatch.setenv("PLO_SUPER_ADMIN_EMAIL", "support@axioload.test")
    client = TestClient(create_app(tmp_path))
    created = _create_company(client, "Société Assistance")
    tenant_id = created["company"]["id"]
    _activate_primary_user(client, created)
    _submit_profile(client)
    client.post(
        f"/api/admin/companies/{tenant_id}/profile-decision",
        headers=ADMIN_HEADERS,
        json={"decision": "approve", "comment": ""},
    )

    assistance = client.post(f"/api/admin/companies/{tenant_id}/assistance", headers=ADMIN_HEADERS)
    assert assistance.status_code == 200
    result = client.post("/local/optimize", json=base_payload)
    assert result.status_code == 200, result.text

    history = client.get("/api/history")
    assert history.status_code == 200
    run = history.json()[0]
    assert run["support_intervention"] is True
    assert run["support_label"] == "Intervention du support AxioLoad"
    assert run["created_by_type"] == "super_admin"
    assert run["vehicle_snapshot"]
    vehicle = run["vehicle_snapshot"][0]
    assert vehicle["model_id"] == "semi_trailer"
    assert vehicle["interior_length_mm"] > 0


def test_global_vehicle_is_locked_and_can_be_duplicated(tmp_path):
    client = TestClient(create_app(tmp_path))
    created = _create_company(client, "Flotte Client")
    tenant_id = created["company"]["id"]
    _activate_primary_user(client, created)
    _submit_profile(client)
    client.post(
        f"/api/admin/companies/{tenant_id}/profile-decision",
        headers=ADMIN_HEADERS,
        json={"decision": "approve", "comment": ""},
    )
    client.post(f"/api/admin/companies/{tenant_id}/assistance", headers=ADMIN_HEADERS)

    vehicles = client.get("/api/vehicles").json()
    global_vehicle = next(vehicle for vehicle in vehicles if vehicle["origin"] == "global")
    modified = dict(global_vehicle)
    modified["name"] = "Modification interdite"
    blocked = client.post("/api/vehicles", json=modified)
    assert blocked.status_code == 403

    duplicated = client.post(
        f"/api/vehicles/{global_vehicle['model_id']}/duplicate",
        json={"model_id": "client-semi", "name": "Semi client"},
    )
    assert duplicated.status_code == 200, duplicated.text
    assert duplicated.json()["origin"] == "custom"
    assert duplicated.json()["base_model_id"] == global_vehicle["model_id"]


def test_dashboard_boots_before_first_optimization(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.get("/api/admin/bootstrap", headers=ADMIN_HEADERS)
    assert response.status_code == 200, response.text
    dashboard = response.json()["dashboard"]
    assert set(dashboard["sections"]) == {"accounts", "usage", "quality", "api"}
    for section in dashboard["sections"].values():
        for metric in section.values():
            assert {"value", "share_pct", "trend_pct", "unit"} <= set(metric)
