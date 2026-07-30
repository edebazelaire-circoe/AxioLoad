from __future__ import annotations

import itertools
from pathlib import Path

from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app
from pallet_optimizer.route_optimization import (
    Point,
    RouteInputError,
    job_cost_matrix,
    optimise,
    physical_points,
    route_cost,
)


ROOT = Path(__file__).resolve().parents[1]


def route_payload(method: str = "hgs") -> dict:
    # Physical point order: depot, A pickup/delivery, B pickup/delivery, C pickup/delivery.
    x_positions = [0, 1, 2, 10, 11, 5, 6]
    matrix = [
        [abs(source - target) * 1_000 for target in x_positions]
        for source in x_positions
    ]
    return {
        "method": method,
        "depot": {"lat": 49.49, "lon": 0.10, "label": "Dépôt"},
        "jobs": [
            {
                "id": "A",
                "client": "Client A",
                "reference": "PAL-A",
                "weight_kg": 500,
                "pickup": {"lat": 49.50, "lon": 0.11, "label": "Enlèvement A"},
                "delivery": {"lat": 49.51, "lon": 0.12, "label": "Livraison A"},
            },
            {
                "id": "B",
                "client": "Client B",
                "reference": "PAL-B",
                "weight_kg": 600,
                "pickup": {"lat": 49.59, "lon": 0.20, "label": "Enlèvement B"},
                "delivery": {"lat": 49.60, "lon": 0.21, "label": "Livraison B"},
            },
            {
                "id": "C",
                "client": "Client C",
                "reference": "PAL-C",
                "weight_kg": 700,
                "pickup": {"lat": 49.54, "lon": 0.15, "label": "Enlèvement C"},
                "delivery": {"lat": 49.55, "lon": 0.16, "label": "Livraison C"},
            },
        ],
        "capacity_kg": 1_000,
        "time_limit_s": 0.25,
        "seed": 11,
        "return_to_depot": True,
        "distance_matrix_m": matrix,
        "duration_matrix_s": [[value / 12.5 for value in row] for row in matrix],
    }


def test_hgs_and_alns_keep_pickup_before_delivery_and_use_same_matrix() -> None:
    outputs = [optimise(route_payload(method)) for method in ("hgs", "alns")]
    for output in outputs:
        assert sorted(output["order"]) == ["A", "B", "C"]
        assert output["provider"] == "matrice fournie"
        assert output["total_distance_km"] > 0
        for job_id in ("A", "B", "C"):
            pickup = next(stop["sequence"] for stop in output["stops"] if stop["job_id"] == job_id and stop["type"] == "pickup")
            delivery = next(stop["sequence"] for stop in output["stops"] if stop["job_id"] == job_id and stop["type"] == "delivery")
            assert pickup < delivery


def test_route_cost_matches_bruteforce_optimum_on_small_case() -> None:
    payload = route_payload("alns")
    result = optimise(payload)
    # Reconstruct the job graph from the supplied physical matrix.
    depot = Point(49.49, 0.10, "Dépôt")
    from pallet_optimizer.route_optimization import parse_problem, MatrixData

    parsed_depot, jobs, _ = parse_problem(payload)
    physical = MatrixData(
        tuple(tuple(float(value) for value in row) for row in payload["distance_matrix_m"]),
        tuple(tuple(float(value) for value in row) for row in payload["duration_matrix_s"]),
        "test",
    )
    matrix = job_cost_matrix(physical, jobs, return_to_depot=True)
    optimum = min(route_cost(order, matrix) for order in itertools.permutations(range(3)))
    id_to_index = {job.id: index for index, job in enumerate(jobs)}
    result_order = [id_to_index[job_id] for job_id in result["order"]]
    assert route_cost(result_order, matrix) == optimum
    assert physical_points(parsed_depot, jobs)[0] == depot


def test_capacity_rejects_mission_heavier_than_vehicle() -> None:
    payload = route_payload()
    payload["capacity_kg"] = 550
    try:
        optimise(payload)
    except RouteInputError as exc:
        assert "B" in str(exc) and "C" in str(exc)
    else:
        raise AssertionError("An overweight mission should be rejected")


def test_route_api_and_compare_are_isolated_from_loading_history(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))
    before = client.get("/api/history").json()
    response = client.post("/api/route/optimize", json=route_payload("hgs"))
    assert response.status_code == 200
    assert response.json()["method_name"] == "HGS / PyVRP"
    compared = client.post("/api/route/compare", json=route_payload("hgs"))
    assert compared.status_code == 200
    assert {item["method"] for item in compared.json()["results"]} == {"hgs", "alns"}
    after = client.get("/api/history").json()
    assert after == before


