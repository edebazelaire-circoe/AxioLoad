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


class AdminIntegrationsMixin:
    def create_api_key(
        self,
        tenant_id: str,
        label: str,
        scopes: Iterable[str],
        expires_at: str | None,
        actor: str,
    ) -> dict[str, Any]:
        label = label.strip()
        if not label:
            raise ValueError("Le nom de la clé est obligatoire")
        company_permissions = self.get_company_permissions(tenant_id)
        if not company_permissions.get("api.use", False):
            raise ValueError("L’accès API doit être activé pour l’entreprise avant de créer une clé")
        normalized_scopes = sorted({scope for scope in scopes if scope in PERMISSION_KEYS and scope != "api.use"})
        forbidden = [scope for scope in normalized_scopes if not company_permissions.get(scope, False)]
        if forbidden:
            raise ValueError("La clé ne peut pas dépasser les droits de l’entreprise : " + ", ".join(forbidden))
        if not normalized_scopes:
            raise ValueError("Sélectionnez au moins un droit pour la clé API")
        if expires_at:
            expiration = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if expiration.tzinfo is None:
                expiration = expiration.replace(tzinfo=UTC)
            if expiration <= datetime.now(UTC):
                raise ValueError("La date d’expiration doit être future")
            expires_at = expiration.isoformat()
        prefix = secrets.token_hex(5)
        secret = secrets.token_urlsafe(36)
        salt, digest = _hash_secret(secret)
        key_id = str(uuid.uuid4())
        hint = secret[-4:]
        now = utc_now()
        company_status = self.get_company(tenant_id)["status"]
        suspended_at = now if company_status != "active" else None
        with _connect(self.registry.registry_path) as db:
            db.execute(
                """INSERT INTO api_keys(id,tenant_id,label,prefix,salt,digest,created_at,scopes_json,expires_at,secret_hint,suspended_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (key_id, tenant_id, label, prefix, salt, digest, now, self._json(normalized_scopes), expires_at, hint, suspended_at),
            )
        self.audit(tenant_id, actor, "api_key.created", key_id, {}, {"label": label, "prefix": prefix, "scopes": normalized_scopes, "expires_at": expires_at})
        return {
            "id": key_id,
            "label": label,
            "prefix": prefix,
            "secret_hint": hint,
            "scopes": normalized_scopes,
            "expires_at": expires_at,
            "secret": f"axio_{prefix}_{secret}",
            "secret_visible_once": True,
        }

    def list_api_keys(self, tenant_id: str) -> list[dict[str, Any]]:
        with _connect(self.registry.registry_path) as db:
            rows = db.execute("SELECT * FROM api_keys WHERE tenant_id=? ORDER BY created_at DESC", (tenant_id,)).fetchall()
        now = datetime.now(UTC)
        output = []
        for row in rows:
            expired = bool(row["expires_at"] and datetime.fromisoformat(row["expires_at"]) <= now)
            output.append(
                {
                    "id": row["id"],
                    "label": row["label"],
                    "prefix": row["prefix"],
                    "masked": f"axio_{row['prefix']}_••••{row['secret_hint'] or ''}",
                    "scopes": self._loads(row["scopes_json"], []),
                    "created_at": row["created_at"],
                    "expires_at": row["expires_at"],
                    "last_used_at": row["last_used_at"],
                    "revoked_at": row["revoked_at"],
                    "suspended_at": row["suspended_at"],
                    "expired": expired,
                    "active": not expired and not row["revoked_at"] and not row["suspended_at"],
                }
            )
        return output

    def revoke_api_key(self, tenant_id: str, key_id: str, actor: str) -> None:
        with _connect(self.registry.registry_path) as db:
            result = db.execute(
                "UPDATE api_keys SET revoked_at=? WHERE id=? AND tenant_id=? AND revoked_at IS NULL",
                (utc_now(), key_id, tenant_id),
            )
        if result.rowcount != 1:
            raise KeyError(key_id)
        self.audit(tenant_id, actor, "api_key.revoked", key_id, {}, {})

    def resolve_api_key(self, api_key: str, required_scope: str) -> str | None:
        parts = api_key.split("_", 2)
        if len(parts) != 3 or parts[0] != "axio":
            return None
        _, prefix, secret = parts
        with _connect(self.registry.registry_path) as db:
            row = db.execute(
                """SELECT k.*,t.status FROM api_keys k JOIN tenants t ON t.id=k.tenant_id
                   WHERE k.prefix=? AND k.revoked_at IS NULL AND k.suspended_at IS NULL""",
                (prefix,),
            ).fetchone()
            if not row or row["status"] != "active":
                return None
            if row["expires_at"] and datetime.fromisoformat(row["expires_at"]) <= datetime.now(UTC):
                return None
            scopes = self._loads(row["scopes_json"], [])
            company_permissions = self.get_company_permissions(str(row["tenant_id"]))
            if not company_permissions.get("api.use", False) or not company_permissions.get(required_scope, False):
                return None
            if required_scope not in scopes or not _verify_secret(secret, row["salt"], row["digest"]):
                return None
            db.execute("UPDATE api_keys SET last_used_at=? WHERE id=?", (utc_now(), row["id"]))
        return str(row["tenant_id"])

    def start_assistance(self, tenant_id: str, actor: str) -> str:
        self.get_company(tenant_id)
        session_id = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        with _connect(self.registry.registry_path) as db:
            db.execute(
                "INSERT INTO assistance_sessions(id,tenant_id,actor,created_at,expires_at) VALUES (?,?,?,?,?)",
                (session_id, tenant_id, actor, now.isoformat(), (now + timedelta(hours=8)).isoformat()),
            )
        self.audit(tenant_id, actor, "assistance.started", session_id, {}, {})
        return session_id

    def resolve_assistance(self, session_id: str | None) -> WebContext | None:
        if not session_id:
            return None
        with _connect(self.registry.registry_path) as db:
            row = db.execute(
                "SELECT * FROM assistance_sessions WHERE id=? AND ended_at IS NULL AND expires_at>?",
                (session_id, utc_now()),
            ).fetchone()
        if not row:
            return None
        return WebContext(
            tenant_id=str(row["tenant_id"]),
            actor_id=str(row["actor"]),
            actor_label=str(row["actor"]),
            actor_type="super_admin",
            assistance_session_id=str(row["id"]),
        )

    def end_assistance(self, session_id: str | None) -> None:
        if not session_id:
            return
        with _connect(self.registry.registry_path) as db:
            row = db.execute("SELECT tenant_id,actor FROM assistance_sessions WHERE id=?", (session_id,)).fetchone()
            db.execute("UPDATE assistance_sessions SET ended_at=? WHERE id=? AND ended_at IS NULL", (utc_now(), session_id))
        if row:
            self.audit(str(row["tenant_id"]), str(row["actor"]), "assistance.ended", session_id, {}, {})

    def resolve_web_context(self, assistance_token: str | None, user_session: str | None) -> WebContext:
        assistance = self.resolve_assistance(assistance_token)
        if assistance:
            return assistance
        user = self.resolve_user_session(user_session)
        if user:
            return user
        return WebContext("local", "local-user", "Utilisateur local", "user")

    def super_admin_actor(self, provided_token: str | None) -> str:
        expected = os.getenv("PLO_SUPER_ADMIN_TOKEN", "").strip()
        if not expected:
            raise PermissionError("Le jeton super administrateur PLO_SUPER_ADMIN_TOKEN doit être configuré sur le serveur")
        if not provided_token:
            raise PermissionError("Jeton super administrateur requis")
        candidate = provided_token or ""
        if candidate.startswith("Bearer "):
            candidate = candidate[7:]
        if not secrets.compare_digest(candidate, expected):
            raise PermissionError("Jeton super administrateur invalide")
        return os.getenv("PLO_SUPER_ADMIN_EMAIL", "superadmin@axioload.local")

    def email_configuration(self) -> dict[str, Any]:
        with _connect(self.registry.registry_path) as db:
            row = db.execute("SELECT value_json FROM admin_settings WHERE setting_key='smtp' ").fetchone()
        value = self._loads(row["value_json"], {}) if row else {}
        config = {
            "host": str(value.get("host") or ""),
            "port": value.get("port"),
            "sender": str(value.get("sender") or ""),
            "username": str(value.get("username") or ""),
            "tls": bool(value.get("tls", True)),
        }
        config["configured"] = bool(config["host"] and config["port"] and config["sender"])
        return config

    def _ensure_vehicle_metadata(self, tenant_id: str) -> None:
        global_ids = {vehicle.model_id for vehicle in default_vehicle_catalog()}
        try:
            current = self.registry.list_vehicles(tenant_id)
        except KeyError:
            return
        now = utc_now()
        with _connect(self.registry.registry_path) as db:
            for vehicle in current:
                origin = "global" if vehicle.model_id in global_ids else "custom"
                db.execute(
                    """INSERT OR IGNORE INTO vehicle_ownership(tenant_id,model_id,origin,created_at)
                       VALUES (?,?,?,?)""",
                    (tenant_id, vehicle.model_id, origin, now),
                )

    def list_vehicles(self, context: WebContext) -> list[dict[str, Any]]:
        self._ensure_vehicle_metadata(context.tenant_id)
        with _connect(self.registry.registry_path) as db:
            ownership = {
                str(row["model_id"]): row
                for row in db.execute(
                    "SELECT * FROM vehicle_ownership WHERE tenant_id=? AND deleted_at IS NULL",
                    (context.tenant_id,),
                ).fetchall()
            }
        output = []
        legacy_local = context.tenant_id == "local" and context.actor_id == "local-user"
        for vehicle in self.registry.list_vehicles(context.tenant_id):
            payload = vehicle_to_payload(vehicle)
            meta = ownership.get(vehicle.model_id)
            origin = str(meta["origin"]) if meta else "custom"
            owner = str(meta["owner_user_id"]) if meta and meta["owner_user_id"] else None
            payload.update(
                {
                    "origin": origin,
                    "owner_user_id": owner,
                    "base_model_id": str(meta["base_model_id"]) if meta and meta["base_model_id"] else None,
                    "can_edit": legacy_local or context.is_super_admin or origin == "custom" and owner == context.actor_id,
                    "can_delete": legacy_local or context.is_super_admin or origin == "custom" and owner == context.actor_id,
                }
            )
            output.append(payload)
        return output

    def save_vehicle(self, context: WebContext, payload: Mapping[str, Any]) -> dict[str, Any]:
        model_id = str(payload.get("model_id") or "").strip().lower()
        if not model_id:
            raise ValueError("Identifiant véhicule obligatoire")
        self._ensure_vehicle_metadata(context.tenant_id)
        with _connect(self.registry.registry_path) as db:
            meta = db.execute(
                "SELECT * FROM vehicle_ownership WHERE tenant_id=? AND model_id=? AND deleted_at IS NULL",
                (context.tenant_id, model_id),
            ).fetchone()
        legacy_local = context.tenant_id == "local" and context.actor_id == "local-user"
        if meta and meta["origin"] == "global" and not legacy_local:
            raise PermissionError("Les véhicules globaux sont verrouillés. Dupliquez le modèle pour le personnaliser")
        if meta and not context.is_super_admin and meta["owner_user_id"] != context.actor_id and not legacy_local:
            raise PermissionError("Seul le créateur ou le super administrateur peut modifier ce véhicule")
        vehicle = self.registry.save_vehicle(context.tenant_id, payload, actor=context.actor_label)
        with _connect(self.registry.registry_path) as db:
            db.execute(
                """INSERT INTO vehicle_ownership(tenant_id,model_id,origin,owner_user_id,created_at)
                   VALUES (?,?, 'custom',?,?)
                   ON CONFLICT(tenant_id,model_id) DO UPDATE SET deleted_at=NULL""",
                (context.tenant_id, vehicle.model_id, context.actor_id, utc_now()),
            )
        return next(entry for entry in self.list_vehicles(context) if entry["model_id"] == vehicle.model_id)

    def duplicate_vehicle(self, context: WebContext, model_id: str, new_model_id: str, name: str) -> dict[str, Any]:
        source = next((item for item in self.list_vehicles(context) if item["model_id"] == model_id), None)
        if not source:
            raise KeyError(model_id)
        if source["origin"] != "global":
            raise ValueError("Seuls les modèles globaux sont dupliqués par cette action")
        candidate = dict(source)
        for key in ("origin", "owner_user_id", "base_model_id", "can_edit", "can_delete", "version"):
            candidate.pop(key, None)
        candidate["model_id"] = new_model_id.strip().lower()
        candidate["name"] = name.strip() or f"{source['name']} personnalisé"
        vehicle = self.registry.save_vehicle(context.tenant_id, candidate, actor=context.actor_label)
        with _connect(self.registry.registry_path) as db:
            db.execute(
                """INSERT INTO vehicle_ownership(tenant_id,model_id,origin,owner_user_id,base_model_id,created_at)
                   VALUES (?,?, 'custom',?,?,?)""",
                (context.tenant_id, vehicle.model_id, context.actor_id, model_id, utc_now()),
            )
        self.audit(context.tenant_id, context.actor_label, "vehicle.duplicated", vehicle.model_id, {"base_model_id": model_id}, vehicle_to_payload(vehicle))
        return next(entry for entry in self.list_vehicles(context) if entry["model_id"] == vehicle.model_id)

    def delete_vehicle(self, context: WebContext, model_id: str) -> None:
        with _connect(self.registry.registry_path) as db:
            meta = db.execute(
                "SELECT * FROM vehicle_ownership WHERE tenant_id=? AND model_id=? AND deleted_at IS NULL",
                (context.tenant_id, model_id),
            ).fetchone()
        if not meta:
            raise KeyError(model_id)
        legacy_local = context.tenant_id == "local" and context.actor_id == "local-user"
        if meta["origin"] == "global" and not legacy_local:
            raise PermissionError("Un véhicule global ne peut pas être supprimé")
        if not context.is_super_admin and meta["owner_user_id"] != context.actor_id and not legacy_local:
            raise PermissionError("Seul le créateur ou le super administrateur peut supprimer ce véhicule")
        snapshot = vehicle_to_payload(self.registry.get_vehicle(context.tenant_id, model_id))
        self.registry.delete_vehicle(context.tenant_id, model_id, actor=context.actor_label)
        with _connect(self.registry.registry_path) as db:
            db.execute(
                "UPDATE vehicle_ownership SET deleted_at=? WHERE tenant_id=? AND model_id=?",
                (utc_now(), context.tenant_id, model_id),
            )
        self.audit(context.tenant_id, context.actor_label, "vehicle.deleted", model_id, snapshot, {})

    @staticmethod
    def _vehicle_ids(value: Any) -> set[str]:
        ids: set[str] = set()
        if isinstance(value, Mapping):
            for key, nested in value.items():
                if key in {"forced_vehicle_id", "vehicle_version_id", "vehicle_model_id", "vehicle_id"} and isinstance(nested, str):
                    ids.add(nested.rsplit("@", 1)[0])
                ids.update(AdminIntegrationsMixin._vehicle_ids(nested))
        elif isinstance(value, (list, tuple)):
            for nested in value:
                ids.update(AdminIntegrationsMixin._vehicle_ids(nested))
        return ids

    def vehicle_snapshot(
        self,
        context: WebContext,
        request_payload: Mapping[str, Any],
        result_payload: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        ids = self._vehicle_ids(request_payload)
        if result_payload:
            ids.update(self._vehicle_ids(result_payload))
        vehicles = {item["model_id"]: item for item in self.list_vehicles(context)}
        return [vehicles[model_id] for model_id in sorted(ids) if model_id in vehicles]

    def annotate_run(self, context: WebContext, run_id: str, request_payload: Mapping[str, Any]) -> None:
        self._ensure_history_columns(context.tenant_id)
        with _connect(self.registry.tenant_path(context.tenant_id)) as db:
            row = db.execute("SELECT result_json FROM optimization_runs WHERE id=?", (run_id,)).fetchone()
            result_payload = self._loads(row["result_json"], {}) if row else {}
            snapshot = self.vehicle_snapshot(context, request_payload, result_payload)
            result = db.execute(
                """UPDATE optimization_runs SET created_by_type=?,created_by_id=?,created_by=?,vehicle_snapshot_json=?,
                   admin_touched_at=CASE WHEN ?='super_admin' THEN ? ELSE admin_touched_at END,
                   admin_touched_by=CASE WHEN ?='super_admin' THEN ? ELSE admin_touched_by END
                   WHERE id=?""",
                (
                    context.actor_type,
                    context.actor_id,
                    context.actor_label,
                    self._json(snapshot),
                    context.actor_type,
                    utc_now(),
                    context.actor_type,
                    context.actor_label,
                    run_id,
                ),
            )
        if result.rowcount == 1 and context.is_super_admin:
            self.registry.audit(context.tenant_id, context.actor_label, "optimization.support_created", run_id, {"vehicle_snapshot": snapshot})

    def touch_run(self, context: WebContext, run_id: str, action: str, details: Mapping[str, Any] | None = None) -> None:
        if not context.is_super_admin:
            return
        self._ensure_history_columns(context.tenant_id)
        with _connect(self.registry.tenant_path(context.tenant_id)) as db:
            db.execute(
                "UPDATE optimization_runs SET admin_touched_at=?,admin_touched_by=? WHERE id=?",
                (utc_now(), context.actor_label, run_id),
            )
        self.registry.audit(context.tenant_id, context.actor_label, f"optimization.support_{action}", run_id, details or {})

    def record_activity(self, tenant_id: str, user_id: str | None, active_seconds: int, event_type: str = "activity") -> None:
        seconds = min(max(int(active_seconds), 0), 900)
        with _connect(self.registry.registry_path) as db:
            db.execute(
                "INSERT INTO activity_events(id,tenant_id,user_id,event_type,active_seconds,created_at) VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), tenant_id, user_id, event_type, seconds, utc_now()),
            )
