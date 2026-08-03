from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends

from .admin_base import PERMISSION_CATALOG
from .admin_service import AdminRepository, WebContext
from .platform.modules import ModuleRegistry
from .version import APP_VERSION


def build_platform_router(
    *,
    admin: AdminRepository,
    module_registry: ModuleRegistry,
    read_context: Callable[..., WebContext],
) -> APIRouter:
    """Create the platform router without changing the public HTTP contract."""

    router = APIRouter(prefix="/api/platform", tags=["platform"])

    @router.get("/modules", name="platform_modules")
    def platform_modules(
        context: WebContext = Depends(read_context),
    ) -> dict[str, Any]:
        if context.is_super_admin or context.actor_id == "local-user":
            permissions = {entry["key"]: True for entry in PERMISSION_CATALOG}
        else:
            permissions = admin.effective_permissions(context.tenant_id, context.actor_id)
        return {
            "version": APP_VERSION,
            "modules": module_registry.manifest(
                permissions,
                is_super_admin=context.is_super_admin,
            ),
        }

    return router
