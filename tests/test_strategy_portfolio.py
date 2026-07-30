from __future__ import annotations

from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app
from pallet_optimizer.catalog import default_vehicle_catalog
from pallet_optimizer.normalization import normalize_payload
from pallet_optimizer.packing import STRATEGIES, pack_single_vehicle
from pallet_optimizer.validation import has_errors, validate_geometry


def reported_payload(vehicle_id: str = "rigid_20m3") -> dict:
    return {
        "dimension_unit": "mm", "weight_unit": "kg", "seed": 1,
        "budget_seconds": 5, "requested_solutions": 5,
        "vehicle_policy": {"mode": "forced", "forced_vehicle_id": vehicle_id, "max_vehicles": 1},
        "items": [
            {"id": "PAL-001", "quantity": 1, "shape": "box", "length": 1200, "width": 800,
             "height": 1200, "weight": 500, "destination": "Client A", "delivery_order": 1,
             "rotation_allowed": False},
            {"id": "PAL-002", "quantity": 1, "shape": "cylinder", "length": 1200, "width": 1000,
             "height": 1200, "weight": 600, "destination": "Client B", "delivery_order": 2,
             "rotation_allowed": True},
        ],
    }


def test_each_packing_strategy_runs_independently_and_returns_valid_geometry() -> None:
    problem = normalize_payload(reported_payload())
    vehicle = next(v for v in default_vehicle_catalog() if v.model_id == "rigid_20m3")
    item_map = {item.id: item for item in problem.items}
    successful = []
    for index, strategy in enumerate(STRATEGIES):
        placements, diagnostics = pack_single_vehicle(problem.items, vehicle, strategy, seed=100 + index)
        assert placements is not None, (strategy.name, diagnostics)
        geometry = validate_geometry(vehicle, placements, item_map)
        assert not has_errors(geometry), (strategy.name, geometry)
        assert len(placements) == 2
        successful.append(strategy.name)
    assert successful == [strategy.name for strategy in STRATEGIES]


def test_local_api_aggregates_valid_results_for_reported_case_without_key(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))
    response = client.post("/local/optimize", json=reported_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"completed", "completed_with_time_limit"}
    assert body["solutions"]
    for solution in body["solutions"]:
        for plan in solution["vehicle_plans"]:
            assert len(plan["placements"]) == 2
            assert all(p["x_mm"] + p["envelope_width_mm"] <= 2100 for p in plan["placements"])
            assert all(p["y_mm"] + p["envelope_length_mm"] <= 4200 for p in plan["placements"])


def test_vehicle_edit_without_key_changes_optimization_geometry(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))
    vehicles = client.get("/api/vehicles").json()
    rigid = next(v for v in vehicles if v["model_id"] == "rigid_20m3")
    rigid.update({"interior_width_mm": 1500, "door_width_mm": 1500, "linear_meter_width_mm": 1500})
    saved = client.post("/api/vehicles", json=rigid)
    assert saved.status_code == 200
    body = client.post("/local/optimize", json=reported_payload()).json()
    assert body["solutions"]
    for p in body["solutions"][0]["vehicle_plans"][0]["placements"]:
        assert p["x_mm"] + p["envelope_width_mm"] <= 1500
