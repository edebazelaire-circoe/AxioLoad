from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app


ROOT = Path(__file__).resolve().parents[1]


def test_settings_page_replaces_engine_status_and_adds_guidance(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert 'id="open-settings"' in html
    assert 'id="tab-settings"' in html
    assert 'class="help-tip' in html
    assert "Portefeuille de moteurs validés" not in html
    assert "Paramètres du calcul" in html
    assert "Marchandises à charger" in html


def test_dark_theme_covers_application_surfaces():
    css = (ROOT / "src" / "pallet_optimizer" / "static" / "app.css").read_text(encoding="utf-8")
    assert 'html[data-theme="dark"]' in css
    for token in ("--paper", "--field", "--surface-2", "--canvas-start", "--line"):
        assert token in css


def test_preparatory_api_keys_remain_front_end_only(tmp_path):
    app = create_app(tmp_path)
    route_paths = {getattr(route, "path", "") for route in app.routes}
    assert "/api/settings" not in route_paths
    assert "/api/settings/api-keys" not in route_paths
    js = (ROOT / "src" / "pallet_optimizer" / "static" / "app.js").read_text(encoding="utf-8")
    assert "SETTINGS_STORAGE_KEY" in js
    assert "localStorage" in js
    assert "La clé de" in js


def test_3d_canvas_context_is_initialized_before_rendering():
    js = (ROOT / "src" / "pallet_optimizer" / "static" / "app.js").read_text(encoding="utf-8")
    canvas_index = js.index("const canvas = $('#viewer')")
    context_index = js.index("const ctx = canvas.getContext('2d')")
    viewer_index = js.index("function drawViewer()")
    assert canvas_index < context_index < viewer_index
