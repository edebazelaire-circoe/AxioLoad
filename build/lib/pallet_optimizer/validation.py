from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .domain import CargoItem, Diagnostic, Placement, Severity, VehicleVersion, WeightMetrics


def rectangles_overlap(a: Placement, b: Placement, extra_gap_mm: int = 0) -> bool:
    return not (
        a.x_mm + a.envelope_width_mm + extra_gap_mm <= b.x_mm
        or b.x_mm + b.envelope_width_mm + extra_gap_mm <= a.x_mm
        or a.y_mm + a.envelope_length_mm + extra_gap_mm <= b.y_mm
        or b.y_mm + b.envelope_length_mm + extra_gap_mm <= a.y_mm
    )


def placement_overlaps_rect(p: Placement, x: int, y: int, width: int, length: int) -> bool:
    return not (
        p.x_mm + p.envelope_width_mm <= x
        or x + width <= p.x_mm
        or p.y_mm + p.envelope_length_mm <= y
        or y + length <= p.y_mm
    )


def validate_geometry(vehicle: VehicleVersion, placements: tuple[Placement, ...], items: dict[str, CargoItem]) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    for p in placements:
        item = items[p.item_id]
        if p.z_mm != 0:
            diagnostics.append(Diagnostic("NOT_ON_FLOOR", f"{p.item_id} ne repose pas sur le plancher", field_path=p.item_id))
        if p.x_mm < 0 or p.y_mm < 0 or p.x_mm + p.envelope_width_mm > vehicle.interior_width_mm or p.y_mm + p.envelope_length_mm > vehicle.interior_length_mm:
            diagnostics.append(Diagnostic("OUT_OF_BOUNDS", f"{p.item_id} dépasse les limites du plancher du véhicule", field_path=p.item_id))
        if p.actual_height_mm + item.margins.top_mm > vehicle.interior_height_mm:
            diagnostics.append(Diagnostic("HEIGHT_EXCEEDED", f"{p.item_id} dépasse la hauteur intérieure", field_path=p.item_id))
        if p.envelope_width_mm > vehicle.door_width_mm or p.actual_height_mm + item.margins.top_mm > vehicle.door_height_mm:
            diagnostics.append(Diagnostic("OPENING_TOO_SMALL", f"{p.item_id} ne peut pas franchir l’ouverture arrière", field_path=p.item_id))
        for obstacle in vehicle.obstacles:
            if placement_overlaps_rect(p, obstacle.x_mm, obstacle.y_mm, obstacle.width_mm, obstacle.length_mm):
                diagnostics.append(Diagnostic("OBSTACLE_COLLISION", f"{p.item_id} entre en collision avec {obstacle.id}", field_path=p.item_id,
                                              details={"obstacle": obstacle.id}))
        if item.zone:
            zone = next((z for z in vehicle.zones if z.id == item.zone), None)
            if zone is None:
                diagnostics.append(Diagnostic("UNKNOWN_ZONE", f"Zone {item.zone} n’est pas définie sur {vehicle.version_id}", field_path=p.item_id))
            elif not (p.x_mm >= zone.rect.x_mm and p.y_mm >= zone.rect.y_mm
                      and p.x_mm + p.envelope_width_mm <= zone.rect.x_mm + zone.rect.width_mm
                      and p.y_mm + p.envelope_length_mm <= zone.rect.y_mm + zone.rect.length_mm):
                diagnostics.append(Diagnostic("ZONE_VIOLATION", f"{p.item_id} se trouve hors de la zone imposée {item.zone}", field_path=p.item_id))
    for i, a in enumerate(placements):
        for b in placements[i + 1:]:
            gap = max(items[a.item_id].separation_mm, items[b.item_id].separation_mm)
            if rectangles_overlap(a, b, gap):
                diagnostics.append(Diagnostic("ITEM_COLLISION", f"{a.item_id} chevauche ou ne respecte pas l’écart avec {b.item_id}",
                                              details={"items": [a.item_id, b.item_id], "gap_mm": gap}))
    return tuple(diagnostics)


