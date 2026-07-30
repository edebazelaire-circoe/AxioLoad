from __future__ import annotations

import json
import os
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable, Mapping

from .catalog import default_vehicle_catalog, vehicle_to_payload
from .persistence import TenantRegistry, _connect, _hash_secret, _verify_secret, utc_now

from .admin_base import (
    COMPANY_STATUSES, DEFAULT_NEW_COMPANY_PERMISSIONS, PERMISSION_KEYS, REQUIRED_PROFILE_FIELDS,
    SENSITIVE_PROFILE_FIELDS, SUSPENSION_MODES, USER_PERMISSION_STATES, WebContext,
)


class AdminInvitationsMixin:
    def create_company_invitation(
        self,
        company_name: str,
        email: str,
        first_name: str,
        last_name: str,
        permissions: Mapping[str, Any] | None,
        actor: str,
        base_url: str,
    ) -> dict[str, Any]:
        company_name = company_name.strip()
        email = email.strip().lower()
        if not company_name or "@" not in email:
            raise ValueError("Le nom de l’entreprise et une adresse e-mail valide sont obligatoires")
        tenant_id = self._unique_tenant_id(company_name)
        self.registry.create_tenant(tenant_id, company_name)
        now = utc_now()
        with _connect(self.registry.registry_path) as db:
            db.execute(
                "UPDATE tenants SET status='invited',suspension_mode='block',updated_at=? WHERE id=?",
                (now, tenant_id),
            )
        self.set_company_permissions(
            tenant_id,
            permissions or DEFAULT_NEW_COMPANY_PERMISSIONS,
            actor=actor,
            audit=False,
        )
        self._ensure_vehicle_metadata(tenant_id)
        self._ensure_history_columns(tenant_id)
        user = self._create_user(
            tenant_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            role="primary",
        )
        invitation = self._issue_invitation(tenant_id, user["id"], base_url)
        self.audit(tenant_id, actor, "company.invited", tenant_id, {}, {"name": company_name, "email": email})
        return {
            "company": self.get_company(tenant_id),
            "user": user,
            "invitation": invitation,
            "email_delivery": "ready" if self.email_configuration()["configured"] else "smtp_not_configured",
        }

    def _create_user(self, tenant_id: str, *, first_name: str, last_name: str, email: str, role: str) -> dict[str, Any]:
        first_name = first_name.strip()
        last_name = last_name.strip()
        email = email.strip().lower()
        if not first_name or not last_name or "@" not in email:
            raise ValueError("Nom, prénom et adresse e-mail sont obligatoires")
        user_id = str(uuid.uuid4())
        with _connect(self.registry.registry_path) as db:
            db.execute(
                """INSERT INTO company_users(id,tenant_id,first_name,last_name,email,role,status,active,created_at)
                   VALUES (?,?,?,?,?,?, 'invited',0,?)""",
                (user_id, tenant_id, first_name, last_name, email, role, utc_now()),
            )
        return self.get_user(user_id)

    def invite_user(
        self,
        tenant_id: str,
        *,
        first_name: str,
        last_name: str,
        email: str,
        overrides: Mapping[str, str] | None,
        actor: str,
        base_url: str,
    ) -> dict[str, Any]:
        self.get_company(tenant_id)
        user = self._create_user(
            tenant_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            role="member",
        )
        if overrides:
            self.set_user_permissions(user["id"], overrides, actor=actor)
        invitation = self._issue_invitation(tenant_id, user["id"], base_url)
        self.audit(tenant_id, actor, "user.invited", user["id"], {}, {"email": email})
        return {
            "user": self.get_user(user["id"]),
            "invitation": invitation,
            "email_delivery": "ready" if self.email_configuration()["configured"] else "smtp_not_configured",
        }

    def _issue_invitation(self, tenant_id: str, user_id: str, base_url: str) -> dict[str, Any]:
        prefix = secrets.token_hex(5)
        secret = secrets.token_urlsafe(32)
        salt, digest = _hash_secret(secret)
        now = datetime.now(UTC)
        expires = now + timedelta(hours=24)
        invitation_id = str(uuid.uuid4())
        with _connect(self.registry.registry_path) as db:
            db.execute(
                "UPDATE invitations SET invalidated_at=? WHERE user_id=? AND used_at IS NULL AND invalidated_at IS NULL",
                (now.isoformat(), user_id),
            )
            db.execute(
                """INSERT INTO invitations(id,tenant_id,user_id,prefix,salt,digest,expires_at,created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (invitation_id, tenant_id, user_id, prefix, salt, digest, expires.isoformat(), now.isoformat()),
            )
            db.execute(
                "UPDATE company_users SET status='invited',active=0 WHERE id=?",
                (user_id,),
            )
            db.execute(
                "UPDATE tenants SET status=CASE WHEN status IN ('draft','invitation_expired') THEN 'invited' ELSE status END,updated_at=? WHERE id=?",
                (now.isoformat(), tenant_id),
            )
        token = f"axio_inv_{prefix}_{secret}"
        return {
            "id": invitation_id,
            "expires_at": expires.isoformat(),
            "activation_url": f"{base_url.rstrip('/')}/activate?token={token}",
            "token_visible_once": True,
        }

    def resend_invitation(self, tenant_id: str, user_id: str, actor: str, base_url: str) -> dict[str, Any]:
        user = self.get_user(user_id)
        if user["tenant_id"] != tenant_id:
            raise KeyError(user_id)
        invitation = self._issue_invitation(tenant_id, user_id, base_url)
        self.audit(tenant_id, actor, "invitation.resent", user_id, {}, {"expires_at": invitation["expires_at"]})
        return invitation

    def refresh_expired_invitations(self) -> None:
        now = utc_now()
        with _connect(self.registry.registry_path) as db:
            rows = db.execute(
                """SELECT DISTINCT tenant_id,user_id FROM invitations
                   WHERE used_at IS NULL AND invalidated_at IS NULL AND expires_at < ?""",
                (now,),
            ).fetchall()
            for row in rows:
                db.execute("UPDATE company_users SET status='invitation_expired' WHERE id=? AND active=0", (row["user_id"],))
                company = db.execute("SELECT status FROM tenants WHERE id=?", (row["tenant_id"],)).fetchone()
                if company and company["status"] == "invited":
                    db.execute("UPDATE tenants SET status='invitation_expired',updated_at=? WHERE id=?", (now, row["tenant_id"]))

    def _invitation_row(self, token: str) -> tuple[Any, str]:
        parts = token.split("_", 3)
        if len(parts) != 4 or parts[:2] != ["axio", "inv"]:
            raise ValueError("Lien d’activation invalide")
        prefix, secret = parts[2], parts[3]
        with _connect(self.registry.registry_path) as db:
            row = db.execute(
                "SELECT * FROM invitations WHERE prefix=? AND used_at IS NULL AND invalidated_at IS NULL",
                (prefix,),
            ).fetchone()
        if not row or not _verify_secret(secret, row["salt"], row["digest"]):
            raise ValueError("Lien d’activation invalide")
        if datetime.fromisoformat(row["expires_at"]) < datetime.now(UTC):
            self.refresh_expired_invitations()
            raise ValueError("Le lien d’activation a expiré")
        return row, secret

    def invitation_preview(self, token: str) -> dict[str, Any]:
        row, _ = self._invitation_row(token)
        user = self.get_user(str(row["user_id"]))
        company = self.get_company(str(row["tenant_id"]))
        return {
            "company": {"id": company["id"], "name": company["name"]},
            "user": {key: user[key] for key in ("id", "first_name", "last_name", "email", "role")},
            "expires_at": row["expires_at"],
            "needs_company_profile": user["role"] == "primary",
        }

    def activate_invitation(self, token: str, password: str) -> dict[str, Any]:
        if len(password) < 10:
            raise ValueError("Le mot de passe doit contenir au moins 10 caractères")
        invitation, _ = self._invitation_row(token)
        salt, digest = _hash_secret(password)
        now = utc_now()
        tenant_id = str(invitation["tenant_id"])
        user_id = str(invitation["user_id"])
        with _connect(self.registry.registry_path) as db:
            user = db.execute("SELECT role FROM company_users WHERE id=?", (user_id,)).fetchone()
            db.execute(
                """UPDATE company_users SET password_salt=?,password_digest=?,status='active',active=1,
                   activated_at=?,disabled_at=NULL WHERE id=?""",
                (salt, digest, now, user_id),
            )
            db.execute("UPDATE invitations SET used_at=? WHERE id=?", (now, invitation["id"]))
            if user and user["role"] == "primary":
                db.execute("UPDATE tenants SET status='to_complete',updated_at=? WHERE id=?", (now, tenant_id))
        session = self.create_user_session(tenant_id, user_id)
        self.audit(tenant_id, self.get_user(user_id)["email"], "invitation.activated", user_id, {}, {})
        return {
            "tenant_id": tenant_id,
            "user": self.get_user(user_id),
            "session_token": session,
            "needs_company_profile": self.get_user(user_id)["role"] == "primary",
        }

    def authenticate(self, tenant_id: str, email: str, password: str) -> dict[str, Any]:
        with _connect(self.registry.registry_path) as db:
            row = db.execute(
                "SELECT * FROM company_users WHERE tenant_id=? AND email=? AND active=1",
                (tenant_id, email.strip().lower()),
            ).fetchone()
        if not row or not row["password_salt"] or not _verify_secret(password, row["password_salt"], row["password_digest"]):
            raise ValueError("Identifiants invalides")
        token = self.create_user_session(tenant_id, str(row["id"]))
        self.record_activity(tenant_id, str(row["id"]), 0, "login")
        return {"session_token": token, "user": self.get_user(str(row["id"]))}

    def create_user_session(self, tenant_id: str, user_id: str) -> str:
        session_id = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        with _connect(self.registry.registry_path) as db:
            db.execute(
                "INSERT INTO user_sessions(id,tenant_id,user_id,created_at,expires_at) VALUES (?,?,?,?,?)",
                (session_id, tenant_id, user_id, now.isoformat(), (now + timedelta(days=30)).isoformat()),
            )
        return session_id

    def end_user_session(self, token: str | None) -> None:
        if not token:
            return
        with _connect(self.registry.registry_path) as db:
            db.execute("UPDATE user_sessions SET ended_at=? WHERE id=? AND ended_at IS NULL", (utc_now(), token))

    def resolve_user_session(self, token: str | None) -> WebContext | None:
        if not token:
            return None
        with _connect(self.registry.registry_path) as db:
            row = db.execute(
                """SELECT s.*,u.first_name,u.last_name,u.email,u.active FROM user_sessions s
                   JOIN company_users u ON u.id=s.user_id
                   WHERE s.id=? AND s.ended_at IS NULL AND s.expires_at>?""",
                (token, utc_now()),
            ).fetchone()
        if not row or not row["active"]:
            return None
        return WebContext(
            tenant_id=str(row["tenant_id"]),
            actor_id=str(row["user_id"]),
            actor_label=f"{row['first_name']} {row['last_name']}".strip() or row["email"],
            actor_type="user",
        )

    def get_user(self, user_id: str) -> dict[str, Any]:
        with _connect(self.registry.registry_path) as db:
            row = db.execute("SELECT * FROM company_users WHERE id=?", (user_id,)).fetchone()
        if not row:
            raise KeyError(user_id)
        overrides = self.get_user_permissions(user_id)
        return {
            "id": row["id"],
            "tenant_id": row["tenant_id"],
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "email": row["email"],
            "role": row["role"],
            "status": row["status"],
            "active": bool(row["active"]),
            "created_at": row["created_at"],
            "activated_at": row["activated_at"],
            "disabled_at": row["disabled_at"],
            "transfer_to_user_id": row["transfer_to_user_id"],
            "permission_overrides": overrides,
            "effective_permissions": self.effective_permissions(str(row["tenant_id"]), user_id),
        }

    def list_users(self, tenant_id: str) -> list[dict[str, Any]]:
        with _connect(self.registry.registry_path) as db:
            rows = db.execute("SELECT id FROM company_users WHERE tenant_id=? ORDER BY role DESC,last_name,first_name", (tenant_id,)).fetchall()
        return [self.get_user(str(row["id"])) for row in rows]

    def disable_user(self, tenant_id: str, user_id: str, actor: str, transfer_to_user_id: str | None = None) -> dict[str, Any]:
        user = self.get_user(user_id)
        if user["tenant_id"] != tenant_id:
            raise KeyError(user_id)
        if transfer_to_user_id:
            target = self.get_user(transfer_to_user_id)
            if target["tenant_id"] != tenant_id or not target["active"]:
                raise ValueError("Le nouvel utilisateur responsable doit être actif dans la même entreprise")
        now = utc_now()
        with _connect(self.registry.registry_path) as db:
            db.execute(
                "UPDATE company_users SET active=0,status='disabled',disabled_at=?,transfer_to_user_id=? WHERE id=?",
                (now, transfer_to_user_id, user_id),
            )
            db.execute("UPDATE user_sessions SET ended_at=? WHERE user_id=? AND ended_at IS NULL", (now, user_id))
            if transfer_to_user_id:
                db.execute(
                    "UPDATE vehicle_ownership SET owner_user_id=? WHERE tenant_id=? AND owner_user_id=? AND origin='custom'",
                    (transfer_to_user_id, tenant_id, user_id),
                )
        self.audit(tenant_id, actor, "user.disabled", user_id, user, {"transfer_to_user_id": transfer_to_user_id})
        return self.get_user(user_id)

