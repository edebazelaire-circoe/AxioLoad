from __future__ import annotations

import os

from .admin_base import (
    DEFAULT_NEW_COMPANY_PERMISSIONS, PERMISSION_CATALOG, PERMISSION_KEYS, WebContext,
)
from .admin_invitations import AdminInvitationsMixin
from .admin_integrations import AdminIntegrationsMixin
from .admin_permissions import AdminPermissionsMixin
from .admin_reporting import AdminReportingMixin
from .admin_base import AdminBaseMixin
from .persistence import _connect, _hash_secret, _verify_secret, utc_now

SUPER_ADMIN_USER_ID = "axioload-super-admin"
DEFAULT_SUPER_ADMIN_EMAIL = "superadmin@axioload.invalid"
DEFAULT_SUPER_ADMIN_USERNAME = "superadmin"
DEFAULT_SUPER_ADMIN_PASSWORD = ""


class AdminRepository(
    AdminInvitationsMixin, AdminPermissionsMixin, AdminIntegrationsMixin,
    AdminReportingMixin, AdminBaseMixin,
):
    """Transitional SQLite-backed administration boundary."""

    def __init__(self, registry):
        super().__init__(registry)
        self._ensure_super_admin_account()

    @staticmethod
    def super_admin_credentials() -> tuple[str, str, str]:
        email = os.getenv("PLO_SUPER_ADMIN_EMAIL", DEFAULT_SUPER_ADMIN_EMAIL).strip().lower()
        username = os.getenv("PLO_SUPER_ADMIN_USERNAME", DEFAULT_SUPER_ADMIN_USERNAME).strip()
        password = os.getenv("PLO_SUPER_ADMIN_PASSWORD", DEFAULT_SUPER_ADMIN_PASSWORD)
        return (
            email or DEFAULT_SUPER_ADMIN_EMAIL,
            username or DEFAULT_SUPER_ADMIN_USERNAME,
            password,
        )

    def _ensure_super_admin_account(self) -> None:
        """Create or refresh the bootstrap Super Admin account only when configured."""
        email, _username, password = self.super_admin_credentials()
        if not password:
            return
        salt, digest = _hash_secret(password)
        now = utc_now()
        with _connect(self.registry.registry_path) as db:
            row = db.execute(
                "SELECT id FROM company_users WHERE id=?",
                (SUPER_ADMIN_USER_ID,),
            ).fetchone()
            if row:
                db.execute(
                    """UPDATE company_users
                       SET tenant_id='local',first_name='Super',last_name='Admin',email=?,role='super_admin',
                           status='active',active=1,password_salt=?,password_digest=?,
                           activated_at=COALESCE(activated_at,?),disabled_at=NULL
                       WHERE id=?""",
                    (email, salt, digest, now, SUPER_ADMIN_USER_ID),
                )
            else:
                db.execute(
                    """INSERT INTO company_users(
                           id,tenant_id,first_name,last_name,email,role,status,active,
                           password_salt,password_digest,created_at,activated_at
                       ) VALUES (?, 'local','Super','Admin',?,'super_admin','active',1,?,?,?,?)""",
                    (SUPER_ADMIN_USER_ID, email, salt, digest, now, now),
                )

    def authenticate_super_admin(self, identifier: str, password: str) -> dict[str, object]:
        email, username, configured_password = self.super_admin_credentials()
        if not configured_password:
            raise ValueError("Compte super administrateur non configuré")
        normalized = identifier.strip().lower()
        if normalized not in {email.lower(), username.lower()}:
            raise ValueError("Identifiants super administrateur invalides")
        with _connect(self.registry.registry_path) as db:
            row = db.execute(
                "SELECT * FROM company_users WHERE id=? AND active=1",
                (SUPER_ADMIN_USER_ID,),
            ).fetchone()
        if not row or not row["password_salt"] or not _verify_secret(
            password, row["password_salt"], row["password_digest"]
        ):
            raise ValueError("Identifiants super administrateur invalides")
        session_id = self.create_user_session("local", SUPER_ADMIN_USER_ID)
        self.record_activity("local", SUPER_ADMIN_USER_ID, 0, "super_admin_login")
        user = self.get_user(SUPER_ADMIN_USER_ID)
        user["username"] = username
        return {"session_token": session_id, "user": user, "mode": "super_admin"}

    def resolve_user_session(self, session_id: str | None) -> WebContext | None:
        context = super().resolve_user_session(session_id)
        if context and context.actor_id == SUPER_ADMIN_USER_ID:
            email, _username, _password = self.super_admin_credentials()
            return WebContext(
                tenant_id="local",
                actor_id=SUPER_ADMIN_USER_ID,
                actor_label=email,
                actor_type="super_admin",
            )
        return context

    def super_admin_actor(self, session_id: str | None = None) -> str:
        """Resolve the authenticated Super Admin browser session."""
        session = self.resolve_user_session((session_id or "").strip())
        if session and session.is_super_admin:
            return session.actor_label
        raise PermissionError("Connexion super administrateur requise")