def calculate_weight(vehicle: VehicleVersion, placements: tuple[Placement, ...]) -> tuple[WeightMetrics, tuple[Diagnostic, ...], float]:
    total = sum(p.weight_kg for p in placements)
    cog = sum(p.weight_kg * (p.y_mm + p.envelope_length_mm / 2) for p in placements) / total if total else 0.0
    diagnostics: list[Diagnostic] = []
    if total > vehicle.payload_kg + 1e-9:
        diagnostics.append(Diagnostic("PAYLOAD_EXCEEDED", f"Charge utile dépassée de {total - vehicle.payload_kg:.1f} kg",
                                      details={"total_kg": total, "limit_kg": vehicle.payload_kg}))
    axle_loads: list[tuple[str, float]] = []
    axle_penalty = 0.0
    if len(vehicle.axles) == 2 and total:
        front, rear = vehicle.axles
        span = rear.position_mm - front.position_mm
        rear_load = sum(p.weight_kg * ((p.y_mm + p.envelope_length_mm / 2) - front.position_mm) / span for p in placements)
        front_load = total - rear_load
        axle_loads = [(front.id, front_load), (rear.id, rear_load)]
        for axle, load in zip(vehicle.axles, (front_load, rear_load), strict=True):
            if load < -1e-6:
                diagnostics.append(Diagnostic("NEGATIVE_AXLE_REACTION", f"Le centre de charge sort du modèle simplifié d’appuis pour {axle.id}",
                                              severity=Severity.WARNING, details={"load_kg": load}))
            if load > axle.max_load_kg + 1e-9:
                diagnostics.append(Diagnostic("AXLE_OVERLOAD", f"{axle.id} dépassé de {load - axle.max_load_kg:.1f} kg",
                                              details={"axle": axle.id, "load_kg": load, "limit_kg": axle.max_load_kg}))
            axle_penalty += max(0.0, load / axle.max_load_kg - 0.85) ** 2
    return WeightMetrics(total, cog, tuple(axle_loads)), tuple(diagnostics), axle_penalty


def validate_delivery_access(placements: tuple[Placement, ...]) -> tuple[Diagnostic, ...]:
    """Rear door at y=0. Larger delivery_order means unloaded earlier."""
    diagnostics: list[Diagnostic] = []
    for a in placements:
        for b in placements:
            if a.item_id == b.item_id or a.delivery_order <= b.delivery_order:
                continue
            x_overlap = not (a.x_mm + a.envelope_width_mm <= b.x_mm or b.x_mm + b.envelope_width_mm <= a.x_mm)
            if x_overlap and a.y_mm > b.y_mm:
                diagnostics.append(Diagnostic(
                    "LIFO_BLOCKED",
                    f"{a.item_id} doit être déchargé avant {b.item_id} mais se trouve plus profondément dans le même couloir d’accès",
                    details={"earlier": a.item_id, "blocking": b.item_id},
                ))
    return tuple(diagnostics)


def validate_compatibility(placements_by_vehicle: tuple[tuple[Placement, ...], ...], items: dict[str, CargoItem]) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    vehicle_of: dict[str, int] = {}
    for index, placements in enumerate(placements_by_vehicle):
        for p in placements:
            vehicle_of[p.item_id] = index
        for i, a in enumerate(placements):
            item_a = items[a.item_id]
            for b in placements[i + 1:]:
                item_b = items[b.item_id]
                conflict = set(item_a.incompatible_tags) & set(item_b.compatibility_tags)
                conflict |= set(item_b.incompatible_tags) & set(item_a.compatibility_tags)
                if conflict:
                    diagnostics.append(Diagnostic("INCOMPATIBLE_CARGO", f"{a.item_id} and {b.item_id} sont incompatibles",
                                                  details={"tags": sorted(conflict)}))
                if item_a.separate_group and item_a.separate_group == item_b.separate_group:
                    diagnostics.append(Diagnostic("SEPARATE_GROUP_SHARED", f"Group {item_a.separate_group} doit être réparti sur des véhicules distincts"))
    groups: dict[str, list[str]] = defaultdict(list)
    for item in items.values():
        if item.keep_together_group:
            groups[item.keep_together_group].append(item.id)
    for group, item_ids in groups.items():
        assigned = {vehicle_of.get(item_id) for item_id in item_ids}
        if len(assigned) > 1:
            diagnostics.append(Diagnostic("KEEP_TOGETHER_SPLIT", f"Group {group} est réparti sur plusieurs véhicules", details={"items": item_ids}))
    return tuple(diagnostics)


def has_errors(diagnostics: tuple[Diagnostic, ...]) -> bool:
    return any(d.severity == Severity.ERROR for d in diagnostics)
