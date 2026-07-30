from __future__ import annotations

from dataclasses import dataclass

from .domain import CargoItem, Shape


@dataclass(frozen=True, slots=True)
class CargoEnvelope:
    actual_length_mm: int
    actual_width_mm: int
    actual_height_mm: int
    envelope_length_mm: int
    envelope_width_mm: int
    envelope_height_mm: int
    shape_note: str


def build_envelope(item: CargoItem, orientation_deg: int) -> CargoEnvelope:
    actual_length, actual_width, envelope_length, envelope_width = item.oriented_dimensions(orientation_deg)
    notes = {
        Shape.PALLET: "Rectangular pallet footprint",
        Shape.BOX: "Rectangular box footprint",
        Shape.ROLL: "Secured roll represented by its support footprint",
        Shape.CYLINDER: "Cylinder represented by its safe bounding rectangle",
        Shape.SHEET: "Sheet bundle represented by its support footprint",
        Shape.POST: "Post bundle represented by its safe bounding rectangle",
        Shape.BAR_RECT: "Rectangular bars represented by bundle footprint",
        Shape.BAR_CYL: "Cylindrical bars represented by bundle bounding rectangle",
        Shape.IRREGULAR: "Irregular cargo represented by a conservative rectangular safety envelope",
    }
    return CargoEnvelope(
        actual_length_mm=actual_length,
        actual_width_mm=actual_width,
        actual_height_mm=item.height_mm,
        envelope_length_mm=envelope_length,
        envelope_width_mm=envelope_width,
        envelope_height_mm=item.height_mm + item.margins.top_mm,
        shape_note=notes[item.shape],
    )
