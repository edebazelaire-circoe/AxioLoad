from __future__ import annotations

import time

from pallet_optimizer.domain import CargoItem, OptimizationProblem, Shape, VehiclePolicy, to_primitive
from pallet_optimizer.engine import OptimizationEngine
from pallet_optimizer.ranking import placement_signature


def make_item(index: int, length: int = 1000, width: int = 1000, weight: float = 100) -> CargoItem:
    return CargoItem(f"I{index}", f"I{index}", index, Shape.PALLET, length, width, 1000, weight,
                     "A", 1, rotation_allowed=True)


def test_simple_case_returns_one_solution_per_optimization_method(base_payload) -> None:
    from pallet_optimizer.normalization import normalize_payload
    result = OptimizationEngine().optimize(normalize_payload(base_payload))
    assert result.status.value == "completed"
    assert len(result.solutions) == 5
    assert {s.method_code for s in result.solutions} == {"extreme_points", "skyline_blf", "block_layers", "brkga_hybrid", "cp_sat"}
    assert all(s.method_name and s.method_description for s in result.solutions)
    assert result.solutions[0].rank == 1
    assert all(s.vehicle_count == 1 for s in result.solutions)


def test_determinism_with_fixed_seed(base_payload) -> None:
    from pallet_optimizer.normalization import normalize_payload
    engine = OptimizationEngine(); problem = normalize_payload(base_payload)
    left = engine.optimize(problem); right = engine.optimize(problem)
    assert to_primitive(left.solutions) == to_primitive(right.solutions)


def test_multi_vehicle_minimizes_vehicle_count(simple_vehicle) -> None:
    items = tuple(make_item(i, length=2000, width=1200, weight=1500) for i in range(4))
    problem = OptimizationProblem(items, (simple_vehicle,), VehiclePolicy("forced", "test", 4), seed=1, budget_seconds=2)
    result = OptimizationEngine().optimize(problem)
    assert result.solutions
    assert result.solutions[0].vehicle_count == 2
    assert all(solution.vehicle_count == 2 for solution in result.solutions)


def test_incompatible_items_are_never_ranked(simple_vehicle) -> None:
    a = CargoItem("A", "A", 0, Shape.PALLET, 1000, 1000, 1000, 100, "A", 1,
                  compatibility_tags=("food",), incompatible_tags=("chemical",))
    b = CargoItem("B", "B", 1, Shape.PALLET, 1000, 1000, 1000, 100, "A", 1,
                  compatibility_tags=("chemical",))
    problem = OptimizationProblem((a, b), (simple_vehicle,), VehiclePolicy("forced", "test", 1), budget_seconds=1)
    result = OptimizationEngine().optimize(problem)
    assert not result.solutions
    assert any(d.code == "INCOMPATIBLE_CARGO" for d in result.diagnostics)


def test_100_objects_respect_short_budget() -> None:
    from pallet_optimizer.catalog import default_vehicle_catalog
    items = tuple(make_item(i, length=200, width=200, weight=10) for i in range(100))
    problem = OptimizationProblem(items, (default_vehicle_catalog()[0],), VehiclePolicy("forced", "semi_trailer", 1),
                                  seed=3, budget_seconds=1.0, requested_solutions=1)
    started = time.perf_counter(); result = OptimizationEngine().optimize(problem); elapsed = time.perf_counter() - started
    assert elapsed < 1.5
    assert result.solutions
    assert result.elapsed_seconds <= elapsed + 0.01


def test_user_reported_three_pallet_case_is_optimized() -> None:
    from pallet_optimizer.normalization import normalize_payload
    payload = {
        "dimension_unit": "mm",
        "weight_unit": "kg",
        "seed": 1,
        "budget_seconds": 5,
        "requested_solutions": 5,
        "vehicle_policy": {"mode": "forced", "forced_vehicle_id": "semi_trailer", "max_vehicles": 1},
        "items": [{
            "id": "PAL-001", "quantity": 3, "shape": "pallet",
            "length": 1200, "width": 800, "height": 1200, "weight": 500,
            "destination": "Client A", "delivery_order": 1, "rotation_allowed": True,
        }],
    }
    result = OptimizationEngine().optimize(normalize_payload(payload))
    assert result.status.value == "completed"
    assert result.solutions
    best = result.solutions[0].vehicle_plans[0]
    assert len(best.placements) == 3
    assert best.occupied_length_m == 1.2
    assert all(p.x_mm + p.envelope_width_mm <= 2450 for p in best.placements)
    assert all(p.y_mm + p.envelope_length_mm <= 13600 for p in best.placements)


