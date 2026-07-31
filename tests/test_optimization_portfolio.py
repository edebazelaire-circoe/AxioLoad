from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app
from pallet_optimizer.catalog import default_vehicle_catalog
from pallet_optimizer.domain import (
    CargoItem,
    DomainError,
    OptimizationProblem,
    Shape,
    VehiclePolicy,
    to_primitive,
)
from pallet_optimizer.engine import OptimizationEngine
from pallet_optimizer import optimization_methods, packing


def _problem(budget: float = 5.0) -> OptimizationProblem:
    vehicle = default_vehicle_catalog()[0]
    item = CargoItem(
        id="PAL-001#1",
        source_id="PAL-001",
        input_index=0,
        shape=Shape.PALLET,
        length_mm=1200,
        width_mm=800,
        height_mm=1200,
        weight_kg=500,
        destination="Client A",
        delivery_order=1,
        rotation_allowed=True,
    )
    return OptimizationProblem(
        items=(item,),
        vehicles=(vehicle,),
        vehicle_policy=VehiclePolicy(
            mode="forced",
            forced_vehicle_id=vehicle.model_id,
            max_vehicles=1,
        ),
        seed=1,
        budget_seconds=budget,
        requested_solutions=5,
    )


def test_budget_accepts_sixty_seconds_and_rejects_more():
    assert _problem(60).budget_seconds == 60
    with pytest.raises(DomainError):
        _problem(61)


def test_one_model_failure_does_not_stop_the_other_models(monkeypatch):
    original = optimization_methods.PACKERS["skyline_blf"]

    def fail_model(*args, **kwargs):
        raise RuntimeError("échec simulé du modèle")

    monkeypatch.setitem(optimization_methods.PACKERS, "skyline_blf", fail_model)
    try:
        result = OptimizationEngine().optimize(_problem())
    finally:
        optimization_methods.PACKERS["skyline_blf"] = original

    payload = to_primitive(result)
    outcomes = payload["method_outcomes"]
    assert len(outcomes) == 5
    assert [outcome["index"] for outcome in outcomes] == [1, 2, 3, 4, 5]
    experimental = next(outcome for outcome in outcomes if outcome["code"] == "skyline_blf")
    assert experimental["status"] == "failure"
    assert "sans interrompre" in next(
        diagnostic["message"]
        for diagnostic in payload["diagnostics"]
        if diagnostic["code"] == "METHOD_INTERNAL_ERROR"
    )
    assert any(outcome["status"] == "success" for outcome in outcomes if outcome["code"] != "skyline_blf")


def test_destination_is_grouped_when_the_client_fits_one_vehicle():
    vehicle = default_vehicle_catalog()[0]
    first = _problem().items[0]
    second = CargoItem(
        id="PAL-002#1",
        source_id="PAL-002",
        input_index=1,
        shape=Shape.PALLET,
        length_mm=1200,
        width_mm=800,
        height_mm=1000,
        weight_kg=400,
        destination="Client A",
        delivery_order=1,
    )
    partition = packing.partition_items((first, second), vehicle, 1, seed=1)
    assert partition is not None
    assert len(partition) == 1
    assert {item.id for item in partition[0]} == {first.id, second.id}
    assert {item.keep_together_group for item in partition[0]} == {"CLIENT::client a"}


def test_optimization_experience_assets_are_injected(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.get("/")
    assert response.status_code == 200
    assert "/static/optimization_experience.css?v=0.18.0" in response.text
    assert "/static/optimization_experience.js?v=0.18.0" in response.text
