from __future__ import annotations

import hashlib
import time
from dataclasses import replace

from .domain import (
    CargoItem,
    Diagnostic,
    OptimizationProblem,
    OptimizationResult,
    RunStatus,
    Severity,
    Solution,
    VehiclePlan,
)
from .metrics import calculate_length_metrics
from .optimization_methods import METHODS, OptimizationMethod, pack_with_method
from .packing import estimate_vehicle_lower_bound, partition_items
from .ranking import solution_key
from .validation import (
    calculate_weight,
    has_errors,
    validate_compatibility,
    validate_delivery_access,
    validate_geometry,
)


class OptimizationEngine:
    version = "0.10.0"

    def optimize(self, problem: OptimizationProblem) -> OptimizationResult:
        started = time.perf_counter()
        deadline = started + problem.budget_seconds
        diagnostics: list[Diagnostic] = []
        method_solutions: list[Solution] = []
        vehicles = problem.vehicles
        if problem.vehicle_policy.mode == "forced":
            vehicles = tuple(
                vehicle
                for vehicle in vehicles
                if vehicle.model_id == problem.vehicle_policy.forced_vehicle_id
                or vehicle.version_id == problem.vehicle_policy.forced_vehicle_id
            )

        precheck = self._precheck(problem, vehicles)
        if precheck:
            elapsed = time.perf_counter() - started
            return OptimizationResult(
                RunStatus.INFEASIBLE,
                (),
                precheck,
                False,
                False,
                elapsed,
                problem.seed,
                self.version,
            )

        for method_index, method in enumerate(METHODS):
            now = time.perf_counter()
            remaining_methods = len(METHODS) - method_index
            remaining_budget = max(0.0, deadline - now)
            if remaining_budget <= 0:
                diagnostics.append(Diagnostic(
                    "METHOD_NOT_RUN",
                    f"La méthode {method.name} n’a pas pu être lancée faute de temps de calcul.",
                    severity=Severity.WARNING,
                    details={"method": method.code},
                ))
                continue
            method_deadline = min(deadline, now + remaining_budget / remaining_methods)
            best_for_method, method_errors = self._solve_method(
                problem,
                vehicles,
                method,
                method_index,
                method_deadline,
            )
            if best_for_method is None:
                if method_errors:
                    for diagnostic in method_errors[:3]:
                        if diagnostic.code not in {existing.code for existing in diagnostics}:
                            diagnostics.append(diagnostic)
                else:
                    diagnostics.append(Diagnostic(
                        "METHOD_NO_SOLUTION",
                        f"La méthode {method.name} n’a pas produit de plan valide dans le temps imparti.",
                        severity=Severity.WARNING,
                        details={"method": method.code},
                    ))
            else:
                method_solutions.append(best_for_method)

        elapsed = time.perf_counter() - started
        time_limit_reached = time.perf_counter() >= deadline
        if method_solutions:
            ordered = sorted(method_solutions, key=solution_key)
            selected = tuple(
                replace(solution, rank=index + 1)
                for index, solution in enumerate(ordered[: problem.requested_solutions])
            )
            status = RunStatus.COMPLETED_WITH_TIME_LIMIT if time_limit_reached else RunStatus.COMPLETED
            return OptimizationResult(
                status,
                selected,
                tuple(diagnostics),
                time_limit_reached,
                False,
                elapsed,
                problem.seed,
                self.version,
            )

        if not diagnostics:
            diagnostics.append(Diagnostic(
                "PACKING_SEARCH_EXHAUSTED",
                "Les cinq méthodes d’optimisation n’ont trouvé aucun plan valide dans le budget de calcul.",
            ))
        return OptimizationResult(
            RunStatus.INFEASIBLE,
            (),
            tuple(diagnostics),
            time_limit_reached,
            False,
            elapsed,
            problem.seed,
            self.version,
        )

    def _solve_method(
        self,
        problem: OptimizationProblem,
        vehicles: tuple,
        method: OptimizationMethod,
        method_index: int,
        method_deadline: float,
    ) -> tuple[Solution | None, tuple[Diagnostic, ...]]:
        best: Solution | None = None
        validation_errors: list[Diagnostic] = []
        for vehicle_count in range(1, problem.vehicle_policy.max_vehicles + 1):
            found_at_count = False
            for vehicle in vehicles:
                if time.perf_counter() >= method_deadline:
                    break
                if vehicle_count < estimate_vehicle_lower_bound(problem.items, vehicle):
                    continue
                for variant in range(3):
                    if time.perf_counter() >= method_deadline:
                        break
                    partitions = partition_items(
                        problem.items,
                        vehicle,
                        vehicle_count,
                        problem.seed + method_index * 1009,
                        variant,
                    )
                    if partitions is None:
                        continue
                    plans: list[VehiclePlan] = []
                    method_failed = False
                    plan_diagnostics: list[Diagnostic] = []
                    for plan_index, items in enumerate(partitions):
                        placements, packing_diagnostics = pack_with_method(
                            method,
                            items,
                            vehicle,
                            problem.seed + method_index * 10_007 + variant * 997 + plan_index * 31,
                            method_deadline,
                        )
                        if placements is None:
                            plan_diagnostics.extend(packing_diagnostics)
                            method_failed = True
                            break
                        item_map = {item.id: item for item in items}
                        geometry = validate_geometry(vehicle, placements, item_map)
                        delivery = validate_delivery_access(placements)
                        weight, weight_diagnostics, _ = calculate_weight(vehicle, placements)
                        all_diagnostics = (*geometry, *delivery, *weight_diagnostics)
                        if has_errors(all_diagnostics):
                            plan_diagnostics.extend(all_diagnostics)
                            validation_errors.extend(diagnostic for diagnostic in all_diagnostics if diagnostic.severity == Severity.ERROR)
                            method_failed = True
                            break
                        length_metrics = calculate_length_metrics(placements)
                        plans.append(VehiclePlan(
                            vehicle_version_id=vehicle.version_id,
                            vehicle_name=vehicle.name,
                            placements=placements,
                            linear_meters=length_metrics.linear_meters,
                            occupied_length_m=length_metrics.occupied_length_m,
                            weight=weight,
                            diagnostics=all_diagnostics,
                        ))
                    if method_failed:
                        continue
                    compatibility = validate_compatibility(
                        tuple(plan.placements for plan in plans),
                        {item.id: item for item in problem.items},
                    )
                    if has_errors(compatibility):
                        validation_errors.extend(diagnostic for diagnostic in compatibility if diagnostic.severity == Severity.ERROR)
                        continue
                    solution = self._build_solution(plans, compatibility, method, variant)
                    if best is None or solution_key(solution) < solution_key(best):
                        best = solution
                    found_at_count = True
                if time.perf_counter() >= method_deadline:
                    break
            if found_at_count:
                break
            if time.perf_counter() >= method_deadline:
                break
        return best, tuple(validation_errors)

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
                        "length_mm": item.length_mm,
                        "width_mm": item.width_mm,
                        "height_mm": item.height_mm,
                        "weight_kg": item.weight_kg,
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
    def _build_solution(
        plans: list[VehiclePlan],
        diagnostics: tuple[Diagnostic, ...],
        method: OptimizationMethod,
        variant: int,
    ) -> Solution:
        total_ldm = sum(plan.linear_meters for plan in plans)
        occupied = sum(plan.occupied_length_m for plan in plans)
        axle_penalty = 0.0
        balance_penalty = 0.0
        for plan in plans:
            if plan.weight.axle_loads_kg:
                loads = [load for _, load in plan.weight.axle_loads_kg]
                axle_penalty += max(loads) / max(1.0, sum(loads))
            if plan.placements:
                weighted_x = sum(
                    (placement.x_mm + placement.envelope_width_mm / 2) * placement.weight_kg
                    for placement in plan.placements
                )
                total_weight = sum(placement.weight_kg for placement in plan.placements)
                mean_x = weighted_x / total_weight
                width = max(placement.x_mm + placement.envelope_width_mm for placement in plan.placements)
                balance_penalty += abs(mean_x - width / 2) / max(1.0, width)
        raw_id = f"{method.code}:{variant}:" + ":".join(
            f"{placement.item_id}@{index},{placement.x_mm},{placement.y_mm},{placement.orientation_deg}"
            for index, plan in enumerate(plans)
            for placement in plan.placements
        )
        solution_id = hashlib.sha1(raw_id.encode(), usedforsecurity=False).hexdigest()[:12]
        advantages = [f"Plan calculé avec la méthode {method.name}"]
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
            method_code=method.code,
            method_name=method.name,
            method_description=method.description,
        )