def test_vehicle_width_changes_the_best_layout() -> None:
    from pallet_optimizer.domain import VehicleVersion
    narrow = VehicleVersion(
        model_id="narrow", version=1, name="Narrow",
        interior_length_mm=5000, interior_width_mm=1600, interior_height_mm=2500,
        linear_meter_width_mm=1600, payload_kg=5000,
        door_width_mm=1600, door_height_mm=2500, axles=(),
    )
    items = tuple(make_item(i, length=1200, width=800, weight=100) for i in range(3))
    result = OptimizationEngine().optimize(
        OptimizationProblem(items, (narrow,), VehiclePolicy("forced", "narrow", 1), budget_seconds=2)
    )
    assert result.solutions
    best = result.solutions[0].vehicle_plans[0]
    assert best.occupied_length_m == 2.0
    assert all(p.x_mm + p.envelope_width_mm <= 1600 for p in best.placements)


def test_too_short_vehicle_returns_actionable_diagnostic() -> None:
    from pallet_optimizer.domain import VehicleVersion
    vehicle = VehicleVersion(
        model_id="short", version=1, name="Short",
        interior_length_mm=1000, interior_width_mm=800, interior_height_mm=2500,
        linear_meter_width_mm=800, payload_kg=5000,
        door_width_mm=800, door_height_mm=2500, axles=(),
    )
    item = make_item(1, length=1200, width=800, weight=100)
    result = OptimizationEngine().optimize(
        OptimizationProblem((item,), (vehicle,), VehiclePolicy("forced", "short", 1), budget_seconds=1)
    )
    assert not result.solutions
    assert any(d.code == "ITEM_DOES_NOT_FIT" for d in result.diagnostics)


def test_linear_meters_follow_each_plan_occupied_length() -> None:
    from pallet_optimizer.domain import Placement
    from pallet_optimizer.metrics import calculate_length_metrics

    first = Placement("A", "A", "A", 1, 0, 0, 0, 0, 1200, 800, 1000, 1200, 800, 100)
    second_beside = Placement("B", "B", "A", 1, 800, 0, 0, 0, 1200, 800, 1000, 1200, 800, 100)
    second_behind = Placement("B", "B", "A", 1, 0, 1200, 0, 0, 1200, 800, 1000, 1200, 800, 100)

    compact = calculate_length_metrics((first, second_beside))
    longitudinal = calculate_length_metrics((first, second_behind))

    assert compact.occupied_length_m == compact.linear_meters == 1.2
    assert longitudinal.occupied_length_m == longitudinal.linear_meters == 2.4


def test_solution_linear_meters_are_individual_and_can_differ() -> None:
    from pallet_optimizer.normalization import normalize_payload

    payload = {
        "vehicle_policy": {"mode": "forced", "forced_vehicle_id": "semi_trailer", "max_vehicles": 1},
        "budget_seconds": 5,
        "requested_solutions": 5,
        "items": [
            {"id": "A", "quantity": 2, "shape": "pallet", "length": 1200, "width": 800,
             "height": 1000, "weight": 100, "destination": "A", "delivery_order": 1},
            {"id": "B", "quantity": 2, "shape": "pallet", "length": 1000, "width": 1000,
             "height": 1000, "weight": 100, "destination": "A", "delivery_order": 1},
        ],
    }
    result = OptimizationEngine().optimize(normalize_payload(payload))
    assert len(result.solutions) == 5
    assert len({solution.total_linear_meters for solution in result.solutions}) > 1
    for solution in result.solutions:
        assert solution.total_linear_meters == solution.occupied_length_m
        assert all(plan.linear_meters == plan.occupied_length_m for plan in solution.vehicle_plans)
