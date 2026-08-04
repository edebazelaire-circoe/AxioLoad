from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page, sync_playwright


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "pallet_optimizer"
    / "static"
    / "fixed_test_accounts_ui.js"
)

ACCOUNTS = {
    "enabled": True,
    "accounts": [
        {
            "key": "super_admin",
            "mode": "super_admin",
            "label": "Super administrateur",
            "description": "Vision globale.",
            "identifier": "b.olivier@circoe.com",
            "username": "superadmn",
            "password": "0123456789",
        },
        {
            "key": "company_admin",
            "mode": "user",
            "label": "Administrateur principal d’entreprise",
            "description": "Vision entreprise.",
            "tenant_id": "axioload-test-company",
            "company_name": "Entreprise test AxioLoad",
            "identifier": "olivierbaptiste6@gmail.com",
            "password": "0123456789",
        },
    ],
}


def _prepare_page(page: Page) -> None:
    page.set_content(
        """
        <main class="login-shell">
          <div class="auth-account-switch">
            <button type="button" data-auth-mode="user">Compte utilisateur</button>
            <button type="button" data-auth-mode="super_admin">Centre de gestion</button>
          </div>
          <form id="login-form">
            <input name="tenant_id">
            <input name="email">
            <input name="password" type="password">
            <button type="submit">Se connecter</button>
          </form>
        </main>
        """
    )
    page.evaluate(
        """accounts => {
          window.fetch = async url => {
            if (String(url).includes('/api/auth/test-accounts')) {
              return new Response(JSON.stringify(accounts), {
                status: 200,
                headers: {'Content-Type': 'application/json'}
              });
            }
            return new Response('{}', {status: 404});
          };
          window.activeMode = 'user';
          document.querySelectorAll('[data-auth-mode]').forEach(button => {
            button.addEventListener('click', () => {
              window.activeMode = button.dataset.authMode;
            });
          });
          document.querySelector('#login-form').addEventListener('submit', event => {
            event.preventDefault();
            window.submitted = {
              mode: window.activeMode,
              tenant_id: event.currentTarget.elements.tenant_id.value,
              email: event.currentTarget.elements.email.value,
              password: event.currentTarget.elements.password.value,
            };
          });
        }""",
        ACCOUNTS,
    )
    page.add_script_tag(path=str(SCRIPT))
    page.wait_for_selector('.fixed-login-account[data-test-account="company_admin"]')


def test_company_card_opens_the_company_superuser_profile() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        _prepare_page(page)

        assert page.locator('.fixed-login-account').count() == 2
        page.locator('[data-test-account="company_admin"]').click()
        page.wait_for_function("() => Boolean(window.submitted)")

        assert page.evaluate("window.submitted") == {
            "mode": "user",
            "tenant_id": "axioload-test-company",
            "email": "olivierbaptiste6@gmail.com",
            "password": "0123456789",
        }
        browser.close()


def test_super_admin_card_opens_the_global_management_profile() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        _prepare_page(page)

        page.locator('[data-test-account="super_admin"]').click()
        page.wait_for_function("() => Boolean(window.submitted)")

        assert page.evaluate("window.submitted") == {
            "mode": "super_admin",
            "tenant_id": "",
            "email": "b.olivier@circoe.com",
            "password": "0123456789",
        }
        browser.close()
