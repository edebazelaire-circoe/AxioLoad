from __future__ import annotations

from fastapi.testclient import TestClient

from pallet_optimizer import optimization_methods
from pallet_optimizer.api import create_app


def _payload() -> dict:
    return {
        "dimension_unit": "mm",
        "weight_unit": "kg",
        "seed": 7,
        "budget_seconds": 15,
        "requested_solutions": 5,
        "vehicle_policy": {
            "mode": "forced",
            "forced_vehicle_id": "semi_trailer",
            "max_vehicles": 1,
        },
        "items": [
            {
                "id": "PAL-001",
                "quantity": 1,
                "shape": "pallet",
                "length": 1200,
                "width": 800,
                "height": 1200,
                "weight": 300,
                "destination": "Client A",
                "delivery_order": 1,
                "rotation_allowed": True,
            },
            {
                "id": "PAL-002",
                "quantity": 1,
                "shape": "pallet",
                "length": 1200,
                "width": 1000,
                "height": 1200,
                "weight": 600,
                "destination": "Client B",
                "delivery_order": 2,
                "rotation_allowed": True,
            },
        ],
    }


def test_one_model_runtime_error_does_not_cancel_other_valid_solutions(tmp_path, monkeypatch) -> None:
    def broken_model(*_args, **_kwargs):
        raise RuntimeError("simulated isolated model failure")

    monkeypatch.setitem(optimization_methods.PACKERS, "brkga_hybrid", broken_model)
    response = TestClient(create_app(tmp_path)).post("/local/optimize", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"completed", "completed_with_time_limit"}
    assert body["solutions"], "A valid result from another model must remain available."

    outcomes = {outcome["code"]: outcome for outcome in body["method_outcomes"]}
    assert outcomes["brkga_hybrid"]["status"] == "failure"
    assert any(outcome["status"] == "success" for outcome in outcomes.values())

    diagnostics = body.get("diagnostics", [])
    assert not any(diagnostic.get("severity") == "error" for diagnostic in diagnostics)
    summary = next(
        diagnostic
        for diagnostic in diagnostics
        if diagnostic.get("code") == "PORTFOLIO_PARTIAL_SUCCESS"
    )
    assert summary["details"]["result_accepted"] is True
    assert "brkga_hybrid" in summary["details"]["failed_models"]
