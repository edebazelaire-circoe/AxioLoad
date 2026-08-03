from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app
from pallet_optimizer.version import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]


def test_platform_modules_is_registered_once_by_an_api_router(tmp_path) -> None:
    schema = create_app(tmp_path).openapi()
    matching_paths = [path for path in schema["paths"] if path == "/api/platform/modules"]

    assert matching_paths == ["/api/platform/modules"]
    operation = schema["paths"]["/api/platform/modules"]
    assert set(operation) == {"get"}
    assert operation["get"]["operationId"].startswith("platform_modules")
    assert "platform" in operation["get"]["tags"]


def test_platform_modules_keeps_its_http_contract(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))
    response = client.get("/api/platform/modules")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    payload = response.json()
    assert set(payload) == {"version", "modules"}
    assert payload["version"] == APP_VERSION
    assert [module["id"] for module in payload["modules"]] == [
        "core",
        "reference_data",
        "optimization",
        "document_control",
        "management",
    ]
    assert all(
        set(module) == {
            "id",
            "label",
            "kind",
            "order",
            "depends_on",
            "migration_state",
            "available",
        }
        for module in payload["modules"]
    )


def test_platform_modules_openapi_contract_is_unchanged(tmp_path) -> None:
    schema = create_app(tmp_path).openapi()
    operation = schema["paths"]["/api/platform/modules"]

    assert set(operation) == {"get"}
    assert operation["get"]["operationId"].startswith("platform_modules")
    assert "200" in operation["get"]["responses"]


def test_platform_route_is_no_longer_declared_inline_in_api_module() -> None:
    api_source = (ROOT / "src" / "pallet_optimizer" / "api.py").read_text(encoding="utf-8")
    router_source = (ROOT / "src" / "pallet_optimizer" / "platform_router.py").read_text(
        encoding="utf-8"
    )
    platform_alias = (
        ROOT / "src" / "pallet_optimizer" / "platform" / "routes.py"
    ).read_text(encoding="utf-8")

    assert '@app.get("/api/platform/modules")' not in api_source
    assert "app.include_router(" in api_source
    assert "APIRouter" in router_source
    assert 'prefix="/api/platform"' in router_source
    assert '@router.get("/modules"' in router_source
    assert "FastAPI" not in platform_alias
    assert "AdminRepository" not in platform_alias
