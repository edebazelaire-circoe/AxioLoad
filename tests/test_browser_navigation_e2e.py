from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright


USER_EMAIL = "olivierbaptiste6@gmail.com"
PASSWORD = "0123456789"
SUPER_ADMIN_USERNAME = "superadmn"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def live_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    port = _free_port()
    data_dir = tmp_path_factory.mktemp("browser-data")
    env = os.environ.copy()
    env.update(
        {
            "PLO_TEST_ACCOUNTS_ONLY": "1",
            "PLO_SUPER_ADMIN_EMAIL": "b.olivier@circoe.com",
            "PLO_SUPER_ADMIN_USERNAME": SUPER_ADMIN_USERNAME,
            "PLO_SUPER_ADMIN_PASSWORD": PASSWORD,
            "PLO_TEST_USER_EMAIL": USER_EMAIL,
            "PLO_TEST_USER_PASSWORD": PASSWORD,
            "PYTHONUNBUFFERED": "1",
        }
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "pallet_optimizer.cli",
            "--data-dir",
            str(data_dir),
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 30
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout else ""
            pytest.fail(f"AxioLoad s'est arrêté pendant le démarrage:\n{output}")
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=1) as response:
                if response.status == 200:
                    break
        except Exception as error:  # pragma: no cover - diagnostic de démarrage
            last_error = error
            time.sleep(0.2)
    else:
        process.terminate()
        output = process.stdout.read() if process.stdout else ""
        pytest.fail(f"AxioLoad n'a pas démarré: {last_error}\n{output}")

    yield base_url

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(headless=True)
        yield instance
        instance.close()


def _open_authenticated_page(
    browser: Browser,
    base_url: str,
    *,
    super_admin: bool,
) -> tuple[Page, list[str]]:
    context = browser.new_context(base_url=base_url, viewport={"width": 1600, "height": 1000})
    endpoint = "/api/auth/super-admin-login" if super_admin else "/api/auth/login"
    payload = (
        {"identifier": SUPER_ADMIN_USERNAME, "password": PASSWORD}
        if super_admin
        else {"tenant_id": "local", "email": USER_EMAIL, "password": PASSWORD}
    )
    response = context.request.post(f"{base_url}{endpoint}", data=payload)
    assert response.ok, f"Connexion impossible ({response.status}): {response.text()}"

    errors: list[str] = []
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
    page.on(
        "console",
        lambda message: errors.append(f"console: {message.text}")
        if message.type == "error" and not message.text.startswith("Failed to load resource:")
        else None,
    )
    page.on(
        "response",
        lambda http_response: errors.append(f"http {http_response.status}: {http_response.url}")
        if http_response.status >= 400
        else None,
    )
    page.goto("/", wait_until="networkidle")
    page.wait_for_function("document.body.dataset.applicationShellReady === 'true'")
    page.wait_for_timeout(1800)
    return page, errors


def _dom_snapshot(page: Page) -> dict[str, object]:
    return page.evaluate(
        r"""
        () => {
          const visible = element => {
            if (!element || element.hidden) return false;
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden'
              && Number(style.opacity || 1) !== 0 && rect.width > 0 && rect.height > 0;
          };
          const ids = [...document.querySelectorAll('[id]')].map(element => element.id);
          const counts = ids.reduce((result, id) => {
            result[id] = (result[id] || 0) + 1;
            return result;
          }, {});
          return {
            activePanels: [...document.querySelectorAll('.tab-panel.active')].map(panel => panel.id),
            visibleActivePanels: [...document.querySelectorAll('.tab-panel.active')]
              .filter(visible).map(panel => panel.id),
            duplicateIds: Object.entries(counts).filter(([, count]) => count > 1),
            workspace: document.body.dataset.workspace || null,
            shellRole: document.body.dataset.shellRole || null,
            shellCurrent: window.AxioLoadShell?.current?.() || null,
            activeButtons: [...document.querySelectorAll('button.active')]
              .map(button => ({
                id: button.id || null,
                text: button.textContent.trim().replace(/\s+/g, ' '),
                shellControl: button.dataset.shellControl || null,
                shellWorkspace: button.dataset.shellWorkspace || null,
                shellTab: button.dataset.shellTab || null,
                shellView: button.dataset.shellView || null,
                legacy: button.dataset.shellLegacy || null,
              })),
            visibleButtons: [...document.querySelectorAll('button')]
              .filter(visible)
              .map(button => ({
                id: button.id || null,
                text: button.textContent.trim().replace(/\s+/g, ' '),
                shellControl: button.dataset.shellControl || null,
                shellWorkspace: button.dataset.shellWorkspace || null,
                shellTab: button.dataset.shellTab || null,
                shellView: button.dataset.shellView || null,
              })),
          };
        }
        """
    )


def _assert_dom_stable(page: Page, expected_panel: str, expected_workspace: str | None = None) -> None:
    page.wait_for_timeout(300)
    snapshot = _dom_snapshot(page)
    assert snapshot["activePanels"] == [expected_panel], snapshot
    assert snapshot["visibleActivePanels"] == [expected_panel], snapshot
    assert snapshot["duplicateIds"] == [], snapshot
    if expected_workspace is not None:
        assert snapshot["workspace"] == expected_workspace, snapshot


