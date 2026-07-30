from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace
from typing import Iterable

from .domain import CargoItem, Diagnostic, Placement, VehicleVersion
from .envelopes import build_envelope
from .validation import placement_overlaps_rect, rectangles_overlap


@dataclass(frozen=True, slots=True)
class PackingStrategy:
    name: str
    item_tiebreak: str
    candidate_order: str
    prefer_rotated: bool = False
    jitter: int = 0
    algorithm: str = "extreme"
    score: str = "bottom-left"


# The portfolio deliberately mixes MaxRects and extreme-point/bottom-left methods.
# A single heuristic can miss feasible packings; a bounded portfolio is far more robust.
STRATEGIES: tuple[PackingStrategy, ...] = (
    PackingStrategy("maxrects-short-side", "area", "front-left", algorithm="maxrects", score="short-side"),
    PackingStrategy("maxrects-area-fit", "width", "front-left", algorithm="maxrects", score="area-fit"),
    PackingStrategy("maxrects-bottom-left", "length", "front-left", algorithm="maxrects", score="bottom-left"),
    PackingStrategy("maxrects-balanced", "weight", "center", algorithm="maxrects", score="balanced"),
    PackingStrategy("compact-front-left", "area", "front-left"),
    PackingStrategy("compact-front-right", "width", "front-right", True),
    PackingStrategy("narrow-lanes", "length", "lane-center"),
    PackingStrategy("depth-columns", "area", "column"),
)


@dataclass(frozen=True, slots=True)
class FreeRect:
    x_mm: int
    y_mm: int
    width_mm: int
    length_mm: int

    @property
    def right_mm(self) -> int:
        return self.x_mm + self.width_mm

    @property
    def rear_mm(self) -> int:
        return self.y_mm + self.length_mm


def _sort_items(items: Iterable[CargoItem], strategy: PackingStrategy, rng: random.Random) -> list[CargoItem]:
    def secondary(item: CargoItem) -> tuple[float, ...]:
        if strategy.item_tiebreak == "width":
            return (-max(item.width_mm, item.length_mm), -min(item.width_mm, item.length_mm), -item.weight_kg)
        if strategy.item_tiebreak == "length":
            return (-item.length_mm, -item.width_mm, -item.weight_kg)
        if strategy.item_tiebreak == "weight":
            return (-item.weight_kg, -(item.length_mm * item.width_mm), -item.length_mm)
        return (-(item.length_mm * item.width_mm), -max(item.length_mm, item.width_mm), -item.weight_kg)

    decorated = []
    for item in items:
        jitter = rng.random() if strategy.jitter else 0.0
        decorated.append(((-item.delivery_order, *secondary(item), jitter, item.input_index, item.id), item))
    decorated.sort(key=lambda pair: pair[0])
    return [item for _, item in decorated]


def _candidate_points(placements: list[Placement], vehicle: VehicleVersion, item_map: dict[str, CargoItem] | None = None) -> list[tuple[int, int]]:
    xs = {0}
    ys = {0}
    for p in placements:
        gap = item_map[p.item_id].separation_mm if item_map else 0
        xs.add(p.x_mm + p.envelope_width_mm + gap)
        ys.add(p.y_mm + p.envelope_length_mm + gap)
        xs.add(max(0, p.x_mm - gap))
        ys.add(max(0, p.y_mm - gap))
    for obstacle in vehicle.obstacles:
        xs.add(obstacle.x_mm + obstacle.width_mm)
        ys.add(obstacle.y_mm + obstacle.length_mm)
    for zone in vehicle.zones:
        xs.add(zone.rect.x_mm)
        xs.add(zone.rect.x_mm + zone.rect.width_mm)
        ys.add(zone.rect.y_mm)
        ys.add(zone.rect.y_mm + zone.rect.length_mm)
    return [(x, y) for x in xs for y in ys if x <= vehicle.interior_width_mm and y <= vehicle.interior_length_mm]


def _ordered_candidates(points: list[tuple[int, int]], envelope_width: int, vehicle: VehicleVersion,
                        strategy: PackingStrategy) -> list[tuple[int, int]]:
    center = vehicle.interior_width_mm / 2
    ys = {y for _, y in points}
    augmented = set(points)
    right_x = max(0, vehicle.interior_width_mm - envelope_width)
    center_x = max(0, round(center - envelope_width / 2))
    for y in ys:
        augmented.add((right_x, y))
        augmented.add((center_x, y))
    points = list(augmented)
    if strategy.candidate_order == "front-right":
        key = lambda p: (p[1], -p[0])
    elif strategy.candidate_order == "center":
        key = lambda p: (p[1], abs((p[0] + envelope_width / 2) - center), p[0])
    elif strategy.candidate_order == "column":
        key = lambda p: (p[0], p[1])
    elif strategy.candidate_order == "lane-center":
        key = lambda p: (p[1], abs((p[0] + envelope_width / 2) - center), -p[0])
    else:
        key = lambda p: (p[1], p[0])
    return sorted(points, key=key)


