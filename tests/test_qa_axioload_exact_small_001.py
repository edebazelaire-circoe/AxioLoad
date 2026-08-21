from math import ceil

from pallet_optimizer.domain import CargoItem, OptimizationProblem, Shape, VehiclePolicy, VehicleVersion
from pallet_optimizer.engine import OptimizationEngine


SCENARIO_ID = "AXIO-OPT-SMALL-001"


def _vehicle() -> VehicleVersion:
    return VehicleVersion(
        model_id="qa_exact_small",
        version=1,
        name="QA exact small vehicle",
        interior_length_mm=2400,
        interior_width_mm=2400,
        interior_height_mm=2500,
        linear_meter_width_mm=2400,
        payload_kg=10000,
        door_width_mm=2400,
        door_height_mm=2500,
        axles=(),
    )


def _item(index: int) -> CargoItem:
    return CargoItem(
        id=f"QA-PAL-{index}",
        source_id=f"QA-PAL-{index}",
        input_index=index,
        shape=Shape.PALLET,
        length_mm=1200,
        width_mm=1200,
        height_mm=1000,
        weight_kg=500,
        destination="QA Client",
        delivery_order=1,
        rotation_allowed=False,
    )


def test_axioload_opt_small_001_matches_independent_exact_vehicle_count_oracle():
    vehicle = _vehicle()
    items = tuple(_item(index) for index in range(5))

    # Independent lower bound: a 2400 x 2400 floor can contain at most four
    # non-rotated 1200 x 1200 pallets. Five pallets therefore require >= 2 vehicles.
    floor_area = vehicle.interior_length_mm * vehicle.interior_width_mm
    item_area = items[0].length_mm * items[0].width_mm
    max_items_per_vehicle_by_area = floor_area // item_area
    exact_lower_bound = ceil(len(items) / max_items_per_vehicle_by_area)
    assert exact_lower_bound == 2

    problem = OptimizationProblem(
        items=items,
        vehicles=(vehicle,),
        vehicle_policy=VehiclePolicy("forced", vehicle.model_id, 2),
        seed=7,
        budget_seconds=3,
        requested_solutions=5,
    )
    result = OptimizationEngine().optimize(problem)

    assert result.status.value in {"completed", "completed_with_time_limit"}, f"{SCENARIO_ID}: {result.status.value}"
    assert result.solutions, f"{SCENARIO_ID}: no feasible solution returned"

    best = result.solutions[0]
    assert best.vehicle_count == exact_lower_bound
    assert all(solution.vehicle_count == exact_lower_bound for solution in result.solutions)

    placements = [placement for plan in best.vehicle_plans for placement in plan.placements]
    assert len(placements) == len(items)
    assert len({placement.item_id for placement in placements}) == len(items)

    for plan in best.vehicle_plans:
        total_weight = sum(placement.weight_kg for placement in plan.placements)
        assert total_weight <= vehicle.payload_kg
        for placement in plan.placements:
            assert placement.x_mm >= 0
            assert placement.y_mm >= 0
            assert placement.z_mm >= 0
            assert placement.x_mm + placement.envelope_width_mm <= vehicle.interior_width_mm
            assert placement.y_mm + placement.envelope_length_mm <= vehicle.interior_length_mm
            assert placement.z_mm + placement.actual_height_mm <= vehicle.interior_height_mm

    # Constructive upper bound from the optimizer is also 2, so lower == upper.
    assert best.vehicle_count == 2
