from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

from pallet_optimizer.api import create_app


SURFACE_SCRIPT = (
    Path(__file__).parents[1]
    / "src"
    / "pallet_optimizer"
    / "static"
    / "company_ai_user_surface.js"
)


def test_application_loads_only_the_user_settings_surface(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    html = client.get("/").text

    assert html.count('/static/company_ai_user_surface.js?v=0.19.7') == 1
    assert '/static/company_ai_endpoint.js?v=0.19.5' not in html
    assert '/static/company_ai_endpoint.js?v=0.19.6' not in html


def test_non_primary_user_gets_redacted_company_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(
        "PLO_DOCUMENT_SECRET_KEY",
        "axioload-test-secret-for-redacted-company-status",
    )
    client = TestClient(create_app(tmp_path))
    secret_value = "test-api-key-abcdefghijklmnopqrstuvwxyz"
    saved = client.put(
        "/api/company/document-ai-config",
        json={
            "connection_mode": "openai_api_key",
            "model": "gpt-5-mini",
            "api_key": secret_value,
            "vendor_zero_retention_confirmed": True,
        },
    )
    assert saved.status_code == 200, saved.text

    monkeypatch.setattr(
        "pallet_optimizer.document_control_bootstrap._primary",
        lambda request, context: False,
    )

    private_config = client.get("/api/company/document-ai-config")
    public_status = client.get("/api/company/document-ai-status")

    assert private_config.status_code == 403
    assert public_status.status_code == 200
    payload = public_status.json()
    assert payload == {
        "configured": True,
        "connection_mode": "openai_api_key",
        "provider": "openai",
        "model": "gpt-5-mini",
        "can_manage": False,
        "explanation": (
            "La connexion au contrôle documentaire se configure dans les Paramètres "
            "de l’espace utilisateur. Seul le responsable principal de l’entreprise "
            "peut enregistrer ou remplacer une passerelle ou une clé API."
        ),
    }
    serialized = public_status.text.lower()
    assert "api_key" not in serialized
    assert "key_hint" not in serialized
    assert "endpoint_url" not in serialized
    assert secret_value not in public_status.text


def test_browser_removes_superadmin_editor_and_uses_user_settings() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.set_content(
            """
            <main>
              <section id="tab-settings">
                <div class="settings-sections">
                  <section class="settings-card full-width">
                    <h3 id="api-settings-title">Gestion des clés API</h3>
                  </section>
                </div>
              </section>
            </main>
            <div id="admin-company-api">
              <section id="dc-admin-ai" class="admin-card dc-admin-ai">
                <h3>IA de contrôle documentaire</h3>
                <input id="dc-a-key" type="password">
              </section>
            </div>
            """
        )
        page.evaluate(
            """() => {
              window.fetch = async url => {
                const path = String(url);
                if (path.includes('/api/company/document-ai-config')) {
                  return new Response(JSON.stringify({detail: 'Responsable principal requis'}), {
                    status: 403,
                    headers: {'Content-Type': 'application/json'}
                  });
                }
                if (path.includes('/api/company/document-ai-status')) {
                  return new Response(JSON.stringify({
                    configured: false,
                    connection_mode: 'endpoint',
                    provider: 'client_endpoint',
                    model: 'managed_by_company',
                    can_manage: false,
                    explanation: 'Configuration côté utilisateur.'
                  }), {
                    status: 200,
                    headers: {'Content-Type': 'application/json'}
                  });
                }
                return new Response('{}', {status: 404, headers: {'Content-Type': 'application/json'}});
              };
            }"""
        )
        page.add_script_tag(path=str(SURFACE_SCRIPT))

        page.wait_for_selector('#dc-admin-ai[data-company-ai-sentinel="1"]', state="attached")
        page.wait_for_selector('#company-ai-user-card[data-company-endpoint-ready="readonly"]')

        assert page.locator('#admin-company-api').get_by_text('IA de contrôle documentaire').count() == 0
        assert page.locator('#admin-company-api input[type="password"]').count() == 0
        card = page.locator('#company-ai-user-card')
        assert card.get_by_text('Connexion à l’intelligence artificielle').is_visible()
        assert card.get_by_text('Configuration située dans l’espace utilisateur.').is_visible()
        assert card.locator('input[name="company-ai-mode"]').count() == 0
        browser.close()


def test_surface_javascript_has_valid_syntax() -> None:
    node = shutil.which("node")
    if not node:
        return
    subprocess.run([node, "--check", str(SURFACE_SCRIPT)], check=True)
