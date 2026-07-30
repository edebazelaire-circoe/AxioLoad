from fastapi.testclient import TestClient
from pallet_optimizer.api import create_app

payload = {
    "vehicle_policy": {"mode": "forced", "forced_vehicle_id": "semi_trailer"},
    "items": [
        {"id": "P1", "quantity": 3, "shape": "pallet", "length": 1200, "width": 800,
         "height": 1200, "weight": 500, "destination": "Client A", "delivery_order": 2},
        {"id": "P2", "quantity": 2, "shape": "roll", "length": 1000, "width": 1000,
         "height": 1200, "weight": 350, "destination": "Client B", "delivery_order": 1,
         "rotation_allowed": False},
    ],
}
client = TestClient(create_app("data-smoke"))
response = client.post("/local/optimize", json=payload)
response.raise_for_status()
body = response.json()
assert body["solutions"], body
print(body["status"], body["solutions"][0]["total_linear_meters"], body["run_id"])
