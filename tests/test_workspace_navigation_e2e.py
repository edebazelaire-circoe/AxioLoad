from __future__ import annotations

import socket
import threading
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import Page, sync_playwright

from pallet_optimizer.api import create_app


ARTIFACTS = Path("test-results")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def live_app(tmp_path: Path) -> Iterator[str]:
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(tmp_path),
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=1) as response:
                if response.status == 200:
                    break
        except OSError:
            time.sleep(0.1)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        pytest.fail("Le serveur AxioLoad n'a pas démarré pour le test navigateur.")

    yield url
    server.should_exit = True
    thread.join(timeout=10)
    assert not thread.is_alive(), "Le serveur du test navigateur ne s'est pas arrêté."


def _assert_only_panel(page: Page, panel_id: str, *, settle_ms: int = 0) -> None:
    page.wait_for_function(
        """panelId =>
          document.querySelector(panelId)?.classList.contains('active') &&
          document.querySelectorAll('main > .tab-panel.active').length === 1
        """,
        arg=panel_id,
        timeout=10_000,
    )
    if settle_ms:
        page.wait_for_timeout(settle_ms)
    assert page.locator("main > .tab-panel.active").count() == 1
    assert page.locator(panel_id).get_attribute("aria-hidden") == "false"
    assert page.locator(panel_id).is_visible()


def _sidebar(page: Page, name: str):
    selector = (
        f'#workspace-switcher .circoe-v3-nav-item[data-workspace="{name}"], '
        f'#workspace-switcher .circoe-v3-nav-item[data-circoe-workspace="{name}"]'
    )
    return page.locator(selector)


def _nav_label(item) -> str:
    return item.locator(":scope > span:not(.circoe-v3-icon)").inner_text().strip()


def test_real_browser_navigation_uses_eight_workspaces_and_preserves_business_views(live_app: str) -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    console_errors: list[str] = []
    page_errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1500, "height": 1000})
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = context.new_page()
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: page_errors.append(str(error)))

        try:
            page.goto(live_app, wait_until="networkidle")
            page.locator("#workspace-switcher.circoe-v3-sidebar").wait_for(state="visible")
            items = page.locator("#workspace-switcher .circoe-v3-nav-item")
            assert items.count() == 8
            expected = [
                "1. Base de données",
                "2. Optimisation",
                "3. Contrôle documentaire",
                "4. Contrôle réglementaire",
                "5. Facturation électronique / Factur-X",
                "6. Historique & traçabilité",
                "7. Paramètres & IA",
                "8. Super Admin",
            ]
            assert [_nav_label(items.nth(index)) for index in range(8)] == expected

            boxes = [items.nth(index).bounding_box() for index in range(8)]
            assert all(boxes)
            assert all(boxes[index + 1]["y"] > boxes[index]["y"] for index in range(7))
            assert max(abs(box["x"] - boxes[0]["x"]) for box in boxes if box) < 2

            _assert_only_panel(page, "#tab-vehicles", settle_ms=1200)

            _sidebar(page, "optimization").click()
            _assert_only_panel(page, "#tab-data", settle_ms=1200)
            assert page.locator("#optimize").is_visible()
            assert page.locator("#cargo-table").is_visible()

            page.locator('nav.tabs [data-tab="results"]').click()
            _assert_only_panel(page, "#tab-results", settle_ms=500)
            assert page.locator("#tab-results").get_attribute("data-preserve-optimization-models") == "true"

            page.locator('nav.tabs [data-tab="route"]').click()
            _assert_only_panel(page, "#tab-route", settle_ms=500)
            page.reload(wait_until="networkidle")
            page.locator("#workspace-switcher.circoe-v3-sidebar").wait_for(state="visible")
            _assert_only_panel(page, "#tab-route", settle_ms=1000)

            _sidebar(page, "documents").click()
            _assert_only_panel(page, "#tab-document-control", settle_ms=1000)
            assert page.locator("#dc-new").is_visible()
            page.locator('nav.tabs [data-workspace-tab="document-history"]').click()
            page.locator("#dc-history").wait_for(state="visible", timeout=10_000)
            assert page.locator("#dc-history").is_visible()

            _sidebar(page, "regulatory").click()
            _assert_only_panel(page, "#tab-regulatory", settle_ms=200)
            assert page.get_by_text("Préparé · non actif", exact=True).is_visible()
            assert page.get_by_text("Aucune règle réglementaire n’est activée dans cette version.", exact=True).is_visible()

            _sidebar(page, "database").click()
            _assert_only_panel(page, "#tab-vehicles", settle_ms=700)
            page.locator('nav.tabs [data-workspace-tab="prompts"]').click()
            _assert_only_panel(page, "#tab-prompt-center", settle_ms=500)
            page.locator('nav.tabs [data-tab="invoice-parties"]').click()
            _assert_only_panel(page, "#tab-invoice-parties", settle_ms=400)
            assert page.locator('#facturx-party-form').is_visible()

            _sidebar(page, "facturx").click()
            _assert_only_panel(page, "#tab-facturx", settle_ms=700)
            transform_tab = page.locator('nav.tabs [data-tab="facturx"]')
            history_tab = page.locator('nav.tabs [data-facturx-view="history"]')
            assert transform_tab.inner_text() == "Nouvelle facture"
            assert page.locator('#facturx-form').is_visible()
            assert page.locator('#facturx-source-file').is_visible()
            assert page.locator('#facturx-extract').is_visible()
            history_tab.click()
            page.wait_for_function("() => document.querySelector('#tab-facturx')?.classList.contains('facturx-history-mode')")
            assert page.locator('#facturx-list').is_visible()
            transform_tab.click()
            assert page.locator('#facturx-form').is_visible()

            _sidebar(page, "history").click()
            _assert_only_panel(page, "#tab-history", settle_ms=600)
            assert _sidebar(page, "history").get_attribute("aria-current") == "page"

            _sidebar(page, "settings").click()
            page.locator("#tab-settings.active").wait_for(state="visible")
            assert _sidebar(page, "settings").get_attribute("aria-current") == "page"
            dark_choice = page.locator('label.theme-choice:has(input[value="dark"])')
            dark_choice.click()
            page.wait_for_function("document.documentElement.dataset.theme === 'dark'")

            admin = _sidebar(page, "admin")
            if page.locator("#open-admin").count() == 0:
                assert admin.is_disabled()

            assert not page_errors, page_errors
            assert not console_errors, console_errors
        except Exception:
            page.screenshot(path=str(ARTIFACTS / "workspace-navigation-failure.png"), full_page=True)
            raise
        finally:
            context.tracing.stop(path=str(ARTIFACTS / "workspace-navigation-trace.zip"))
            context.close()
            browser.close()
