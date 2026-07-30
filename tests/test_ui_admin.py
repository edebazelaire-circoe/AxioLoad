from __future__ import annotations

from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app


def test_super_admin_assets_and_activation_pages_are_loaded(tmp_path):
    client = TestClient(create_app(tmp_path))

    response = client.get("/")
    assert response.status_code == 200
    assert 'id="open-settings"' in response.text
    assert '<script src="/static/admin.js?v=0.12.0"></script>' in response.text
    assert '<link rel="stylesheet" href="/static/admin.css?v=0.12.0">' in response.text

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