def test_route_tab_and_assets_are_packaged(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))
    html = client.get("/").text
    assert 'data-tab="route"' in html
    assert 'id="tab-route"' in html
    assert "HGS / PyVRP" in html
    assert "ALNS" in html
    assert (ROOT / "src" / "pallet_optimizer" / "static" / "route.js").exists()
    assert (ROOT / "src" / "pallet_optimizer" / "static" / "route.css").exists()


def test_pickups_can_be_interleaved_before_deliveries_when_capacity_allows() -> None:
    x_positions = [0, 1, 10, 1, 11]
    matrix = [[abs(source - target) * 1_000 for target in x_positions] for source in x_positions]
    base = {
        "depot": {"lat": 0, "lon": 0, "label": "Dépôt"},
        "jobs": [
            {
                "id": "A", "client": "A", "reference": "A", "weight_kg": 500,
                "pickup": {"lat": 0, "lon": 0.1, "label": "Entrepôt"},
                "delivery": {"lat": 0, "lon": 1.0, "label": "Client A"},
            },
            {
                "id": "B", "client": "B", "reference": "B", "weight_kg": 500,
                "pickup": {"lat": 0, "lon": 0.1, "label": "Entrepôt"},
                "delivery": {"lat": 0, "lon": 1.1, "label": "Client B"},
            },
        ],
        "capacity_kg": 1_000,
        "time_limit_s": 0.25,
        "seed": 5,
        "return_to_depot": True,
        "distance_matrix_m": matrix,
    }
    for method in ("hgs", "alns"):
        result = optimise({**base, "method": method})
        stop_types = [stop["type"] for stop in result["stops"]]
        assert stop_types[1:5] == ["pickup", "pickup", "delivery", "delivery"]
        assert result["total_distance_km"] == 22.0
        assert max(stop.get("load_after_kg", 0) for stop in result["stops"]) == 1_000


def test_capacity_can_force_a_delivery_before_the_next_pickup() -> None:
    x_positions = [0, 1, 10, 1, 11]
    matrix = [[abs(source - target) * 1_000 for target in x_positions] for source in x_positions]
    payload = {
        "method": "alns",
        "depot": {"lat": 0, "lon": 0, "label": "Dépôt"},
        "jobs": [
            {"id": "A", "client": "A", "reference": "A", "weight_kg": 500,
             "pickup": {"lat": 0, "lon": 0.1, "label": "P"}, "delivery": {"lat": 0, "lon": 1.0, "label": "A"}},
            {"id": "B", "client": "B", "reference": "B", "weight_kg": 500,
             "pickup": {"lat": 0, "lon": 0.1, "label": "P"}, "delivery": {"lat": 0, "lon": 1.1, "label": "B"}},
        ],
        "capacity_kg": 600,
        "time_limit_s": 0.25,
        "seed": 5,
        "return_to_depot": True,
        "distance_matrix_m": matrix,
    }
    result = optimise(payload)
    assert max(stop.get("load_after_kg", 0) for stop in result["stops"]) <= 600
    first_delivery = next(index for index, stop in enumerate(result["stops"]) if stop["type"] == "delivery")
    second_pickup = [index for index, stop in enumerate(result["stops"]) if stop["type"] == "pickup"][1]
    assert first_delivery < second_pickup


def test_route_result_exposes_client_summary_quantities_weights_and_direct_distances() -> None:
    payload = route_payload("hgs")
    payload["jobs"][0].update({"quantity": 3, "unit_type": "palette"})
    payload["jobs"][1].update({"quantity": 2, "unit_type": "colis"})
    payload["jobs"][2].update({"quantity": 1, "unit_type": "unité"})
    result = optimise(payload)
    summaries = {item["job_id"]: item for item in result["jobs_summary"]}
    assert summaries["A"]["quantity"] == 3
    assert summaries["A"]["unit_type"] == "palette"
    assert summaries["A"]["direct_distance_km"] == 1.0
    assert summaries["B"]["direct_distance_km"] == 1.0
    assert summaries["C"]["direct_distance_km"] == 1.0
    assert result["total_weight_kg"] == 1_800
    assert result["total_handling_units"] == 6


def test_route_map_client_colours_and_recap_are_packaged(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))
    html = client.get("/").text
    assert 'id="route-map-legend"' in html
    assert 'id="route-recap-table"' in html
    assert "Nombre de palettes / colis" in html
    assert "contributeurs OpenStreetMap" in html
    route_js = (ROOT / "src" / "pallet_optimizer" / "static" / "route.js").read_text(encoding="utf-8")
    assert "https://tile.openstreetmap.org/" in route_js
    assert "function clientColor" in route_js
    assert "function renderRecapTable" in route_js
    assert "direct_distance_km" in route_js
