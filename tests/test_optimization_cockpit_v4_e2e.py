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
def cockpit_app(tmp_path: Path) -> Iterator[str]:
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
        pytest.fail("Le serveur AxioLoad n'a pas démarré pour le test cockpit.")

    yield url
    server.should_exit = True
    thread.join(timeout=10)
    assert not thread.is_alive()


def _render_cockpit(page) -> None:
    page.evaluate(
        """() => {
          const content = document.querySelector('#results-content');
          content.classList.remove('hidden');
          document.querySelector('#empty-results')?.classList.add('hidden');
          const cards = document.querySelector('#solution-cards');
          cards.innerHTML = `
            <article class="solution-card active" role="button"><div class="solution-card-title">Solution 1</div></article>
            <article class="solution-card" role="button"><div class="solution-card-title">Solution 2</div></article>
            <article class="solution-card" role="button"><div class="solution-card-title">Solution 3</div></article>`;
          const payload = {
            solutions: [
              {rank: 1, method_code: 'cp_sat', method_name: 'Modèle exact', vehicle_count: 1, occupied_length_m: 4.2, total_linear_meters: 4.1, vehicle_plans: []},
              {rank: 2, method_code: 'extreme_points', method_name: 'Points extrêmes', vehicle_count: 1, occupied_length_m: 4.4, total_linear_meters: 4.3, vehicle_plans: []},
              {rank: 3, method_code: 'tabu_search', method_name: 'Recherche tabou', vehicle_count: 1, occupied_length_m: 4.6, total_linear_meters: 4.5, vehicle_plans: []}
            ],
            method_outcomes: [
              {index: 1, code: 'cp_sat', name: 'Modèle 1 · Exact', short_label: 'CP-SAT', status: 'success', vehicle_count: 1, occupied_length_m: 4.2},
              {index: 2, code: 'extreme_points', name: 'Modèle 2 · Points extrêmes', short_label: 'GRASP', status: 'success', vehicle_count: 1, occupied_length_m: 4.4},
              {index: 3, code: 'brkga_hybrid', name: 'Modèle 3 · Génétique', short_label: 'BRKGA', status: 'failure', reason: 'Aucun plan valide.'},
              {index: 4, code: 'tabu_search', name: 'Modèle 4 · Recherche tabou', short_label: 'TABU', status: 'success', vehicle_count: 1, occupied_length_m: 4.6},
              {index: 5, code: 'routing_hybrid', name: 'Modèle 5 · Hybride tournée', short_label: 'VRP', status: 'timeout', reason: 'Temps de calcul atteint.'}
            ]
          };
          const request = {
            items: [
              {id: 'PAL-001', quantity: 12, weight: 500, destination: 'Lyon', delivery_order: 1},
              {id: 'PAL-002', quantity: 8, weight: 450, destination: 'Saint-Étienne', delivery_order: 2}
            ],
            vehicle_policy: {forced_vehicle_id: 'semi_13_6', max_vehicles: 2},
            budget_seconds: 30,
            default_margins: {left: 20},
            total_optimization_enabled: false
          };
          window.AxioVerticalResults.render(payload);
          window.AxioOptimizationCockpit.render(payload, request);
        }"""
    )
    page.locator("#opx4-cockpit").wait_for(state="visible")
    page.locator("#opx4-scenario-list .opx4-scenario-row").nth(4).wait_for(state="visible")
    page.locator("#opx-model-row .ovr-model-card").nth(4).wait_for(state="visible")


def test_cockpit_composes_existing_results_without_remapping_models(cockpit_app: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1050})
        page.goto(cockpit_app, wait_until="networkidle")
        page.wait_for_function("() => Boolean(window.AxioOptimizationCockpit && window.AxioVerticalResults)")
        page.locator('#workspace-switcher [data-workspace="optimization"]').click()
        page.locator('nav.tabs [data-tab="results"]').click()
        _render_cockpit(page)

        scenarios = page.locator("#opx4-scenario-list .opx4-scenario-row")
        assert scenarios.count() == 5
        assert scenarios.evaluate_all("rows => rows.map(row => row.dataset.method)") == [
            "cp_sat", "extreme_points", "brkga_hybrid", "tabu_search", "routing_hybrid"
        ]
        assert scenarios.nth(0).locator(".opx4-rank").inner_text() == "1"
        assert scenarios.nth(2).is_disabled()
        assert scenarios.nth(4).is_disabled()

        assert page.locator("#opx4-model-detail-slot #opx-method-portfolio").count() == 1
        assert page.locator("#opx4-viewer-slot .viewer-grid").count() == 1
        assert page.locator("#opx4-decision-slot .decision-panel").count() == 1
        assert page.locator("#opx-model-row .ovr-model-card").count() == 5
        assert page.locator("#opx-solution-row .opx-solution-cell").count() == 5
        assert page.locator("#opx4-input-summary").get_by_text("Lyon", exact=True).is_visible()
        assert page.locator("#opx4-input-summary").get_by_text("Saint-Étienne", exact=True).is_visible()
        assert "method_code" in page.locator(".opx4-engine-badge").inner_text()

        browser.close()


def test_cockpit_keeps_horizontal_overflow_inside_components_on_phone(cockpit_app: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(cockpit_app, wait_until="networkidle")
        page.wait_for_function("() => Boolean(window.AxioOptimizationCockpit && window.AxioVerticalResults)")
        page.locator('#workspace-switcher [data-workspace="optimization"]').click()
        page.locator('nav.tabs [data-tab="results"]').click()
        _render_cockpit(page)

        widths = page.evaluate(
            """() => ({
              body: document.documentElement.scrollWidth,
              viewport: window.innerWidth,
              scenariosClient: document.querySelector('.opx4-scenario-list').clientWidth,
              scenariosScroll: document.querySelector('.opx4-scenario-list').scrollWidth,
              comparisonClient: document.querySelector('.opx-comparison-scroll').clientWidth,
              comparisonScroll: document.querySelector('.opx-comparison-scroll').scrollWidth
            })"""
        )
        assert widths["body"] <= widths["viewport"] + 1
        assert widths["scenariosScroll"] > widths["scenariosClient"]
        assert widths["comparisonScroll"] > widths["comparisonClient"]
        assert page.locator("#opx4-viewer-slot .viewer-grid").is_visible()

        browser.close()
