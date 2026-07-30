from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, replace
from typing import Callable

from .domain import CargoItem, Diagnostic, Placement, VehicleVersion
from .envelopes import build_envelope
from .packing import (
    PackingStrategy,
    _candidate_is_valid,
    _candidate_points,
    _make_placement,
    _ordered_candidates,
    _pack_extreme_points,
    _pack_maxrects,
    _sort_items,
)


@dataclass(frozen=True, slots=True)
class OptimizationMethod:
    code: str
    name: str
    description: str
    short_label: str


METHODS: tuple[OptimizationMethod, ...] = (
    OptimizationMethod(
        code="extreme_points",
        name="MaxRects / Points extrêmes",
        short_label="Espaces libres",
        description=(
            "Place chaque objet dans un espace libre ou un point d’ancrage créé par les objets déjà chargés. "
            "La méthode teste les rotations autorisées et privilégie les positions qui réduisent la longueur occupée."
        ),
    ),
    OptimizationMethod(
        code="skyline_blf",
        name="Skyline Bottom-Left-Fill",
        short_label="Profil de chargement",
        description=(
            "Maintient un profil longitudinal du chargement et pose chaque objet au niveau le plus bas possible, "
            "puis le plus à gauche. Les rotations autorisées sont comparées avant chaque placement."
        ),
    ),
    OptimizationMethod(
        code="block_layers",
        name="Blocs et couches",
        short_label="Blocs logistiques",
        description=(
            "Regroupe les objets identiques ou compatibles en rangées et couches régulières. Cette organisation "
            "favorise la stabilité visuelle, la manutention et le respect de l’ordre de déchargement."
        ),
    ),
    OptimizationMethod(
        code="brkga_hybrid",
        name="BRKGA hybride",
        short_label="Recherche génétique",
        description=(
            "Fait évoluer plusieurs ordres de chargement et choix d’orientation à l’aide de clés aléatoires biaisées, "
            "puis décode chaque candidat avec un placement spatial par points extrêmes."
        ),
    ),
    OptimizationMethod(
        code="cp_sat",
        name="Résolveur par contraintes CP-SAT",
        short_label="Contraintes exactes",
        description=(
            "Formule les positions, rotations, non-chevauchements, dimensions, ordre de livraison et limites d’essieux "
            "comme des contraintes. OR-Tools CP-SAT est utilisé lorsqu’il est disponible, avec un solveur de secours intégré."
        ),
    ),
)

METHOD_BY_CODE = {method.code: method for method in METHODS}


def _orientations(item: CargoItem, preferred: int | None = None) -> list[int]:
    values = [0]
    if item.rotation_allowed and item.length_mm != item.width_mm:
        values.append(90)
    if preferred in values:
        values.remove(preferred)
        values.insert(0, preferred)
    return values


def _occupied_length(placements: tuple[Placement, ...] | list[Placement]) -> int:
    return max((p.y_mm + p.envelope_length_mm for p in placements), default=0)


def _balance_penalty(placements: tuple[Placement, ...] | list[Placement], vehicle: VehicleVersion) -> float:
    total = sum(p.weight_kg for p in placements)
    if total <= 0:
        return 0.0
    center = sum((p.x_mm + p.envelope_width_mm / 2) * p.weight_kg for p in placements) / total
    return abs(center - vehicle.interior_width_mm / 2) / max(1.0, vehicle.interior_width_mm)


def _pack_sequence(
    items: list[CargoItem],
    vehicle: VehicleVersion,
    preferred_orientations: dict[str, int],
    candidate_order: str = "front-left",
) -> tuple[Placement, ...] | None:
    strategy = PackingStrategy(
        name="sequence-decoder",
        item_tiebreak="area",
        candidate_order=candidate_order,
        algorithm="extreme",
    )
    item_map = {item.id: item for item in items}
    placed: list[Placement] = []
    for item in items:
        best: tuple[tuple[float, ...], Placement] | None = None
        for orientation in _orientations(item, preferred_orientations.get(item.id)):
            envelope = build_envelope(item, orientation)
            points = _ordered_candidates(
                _candidate_points(placed, vehicle, item_map),
                envelope.envelope_width_mm,
                vehicle,
                strategy,
            )
            for x, y in points:
                candidate = _make_placement(item, orientation, x, y)
                if not _candidate_is_valid(candidate, placed, item_map, vehicle):
                    continue
                occupied = max(_occupied_length(placed), y + candidate.envelope_length_mm)
                center_error = abs((x + candidate.envelope_width_mm / 2) - vehicle.interior_width_mm / 2)
                score = (occupied, y, center_error, x, orientation)
                if best is None or score < best[0]:
                    best = (score, candidate)
        if best is None:
            return None
        placed.append(best[1])
    return tuple(placed)


