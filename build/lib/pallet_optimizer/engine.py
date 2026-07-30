from __future__ import annotations

import hashlib
import time
from dataclasses import replace

from .domain import (CargoItem, Diagnostic, OptimizationProblem, OptimizationResult, RunStatus,
                     Severity, Solution, VehiclePlan)
from .metrics import calculate_length_metrics
from .packing import STRATEGIES, PackingStrategy, estimate_vehicle_lower_bound, pack_single_vehicle, partition_items
from .ranking import rank_and_select
from .validation import (calculate_weight, has_errors, validate_compatibility, validate_delivery_access,
                         validate_geometry)


class OptimizationEngine:
    version = "0.6.1"

    def optimize(self, problem: OptimizationProblem) -> OptimizationResult:
        started = time.perf_counter()
        deadline = started + problem.budget_seconds
        candidates: list[Solution] = []
        diagnostics: list[Diagnostic] = []
        time_limit_reached = False
        vehicles = problem.vehicles
        if problem.vehicle_policy.mode == "forced":
            vehicles = tuple(v for v in vehicles if v.model_id == problem.vehicle_policy.forced_vehicle_id or v.version_id == problem.vehicle_policy.forced_vehicle_id)
        precheck = self._precheck(problem, vehicles)
        if precheck:
            elapsed = time.perf_counter() - started
            return OptimizationResult(
                RunStatus.INFEASIBLE, (), precheck, False, False, elapsed, problem.seed, self.version
            )
        for vehicle_count in range(1, problem.vehicle_policy.max_vehicles + 1):
            found_at_count = False
            for vehicle in vehicles:
                if vehicle_count < estimate_vehicle_lower_bound(problem.items, vehicle):
                    continue
                for strategy_index, strategy in enumerate(STRATEGIES):
                    for variant in range(4):
                        if time.perf_counter() >= deadline:
                            time_limit_reached = True
                            break
                        partitions = partition_items(problem.items, vehicle, vehicle_count, problem.seed, variant + strategy_index)
                        if partitions is None:
                            continue
                        plans: list[VehiclePlan] = []
                        failed = False
                        plan_diags: list[Diagnostic] = []
                        for plan_index, items in enumerate(partitions):
                            local_strategy = replace(strategy, jitter=1 if variant else 0)
                            placements, packing_diags = pack_single_vehicle(
                                items, vehicle, local_strategy,
                                problem.seed + variant * 97 + strategy_index * 17 + plan_index,
                            )
                            if placements is None:
                                plan_diags.extend(packing_diags)
                                failed = True
                                break
                            item_map = {item.id: item for item in items}
                            geometry = validate_geometry(vehicle, placements, item_map)
                            delivery = validate_delivery_access(placements)
                            weight, weight_diags, axle_penalty = calculate_weight(vehicle, placements)
                            all_diags = (*geometry, *delivery, *weight_diags)
                            if has_errors(all_diags):
                                plan_diags.extend(all_diags)
                                failed = True
                                break
                            length_metrics = calculate_length_metrics(placements)
                            plans.append(VehiclePlan(
                                vehicle_version_id=vehicle.version_id,
                                vehicle_name=vehicle.name,
                                placements=placements,
                                linear_meters=length_metrics.linear_meters,
                                occupied_length_m=length_metrics.occupied_length_m,
                                weight=weight,
                                diagnostics=all_diags,
                            ))
                        if failed:
                            if not diagnostics and plan_diags:
                                diagnostics.extend(plan_diags[:3])
                            continue
                        compatibility = validate_compatibility(tuple(plan.placements for plan in plans), {i.id: i for i in problem.items})
                        if has_errors(compatibility):
                            if not diagnostics:
                                diagnostics.extend(compatibility[:3])
                            continue
                        solution = self._build_solution(plans, compatibility, strategy.name, variant)
                        candidates.append(solution)
                        found_at_count = True
                    if time_limit_reached:
                        break
                if time_limit_reached:
                    break
            if found_at_count:
                break
            if time_limit_reached:
                break
        elapsed = time.perf_counter() - started
        if candidates:
            selected = rank_and_select(candidates, problem.requested_solutions)
            status = RunStatus.COMPLETED_WITH_TIME_LIMIT if time_limit_reached else RunStatus.COMPLETED
            result_diags = tuple(d for d in diagnostics if d.severity != Severity.ERROR)
            return OptimizationResult(status, selected, result_diags, time_limit_reached, False, elapsed, problem.seed, self.version)
        if not diagnostics:
            diagnostics.append(Diagnostic(
                "PACKING_SEARCH_EXHAUSTED",
                "Le portefeuille de méthodes de placement n’a pas trouvé de plan dans le budget de calcul. "
                "Augmentez le budget, autorisez un véhicule supplémentaire ou vérifiez les contraintes de séparation et d’ordre.",
            ))
        return OptimizationResult(RunStatus.INFEASIBLE, (), tuple(diagnostics), time_limit_reached, False, elapsed, problem.seed, self.version)


    @staticmethod
    def _precheck(problem: OptimizationProblem, vehicles: tuple) -> tuple[Diagnostic, ...]:
        diagnostics: list[Diagnostic] = []
        if not vehicles:
            return (Diagnostic("UNKNOWN_VEHICLE", "Le véhicule sélectionné n’existe plus dans le catalogue."),)
        unfit_sources: set[str] = set()
        for item in problem.items:
            fits_one = False
            for vehicle in vehicles:
                orientations = [0, 90] if item.rotation_allowed and item.length_mm != item.width_mm else [0]
                for orientation in orientations:
                    _, _, envelope_length, envelope_width = item.oriented_dimensions(orientation)
                    if (
                        envelope_length <= vehicle.interior_length_mm
                        and envelope_width <= vehicle.interior_width_mm
                        and envelope_width <= vehicle.door_width_mm
                        and item.height_mm + item.margins.top_mm <= vehicle.interior_height_mm
                        and item.height_mm + item.margins.top_mm <= vehicle.door_height_mm
                        and item.weight_kg <= vehicle.payload_kg
                    ):
                        fits_one = True
                        break
                if fits_one:
                    break
            if not fits_one and item.source_id not in unfit_sources:
                unfit_sources.add(item.source_id)
                diagnostics.append(Diagnostic(
                    "ITEM_DOES_NOT_FIT",
                    f"{item.source_id} ne peut entrer dans aucun véhicule sélectionné avec ses dimensions, sa hauteur, son poids et la rotation autorisée.",
                    field_path=item.source_id,
                    details={
                        "length_mm": item.length_mm, "width_mm": item.width_mm,
                        "height_mm": item.height_mm, "weight_kg": item.weight_kg,
                    },
                ))
        if problem.vehicle_policy.mode == "forced" and vehicles:
            vehicle = vehicles[0]
            max_vehicles = problem.vehicle_policy.max_vehicles
            total_weight = sum(item.weight_kg for item in problem.items)
            if total_weight > vehicle.payload_kg * max_vehicles + 1e-9:
                diagnostics.append(Diagnostic(
                    "TOTAL_PAYLOAD_EXCEEDED",
                    f"Le chargement pèse {total_weight:.1f} kg, au-delà des {vehicle.payload_kg * max_vehicles:.1f} kg disponibles sur {max_vehicles} véhicule(s).",
                ))
            usable_area = vehicle.interior_length_mm * vehicle.interior_width_mm - sum(
                obstacle.length_mm * obstacle.width_mm for obstacle in vehicle.obstacles
            )
            total_area = sum(
                (item.length_mm + item.margins.front_mm + item.margins.rear_mm)
                * (item.width_mm + item.margins.left_mm + item.margins.right_mm)
                for item in problem.items
            )
            if total_area > usable_area * max_vehicles:
                diagnostics.append(Diagnostic(
                    "TOTAL_FLOOR_AREA_EXCEEDED",
                    "La surface au sol demandée dépasse la surface intérieure disponible, même avant prise en compte des contraintes de rangement.",
                ))
        return tuple(diagnostics)

    @staticmethod
    def _build_solution(plans: list[VehiclePlan], diagnostics: tuple[Diagnostic, ...], strategy: str, variant: int) -> Solution:
        total_ldm = sum(plan.linear_meters for plan in plans)
        occupied = sum(plan.occupied_length_m for plan in plans)
        axle_penalty = 0.0
        balance_penalty = 0.0
        for plan in plans:
            if plan.weight.axle_loads_kg:
                loads = [load for _, load in plan.weight.axle_loads_kg]
                axle_penalty += max(loads) / max(1.0, sum(loads))
            if plan.placements:
                weighted_x = sum((p.x_mm + p.envelope_width_mm / 2) * p.weight_kg for p in plan.placements)
                total_weight = sum(p.weight_kg for p in plan.placements)
                mean_x = weighted_x / total_weight
                width = max(p.x_mm + p.envelope_width_mm for p in plan.placements)
                balance_penalty += abs(mean_x - width / 2) / max(1.0, width)
        raw_id = f"{strategy}:{variant}:" + ":".join(
            f"{p.item_id}@{index},{p.x_mm},{p.y_mm},{p.orientation_deg}"
            for index, plan in enumerate(plans) for p in plan.placements
        )
        solution_id = hashlib.sha1(raw_id.encode(), usedforsecurity=False).hexdigest()[:12]
        advantages = [f"Plan valide obtenu par {strategy}"]
        if len(plans) == 1:
            advantages.append("Chargement regroupé dans un seul véhicule")
        disadvantages = []
        if axle_penalty > 0.9:
            disadvantages.append("Répartition des charges à surveiller")
        return Solution(
            id=solution_id,
            rank=0,
            vehicle_plans=tuple(plans),
            total_linear_meters=total_ldm,
            occupied_length_m=occupied,
            vehicle_count=len(plans),
            axle_penalty=axle_penalty,
            balance_penalty=balance_penalty,
            advantages=tuple(advantages),
            disadvantages=tuple(disadvantages),
            diagnostics=diagnostics,
        )
