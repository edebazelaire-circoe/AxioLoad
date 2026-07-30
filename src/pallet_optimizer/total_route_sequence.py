from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from . import total_optimization as total_engine
from .route_optimization import Point


@dataclass(frozen=True, slots=True)
class LifoWavePlan:
    waves: tuple[tuple[int, ...], ...]
    physical_indices: tuple[int, ...]
    distance_m: float
    duration_s: float


_SEQUENCE_CACHE: dict[tuple[int, tuple[int, ...]], LifoWavePlan] = {}
_INSTALLED = False


def clear_sequence_cache() -> None:
    _SEQUENCE_CACHE.clear()


def _path_metric(matrix: Sequence[Sequence[float]], origin: int, nodes: Sequence[int]) -> float:
    if not nodes:
        return 0.0
    total = float(matrix[origin][nodes[0]])
    total += sum(float(matrix[left][right]) for left, right in zip(nodes, nodes[1:]))
    return total


def _wave_nodes(problem: Any, delivery_order: Sequence[int], start: int, end: int) -> list[int]:
    pickups = [problem.pickup_index(delivery_order[index]) for index in range(end - 1, start - 1, -1)]
    deliveries = [problem.delivery_index(delivery_order[index]) for index in range(start, end)]
    return pickups + deliveries


def best_lifo_wave_plan(problem: Any, delivery_order: Sequence[int]) -> LifoWavePlan:
    """
    Split a fixed delivery order into consecutive LIFO loading waves.

    A wave loads its clients in reverse delivery order, then delivers them in the
    requested order. Consecutive waves allow the truck to deliver part of its load,
    visit another loading point, and continue without violating pickup precedence.
    """
    order = tuple(int(index) for index in delivery_order)
    cache_key = (id(problem), order)
    cached = _SEQUENCE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    if not order:
        indices = (0, 0) if problem.return_to_depot else (0,)
        plan = LifoWavePlan((), indices, 0.0, 0.0)
        _SEQUENCE_CACHE[cache_key] = plan
        return plan

    distances = problem.distance_matrix.distances_m
    durations = problem.distance_matrix.durations_s
    size = len(order)
    # Each entry stores: (distance, wave_count, duration, previous_boundary).
    best: list[tuple[float, int, float, int] | None] = [None] * (size + 1)
    best[0] = (0.0, 0, 0.0, -1)

    for end in range(1, size + 1):
        chosen: tuple[float, int, float, int] | None = None
        for start in range(end):
            previous = best[start]
            if previous is None:
                continue
            origin = 0 if start == 0 else problem.delivery_index(order[start - 1])
            nodes = _wave_nodes(problem, order, start, end)
            distance = previous[0] + _path_metric(distances, origin, nodes)
            duration = previous[2] + _path_metric(durations, origin, nodes)
            candidate = (distance, previous[1] + 1, duration, start)
            # Distance is the primary criterion. Fewer loading waves break ties.
            if chosen is None or (candidate[0], candidate[1], candidate[2]) < (
                chosen[0],
                chosen[1],
                chosen[2],
            ):
                chosen = candidate
        best[end] = chosen

    final = best[size]
    if final is None:
        raise RuntimeError("Aucune séquence d’arrêts LIFO n’a pu être construite.")

    boundaries: list[tuple[int, int]] = []
    end = size
    while end > 0:
        entry = best[end]
        if entry is None:
            raise RuntimeError("Séquence LIFO incomplète.")
        start = entry[3]
        boundaries.append((start, end))
        end = start
    boundaries.reverse()

    waves = tuple(tuple(order[start:end]) for start, end in boundaries)
    physical = [0]
    for start, end in boundaries:
        physical.extend(_wave_nodes(problem, order, start, end))
    distance = final[0]
    duration = final[2]
    if problem.return_to_depot:
        last = physical[-1]
        distance += float(distances[last][0])
        duration += float(durations[last][0])
        physical.append(0)

    plan = LifoWavePlan(waves, tuple(physical), distance, duration)
    _SEQUENCE_CACHE[cache_key] = plan
    return plan


