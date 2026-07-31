from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import Any

from . import packing


def install_client_grouping() -> None:
    """Keep one client's cargo together whenever it fits in one vehicle.

    Explicit keep-together groups remain strict. A destination without an
    explicit group is converted into a temporary client group only when the
    floor-area and payload lower bound proves that the whole client can fit in
    one vehicle. Oversized clients remain splittable into the minimum required
    number of lots by the existing partitioner.
    """
    current = packing.partition_items
    if getattr(current, "_axioload_client_partitioning", False):
        return

    def partition_by_client(
        items: tuple[Any, ...],
        vehicle: Any,
        vehicle_count: int,
        seed: int,
        variant: int = 0,
    ) -> tuple[tuple[Any, ...], ...] | None:
        destinations: dict[str, list[Any]] = defaultdict(list)
        for item in items:
            if item.keep_together_group:
                continue
            destination = str(item.destination or "").strip().casefold()
            if destination:
                destinations[destination].append(item)

        generated_groups: dict[str, str] = {}
        for destination, client_items in destinations.items():
            if len(client_items) < 2:
                continue
            if packing.estimate_vehicle_lower_bound(tuple(client_items), vehicle) <= 1:
                generated_groups.update(
                    {item.id: f"CLIENT::{destination}" for item in client_items}
                )

        prepared = tuple(
            replace(item, keep_together_group=generated_groups[item.id])
            if item.id in generated_groups else item
            for item in items
        )
        return current(prepared, vehicle, vehicle_count, seed, variant)

    partition_by_client._axioload_client_partitioning = True  # type: ignore[attr-defined]
    packing.partition_items = partition_by_client  # type: ignore[assignment]
