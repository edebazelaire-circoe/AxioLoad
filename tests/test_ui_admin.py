from __future__ import annotations

from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app


def test_super_admin_assets_and_activation_pages_are_loaded(tmp_path):
    client = TestClient(create_app(tmp_path))

    response = client.get("/")
    assert response.status_code == 200
    assert 'id="open-settings"' in response.text
    units_script = '<script src="/static/units_import.js?v=0.12.2"></script>'
    admin_script = '<script src="/static/admin.js?v=0.12.2"></script>'
    assert units_script in response.text
    assert admin_script in response.text
    assert response.text.index(units_script) < response.text.index(admin_script)
    assert '<link rel="stylesheet" href="/static/admin.css?v=0.12.2">' in response.text
    assert "history_stability.js" not in response.text

    units_response = client.get("/static/units_import.js")
    assert units_response.status_code == 200
    units = units_response.text
    for token in (
        "Unité des dimensions",
        "Millimètres",
        "Mètres",
        "L’ancien format Excel .xls",
        "dimension_unit",
        "missingTotalData",
    ):
        assert token in units

    script_response = client.get("/static/admin.js")
    assert script_response.status_code == 200
    script = script_response.text
    for token in (
        "open-admin",
        "Pilotage AxioLoad",
        "Entreprises clientes",
        "Droits communs de l’entreprise",
        "Clé API visible une seule fois",
        "Intervention du support AxioLoad",
        "admin-dashboard-users",
    ):
        assert token in script

    assert client.get("/activate").status_code == 200
    assert client.get("/login").status_code == 200