def _candidate_is_valid(candidate: Placement, placed: list[Placement], item_map: dict[str, CargoItem],
                        vehicle: VehicleVersion) -> bool:
    item = item_map[candidate.item_id]
    if candidate.x_mm < 0 or candidate.y_mm < 0:
        return False
    if candidate.x_mm + candidate.envelope_width_mm > vehicle.interior_width_mm:
        return False
    if candidate.y_mm + candidate.envelope_length_mm > vehicle.interior_length_mm:
        return False
    if candidate.actual_height_mm + item.margins.top_mm > vehicle.interior_height_mm:
        return False
    if candidate.envelope_width_mm > vehicle.door_width_mm or candidate.actual_height_mm + item.margins.top_mm > vehicle.door_height_mm:
        return False
    for obstacle in vehicle.obstacles:
        if placement_overlaps_rect(candidate, obstacle.x_mm, obstacle.y_mm, obstacle.width_mm, obstacle.length_mm):
            return False
    if item.zone:
        zone = next((z for z in vehicle.zones if z.id == item.zone), None)
        if zone is None:
            return False
        if not (candidate.x_mm >= zone.rect.x_mm and candidate.y_mm >= zone.rect.y_mm
                and candidate.x_mm + candidate.envelope_width_mm <= zone.rect.x_mm + zone.rect.width_mm
                and candidate.y_mm + candidate.envelope_length_mm <= zone.rect.y_mm + zone.rect.length_mm):
            return False
    for other in placed:
        gap = max(item.separation_mm, item_map[other.item_id].separation_mm)
        if rectangles_overlap(candidate, other, gap):
            return False
        # Rear door is y=0. Higher delivery order must remain no deeper than lower order
        # whenever both objects share an access corridor.
        x_overlap = not (
            candidate.x_mm + candidate.envelope_width_mm <= other.x_mm
            or other.x_mm + other.envelope_width_mm <= candidate.x_mm
        )
        if x_overlap:
            if candidate.delivery_order > other.delivery_order and candidate.y_mm > other.y_mm:
                return False
            if other.delivery_order > candidate.delivery_order and other.y_mm > candidate.y_mm:
                return False
    return True


def _make_placement(item: CargoItem, orientation: int, x: int, y: int) -> Placement:
    envelope = build_envelope(item, orientation)
    return Placement(
        item_id=item.id,
        source_id=item.source_id,
        destination=item.destination,
        delivery_order=item.delivery_order,
        x_mm=x,
        y_mm=y,
        z_mm=0,
        orientation_deg=orientation,
        actual_length_mm=envelope.actual_length_mm,
        actual_width_mm=envelope.actual_width_mm,
        actual_height_mm=envelope.actual_height_mm,
        envelope_length_mm=envelope.envelope_length_mm,
        envelope_width_mm=envelope.envelope_width_mm,
        weight_kg=item.weight_kg,
    )


def _pack_extreme_points(items: tuple[CargoItem, ...], vehicle: VehicleVersion, strategy: PackingStrategy,
                         seed: int) -> tuple[tuple[Placement, ...] | None, tuple[Diagnostic, ...]]:
    rng = random.Random(seed)
    item_map = {item.id: item for item in items}
    placed: list[Placement] = []
    for item in _sort_items(items, strategy, rng):
        orientations = [0]
        if item.rotation_allowed and item.length_mm != item.width_mm:
            orientations.append(90)
        if strategy.prefer_rotated:
            orientations.reverse()
        selected: Placement | None = None
        for orientation in orientations:
            envelope = build_envelope(item, orientation)
            points = _ordered_candidates(
                _candidate_points(placed, vehicle, item_map),
                envelope.envelope_width_mm,
                vehicle,
                strategy,
            )
            for x, y in points:
                candidate = _make_placement(item, orientation, x, y)
                if _candidate_is_valid(candidate, placed, item_map, vehicle):
                    selected = candidate
                    break
            if selected:
                break
        if selected is None:
            return None, (Diagnostic(
                "NO_PLACEMENT",
                f"Le moteur n’a pas trouvé de position pour {item.id} dans {vehicle.name} avec la méthode {strategy.name}.",
                field_path=item.id,
                details={"strategy": strategy.name},
            ),)
        placed.append(selected)
    return tuple(placed), ()


def _rectangles_intersect(a: FreeRect, b: FreeRect) -> bool:
    return not (a.right_mm <= b.x_mm or b.right_mm <= a.x_mm or a.rear_mm <= b.y_mm or b.rear_mm <= a.y_mm)


