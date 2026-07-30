from __future__ import annotations

import pytest

from pallet_optimizer.catalog import default_vehicle_catalog, find_vehicle
from pallet_optimizer.domain import VehicleVersion
from pallet_optimizer.total_optimization import TotalOptimizationError
from pallet_optimizer.total_preprocessing import optimise_total_prepared


def _matrix(size: int) -> list[list[float]]:
    return [
        [0.0 if left == right else float(abs(left - right) * 1000 + 250) for right in range(size)]
        for left in range(size)
    ]


def _point(lat: float, lon: float, label: str) -> dict:
    return {"lat": lat, "lon": lon, "label": label}


def test_33_euro_pallets_for_one_client_fit_one_standard_semi_trailer():
    vehicle = find_vehicle("semi_trailer", default_vehicle_catalog())
    payload = {
        "loading": {
            "dimension_unit": "mm",
            "weight_unit": "kg",
            "seed": 3,
            "budget_seconds": 2,
            "vehicle_policy": {
                "mode": "forced",
                "forced_vehicle_id": "semi_trailer",
                "max_vehicles": 6,
            },
            "items": [{
                "id": "PAL-001",
                "quantity": 33,
                "shape": "pallet",
                "length": 1200,
                "width": 800,
                "height": 1400,
                "weight": 500,
                "destination": "Client A",
                "delivery_order": 1,
                "rotation_allowed": True,
            }],
        },
        "route": {
            "depot": _point(49.49366, 0.114, "Dépôt"),
            "jobs": [{
                "id": "JOB-A",
                "client": "Client A",
                "item_ids": ["PAL-001"],
                "quantity": 33,
                "unit_type": "palettes",
                "weight_kg": 16500,
                "pickup": _point(49.49366, 0.114, "Dépôt"),
                "delivery": _point(49.51, 0.15, "Client A"),
            }],
            "return_to_depot": True,
            "distance_matrix_m": _matrix(3),
            "duration_matrix_s": _matrix(3),
            "_fetch_geometry": False,
        },
        "time_limit_s": 2,
    }

    result = optimise_total_prepared(payload, (vehicle,))

    assert "split_clients" not in result
    assert len(result["solutions"]) == 2
    for solution in result["solutions"]:
        assert solution["vehicle_count"] == 1
        assert solution["total_handling_units"] == 33
        placements = solution["routes"][0]["loading_plan"]["placements"]
        assert len(placements) == 33


def _small_vehicle() -> VehicleVersion:
    return VehicleVersion(
        model_id="small_test",
        version=1,
        name="Petit véhicule test",
        interior_length_mm=2400,
        interior_width_mm=1600,
        interior_height_mm=2500,
        linear_meter_width_mm=1600,
        payload_kg=10000,
        door_width_mm=1600,
        door_height_mm=2500,
        axles=(),
    )


def _split_delivery_payload(max_vehicles: int) -> dict:
    distances = _matrix(5)
    return {
        "loading": {
            "dimension_unit": "mm",
            "weight_unit": "kg",
            "seed": 7,
            "budget_seconds": 4,
            "vehicle_policy": {
                "mode": "forced",
                "forced_vehicle_id": "small_test",
                "max_vehicles": max_vehicles,
            },
            "items": [
                {
                    "id": "A-PAL",
                    "quantity": 5,
                    "shape": "pallet",
                    "length": 1200,
                    "width": 800,
                    "height": 1000,
                    "weight": 300,
                    "destination": "Client A",
                    "rotation_allowed": True,
                },
                {
                    "id": "B-PAL",
                    "quantity": 3,
                    "shape": "pallet",
                    "length": 1200,
                    "width": 800,
                    "height": 1000,
                    "weight": 300,
                    "destination": "Client B",
                    "rotation_allowed": True,
                },
            ],
        },
        "route": {
            "depot": _point(49.49, 0.10, "Dépôt"),
            "jobs": [
                {
                    "id": "JOB-A",
                    "client": "Client A",
                    "item_ids": ["A-PAL"],
                    "quantity": 5,
                    "unit_type": "palettes",
                    "weight_kg": 1500,
                    "pickup": _point(49.49, 0.10, "Dépôt"),
                    "delivery": _point(49.50, 0.11, "Client A"),
                },
                {
                    "id": "JOB-B",
                    "client": "Client B",
                    "item_ids": ["B-PAL"],
                    "quantity": 3,
                    "unit_type": "palettes",
                    "weight_kg": 900,
                    "pickup": _point(49.49, 0.10, "Dépôt"),
                    "delivery": _point(49.505, 0.115, "Client B"),
                },
            ],
            "return_to_depot": True,
            "distance_matrix_m": distances,
            "duration_matrix_s": [[value / 13.8889 for value in row] for row in distances],
            "_fetch_geometry": False,
        },
        "time_limit_s": 4,
    }


def test_oversized_client_is_split_into_flexible_lots_then_recombined_by_both_methods():
    result = optimise_total_prepared(_split_delivery_payload(2), (_small_vehicle(),))

    assert result["split_clients"]
    assert result["split_clients"][0]["client"] == "Client A"
    assert result["split_clients"][0]["lot_count"] >= 2
    assert {solution["method"] for solution in result["solutions"]} == {
        "coupled_alns_3d_oracle",
        "bilevel_genetic_3l_cvrp",
    }
    for solution in result["solutions"]:
        assert solution["vehicle_count"] == 2
        assert solution["total_handling_units"] == 8
        placements = [
            placement
            for route in solution["routes"]
            for placement in route["loading_plan"]["placements"]
        ]
        assert len(placements) == 8


def test_global_capacity_shortage_is_reported_before_route_search():
    with pytest.raises(TotalOptimizationError, match="nécessite au minimum 2 véhicule"):
        optimise_total_prepared(_split_delivery_payload(1), (_small_vehicle(),))
