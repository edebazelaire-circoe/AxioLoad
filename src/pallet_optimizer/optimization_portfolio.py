from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import replace
from typing import Any, Iterable

from . import domain, packing, validation
from .domain import Diagnostic, OptimizationResult, Placement, Severity

_INSTALLED = False


def _group_key(item: Any) -> str:
    explicit = str(getattr(item, "keep_together_group", "") or "").strip()
    if explicit:
        return explicit
    destination = str(getattr(item, "destination", "") or "").strip().casefold()
    return f"client::{destination}" if destination else f"item::{item.id}"


def _install_grouped_item_order() -> None:
    original = packing._sort_items
    if getattr(original, "_axioload_client_grouping", False):
        return

    def grouped_sort(items: Iterable[Any], strategy: Any, rng: Any) -> list[Any]:
        source = list(items)
        groups: dict[tuple[int, str], list[Any]] = defaultdict(list)
        for item in source:
            groups[(-int(item.delivery_order), _group_key(item))].append(item)
        ordered: list[Any] = []
        for key in sorted(groups, key=lambda value: (value[0], value[1])):
            ordered.extend(original(groups[key], strategy, rng))
        return ordered

    grouped_sort._axioload_client_grouping = True  # type: ignore[attr-defined]
    packing._sort_items = grouped_sort  # type: ignore[assignment]


def _rectangle_gap(a: Placement, b: Placement) -> float:
    dx = max(a.x_mm - (b.x_mm + b.envelope_width_mm), b.x_mm - (a.x_mm + a.envelope_width_mm), 0)
    dy = max(a.y_mm - (b.y_mm + b.envelope_length_mm), b.y_mm - (a.y_mm + a.envelope_length_mm), 0)
    return (dx * dx + dy * dy) ** 0.5


def _connected_block(placements: list[Placement], tolerance_mm: int = 150) -> bool:
    if len(placements) < 2:
        return True
    visited = {0}
    frontier = [0]
    while frontier:
        current = frontier.pop()
        for index, candidate in enumerate(placements):
            if index in visited:
                continue
            if _rectangle_gap(placements[current], candidate) <= tolerance_mm:
                visited.add(index)
                frontier.append(index)
    return len(visited) == len(placements)


def _install_client_contiguity_validation() -> None:
    original = validation.validate_compatibility
    if getattr(original, "_axioload_client_contiguity", False):
        return

    def validate_with_client_blocks(
        placements_by_vehicle: tuple[tuple[Placement, ...], ...],
        items: dict[str, Any],
    ) -> tuple[Diagnostic, ...]:
        diagnostics = list(original(placements_by_vehicle, items))
        locations: dict[str, list[tuple[int, Placement]]] = defaultdict(list)
        for vehicle_index, placements in enumerate(placements_by_vehicle):
            for placement in placements:
                locations[_group_key(items[placement.item_id])].append((vehicle_index, placement))

        for group, located in locations.items():
            if group.startswith("item::") or len(located) < 2:
                continue
            vehicles = {vehicle_index for vehicle_index, _ in located}
            if len(vehicles) > 1 and not any(
                diagnostic.code == "KEEP_TOGETHER_SPLIT" and group in diagnostic.message
                for diagnostic in diagnostics
            ):
                diagnostics.append(Diagnostic(
                    "CLIENT_GROUP_SPLIT",
                    f"Le groupe client {group.removeprefix('client::')} est réparti sur plusieurs véhicules.",
                    details={"group": group, "vehicles": sorted(vehicles)},
                ))
                continue
            placements = [placement for _, placement in located]
            if not _connected_block(placements):
                diagnostics.append(Diagnostic(
                    "CLIENT_BLOCK_NOT_CONTIGUOUS",
                    f"Les marchandises du groupe client {group.removeprefix('client::')} ne forment pas un bloc spatial contigu.",
                    details={"group": group, "items": [placement.item_id for placement in placements]},
                ))
        return tuple(diagnostics)

    validate_with_client_blocks._axioload_client_contiguity = True  # type: ignore[attr-defined]
    validation.validate_compatibility = validate_with_client_blocks  # type: ignore[assignment]


