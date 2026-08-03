from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from .admin_service import AdminRepository, SUPER_ADMIN_USER_ID
from .persistence import _connect, _hash_secret, utc_now

TEST_USER_ID = "axioload-test-user"
DEFAULT_TEST_USER_EMAIL = "olivierbaptiste6@gmail.com"
DEFAULT_TEST_USER_PASSWORD = "0123456789"

_original_init: Callable[..., Any] | None = None
_original_ensure_super_admin_account: Callable[..., Any] | None = None
_original_create_company_invitation: Callable[..., Any] | None = None
_original_invite_user: Callable[..., Any] | None = None
_original_resend_invitation: Callable[..., Any] | None = None


def fixed_test_accounts_enabled() -> bool:
    return os.getenv("PLO_TEST_ACCOUNTS_ONLY", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _table_exists(db: Any, table_name: str) -> bool:
    return bool(
        db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
    )


def _remove_other_account_references(db: Any) -> None:
    allowed = (SUPER_ADMIN_USER_ID, TEST_USER_ID)
    placeholders = "?,?"

    if _table_exists(db, "password_reset_requests"):
        db.execute("DELETE FROM password_reset_requests")
    if _table_exists(db, "invitations"):
        # Fixed test accounts are active immediately. No activation link is retained.
        db.execute("DELETE FROM invitations")
    if _table_exists(db, "user_permissions"):
        db.execute("DELETE FROM user_permissions")
    if _table_exists(db, "user_sessions"):
        # A restart requires a fresh login with the fixed credentials. No former
        # browser session survives the account reset.
        db.execute("DELETE FROM user_sessions")
    if _table_exists(db, "assistance_sessions"):
        db.execute("DELETE FROM assistance_sessions")
    if _table_exists(db, "activity_events"):
        db.execute(
            f"DELETE FROM activity_events WHERE user_id IS NOT NULL AND user_id NOT IN ({placeholders})",
            allowed,
        )
    if _table_exists(db, "vehicle_ownership"):
        db.execute(
            f"UPDATE vehicle_ownership SET owner_user_id=NULL "
            f"WHERE owner_user_id IS NOT NULL AND owner_user_id NOT IN ({placeholders})",
            allowed,
        )

    db.execute(
        f"DELETE FROM company_users WHERE id NOT IN ({placeholders})",
        allowed,
    )


def _upsert_test_user(admin: AdminRepository) -> None:
    email = (
        os.getenv("PLO_TEST_USER_EMAIL", DEFAULT_TEST_USER_EMAIL).strip().lower()
        or DEFAULT_TEST_USER_EMAIL
    )
    password = os.getenv("PLO_TEST_USER_PASSWORD", DEFAULT_TEST_USER_PASSWORD)
    password = password or DEFAULT_TEST_USER_PASSWORD
    salt, digest = _hash_secret(password)
    now = utc_now()

    admin.ensure_company("local", "Entreprise locale", status="active", grant_all=True)

    with _connect(admin.registry.registry_path) as db:
        _remove_other_account_references(db)
        columns = {
            str(row["name"])
            for row in db.execute("PRAGMA table_info(company_users)").fetchall()
        }
        existing = db.execute(
            "SELECT id FROM company_users WHERE id=?",
            (TEST_USER_ID,),
        ).fetchone()
        must_change_update = ",must_change_password=0" if "must_change_password" in columns else ""
        if existing:
            db.execute(
                f"""UPDATE company_users
                    SET tenant_id='local',first_name='Baptiste',last_name='Olivier',
                        email=?,role='member',status='active',active=1,
                        password_salt=?,password_digest=?,activated_at=COALESCE(activated_at,?),
                        disabled_at=NULL{must_change_update}
                    WHERE id=?""",
                (email, salt, digest, now, TEST_USER_ID),
            )
        else:
            fields = (
                "id,tenant_id,first_name,last_name,email,role,status,active,"
                "password_salt,password_digest,created_at,activated_at"
            )
            values = "?, 'local','Baptiste','Olivier',?,'member','active',1,?,?,?,?"
            parameters: list[Any] = [TEST_USER_ID, email, salt, digest, now, now]
            if "must_change_password" in columns:
                fields += ",must_change_password"
                values += ",0"
            db.execute(
                f"INSERT INTO company_users({fields}) VALUES ({values})",
                parameters,
            )

        db.execute(
            "UPDATE tenants SET status='active',active=1,updated_at=? WHERE id='local'",
            (now,),
        )

    # Remove unused legacy credentials from tenant databases. Portal accounts live
    # exclusively in company_users during this test phase.
    for tenant in admin._tenant_rows(include_archived=True):
        try:
            tenant_path = admin.registry.tenant_path(str(tenant["id"]))
        except KeyError:
            continue
        with _connect(tenant_path) as tenant_db:
            if _table_exists(tenant_db, "users"):
                tenant_db.execute("DELETE FROM users")


def install_fixed_test_accounts() -> None:
    global _original_init
    global _original_ensure_super_admin_account
    global _original_create_company_invitation
    global _original_invite_user
    global _original_resend_invitation

    if getattr(AdminRepository, "_axioload_fixed_test_accounts", False):
        return

    _original_init = AdminRepository.__init__
    _original_ensure_super_admin_account = AdminRepository._ensure_super_admin_account
    _original_create_company_invitation = AdminRepository.create_company_invitation
    _original_invite_user = AdminRepository.invite_user
    _original_resend_invitation = AdminRepository.resend_invitation

    def ensure_super_admin_account(self: AdminRepository) -> None:
        if fixed_test_accounts_enabled():
            with _connect(self.registry.registry_path) as db:
                _remove_other_account_references(db)
        assert _original_ensure_super_admin_account is not None
        _original_ensure_super_admin_account(self)

    def repository_init(self: AdminRepository, registry: Any) -> None:
        assert _original_init is not None
        _original_init(self, registry)
        if fixed_test_accounts_enabled():
            _upsert_test_user(self)

    def create_company_invitation(self: AdminRepository, *args: Any, **kwargs: Any) -> Any:
        if fixed_test_accounts_enabled():
            raise PermissionError(
                "Mode de test à deux comptes : la création d’une entreprise est temporairement désactivée"
            )
        assert _original_create_company_invitation is not None
        return _original_create_company_invitation(self, *args, **kwargs)

    def invite_user(self: AdminRepository, *args: Any, **kwargs: Any) -> Any:
        if fixed_test_accounts_enabled():
            raise PermissionError(
                "Mode de test à deux comptes : l’ajout d’un utilisateur est temporairement désactivé"
            )
        assert _original_invite_user is not None
        return _original_invite_user(self, *args, **kwargs)

    def resend_invitation(self: AdminRepository, *args: Any, **kwargs: Any) -> Any:
        if fixed_test_accounts_enabled():
            raise PermissionError(
                "Mode de test à deux comptes : aucune invitation n’est utilisée"
            )
        assert _original_resend_invitation is not None
        return _original_resend_invitation(self, *args, **kwargs)

    AdminRepository._ensure_super_admin_account = ensure_super_admin_account  # type: ignore[method-assign]
    AdminRepository.__init__ = repository_init  # type: ignore[method-assign]
    AdminRepository.create_company_invitation = create_company_invitation  # type: ignore[method-assign]
    AdminRepository.invite_user = invite_user  # type: ignore[method-assign]
    AdminRepository.resend_invitation = resend_invitation  # type: ignore[method-assign]
    AdminRepository._axioload_fixed_test_accounts = True  # type: ignore[attr-defined]
