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
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
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


def _assert_only_panel(page: Page, workspace: str, panel_id: str, *, settle_ms: int = 0) -> None:
    page.wait_for_function(
        """([workspace, panelId]) =>
          document.body.dataset.workspace === workspace &&
          document.querySelector(panelId)?.classList.contains('active') &&
          document.querySelectorAll('main > .tab-panel.active').length === 1
        """,
        arg=[workspace, panel_id],
        timeout=10_000,
    )
    if settle_ms:
        page.wait_for_timeout(settle_ms)
    assert page.locator("main > .tab-panel.active").count() == 1
    assert page.locator(panel_id).get_attribute("aria-hidden") == "false"
    assert page.locator(panel_id).is_visible()


def _click_tile_edge(page: Page, workspace: str) -> None:
    tile = page.locator(f'#workspace-switcher [data-workspace="{workspace}"]')
    tile.wait_for(state="visible")
    box = tile.bounding_box()
    assert box is not None
    page.mouse.click(box["x"] + box["width"] - 12, box["y"] + box["height"] - 12)


def test_real_browser_navigation_loads_the_requested_pages_and_survives_reload(live_app: str) -> None:
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
            page.locator("#workspace-switcher").wait_for(state="visible")
            page.locator('#workspace-switcher [data-workspace="facturx"]').wait_for(state="visible")
            page.wait_for_function(
                "() => document.querySelector('#workspace-switcher')?.dataset.visibleCount === '4'"
            )
            workspace_boxes = [
                page.locator(f'#workspace-switcher [data-workspace="{workspace}"]').bounding_box()
                for workspace in ("database", "optimization", "documents", "facturx")
            ]
            assert all(workspace_boxes)
            workspace_y = [box["y"] for box in workspace_boxes if box]
            assert max(workspace_y) - min(workspace_y) < 3

            _assert_only_panel(page, "database", "#tab-vehicles", settle_ms=1800)

            _click_tile_edge(page, "optimization")
            _assert_only_panel(page, "optimization", "#tab-data", settle_ms=1800)

            page.locator('nav.tabs [data-tab="route"]').click()
            _assert_only_panel(page, "optimization", "#tab-route", settle_ms=1200)

            page.reload(wait_until="networkidle")
            page.locator("#workspace-switcher").wait_for(state="visible")
            _assert_only_panel(page, "optimization", "#tab-route", settle_ms=1800)

            _click_tile_edge(page, "documents")
            _assert_only_panel(page, "documents", "#tab-document-control", settle_ms=1800)
            assert page.locator("#dc-new").is_visible()

            page.locator('nav.tabs [data-workspace-tab="document-history"]').click()
            _assert_only_panel(page, "documents", "#tab-document-control", settle_ms=1000)
            assert "dc-hidden" not in (page.locator("#dc-history").get_attribute("class") or "")
            assert page.locator("#dc-history").is_visible()

            _click_tile_edge(page, "database")
            _assert_only_panel(page, "database", "#tab-vehicles", settle_ms=1800)

            page.locator('nav.tabs [data-workspace-tab="prompts"]').click()
            _assert_only_panel(page, "database", "#tab-prompt-center", settle_ms=1000)

            page.locator('nav.tabs [data-tab="invoice-parties"]').click()
            _assert_only_panel(page, "database", "#tab-invoice-parties", settle_ms=800)
            assert page.locator('#facturx-party-form').is_visible()
            assert page.get_by_text('Clients et fournisseurs', exact=True).is_visible()

            _click_tile_edge(page, "facturx")
            _assert_only_panel(page, "facturx", "#tab-facturx", settle_ms=1200)
            transform_tab = page.locator('nav.tabs [data-tab="facturx"]')
            history_tab = page.locator('nav.tabs [data-facturx-view="history"]')
            assert transform_tab.inner_text() == "Transformation des factures"
            assert history_tab.inner_text() == "Historique"
            assert page.locator('#facturx-form').is_visible()
            assert page.locator('#facturx-source-file').is_visible()
            assert page.locator('#facturx-extract').is_visible()
            assert 'active' not in (page.locator('#tab-data').get_attribute('class') or '').split()

            history_tab.click()
            page.wait_for_function(
                "() => document.querySelector('#tab-facturx')?.classList.contains('facturx-history-mode')"
            )
            assert not page.locator('#facturx-form').is_visible()
            assert page.locator('#facturx-list').is_visible()
            assert history_tab.get_attribute('aria-selected') == 'true'

            transform_tab.click()
            page.wait_for_function(
                "() => document.querySelector('#tab-facturx')?.classList.contains('facturx-transform-mode')"
            )
            assert page.locator('#facturx-form').is_visible()
            assert not page.locator('#facturx-list').is_visible()

            page.reload(wait_until="networkidle")
            page.locator("#workspace-switcher").wait_for(state="visible")
            page.locator('#tab-facturx').wait_for(state="attached")
            _assert_only_panel(page, "facturx", "#tab-facturx", settle_ms=1200)
            assert page.locator('#facturx-form').is_visible()
            assert page.locator('nav.tabs [data-tab="facturx"]').inner_text() == "Transformation des factures"
            assert page.locator('nav.tabs [data-facturx-view="history"]').is_visible()
            assert 'active' not in (page.locator('#tab-data').get_attribute('class') or '').split()

            page.locator("#open-settings").click()
            page.locator("#tab-settings.active").wait_for(state="visible")
            dark_choice = page.locator('label.theme-choice:has(input[value="dark"])')
            dark_box = dark_choice.bounding_box()
            assert dark_box is not None
            page.mouse.click(dark_box["x"] + dark_box["width"] - 10, dark_box["y"] + dark_box["height"] / 2)
            page.wait_for_function("document.documentElement.dataset.theme === 'dark'")

            assert not page_errors, page_errors
            assert not console_errors, console_errors
        except Exception:
            page.screenshot(path=str(ARTIFACTS / "workspace-navigation-failure.png"), full_page=True)
            raise
        finally:
            context.tracing.stop(path=str(ARTIFACTS / "workspace-navigation-trace.zip"))
            context.close()
            browser.close()
