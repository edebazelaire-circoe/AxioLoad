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


class AdminPermissionsMixin:
    def get_company_permissions(self, tenant_id: str) -> dict[str, bool]:
        with _connect(self.registry.registry_path) as db:
            rows = db.execute("SELECT permission_key,allowed FROM company_permissions WHERE tenant_id=?", (tenant_id,)).fetchall()
        return {str(row["permission_key"]): bool(row["allowed"]) for row in rows}

    def set_company_permissions(
        self,
        tenant_id: str,
        permissions: Mapping[str, Any],
        *,
        actor: str,
        audit: bool = True,
    ) -> dict[str, bool]:
        before = self.get_company_permissions(tenant_id)
        normalized = {key: bool(permissions.get(key, before.get(key, False))) for key in PERMISSION_KEYS}
        with _connect(self.registry.registry_path) as db:
            for key, allowed in normalized.items():
                db.execute(
                    """INSERT INTO company_permissions(tenant_id,permission_key,allowed) VALUES (?,?,?)
                       ON CONFLICT(tenant_id,permission_key) DO UPDATE SET allowed=excluded.allowed""",
                    (tenant_id, key, int(allowed)),
                )
        if audit:
            self.audit(tenant_id, actor, "permissions.company.updated", tenant_id, before, normalized)
        return normalized

    def get_user_permissions(self, user_id: str) -> dict[str, str]:
        with _connect(self.registry.registry_path) as db:
            rows = db.execute("SELECT permission_key,state FROM user_permissions WHERE user_id=?", (user_id,)).fetchall()
        values = {key: "inherited" for key in PERMISSION_KEYS}
        values.update({str(row["permission_key"]): str(row["state"]) for row in rows})
        return values

    def set_user_permissions(self, user_id: str, overrides: Mapping[str, str], *, actor: str) -> dict[str, str]:
        user = self.get_user(user_id)
        before = self.get_user_permissions(user_id)
        normalized: dict[str, str] = {}
        with _connect(self.registry.registry_path) as db:
            for key in PERMISSION_KEYS:
                state = str(overrides.get(key, before.get(key, "inherited")))
                if state not in USER_PERMISSION_STATES:
                    raise ValueError(f"État de permission invalide pour {key}")
                normalized[key] = state
                db.execute(
                    """INSERT INTO user_permissions(user_id,permission_key,state) VALUES (?,?,?)
                       ON CONFLICT(user_id,permission_key) DO UPDATE SET state=excluded.state""",
                    (user_id, key, state),
                )
        self.audit(user["tenant_id"], actor, "permissions.user.updated", user_id, before, normalized)
        return normalized

    def effective_permissions(self, tenant_id: str, user_id: str | None) -> dict[str, bool]:
        company = self.get_company_permissions(tenant_id)
        if not user_id:
            return {key: company.get(key, False) for key in PERMISSION_KEYS}
        overrides = self.get_user_permissions(user_id)
        return {
            key: True if overrides[key] == "allow" else False if overrides[key] == "deny" else company.get(key, False)
            for key in PERMISSION_KEYS
        }

    def require_permission(self, context: WebContext, permission_key: str, *, write: bool = False) -> None:
        if permission_key not in PERMISSION_KEYS:
            raise ValueError(permission_key)
        self.assert_company_access(context, write=write)
        if context.is_super_admin or context.tenant_id == "local" and context.actor_id == "local-user":
            return
        if not self.effective_permissions(context.tenant_id, context.actor_id).get(permission_key, False):
            raise PermissionError("Vous ne disposez pas de cette autorisation")

    def submit_profile(self, context: WebContext, payload: Mapping[str, Any]) -> dict[str, Any]:
        if context.is_super_admin:
            raise PermissionError("Le super administrateur ne peut pas modifier les données de base déclarées par le client")
        company = self.get_company(context.tenant_id)
        current = dict(company["profile"])
        candidate = {
            "legal_name": str(payload.get("legal_name") or "").strip(),
            "siret": str(payload.get("siret") or "").strip(),
            "address": str(payload.get("address") or "").strip(),
            "country": str(payload.get("country") or "").strip(),
            "contact_first_name": str(payload.get("contact_first_name") or "").strip(),
            "contact_last_name": str(payload.get("contact_last_name") or "").strip(),
            "phone": str(payload.get("phone") or "").strip(),
            "contact_email": str(payload.get("contact_email") or "").strip().lower(),
        }
        missing = sorted(field for field in REQUIRED_PROFILE_FIELDS if not candidate[field])
        if missing:
            raise ValueError("Champs obligatoires manquants : " + ", ".join(missing))
        changed_sensitive = {key for key in SENSITIVE_PROFILE_FIELDS if candidate.get(key) != current.get(key)}
        initial = company["status"] in {"to_complete", "pending_validation", "correction_required", "invited", "invitation_expired"}
        change_id = str(uuid.uuid4())
        now = utc_now()
        with _connect(self.registry.registry_path) as db:
            db.execute(
                "UPDATE tenants SET name=?,profile_json=?,profile_pending=?,validation_comment=NULL,updated_at=?,status=? WHERE id=?",
                (
                    candidate["legal_name"],
                    self._json(candidate),
                    int(initial or bool(changed_sensitive)),
                    now,
                    "pending_validation" if initial else company["status"],
                    context.tenant_id,
                ),
            )
            if initial or changed_sensitive:
                db.execute(
                    """INSERT INTO profile_changes(id,tenant_id,change_type,previous_json,proposed_json,status,created_at)
                       VALUES (?,?,?,?,?,'pending',?)""",
                    (
                        change_id,
                        context.tenant_id,
                        "initial" if initial else "sensitive_update",
                        self._json({key: current.get(key) for key in SENSITIVE_PROFILE_FIELDS}),
                        self._json({key: candidate.get(key) for key in SENSITIVE_PROFILE_FIELDS}),
                        now,
                    ),
                )
        self.audit(context.tenant_id, context.actor_label, "profile.submitted", context.tenant_id, current, candidate)
        return self.get_company(context.tenant_id)

    def decide_profile(self, tenant_id: str, decision: str, comment: str, actor: str) -> dict[str, Any]:
        if decision not in {"approve", "reject", "request_correction"}:
            raise ValueError("Décision inconnue")
        comment = comment.strip()
        if decision != "approve" and not comment:
            raise ValueError("Un commentaire est obligatoire pour expliquer le refus ou la correction demandée")
        company = self.get_company(tenant_id)
        with _connect(self.registry.registry_path) as db:
            change = db.execute(
                "SELECT * FROM profile_changes WHERE tenant_id=? AND status='pending' ORDER BY created_at DESC LIMIT 1",
                (tenant_id,),
            ).fetchone()
            if not change and not company["profile"]["pending_validation"]:
                raise ValueError("Aucune modification n’est en attente")
            now = utc_now()
            status = company["status"]
            profile = dict(company["profile"])
            if decision == "approve":
                next_status = "active" if status in {"pending_validation", "correction_required", "to_complete"} else status
                db.execute(
                    "UPDATE tenants SET status=?,profile_pending=0,validation_comment=NULL,updated_at=? WHERE id=?",
                    (next_status, now, tenant_id),
                )
            elif change and change["change_type"] == "sensitive_update":
                previous = self._loads(change["previous_json"], {})
                profile.update(previous)
                db.execute(
                    "UPDATE tenants SET name=?,profile_json=?,profile_pending=0,validation_comment=?,updated_at=? WHERE id=?",
                    (profile.get("legal_name") or company["name"], self._json(profile), comment, now, tenant_id),
                )
            else:
                next_status = "refused" if decision == "reject" else "correction_required"
                db.execute(
                    "UPDATE tenants SET status=?,profile_pending=0,validation_comment=?,updated_at=? WHERE id=?",
                    (next_status, comment, now, tenant_id),
                )
            if change:
                db.execute(
                    "UPDATE profile_changes SET status=?,comment=?,decided_at=?,decided_by=? WHERE id=?",
                    (decision, comment, now, actor, change["id"]),
                )
        self.audit(tenant_id, actor, f"profile.{decision}", tenant_id, company["profile"], self.get_company(tenant_id)["profile"])
        return self.get_company(tenant_id)

    def update_company_status(
        self,
        tenant_id: str,
        status: str,
        *,
        actor: str,
        suspension_mode: str = "block",
        reactivate_keys: bool = False,
    ) -> dict[str, Any]:
        if status not in COMPANY_STATUSES:
            raise ValueError("Statut d’entreprise inconnu")
        if suspension_mode not in SUSPENSION_MODES:
            raise ValueError("Mode de suspension inconnu")
        before = self.get_company(tenant_id)
        now = utc_now()
        with _connect(self.registry.registry_path) as db:
            db.execute(
                "UPDATE tenants SET status=?,suspension_mode=?,updated_at=? WHERE id=?",
                (status, suspension_mode, now, tenant_id),
            )
            if status in {"suspended", "archived"}:
                db.execute(
                    "UPDATE api_keys SET suspended_at=COALESCE(suspended_at,?) WHERE tenant_id=? AND revoked_at IS NULL",
                    (now, tenant_id),
                )
            elif status == "active" and reactivate_keys:
                db.execute(
                    """UPDATE api_keys SET suspended_at=NULL WHERE tenant_id=? AND revoked_at IS NULL
                       AND (expires_at IS NULL OR expires_at>?)""",
                    (tenant_id, now),
                )
        self.audit(tenant_id, actor, "company.status.updated", tenant_id, {"status": before["status"]}, {"status": status, "suspension_mode": suspension_mode, "reactivate_keys": reactivate_keys})
        return self.get_company(tenant_id)

    def assert_company_access(self, context: WebContext, *, write: bool) -> None:
        company = self.get_company(context.tenant_id)
        if context.is_super_admin:
            return
        status = company["status"]
        if status == "suspended":
            if company["suspension_mode"] == "block" or write:
                raise PermissionError("L’entreprise est suspendue")
            return
        if status not in {"active"} and context.tenant_id != "local":
            raise PermissionError("L’accès à AxioLoad n’est pas encore actif")