def _split_free_rectangle(free: FreeRect, used: FreeRect) -> list[FreeRect]:
    if not _rectangles_intersect(free, used):
        return [free]
    output: list[FreeRect] = []
    if used.x_mm > free.x_mm:
        output.append(FreeRect(free.x_mm, free.y_mm, used.x_mm - free.x_mm, free.length_mm))
    if used.right_mm < free.right_mm:
        output.append(FreeRect(used.right_mm, free.y_mm, free.right_mm - used.right_mm, free.length_mm))
    if used.y_mm > free.y_mm:
        output.append(FreeRect(free.x_mm, free.y_mm, free.width_mm, used.y_mm - free.y_mm))
    if used.rear_mm < free.rear_mm:
        output.append(FreeRect(free.x_mm, used.rear_mm, free.width_mm, free.rear_mm - used.rear_mm))
    return [r for r in output if r.width_mm > 0 and r.length_mm > 0]


def _contains(outer: FreeRect, inner: FreeRect) -> bool:
    return (
        inner.x_mm >= outer.x_mm and inner.y_mm >= outer.y_mm
        and inner.right_mm <= outer.right_mm and inner.rear_mm <= outer.rear_mm
    )


def _prune_free_rectangles(rectangles: list[FreeRect]) -> list[FreeRect]:
    unique = list(dict.fromkeys(rectangles))
    output: list[FreeRect] = []
    for i, rect in enumerate(unique):
        if any(i != j and _contains(other, rect) for j, other in enumerate(unique)):
            continue
        output.append(rect)
    return output


def _subtract_used(free_rectangles: list[FreeRect], used: FreeRect) -> list[FreeRect]:
    split: list[FreeRect] = []
    for free in free_rectangles:
        split.extend(_split_free_rectangle(free, used))
    return _prune_free_rectangles(split)


def _maxrect_score(candidate: Placement, free: FreeRect, vehicle: VehicleVersion, strategy: PackingStrategy,
                   placed: list[Placement]) -> tuple[float, ...]:
    dw = free.width_mm - candidate.envelope_width_mm
    dl = free.length_mm - candidate.envelope_length_mm
    short_side = min(dw, dl)
    long_side = max(dw, dl)
    area_fit = free.width_mm * free.length_mm - candidate.envelope_width_mm * candidate.envelope_length_mm
    occupied_depth = max([candidate.y_mm + candidate.envelope_length_mm, *[p.y_mm + p.envelope_length_mm for p in placed]])
    center_error = abs((candidate.x_mm + candidate.envelope_width_mm / 2) - vehicle.interior_width_mm / 2)
    if strategy.score == "area-fit":
        return (area_fit, short_side, occupied_depth, candidate.y_mm, candidate.x_mm)
    if strategy.score == "bottom-left":
        return (occupied_depth, candidate.y_mm + candidate.envelope_length_mm, candidate.x_mm, short_side)
    if strategy.score == "balanced":
        return (occupied_depth, center_error, area_fit, candidate.y_mm, candidate.x_mm)
    return (short_side, long_side, occupied_depth, candidate.y_mm, candidate.x_mm)


def _pack_maxrects(items: tuple[CargoItem, ...], vehicle: VehicleVersion, strategy: PackingStrategy,
                   seed: int) -> tuple[tuple[Placement, ...] | None, tuple[Diagnostic, ...]]:
    rng = random.Random(seed)
    item_map = {item.id: item for item in items}
    placed: list[Placement] = []
    free_rectangles = [FreeRect(0, 0, vehicle.interior_width_mm, vehicle.interior_length_mm)]
    for obstacle in vehicle.obstacles:
        free_rectangles = _subtract_used(
            free_rectangles,
            FreeRect(obstacle.x_mm, obstacle.y_mm, obstacle.width_mm, obstacle.length_mm),
        )

    for item in _sort_items(items, strategy, rng):
        orientations = [0]
        if item.rotation_allowed and item.length_mm != item.width_mm:
            orientations.append(90)
        if strategy.prefer_rotated:
            orientations.reverse()
        best: tuple[tuple[float, ...], Placement] | None = None
        for orientation in orientations:
            envelope = build_envelope(item, orientation)
            for free in free_rectangles:
                if envelope.envelope_width_mm > free.width_mm or envelope.envelope_length_mm > free.length_mm:
                    continue
                xs = {
                    free.x_mm,
                    free.right_mm - envelope.envelope_width_mm,
                    round(free.x_mm + (free.width_mm - envelope.envelope_width_mm) / 2),
                }
                ys = {free.y_mm}
                for x in xs:
                    for y in ys:
                        candidate = _make_placement(item, orientation, x, y)
                        if not _candidate_is_valid(candidate, placed, item_map, vehicle):
                            continue
                        score = _maxrect_score(candidate, free, vehicle, strategy, placed)
                        if best is None or score < best[0]:
                            best = (score, candidate)
        if best is None:
            return None, (Diagnostic(
                "NO_PLACEMENT",
                f"Le moteur MaxRects n’a pas trouvé de position pour {item.id} dans {vehicle.name}.",
                field_path=item.id,
                details={"strategy": strategy.name},
            ),)
        selected = best[1]
        placed.append(selected)
        free_rectangles = _subtract_used(
            free_rectangles,
            FreeRect(selected.x_mm, selected.y_mm, selected.envelope_width_mm, selected.envelope_length_mm),
        )
    return tuple(placed), ()


