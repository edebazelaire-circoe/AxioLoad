from __future__ import annotations

from collections import defaultdict
from typing import Any

from . import packing


def install_client_grouping() -> None:
    """Treat one destination as one indivisible client bundle by default.

    An explicit keep_together_group remains authoritative. When it is absent,
    the normalized destination becomes the grouping key. This rule applies to
    direct API calls as well as the browser interface.
    """
    current = packing._bundles
    if getattr(current, "_axioload_client_bundles", False):
        return

    def client_bundles(items: tuple[Any, ...]) -> list[list[Any]]:
        grouped: dict[str, list[Any]] = defaultdict(list)
        singles: list[list[Any]] = []
        for item in items:
            explicit = str(item.keep_together_group or "").strip()
            destination = str(item.destination or "").strip().casefold()
            key = explicit or (f"client::{destination}" if destination else "")
            if key:
                grouped[key].append(item)
            else:
                singles.append([item])
        return list(grouped.values()) + singles

    client_bundles._axioload_client_bundles = True  # type: ignore[attr-defined]
    packing._bundles = client_bundles  # type: ignore[assignment]
