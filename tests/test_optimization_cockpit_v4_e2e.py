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


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def results_app(tmp_path: Path) -> Iterator[str]:
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(tmp_path), host="127.0.0.1", port=port, log_level="warning", access_log=False)
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
        pytest.fail("Le serveur AxioLoad n'a pas démarré pour le test des résultats.")

    yield url
    server.should_exit = True
    thread.join(timeout=10)
    assert not thread.is_alive()


def _open_results(page: Page, app_url: str) -> None:
    page.goto(app_url, wait_until="networkidle")
    page.wait_for_function("() => Boolean(window.AxioVerticalResults)")
    assert page.evaluate("() => typeof window.AxioOptimizationCockpit") == "undefined"
    page.locator('#workspace-switcher [data-workspace="optimization"]').click()
    page.locator('nav.tabs [data-tab="results"]').click()
    page.wait_for_function(
        "() => document.body.dataset.workspace === 'optimization' "
        "&& document.querySelector('#tab-results')?.classList.contains('active')"
    )


def _render_results(page: Page) -> None:
    page.evaluate(
        """() => {
          const content = document.querySelector('#results-content');
          content.classList.remove('hidden');
          document.querySelector('#empty-results')?.classList.add('hidden');
          const cards = document.querySelector('#solution-cards');
          cards.innerHTML = '<article class="solution-card active" role="button"><div class="solution-card-title">Solution 1</div></article>'
            + '<article class="solution-card" role="button"><div class="solution-card-title">Solution 2</div></article>'
            + '<article class="solution-card" role="button"><div class="solution-card-title">Solution 3</div></article>';
          window.AxioVerticalResults.render({
            solutions: [
              {rank: 1, method_code: 'cp_sat', method_name: 'Modèle exact', vehicle_count: 1, occupied_length_m: 4.2},
              {rank: 2, method_code: 'extreme_points', method_name: 'Points extrêmes', vehicle_count: 1, occupied_length_m: 4.4},
              {rank: 3, method_code: 'tabu_search', method_name: 'Recherche tabou', vehicle_count: 1, occupied_length_m: 4.6}
            ],
            method_outcomes: [
              {index: 1, code: 'cp_sat', name: 'Modèle 1 · Exact', short_label: 'CP-SAT', status: 'success'},
              {index: 2, code: 'extreme_points', name: 'Modèle 2 · Points extrêmes', short_label: 'GRASP', status: 'success'},
              {index: 3, code: 'brkga_hybrid', name: 'Modèle 3 · Génétique', short_label: 'BRKGA', status: 'failure'},
              {index: 4, code: 'tabu_search', name: 'Modèle 4 · Recherche tabou', short_label: 'TABU', status: 'success'},
              {index: 5, code: 'routing_hybrid', name: 'Modèle 5 · Hybride tournée', short_label: 'VRP', status: 'timeout'}
            ]
          });
        }"""
    )
    page.locator("#opx-model-row .ovr-model-card").nth(4).wait_for(state="visible")


def test_results_keep_pre_cockpit_comparison_layout(results_app: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1050})
        _open_results(page, results_app)
        _render_results(page)

        assert page.locator("#opx4-cockpit").count() == 0
        assert page.locator("#opx-method-portfolio").is_visible()
        assert page.locator("#opx-model-row .ovr-model-card").count() == 5
        assert page.locator("#opx-solution-row .opx-solution-cell").count() == 5
        assert page.locator(".viewer-grid").count() == 1
        assert page.locator(".decision-panel").count() == 1

        browser.close()


def test_results_keep_comparison_overflow_on_phone_without_cockpit(results_app: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        _open_results(page, results_app)
        _render_results(page)

        metrics = page.locator(".opx-comparison-scroll").evaluate(
            "element => ({clientWidth: element.clientWidth, scrollWidth: element.scrollWidth, "
            "bodyWidth: document.documentElement.scrollWidth, viewportWidth: window.innerWidth})"
        )
        assert metrics["scrollWidth"] > metrics["clientWidth"]
        assert metrics["bodyWidth"] <= metrics["viewportWidth"] + 1
        assert page.locator("#opx4-cockpit").count() == 0

        browser.close()
