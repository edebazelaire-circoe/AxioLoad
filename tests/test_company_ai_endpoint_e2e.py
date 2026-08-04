from __future__ import annotations

import socket
import threading
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import sync_playwright

from pallet_optimizer.api import create_app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def endpoint_settings_app(tmp_path: Path) -> Iterator[str]:
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
        pytest.fail("Le serveur AxioLoad n'a pas démarré pour le test endpoint.")

    yield url

    server.should_exit = True
    thread.join(timeout=10)
    assert not thread.is_alive()


@pytest.mark.parametrize("width,height", ((1280, 900), (390, 844)))
def test_primary_manager_sees_endpoint_only_setting(endpoint_settings_app: str, width: int, height: int) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(endpoint_settings_app, wait_until="networkidle")
        page.wait_for_selector('#company-ai-endpoint-title', state='attached')
        page.locator('#open-settings').click()
        page.wait_for_function(
            "() => document.querySelector('#tab-settings')?.classList.contains('active')"
        )

        card = page.locator('.company-endpoint-card')
        card.wait_for(state='visible')
        assert card.locator('text=Votre entreprise garde la main.').is_visible()
        assert card.locator('text=Seul le responsable de l’entreprise').is_visible()
        assert card.locator('input[type="url"]').count() == 1
        assert card.locator('input[type="password"]').count() == 0
        assert card.locator('#dc-a-key').count() == 0
        assert card.locator('select').count() == 0

        input_field = card.locator('#company-ai-endpoint-url')
        input_field.fill('https://gateway.example/axioload/document-control')
        card.locator('#company-ai-endpoint-save').click()
        page.wait_for_function(
            "() => document.querySelector('#company-ai-endpoint-message')?.textContent.includes('Endpoint enregistré')"
        )
        assert card.locator('#company-ai-endpoint-status strong').inner_text() == 'gateway.example'

        body_metrics = page.evaluate(
            "() => ({bodyWidth: document.documentElement.scrollWidth, viewportWidth: window.innerWidth})"
        )
        assert body_metrics['bodyWidth'] <= body_metrics['viewportWidth'] + 1

        if width <= 650:
            card_box = card.bounding_box()
            save_box = card.locator('#company-ai-endpoint-save').bounding_box()
            test_box = card.locator('#company-ai-endpoint-test').bounding_box()
            assert card_box and save_box and test_box
            assert save_box['height'] >= 43
            assert test_box['height'] >= 43
            assert save_box['width'] >= card_box['width'] - 50
            assert test_box['width'] >= card_box['width'] - 50

        browser.close()
