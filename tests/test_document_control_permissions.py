from __future__ import annotations

from pallet_optimizer.admin_service import AdminRepository
from pallet_optimizer.document_control_permissions import DOCUMENT_CONTROL_PERMISSION_KEYS
from pallet_optimizer.persistence import TenantRegistry, _connect


def test_legacy_company_receives_missing_document_control_permissions(tmp_path):
    registry = TenantRegistry(tmp_path)
    admin = AdminRepository(registry)
    admin.ensure_company("legacy-company", "Entreprise historique", status="active")

    # Reproduce a company created before the document-control permissions existed.
    with _connect(registry.registry_path) as db:
        db.execute(
            "DELETE FROM company_permissions WHERE tenant_id=? AND permission_key LIKE 'document_control.%'",
            ("legacy-company",),
        )

    assert not any(
        key in admin.get_company_permissions("legacy-company")
        for key in DOCUMENT_CONTROL_PERMISSION_KEYS
    )

    migrated = AdminRepository(registry)
    permissions = migrated.get_company_permissions("legacy-company")

    assert all(permissions[key] is True for key in DOCUMENT_CONTROL_PERMISSION_KEYS)


def test_migration_preserves_an_explicit_document_control_denial(tmp_path):
    registry = TenantRegistry(tmp_path)
    admin = AdminRepository(registry)
    admin.ensure_company("restricted-company", "Entreprise restreinte", status="active")

    with _connect(registry.registry_path) as db:
        db.execute(
            "UPDATE company_permissions SET allowed=0 WHERE tenant_id=? AND permission_key=?",
            ("restricted-company", "document_control.view"),
        )
        db.execute(
            "DELETE FROM company_permissions WHERE tenant_id=? AND permission_key=?",
            ("restricted-company", "document_control.export"),
        )

    migrated = AdminRepository(registry)
    permissions = migrated.get_company_permissions("restricted-company")

    assert permissions["document_control.view"] is False
    assert permissions["document_control.export"] is True