def _click_and_check(
    page: Page,
    selector: str,
    panel: str,
    workspace: str | None,
) -> None:
    control = page.locator(selector)
    expect(control).to_have_count(1)
    expect(control).to_be_visible()
    expect(control).to_be_enabled()
    control.click()
    _assert_dom_stable(page, panel, workspace)


def _exercise_all_navigation_controls(page: Page, *, super_admin: bool) -> None:
    expect(page.locator("#site-logout")).to_have_count(1)
    expect(page.locator("#site-logout")).to_be_visible()
    expect(page.locator('[data-shell-control="settings"]')).to_be_visible()

    admin = page.locator('[data-shell-control="admin"]')
    if super_admin:
        expect(admin).to_be_visible()
    else:
        expect(admin).to_be_hidden()

    _click_and_check(
        page,
        '.workspace-card[data-shell-workspace="database"]',
        "tab-vehicles",
        "database",
    )
    _click_and_check(page, '[data-shell-tab="vehicles"]', "tab-vehicles", "database")
    _click_and_check(page, '[data-shell-view="prompt-center"]', "tab-prompt-center", "database")

    _click_and_check(
        page,
        '.workspace-card[data-shell-workspace="optimization"]',
        "tab-data",
        "optimization",
    )
    for tab_name in ("data", "results", "history", "route", "total"):
        _click_and_check(
            page,
            f'[data-shell-tab="{tab_name}"]',
            f"tab-{tab_name}",
            "optimization",
        )

    _click_and_check(
        page,
        '.workspace-card[data-shell-workspace="documents"]',
        "tab-document-control",
        "documents",
    )
    _click_and_check(
        page,
        '[data-shell-view="document-new"]',
        "tab-document-control",
        "documents",
    )
    _click_and_check(
        page,
        '[data-shell-view="document-history"]',
        "tab-document-control",
        "documents",
    )

    _click_and_check(page, '[data-shell-control="settings"]', "tab-settings", None)
    _click_and_check(page, '[data-shell-control="close-settings"]', "tab-document-control", "documents")

    if super_admin:
        _click_and_check(page, '[data-shell-control="admin"]', "tab-admin", None)
        _click_and_check(page, '[data-shell-control="close-admin"]', "tab-document-control", "documents")


def _exercise_rapid_clicks(page: Page) -> None:
    page.evaluate(
        """
        () => {
          const selectors = [
            '.workspace-card[data-shell-workspace="database"]',
            '.workspace-card[data-shell-workspace="optimization"]',
            '.workspace-card[data-shell-workspace="documents"]',
          ];
          for (let round = 0; round < 40; round += 1) {
            for (const selector of selectors) document.querySelector(selector).click();
          }
          document.querySelector('.workspace-card[data-shell-workspace="optimization"]').click();
        }
        """
    )
    _assert_dom_stable(page, "tab-data", "optimization")

    page.evaluate(
        """
        () => {
          const selectors = [
            '[data-shell-tab="data"]',
            '[data-shell-tab="results"]',
            '[data-shell-tab="history"]',
            '[data-shell-tab="route"]',
            '[data-shell-tab="total"]',
          ];
          for (let round = 0; round < 30; round += 1) {
            for (const selector of selectors) document.querySelector(selector).click();
          }
          document.querySelector('[data-shell-tab="history"]').click();
        }
        """
    )
    _assert_dom_stable(page, "tab-history", "optimization")


def _logout_and_check(page: Page, base_url: str) -> None:
    context = page.context
    assert any(cookie["name"] == "axioload_session" for cookie in context.cookies())

    page.locator("#site-logout").click()
    page.wait_for_url(f"{base_url}/login**", timeout=5000)
    expect(page.locator("#login-form")).to_be_visible()

    assert not any(cookie["name"] == "axioload_session" for cookie in context.cookies())

    response = context.request.get(f"{base_url}/api/company/context")
    assert response.status == 200, response.text()
    anonymous = response.json()
    assert anonymous["mode"] == "user"
    assert anonymous["user"] is None
    assert anonymous["actor"] == "Utilisateur local"

    admin = context.request.get(f"{base_url}/api/admin/bootstrap")
    assert admin.status in {401, 403}, admin.text()


def test_real_browser_user_buttons_dom_and_logout(browser: Browser, live_server: str) -> None:
    page, errors = _open_authenticated_page(browser, live_server, super_admin=False)
    try:
        _exercise_all_navigation_controls(page, super_admin=False)
        _exercise_rapid_clicks(page)
        _logout_and_check(page, live_server)
        assert errors == [], errors
    finally:
        page.context.close()


def test_real_browser_super_admin_buttons_dom_and_logout(browser: Browser, live_server: str) -> None:
    page, errors = _open_authenticated_page(browser, live_server, super_admin=True)
    try:
        _exercise_all_navigation_controls(page, super_admin=True)
        _exercise_rapid_clicks(page)
        _logout_and_check(page, live_server)
        assert errors == [], errors
    finally:
        page.context.close()
