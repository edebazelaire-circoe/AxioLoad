from __future__ import annotations

import ast
import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app
from pallet_optimizer.domain import OptimizationResult, RunStatus
from pallet_optimizer.persistence import TenantRegistry, TenantRunRepository


def test_engine_modules_do_not_import_web_orm_or_rendering() -> None:
    package = Path(__file__).parents[1] / "src" / "pallet_optimizer"
    forbidden = {"fastapi", "sqlalchemy", "sqlite3", "jinja2", "reportlab", "openpyxl"}
    for filename in ["domain.py", "envelopes.py", "validation.py", "packing.py", "ranking.py", "engine.py"]:
        tree = ast.parse((package / filename).read_text())
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import): imports.update(alias.name.split('.')[0] for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.module: imports.add(node.module.split('.')[0])
        assert not imports & forbidden, (filename, imports & forbidden)


def test_tenant_databases_are_physically_isolated(tmp_path) -> None:
    registry = TenantRegistry(tmp_path)
    alpha = registry.create_tenant("alpha", "Alpha")
    beta = registry.create_tenant("beta", "Beta")
    assert alpha != beta and alpha.exists() and beta.exists()
    repository = TenantRunRepository(registry)
    result = OptimizationResult(RunStatus.INFEASIBLE, (), (), False, False, 0.0, 1)
    run_id = repository.save_run("alpha", {"items": []}, result)
    assert repository.get_run("alpha", run_id)["id"] == run_id
    try:
        repository.get_run("beta", run_id)
        assert False, "cross-tenant read unexpectedly succeeded"
    except KeyError:
        pass


def test_api_keys_are_hashed_and_revocable(tmp_path) -> None:
    registry = TenantRegistry(tmp_path); registry.create_tenant("alpha", "Alpha")
    key = registry.issue_api_key("alpha", "integration")
    assert registry.resolve_api_key(key) == "alpha"
    prefix = key.split('_')[1]
    with sqlite3.connect(registry.registry_path) as db:
        row = db.execute("SELECT digest,salt FROM api_keys WHERE prefix=?", (prefix,)).fetchone()
    assert key not in row[0] and key not in row[1]
    registry.revoke_api_key("alpha", prefix, "admin")
    assert registry.resolve_api_key(key) is None


def payload() -> dict:
    return {"vehicle_policy":{"mode":"forced","forced_vehicle_id":"semi_trailer"},"budget_seconds":1,
            "items":[{"id":"P1","quantity":2,"shape":"pallet","length":1200,"width":800,
                      "height":1000,"weight":300,"destination":"A","delivery_order":1}]}


def test_public_api_returns_only_best_solution_and_structured_status(tmp_path) -> None:
    app = create_app(tmp_path); registry = app.state.registry; key = registry.issue_api_key("local", "test")
    client = TestClient(app)
    response = client.post("/v1/optimizations", json=payload(), headers={"X-API-Key": key})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"completed", "completed_with_time_limit"}
    assert len(body["solutions"]) == 1
    assert body["optimality_guaranteed"] is False
    assert body["solutions"][0]["vehicle_plans"][0]["placements"]


def test_local_history_requires_no_api_key(tmp_path) -> None:
    app = create_app(tmp_path)
    client = TestClient(app)
    created = client.post("/local/optimize", json=payload())
    assert created.status_code == 200
    history = client.get("/api/history")
    assert history.status_code == 200
    assert len(history.json()) == 1


def test_exports_preserve_all_placements(tmp_path) -> None:
    app = create_app(tmp_path); client = TestClient(app)
    response = client.post("/local/optimize", json=payload()); run_id = response.json()["run_id"]
    detail = client.get(f"/api/history/{run_id}", ).json()
    count = len(detail["result"]["solutions"][0]["vehicle_plans"][0]["placements"])
    csv_response = client.get(f"/api/history/{run_id}/export.csv", )
    json_response = client.get(f"/api/history/{run_id}/export.json", )
    assert csv_response.status_code == 200 and len(csv_response.text.strip().splitlines()) == count + 1
    assert json.loads(json_response.content)["id"] == run_id


def test_backup_and_restore_all_tenants(tmp_path) -> None:
    from pallet_optimizer.operations import backup_all, restore_all
    source = tmp_path / "source"; backups = tmp_path / "backups"; restored = tmp_path / "restored"
    registry = TenantRegistry(source); registry.create_tenant("alpha", "Alpha")
    repository = TenantRunRepository(registry)
    result = OptimizationResult(RunStatus.INFEASIBLE, (), (), False, False, 0.0, 1)
    run_id = repository.save_run("alpha", {"items": []}, result)
    backup = backup_all(registry, backups)
    restored_registry = restore_all(backup, restored)
    restored_repository = TenantRunRepository(restored_registry)
    assert restored_repository.get_run("alpha", run_id)["id"] == run_id


