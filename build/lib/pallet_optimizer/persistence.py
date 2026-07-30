from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from .catalog import default_vehicle_catalog, vehicle_from_payload, vehicle_to_payload
from .domain import DomainError, OptimizationResult, VehicleVersion, to_primitive


TENANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def _hash_secret(secret: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt, 200_000)
    return salt.hex(), digest.hex()


def _verify_secret(secret: str, salt_hex: str, digest_hex: str) -> bool:
    _, candidate = _hash_secret(secret, bytes.fromhex(salt_hex))
    return hmac.compare_digest(candidate, digest_hex)


class TenantRegistry:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.tenants_dir = self.data_dir / "tenants"
        self.tenants_dir.mkdir(exist_ok=True)
        self.registry_path = self.data_dir / "registry.sqlite"
        self._migrate_registry()

    def _migrate_registry(self) -> None:
        with _connect(self.registry_path) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tenants (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    db_path TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    label TEXT NOT NULL,
                    prefix TEXT NOT NULL UNIQUE,
                    salt TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    revoked_at TEXT
                );
            """)

    def create_tenant(self, tenant_id: str, name: str) -> Path:
        tenant_id = tenant_id.lower()
        if not TENANT_ID_RE.fullmatch(tenant_id):
            raise ValueError("tenant_id must contain 2-63 lowercase letters, digits, underscores or hyphens")
        db_path = self.tenants_dir / f"{tenant_id}.sqlite"
        with _connect(self.registry_path) as db:
            db.execute(
                "INSERT OR IGNORE INTO tenants(id, name, db_path, created_at, active) VALUES (?, ?, ?, ?, 1)",
                (tenant_id, name, str(db_path), utc_now()),
            )
        self._migrate_tenant(db_path)
        self._seed_default_vehicles(db_path)
        return db_path

    @staticmethod
    def _migrate_tenant(path: Path) -> None:
        with _connect(path) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL CHECK(role IN ('operator','company_admin')),
                    password_salt TEXT NOT NULL,
                    password_digest TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS load_cases (
                    id TEXT PRIMARY KEY,
                    owner_user_id TEXT,
                    name TEXT,
                    input_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS optimization_runs (
                    id TEXT PRIMARY KEY,
                    load_case_id TEXT,
                    status TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    elapsed_seconds REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    id TEXT PRIMARY KEY,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target TEXT,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS usage_metrics (
                    id TEXT PRIMARY KEY,
                    channel TEXT NOT NULL,
                    status TEXT NOT NULL,
                    elapsed_seconds REAL NOT NULL,
                    item_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS vehicle_models (
                    model_id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)


    @staticmethod
    def _seed_default_vehicles(path: Path) -> None:
        now = utc_now()
        with _connect(path) as db:
            count = db.execute("SELECT COUNT(*) FROM vehicle_models").fetchone()[0]
            if count:
                return
            for vehicle in default_vehicle_catalog():
                db.execute(
                    "INSERT INTO vehicle_models(model_id,version,payload_json,created_at,updated_at) VALUES (?,?,?,?,?)",
                    (vehicle.model_id, vehicle.version, json.dumps(vehicle_to_payload(vehicle), ensure_ascii=False), now, now),
                )

    def list_vehicles(self, tenant_id: str) -> tuple[VehicleVersion, ...]:
        path = self.tenant_path(tenant_id)
        self._migrate_tenant(path)
        self._seed_default_vehicles(path)
        with _connect(path) as db:
            rows = db.execute(
                "SELECT payload_json FROM vehicle_models ORDER BY CASE model_id WHEN 'semi_trailer' THEN 0 WHEN 'rigid_20m3' THEN 1 ELSE 2 END, model_id"
            ).fetchall()
        return tuple(vehicle_from_payload(json.loads(row["payload_json"])) for row in rows)

    def get_vehicle(self, tenant_id: str, model_id: str) -> VehicleVersion:
        path = self.tenant_path(tenant_id)
        self._migrate_tenant(path)
        self._seed_default_vehicles(path)
        with _connect(path) as db:
            row = db.execute(
                "SELECT payload_json FROM vehicle_models WHERE model_id=?", (model_id,)
            ).fetchone()
        if not row:
            raise KeyError(model_id)
        return vehicle_from_payload(json.loads(row["payload_json"]))

    def save_vehicle(self, tenant_id: str, payload: Mapping[str, Any], actor: str = "operator") -> VehicleVersion:
        model_id = str(payload.get("model_id", "")).strip().lower()
        try:
            current = self.get_vehicle(tenant_id, model_id)
        except KeyError:
            current = None
        next_version = (current.version + 1) if current else 1
        vehicle = vehicle_from_payload(payload, current=current, next_version=next_version)
        if current is not None:
            current_payload = vehicle_to_payload(current)
            candidate_payload = vehicle_to_payload(vehicle)
            current_payload.pop("version", None)
            candidate_payload.pop("version", None)
            if current_payload == candidate_payload:
                return current
        now = utc_now()
        with _connect(self.tenant_path(tenant_id)) as db:
            db.execute(
                """INSERT INTO vehicle_models(model_id,version,payload_json,created_at,updated_at)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(model_id) DO UPDATE SET
                     version=excluded.version,payload_json=excluded.payload_json,updated_at=excluded.updated_at""",
                (vehicle.model_id, vehicle.version, json.dumps(vehicle_to_payload(vehicle), ensure_ascii=False), now, now),
            )
        self.audit(tenant_id, actor, "vehicle.saved", vehicle.model_id, {"version": vehicle.version})
        return vehicle

    def delete_vehicle(self, tenant_id: str, model_id: str, actor: str = "operator") -> None:
        with _connect(self.tenant_path(tenant_id)) as db:
            result = db.execute("DELETE FROM vehicle_models WHERE model_id=?", (model_id,))
            if result.rowcount != 1:
                raise KeyError(model_id)
            remaining = db.execute("SELECT COUNT(*) FROM vehicle_models").fetchone()[0]
            if remaining == 0:
                raise ValueError("Au moins un véhicule doit rester disponible")
        self.audit(tenant_id, actor, "vehicle.deleted", model_id, {})

    def reset_default_vehicles(self, tenant_id: str, actor: str = "operator") -> tuple[VehicleVersion, ...]:
        now = utc_now()
        with _connect(self.tenant_path(tenant_id)) as db:
            db.execute("DELETE FROM vehicle_models")
            for vehicle in default_vehicle_catalog():
                db.execute(
                    "INSERT INTO vehicle_models(model_id,version,payload_json,created_at,updated_at) VALUES (?,?,?,?,?)",
                    (vehicle.model_id, vehicle.version, json.dumps(vehicle_to_payload(vehicle), ensure_ascii=False), now, now),
                )
        self.audit(tenant_id, actor, "vehicle.defaults_restored", None, {})
        return self.list_vehicles(tenant_id)

    def tenant_path(self, tenant_id: str) -> Path:
        with _connect(self.registry_path) as db:
            row = db.execute("SELECT db_path FROM tenants WHERE id=? AND active=1", (tenant_id,)).fetchone()
        if not row:
            raise KeyError(tenant_id)
        return Path(row["db_path"])

    def issue_api_key(self, tenant_id: str, label: str = "default") -> str:
        self.tenant_path(tenant_id)
        prefix = secrets.token_hex(4)
        secret = secrets.token_urlsafe(32)
        salt, digest = _hash_secret(secret)
        key_id = str(uuid.uuid4())
        with _connect(self.registry_path) as db:
            db.execute(
                "INSERT INTO api_keys(id, tenant_id, label, prefix, salt, digest, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (key_id, tenant_id, label, prefix, salt, digest, utc_now()),
            )
        self.audit(tenant_id, "system", "api_key.created", key_id, {"label": label, "prefix": prefix})
        return f"plo_{prefix}_{secret}"

    def resolve_api_key(self, api_key: str) -> str | None:
        parts = api_key.split("_", 2)
        if len(parts) != 3 or parts[0] != "plo":
            return None
        _, prefix, secret = parts
        with _connect(self.registry_path) as db:
            row = db.execute(
                "SELECT tenant_id, salt, digest FROM api_keys WHERE prefix=? AND revoked_at IS NULL",
                (prefix,),
            ).fetchone()
        if row and _verify_secret(secret, row["salt"], row["digest"]):
            return str(row["tenant_id"])
        return None

    def revoke_api_key(self, tenant_id: str, prefix: str, actor: str) -> None:
        with _connect(self.registry_path) as db:
            result = db.execute(
                "UPDATE api_keys SET revoked_at=? WHERE tenant_id=? AND prefix=? AND revoked_at IS NULL",
                (utc_now(), tenant_id, prefix),
            )
            if result.rowcount != 1:
                raise KeyError(prefix)
        self.audit(tenant_id, actor, "api_key.revoked", prefix, {})

    def create_user(self, tenant_id: str, email: str, password: str, role: str = "operator") -> str:
        if role not in {"operator", "company_admin"}:
            raise ValueError("invalid role")
        salt, digest = _hash_secret(password)
        user_id = str(uuid.uuid4())
        with _connect(self.tenant_path(tenant_id)) as db:
            db.execute(
                "INSERT INTO users(id,email,role,password_salt,password_digest,created_at) VALUES (?,?,?,?,?,?)",
                (user_id, email.lower(), role, salt, digest, utc_now()),
            )
        self.audit(tenant_id, email.lower(), "user.created", user_id, {"role": role})
        return user_id

    def authenticate_user(self, tenant_id: str, email: str, password: str) -> dict[str, Any] | None:
        with _connect(self.tenant_path(tenant_id)) as db:
            row = db.execute(
                "SELECT id,email,role,password_salt,password_digest FROM users WHERE email=? AND active=1",
                (email.lower(),),
            ).fetchone()
        if row and _verify_secret(password, row["password_salt"], row["password_digest"]):
            return {"id": row["id"], "email": row["email"], "role": row["role"]}
        return None


    def usage_stats(self, tenant_id: str) -> dict[str, Any]:
        with _connect(self.tenant_path(tenant_id)) as db:
            totals = db.execute(
                "SELECT COUNT(*) AS runs, COALESCE(SUM(item_count),0) AS items, COALESCE(AVG(elapsed_seconds),0) AS avg_seconds FROM usage_metrics"
            ).fetchone()
            statuses = db.execute(
                "SELECT status, COUNT(*) AS count FROM usage_metrics GROUP BY status ORDER BY status"
            ).fetchall()
        return {
            "runs": totals["runs"], "items": totals["items"], "average_seconds": totals["avg_seconds"],
            "by_status": {row["status"]: row["count"] for row in statuses},
        }

    def audit(self, tenant_id: str, actor: str, action: str, target: str | None, details: Mapping[str, Any]) -> None:
        with _connect(self.tenant_path(tenant_id)) as db:
            db.execute(
                "INSERT INTO audit_events(id,actor,action,target,details_json,created_at) VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), actor, action, target, json.dumps(details, ensure_ascii=False), utc_now()),
            )


class TenantRunRepository:
    def __init__(self, registry: TenantRegistry):
        self.registry = registry

    def save_run(self, tenant_id: str, request_payload: Mapping[str, Any], result: OptimizationResult, channel: str = "interactive") -> str:
        run_id = str(uuid.uuid4())
        result_json = json.dumps(to_primitive(result), ensure_ascii=False, separators=(",", ":"))
        request_json = json.dumps(request_payload, ensure_ascii=False, separators=(",", ":"))
        with _connect(self.registry.tenant_path(tenant_id)) as db:
            db.execute(
                "INSERT INTO optimization_runs(id,status,request_json,result_json,elapsed_seconds,created_at) VALUES (?,?,?,?,?,?)",
                (run_id, result.status.value, request_json, result_json, result.elapsed_seconds, utc_now()),
            )
            db.execute(
                "INSERT INTO usage_metrics(id,channel,status,elapsed_seconds,item_count,created_at) VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), channel, result.status.value, result.elapsed_seconds,
                 len(request_payload.get("items", [])) if isinstance(request_payload.get("items"), list) else 0, utc_now()),
            )
        return run_id

    def list_runs(self, tenant_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with _connect(self.registry.tenant_path(tenant_id)) as db:
            rows = db.execute(
                "SELECT id,status,elapsed_seconds,created_at,result_json FROM optimization_runs ORDER BY created_at DESC LIMIT ?",
                (min(max(limit, 1), 200),),
            ).fetchall()
        output = []
        for row in rows:
            result = json.loads(row["result_json"])
            best = (result.get("solutions") or [{}])[0]
            output.append({
                "id": row["id"], "status": row["status"], "elapsed_seconds": row["elapsed_seconds"],
                "created_at": row["created_at"], "vehicle_count": best.get("vehicle_count"),
                "linear_meters": best.get("total_linear_meters"),
            })
        return output

    def get_run(self, tenant_id: str, run_id: str) -> dict[str, Any]:
        with _connect(self.registry.tenant_path(tenant_id)) as db:
            row = db.execute(
                "SELECT id,status,request_json,result_json,elapsed_seconds,created_at FROM optimization_runs WHERE id=?",
                (run_id,),
            ).fetchone()
        if not row:
            raise KeyError(run_id)
        return {
            "id": row["id"], "status": row["status"], "request": json.loads(row["request_json"]),
            "result": json.loads(row["result_json"]), "elapsed_seconds": row["elapsed_seconds"],
            "created_at": row["created_at"],
        }

    def delete_run(self, tenant_id: str, run_id: str, actor: str = "operator") -> None:
        with _connect(self.registry.tenant_path(tenant_id)) as db:
            result = db.execute("DELETE FROM optimization_runs WHERE id=?", (run_id,))
            if result.rowcount != 1:
                raise KeyError(run_id)
        self.registry.audit(tenant_id, actor, "optimization_run.deleted", run_id, {})
