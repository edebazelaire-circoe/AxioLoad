from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app
from pallet_optimizer.facturx import FacturXRepository, build_facturx_xml, select_profile, validate_invoice


def valid_invoice() -> dict:
    return {
        "direction": "outgoing",
        "document_type": "invoice",
        "invoice_number": "F-2026-0001",
        "issue_date": "2026-09-01",
        "currency": "EUR",
        "seller": {
            "legal_name": "Entreprise émettrice",
            "siren": "123456789",
            "country_code": "FR",
        },
        "buyer": {
            "legal_name": "Entreprise cliente",
            "siren": "987654321",
            "country_code": "FR",
        },
        "lines": [
            {
                "description": "Prestation logistique",
                "quantity": "2",
                "unit_code": "C62",
                "unit_price": "100.00",
                "vat_rate": "20.00",
                "line_net_amount": "200.00",
            }
        ],
        "total_net": "200.00",
        "total_tax": "40.00",
        "total_gross": "240.00",
    }


def test_valid_invoice_is_en16931_and_totals_are_recomputed() -> None:
    invoice = valid_invoice()
    report = validate_invoice(invoice)

    assert report["valid"] is True
    assert report["profile"] == "EN 16931"
    assert report["totals"] == {"net": "200.00", "tax": "40.00", "gross": "240.00"}
    assert select_profile(invoice) == "EN 16931"


def test_reverse_charge_selects_extended_profile() -> None:
    invoice = valid_invoice()
    invoice["reverse_charge"] = True

    assert select_profile(invoice) == "EXTENDED"


def test_inconsistent_totals_block_generation() -> None:
    invoice = valid_invoice()
    invoice["total_gross"] = "250.00"

    report = validate_invoice(invoice)

    assert report["valid"] is False
    assert any(error["field"] == "total_gross" for error in report["errors"])


def test_xml_generation_requires_a_valid_invoice() -> None:
    xml = build_facturx_xml(valid_invoice())
    root = ElementTree.fromstring(xml)

    assert root.tag == "CrossIndustryInvoice"
    assert root.attrib["profile"] == "EN 16931"
    assert root.findtext("./Header/InvoiceNumber") == "F-2026-0001"


def test_repository_deletes_source_by_policy_and_requires_human_validation(tmp_path) -> None:
    app = create_app(tmp_path)
    repository = FacturXRepository(app.state.registry)
    created = repository.create_invoice("local", "local-user", {**valid_invoice(), "source_name": "facture.pdf"})

    assert created["source_deleted"] == 1
    assert created["status"] == "draft"

    validated = repository.validate_human("local", created["id"], "local-user")
    assert validated["status"] == "validated"
    assert validated["validated_by"] == "local-user"


def test_facturx_routes_are_registered_without_removing_document_control(tmp_path) -> None:
    app = create_app(tmp_path)
    paths = {route.path for route in app.routes}

    assert "/api/facturx/bootstrap" in paths
    assert "/api/facturx/invoices" in paths
    assert "/api/facturx/invoices/{invoice_id}/validate" in paths
    assert "/api/facturx/invoices/{invoice_id}/factur-x.xml" in paths
    assert "/api/document-control/bootstrap" in paths


def test_facturx_workspace_is_loaded_in_main_page(tmp_path) -> None:
    response = TestClient(create_app(tmp_path)).get("/")

    assert response.status_code == 200
    assert response.text.count('/static/facturx.css?v=0.20.2') == 1
    assert response.text.count('/static/facturx.js?v=0.20.2') == 1


def test_facturx_uses_the_shared_workspace_router() -> None:
    static = Path(__file__).resolve().parents[1] / "src" / "pallet_optimizer" / "static"
    facturx_script = (static / "facturx.js").read_text(encoding="utf-8")
    navigation_script = (static / "workspace_navigation_fix.js").read_text(encoding="utf-8")

    assert "card.dataset.workspace = 'facturx'" in facturx_script
    assert "tab.dataset.tab = 'facturx'" in facturx_script
    assert "data-facturx-workspace" not in facturx_script
    assert "function openWorkspace()" not in facturx_script
    assert "facturx: 'facturx.view'" in navigation_script
    assert "function openFacturxWorkspace()" in navigation_script


def test_facturx_has_one_persistence_path_and_no_browser_store() -> None:
    package_root = Path(__file__).resolve().parents[1] / "src" / "pallet_optimizer"
    python_sources = list(package_root.rglob("*.py"))
    storage_definitions = [
        path
        for path in python_sources
        if "CREATE TABLE IF NOT EXISTS electronic_invoices" in path.read_text(encoding="utf-8")
    ]

    assert storage_definitions == [package_root / "facturx.py"]

    frontend = (package_root / "static" / "facturx.js").read_text(encoding="utf-8")
    assert "/api/facturx/invoices" in frontend
    assert "localStorage" not in frontend
    assert "sessionStorage" not in frontend


def test_facturx_frontend_contains_visible_workspace_and_editable_lines() -> None:
    static = Path(__file__).resolve().parents[1] / "src" / "pallet_optimizer" / "static"
    script = (static / "facturx.js").read_text(encoding="utf-8")

    for token in (
        "Facturation électronique",
        "Créer et contrôler une facture Factur-X",
        "facturx-add-line",
        "Enregistrer le brouillon",
        "Valider humainement",
        "/api/facturx/invoices",
    ):
        assert token in script
