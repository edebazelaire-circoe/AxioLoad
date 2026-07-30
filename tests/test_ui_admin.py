from __future__ import annotations

from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app


def test_admin_panel_asset_is_loaded_without_replacing_settings(tmp_path):
    client = TestClient(create_app(tmp_path))

    response = client.get("/")
    assert response.status_code == 200
    assert 'id="open-settings"' in response.text
    assert '<script src="/static/admin.js"></script>' in response.text

    script_response = client.get("/static/admin.js")
    assert script_response.status_code == 200
    script = script_response.text
    for token in (
        "open-admin",
        "tab-admin",
        "Configuration administrateur",
        "Panneau prêt à être configuré",
        "Configuration à venir",
    ):
        assert token in script
