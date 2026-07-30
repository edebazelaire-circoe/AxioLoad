from __future__ import annotations

import math
from pathlib import Path

from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app


def _matrix(points: list[tuple[float, float]]) -> list[list[float]]:
    return [
        [0.0 if i == j else round(math.hypot(a[0] - b[0], a[1] - b[1]) * 100_000) for j, b in enumerate(points)]
        for i, a in enumerate(points)
    ]


def _payload() -> dict:
    points = [
        (49.49, 0.10), (49.50, 0.11), (49.55, 0.20),
        (49.48, 0.09), (49.65, 0.30), (49.47, 0.08), (49.70, 0.40),
    ]
    distances = _matrix(points)
    return {
        "loading": {
            "dimension_unit": "mm", "weight_unit": "kg", "seed": 2, "budget_seconds": 2,
            "vehicle_policy": {"mode": "forced", "forced_vehicle_id": "rigid_20m3", "max_vehicles": 3},
            "items": [
                {"id": "ROT", "quantity": 1, "shape": "box", "length": 1800, "width": 2200,
                 "height": 800, "weight": 500, "destination": "A", "delivery_order": 1,
                 "rotation_allowed": True},
                {"id": "PB", "quantity": 2, "shape": "pallet", "length": 1200, "width": 800,
                 "height": 1000, "weight": 300, "destination": "B", "delivery_order": 2,
                 "rotation_allowed": True},
                {"id": "BC", "quantity": 1, "shape": "box", "length": 1000, "width": 900,
                 "height": 700, "weight": 150, "destination": "C", "delivery_order": 3,
                 "rotation_allowed": True},
            ],
        },
        "route": {
            "depot": {"lat": points[0][0], "lon": points[0][1], "label": "Dépôt"},
            "jobs": [
                {"id": "JA", "client": "A", "item_ids": ["ROT"], "quantity": 1,
                 "unit_type": "colis", "weight_kg": 500,
                 "pickup": {"lat": points[1][0], "lon": points[1][1], "label": "PA"},
                 "delivery": {"lat": points[2][0], "lon": points[2][1], "label": "DA"}},
                {"id": "JB", "client": "B", "item_ids": ["PB"], "quantity": 2,
                 "unit_type": "palettes", "weight_kg": 600,
                 "pickup": {"lat": points[3][0], "lon": points[3][1], "label": "PB"},
                 "delivery": {"lat": points[4][0], "lon": points[4][1], "label": "DB"}},
                {"id": "JC", "client": "C", "item_ids": ["BC"], "quantity": 1,
                 "unit_type": "colis", "weight_kg": 150,
                 "pickup": {"lat": points[5][0], "lon": points[5][1], "label": "PC"},
                 "delivery": {"lat": points[6][0], "lon": points[6][1], "label": "DC"}},
            ],
            "return_to_depot": True,
            "distance_matrix_m": distances,
            "duration_matrix_s": [[value / 13.8889 for value in row] for row in distances],
            "_fetch_geometry": False,
        },
    }


def test_total_endpoint_compares_two_integrated_methods_and_preserves_rotation(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.post("/api/total/optimize", json=_payload())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert {solution["method"] for solution in body["solutions"]} == {
        "coupled_alns_3d_oracle", "bilevel_genetic_3l_cvrp",
    }
    assert client.get("/api/history").json() == []
    for solution in body["solutions"]:
        assert 1 <= solution["vehicle_count"] <= 3
        assert solution["total_distance_km"] > 0
        assert solution["total_linear_meters"] > 0
        clients = [client_data["client"] for route in solution["routes"] for client_data in route["clients"]]
        assert sorted(clients) == ["A", "B", "C"]
        placements = [placement for route in solution["routes"] for placement in route["loading_plan"]["placements"]]
        assert next(placement for placement in placements if placement["item_id"] == "ROT")["orientation_deg"] == 90


def test_total_mode_is_isolated_in_ui_and_classic_optimization_still_works(tmp_path):
    client = TestClient(create_app(tmp_path))
    html = client.get("/").text
    assert 'id="total-optimization-enabled"' in html
    assert 'id="tab-total"' in html
    assert '/static/total.js' in html
    assert '/static/total.css' in html

    classic = client.post("/local/optimize", json={
        "vehicle_policy": {"mode": "forced", "forced_vehicle_id": "semi_trailer"},
        "budget_seconds": 1,
        "items": [{"id": "P1", "quantity": 1, "shape": "pallet", "length": 1200,
                   "width": 800, "height": 1000, "weight": 200, "destination": "A",
                   "delivery_order": 1}],
    })
    assert classic.status_code == 200
    assert classic.json()["solutions"]

    root = Path(__file__).resolve().parents[1]
    javascript = (root / "src" / "pallet_optimizer" / "static" / "total.js").read_text(encoding="utf-8")
    assert "AxioTotalOptimization" in javascript
    assert "/api/total/optimize" in javascript
