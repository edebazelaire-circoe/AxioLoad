from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app


SCENARIO_ID = "AXIO-VEHICLE-CRUD-001"
QA_MODEL_ID = "qa_vehicle_crud_001"


def test_axioload_vehicle_crud_001_create_update_reload_and_delete(tmp_path):
    client = TestClient(create_app(tmp_path))

    template = client.get("/api/vehicles").json()[0]
    vehicle = {
        **template,
        "model_id": QA_MODEL_ID,
        "name": "Vehicle QA CRUD 1",
        "interior_length_mm": 7000,
        "interior_width_mm": 2400,
        "interior_height_mm": 2600,
        "linear_meter_width_mm": 2400,
        "payload_kg": 12000,
        "door_width_mm": 2350,
        "door_height_mm": 2500,
    }
    vehicle.pop("version", None)
    vehicle.pop("version_id", None)

    created = client.post("/api/vehicles", json=vehicle)
    assert created.status_code == 200, f"{SCENARIO_ID}: creation failed: {created.text}"
    created_body = created.json()
    assert created_body["model_id"] == QA_MODEL_ID
    assert created_body["name"] == "Vehicle QA CRUD 1"
    created_version = created_body["version"]

    reloaded = client.get("/api/vehicles")
    assert reloaded.status_code == 200
    stored = next((item for item in reloaded.json() if item["model_id"] == QA_MODEL_ID), None)
    assert stored is not None
    assert stored["payload_kg"] == 12000

    stored.update({
        "name": "Vehicle QA CRUD 1 updated",
        "payload_kg": 13500,
        "interior_length_mm": 7200,
    })
    updated = client.post("/api/vehicles", json=stored)
    assert updated.status_code == 200, f"{SCENARIO_ID}: update failed: {updated.text}"
    updated_body = updated.json()
    assert updated_body["version"] == created_version + 1
    assert updated_body["name"] == "Vehicle QA CRUD 1 updated"
    assert updated_body["payload_kg"] == 13500
    assert updated_body["interior_length_mm"] == 7200

    persisted = next(item for item in client.get("/api/vehicles").json() if item["model_id"] == QA_MODEL_ID)
    assert persisted["version"] == created_version + 1
    assert persisted["payload_kg"] == 13500

    deleted = client.delete(f"/api/vehicles/{QA_MODEL_ID}")
    assert deleted.status_code == 204

    remaining_ids = {item["model_id"] for item in client.get("/api/vehicles").json()}
    assert QA_MODEL_ID not in remaining_ids
