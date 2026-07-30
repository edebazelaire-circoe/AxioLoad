from __future__ import annotations

import time

from pallet_optimizer.catalog import default_vehicle_catalog
from pallet_optimizer.domain import CargoItem, OptimizationProblem, Shape, VehiclePolicy, VehicleVersion
from pallet_optimizer.engine import OptimizationEngine
from pallet_optimizer.optimization_methods import METHODS, pack_with_method
from pallet_optimizer.validation import has_errors, validate_delivery_access, validate_geometry


def item(
    item_id: str,
    index: int,
    *,
    length: int = 1200,
    width: int = 800,
    order: int = 1,
    rotation: bool = True,
) -> CargoItem:
    return CargoItem(
        item_id,
        item_id,
        index,
        Shape.PALLET,
        length,
        width,
        1100,
        250,
        "Client",
        order,
        rotation_allowed=rotation,
    )


def test_five_methods_run_independently_and_respect_vehicle_geometry() -> None:
    vehicle = default_vehicle_catalog()[0]
    items = (
        item("A1", 0, order=2),
        item("A2", 1, order=2),
        item("B1", 2, length=1000, width=1000, order=1),
        item("B2", 3, length=1000, width=1000, order=1),
    )
    item_map = {cargo.id: cargo for cargo in items}
    successful = set()
    for index, method in enumerate(METHODS):
        placements, diagnostics = pack_with_method(
            method,
            items,
            vehicle,
            seed=100 + index,
            deadline=time.perf_counter() + 2.0,
        )
        assert placements is not None, (method.code, diagnostics)
        assert not has_errors(validate_geometry(vehicle, placements, item_map))
        assert not has_errors(validate_delivery_access(placements))
        assert all(p.x_mm + p.envelope_width_mm <= vehicle.interior_width_mm for p in placements)
        assert all(p.y_mm + p.envelope_length_mm <= vehicle.interior_length_mm for p in placements)
        successful.add(method.code)
    assert successful == {method.code for method in METHODS}


def test_rotation_input_is_used_by_each_method() -> None:
    vehicle = VehicleVersion(
        model_id="rotation_test",
        version=1,
        name="Rotation test",
        interior_length_mm=1300,
        interior_width_mm=900,
        interior_height_mm=2200,
        linear_meter_width_mm=900,
        payload_kg=3000,
        door_width_mm=900,
        door_height_mm=2200,
        axles=(),
    )
    rotatable = (item("R", 0, length=800, width=1200, rotation=True),)
    locked = (item("L", 0, length=800, width=1200, rotation=False),)
    for index, method in enumerate(METHODS):
        placements, _ = pack_with_method(
            method,
            rotatable,
            vehicle,
            seed=200 + index,
            deadline=time.perf_counter() + 1.5,
        )
        assert placements is not None, method.code
        assert placements[0].orientation_deg == 90
        locked_placements, _ = pack_with_method(
            method,
            locked,
            vehicle,
            seed=300 + index,
            deadline=time.perf_counter() + 0.5,
        )
        assert locked_placements is None, method.code


def test_engine_returns_one_explained_solution_per_method() -> None:
    vehicle = default_vehicle_catalog()[0]
    items = tuple(item(f"P{index}", index, order=2 if index < 3 else 1) for index in range(6))
    result = OptimizationEngine().optimize(
        OptimizationProblem(
            items,
            (vehicle,),
            VehiclePolicy("forced", "semi_trailer", 1),
            seed=7,
            budget_seconds=5,
            requested_solutions=5,
        )
    )
    assert len(result.solutions) == 5
    assert {solution.method_code for solution in result.solutions} == {method.code for method in METHODS}
    assert all(solution.method_name and solution.method_description for solution in result.solutions)
    assert all(solution.total_linear_meters == solution.occupied_length_m for solution in result.solutions)
