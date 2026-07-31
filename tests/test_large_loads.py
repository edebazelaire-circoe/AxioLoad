from __future__ import annotations

from pallet_optimizer.normalization import normalize_payload


def test_more_than_100_expanded_objects_are_accepted():
    problem = normalize_payload({
        "items": [{
            "id": "PAL",
            "quantity": 125,
            "shape": "pallet",
            "length": 1200,
            "width": 800,
            "height": 1000,
            "weight": 250,
            "destination": "Client A",
        }]
    })
    assert len(problem.items) == 125
