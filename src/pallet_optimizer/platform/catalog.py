from __future__ import annotations

from .modules import MigrationState, ModuleDescriptor, ModuleKind, ModuleRegistry


def build_default_module_registry() -> ModuleRegistry:
    """Describe the target module boundaries without moving legacy code yet."""

    return ModuleRegistry(
        (
            ModuleDescriptor(
                module_id="core",
                label="Socle AxioLoad",
                kind=ModuleKind.CORE,
                order=0,
                route_prefixes=(
                    "/",
                    "/health",
                    "/login",
                    "/activate",
                    "/change-password",
                    "/api/auth",
                    "/api/company",
                    "/api/platform",
                ),
                backend_packages=(
                    "admin_service",
                    "admin_api",
                    "super_admin_routes",
                    "password_reset_system",
                    "fixed_test_accounts",
                ),
                frontend_assets=(
                    "login.js",
                    "auth_experience.js",
                    "password_reset.js",
                ),
                migration_state=MigrationState.FOUNDATION,
            ),
            ModuleDescriptor(
                module_id="reference_data",
                label="Base de données",
                kind=ModuleKind.WORKSPACE,
                order=10,
                depends_on=("core",),
                permission_prefixes=("vehicles", "settings"),
                route_prefixes=("/api/vehicles", "/api/import", "/api/prompts"),
                backend_packages=("catalog", "persistence", "prompt_center_system"),
                frontend_assets=("workflow_layout.js", "prompt_center_experience.js"),
            ),
            ModuleDescriptor(
                module_id="optimization",
                label="Optimisation",
                kind=ModuleKind.WORKSPACE,
                order=20,
                depends_on=("core", "reference_data"),
                permission_prefixes=(
                    "data",
                    "results",
                    "history",
                    "route",
                    "total",
                    "exports",
                ),
                route_prefixes=(
                    "/local/optimize",
                    "/v1/optimizations",
                    "/api/route",
                    "/api/total",
                    "/api/history",
                    "/api/exports",
                ),
                backend_packages=(
                    "engine",
                    "service",
                    "optimization_portfolio",
                    "route_optimization",
                    "total_optimization",
                    "workflow_history",
                ),
                frontend_assets=(
                    "optimization_experience.js",
                    "results_enhancements.js",
                    "workflow_layout.js",
                ),
            ),
            ModuleDescriptor(
                module_id="document_control",
                label="Contrôle documentaire",
                kind=ModuleKind.WORKSPACE,
                order=30,
                depends_on=("core", "reference_data"),
                permission_prefixes=("document_control",),
                route_prefixes=("/api/document-control",),
                backend_packages=(
                    "document_control",
                    "document_control_bootstrap",
                    "document_control_system",
                ),
                frontend_assets=(
                    "document_control.js",
                    "document_control_experience_v2.js",
                ),
            ),
            ModuleDescriptor(
                module_id="management",
                label="Centre de gestion",
                kind=ModuleKind.MANAGEMENT,
                order=40,
                depends_on=("core",),
                route_prefixes=("/api/admin",),
                backend_packages=("admin_service", "admin_integrations", "admin_panel"),
                frontend_assets=("admin.js", "fixed_test_accounts_ui.js"),
            ),
        )
    )