def pack_extreme_points(
    items: tuple[CargoItem, ...],
    vehicle: VehicleVersion,
    seed: int,
    deadline: float,
) -> tuple[tuple[Placement, ...] | None, tuple[Diagnostic, ...]]:
    strategies = (
        PackingStrategy("maxrects-short-side", "area", "front-left", algorithm="maxrects", score="short-side"),
        PackingStrategy("maxrects-area-fit", "width", "center", algorithm="maxrects", score="area-fit"),
        PackingStrategy("extreme-points", "length", "front-left", algorithm="extreme", score="bottom-left"),
    )
    best: tuple[Placement, ...] | None = None
    for index, strategy in enumerate(strategies):
        if time.perf_counter() >= deadline:
            break
        if strategy.algorithm == "maxrects":
            placements, _ = _pack_maxrects(items, vehicle, strategy, seed + index * 31)
            if placements is None:
                placements, _ = _pack_extreme_points(items, vehicle, replace(strategy, algorithm="extreme"), seed + index * 31)
        else:
            placements, _ = _pack_extreme_points(items, vehicle, strategy, seed + index * 31)
        if placements is not None and (best is None or (_occupied_length(placements), _balance_penalty(placements, vehicle)) < (_occupied_length(best), _balance_penalty(best, vehicle))):
            best = placements
    if best is None:
        return None, (Diagnostic("EXTREME_POINTS_FAILED", "La méthode MaxRects / Points extrêmes n’a pas trouvé de placement valide."),)
    return best, ()


def _skyline_depth_at(
    x_mm: int,
    width_mm: int,
    placed: list[Placement],
    item_map: dict[str, CargoItem],
    vehicle: VehicleVersion,
) -> int:
    y_mm = 0
    right = x_mm + width_mm
    for placement in placed:
        gap = item_map[placement.item_id].separation_mm
        other_left = placement.x_mm - gap
        other_right = placement.x_mm + placement.envelope_width_mm + gap
        if right > other_left and x_mm < other_right:
            y_mm = max(y_mm, placement.y_mm + placement.envelope_length_mm + gap)
    for obstacle in vehicle.obstacles:
        if right > obstacle.x_mm and x_mm < obstacle.x_mm + obstacle.width_mm:
            y_mm = max(y_mm, obstacle.y_mm + obstacle.length_mm)
    return y_mm


def pack_skyline(
    items: tuple[CargoItem, ...],
    vehicle: VehicleVersion,
    seed: int,
    deadline: float,
) -> tuple[tuple[Placement, ...] | None, tuple[Diagnostic, ...]]:
    strategy = PackingStrategy("skyline-bottom-left", "area", "front-left", algorithm="skyline")
    rng = random.Random(seed)
    ordered = _sort_items(items, strategy, rng)
    item_map = {item.id: item for item in items}
    placed: list[Placement] = []
    for item in ordered:
        if time.perf_counter() >= deadline:
            return None, (Diagnostic("SKYLINE_TIMEOUT", "La méthode Skyline a atteint son temps de calcul."),)
        candidates: list[tuple[tuple[float, ...], Placement]] = []
        for orientation in _orientations(item):
            envelope = build_envelope(item, orientation)
            xs = {0, max(0, vehicle.interior_width_mm - envelope.envelope_width_mm)}
            for placement in placed:
                xs.add(placement.x_mm)
                xs.add(placement.x_mm + placement.envelope_width_mm)
            for obstacle in vehicle.obstacles:
                xs.add(obstacle.x_mm)
                xs.add(obstacle.x_mm + obstacle.width_mm)
            for x_mm in sorted(xs):
                if x_mm < 0 or x_mm + envelope.envelope_width_mm > vehicle.interior_width_mm:
                    continue
                y_mm = _skyline_depth_at(x_mm, envelope.envelope_width_mm, placed, item_map, vehicle)
                candidate = _make_placement(item, orientation, x_mm, y_mm)
                if not _candidate_is_valid(candidate, placed, item_map, vehicle):
                    continue
                score = (
                    y_mm + candidate.envelope_length_mm,
                    y_mm,
                    x_mm,
                    abs((x_mm + candidate.envelope_width_mm / 2) - vehicle.interior_width_mm / 2),
                )
                candidates.append((score, candidate))
        if not candidates:
            return None, (Diagnostic("SKYLINE_FAILED", f"Skyline n’a pas trouvé de position pour {item.id}."),)
        placed.append(min(candidates, key=lambda pair: pair[0])[1])
    return tuple(placed), ()


