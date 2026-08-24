import json
import os
from itertools import combinations
from math import ceil
from pathlib import Path

from pallet_optimizer.domain import CargoItem, OptimizationProblem, Shape, VehiclePolicy, VehicleVersion
from pallet_optimizer.engine import OptimizationEngine


SCENARIO_ID = "AXIO-OPT-SMALL-001"
PALLET_SIDE_MM = 1200
EXACT_VEHICLE_COUNT = 2
EXACT_TOTAL_OCCUPIED_LENGTH_M = 3.6


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
        length_mm=PALLET_SIDE_MM,
        width_mm=PALLET_SIDE_MM,
        height_mm=1000,
        weight_kg=500,
        destination="QA Client",
        delivery_order=1,
        rotation_allowed=False,
    )


def _rectangles_overlap(left, right) -> bool:
    return not (
        left.x_mm + left.envelope_width_mm <= right.x_mm
        or right.x_mm + right.envelope_width_mm <= left.x_mm
        or left.y_mm + left.envelope_length_mm <= right.y_mm
        or right.y_mm + right.envelope_length_mm <= left.y_mm
    )


def _write_evidence(payload: dict[str, object]) -> None:
    evidence_path = os.environ.get("QA_EVIDENCE_PATH", "").strip()
    if not evidence_path:
        return
    path = Path(evidence_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_axioload_opt_small_001_matches_independent_exact_vehicle_count_oracle():
    vehicle = _vehicle()
    items = tuple(_item(index) for index in range(5))

    # Independent vehicle-count oracle. A 2400 x 2400 floor can contain at most
    # four non-rotated 1200 x 1200 pallets. Five pallets therefore require at
    # least two vehicles, and a constructive 4 + 1 split proves two feasible.
    floor_area = vehicle.interior_length_mm * vehicle.interior_width_mm
    item_area = items[0].length_mm * items[0].width_mm
    max_items_per_vehicle_by_area = floor_area // item_area
    exact_lower_bound = ceil(len(items) / max_items_per_vehicle_by_area)
    assert exact_lower_bound == EXACT_VEHICLE_COUNT

    # Independent occupied-length oracle. In one 1200-mm longitudinal row, a
    # 2400-mm-wide vehicle can hold at most two pallets. With five pallets and
    # exactly two non-empty vehicles, one vehicle therefore needs two rows
    # (2400 mm) while the other needs at least one row (1200 mm): 3.6 m total.
    rows_required = ceil(len(items) / 2)
    assert rows_required == 3
    exact_occupied_length_m = rows_required * PALLET_SIDE_MM / 1000.0
    assert exact_occupied_length_m == EXACT_TOTAL_OCCUPIED_LENGTH_M

    # The crafted fixture intentionally has no axle model, no incompatibility
    # tags and one common delivery stop/order. Therefore axle, incompatibility
    # and LIFO violation counts have an independently known value of zero.
    assert vehicle.axles == ()
    assert all(not item.compatibility_tags and not item.incompatible_tags for item in items)
    assert len({(item.destination, item.delivery_order) for item in items}) == 1

    problem = OptimizationProblem(
        items=items,
        vehicles=(vehicle,),
        vehicle_policy=VehiclePolicy("forced", vehicle.model_id, EXACT_VEHICLE_COUNT),
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
    assert abs(best.occupied_length_m - exact_occupied_length_m) < 1e-9

    placements = [placement for plan in best.vehicle_plans for placement in plan.placements]
    assert len(placements) == len(items)
    assert len({placement.item_id for placement in placements}) == len(items)
    assert {placement.item_id for placement in placements} == {item.id for item in items}

    overlap_count = 0
    for plan in best.vehicle_plans:
        total_weight = sum(placement.weight_kg for placement in plan.placements)
        assert total_weight <= vehicle.payload_kg
        assert plan.weight.axle_loads_kg == ()

        for placement in plan.placements:
            assert placement.x_mm >= 0
            assert placement.y_mm >= 0
            assert placement.z_mm >= 0
            assert placement.x_mm + placement.envelope_width_mm <= vehicle.interior_width_mm
            assert placement.y_mm + placement.envelope_length_mm <= vehicle.interior_length_mm
            assert placement.z_mm + placement.actual_height_mm <= vehicle.interior_height_mm

        overlaps = [
            (left.item_id, right.item_id)
            for left, right in combinations(plan.placements, 2)
            if _rectangles_overlap(left, right)
        ]
        overlap_count += len(overlaps)
        assert overlaps == [], f"{SCENARIO_ID}: geometry overlaps: {overlaps}"

    # No error diagnostic is allowed to hide a business-constraint violation in
    # an otherwise returned solution.
    error_codes = {
        diagnostic.code
        for diagnostic in (*result.diagnostics, *best.diagnostics)
        if getattr(diagnostic.severity, "value", diagnostic.severity) == "error"
    }
    assert error_codes == set(), f"{SCENARIO_ID}: unexpected error diagnostics: {sorted(error_codes)}"

    _write_evidence(
        {
            "scenario_id": SCENARIO_ID,
            "execution_layer": "optimizer_engine",
            "optimizer_status": result.status.value,
            "vehicle_count": best.vehicle_count,
            "expected_vehicle_count": EXACT_VEHICLE_COUNT,
            "occupied_length_m": best.occupied_length_m,
            "expected_occupied_length_m": EXACT_TOTAL_OCCUPIED_LENGTH_M,
            "placement_count": len(placements),
            "unique_placement_count": len({placement.item_id for placement in placements}),
            "unplaced_required_item_count": 0,
            "geometry_overlap_count": overlap_count,
            "dimension_violation_count": 0,
            "weight_violation_count": 0,
            "axle_violation_count": 0,
            "lifo_violation_count": 0,
            "incompatibility_violation_count": 0,
            "error_diagnostic_count": len(error_codes),
            "browser_exercised": False,
            "server_exercised": False,
        }
    )
