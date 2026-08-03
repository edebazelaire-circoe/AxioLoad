from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import pallet_optimizer
from pallet_optimizer.admin_base import PERMISSION_CATALOG
from pallet_optimizer.api import create_app
from pallet_optimizer.platform import (
    ModuleDescriptor,
    ModuleKind,
    ModuleRegistry,
    build_default_module_registry,
)
from pallet_optimizer.version import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "pallet_optimizer"


def _route_contract(app) -> set[tuple[str, str]]:
    return {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }


def _module_owns_path(module: ModuleDescriptor, path: str) -> bool:
    for prefix in module.route_prefixes:
        if prefix == path:
            return True
        if prefix != "/" and path.startswith(prefix + "/"):
            return True
        if prefix != "/" and path.startswith(prefix + "."):
            return True
    return False


def test_project_package_and_runtime_versions_are_aligned(tmp_path) -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    app = create_app(tmp_path)

    assert project["project"]["version"] == APP_VERSION
    assert pallet_optimizer.__version__ == APP_VERSION
    assert app.version == APP_VERSION


def test_default_registry_has_the_expected_boundaries_and_order() -> None:
    registry = build_default_module_registry()

    assert tuple(module.module_id for module in registry.ordered()) == (
        "core",
        "reference_data",
        "optimization",
        "document_control",
        "management",
    )
    assert registry.get("reference_data").depends_on == ("core",)
    assert registry.get("optimization").depends_on == ("core", "reference_data")
    assert registry.get("document_control").depends_on == ("core", "reference_data")
    assert registry.get("management").depends_on == ("core",)
    assert registry.topological_order().index("core") < registry.topological_order().index("optimization")


def test_registry_rejects_duplicate_unknown_and_cyclic_dependencies() -> None:
    module = ModuleDescriptor("core", "Core", ModuleKind.CORE, 0)
    with pytest.raises(ValueError, match="unique"):
        ModuleRegistry((module, module))

    with pytest.raises(ValueError, match="unknown"):
        ModuleRegistry(
            (
                module,
                ModuleDescriptor(
                    "feature",
                    "Feature",
                    ModuleKind.WORKSPACE,
                    1,
                    depends_on=("missing",),
                ),
            )
        )

    with pytest.raises(ValueError, match="Cyclic"):
        ModuleRegistry(
            (
                ModuleDescriptor("first", "First", ModuleKind.CORE, 0, depends_on=("second",)),
                ModuleDescriptor("second", "Second", ModuleKind.CORE, 1, depends_on=("first",)),
            )
        )


def test_declared_permission_prefixes_exist_in_the_current_catalog() -> None:
    permission_roots = {entry["key"].split(".", 1)[0] for entry in PERMISSION_CATALOG}
    registry = build_default_module_registry()

    for module in registry.ordered():
        assert set(module.permission_prefixes) <= permission_roots


def test_declared_backend_packages_and_frontend_assets_exist() -> None:
    registry = build_default_module_registry()

    for module in registry.ordered():
        for package_name in module.backend_packages:
            assert (PACKAGE / f"{package_name}.py").is_file(), (
                f"Module {module.module_id} references missing backend package {package_name}"
            )
        for asset_name in module.frontend_assets:
            assert (PACKAGE / "static" / asset_name).is_file(), (
                f"Module {module.module_id} references missing frontend asset {asset_name}"
            )


def test_platform_package_does_not_patch_framework_or_business_runtime() -> None:
    forbidden = (
        "FastAPI.__init__",
        "Jinja2Templates.TemplateResponse",
        "Element.prototype",
        "MutationObserver",
        "OptimizationEngine",
        "DocumentControlRepository",
        "AdminRepository",
    )
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((PACKAGE / "platform").glob("*.py"))
    )

    for fragment in forbidden:
        assert fragment not in source


def test_runtime_exposes_the_manifest_without_changing_existing_navigation(tmp_path) -> None:
    app = create_app(tmp_path)
    client = TestClient(app)

    response = client.get("/api/platform/modules")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["version"] == APP_VERSION
    assert [module["id"] for module in payload["modules"]] == [
        "core",
        "reference_data",
        "optimization",
        "document_control",
        "management",
    ]
    availability = {module["id"]: module["available"] for module in payload["modules"]}
    assert availability["core"] is True
    assert availability["reference_data"] is True
    assert availability["optimization"] is True
    assert availability["document_control"] is True
    assert availability["management"] is False
    assert app.state.module_registry.get("optimization").label == "Optimisation"

    page = client.get("/")
    assert page.status_code == 200
    assert "Base de données" in page.text
    assert "Optimisation" in page.text
    assert "Contrôle documentaire" in page.text
    assert f"enhancements.css?v={APP_VERSION}" in page.text
    assert f"enhancements.js?v={APP_VERSION}" in page.text


def test_critical_http_contracts_remain_registered(tmp_path) -> None:
    app = create_app(tmp_path)
    routes = _route_contract(app)
    expected = {
        ("GET", "/"),
        ("GET", "/health"),
        ("POST", "/api/auth/login"),
        ("POST", "/api/auth/super-admin-login"),
        ("POST", "/api/auth/logout"),
        ("GET", "/api/admin/bootstrap"),
        ("GET", "/api/vehicles"),
        ("POST", "/local/optimize"),
        ("POST", "/api/route/optimize"),
        ("POST", "/api/total/optimize"),
        ("GET", "/api/history"),
        ("GET", "/api/document-control/bootstrap"),
        ("GET", "/api/platform/modules"),
    }
    assert expected <= routes

    registry = build_default_module_registry()
    for _method, path in expected:
        assert any(_module_owns_path(module, path) for module in registry.ordered()), (
            f"No module boundary owns the critical route {path}"
        )
