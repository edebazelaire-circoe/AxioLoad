from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pallet_optimizer.route_optimization import MatrixData, Point
from pallet_optimizer.total_route_sequence import (
    best_lifo_wave_plan,
    build_lifo_stops,
    clear_sequence_cache,
)


@dataclass(frozen=True)
class FakeClient:
    id: str
    client: str
    pickup: Point
    delivery: Point
    quantity: int = 1
    unit_type: str = "palette"
    weight_kg: float = 100.0


@dataclass
class FakeProblem:
    clients: tuple[FakeClient, ...]
    depot: Point
    distance_matrix: MatrixData
    return_to_depot: bool = True

    def pickup_index(self, client_index: int) -> int:
        return 1 + 2 * client_index

    def delivery_index(self, client_index: int) -> int:
        return 2 + 2 * client_index


def line_matrix(*positions: float) -> MatrixData:
    values = tuple(
        tuple(abs(left - right) for right in positions)
        for left in positions
    )
    return MatrixData(values, values, "test")


def test_same_loading_point_is_one_real_stop_before_deliveries() -> None:
    clear_sequence_cache()
    warehouse = Point(49.468586, 0.271508, "Entrepôt commun")
    problem = FakeProblem(
        clients=(
            FakeClient("A", "Tang frère", warehouse, Point(48.755636, 2.359840, "Tang frère")),
            FakeClient("B", "Métro", warehouse, Point(48.744997, 2.363359, "Métro")),
        ),
        depot=Point(49.493660, 0.114000, "Départ"),
        # depot, pickup A, delivery A, pickup B, delivery B
        distance_matrix=line_matrix(0, 0, 10, 0, 20),
    )

    plan = best_lifo_wave_plan(problem, (0, 1))
    assert plan.waves == ((0, 1),)
    assert plan.physical_indices == (0, 3, 1, 2, 4, 0)

    stops = build_lifo_stops(problem, (0, 1))
    assert [stop["type"] for stop in stops] == ["start", "pickup", "delivery", "delivery", "return"]
    assert stops[1]["label"] == "Entrepôt commun"
    assert set(stops[1]["clients"]) == {"Tang frère", "Métro"}
    assert len(stops[1]["operations"]) == 2


def test_route_can_deliver_then_reload_when_it_reduces_distance() -> None:
    clear_sequence_cache()
    problem = FakeProblem(
        clients=(
            FakeClient("A", "Client A", Point(0, 0, "Chargement A"), Point(0, 1, "Livraison A")),
            FakeClient("B", "Client B", Point(0, 1, "Chargement B"), Point(0, 2, "Livraison B")),
        ),
        depot=Point(0, 0, "Départ"),
        # One wave costs 50. Two waves cost 40 because pickup B is at delivery A.
        distance_matrix=line_matrix(0, 0, 10, 10, 20),
    )

    plan = best_lifo_wave_plan(problem, (0, 1))
    assert plan.waves == ((0,), (1,))
    assert plan.physical_indices == (0, 1, 2, 3, 4, 0)

    stops = build_lifo_stops(problem, (0, 1))
    assert [stop["type"] for stop in stops] == [
        "start",
        "pickup",
        "delivery",
        "pickup",
        "delivery",
        "return",
    ]
    assert [stop["label"] for stop in stops[1:-1]] == [
        "Chargement A",
        "Livraison A",
        "Chargement B",
        "Livraison B",
    ]


def test_total_ui_shows_one_colored_operational_path() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "pallet_optimizer"
    javascript = (root / "static" / "total.js").read_text(encoding="utf-8")
    stylesheet = (root / "static" / "total.css").read_text(encoding="utf-8")
    preprocessing = (root / "total_preprocessing.py").read_text(encoding="utf-8")

    assert "function renderRoutePath(route)" in javascript
    assert "total-operation-badge" in javascript
    assert "Enlèvements :" not in javascript
    assert "Livraisons :" not in javascript
    assert ".total-path-step.pickup" in stylesheet
    assert ".total-path-step.delivery" in stylesheet
    assert "install_wave_routing()" in preprocessing


def test_total_api_uses_real_shared_pickup_stop(tmp_path) -> None:
    from fastapi.testclient import TestClient

    from pallet_optimizer.api import create_app

    matrix = [list(row) for row in line_matrix(0, 0, 10, 0, 20).distances_m]
    payload = {
        "loading": {
            "vehicle_policy": {
                "mode": "forced",
                "forced_vehicle_id": "semi_trailer",
                "max_vehicles": 2,
            },
            "budget_seconds": 2,
            "items": [
                {
                    "id": "PAL-A",
                    "quantity": 1,
                    "shape": "pallet",
                    "length": 1200,
                    "width": 800,
                    "height": 1000,
                    "weight": 100,
                    "destination": "Tang frère",
                    "delivery_order": 1,
                },
                {
                    "id": "PAL-B",
                    "quantity": 1,
                    "shape": "pallet",
                    "length": 1200,
                    "width": 800,
                    "height": 1000,
                    "weight": 100,
                    "destination": "Métro",
                    "delivery_order": 2,
                },
            ],
        },
        "route": {
            "depot": {"lat": 49.493660, "lon": 0.114000, "label": "Départ"},
            "return_to_depot": True,
            "_fetch_geometry": False,
            "distance_matrix_m": matrix,
            "duration_matrix_s": matrix,
            "jobs": [
                {
                    "id": "JOB-A",
                    "client": "Tang frère",
                    "item_ids": ["PAL-A"],
                    "quantity": 1,
                    "unit_type": "palette",
                    "weight_kg": 100,
                    "pickup": {"lat": 49.468586, "lon": 0.271508, "label": "Entrepôt commun"},
                    "delivery": {"lat": 48.755636, "lon": 2.359840, "label": "Tang frère livraison"},
                },
                {
                    "id": "JOB-B",
                    "client": "Métro",
                    "item_ids": ["PAL-B"],
                    "quantity": 1,
                    "unit_type": "palette",
                    "weight_kg": 100,
                    "pickup": {"lat": 49.468586, "lon": 0.271508, "label": "Entrepôt commun"},
                    "delivery": {"lat": 48.744997, "lon": 2.363359, "label": "Métro livraison"},
                },
            ],
        },
        "time_limit_s": 2,
        "seed": 1,
    }

    response = TestClient(create_app(tmp_path)).post("/api/total/optimize", json=payload)
    assert response.status_code == 200, response.text
    for solution in response.json()["solutions"]:
        assert solution["vehicle_count"] == 1
        stops = solution["routes"][0]["stops"]
        pickup_stops = [stop for stop in stops if stop["type"] == "pickup"]
        assert len(pickup_stops) == 1
        assert pickup_stops[0]["label"] == "Entrepôt commun"
        assert {operation["client"] for operation in pickup_stops[0]["operations"]} == {"Tang frère", "Métro"}
