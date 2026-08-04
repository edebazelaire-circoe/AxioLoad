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
def loading_ui_app(tmp_path: Path) -> Iterator[str]:
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
        pytest.fail("Le serveur AxioLoad n'a pas démarré pour le test de mise en page.")

    yield url

    server.should_exit = True
    thread.join(timeout=10)
    assert not thread.is_alive()


def test_calculation_time_is_aligned_with_loading_actions(loading_ui_app: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1500, "height": 1000})
            page.set_default_timeout(15_000)
            page.goto(loading_ui_app, wait_until="domcontentloaded")

            page.locator('#workspace-switcher [data-workspace="optimization"]').click()
            page.locator('#tab-data.active').wait_for(state="visible")
            actions = page.locator('#tab-data .form-actions.opx-resilient-actions')
            actions.wait_for(state="visible")

            assert page.locator('#budget-seconds').evaluate(
                "element => element.closest('label').parentElement.classList.contains('opx-resilient-actions')"
            )

            controls = [
                page.locator('#add-row'),
                page.locator('#duplicate-row'),
                page.locator('#budget-seconds'),
                page.locator('#optimize'),
            ]
            boxes = [control.bounding_box() for control in controls]
            assert all(box is not None for box in boxes)
            bottoms = [round(box["y"] + box["height"], 1) for box in boxes if box is not None]
            assert max(bottoms) - min(bottoms) <= 3.0, bottoms
        finally:
            browser.close()
