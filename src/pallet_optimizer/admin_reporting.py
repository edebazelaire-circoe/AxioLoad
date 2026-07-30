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


class AdminReportingMixin:
    @staticmethod
    def _period(start: str | None, end: str | None) -> tuple[datetime, datetime, datetime, datetime]:
        now = datetime.now(UTC)
        if start:
            current_start = datetime.fromisoformat(start).replace(tzinfo=UTC) if "T" not in start else datetime.fromisoformat(start.replace("Z", "+00:00"))
        else:
            current_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if end:
            current_end = datetime.fromisoformat(end).replace(tzinfo=UTC) + timedelta(days=1) if "T" not in end else datetime.fromisoformat(end.replace("Z", "+00:00"))
        else:
            current_end = now
        duration = current_end - current_start
        previous_end = current_start
        previous_start = previous_end - duration
        return current_start, current_end, previous_start, previous_end

    @staticmethod
    def _metric(value: float, denominator: float, previous: float, *, unit: str = "count") -> dict[str, Any]:
        share = 0.0 if denominator <= 0 else value / denominator * 100
        trend = 0.0 if previous == 0 and value == 0 else 100.0 if previous == 0 else (value - previous) / abs(previous) * 100
        return {"value": round(value, 2), "share_pct": round(share, 1), "trend_pct": round(trend, 1), "unit": unit}

    def _tenant_metrics(self, tenant_id: str, start: datetime, end: datetime, user_ids: set[str] | None = None) -> dict[str, float]:
        start_s, end_s = start.isoformat(), end.isoformat()
        values: dict[str, float] = {
            "optimizations": 0,
            "validations": 0,
            "success": 0,
            "warnings": 0,
            "failures": 0,
            "elapsed_total": 0,
            "api_calls": 0,
            "api_errors": 0,
            "exports": 0,
            "active_seconds": 0,
            "active_users": 0,
        }
        try:
            self._ensure_history_columns(tenant_id)
            with _connect(self.registry.tenant_path(tenant_id)) as db:
                run_query = "SELECT status,elapsed_seconds,result_json,validation_status FROM optimization_runs WHERE created_at>=? AND created_at<?"
                run_params: list[Any] = [start_s, end_s]
                if user_ids:
                    placeholders = ",".join("?" for _ in user_ids)
                    run_query += f" AND created_by_id IN ({placeholders})"
                    run_params.extend(sorted(user_ids))
                runs = db.execute(run_query, run_params).fetchall()
                values["optimizations"] = len(runs)
                values["validations"] = sum(1 for row in runs if row["validation_status"] == "validated")
                values["success"] = sum(1 for row in runs if row["status"] not in {"invalid_input", "internal_error"})
                values["failures"] = sum(1 for row in runs if row["status"] in {"invalid_input", "internal_error"})
                values["warnings"] = sum(1 for row in runs if '"severity":"warning"' in (row["result_json"] or ""))
                values["elapsed_total"] = sum(float(row["elapsed_seconds"] or 0) for row in runs)
                usage = db.execute(
                    "SELECT channel,status FROM usage_metrics WHERE created_at>=? AND created_at<?",
                    (start_s, end_s),
                ).fetchall()
                values["api_calls"] = sum(1 for row in usage if row["channel"] == "api")
                values["api_errors"] = sum(1 for row in usage if row["channel"] == "api" and row["status"] in {"invalid_input", "internal_error"})
                audit = db.execute(
                    "SELECT COUNT(*) count FROM audit_events WHERE action LIKE 'export.%' AND created_at>=? AND created_at<?",
                    (start_s, end_s),
                ).fetchone()
                values["exports"] = int(audit["count"] or 0)
        except KeyError:
            pass
        with _connect(self.registry.registry_path) as db:
            params: list[Any] = [tenant_id, start_s, end_s]
            clause = "tenant_id=? AND created_at>=? AND created_at<?"
            if user_ids:
                placeholders = ",".join("?" for _ in user_ids)
                clause += f" AND user_id IN ({placeholders})"
                params.extend(sorted(user_ids))
            activity = db.execute(
                f"SELECT COALESCE(SUM(active_seconds),0) seconds,COUNT(DISTINCT user_id) users FROM activity_events WHERE {clause}",
                params,
            ).fetchone()
            values["active_seconds"] = float(activity["seconds"] or 0)
            values["active_users"] = float(activity["users"] or 0)
        return values

    def dashboard(self, *, tenant_id: str | None, start: str | None, end: str | None, user_ids: Iterable[str] | None = None) -> dict[str, Any]:
        current_start, current_end, previous_start, previous_end = self._period(start, end)
        tenants = [tenant_id] if tenant_id else [company["id"] for company in self.list_companies() if company["status"] != "archived"]
        selected_users = set(user_ids or []) or None

        def aggregate(period_start: datetime, period_end: datetime) -> dict[str, float]:
            totals: dict[str, float] = {}
            for tenant in tenants:
                values = self._tenant_metrics(tenant, period_start, period_end, selected_users if tenant_id else None)
                for key, value in values.items():
                    totals[key] = totals.get(key, 0.0) + value
            return totals

        current = aggregate(current_start, current_end)
        previous = aggregate(previous_start, previous_end)
        companies = [self.get_company(item) for item in tenants]
        users = [user for item in tenants for user in self.list_users(item)]
        api_keys = [key for item in tenants for key in self.list_api_keys(item)]
        total_runs = current.get("optimizations", 0)
        total_companies = len(companies)
        total_users = len(users)
        total_api_calls = current.get("api_calls", 0)
        active_keys = sum(1 for key in api_keys if key["active"])
        previous_runs = previous.get("optimizations", 0)
        avg_seconds = current.get("elapsed_total", 0) / total_runs if total_runs else 0
        previous_avg = previous.get("elapsed_total", 0) / previous_runs if previous_runs else 0
        sections = {
            "accounts": {
                "companies": self._metric(total_companies, total_companies or 1, total_companies),
                "active_companies": self._metric(sum(1 for item in companies if item["status"] == "active"), total_companies, 0),
                "users": self._metric(total_users, total_users or 1, total_users),
                "pending_invitations": self._metric(sum(1 for user in users if user["status"] in {"invited", "invitation_expired"}), total_users, 0),
            },
            "usage": {
                "optimizations": self._metric(total_runs, total_runs or 1, previous_runs),
                "validations": self._metric(current.get("validations", 0), total_runs, previous.get("validations", 0)),
                "exports": self._metric(current.get("exports", 0), total_runs, previous.get("exports", 0)),
                "active_time_minutes": self._metric(current.get("active_seconds", 0) / 60, max(current.get("active_seconds", 0) / 60, 1), previous.get("active_seconds", 0) / 60, unit="minutes"),
            },
            "quality": {
                "successful": self._metric(current.get("success", 0), total_runs, previous.get("success", 0)),
                "warnings": self._metric(current.get("warnings", 0), total_runs, previous.get("warnings", 0)),
                "failures": self._metric(current.get("failures", 0), total_runs, previous.get("failures", 0)),
                "average_compute_seconds": self._metric(avg_seconds, avg_seconds or 1, previous_avg, unit="seconds"),
            },
            "api": {
                "calls": self._metric(total_api_calls, total_api_calls or 1, previous.get("api_calls", 0)),
                "active_keys": self._metric(active_keys, len(api_keys), active_keys),
                "errors": self._metric(current.get("api_errors", 0), total_api_calls, previous.get("api_errors", 0)),
                "expiring_keys": self._metric(sum(1 for key in api_keys if key["expires_at"] and not key["expired"]), len(api_keys), 0),
            },
        }
        return {
            "period": {
                "from": current_start.isoformat(),
                "to": current_end.isoformat(),
                "previous_from": previous_start.isoformat(),
                "previous_to": previous_end.isoformat(),
            },
            "sections": sections,
        }

    def audit(
        self,
        tenant_id: str | None,
        actor: str,
        action: str,
        target: str | None,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
    ) -> None:
        with _connect(self.registry.registry_path) as db:
            db.execute(
                """INSERT INTO admin_audit_events(id,tenant_id,actor,action,target,before_json,after_json,created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), tenant_id, actor, action, target, self._json(before), self._json(after), utc_now()),
            )

    def list_audit(self, tenant_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with _connect(self.registry.registry_path) as db:
            if tenant_id:
                rows = db.execute(
                    "SELECT * FROM admin_audit_events WHERE tenant_id=? ORDER BY created_at DESC LIMIT ?",
                    (tenant_id, min(max(limit, 1), 500)),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM admin_audit_events ORDER BY created_at DESC LIMIT ?",
                    (min(max(limit, 1), 500),),
                ).fetchall()
        return [
            {
                "id": row["id"],
                "tenant_id": row["tenant_id"],
                "actor": row["actor"],
                "action": row["action"],
                "target": row["target"],
                "before": self._loads(row["before_json"], {}),
                "after": self._loads(row["after_json"], {}),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

