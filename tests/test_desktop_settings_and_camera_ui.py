from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

from pallet_optimizer.api import create_app


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "pallet_optimizer" / "static"


def test_desktop_workspace_assets_are_injected_once(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    for path in ("/", "/login"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.text.count('/static/desktop_workspace.css?v=0.19.6') == 1
        assert response.text.count('/static/desktop_workspace.js?v=0.19.6') == 1


def test_login_and_settings_keep_desktop_layout_on_a_narrow_viewport() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.set_content(
            """
            <main class="login-shell">
              <div class="auth-account-switch"><button>Utilisateur</button><button>Superadmin</button></div>
              <div class="fixed-login-accounts__grid"><article>Compte 1</article><article>Compte 2</article></div>
              <form class="login-form">
                <label>Entreprise<input></label><label>E-mail<input></label><label>Mot de passe<input></label>
                <div class="login-actions"><button>Connexion</button></div>
              </form>
            </main>
            <section id="tab-settings" class="settings-page panel tab-panel active">
              <div class="panel-heading"><div><h2>Paramètres</h2></div><button>Fermer</button></div>
              <div class="settings-sections">
                <section class="settings-card">Compte</section>
                <section class="settings-card">Apparence</section>
                <section class="settings-card full-width company-endpoint-card">
                  <fieldset class="company-ai-mode-selector">
                    <label class="company-ai-mode-choice">Passerelle</label>
                    <label class="company-ai-mode-choice">Clé API</label>
                  </fieldset>
                  <div class="settings-actions company-endpoint-actions">
                    <button class="primary">Enregistrer</button>
                    <button>Tester</button>
                    <button>Supprimer</button>
                  </div>
                </section>
              </div>
            </section>
            """
        )
        for stylesheet in (
            "app.css",
            "auth_experience.css",
            "fixed_test_accounts.css",
            "company_ai_endpoint.css",
            "desktop_workspace.css",
        ):
            page.add_style_tag(path=str(STATIC / stylesheet))

        layout = page.evaluate(
            """() => {
              const tracks = selector => getComputedStyle(document.querySelector(selector)).gridTemplateColumns.split(' ').filter(Boolean).length;
              const login = document.querySelector('.login-shell').getBoundingClientRect();
              const settings = document.querySelector('#tab-settings').getBoundingClientRect();
              const actions = document.querySelector('.company-endpoint-actions');
              const firstAction = actions.querySelector('button').getBoundingClientRect();
              return {
                loginWidth: login.width,
                loginColumns: tracks('.login-form'),
                authColumns: tracks('.auth-account-switch'),
                accountColumns: tracks('.fixed-login-accounts__grid'),
                settingsWidth: settings.width,
                settingsColumns: tracks('#tab-settings .settings-sections'),
                modeColumns: tracks('#tab-settings .company-ai-mode-selector'),
                headingDisplay: getComputedStyle(document.querySelector('#tab-settings .panel-heading')).display,
                actionsDisplay: getComputedStyle(actions).display,
                actionWidth: firstAction.width,
                actionsWidth: actions.getBoundingClientRect().width,
                pageWidth: document.documentElement.scrollWidth,
                viewportWidth: window.innerWidth,
              };
            }"""
        )

        assert layout["loginWidth"] >= 1000
        assert layout["loginColumns"] == 3
        assert layout["authColumns"] == 2
        assert layout["accountColumns"] == 2
        assert layout["settingsWidth"] >= 1120
        assert layout["settingsColumns"] == 2
        assert layout["modeColumns"] == 2
        assert layout["headingDisplay"] == "flex"
        assert layout["actionsDisplay"] == "flex"
        assert layout["actionWidth"] < layout["actionsWidth"]
        assert layout["pageWidth"] > layout["viewportWidth"]
        browser.close()


def test_duplicate_business_prompt_is_removed_only_from_settings() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            """
            <button id="open-settings">Paramètres</button>
            <main>
              <section id="tab-settings"><div class="settings-sections"><section id="dc-prompt-settings">Doublon paramètres</section></div></section>
              <section id="tab-prompt-center"><h2>Prompts de contrôle documentaire</h2></section>
            </main>
            """
        )
        page.add_script_tag(path=str(STATIC / "desktop_workspace.js"))
        page.wait_for_function("() => !document.querySelector('#dc-prompt-settings')")

        assert page.locator('#dc-prompt-settings').count() == 0
        assert page.locator('#tab-prompt-center').is_visible()
        assert page.locator('#tab-prompt-center').get_by_text('Prompts de contrôle documentaire').is_visible()
        browser.close()


def test_document_control_keeps_upload_above_and_only_camera_below() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            """
            <main>
              <div id="dc-message" class="message hidden"></div>
              <form id="dc-form">
                <label class="dc-dropzone">Déposer un fichier<span class="dc-file-state">PDF, JPG ou PNG</span><input type="file" name="left_file"></label>
                <label class="dc-dropzone">Déposer un fichier<span class="dc-file-state">PDF, JPG ou PNG</span><input type="file" name="right_file"></label>
              </form>
            </main>
            """
        )
        page.add_style_tag(path=str(STATIC / "app.css"))
        page.add_style_tag(path=str(STATIC / "document_camera.css"))
        page.add_script_tag(path=str(STATIC / "document_camera.js"))
        page.wait_for_selector('.dc-camera-tools[data-for="left_file"] .dc-camera-button')

        upper = page.locator('input[name="left_file"]').locator('xpath=..')
        lower = page.locator('.dc-camera-tools[data-for="left_file"]')
        assert upper.get_by_text('Déposer un fichier').is_visible()
        assert upper.get_by_text('PDF, JPG ou PNG').is_visible()
        assert lower.get_by_text('Prendre une photo').is_visible()
        assert 'Déposer un fichier' not in lower.inner_text()
        assert 'PDF, JPG ou PNG' not in lower.inner_text()
        assert page.locator('.dc-camera-status').first.is_hidden()
        assert page.locator('body > input[data-dc-camera-for="left_file"]').count() == 1
        assert page.locator('main input[data-dc-camera-for="left_file"]').count() == 0
        browser.close()


def test_desktop_workspace_javascript_has_valid_syntax() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js n’est pas disponible dans cet environnement")
    result = subprocess.run(
        [node, "--check", str(STATIC / "desktop_workspace.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