def _install_model_profiles() -> tuple[Any, ...]:
    from . import optimization_methods

    method_type = optimization_methods.OptimizationMethod
    profiles = (
        method_type(
            code="cp_sat",
            name="Modèle 1 · Exact mathématique",
            short_label="CP-SAT / MILP-ready",
            description=(
                "Résolution exacte par contraintes avec positions, rotations, non-chevauchements, LIFO et essieux. "
                "OR-Tools CP-SAT est utilisé dans cette version ; l'interface reste prête pour un solveur MILP externe."
            ),
        ),
        method_type(
            code="extreme_points",
            name="Modèle 2 · Points extrêmes + GRASP",
            short_label="Construction multistart",
            description=(
                "Construction géométrique rapide par MaxRects et points extrêmes, relancée avec plusieurs graines "
                "afin de conserver le meilleur plan faisable."
            ),
        ),
        method_type(
            code="brkga_hybrid",
            name="Modèle 3 · Génétique multi-objectifs",
            short_label="BRKGA",
            description=(
                "Recherche génétique sur l'ordre et l'orientation, avec pénalités de longueur occupée, équilibre du poids, "
                "regroupement client et accessibilité LIFO."
            ),
        ),
        method_type(
            code="skyline_blf",
            name="Modèle 4 · Politique DRL/PPO",
            short_label="Mode heuristique expérimental",
            description=(
                "Interface de politique séquentielle compatible avec un futur modèle PPO. Sans poids entraînés configurés, "
                "AxioLoad utilise une politique Skyline déterministe et l'indique comme mode expérimental."
            ),
        ),
        method_type(
            code="block_layers",
            name="Modèle 5 · Décomposition multi-véhicules",
            short_label="Génération de colonnes heuristique",
            description=(
                "Décomposition maître / sous-problème : le moteur recherche le nombre minimal de véhicules puis construit "
                "des plans unitaires en blocs. Cette version est heuristique et ne revendique pas une borne duale exacte."
            ),
        ),
    )
    optimization_methods.METHODS = profiles
    optimization_methods.METHOD_BY_CODE = {method.code: method for method in profiles}
    return profiles


def _install_grasp_multistart() -> None:
    from . import optimization_methods

    current = optimization_methods.PACKERS["extreme_points"]
    if getattr(current, "_axioload_grasp", False):
        return

    def grasp_multistart(items: Any, vehicle: Any, seed: int, deadline: float) -> Any:
        best = None
        best_score = None
        diagnostics: list[Diagnostic] = []
        attempts = 0
        while attempts < 4 and time.perf_counter() < deadline:
            placements, attempt_diagnostics = current(items, vehicle, seed + attempts * 104729, deadline)
            diagnostics.extend(attempt_diagnostics)
            if placements:
                occupied = max((p.y_mm + p.envelope_length_mm for p in placements), default=0)
                total_weight = sum(p.weight_kg for p in placements)
                center = (
                    sum((p.x_mm + p.envelope_width_mm / 2) * p.weight_kg for p in placements) / total_weight
                    if total_weight else vehicle.interior_width_mm / 2
                )
                balance = abs(center - vehicle.interior_width_mm / 2)
                score = (occupied, balance)
                if best_score is None or score < best_score:
                    best = placements
                    best_score = score
            attempts += 1
        if best is None:
            return None, tuple(diagnostics[:3]) or (
                Diagnostic("GRASP_FAILED", "Les constructions GRASP n'ont produit aucun placement valide."),
            )
        return best, ()

    grasp_multistart._axioload_grasp = True  # type: ignore[attr-defined]
    optimization_methods.PACKERS["extreme_points"] = grasp_multistart


def _outcome_mode(code: str) -> tuple[str, str]:
    if code == "cp_sat":
        return "operational", "Exact lorsque le solveur termine avec une solution prouvée ; sinon meilleure solution faisable ou échec explicite."
    if code == "skyline_blf":
        return "experimental", "Politique heuristique active. Aucun réseau PPO entraîné n'est présenté comme opérationnel."
    if code == "block_layers":
        return "heuristic", "Décomposition heuristique sans garantie de borne Dantzig-Wolfe."
    return "operational", "Modèle opérationnel dans le budget sélectionné."


