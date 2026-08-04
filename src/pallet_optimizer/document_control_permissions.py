from __future__ import annotations

from typing import Any, Mapping

from . import admin_base
from .persistence import _connect

DOCUMENT_CONTROL_PERMISSION_KEYS: tuple[str, ...] = (
    "document_control.view",
    "document_control.run",
    "document_control.history",
    "document_control.export",
)


def _permission_defaults(tenant_id: str, *, grant_all: bool = False) -> dict[str, bool]:
    """Return the values to use only for permission rows that do not exist yet."""

    if grant_all or tenant_id == "local":
        return {key: True for key in admin_base.PERMISSION_KEYS}
    return {
        key: bool(admin_base.DEFAULT_NEW_COMPANY_PERMISSIONS.get(key, False))
        for key in admin_base.PERMISSION_KEYS
    }


def _insert_missing_permissions(
    db: Any,
    tenant_id: str,
    permissions: Mapping[str, bool],
) -> None:
    for permission_key, allowed in permissions.items():
        db.execute(
            """INSERT OR IGNORE INTO company_permissions(
                   tenant_id, permission_key, allowed
               ) VALUES (?, ?, ?)""",
            (tenant_id, permission_key, int(allowed)),
        )


def install_document_control_permission_migration() -> None:
    """Backfill every missing permission without overwriting explicit choices.

    The document-control module extends ``PERMISSION_KEYS`` before the admin
    repository is created. On a fresh or historical registry, document rows can
    therefore exist before the original core rows. The old ``ensure_company``
    implementation only checked whether *any* row existed and then skipped the
    complete default seed. This produced a company context where vehicles,
    data, results, routes and history were all reported as denied, even for the
    local account. Visually the workspace tile changed colour, while the target
    page was refused and the previous panel stayed active.

    Both migration and company creation now insert each missing key
    independently. ``INSERT OR IGNORE`` preserves every explicit denial already
    configured by an administrator.
    """

    current_migrate = admin_base.AdminBaseMixin._migrate
    if not getattr(current_migrate, "_axioload_permission_defaults_migration", False):

        def migrate(self: Any) -> None:
            current_migrate(self)
            with _connect(self.registry.registry_path) as db:
                tenants = db.execute("SELECT id FROM tenants").fetchall()
                for tenant in tenants:
                    tenant_id = str(tenant["id"])
                    _insert_missing_permissions(
                        db,
                        tenant_id,
                        _permission_defaults(tenant_id),
                    )

        migrate._axioload_permission_defaults_migration = True  # type: ignore[attr-defined]
        admin_base.AdminBaseMixin._migrate = migrate

    current_ensure_company = admin_base.AdminBaseMixin.ensure_company
    if not getattr(current_ensure_company, "_axioload_permission_defaults_seed", False):

        def ensure_company(
            self: Any,
            tenant_id: str,
            name: str,
            *,
            status: str = "draft",
            grant_all: bool = False,
        ) -> None:
            current_ensure_company(
                self,
                tenant_id,
                name,
                status=status,
                grant_all=grant_all,
            )
            with _connect(self.registry.registry_path) as db:
                _insert_missing_permissions(
                    db,
                    tenant_id,
                    _permission_defaults(tenant_id, grant_all=grant_all),
                )

        ensure_company._axioload_permission_defaults_seed = True  # type: ignore[attr-defined]
        admin_base.AdminBaseMixin.ensure_company = ensure_company
