from __future__ import annotations

from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app


def test_super_admin_assets_and_activation_pages_are_loaded(tmp_path):
    client = TestClient(create_app(tmp_path))

    response = client.get("/")
    assert response.status_code == 200
    assert 'id="open-settings"' in response.text
    history_guard = '<script src="/static/history_stability.js?v=0.12.0"></script>'
    admin_script = '<script src="/static/admin.js?v=0.12.0"></script>'
    assert history_guard in response.text
    assert admin_script in response.text
    assert response.text.index(history_guard) < response.text.index(admin_script)
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

    guard_response = client.get("/static/history_stability.js")
    assert guard_response.status_code == 200
    guard = guard_response.text
    assert "pathname === '/api/history'" in guard
    assert "cachedResponse.clone()" in guard
    assert "if (!inFlight)" in guard
    assert "mutatesHistory" in guard

    assert client.get("/activate").status_code == 200
    assert client.get("/login").status_code == 200
