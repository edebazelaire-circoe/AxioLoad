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

COMPANY_STATUSES = {"draft", "invited", "invitation_expired", "to_complete", "pending_validation", "correction_required", "active", "suspended", "archived", "refused"}
USER_STATUSES = {"invited", "invitation_expired", "active", "disabled"}
SUSPENSION_MODES = {"block", "read_only"}
USER_PERMISSION_STATES = {"inherited", "allow", "deny"}
SENSITIVE_PROFILE_FIELDS = {"legal_name", "address", "country"}
REQUIRED_PROFILE_FIELDS = {"legal_name", "address", "country", "contact_first_name", "contact_last_name", "phone", "contact_email"}
PERMISSION_CATALOG: tuple[dict[str, str], ...] = (
    {"key": "vehicles.view", "module": "vehicles", "label": "Consulter les véhicules"},
    {"key": "vehicles.create", "module": "vehicles", "label": "Créer un véhicule personnalisé"},
    {"key": "vehicles.edit", "module": "vehicles", "label": "Modifier ses véhicules"},
    {"key": "vehicles.delete", "module": "vehicles", "label": "Supprimer ses véhicules"},
    {"key": "data.view", "module": "data", "label": "Accéder aux données"},
    {"key": "data.edit", "module": "data", "label": "Modifier les données"},
    {"key": "data.import", "module": "data", "label": "Importer CSV/XLSX"},
    {"key": "results.view", "module": "results", "label": "Consulter les résultats"},
    {"key": "results.run", "module": "results", "label": "Lancer un chargement"},
    {"key": "history.view", "module": "history", "label": "Consulter l’historique"},
    {"key": "history.validate", "module": "history", "label": "Valider une optimisation"},
    {"key": "history.delete", "module": "history", "label": "Supprimer un historique"},
    {"key": "route.view", "module": "route", "label": "Consulter l’itinéraire"},
    {"key": "route.run", "module": "route", "label": "Lancer un itinéraire"},
    {"key": "total.view", "module": "total", "label": "Consulter l’optimisation totale"},
    {"key": "total.run", "module": "total", "label": "Lancer une optimisation totale"},
    {"key": "exports.use", "module": "exports", "label": "Exporter les résultats"},
    {"key": "api.use", "module": "api", "label": "Utiliser l’API"},
    {"key": "settings.view", "module": "settings", "label": "Consulter les paramètres"},
    {"key": "settings.edit", "module": "settings", "label": "Modifier les paramètres"},
)
PERMISSION_KEYS = {entry["key"] for entry in PERMISSION_CATALOG}
DEFAULT_NEW_COMPANY_PERMISSIONS = {key: key not in {"history.delete", "api.use", "settings.edit"} for key in PERMISSION_KEYS}


from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class WebContext:
    tenant_id: str
    actor_id: str
    actor_label: str
    actor_type: str
    assistance_session_id: str | None = None

    @property
    def is_super_admin(self) -> bool:
        return self.actor_type == "super_admin"



