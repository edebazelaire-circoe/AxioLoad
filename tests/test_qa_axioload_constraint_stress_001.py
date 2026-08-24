from __future__ import annotations

from pallet_optimizer.domain import (
    AxleSpec,
    CargoItem,
    OptimizationProblem,
    Placement,
    Shape,
    VehiclePolicy,
    VehicleVersion,
)
from pallet_optimizer.engine import OptimizationEngine
from pallet_optimizer.validation import (
    calculate_weight,
    validate_compatibility,
    validate_delivery_access,
    validate_geometry,
)


SCENARIO_ID = "AXIO-CONSTRAINT-STRESS-001"


def _vehicle(*, axles=(), payload_kg: float = 2000) -> VehicleVersion:
    return VehicleVersion(
        model_id="qa_limit",
        version=1,
        name="QA Limit Vehicle",
        interior_length_mm=2000,
        interior_width_mm=1000,
        interior_height_mm=2000,
        linear_meter_width_mm=1000,
        payload_kg=payload_kg,
        door_width_mm=1000,
        door_height_mm=2000,
        axles=tuple(axles),
    )


def _item(
    item_id: str,
    *,
    length: int = 800,
    width: int = 800,
    height: int = 1000,
    weight: float = 100,
    delivery_order: int = 1,
    compatibility_tags=(),
    incompatible_tags=(),
) -> CargoItem:
    return CargoItem(
        id=item_id,
        source_id=item_id,
        input_index=0 if item_id == "A" else 1,
        shape=Shape.PALLET,
        length_mm=length,
        width_mm=width,
        height_mm=height,
        weight_kg=weight,
        destination="QA",
        delivery_order=delivery_order,
        rotation_allowed=False,
        compatibility_tags=tuple(compatibility_tags),
        incompatible_tags=tuple(incompatible_tags),
    )


def _placement(
    item_id: str,
    *,
    y: int = 0,
    length: int = 800,
    width: int = 800,
    height: int = 1000,
    weight: float = 100,
    delivery_order: int = 1,
) -> Placement:
    return Placement(
        item_id=item_id,
        source_id=item_id,
        destination="QA",
        delivery_order=delivery_order,
        x_mm=0,
        y_mm=y,
        z_mm=0,
        orientation_deg=0,
        actual_length_mm=length,
        actual_width_mm=width,
        actual_height_mm=height,
        envelope_length_mm=length,
        envelope_width_mm=width,
        weight_kg=weight,
    )


def _codes(diagnostics) -> set[str]:
    return {diagnostic.code for diagnostic in diagnostics}


def test_axioload_constraint_stress_001_enforces_exact_boundaries_payload_axles_lifo_and_incompatibility():
    vehicle = _vehicle()

    # Dimension boundary: an item exactly equal to the vehicle envelope is feasible,
    # while +1 mm beyond the interior length is rejected by the actual optimizer.
    exact = _item("A", length=2000, width=1000, height=2000, weight=500)
    exact_result = OptimizationEngine().optimize(
        OptimizationProblem(
            (exact,),
            (vehicle,),
            VehiclePolicy("forced", "qa_limit", 1),
            budget_seconds=1,
            requested_solutions=1,
        )
    )
    assert exact_result.solutions, f"{SCENARIO_ID}: exact-fit item should remain feasible"

    oversized = _item("A", length=2001, width=1000, height=2000, weight=500)
    oversized_result = OptimizationEngine().optimize(
        OptimizationProblem(
            (oversized,),
            (vehicle,),
            VehiclePolicy("forced", "qa_limit", 1),
            budget_seconds=1,
            requested_solutions=1,
        )
    )
    assert not oversized_result.solutions
    assert "ITEM_DOES_NOT_FIT" in _codes(oversized_result.diagnostics)

    exact_placement = _placement("A", length=2000, width=1000, height=2000, weight=500)
    assert not validate_geometry(vehicle, (exact_placement,), {"A": exact})

    too_high = _item("A", length=800, width=800, height=2001, weight=100)
    high_placement = _placement("A", length=800, width=800, height=2001, weight=100)
    height_codes = _codes(validate_geometry(vehicle, (high_placement,), {"A": too_high}))
    assert {"HEIGHT_EXCEEDED", "OPENING_TOO_SMALL"}.issubset(height_codes)

    # Payload boundary: exactly the limit is accepted; +1 kg is explicitly diagnosed.
    at_payload = _placement("A", weight=2000)
    _, at_payload_diagnostics, _ = calculate_weight(vehicle, (at_payload,))
    assert "PAYLOAD_EXCEEDED" not in _codes(at_payload_diagnostics)
    above_payload = _placement("A", weight=2001)
    _, above_payload_diagnostics, _ = calculate_weight(vehicle, (above_payload,))
    assert "PAYLOAD_EXCEEDED" in _codes(above_payload_diagnostics)

    # Axle limit: total payload is legal, but the rear support is overloaded by position.
    axle_vehicle = _vehicle(
        payload_kg=1200,
        axles=(AxleSpec("front", 0, 600), AxleSpec("rear", 2000, 600)),
    )
    rear_heavy = _placement("A", y=1400, length=400, width=800, weight=1000)
    weight_metrics, axle_diagnostics, _ = calculate_weight(axle_vehicle, (rear_heavy,))
    assert weight_metrics.total_weight_kg == 1000
    assert "PAYLOAD_EXCEEDED" not in _codes(axle_diagnostics)
    assert "AXLE_OVERLOAD" in _codes(axle_diagnostics)

    # LIFO: larger delivery_order means unloaded earlier and cannot sit deeper in the same lane.
    earlier_deep = _placement("A", y=1000, length=700, width=800, delivery_order=2)
    later_near_door = _placement("B", y=0, length=700, width=800, delivery_order=1)
    assert "LIFO_BLOCKED" in _codes(validate_delivery_access((earlier_deep, later_near_door)))
    earlier_near_door = _placement("A", y=0, length=700, width=800, delivery_order=2)
    later_deep = _placement("B", y=1000, length=700, width=800, delivery_order=1)
    assert "LIFO_BLOCKED" not in _codes(validate_delivery_access((earlier_near_door, later_deep)))

    # Incompatibility: food explicitly incompatible with chemical cannot share one vehicle.
    food = _item("A", compatibility_tags=("food",), incompatible_tags=("chemical",))
    chemical = _item("B", compatibility_tags=("chemical",))
    food_p = _placement("A", y=0)
    chemical_p = _placement("B", y=900)
    same_vehicle = validate_compatibility(((food_p, chemical_p),), {"A": food, "B": chemical})
    assert "INCOMPATIBLE_CARGO" in _codes(same_vehicle)
    separate_vehicles = validate_compatibility(((food_p,), (chemical_p,)), {"A": food, "B": chemical})
    assert "INCOMPATIBLE_CARGO" not in _codes(separate_vehicles)
