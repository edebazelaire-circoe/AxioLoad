from __future__ import annotations

from dataclasses import replace

from pallet_optimizer.domain import CargoItem, Margins, Placement, Rect, Shape, VehicleVersion, ZoneSpec
from pallet_optimizer.packing import STRATEGIES, pack_single_vehicle
from pallet_optimizer.validation import (calculate_weight, validate_delivery_access, validate_geometry)


def item(item_id: str, *, order: int = 1, rotation: bool = True, weight: float = 100,
         zone: str | None = None) -> CargoItem:
    return CargoItem(item_id, item_id, 0, Shape.PALLET, 1200, 800, 1000, weight, "A", order,
                     rotation_allowed=rotation, margins=Margins(), zone=zone)


def placement(i: CargoItem, x: int, y: int, orientation: int = 0) -> Placement:
    al, aw, el, ew = i.oriented_dimensions(orientation)
    return Placement(i.id, i.source_id, i.destination, i.delivery_order, x, y, 0, orientation,
                     al, aw, i.height_mm, el, ew, i.weight_kg)


def test_collision_bounds_and_floor_are_rejected(simple_vehicle) -> None:
    a, b = item("A"), item("B")
    diagnostics = validate_geometry(simple_vehicle, (placement(a, 0, 0), placement(b, 100, 100)), {"A": a, "B": b})
    assert "ITEM_COLLISION" in {d.code for d in diagnostics}
    bad = Placement("A", "A", "A", 1, 3500, 0, 1, 0, 1200, 800, 1000, 1200, 800, 100)
    diagnostics = validate_geometry(simple_vehicle, (bad,), {"A": a})
    assert {"OUT_OF_BOUNDS", "NOT_ON_FLOOR"} <= {d.code for d in diagnostics}


def test_obstacle_and_zone_are_hard_constraints(simple_vehicle) -> None:
    vehicle = replace(
        simple_vehicle,
        obstacles=(Rect(0, 0, 500, 500, 300, "wheel"),),
        zones=(ZoneSpec("cold", Rect(1200, 0, 1200, 4000, 0, "cold")),),
    )
    cargo = item("A", zone="cold")
    codes = {d.code for d in validate_geometry(vehicle, (placement(cargo, 0, 0),), {"A": cargo})}
    assert "OBSTACLE_COLLISION" in codes
    assert "ZONE_VIOLATION" in codes


def test_rotation_lock_is_never_violated(simple_vehicle) -> None:
    cargo = item("A", rotation=False)
    placements, diagnostics = pack_single_vehicle((cargo,), simple_vehicle, STRATEGIES[1], 1)
    assert not diagnostics
    assert placements and placements[0].orientation_deg == 0


def test_opening_too_small_is_rejected(simple_vehicle) -> None:
    cargo = CargoItem("A", "A", 0, Shape.PALLET, 1200, 2500, 1000, 100, "A", 1)
    codes = {d.code for d in validate_geometry(simple_vehicle, (placement(cargo, 0, 0),), {"A": cargo})}
    assert "OPENING_TOO_SMALL" in codes


def test_payload_and_axle_overload_have_precise_diagnostics(simple_vehicle) -> None:
    cargo = item("A", weight=5000)
    metrics, diagnostics, _ = calculate_weight(simple_vehicle, (placement(cargo, 0, 0),))
    assert metrics.total_weight_kg == 5000
    assert "PAYLOAD_EXCEEDED" in {d.code for d in diagnostics}
    assert "AXLE_OVERLOAD" in {d.code for d in diagnostics}


def test_lifo_blocking_is_detected() -> None:
    early = item("EARLY", order=2)
    late = item("LATE", order=1)
    codes = {d.code for d in validate_delivery_access((placement(early, 0, 1200), placement(late, 0, 0)))}
    assert codes == {"LIFO_BLOCKED"}


def test_packer_can_place_item_inside_required_zone(simple_vehicle) -> None:
    vehicle = replace(simple_vehicle, zones=(ZoneSpec("cold", Rect(1200, 0, 1200, 4000, 0, "cold")),))
    cargo = item("A", zone="cold")
    placements, diagnostics = pack_single_vehicle((cargo,), vehicle, STRATEGIES[0], 1)
    assert not diagnostics and placements
    assert placements[0].x_mm >= 1200
