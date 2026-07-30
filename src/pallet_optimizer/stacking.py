from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Mapping, Sequence

from . import engine as engine_module
from . import total_optimization as total_module
from . import total_preprocessing as preprocessing_module
from .domain import CargoItem, Diagnostic, OptimizationProblem, OptimizationResult, Placement, Severity, Solution, VehiclePolicy, VehicleVersion
from .normalization import normalize_payload


@dataclass(frozen=True, slots=True)
class StackPreparation:
    items: tuple[CargoItem, ...]
    diagnostics: tuple[Diagnostic, ...]


_STACK_ITEMS: dict[str, tuple[CargoItem, ...]] = {}
_STACK_SYNTHETIC: dict[str, CargoItem] = {}
_INSTALLED = False
_ORIGINAL_ENGINE_OPTIMIZE = engine_module.OptimizationEngine.optimize
_ORIGINAL_ENGINE_PRECHECK = engine_module.OptimizationEngine._precheck
_ORIGINAL_ENGINE_LOWER_BOUND = engine_module.estimate_vehicle_lower_bound
_ORIGINAL_ENGINE_PARTITION = engine_module.partition_items
_ORIGINAL_ENGINE_COMPATIBILITY = engine_module.validate_compatibility
_ORIGINAL_PACK_WITH_METHOD = total_module.pack_with_method
_ORIGINAL_GEOMETRY = total_module.validate_geometry
_ORIGINAL_ORACLE_EVALUATE = total_module.PackingOracle.evaluate


def clear_stacking_registry() -> None:
    _STACK_ITEMS.clear(); _STACK_SYNTHETIC.clear()


def _usable_floor_area_m2(vehicle: VehicleVersion) -> float:
    area = vehicle.interior_length_mm * vehicle.interior_width_mm - sum(o.length_mm * o.width_mm for o in vehicle.obstacles)
    return max(0.001, area / 1_000_000)


def _derived_zone_load_limit(vehicle: VehicleVersion) -> float:
    return max(1500.0, 2.0 * vehicle.payload_kg / _usable_floor_area_m2(vehicle))


def _stack_key(item: CargoItem) -> tuple[Any, ...]:
    return (item.source_id,item.shape,item.length_mm,item.width_mm,item.height_mm,round(item.weight_kg,6),item.destination,
            item.delivery_order,item.rotation_allowed,item.margins,item.compatibility_tags,item.incompatible_tags,
            item.keep_together_group,item.separate_group,item.separation_mm,item.zone)


