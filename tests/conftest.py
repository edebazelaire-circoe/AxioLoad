from __future__ import annotations

import pytest

from pallet_optimizer.domain import AxleSpec, VehicleVersion


@pytest.fixture
def simple_vehicle() -> VehicleVersion:
    return VehicleVersion(
        model_id="test",
        version=1,
        name="Test vehicle",
        interior_length_mm=4000,
        interior_width_mm=2400,
        interior_height_mm=2500,
        linear_meter_width_mm=2400,
        payload_kg=4000,
        door_width_mm=2400,
        door_height_mm=2500,
        axles=(AxleSpec("front", 0, 3000), AxleSpec("rear", 4000, 3000)),
    )


@pytest.fixture
def base_payload() -> dict:
    return {
        "dimension_unit": "mm",
        "weight_unit": "kg",
        "vehicle_policy": {"mode": "forced", "forced_vehicle_id": "semi_trailer", "max_vehicles": 5},
        "seed": 42,
        "budget_seconds": 2,
        "items": [
            {"id": "A", "quantity": 2, "shape": "pallet", "length": 1200, "width": 800,
             "height": 1200, "weight": 500, "destination": "Client A", "delivery_order": 2},
            {"id": "B", "quantity": 2, "shape": "pallet", "length": 1200, "width": 1000,
             "height": 1200, "weight": 600, "destination": "Client B", "delivery_order": 1},
        ],
    }
