from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app
from pallet_optimizer.facturx import FacturXRepository


def _invoice(number: str) -> dict:
    return {
        "direction": "outgoing",
        "document_type": "invoice",
        "invoice_number": number,
        "issue_date": "2026-08-09",
        "currency": "EUR",
        "seller": {"legal_name": "Vendeur", "siren": "123456789", "country_code": "FR"},
        "buyer": {"legal_name": "Acheteur", "siren": "987654321", "country_code": "FR"},
        "lines": [
            {
                "description": "Prestation",
                "quantity": "1",
                "unit_code": "C62",
                "unit_price": "100.00",
                "vat_rate": "20.00",
                "line_net_amount": "100.00",
            }
        ],
        "total_net": "100.00",
        "total_tax": "20.00",
        "total_gross": "120.00",
    }


def test_facturx_data_is_isolated_by_tenant(tmp_path) -> None:
    app = create_app(tmp_path)
    registry = app.state.registry
    registry.create_tenant("tenant-a", "Tenant A")
    registry.create_tenant("tenant-b", "Tenant B")
    repository = FacturXRepository(registry)

    repository.save_party(
        "tenant-a",
        {
            "party_type": "customer",
            "legal_name": "Client A",
            "siren": "111222333",
            "country_code": "FR",
        },
    )
    repository.create_invoice("tenant-a", "user-a", _invoice("A-001"))

    assert len(repository.list_parties("tenant-a")) == 1
    assert len(repository.list_invoices("tenant-a")) == 1
    assert repository.list_parties("tenant-b") == []
    assert repository.list_invoices("tenant-b") == []


def test_unvalidated_invoice_cannot_be_exported(tmp_path) -> None:
    app = create_app(tmp_path)
    repository = FacturXRepository(app.state.registry)
    created = repository.create_invoice("local", "local-user", _invoice("LOCAL-001"))
    client = TestClient(app)

    blocked = client.get(f"/api/facturx/invoices/{created['id']}/factur-x.xml")
    assert blocked.status_code == 409

    repository.validate_human("local", created["id"], "local-user")
    exported = client.get(f"/api/facturx/invoices/{created['id']}/factur-x.xml")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/xml")


def test_facturx_reuses_the_document_control_ai_configuration() -> None:
    package = Path(__file__).resolve().parents[1] / "src" / "pallet_optimizer"
    bootstrap = (package / "facturx_bootstrap.py").read_text(encoding="utf-8")
    facturx = (package / "facturx.py").read_text(encoding="utf-8")

    assert "from .company_ai_dual_mode import get_connection_config" in bootstrap
    assert "DocumentControlRepository" in bootstrap
    assert "get_connection_config(" in bootstrap
    assert "CREATE TABLE IF NOT EXISTS document_ai_config" not in facturx
    assert '"store": False' in facturx


def test_https_hardening_secures_session_cookie_and_headers() -> None:
    app = FastAPI()

    @app.get("/cookie")
    def cookie() -> JSONResponse:
        response = JSONResponse({"ok": True})
        response.set_cookie(
            "axioload_session",
            "test-token",
            httponly=True,
            secure=False,
            samesite="lax",
        )
        return response

    response = TestClient(app, base_url="https://logipilot.test").get(
        "/cookie",
        headers={"X-Forwarded-Proto": "https"},
    )
    cookie_header = response.headers.get("set-cookie", "")

    assert "HttpOnly" in cookie_header
    assert "SameSite=lax" in cookie_header
    assert "Secure" in cookie_header
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "same-origin"
    assert "max-age=31536000" in response.headers["strict-transport-security"]


def test_cross_origin_browser_write_is_rejected_when_session_cookie_is_present() -> None:
    app = FastAPI()

    @app.post("/write")
    def write() -> dict[str, bool]:
        return {"ok": True}

    client = TestClient(app, base_url="https://logipilot.test")
    session_header = {"Cookie": "axioload_session=test-token"}

    rejected = client.post(
        "/write",
        headers={**session_header, "Origin": "https://evil.example"},
    )
    accepted = client.post(
        "/write",
        headers={**session_header, "Origin": "https://logipilot.test"},
    )

    assert rejected.status_code == 403
    assert accepted.status_code == 200


def test_final_facturx_ui_assets_are_loaded_once(tmp_path) -> None:
    response = TestClient(create_app(tmp_path)).get("/")

    assert response.status_code == 200
    assert response.text.count('/static/facturx_final.css?v=0.20.4') == 1
    assert response.text.count('/static/facturx_view_modes.js?v=0.20.4') == 1
