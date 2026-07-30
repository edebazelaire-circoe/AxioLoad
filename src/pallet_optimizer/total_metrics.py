from __future__ import annotations

from typing import Any, Sequence

from . import total_optimization as total_module
from .total_route_sequence import best_lifo_wave_plan

_INSTALLED = False
_ORIGINAL_BUILD_SOLUTION = total_module._build_solution


def _same_point(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return abs(float(left.get("lat") or 0)-float(right.get("lat") or 0)) < 1e-7 and abs(float(left.get("lon") or 0)-float(right.get("lon") or 0)) < 1e-7


def _merge_departure_pickup(stops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(stops)<2 or stops[0].get("type")!="start" or stops[1].get("type")!="pickup" or not _same_point(stops[0],stops[1]): return stops
    start, pickup = dict(stops[0]), stops[1]; start["type"] = "pickup"
    start["operations"] = [*(start.get("operations") or [{"type":"start"}]),*(pickup.get("operations") or [{"type":"pickup","client":pickup.get("client","")}])]
    start["clients"] = list(dict.fromkeys(pickup.get("clients") or [pickup.get("client")]))
    start["client"] = ", ".join(value for value in start["clients"] if value)
    for key in ("quantity","unit_type","weight_kg","load_after_kg"): start[key] = pickup.get(key)
    merged = [start,*stops[2:]]
    for sequence, stop in enumerate(merged,1): stop["sequence"] = sequence
    return merged


def _empty_metrics(problem: Any, route: Sequence[int]) -> tuple[float,float,float]:
    plan = best_lifo_wave_plan(problem,route); indices = plan.physical_indices; empty_m = 0.0; load = 0.0
    for origin,target in zip(indices,indices[1:]):
        distance = float(problem.distance_matrix.distances_m[origin][target])
        if load <= 1e-9: empty_m += distance
        if target == 0: continue
        client = problem.clients[(target-1)//2]
        if target % 2 == 1: load += client.weight_kg
        else: load = max(0.0,load-client.weight_kg)
    total_m = float(plan.distance_m); empty_km = empty_m/1000; total_km = total_m/1000
    return empty_km,max(0.0,total_km-empty_km),(empty_m/total_m*100 if total_m>0 else 0.0)


def _build_solution(problem: Any,routes: Sequence[Sequence[int]],oracle: Any,methods: Sequence[str],*,code: str,name: str,
                    description: str,iterations: int,elapsed: float) -> dict[str, Any]:
    solution = _ORIGINAL_BUILD_SOLUTION(problem,routes,oracle,methods,code=code,name=name,description=description,iterations=iterations,elapsed=elapsed)
    total_empty = total_loaded = 0.0
    for route_indices, route_result in zip(routes,solution.get("routes") or [],strict=False):
        empty_km,loaded_km,percent = _empty_metrics(problem,route_indices)
        route_result["empty_distance_km"] = empty_km; route_result["loaded_distance_km"] = loaded_km; route_result["empty_distance_percent"] = percent
        route_result["stops"] = _merge_departure_pickup(list(route_result.get("stops") or []))
        route_result["vehicle_dimensions"] = {"interior_length_mm":problem.vehicle.interior_length_mm,"interior_width_mm":problem.vehicle.interior_width_mm,
            "interior_height_mm":problem.vehicle.interior_height_mm,"exterior_length_mm":problem.vehicle.exterior_length_mm,
            "exterior_width_mm":problem.vehicle.exterior_width_mm,"exterior_height_mm":problem.vehicle.exterior_height_mm}
        total_empty += empty_km; total_loaded += loaded_km
    total = total_empty+total_loaded
    solution["empty_distance_km"] = total_empty; solution["loaded_distance_km"] = total_loaded
    solution["empty_distance_percent"] = total_empty/total*100 if total>0 else 0.0
    return solution


def install_total_metrics() -> None:
    global _INSTALLED
    if _INSTALLED: return
    total_module._build_solution = _build_solution; _INSTALLED = True
