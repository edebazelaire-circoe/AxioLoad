from __future__ import annotations

from typing import Any

from . import admin_base
from .persistence import _connect

DOCUMENT_CONTROL_PERMISSION_KEYS: tuple[str, ...] = (
    "document_control.view",
    "document_control.run",
    "document_control.history",
    "document_control.export",
)


def install_document_control_permission_migration() -> None:
    """Grant newly introduced document-control permissions to legacy tenants.

    New companies receive these permissions through
    ``DEFAULT_NEW_COMPANY_PERMISSIONS``. Companies created before version 0.13.0
    have no rows for the new keys, however, and the permission resolver treats a
    missing row as ``False``. The front end therefore creates the tab and hides
    it again as soon as ``/api/company/context`` returns.

    This migration inserts only missing rows. An explicit denial previously set
    by a super administrator is preserved by ``INSERT OR IGNORE``.
    """

    current_migrate = admin_base.AdminBaseMixin._migrate
    if getattr(current_migrate, "_axioload_document_permission_migration", False):
        return

    def migrate(self: Any) -> None:
        current_migrate(self)
        with _connect(self.registry.registry_path) as db:
            tenants = db.execute("SELECT id FROM tenants").fetchall()
            for tenant in tenants:
                tenant_id = str(tenant["id"])
                for permission_key in DOCUMENT_CONTROL_PERMISSION_KEYS:
                    db.execute(
                        """INSERT OR IGNORE INTO company_permissions(
                               tenant_id, permission_key, allowed
                           ) VALUES (?, ?, 1)""",
                        (tenant_id, permission_key),
                    )

    migrate._axioload_document_permission_migration = True  # type: ignore[attr-defined]
    admin_base.AdminBaseMixin._migrate = migrate
