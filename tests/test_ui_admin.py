from __future__ import annotations

from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app


def test_super_admin_assets_and_activation_pages_are_loaded(tmp_path):
    client = TestClient(create_app(tmp_path))

    response = client.get("/")
    assert response.status_code == 200
    assert 'id="open-settings"' in response.text
    units_script = '<script src="/static/units_import.js?v=0.18.0"></script>'
    workflow_script = '<script src="/static/workflow_layout.js?v=0.18.0"></script>'
    results_script = '<script src="/static/results_enhancements.js?v=0.18.0"></script>'
    admin_script = '<script src="/static/admin.js?v=0.18.0"></script>'
    assert units_script in response.text
    assert workflow_script in response.text
    assert results_script in response.text
    assert admin_script in response.text
    assert response.text.index(units_script) < response.text.index(workflow_script) < response.text.index(results_script) < response.text.index(admin_script)
    assert '<link rel="stylesheet" href="/static/admin.css?v=0.18.0">' in response.text
    assert '<link rel="stylesheet" href="/static/workflow_layout.css?v=0.18.0">' in response.text
    assert '<link rel="stylesheet" href="/static/results_enhancements.css?v=0.18.0">' in response.text
    assert "history_stability.js" not in response.text

    units_response = client.get("/static/units_import.js")
    assert units_response.status_code == 200
    units = units_response.text
    for token in ("Unité des dimensions", "Millimètres", "Mètres", "ancien format .xls", "dimension_unit", "missingTotalData"):
        assert token in units

    workflow_response = client.get("/static/workflow_layout.js")
    assert workflow_response.status_code == 200
    workflow = workflow_response.text
    for token in ("Flotte disponible", "+ Ajouter un camion", "vehicle_fleet", "calculation-toolbar", "Client"):
        assert token in workflow

    results_response = client.get("/static/results_enhancements.js")
    assert results_response.status_code == 200
    results = results_response.text
    for token in (
        "État des méthodes de calcul",
        "vehicle-accordion",
        "diag-clickable",
        "captureFleetSheet",
        "Contraintes routières poids lourd",
        "60 s",
    ):
        assert token in results
    assert "Véhicules de la solution" not in results
    assert "vehicle-thumbnail" not in results

    script_response = client.get("/static/admin.js")
    assert script_response.status_code == 200
    script = script_response.text
    for token in (
        "open-admin", "Pilotage AxioLoad", "Entreprises clientes", "Droits communs de l’entreprise",
        "Clé API visible une seule fois", "Intervention du support AxioLoad", "admin-dashboard-users",
    ):
        assert token in script

    assert client.get("/activate").status_code == 200
    assert client.get("/login").status_code == 200
