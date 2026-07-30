from __future__ import annotations

from dataclasses import replace

from .domain import Solution


def solution_key(solution: Solution) -> tuple[float, ...]:
    return (
        float(solution.vehicle_count),
        round(solution.occupied_length_m, 6),
        round(solution.total_linear_meters, 6),
        round(solution.axle_penalty, 9),
        round(solution.balance_penalty, 9),
    )


def placement_signature(solution: Solution) -> tuple:
    signature = []
    for vehicle_index, plan in enumerate(solution.vehicle_plans):
        for p in plan.placements:
            signature.append((vehicle_index, p.source_id, p.orientation_deg, p.x_mm, p.y_mm))
    return tuple(sorted(signature))


def diversity_distance(a: Solution, b: Solution) -> float:
    pa = sorted((vehicle_index, p.source_id, p.x_mm, p.y_mm, p.orientation_deg)
                for vehicle_index, plan in enumerate(a.vehicle_plans) for p in plan.placements)
    pb = sorted((vehicle_index, p.source_id, p.x_mm, p.y_mm, p.orientation_deg)
                for vehicle_index, plan in enumerate(b.vehicle_plans) for p in plan.placements)
    if len(pa) != len(pb):
        return 1.0
    changed = 0.0
    for left, right in zip(pa, pb, strict=True):
        va, source_a, xa, ya, oa = left
        vb, source_b, xb, yb, ob = right
        if source_a != source_b or va != vb:
            changed += 1.0
        elif oa != ob:
            changed += 0.7
        elif abs(xa - xb) + abs(ya - yb) >= 150:
            changed += 0.35
    return changed / max(1, len(pa))


def rank_and_select(solutions: list[Solution], count: int) -> tuple[Solution, ...]:
    unique: list[Solution] = []
    seen = set()
    for solution in sorted(solutions, key=solution_key):
        signature = placement_signature(solution)
        if signature in seen:
            continue
        seen.add(signature)
        unique.append(solution)
    selected: list[Solution] = []
    for solution in unique:
        if not selected or all(diversity_distance(solution, existing) >= 0.08 for existing in selected):
            selected.append(solution)
        if len(selected) == count:
            break
    if len(selected) < count:
        for solution in unique:
            if solution not in selected:
                selected.append(solution)
            if len(selected) == count:
                break
    return tuple(replace(solution, rank=index + 1) for index, solution in enumerate(selected))