class AdminBaseMixin:
    def __init__(self, registry: TenantRegistry):
        self.registry = registry
        self._migrate()
        self.ensure_company("local", "Entreprise locale", status="active", grant_all=True)

    def _migrate(self) -> None:
        with _connect(self.registry.registry_path) as db:
            self._ensure_columns(
                db,
                "tenants",
                {
                    "status": "TEXT NOT NULL DEFAULT 'active'",
                    "suspension_mode": "TEXT NOT NULL DEFAULT 'block'",
                    "profile_json": "TEXT NOT NULL DEFAULT '{}'",
                    "profile_pending": "INTEGER NOT NULL DEFAULT 0",
                    "validation_comment": "TEXT",
                    "updated_at": "TEXT",
                },
            )
            self._ensure_columns(
                db,
                "api_keys",
                {
                    "scopes_json": "TEXT NOT NULL DEFAULT '[]'",
                    "expires_at": "TEXT",
                    "suspended_at": "TEXT",
                    "last_used_at": "TEXT",
                    "secret_hint": "TEXT",
                },
            )
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS company_users (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    first_name TEXT NOT NULL,
                    last_name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'member',
                    status TEXT NOT NULL DEFAULT 'invited',
                    active INTEGER NOT NULL DEFAULT 0,
                    password_salt TEXT,
                    password_digest TEXT,
                    created_at TEXT NOT NULL,
                    activated_at TEXT,
                    disabled_at TEXT,
                    transfer_to_user_id TEXT,
                    UNIQUE(tenant_id, email)
                );
                CREATE TABLE IF NOT EXISTS company_permissions (
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    permission_key TEXT NOT NULL,
                    allowed INTEGER NOT NULL,
                    PRIMARY KEY(tenant_id, permission_key)
                );
                CREATE TABLE IF NOT EXISTS user_permissions (
                    user_id TEXT NOT NULL REFERENCES company_users(id),
                    permission_key TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'inherited',
                    PRIMARY KEY(user_id, permission_key)
                );
                CREATE TABLE IF NOT EXISTS invitations (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    user_id TEXT NOT NULL REFERENCES company_users(id),
                    prefix TEXT NOT NULL UNIQUE,
                    salt TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    used_at TEXT,
                    invalidated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS profile_changes (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    change_type TEXT NOT NULL,
                    previous_json TEXT NOT NULL,
                    proposed_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    comment TEXT,
                    created_at TEXT NOT NULL,
                    decided_at TEXT,
                    decided_by TEXT
                );
                CREATE TABLE IF NOT EXISTS admin_audit_events (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target TEXT,
                    before_json TEXT NOT NULL DEFAULT '{}',
                    after_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS activity_events (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    user_id TEXT,
                    event_type TEXT NOT NULL,
                    active_seconds INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS assistance_sessions (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    actor TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    ended_at TEXT
                );
                CREATE TABLE IF NOT EXISTS user_sessions (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    user_id TEXT NOT NULL REFERENCES company_users(id),
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    ended_at TEXT
                );
                CREATE TABLE IF NOT EXISTS vehicle_ownership (
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    model_id TEXT NOT NULL,
                    origin TEXT NOT NULL,
                    owner_user_id TEXT,
                    base_model_id TEXT,
                    created_at TEXT NOT NULL,
                    deleted_at TEXT,
                    PRIMARY KEY(tenant_id, model_id)
                );
                CREATE TABLE IF NOT EXISTS admin_settings (
                    setting_key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
        with _connect(self.registry.registry_path) as db:
            tenants = db.execute("SELECT id,db_path FROM tenants").fetchall()
            for tenant in tenants:
                tenant_id = str(tenant["id"])
                expected_path = self.registry.tenants_dir / f"{tenant_id}.sqlite"
                if str(tenant["db_path"]) != str(expected_path):
                    db.execute("UPDATE tenants SET db_path=? WHERE id=?", (str(expected_path), tenant_id))
                self.registry._migrate_tenant(expected_path)
                self.registry._seed_default_vehicles(expected_path)
        for tenant in self._tenant_rows(include_archived=True):
            self._ensure_vehicle_metadata(str(tenant["id"]))
            self._ensure_history_columns(str(tenant["id"]))

    @staticmethod
    def _ensure_columns(db: Any, table: str, columns: Mapping[str, str]) -> None:
        existing = {str(row["name"]) for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, declaration in columns.items():
            if name not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")

    def _ensure_history_columns(self, tenant_id: str) -> None:
        with _connect(self.registry.tenant_path(tenant_id)) as db:
            self._ensure_columns(
                db,
                "optimization_runs",
                {
                    "optimization_type": "TEXT NOT NULL DEFAULT 'loading'",
                    "title": "TEXT",
                    "validation_status": "TEXT NOT NULL DEFAULT 'pending'",
                    "validated_at": "TEXT",
                    "validated_by": "TEXT",
                    "selected_solution": "INTEGER",
                    "validation_comment": "TEXT",
                    "created_by_type": "TEXT NOT NULL DEFAULT 'user'",
                    "created_by_id": "TEXT",
                    "created_by": "TEXT",
                    "admin_touched_at": "TEXT",
                    "admin_touched_by": "TEXT",
                    "vehicle_snapshot_json": "TEXT NOT NULL DEFAULT '[]'",
                },
            )

    def _tenant_rows(self, include_archived: bool = False) -> list[Any]:
        with _connect(self.registry.registry_path) as db:
            query = "SELECT * FROM tenants"
            if not include_archived:
                query += " WHERE COALESCE(status,'active') <> 'archived'"
            return db.execute(query + " ORDER BY name").fetchall()

    def ensure_company(self, tenant_id: str, name: str, *, status: str = "draft", grant_all: bool = False) -> None:
        self.registry.create_tenant(tenant_id, name)
        now = utc_now()
        with _connect(self.registry.registry_path) as db:
            db.execute(
                "UPDATE tenants SET name=?,status=COALESCE(status,?),updated_at=COALESCE(updated_at,?) WHERE id=?",
                (name, status, now, tenant_id),
            )
        existing = self.get_company_permissions(tenant_id)
        if not existing:
            self.set_company_permissions(
                tenant_id,
                {key: True for key in PERMISSION_KEYS} if grant_all else DEFAULT_NEW_COMPANY_PERMISSIONS,
                actor="system",
                audit=False,
            )
        self._ensure_vehicle_metadata(tenant_id)
        self._ensure_history_columns(tenant_id)

    @staticmethod
    def _slug(value: str) -> str:
        normalized = value.lower().strip()
        normalized = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
        return (normalized or "client")[:50]

    def _unique_tenant_id(self, company_name: str) -> str:
        base = self._slug(company_name)
        with _connect(self.registry.registry_path) as db:
            candidate = base
            index = 2
            while db.execute("SELECT 1 FROM tenants WHERE id=?", (candidate,)).fetchone():
                candidate = f"{base[:54]}-{index}"
                index += 1
        return candidate

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _loads(value: str | None, fallback: Any) -> Any:
        try:
            return json.loads(value or "")
        except (TypeError, ValueError, json.JSONDecodeError):
            return fallback

    def _profile_from_row(self, row: Any) -> dict[str, Any]:
        profile = self._loads(row["profile_json"], {})
        profile.setdefault("legal_name", row["name"])
        profile.setdefault("siret", "")
        profile["pending_validation"] = bool(row["profile_pending"])
        profile["validation_comment"] = row["validation_comment"] or ""
        return profile

    def get_company(self, tenant_id: str) -> dict[str, Any]:
        self.refresh_expired_invitations()
        with _connect(self.registry.registry_path) as db:
            row = db.execute("SELECT * FROM tenants WHERE id=?", (tenant_id,)).fetchone()
            if not row:
                raise KeyError(tenant_id)
            user_counts = db.execute(
                "SELECT COUNT(*) total,SUM(CASE WHEN active=1 THEN 1 ELSE 0 END) active FROM company_users WHERE tenant_id=?",
                (tenant_id,),
            ).fetchone()
            key_counts = db.execute(
                "SELECT COUNT(*) total,SUM(CASE WHEN revoked_at IS NULL AND suspended_at IS NULL THEN 1 ELSE 0 END) active FROM api_keys WHERE tenant_id=?",
                (tenant_id,),
            ).fetchone()
        return {
            "id": row["id"],
            "name": row["name"],
            "status": row["status"] or "active",
            "suspension_mode": row["suspension_mode"] or "block",
            "profile": self._profile_from_row(row),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "users_count": int(user_counts["total"] or 0),
            "active_users_count": int(user_counts["active"] or 0),
            "api_keys_count": int(key_counts["total"] or 0),
            "active_api_keys_count": int(key_counts["active"] or 0),
            "permissions": self.get_company_permissions(tenant_id),
        }

    def list_companies(self) -> list[dict[str, Any]]:
        self.refresh_expired_invitations()
        return [self.get_company(str(row["id"])) for row in self._tenant_rows(include_archived=True)]