def _point_for_index(problem: Any, physical_index: int) -> Point:
    if physical_index == 0:
        return problem.depot
    client_index = (physical_index - 1) // 2
    client = problem.clients[client_index]
    return client.pickup if physical_index % 2 == 1 else client.delivery


def _same_point(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return abs(float(left["lat"]) - float(right["lat"])) < 1e-7 and abs(
        float(left["lon"]) - float(right["lon"])
    ) < 1e-7


def _operation_stop(problem: Any, physical_index: int, load_kg: float) -> tuple[dict[str, Any], float]:
    client_index = (physical_index - 1) // 2
    client = problem.clients[client_index]
    is_pickup = physical_index % 2 == 1
    operation_type = "pickup" if is_pickup else "delivery"
    point = client.pickup if is_pickup else client.delivery
    updated_load = load_kg + client.weight_kg if is_pickup else max(0.0, load_kg - client.weight_kg)
    operation = {
        "type": operation_type,
        "client_id": client.id,
        "client": client.client,
        "quantity": client.quantity,
        "unit_type": client.unit_type,
        "weight_kg": client.weight_kg,
    }
    return (
        {
            "type": operation_type,
            "label": point.label,
            "lat": point.lat,
            "lon": point.lon,
            "client_id": client.id,
            "client": client.client,
            "clients": [client.client],
            "quantity": client.quantity,
            "unit_type": client.unit_type,
            "weight_kg": client.weight_kg,
            "operations": [operation],
            "load_after_kg": updated_load,
        },
        updated_load,
    )


def build_lifo_stops(problem: Any, delivery_order: Sequence[int]) -> list[dict[str, Any]]:
    plan = best_lifo_wave_plan(problem, delivery_order)
    stops: list[dict[str, Any]] = [
        {
            "sequence": 1,
            "type": "start",
            "client": "",
            "clients": [],
            "label": problem.depot.label,
            "lat": problem.depot.lat,
            "lon": problem.depot.lon,
            "operations": [{"type": "start"}],
            "load_after_kg": 0.0,
        }
    ]
    load_kg = 0.0
    for physical_index in plan.physical_indices[1:]:
        if physical_index == 0:
            stops.append(
                {
                    "type": "return",
                    "client": "",
                    "clients": [],
                    "label": problem.depot.label,
                    "lat": problem.depot.lat,
                    "lon": problem.depot.lon,
                    "operations": [{"type": "return"}],
                    "load_after_kg": load_kg,
                }
            )
            continue

        candidate, load_kg = _operation_stop(problem, physical_index, load_kg)
        previous = stops[-1]
        if previous.get("type") == candidate["type"] and _same_point(previous, candidate):
            previous["operations"].extend(candidate["operations"])
            previous["clients"].extend(candidate["clients"])
            previous["client"] = ", ".join(dict.fromkeys(previous["clients"]))
            previous["quantity"] = int(previous.get("quantity") or 0) + int(candidate["quantity"])
            previous["weight_kg"] = float(previous.get("weight_kg") or 0.0) + float(candidate["weight_kg"])
            previous["unit_type"] = (
                previous.get("unit_type")
                if previous.get("unit_type") == candidate.get("unit_type")
                else "unités mixtes"
            )
            previous["load_after_kg"] = load_kg
        else:
            stops.append(candidate)

    for sequence, stop in enumerate(stops, 1):
        stop["sequence"] = sequence
    return stops


def _patched_route_physical_indices(problem: Any, delivery_order: Sequence[int]) -> list[int]:
    return list(best_lifo_wave_plan(problem, delivery_order).physical_indices)


def _patched_route_points(problem: Any, delivery_order: Sequence[int]) -> list[Point]:
    return [
        _point_for_index(problem, physical_index)
        for physical_index in best_lifo_wave_plan(problem, delivery_order).physical_indices
    ]


def install_wave_routing() -> None:
    """Install the wave-aware route metrics before ALNS and genetic optimization run."""
    global _INSTALLED
    if _INSTALLED:
        return
    total_engine.TotalProblem.route_physical_indices = _patched_route_physical_indices
    total_engine.TotalProblem.route_points = _patched_route_points
    total_engine._stops = build_lifo_stops
    _INSTALLED = True