def _install_engine_isolation(profiles: tuple[Any, ...]) -> None:
    from .engine import OptimizationEngine

    original_solve = OptimizationEngine._solve_method
    original_optimize = OptimizationEngine.optimize
    if getattr(original_optimize, "_axioload_five_model_portfolio", False):
        return

    def solve_isolated(self: Any, problem: Any, vehicles: Any, method: Any, method_index: int, method_deadline: float) -> Any:
        started = time.perf_counter()
        try:
            solution, errors = original_solve(self, problem, vehicles, method, method_index, method_deadline)
            status = "success" if solution is not None else (
                "timeout" if time.perf_counter() >= method_deadline else "failure"
            )
            reason = "" if solution is not None else (
                errors[0].message if errors else "Aucun plan valide n'a été trouvé dans le temps imparti."
            )
            self._axioload_method_runs[method.code] = {
                "status": status,
                "elapsed_seconds": round(time.perf_counter() - started, 4),
                "reason": reason,
                "diagnostic_codes": [error.code for error in errors[:5]],
            }
            return solution, errors
        except Exception as exc:  # one model must never stop the remaining portfolio
            self._axioload_method_runs[method.code] = {
                "status": "failure",
                "elapsed_seconds": round(time.perf_counter() - started, 4),
                "reason": f"Erreur isolée du modèle : {exc}",
                "diagnostic_codes": ["METHOD_INTERNAL_ERROR"],
            }
            return None, (
                Diagnostic(
                    "METHOD_INTERNAL_ERROR",
                    f"Le modèle {method.name} a échoué sans interrompre les autres calculs.",
                    severity=Severity.WARNING,
                    details={"method": method.code, "error": str(exc)},
                ),
            )

    def optimize_portfolio(self: Any, problem: Any) -> OptimizationResult:
        self._axioload_method_runs = {}
        result = original_optimize(self, problem)
        solutions = {solution.method_code: solution for solution in result.solutions}
        outcomes: list[dict[str, Any]] = []
        for index, method in enumerate(profiles, start=1):
            run = dict(self._axioload_method_runs.get(method.code) or {})
            if not run:
                matching = next(
                    (
                        diagnostic for diagnostic in result.diagnostics
                        if diagnostic.details.get("method") == method.code
                    ),
                    None,
                )
                run = {
                    "status": "not_run" if matching and matching.code == "METHOD_NOT_RUN" else "failure",
                    "elapsed_seconds": 0.0,
                    "reason": matching.message if matching else "Le modèle n'a pas produit de résultat exploitable.",
                    "diagnostic_codes": [matching.code] if matching else [],
                }
            solution = solutions.get(method.code)
            mode, note = _outcome_mode(method.code)
            outcome = {
                "index": index,
                "code": method.code,
                "name": method.name,
                "short_label": method.short_label,
                "description": method.description,
                "execution_mode": mode,
                "execution_note": note,
                **run,
                "solution_id": solution.id if solution else None,
                "vehicle_count": solution.vehicle_count if solution else None,
                "occupied_length_m": solution.occupied_length_m if solution else None,
                "linear_meters": solution.total_linear_meters if solution else None,
                "axle_penalty": solution.axle_penalty if solution else None,
                "balance_penalty": solution.balance_penalty if solution else None,
            }
            outcomes.append(outcome)
        portfolio = Diagnostic(
            "METHOD_PORTFOLIO",
            "Résultat indépendant des cinq modèles d'optimisation.",
            severity=Severity.INFO,
            details={"outcomes": outcomes},
        )
        return replace(
            result,
            diagnostics=(*result.diagnostics, portfolio),
            engine_version="0.15.0",
        )

    solve_isolated._axioload_five_model_portfolio = True  # type: ignore[attr-defined]
    optimize_portfolio._axioload_five_model_portfolio = True  # type: ignore[attr-defined]
    OptimizationEngine._solve_method = solve_isolated  # type: ignore[method-assign]
    OptimizationEngine.optimize = optimize_portfolio  # type: ignore[method-assign]
    OptimizationEngine.version = "0.15.0"


def _install_serialization() -> None:
    original = domain.to_primitive
    if getattr(original, "_axioload_method_outcomes", False):
        return

    def to_primitive_with_outcomes(value: Any) -> Any:
        payload = original(value)
        if isinstance(value, OptimizationResult) and isinstance(payload, dict):
            for diagnostic in value.diagnostics:
                if diagnostic.code == "METHOD_PORTFOLIO":
                    payload["method_outcomes"] = original(diagnostic.details.get("outcomes", []))
                    break
            payload.setdefault("method_outcomes", [])
        return payload

    to_primitive_with_outcomes._axioload_method_outcomes = True  # type: ignore[attr-defined]
    domain.to_primitive = to_primitive_with_outcomes  # type: ignore[assignment]


def install_optimization_portfolio() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_grouped_item_order()
    _install_client_contiguity_validation()
    profiles = _install_model_profiles()
    _install_grasp_multistart()
    _install_engine_isolation(profiles)
    _install_serialization()
    _INSTALLED = True
