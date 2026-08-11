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
from pallet_optimizer.company_ai_dual_mode import ALLOWED_OPENAI_MODELS


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def ai_settings_app(tmp_path: Path, monkeypatch) -> Iterator[str]:
    monkeypatch.setenv("PLO_DOCUMENT_SECRET_KEY", "axioload-browser-test-secret")
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
        pytest.fail("Le serveur AxioLoad n'a pas démarré pour le test de connexion IA.")

    yield url

    server.should_exit = True
    thread.join(timeout=10)
    assert not thread.is_alive()


@pytest.mark.parametrize("width,height", ((1280, 900), (390, 844)))
def test_primary_manager_can_choose_endpoint_or_api_key(
    ai_settings_app: str,
    width: int,
    height: int,
) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(ai_settings_app, wait_until="networkidle")
        page.wait_for_selector('#company-ai-connection-title', state='attached')
        page.locator('#open-settings').click()
        page.wait_for_function(
            "() => document.querySelector('#tab-settings')?.classList.contains('active')"
        )

        assert page.locator('#company-ai-user-card').count() == 1
        card = page.locator('#company-ai-user-card')
        card.wait_for(state='visible')
        assert card.get_by_text(
            'Configuration réservée au responsable principal.', exact=True
        ).is_visible()
        assert card.locator(
            '.company-ai-mode-choice strong', has_text='Passerelle de mon entreprise'
        ).is_visible()
        assert card.locator(
            '.company-ai-mode-choice strong', has_text='Clé API OpenAI'
        ).is_visible()
        assert card.locator('input[name="company-ai-mode"]').count() == 2
        assert card.locator('input[type="url"]').count() == 1
        assert card.locator('input[type="password"]').count() == 1
        assert card.locator('select#company-ai-model').count() == 1
        assert card.locator('#dc-a-key').count() == 0

        endpoint_panel = card.locator('#company-ai-endpoint-panel')
        api_panel = card.locator('#company-ai-api-panel')
        assert endpoint_panel.is_visible()
        assert not api_panel.is_visible()

        input_field = card.locator('#company-ai-endpoint-url')
        input_field.fill('https://gateway.example/axioload/document-control')
        card.locator('#company-ai-connection-save').click()
        page.wait_for_function(
            "() => document.querySelector('#company-ai-connection-message')?.textContent.includes('Configuration enregistrée')"
        )
        assert card.locator('#company-ai-connection-status strong').inner_text() == 'gateway.example'

        card.locator(
            '.company-ai-mode-choice', has_text='Clé API OpenAI'
        ).click()
        assert api_panel.is_visible()
        assert not endpoint_panel.is_visible()
        model_ids = card.locator('#company-ai-model option').evaluate_all(
            "options => options.map(option => option.value)"
        )
        assert set(model_ids) == ALLOWED_OPENAI_MODELS
        assert card.locator('#company-ai-model').input_value() == 'gpt-5-mini'
        assert card.locator('.company-ai-model-note strong').inner_text() == 'Liste contrôlée par LogiPilot'

        body_metrics = page.evaluate(
            "() => ({bodyWidth: document.documentElement.scrollWidth, viewportWidth: window.innerWidth})"
        )
        assert body_metrics['bodyWidth'] <= body_metrics['viewportWidth'] + 1

        if width <= 650:
            card_box = card.bounding_box()
            mode_one = card.locator('.company-ai-mode-choice').nth(0).bounding_box()
            mode_two = card.locator('.company-ai-mode-choice').nth(1).bounding_box()
            save_box = card.locator('#company-ai-connection-save').bounding_box()
            test_box = card.locator('#company-ai-connection-test').bounding_box()
            delete_box = card.locator('#company-ai-connection-delete').bounding_box()
            assert card_box and mode_one and mode_two and save_box and test_box and delete_box
            assert mode_two['y'] > mode_one['y'] + mode_one['height'] - 2
            card_right = card_box['x'] + card_box['width'] + 1
            for box in (mode_one, mode_two, save_box, test_box, delete_box):
                assert box['x'] >= card_box['x'] - 1
                assert box['x'] + box['width'] <= card_right
            assert save_box['height'] >= 43
            assert test_box['height'] >= 43
            assert delete_box['height'] >= 43

        browser.close()


def test_api_key_mode_can_be_saved_without_exposing_the_key(ai_settings_app: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(ai_settings_app, wait_until="networkidle")
        page.locator('#open-settings').click()
        page.wait_for_function(
            "() => document.querySelector('#tab-settings')?.classList.contains('active')"
        )

        card = page.locator('#company-ai-user-card')
        card.wait_for(state='visible')
        card.locator('.company-ai-mode-choice', has_text='Clé API OpenAI').click()
        card.locator('#company-ai-model').select_option('gpt-5-mini')
        card.locator('#company-ai-api-key').fill('sk-proj-browser-test-abcdefghijklmnopqrstuvwxyz')
        card.locator('#company-ai-retention-confirmed').check()
        card.locator('#company-ai-connection-save').click()
        page.wait_for_function(
            "() => document.querySelector('#company-ai-connection-message')?.textContent.includes('Configuration enregistrée')"
        )

        assert card.locator('#company-ai-api-key').input_value() == ''
        assert 'browser-test-abcdefghijklmnopqrstuvwxyz' not in page.content()
        assert 'gpt-5-mini' in card.locator('#company-ai-connection-status').inner_text()

        browser.close()