def prepare_stacks(items: Sequence[CargoItem], vehicle: VehicleVersion) -> StackPreparation:
    grouped: dict[tuple[Any, ...], list[CargoItem]] = {}; output: list[CargoItem] = []; diagnostics: list[Diagnostic] = []
    for item in items:
        if item.stackable and item.shape.value == "pallet": grouped.setdefault(_stack_key(item), []).append(item)
        else: output.append(item)
    pressure_limit = _derived_zone_load_limit(vehicle)
    for group in grouped.values():
        group.sort(key=lambda value: (value.input_index, value.id)); first = group[0]
        max_by_height = max(1, min(vehicle.interior_height_mm, vehicle.door_height_mm) // max(1, first.height_mm))
        footprint_m2 = max(0.001, first.length_mm * first.width_mm / 1_000_000)
        max_by_pressure = max(1, math.floor(pressure_limit * footprint_m2 / max(first.weight_kg, 0.001)))
        stack_count = max(1, min(max_by_height, max_by_pressure))
        if len(group) > 1 and max_by_pressure < min(len(group), max_by_height):
            diagnostics.append(Diagnostic("STACKING_LIMITED_BY_WEIGHT_CONCENTRATION",
                f"{first.source_id} est indiqué gerbable, mais le poids concentré sur une même empreinte limite les piles à {max_by_pressure} unité(s). Les unités restantes sont réparties sur d’autres positions.",
                severity=Severity.WARNING, field_path=first.source_id,
                details={"estimated_limit_kg_m2":round(pressure_limit,1),"footprint_m2":round(footprint_m2,3),"unit_weight_kg":first.weight_kg}))
        for stack_index, start in enumerate(range(0, len(group), stack_count), 1):
            members = tuple(group[start:start + stack_count])
            if len(members) == 1: output.append(members[0]); continue
            synthetic_id = f"__stack__{first.source_id}__{stack_index}__{len(members)}"
            synthetic = replace(first,id=synthetic_id,input_index=min(m.input_index for m in members),
                                height_mm=sum(m.height_mm for m in members),weight_kg=sum(m.weight_kg for m in members),stackable=False)
            _STACK_ITEMS[synthetic_id] = members; _STACK_SYNTHETIC[synthetic_id] = synthetic; output.append(synthetic)
            diagnostics.append(Diagnostic("STACKING_APPLIED",f"{len(members)} palettes {first.source_id} sont gerbées sur une même empreinte.",
                                          severity=Severity.INFO,field_path=first.source_id,
                                          details={"stack_size":len(members),"synthetic_id":synthetic_id}))
    output.sort(key=lambda item: (item.input_index, item.id))
    return StackPreparation(tuple(output), tuple(diagnostics))


def _resolved_item_map(item_map: Mapping[str, CargoItem], placements: Sequence[Placement]) -> dict[str, CargoItem]:
    resolved = dict(item_map)
    for placement in placements:
        if placement.item_id in _STACK_SYNTHETIC: resolved[placement.item_id] = _STACK_SYNTHETIC[placement.item_id]
    return resolved


def _compatibility(placements_by_vehicle: tuple[tuple[Placement, ...], ...], items: dict[str, CargoItem]) -> tuple[Diagnostic, ...]:
    merged = dict(items)
    for placements in placements_by_vehicle: merged.update(_resolved_item_map(merged, placements))
    return _ORIGINAL_ENGINE_COMPATIBILITY(placements_by_vehicle, merged)


def _geometry(vehicle: VehicleVersion, placements: tuple[Placement, ...], items: dict[str, CargoItem]) -> tuple[Diagnostic, ...]:
    return _ORIGINAL_GEOMETRY(vehicle, placements, _resolved_item_map(items, placements))


def _lower_bound(items: tuple[CargoItem, ...], vehicle: VehicleVersion) -> int:
    return _ORIGINAL_ENGINE_LOWER_BOUND(prepare_stacks(items, vehicle).items, vehicle)


def _partition(items: tuple[CargoItem, ...], vehicle: VehicleVersion, vehicle_count: int, seed: int,
               variant: int = 0) -> tuple[tuple[CargoItem, ...], ...] | None:
    return _ORIGINAL_ENGINE_PARTITION(prepare_stacks(items, vehicle).items, vehicle, vehicle_count, seed, variant)


def _precheck(problem: OptimizationProblem, vehicles: tuple[VehicleVersion, ...]) -> tuple[Diagnostic, ...]:
    if problem.vehicle_policy.mode == "forced" and len(vehicles) == 1:
        return _ORIGINAL_ENGINE_PRECHECK(replace(problem, items=prepare_stacks(problem.items, vehicles[0]).items), vehicles)
    return _ORIGINAL_ENGINE_PRECHECK(problem, vehicles)


def _expand_placement(placement: Placement) -> tuple[Placement, ...]:
    members = _STACK_ITEMS.get(placement.item_id)
    if not members: return (placement,)
    expanded = []; z_mm = placement.z_mm
    for member in members:
        actual_length, actual_width, envelope_length, envelope_width = member.oriented_dimensions(placement.orientation_deg)
        expanded.append(Placement(item_id=member.id,source_id=member.source_id,destination=member.destination,
            delivery_order=member.delivery_order,x_mm=placement.x_mm,y_mm=placement.y_mm,z_mm=z_mm,
            orientation_deg=placement.orientation_deg,actual_length_mm=actual_length,actual_width_mm=actual_width,
            actual_height_mm=member.height_mm,envelope_length_mm=envelope_length,envelope_width_mm=envelope_width,
            weight_kg=member.weight_kg))
        z_mm += member.height_mm
    return tuple(expanded)


def expand_placements(placements: Sequence[Placement]) -> tuple[Placement, ...]:
    return tuple(expanded for placement in placements for expanded in _expand_placement(placement))


def _expand_solution(solution: Solution) -> Solution:
    return replace(solution, vehicle_plans=tuple(replace(plan,placements=expand_placements(plan.placements)) for plan in solution.vehicle_plans))


def _engine_optimize(self: engine_module.OptimizationEngine, problem: OptimizationProblem) -> OptimizationResult:
    clear_stacking_registry(); selected = problem.vehicles
    if problem.vehicle_policy.mode == "forced":
        selected = tuple(v for v in selected if v.model_id == problem.vehicle_policy.forced_vehicle_id or v.version_id == problem.vehicle_policy.forced_vehicle_id)
    stack_diagnostics = list(prepare_stacks(problem.items, selected[0]).diagnostics) if selected else []
    result = _ORIGINAL_ENGINE_OPTIMIZE(self, problem)
    unique = {(d.code,d.field_path):d for d in (*result.diagnostics,*stack_diagnostics)}
    return replace(result,solutions=tuple(_expand_solution(s) for s in result.solutions),diagnostics=tuple(unique.values()))


def _pack_with_method(method: Any, items: tuple[CargoItem, ...], vehicle: VehicleVersion, seed: int, deadline: float):
    return _ORIGINAL_PACK_WITH_METHOD(method, prepare_stacks(items, vehicle).items, vehicle, seed, deadline)


def _expand_plan_dict(plan: dict[str, Any]) -> dict[str, Any]:
    output = []
    for raw in plan.get("placements") or []:
        members = _STACK_ITEMS.get(str(raw.get("item_id") or ""))
        if not members: output.append(raw); continue
        z_mm = int(raw.get("z_mm") or 0); orientation = int(raw.get("orientation_deg") or 0)
        for member in members:
            actual_length, actual_width, envelope_length, envelope_width = member.oriented_dimensions(orientation)
            output.append({**raw,"item_id":member.id,"source_id":member.source_id,"destination":member.destination,
                "delivery_order":member.delivery_order,"z_mm":z_mm,"actual_length_mm":actual_length,
                "actual_width_mm":actual_width,"actual_height_mm":member.height_mm,"envelope_length_mm":envelope_length,
                "envelope_width_mm":envelope_width,"weight_kg":member.weight_kg,"stacked":True,"stack_id":raw.get("item_id")})
            z_mm += member.height_mm
    return {**plan,"placements":output}


def _oracle_evaluate(self: Any, route: Sequence[int], method_codes: Sequence[str], *, seed_offset: int = 0):
    result = _ORIGINAL_ORACLE_EVALUATE(self, route, method_codes, seed_offset=seed_offset)
    return replace(result, plan=_expand_plan_dict(result.plan)) if result.plan is not None else result


def diagnostics_for_payload(payload: Mapping[str, Any], catalog: tuple[VehicleVersion, ...]) -> tuple[Diagnostic, ...]:
    try: problem = normalize_payload(payload, requested_solutions=1, catalog=catalog)
    except Exception: return ()
    return prepare_stacks(problem.items, problem.vehicles[0]).diagnostics if problem.vehicles else ()


def can_pack_items(items: tuple[CargoItem, ...], vehicle: VehicleVersion, *, budget_seconds: float = 2.0) -> tuple[bool, tuple[Diagnostic, ...]]:
    problem = OptimizationProblem(items=items,vehicles=(vehicle,),vehicle_policy=VehiclePolicy(mode="forced",forced_vehicle_id=vehicle.model_id,max_vehicles=1),
                                  budget_seconds=max(0.2,min(30.0,budget_seconds)),requested_solutions=1)
    result = engine_module.OptimizationEngine().optimize(problem)
    return bool(result.solutions), result.diagnostics


def install_stacking() -> None:
    global _INSTALLED
    if _INSTALLED: return
    engine_module.estimate_vehicle_lower_bound = _lower_bound; engine_module.partition_items = _partition
    engine_module.validate_compatibility = _compatibility; engine_module.OptimizationEngine._precheck = staticmethod(_precheck)
    engine_module.OptimizationEngine.optimize = _engine_optimize
    total_module.pack_with_method = _pack_with_method; total_module.validate_geometry = _geometry
    total_module.validate_compatibility = _compatibility; total_module.PackingOracle.evaluate = _oracle_evaluate
    preprocessing_module.pack_with_method = _pack_with_method; preprocessing_module.validate_geometry = _geometry
    preprocessing_module.validate_compatibility = _compatibility; preprocessing_module.estimate_vehicle_lower_bound = _lower_bound
    _INSTALLED = True
