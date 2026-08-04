from __future__ import annotations

from pallet_optimizer.admin_base import PERMISSION_KEYS
from pallet_optimizer.admin_service import AdminRepository
from pallet_optimizer.document_control_permissions import DOCUMENT_CONTROL_PERMISSION_KEYS
from pallet_optimizer.persistence import TenantRegistry, _connect


def test_local_company_receives_every_permission_on_first_start(tmp_path):
    registry = TenantRegistry(tmp_path)
    admin = AdminRepository(registry)

    permissions = admin.get_company_permissions("local")

    assert set(PERMISSION_KEYS).issubset(permissions)
    assert all(permissions[key] is True for key in PERMISSION_KEYS)


def test_legacy_company_receives_every_missing_default_permission(tmp_path):
    registry = TenantRegistry(tmp_path)
    admin = AdminRepository(registry)
    admin.ensure_company("legacy-company", "Entreprise historique", status="active")

    missing_keys = {
        "vehicles.view",
        "data.view",
        "results.view",
        "route.view",
        "history.view",
        *DOCUMENT_CONTROL_PERMISSION_KEYS,
    }
    with _connect(registry.registry_path) as db:
        for permission_key in missing_keys:
            db.execute(
                "DELETE FROM company_permissions WHERE tenant_id=? AND permission_key=?",
                ("legacy-company", permission_key),
            )

    before = admin.get_company_permissions("legacy-company")
    assert missing_keys.isdisjoint(before)

    migrated = AdminRepository(registry)
    permissions = migrated.get_company_permissions("legacy-company")

    assert all(permissions[key] is True for key in missing_keys)


def test_migration_preserves_explicit_core_and_document_denials(tmp_path):
    registry = TenantRegistry(tmp_path)
    admin = AdminRepository(registry)
    admin.ensure_company("restricted-company", "Entreprise restreinte", status="active")

    with _connect(registry.registry_path) as db:
        for permission_key in ("data.view", "document_control.view"):
            db.execute(
                "UPDATE company_permissions SET allowed=0 WHERE tenant_id=? AND permission_key=?",
                ("restricted-company", permission_key),
            )
        for permission_key in ("route.view", "document_control.export"):
            db.execute(
                "DELETE FROM company_permissions WHERE tenant_id=? AND permission_key=?",
                ("restricted-company", permission_key),
            )

    migrated = AdminRepository(registry)
    permissions = migrated.get_company_permissions("restricted-company")

    assert permissions["data.view"] is False
    assert permissions["document_control.view"] is False
    assert permissions["route.view"] is True
    assert permissions["document_control.export"] is True
