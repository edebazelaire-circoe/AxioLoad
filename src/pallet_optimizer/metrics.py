from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .domain import Placement


@dataclass(frozen=True, slots=True)
class LengthMetrics:
    """Longitudinal occupancy metrics derived from the placement coordinates.

    The persistence and API fields keep their historical names for backward
    compatibility. In AxioLoad, ``linear_meters`` intentionally represents the
    actual occupied truck length, as requested by the product owner.
    """

    occupied_length_mm: int
    occupied_length_m: float
    linear_meters: float


def calculate_length_metrics(placements: Iterable[Placement]) -> LengthMetrics:
    occupied_mm = max(
        (placement.y_mm + placement.envelope_length_mm for placement in placements),
        default=0,
    )
    occupied_m = occupied_mm / 1000.0
    return LengthMetrics(
        occupied_length_mm=occupied_mm,
        occupied_length_m=occupied_m,
        linear_meters=occupied_m,
    )