def _layer_groups(items: tuple[CargoItem, ...]) -> list[list[CargoItem]]:
    grouped: dict[tuple, list[CargoItem]] = {}
    for item in items:
        key = (
            item.delivery_order,
            item.source_id,
            item.length_mm,
            item.width_mm,
            item.height_mm,
            item.rotation_allowed,
            item.keep_together_group,
        )
        grouped.setdefault(key, []).append(item)
    groups = list(grouped.values())
    groups.sort(key=lambda group: (-group[0].delivery_order, -len(group), -(group[0].length_mm * group[0].width_mm), group[0].input_index))
    return groups


def _best_layer_orientation(group: list[CargoItem], vehicle: VehicleVersion) -> int:
    item = group[0]
    scored: list[tuple[tuple[int, int, int], int]] = []
    for orientation in _orientations(item):
        envelope = build_envelope(item, orientation)
        if envelope.envelope_width_mm > vehicle.interior_width_mm or envelope.envelope_length_mm > vehicle.interior_length_mm:
            continue
        across = max(1, vehicle.interior_width_mm // envelope.envelope_width_mm)
        rows = math.ceil(len(group) / across)
        depth = rows * envelope.envelope_length_mm
        unused = vehicle.interior_width_mm - min(len(group), across) * envelope.envelope_width_mm
        scored.append(((depth, unused, orientation), orientation))
    return min(scored)[1] if scored else 0


def pack_block_layers(
    items: tuple[CargoItem, ...],
    vehicle: VehicleVersion,
    seed: int,
    deadline: float,
) -> tuple[tuple[Placement, ...] | None, tuple[Diagnostic, ...]]:
    del seed
    item_map = {item.id: item for item in items}
    placed: list[Placement] = []
    current_depth = 0
    for group in _layer_groups(items):
        if time.perf_counter() >= deadline:
            return None, (Diagnostic("LAYER_TIMEOUT", "La méthode Blocs et couches a atteint son temps de calcul."),)
        orientation = _best_layer_orientation(group, vehicle)
        envelope = build_envelope(group[0], orientation)
        across = max(1, vehicle.interior_width_mm // envelope.envelope_width_mm)
        group_start = current_depth
        for index, item in enumerate(group):
            row = index // across
            column = index % across
            preferred = orientation if orientation in _orientations(item) else 0
            candidate = _make_placement(
                item,
                preferred,
                column * envelope.envelope_width_mm,
                group_start + row * envelope.envelope_length_mm,
            )
            if not _candidate_is_valid(candidate, placed, item_map, vehicle):
                # Practical repair for obstacles, separation or slightly heterogeneous groups.
                repaired = _pack_sequence([item], vehicle, {item.id: preferred})
                if repaired is None:
                    return None, (Diagnostic("LAYER_FAILED", f"La construction en blocs n’a pas pu placer {item.id}."),)
                repair_candidates = []
                for candidate_point in _candidate_points(placed, vehicle, item_map):
                    repaired_candidate = _make_placement(item, preferred, *candidate_point)
                    if _candidate_is_valid(repaired_candidate, placed, item_map, vehicle):
                        repair_candidates.append(repaired_candidate)
                if not repair_candidates:
                    return None, (Diagnostic("LAYER_FAILED", f"La construction en blocs n’a pas pu réparer le placement de {item.id}."),)
                candidate = min(repair_candidates, key=lambda p: (p.y_mm + p.envelope_length_mm, p.y_mm, p.x_mm))
            placed.append(candidate)
        current_depth = max(current_depth, _occupied_length(placed))
    return tuple(placed), ()


def _chromosome_fitness(
    chromosome: tuple[float, ...],
    items: tuple[CargoItem, ...],
    vehicle: VehicleVersion,
) -> tuple[float, tuple[Placement, ...] | None]:
    n = len(items)
    order_keys = chromosome[:n]
    rotation_keys = chromosome[n:]
    ordered_indices = sorted(
        range(n),
        key=lambda index: (-items[index].delivery_order, order_keys[index], -items[index].length_mm * items[index].width_mm, items[index].input_index),
    )
    ordered = [items[index] for index in ordered_indices]
    orientations = {
        items[index].id: 90 if rotation_keys[index] >= 0.5 and items[index].rotation_allowed and items[index].length_mm != items[index].width_mm else 0
        for index in range(n)
    }
    placements = _pack_sequence(ordered, vehicle, orientations, candidate_order="center")
    if placements is None:
        return 1e12, None
    occupied = _occupied_length(placements)
    balance = _balance_penalty(placements, vehicle)
    orientation_changes = sum(1 for placement in placements if placement.orientation_deg == 90)
    return occupied + balance * 250 + orientation_changes * 0.01, placements


def pack_brkga(
    items: tuple[CargoItem, ...],
    vehicle: VehicleVersion,
    seed: int,
    deadline: float,
) -> tuple[tuple[Placement, ...] | None, tuple[Diagnostic, ...]]:
    rng = random.Random(seed)
    n = len(items)
    population_size = 10 if n > 55 else 16 if n > 25 else 24
    elite_count = max(2, round(population_size * 0.22))
    mutant_count = max(2, round(population_size * 0.15))
    elite_bias = 0.72

    deterministic_order = [0.0] * n
    order = sorted(range(n), key=lambda i: (-items[i].delivery_order, -(items[i].length_mm * items[i].width_mm), items[i].input_index))
    for rank, index in enumerate(order):
        deterministic_order[index] = rank / max(1, n - 1)
    deterministic_rotation = [0.75 if item.rotation_allowed and item.width_mm > item.length_mm else 0.25 for item in items]
    population: list[tuple[float, ...]] = [tuple(deterministic_order + deterministic_rotation)]
    while len(population) < population_size:
        population.append(tuple(rng.random() for _ in range(n * 2)))

    best: tuple[float, tuple[Placement, ...]] | None = None
    generations = 0
    while time.perf_counter() < deadline and generations < (7 if n > 55 else 12 if n > 25 else 20):
        evaluated: list[tuple[float, tuple[float, ...], tuple[Placement, ...] | None]] = []
        for chromosome in population:
            if time.perf_counter() >= deadline:
                break
            fitness, placements = _chromosome_fitness(chromosome, items, vehicle)
            evaluated.append((fitness, chromosome, placements))
            if placements is not None and (best is None or fitness < best[0]):
                best = (fitness, placements)
        if not evaluated:
            break
        evaluated.sort(key=lambda row: row[0])
        elites = [row[1] for row in evaluated[:elite_count]]
        non_elites = [row[1] for row in evaluated[elite_count:]] or elites
        next_population = list(elites)
        for _ in range(mutant_count):
            next_population.append(tuple(rng.random() for _ in range(n * 2)))
        while len(next_population) < population_size:
            elite_parent = rng.choice(elites)
            other_parent = rng.choice(non_elites)
            child = tuple(
                elite_gene if rng.random() < elite_bias else other_gene
                for elite_gene, other_gene in zip(elite_parent, other_parent, strict=True)
            )
            next_population.append(child)
        population = next_population
        generations += 1

    if best is None:
        return None, (Diagnostic("BRKGA_FAILED", "Le BRKGA hybride n’a pas décodé de placement valide dans le temps imparti."),)
    return best[1], ()


def _pack_cp_sat_ortools(
    items: tuple[CargoItem, ...],
    vehicle: VehicleVersion,
    seed: int,
    deadline: float,
) -> tuple[Placement, ...] | None:
    try:
        from ortools.sat.python import cp_model  # type: ignore
    except ImportError:
        return None

    remaining = deadline - time.perf_counter()
    if remaining <= 0.05:
        return None
    model = cp_model.CpModel()
    n = len(items)
    x_vars = []
    y_vars = []
    width_vars = []
    length_vars = []
    rotation_vars = []
    end_y_vars = []

    for index, item in enumerate(items):
        env0 = build_envelope(item, 0)
        env90 = build_envelope(item, 90) if item.rotation_allowed and item.length_mm != item.width_mm else env0
        rotation = model.new_bool_var(f"rot_{index}") if env90 != env0 else None
        width = model.new_int_var(min(env0.envelope_width_mm, env90.envelope_width_mm), max(env0.envelope_width_mm, env90.envelope_width_mm), f"w_{index}")
        length = model.new_int_var(min(env0.envelope_length_mm, env90.envelope_length_mm), max(env0.envelope_length_mm, env90.envelope_length_mm), f"l_{index}")
        if rotation is None:
            model.add(width == env0.envelope_width_mm)
            model.add(length == env0.envelope_length_mm)
        else:
            model.add(width == env0.envelope_width_mm + (env90.envelope_width_mm - env0.envelope_width_mm) * rotation)
            model.add(length == env0.envelope_length_mm + (env90.envelope_length_mm - env0.envelope_length_mm) * rotation)
        x = model.new_int_var(0, vehicle.interior_width_mm, f"x_{index}")
        y = model.new_int_var(0, vehicle.interior_length_mm, f"y_{index}")
        end_y = model.new_int_var(0, vehicle.interior_length_mm, f"end_y_{index}")
        model.add(x + width <= vehicle.interior_width_mm)
        model.add(width <= vehicle.door_width_mm)
        model.add(y + length <= vehicle.interior_length_mm)
        model.add(end_y == y + length)
        if item.zone:
            zone = next((zone for zone in vehicle.zones if zone.id == item.zone), None)
            if zone is None:
                return None
            model.add(x >= zone.rect.x_mm)
            model.add(y >= zone.rect.y_mm)
            model.add(x + width <= zone.rect.x_mm + zone.rect.width_mm)
            model.add(y + length <= zone.rect.y_mm + zone.rect.length_mm)
        x_vars.append(x)
        y_vars.append(y)
        width_vars.append(width)
        length_vars.append(length)
        rotation_vars.append(rotation)
        end_y_vars.append(end_y)

    for i in range(n):
        for j in range(i + 1, n):
            gap = max(items[i].separation_mm, items[j].separation_mm)
            left = model.new_bool_var(f"left_{i}_{j}")
            right = model.new_bool_var(f"right_{i}_{j}")
            before = model.new_bool_var(f"before_{i}_{j}")
            after = model.new_bool_var(f"after_{i}_{j}")
            model.add(x_vars[i] + width_vars[i] + gap <= x_vars[j]).only_enforce_if(left)
            model.add(x_vars[j] + width_vars[j] + gap <= x_vars[i]).only_enforce_if(right)
            model.add(y_vars[i] + length_vars[i] + gap <= y_vars[j]).only_enforce_if(before)
            model.add(y_vars[j] + length_vars[j] + gap <= y_vars[i]).only_enforce_if(after)
            if items[i].delivery_order > items[j].delivery_order:
                model.add_bool_or([left, right, before])
            elif items[j].delivery_order > items[i].delivery_order:
                model.add_bool_or([left, right, after])
            else:
                model.add_bool_or([left, right, before, after])

    for i in range(n):
        for obstacle_index, obstacle in enumerate(vehicle.obstacles):
            left = model.new_bool_var(f"obs_left_{i}_{obstacle_index}")
            right = model.new_bool_var(f"obs_right_{i}_{obstacle_index}")
            before = model.new_bool_var(f"obs_before_{i}_{obstacle_index}")
            after = model.new_bool_var(f"obs_after_{i}_{obstacle_index}")
            model.add(x_vars[i] + width_vars[i] <= obstacle.x_mm).only_enforce_if(left)
            model.add(obstacle.x_mm + obstacle.width_mm <= x_vars[i]).only_enforce_if(right)
            model.add(y_vars[i] + length_vars[i] <= obstacle.y_mm).only_enforce_if(before)
            model.add(obstacle.y_mm + obstacle.length_mm <= y_vars[i]).only_enforce_if(after)
            model.add_bool_or([left, right, before, after])

    total_weight_g = sum(int(round(item.weight_kg * 1000)) for item in items)
    if len(vehicle.axles) == 2 and total_weight_g > 0:
        front, rear = vehicle.axles
        span = rear.position_mm - front.position_mm
        moment2_terms = []
        for index, item in enumerate(items):
            weight_g = int(round(item.weight_kg * 1000))
            moment2_terms.append(weight_g * (2 * y_vars[index] + length_vars[index] - 2 * front.position_mm))
        moment2 = sum(moment2_terms)
        rear_limit = int(round(rear.max_load_kg * 1000))
        front_limit = int(round(front.max_load_kg * 1000))
        model.add(moment2 <= 2 * span * rear_limit)
        model.add(moment2 >= 2 * span * (total_weight_g - front_limit))

    max_end = model.new_int_var(0, vehicle.interior_length_mm, "occupied_length")
    model.add_max_equality(max_end, end_y_vars)
    model.minimize(max_end)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.05, min(remaining, 5.0))
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = seed
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    placements = []
    for index, item in enumerate(items):
        orientation = 90 if rotation_vars[index] is not None and solver.value(rotation_vars[index]) else 0
        placements.append(_make_placement(item, orientation, solver.value(x_vars[index]), solver.value(y_vars[index])))
    return tuple(placements)


def _constraint_backtracking(
    items: tuple[CargoItem, ...],
    vehicle: VehicleVersion,
    seed: int,
    deadline: float,
) -> tuple[Placement, ...] | None:
    rng = random.Random(seed)
    ordered = sorted(items, key=lambda item: (-item.delivery_order, -(item.length_mm * item.width_mm), -item.weight_kg, item.input_index))
    item_map = {item.id: item for item in items}
    best: tuple[Placement, ...] | None = None
    best_length = vehicle.interior_length_mm + 1

    def search(index: int, placed: list[Placement]) -> None:
        nonlocal best, best_length
        if time.perf_counter() >= deadline:
            return
        if index == len(ordered):
            length = _occupied_length(placed)
            if length < best_length:
                best = tuple(placed)
                best_length = length
            return
        item = ordered[index]
        candidates = []
        for orientation in _orientations(item):
            envelope = build_envelope(item, orientation)
            strategy = PackingStrategy("constraint-search", "area", "front-left")
            points = _ordered_candidates(_candidate_points(placed, vehicle, item_map), envelope.envelope_width_mm, vehicle, strategy)
            for x_mm, y_mm in points:
                candidate = _make_placement(item, orientation, x_mm, y_mm)
                if not _candidate_is_valid(candidate, placed, item_map, vehicle):
                    continue
                projected = max(_occupied_length(placed), y_mm + candidate.envelope_length_mm)
                if projected > best_length:
                    continue
                candidates.append((projected, y_mm, x_mm, rng.random(), candidate))
        candidates.sort(key=lambda row: row[:-1])
        branch_limit = 20 if len(items) <= 18 else 8
        for *_, candidate in candidates[:branch_limit]:
            placed.append(candidate)
            search(index + 1, placed)
            placed.pop()
            if time.perf_counter() >= deadline:
                return

    search(0, [])
    return best


def pack_cp_sat(
    items: tuple[CargoItem, ...],
    vehicle: VehicleVersion,
    seed: int,
    deadline: float,
) -> tuple[tuple[Placement, ...] | None, tuple[Diagnostic, ...]]:
    placements = _pack_cp_sat_ortools(items, vehicle, seed, deadline)
    if placements is None and time.perf_counter() < deadline:
        placements = _constraint_backtracking(items, vehicle, seed, deadline)
    if placements is None:
        return None, (Diagnostic("CP_SAT_FAILED", "Le résolveur par contraintes n’a pas trouvé de placement valide dans le temps imparti."),)
    return placements, ()


PACKERS: dict[str, Callable[[tuple[CargoItem, ...], VehicleVersion, int, float], tuple[tuple[Placement, ...] | None, tuple[Diagnostic, ...]]]] = {
    "extreme_points": pack_extreme_points,
    "skyline_blf": pack_skyline,
    "block_layers": pack_block_layers,
    "brkga_hybrid": pack_brkga,
    "cp_sat": pack_cp_sat,
}


def pack_with_method(
    method: OptimizationMethod,
    items: tuple[CargoItem, ...],
    vehicle: VehicleVersion,
    seed: int,
    deadline: float,
) -> tuple[tuple[Placement, ...] | None, tuple[Diagnostic, ...]]:
    return PACKERS[method.code](items, vehicle, seed, deadline)