def test_user_roles_and_password_hashing(tmp_path) -> None:
    registry = TenantRegistry(tmp_path); registry.create_tenant("alpha", "Alpha")
    registry.create_user("alpha", "admin@example.com", "correct-horse-battery-staple", "company_admin")
    assert registry.authenticate_user("alpha", "admin@example.com", "wrong") is None
    user = registry.authenticate_user("alpha", "admin@example.com", "correct-horse-battery-staple")
    assert user and user["role"] == "company_admin"
    with sqlite3.connect(registry.tenant_path("alpha")) as db:
        salt, digest = db.execute("SELECT password_salt,password_digest FROM users").fetchone()
    assert "correct-horse-battery-staple" not in salt + digest


def test_browser_endpoints_work_without_api_key_even_when_demo_mode_is_zero(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PLO_DEMO_MODE", "0")
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/vehicles").status_code == 200
    assert client.post("/local/optimize", json=payload()).status_code == 200


def test_vehicle_catalog_can_be_updated_and_is_used_by_optimizer(tmp_path) -> None:
    app = create_app(tmp_path)
    client = TestClient(app)
    headers = {}
    vehicles = client.get("/api/vehicles", headers=headers).json()
    semi = next(v for v in vehicles if v["model_id"] == "semi_trailer")
    original_version = semi["version"]
    semi.update({
        "name": "Semi test étroit",
        "interior_length_mm": 5000,
        "interior_width_mm": 1600,
        "linear_meter_width_mm": 1600,
        "door_width_mm": 1600,
    })
    saved = client.post("/api/vehicles", headers=headers, json=semi)
    assert saved.status_code == 200
    body = saved.json()
    assert body["version"] == original_version + 1
    assert body["interior_width_mm"] == 1600

    request = {
        "vehicle_policy": {"mode": "forced", "forced_vehicle_id": "semi_trailer", "max_vehicles": 1},
        "budget_seconds": 2,
        "items": [{
            "id": "P", "quantity": 3, "shape": "pallet",
            "length": 1200, "width": 800, "height": 1000, "weight": 100,
            "destination": "A", "delivery_order": 1,
        }],
    }
    result = client.post("/local/optimize", json=request).json()
    assert result["status"] == "completed"
    plan = result["solutions"][0]["vehicle_plans"][0]
    assert plan["vehicle_version_id"] == f"semi_trailer@{original_version + 1}"
    assert plan["occupied_length_m"] == 2.0
    assert all(p["x_mm"] + p["envelope_width_mm"] <= 1600 for p in plan["placements"])


def test_vehicle_dimension_validation_rejects_door_wider_than_body(tmp_path) -> None:
    app = create_app(tmp_path)
    client = TestClient(app)
    headers = {}
    vehicle = client.get("/api/vehicles", headers=headers).json()[0]
    vehicle["interior_width_mm"] = 1000
    vehicle["door_width_mm"] = 1200
    response = client.post("/api/vehicles", headers=headers, json=vehicle)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_OPENING"


def test_deleted_vehicle_is_not_reseeded(tmp_path) -> None:
    app = create_app(tmp_path)
    client = TestClient(app)
    headers = {}
    response = client.delete("/api/vehicles/rigid_20m3", headers=headers)
    assert response.status_code == 204
    vehicles = client.get("/api/vehicles", headers=headers).json()
    assert [v["model_id"] for v in vehicles] == ["semi_trailer"]


def test_index_still_renders_when_demo_mode_is_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PLO_DEMO_MODE", "0")
    client = TestClient(create_app(tmp_path))
    response = client.get("/")
    assert response.status_code == 200
    assert "0. Véhicules" in response.text


def test_operational_pdf_embeds_3d_capture_and_checks_metrics(tmp_path) -> None:
    import base64

    client = TestClient(create_app(tmp_path))
    optimized = client.post("/local/optimize", json=payload()).json()
    run_id = optimized["run_id"]
    plan = optimized["solutions"][0]["vehicle_plans"][0]
    # Valid 1 x 1 transparent PNG.
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    request = {
        "image_data_url": "data:image/png;base64," + base64.b64encode(png).decode(),
        "solution_index": 0,
        "vehicle_index": 0,
        "displayed_metrics": {
            "occupied_length_m": plan["occupied_length_m"],
            "linear_meters": plan["linear_meters"],
        },
        "vehicle_dimensions": {
            "interior_length_mm": 13600,
            "interior_width_mm": 2450,
            "interior_height_mm": 2700,
        },
    }
    response = client.post(f"/api/history/{run_id}/export-operational.pdf", json=request)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 1500

    request["displayed_metrics"]["linear_meters"] += 1
    mismatch = client.post(f"/api/history/{run_id}/export-operational.pdf", json=request)
    assert mismatch.status_code == 409


def test_brand_assets_and_coordinate_contract_are_packaged() -> None:
    package = Path(__file__).parents[1] / "src" / "pallet_optimizer"
    for asset in (
        "axioload-horizontal.svg", "axioload-horizontal-dark.svg", "axioload-compact.svg",
        "axioload-icon.svg", "favicon.svg", "favicon.ico",
    ):
        assert (package / "static" / "brand" / asset).exists()
    javascript = (package / "static" / "app.js").read_text()
    assert "projectWorld(longitudinal,width,height" in javascript
    assert "Position longitudinale" in javascript
    assert "Longueur réellement occupée" in javascript
