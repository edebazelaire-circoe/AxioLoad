from __future__ import annotations

import json
import os
import socket
import threading
import time
import urllib.request
from collections.abc import Iterator
from itertools import combinations
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import Page, sync_playwright

from pallet_optimizer.api import create_app


SCENARIO_ID = "AXIO-MULTI-SIM-001"

# Five deliberately different, deterministic business cases.  The goal of this
# scenario is not to replay one benchmark five times: every case changes both
# the number of pallets and the number of delivery clients.
CASES = (
    {
        "id": "SIM-01",
        "clients": (
            {"name": "QA S1 Client 1", "quantity": 8, "length": 1200, "width": 800, "height": 1000, "weight": 350},
        ),
    },
    {
        "id": "SIM-02",
        "clients": (
            {"name": "QA S2 Client 1", "quantity": 8, "length": 1200, "width": 800, "height": 1100, "weight": 400},
            {"name": "QA S2 Client 2", "quantity": 7, "length": 1000, "width": 1000, "height": 1200, "weight": 450},
        ),
    },
    {
        "id": "SIM-03",
        "clients": (
            {"name": "QA S3 Client 1", "quantity": 8, "length": 1200, "width": 800, "height": 1000, "weight": 420},
            {"name": "QA S3 Client 2", "quantity": 8, "length": 1000, "width": 1000, "height": 1150, "weight": 460},
            {"name": "QA S3 Client 3", "quantity": 8, "length": 1200, "width": 1000, "height": 1250, "weight": 500},
        ),
    },
    {
        "id": "SIM-04",
        "clients": (
            {"name": "QA S4 Client 1", "quantity": 9, "length": 1200, "width": 800, "height": 1000, "weight": 400},
            {"name": "QA S4 Client 2", "quantity": 9, "length": 1000, "width": 1000, "height": 1200, "weight": 480},
            {"name": "QA S4 Client 3", "quantity": 9, "length": 1200, "width": 1000, "height": 1300, "weight": 520},
            {"name": "QA S4 Client 4", "quantity": 9, "length": 800, "width": 800, "height": 900, "weight": 300},
        ),
    },
    {
        "id": "SIM-05",
        "clients": (
            {"name": "QA S5 Client 1", "quantity": 10, "length": 1200, "width": 800, "height": 1000, "weight": 380},
            {"name": "QA S5 Client 2", "quantity": 10, "length": 1000, "width": 1000, "height": 1150, "weight": 450},
            {"name": "QA S5 Client 3", "quantity": 10, "length": 1200, "width": 1000, "height": 1250, "weight": 520},
            {"name": "QA S5 Client 4", "quantity": 10, "length": 800, "width": 800, "height": 950, "weight": 320},
            {"name": "QA S5 Client 5", "quantity": 10, "length": 1200, "width": 800, "height": 1400, "weight": 560},
        ),
    },
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def multi_sim_app(tmp_path: Path) -> Iterator[str]:
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
        pytest.fail("AxioLoad did not start for the multi-simulation QA scenario.")

    yield url
    server.should_exit = True
    thread.join(timeout=10)
    assert not thread.is_alive()


def _evidence_path() -> Path | None:
    raw = os.environ.get("QA_EVIDENCE_PATH", "").strip()
    return Path(raw) if raw else None


def _artifact_dir(tmp_path: Path) -> Path:
    evidence = _evidence_path()
    root = evidence.parent if evidence else tmp_path / "qa-multi-sim-artifacts"
    root.mkdir(parents=True, exist_ok=True)
    screenshots = root / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    return root


def _rectangles_overlap(left: dict, right: dict) -> bool:
    return not (
        left["x_mm"] + left["envelope_width_mm"] <= right["x_mm"]
        or right["x_mm"] + right["envelope_width_mm"] <= left["x_mm"]
        or left["y_mm"] + left["envelope_length_mm"] <= right["y_mm"]
        or right["y_mm"] + right["envelope_length_mm"] <= left["y_mm"]
    )


def _clear_cargo_rows(page: Page) -> None:
    rows = page.locator("#cargo-table tbody tr")
    while rows.count():
        rows.first.locator(".row-delete").click()


def _fill_case(page: Page, case: dict) -> tuple[int, tuple[str, ...]]:
    _clear_cargo_rows(page)
    client_names: list[str] = []
    total_pallets = 0
    for client_index, client in enumerate(case["clients"], start=1):
        page.locator("#add-row").click()
        row = page.locator("#cargo-table tbody tr").last
        row.locator('[data-k="id"]').fill(f"QA-{case['id']}-C{client_index}")
        row.locator('[data-k="quantity"]').fill(str(client["quantity"]))
        row.locator('[data-k="shape"]').select_option(label="pallet")
        row.locator('[data-k="length"]').fill(str(client["length"]))
        row.locator('[data-k="width"]').fill(str(client["width"]))
        row.locator('[data-k="height"]').fill(str(client["height"]))
        row.locator('[data-k="weight"]').fill(str(client["weight"]))
        row.locator('[data-k="destination"]').fill(client["name"])
        row.locator('[data-k="delivery_order"]').fill(str(client_index))
        row.locator('[data-k="rotation_allowed"]').check()
        client_names.append(client["name"])
        total_pallets += int(client["quantity"])

    assert page.locator("#cargo-table tbody tr").count() == len(case["clients"])
    return total_pallets, tuple(client_names)


def _collect_result_metrics(result: dict, expected_pallets: int, expected_sources: set[str]) -> dict:
    assert result["status"] in {"completed", "completed_with_time_limit"}
    assert result["solutions"], "No feasible AxioLoad solution returned."
    best = result["solutions"][0]
    placements = [placement for plan in best["vehicle_plans"] for placement in plan["placements"]]

    assert len(placements) == expected_pallets
    assert len({placement["item_id"] for placement in placements}) == expected_pallets
    assert {placement["source_id"] for placement in placements} == expected_sources

    overlap_count = 0
    for plan in best["vehicle_plans"]:
        for left, right in combinations(plan["placements"], 2):
            if _rectangles_overlap(left, right):
                overlap_count += 1
    assert overlap_count == 0

    diagnostics = list(result.get("diagnostics") or []) + list(best.get("diagnostics") or [])
    error_diagnostics = [diag for diag in diagnostics if str(diag.get("severity", "")).lower() == "error"]
    assert error_diagnostics == []

    return {
        "optimizer_status": result["status"],
        "run_id": result.get("run_id"),
        "vehicle_count": best["vehicle_count"],
        "occupied_length_m": best["occupied_length_m"],
        "placement_count": len(placements),
        "unique_placement_count": len({placement["item_id"] for placement in placements}),
        "geometry_overlap_count": overlap_count,
        "error_diagnostic_count": len(error_diagnostics),
    }


def _write_html_report(root: Path, simulations: list[dict]) -> None:
    rows = []
    sections = []
    for sim in simulations:
        rows.append(
            "<tr>"
            f"<td>{sim['case_id']}</td><td>{sim['pallet_count']}</td><td>{sim['client_count']}</td>"
            f"<td>{sim['vehicle_count']}</td><td>{sim['placement_count']}/{sim['pallet_count']}</td>"
            f"<td>{sim['geometry_overlap_count']}</td><td>{sim['error_diagnostic_count']}</td><td>PASS</td>"
            "</tr>"
        )
        sections.append(
            f"<h2>{sim['case_id']} — {sim['pallet_count']} palettes / {sim['client_count']} clients</h2>"
            f"<p>Véhicules utilisés : <strong>{sim['vehicle_count']}</strong> — longueur occupée : "
            f"<strong>{sim['occupied_length_m']:.2f} m</strong> — placements : "
            f"<strong>{sim['placement_count']}</strong>.</p>"
            f"<p>Clients : {', '.join(sim['client_names'])}</p>"
            f"<h3>Données saisies dans AxioLoad</h3><img src=\"{sim['input_screenshot']}\" alt=\"Entrée {sim['case_id']}\">"
            f"<h3>Résultat affiché par AxioLoad</h3><img src=\"{sim['result_screenshot']}\" alt=\"Résultat {sim['case_id']}\">"
        )
    html = """<!doctype html><html lang=\"fr\"><head><meta charset=\"utf-8\"><title>AxioLoad QA multi-simulations</title>
<style>body{font-family:Arial,sans-serif;max-width:1500px;margin:30px auto;padding:0 20px;color:#16242c}table{border-collapse:collapse;width:100%;margin-bottom:32px}th,td{border:1px solid #bbb;padding:8px;text-align:left}img{max-width:100%;border:1px solid #bbb;margin-bottom:24px}h1,h2{margin-top:32px}</style></head><body>"""
    html += "<h1>AXIO-MULTI-SIM-001 — Rapport QA</h1>"
    html += "<p>Cinq simulations distinctes exécutées dans l'interface AxioLoad avec données synthétiques.</p>"
    html += "<table><thead><tr><th>Simulation</th><th>Palettes</th><th>Clients</th><th>Camions</th><th>Placements</th><th>Chevauchements</th><th>Erreurs</th><th>Statut</th></tr></thead><tbody>"
    html += "".join(rows) + "</tbody></table>" + "".join(sections) + "</body></html>"
    (root / "multi-simulation-report.html").write_text(html, encoding="utf-8")


def _write_evidence(payload: dict) -> None:
    path = _evidence_path()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_axioload_multi_sim_001_executes_five_distinct_ui_simulations_with_screenshots(
    multi_sim_app: str,
    tmp_path: Path,
) -> None:
    # Input diversity is part of the oracle: no case may silently become a
    # repeated execution of another case.
    pallet_counts = [sum(client["quantity"] for client in case["clients"]) for case in CASES]
    client_counts = [len(case["clients"]) for case in CASES]
    assert pallet_counts == [8, 15, 24, 36, 50]
    assert client_counts == [1, 2, 3, 4, 5]
    assert len(set(zip(pallet_counts, client_counts))) == len(CASES)

    artifact_root = _artifact_dir(tmp_path)
    screenshots_root = artifact_root / "screenshots"
    simulations: list[dict] = []
    console_errors: list[str] = []
    page_errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1100})
        page.set_default_timeout(20_000)
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.goto(multi_sim_app, wait_until="networkidle")
        page.locator('#workspace-switcher [data-workspace="optimization"]').click()
        page.locator('[data-tab="data"]').click()
        page.locator("#tab-data.active").wait_for(state="visible")

        # Use the same visible fleet controls as a real user. The current UI
        # intentionally hides #vehicle-id/#max-vehicles as legacy sync fields.
        fleet_row = page.locator("#fleet-lines .fleet-line").first
        fleet_row.wait_for(state="visible")
        fleet_row.locator("select").select_option("semi_trailer")
        fleet_quantity = fleet_row.locator('input[type="number"]')
        fleet_quantity.fill("10")
        fleet_quantity.press("Tab")
        page.locator("#calculation-toolbar #budget-seconds").fill("3")
        assert page.locator("#vehicle-id").input_value() == "semi_trailer"
        assert page.locator("#max-vehicles").input_value() == "10"

        for case in CASES:
            page.locator('[data-tab="data"]').click()
            page.locator("#tab-data.active").wait_for(state="visible")
            total_pallets, client_names = _fill_case(page, case)
            expected_sources = {f"QA-{case['id']}-C{index}" for index in range(1, len(client_names) + 1)}

            input_filename = f"{case['id'].lower()}-input.png"
            input_path = screenshots_root / input_filename
            page.screenshot(path=str(input_path), full_page=True)

            with page.expect_response(
                lambda response: response.request.method == "POST" and response.url.endswith("/local/optimize"),
                timeout=45_000,
            ) as response_info:
                page.locator("#optimize").click()
            response = response_info.value
            assert response.status == 200, f"{case['id']}: optimization HTTP {response.status}"
            result = response.json()
            metrics = _collect_result_metrics(result, total_pallets, expected_sources)

            page.locator("#results-content:not(.hidden)").wait_for(timeout=30_000)
            page.locator(".solution-card").first.wait_for(state="visible", timeout=30_000)
            page.locator("#viewer").wait_for(state="visible", timeout=30_000)
            page.locator("#opx4-input-summary").wait_for(state="visible", timeout=30_000)
            summary_text = page.locator("#opx4-input-summary").inner_text()
            for client_name in client_names:
                assert client_name in summary_text, f"{case['id']}: client missing from UI result summary: {client_name}"

            result_filename = f"{case['id'].lower()}-result.png"
            result_path = screenshots_root / result_filename
            page.screenshot(path=str(result_path), full_page=True)

            simulation = {
                "case_id": case["id"],
                "pallet_count": total_pallets,
                "client_count": len(client_names),
                "client_names": list(client_names),
                **metrics,
                "input_screenshot": f"screenshots/{input_filename}",
                "result_screenshot": f"screenshots/{result_filename}",
            }
            simulations.append(simulation)

            if metrics["run_id"]:
                delete_status = page.evaluate(
                    "async runId => (await fetch(`/api/history/${encodeURIComponent(runId)}`, {method:'DELETE'})).status",
                    metrics["run_id"],
                )
                assert delete_status == 204, f"{case['id']}: QA history cleanup failed ({delete_status})"

        browser.close()

    assert not page_errors, page_errors
    assert not console_errors, console_errors
    assert len(simulations) == 5
    assert [sim["pallet_count"] for sim in simulations] == [8, 15, 24, 36, 50]
    assert [sim["client_count"] for sim in simulations] == [1, 2, 3, 4, 5]
    assert all(sim["placement_count"] == sim["pallet_count"] for sim in simulations)
    assert all(sim["geometry_overlap_count"] == 0 for sim in simulations)
    assert all(sim["error_diagnostic_count"] == 0 for sim in simulations)

    _write_html_report(artifact_root, simulations)
    _write_evidence(
        {
            "scenario_id": SCENARIO_ID,
            "execution_layer": "browser_ui+local_api+optimizer_engine",
            "optimizer_status": "five_distinct_simulations_completed",
            "simulation_count": len(simulations),
            "all_cases_distinct": True,
            "total_pallets_tested": sum(sim["pallet_count"] for sim in simulations),
            "total_clients_tested": sum(sim["client_count"] for sim in simulations),
            "screenshot_count": len(simulations) * 2,
            "browser_exercised": True,
            "server_exercised": True,
            "report_file": "multi-simulation-report.html",
            "simulations": simulations,
        }
    )
