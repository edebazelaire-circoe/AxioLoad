from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app
from pallet_optimizer.document_control import DocumentControlRepository
from pallet_optimizer.persistence import _connect


def _activate_user(
    app,
    tenant_id: str,
    *,
    index: int,
    role: str = "member",
) -> tuple[dict, str]:
    admin = app.state.admin
    admin.ensure_company(tenant_id, f"Entreprise {tenant_id}", status="active")
    user = admin._create_user(  # type: ignore[attr-defined]
        tenant_id,
        first_name=f"Responsable{index}",
        last_name=tenant_id,
        email=f"responsable{index}@{tenant_id}.example",
        role=role,
    )
    with _connect(app.state.registry.registry_path) as db:
        db.execute(
            "UPDATE company_users SET status='active',active=1 WHERE id=?",
            (user["id"],),
        )
        db.execute(
            "UPDATE tenants SET status='active' WHERE id=?",
            (tenant_id,),
        )
    token = admin.create_user_session(tenant_id, user["id"])
    return admin.get_user(user["id"]), token


def _client_for(app, token: str) -> TestClient:
    client = TestClient(app)
    client.cookies.set("axioload_session", token)
    return client


def test_sole_active_user_can_manage_company_ai_even_with_legacy_member_role(
    tmp_path: Path,
) -> None:
    app = create_app(tmp_path)
    user, token = _activate_user(app, "societe-seule", index=1, role="member")
    client = _client_for(app, token)

    assert user["role"] == "member"
    assert len([entry for entry in app.state.admin.list_users("societe-seule") if entry["active"]]) == 1

    configuration = client.get("/api/company/document-ai-config")
    status = client.get("/api/company/document-ai-status")
    bootstrap = client.get("/api/document-control/bootstrap")

    assert configuration.status_code == 200, configuration.text
    assert status.status_code == 200
    assert status.json()["can_manage"] is True
    assert bootstrap.status_code == 200
    assert bootstrap.json()["is_primary_admin"] is True

    saved = client.put(
        "/api/company/document-ai-config",
        json={
            "connection_mode": "endpoint",
            "endpoint_url": "https://ia.societe-seule.example/axioload/document-control",
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["endpoint_host"] == "ia.societe-seule.example"


def test_sole_user_fallback_stops_when_a_second_active_user_exists(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    first, first_token = _activate_user(app, "societe-equipe", index=1, role="member")
    first_client = _client_for(app, first_token)
    assert first_client.get("/api/company/document-ai-config").status_code == 200

    _activate_user(app, "societe-equipe", index=2, role="member")

    denied = first_client.get("/api/company/document-ai-config")
    public_status = first_client.get("/api/company/document-ai-status")
    assert denied.status_code == 403
    assert public_status.status_code == 200
    assert public_status.json()["can_manage"] is False

    with _connect(app.state.registry.registry_path) as db:
        db.execute("UPDATE company_users SET role='primary' WHERE id=?", (first["id"],))

    allowed_again = first_client.get("/api/company/document-ai-config")
    assert allowed_again.status_code == 200, allowed_again.text


def test_three_single_user_companies_keep_separate_openai_configuration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "PLO_DOCUMENT_SECRET_KEY",
        "axioload-multi-company-document-ai-test-secret",
    )
    app = create_app(tmp_path)
    repository = DocumentControlRepository(app.state.registry)
    expected = {
        "entreprise-alpha": (
            "gpt-5-mini",
            "sk-proj-alpha-abcdefghijklmnopqrstuvwxyz-1001",
        ),
        "entreprise-beta": (
            "gpt-4.1",
            "sk-proj-beta-abcdefghijklmnopqrstuvwxyz-2002",
        ),
        "entreprise-gamma": (
            "gpt-4o-mini",
            "sk-proj-gamma-abcdefghijklmnopqrstuvwxyz-3003",
        ),
    }
    clients: dict[str, TestClient] = {}

    for index, (tenant_id, (model, api_key)) in enumerate(expected.items(), start=1):
        _, token = _activate_user(app, tenant_id, index=index, role="member")
        client = _client_for(app, token)
        clients[tenant_id] = client

        saved = client.put(
            "/api/company/document-ai-config",
            json={
                "connection_mode": "openai_api_key",
                "model": model,
                "api_key": api_key,
                "vendor_zero_retention_confirmed": True,
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["model"] == model
        assert saved.json()["api_key_hint"] == api_key[-4:]
        assert "api_key" not in saved.json()

    for tenant_id, (model, api_key) in expected.items():
        public_config = clients[tenant_id].get("/api/company/document-ai-config")
        assert public_config.status_code == 200
        assert public_config.json()["model"] == model
        assert public_config.json()["api_key_hint"] == api_key[-4:]

        internal_config = repository.get_connection_config(  # type: ignore[attr-defined]
            tenant_id,
            include_secret=True,
        )
        assert internal_config["model"] == model
        assert internal_config["api_key"] == api_key

    with _connect(app.state.registry.registry_path) as db:
        rows = db.execute(
            """SELECT tenant_id,model,key_hint,encrypted_api_key
               FROM document_ai_config
               WHERE tenant_id IN ('entreprise-alpha','entreprise-beta','entreprise-gamma')
               ORDER BY tenant_id"""
        ).fetchall()

    assert len(rows) == 3
    for row in rows:
        model, api_key = expected[str(row["tenant_id"])]
        assert row["model"] == model
        assert row["key_hint"] == api_key[-4:]
        assert api_key not in str(row["encrypted_api_key"] or "")
