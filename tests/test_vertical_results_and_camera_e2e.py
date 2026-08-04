from __future__ import annotations

import socket
import threading
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from PIL import Image
from playwright.sync_api import sync_playwright

from pallet_optimizer.api import create_app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def vertical_camera_app(tmp_path: Path) -> Iterator[str]:
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
        pytest.fail("Le serveur AxioLoad n'a pas démarré pour les tests d'interface.")

    yield url

    server.should_exit = True
    thread.join(timeout=10)
    assert not thread.is_alive()


def test_solutions_are_displayed_below_their_matching_model(vertical_camera_app: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.goto(vertical_camera_app, wait_until="networkidle")
        page.wait_for_function("() => Boolean(window.AxioVerticalResults)")

        page.evaluate(
            """() => {
                const content = document.querySelector('#results-content');
                content.classList.remove('hidden');
                const cards = document.querySelector('#solution-cards');
                cards.innerHTML = `
                  <article class="solution-card active" role="button"><div class="solution-card-title">Solution 1</div><div class="metric-big">4,2 <span>m.l.</span></div></article>
                  <article class="solution-card" role="button"><div class="solution-card-title">Solution 2</div><div class="metric-big">4,4 <span>m.l.</span></div></article>`;
                window.AxioVerticalResults.render({
                  solutions: [
                    {rank: 1, method_code: 'cp_sat', method_name: 'Modèle exact', vehicle_count: 1, occupied_length_m: 4.2},
                    {rank: 2, method_code: 'extreme_points', method_name: 'Points extrêmes', vehicle_count: 1, occupied_length_m: 4.4}
                  ],
                  method_outcomes: [
                    {index: 1, code: 'cp_sat', name: 'Modèle 1 · Exact', short_label: 'CP-SAT', status: 'success', vehicle_count: 1, occupied_length_m: 4.2},
                    {index: 2, code: 'extreme_points', name: 'Modèle 2 · Points extrêmes', short_label: 'GRASP', status: 'success', vehicle_count: 1, occupied_length_m: 4.4},
                    {index: 3, code: 'brkga_hybrid', name: 'Modèle 3 · Génétique', short_label: 'BRKGA', status: 'failure', reason: 'Aucun plan valide.'}
                  ]
                });
              }"""
        )

        rows = page.locator('#opx-model-solution-stack .opx-model-solution-row')
        rows.nth(2).wait_for(state="visible")
        assert rows.count() == 3
        assert rows.nth(0).locator('.solution-card-title').inner_text() == 'Solution 1'
        assert rows.nth(1).locator('.solution-card-title').inner_text() == 'Solution 2'
        assert rows.nth(2).locator('.opx-no-solution').is_visible()

        first_model = rows.nth(0).locator('.ovr-model-card').bounding_box()
        first_solution = rows.nth(0).locator('.opx-solution-below').bounding_box()
        first_row = rows.nth(0).bounding_box()
        second_row = rows.nth(1).bounding_box()
        assert first_model and first_solution and first_row and second_row
        assert first_solution['y'] > first_model['y'] + first_model['height'] - 2
        assert second_row['y'] > first_row['y'] + first_row['height']

        browser.close()


def test_camera_button_converts_a_photo_to_jpeg(vertical_camera_app: str, tmp_path: Path) -> None:
    photo = tmp_path / "camera-source.png"
    Image.new("RGB", (1200, 900), "white").save(photo, format="PNG")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.goto(vertical_camera_app, wait_until="networkidle")
        page.wait_for_function("() => Boolean(window.AxioDocumentCamera)")
        page.locator('#workspace-switcher [data-workspace="documents"]').click()
        page.wait_for_function(
            "() => document.body.dataset.workspace === 'documents' && document.querySelector('#tab-document-control')?.classList.contains('active')"
        )

        camera = page.locator('input[data-dc-camera-for="left_file"]')
        camera.wait_for(state="attached")
        assert camera.get_attribute('capture') == 'environment'
        assert camera.get_attribute('accept') == 'image/*'

        camera.set_input_files(str(photo))
        status = page.locator('.dc-camera-tools[data-for="left_file"] .dc-camera-status')
        status.wait_for(state="visible")
        page.wait_for_function(
            "() => document.querySelector('.dc-camera-tools[data-for=\"left_file\"] .dc-camera-status')?.textContent.includes('Photo prête')"
        )

        uploaded = page.locator('input[name="left_file"]').evaluate(
            "input => ({required: input.required, name: input.files[0]?.name, type: input.files[0]?.type, size: input.files[0]?.size})"
        )
        assert uploaded['required'] is False
        assert uploaded['name'].endswith('.jpg')
        assert uploaded['type'] == 'image/jpeg'
        assert uploaded['size'] > 0
        assert page.locator('.dc-camera-tools[data-for="left_file"] .dc-camera-preview img').is_visible()

        browser.close()