def pack_single_vehicle(items: tuple[CargoItem, ...], vehicle: VehicleVersion, strategy: PackingStrategy,
                        seed: int) -> tuple[tuple[Placement, ...] | None, tuple[Diagnostic, ...]]:
    if strategy.algorithm == "maxrects":
        placements, diagnostics = _pack_maxrects(items, vehicle, strategy, seed)
        if placements is not None:
            return placements, diagnostics
        # MaxRects can miss a feasible placement with practical constraints. Fall back to
        # an extreme-point search using the same item order before declaring failure.
        return _pack_extreme_points(items, vehicle, replace(strategy, algorithm="extreme"), seed)
    return _pack_extreme_points(items, vehicle, strategy, seed)


def estimate_vehicle_lower_bound(items: tuple[CargoItem, ...], vehicle: VehicleVersion) -> int:
    total_area = sum(
        (item.length_mm + item.margins.front_mm + item.margins.rear_mm)
        * (item.width_mm + item.margins.left_mm + item.margins.right_mm)
        for item in items
    )
    usable_area = vehicle.interior_length_mm * vehicle.interior_width_mm - sum(
        obstacle.length_mm * obstacle.width_mm for obstacle in vehicle.obstacles
    )
    area_bound = math.ceil(total_area / max(1, usable_area))
    weight_bound = math.ceil(sum(item.weight_kg for item in items) / vehicle.payload_kg)
    return max(1, area_bound, weight_bound)


def _bundles(items: tuple[CargoItem, ...]) -> list[list[CargoItem]]:
    grouped: dict[str, list[CargoItem]] = {}
    singles: list[list[CargoItem]] = []
    for item in items:
        if item.keep_together_group:
            grouped.setdefault(item.keep_together_group, []).append(item)
        else:
            singles.append([item])
    return list(grouped.values()) + singles


def partition_items(items: tuple[CargoItem, ...], vehicle: VehicleVersion, vehicle_count: int,
                    seed: int, variant: int = 0) -> tuple[tuple[CargoItem, ...], ...] | None:
    rng = random.Random(seed + variant * 1009)
    bundles = _bundles(items)
    bundles.sort(key=lambda group: (-sum(i.length_mm * i.width_mm for i in group), -sum(i.weight_kg for i in group), group[0].id))
    if variant:
        for start in range(0, len(bundles), 3):
            chunk = bundles[start:start + 3]
            rng.shuffle(chunk)
            bundles[start:start + 3] = chunk
    bins: list[list[CargoItem]] = [[] for _ in range(vehicle_count)]
    area_used = [0 for _ in bins]
    weight_used = [0.0 for _ in bins]
    separate_seen: list[set[str]] = [set() for _ in bins]
    floor_area = vehicle.interior_length_mm * vehicle.interior_width_mm - sum(
        obstacle.length_mm * obstacle.width_mm for obstacle in vehicle.obstacles
    )
    for bundle in bundles:
        area = sum((i.length_mm + i.margins.front_mm + i.margins.rear_mm) *
                   (i.width_mm + i.margins.left_mm + i.margins.right_mm) for i in bundle)
        weight = sum(i.weight_kg for i in bundle)
        separate = {i.separate_group for i in bundle if i.separate_group}
        candidates = []
        for idx in range(vehicle_count):
            if area_used[idx] + area > floor_area or weight_used[idx] + weight > vehicle.payload_kg:
                continue
            if separate & separate_seen[idx]:
                continue
            score = (area_used[idx] / max(1, floor_area), weight_used[idx] / vehicle.payload_kg, idx)
            candidates.append((score, idx))
        if not candidates:
            return None
        _, selected = min(candidates)
        bins[selected].extend(bundle)
        area_used[selected] += area
        weight_used[selected] += weight
        separate_seen[selected].update(separate)
    if any(not group for group in bins):
        return None
    return tuple(tuple(group) for group in bins)
