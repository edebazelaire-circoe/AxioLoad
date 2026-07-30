from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any, Mapping

from .persistence import TenantRegistry, TenantRunRepository, _connect, utc_now

_COLUMNS = {
    "optimization_type": "TEXT NOT NULL DEFAULT 'loading'", "title": "TEXT",
    "validation_status": "TEXT NOT NULL DEFAULT 'pending'", "validated_at": "TEXT", "validated_by": "TEXT",
    "selected_solution": "INTEGER", "validation_comment": "TEXT",
}
_INSTALLED = False
_ORIGINAL_SAVE_RUN = TenantRunRepository.save_run


def _ensure_columns(registry: TenantRegistry, tenant_id: str) -> None:
    with _connect(registry.tenant_path(tenant_id)) as db:
        existing = {str(row["name"]) for row in db.execute("PRAGMA table_info(optimization_runs)").fetchall()}
        for name, declaration in _COLUMNS.items():
            if name not in existing: db.execute(f"ALTER TABLE optimization_runs ADD COLUMN {name} {declaration}")


def _default_title(request_payload: Mapping[str, Any], optimization_type: str) -> str:
    supplied = str(request_payload.get("optimization_title") or request_payload.get("title") or "").strip()
    if supplied: return supplied[:180]
    labels = {"loading": "Optimisation de chargement", "route": "Optimisation d’itinéraire", "total": "Optimisation totale"}
    items = request_payload.get("items")
    if optimization_type == "total" and isinstance(request_payload.get("loading"), Mapping): items = request_payload["loading"].get("items")
    references = [str(item.get("id") or "").strip() for item in items or [] if isinstance(item, Mapping)]
    references = [value for value in references if value]
    suffix = ""
    if references:
        suffix = " · " + " · ".join(references[:2])
        if len(references) > 2: suffix += f" +{len(references) - 2}"
    return (labels.get(optimization_type, "Optimisation") + suffix)[:180]


def _save_run(self: TenantRunRepository, tenant_id: str, request_payload: Mapping[str, Any], result: Any,
              channel: str = "interactive") -> str:
    _ensure_columns(self.registry, tenant_id)
    run_id = _ORIGINAL_SAVE_RUN(self, tenant_id, request_payload, result, channel)
    with _connect(self.registry.tenant_path(tenant_id)) as db:
        db.execute("UPDATE optimization_runs SET optimization_type='loading', title=? WHERE id=?",
                   (_default_title(request_payload, "loading"), run_id))
    return run_id


def _row_metadata(row: sqlite3.Row) -> dict[str, Any]:
    return {"optimization_type": row["optimization_type"] or "loading", "title": row["title"] or "Optimisation",
            "validation_status": row["validation_status"] or "pending", "validated_at": row["validated_at"],
            "validated_by": row["validated_by"], "selected_solution": row["selected_solution"],
            "validation_comment": row["validation_comment"] or ""}


def _list_runs(self: TenantRunRepository, tenant_id: str, limit: int = 50) -> list[dict[str, Any]]:
    _ensure_columns(self.registry, tenant_id)
    with _connect(self.registry.tenant_path(tenant_id)) as db:
        rows = db.execute("""SELECT id,status,elapsed_seconds,created_at,result_json,optimization_type,title,
            validation_status,validated_at,validated_by,selected_solution,validation_comment
            FROM optimization_runs ORDER BY created_at DESC LIMIT ?""", (min(max(limit, 1), 200),)).fetchall()
    output = []
    for row in rows:
        result = json.loads(row["result_json"]); solutions = result.get("solutions") or []; best = solutions[0] if solutions else result
        vehicle_count = best.get("vehicle_count")
        if vehicle_count is None and row["optimization_type"] == "route": vehicle_count = 1
        output.append({"id": row["id"], "status": row["status"], "elapsed_seconds": row["elapsed_seconds"],
                       "created_at": row["created_at"], "vehicle_count": vehicle_count,
                       "linear_meters": best.get("total_linear_meters"), **_row_metadata(row)})
    return output


def _get_run(self: TenantRunRepository, tenant_id: str, run_id: str) -> dict[str, Any]:
    _ensure_columns(self.registry, tenant_id)
    with _connect(self.registry.tenant_path(tenant_id)) as db:
        row = db.execute("""SELECT id,status,request_json,result_json,elapsed_seconds,created_at,optimization_type,title,
            validation_status,validated_at,validated_by,selected_solution,validation_comment
            FROM optimization_runs WHERE id=?""", (run_id,)).fetchone()
    if not row: raise KeyError(run_id)
    metadata = _row_metadata(row)
    return {"id": row["id"], "status": row["status"], "request": json.loads(row["request_json"]),
            "result": json.loads(row["result_json"]), "elapsed_seconds": row["elapsed_seconds"],
            "created_at": row["created_at"], **metadata,
            "decision": {"status": metadata["validation_status"], "decisionAt": metadata["validated_at"],
                         "user": metadata["validated_by"], "selectedSolution": metadata["selected_solution"],
                         "comment": metadata["validation_comment"]}}


def validate_optimization(repository: TenantRunRepository, tenant_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    _ensure_columns(repository.registry, tenant_id)
    optimization_type = str(payload.get("optimization_type") or "loading").strip().lower()
    if optimization_type not in {"loading", "route", "total"}: raise ValueError("Type d’optimisation inconnu")
    title = str(payload.get("title") or "").strip()
    if not title: raise ValueError("Le titre de l’optimisation est obligatoire")
    title = title[:180]; user = str(payload.get("user") or "Utilisateur local").strip()[:180]
    comment = str(payload.get("comment") or "").strip()[:1000]
    selected_raw = payload.get("selected_solution"); selected = int(selected_raw) if selected_raw not in (None, "") else None
    request_payload = payload.get("request") if isinstance(payload.get("request"), Mapping) else {}
    result_payload = payload.get("result") if isinstance(payload.get("result"), Mapping) else {}
    run_id = str(payload.get("run_id") or "").strip(); now = utc_now()
    if run_id:
        with _connect(repository.registry.tenant_path(tenant_id)) as db:
            updated = db.execute("""UPDATE optimization_runs SET optimization_type=?,title=?,validation_status='validated',
                validated_at=?,validated_by=?,selected_solution=?,validation_comment=? WHERE id=?""",
                (optimization_type, title, now, user, selected, comment, run_id))
            if updated.rowcount != 1: raise KeyError(run_id)
    else:
        if not result_payload: raise ValueError("Le résultat à valider est manquant")
        run_id = str(uuid.uuid4()); status = str(result_payload.get("status") or "completed"); elapsed = float(result_payload.get("elapsed_seconds") or 0.0)
        with _connect(repository.registry.tenant_path(tenant_id)) as db:
            db.execute("""INSERT INTO optimization_runs(id,status,request_json,result_json,elapsed_seconds,created_at,
                optimization_type,title,validation_status,validated_at,validated_by,selected_solution,validation_comment)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run_id,status,json.dumps(request_payload,ensure_ascii=False,separators=(",",":")),
                 json.dumps(result_payload,ensure_ascii=False,separators=(",",":")),elapsed,now,optimization_type,title,
                 "validated",now,user,selected,comment))
    repository.registry.audit(tenant_id, user, "optimization.validated", run_id,
                              {"optimization_type": optimization_type, "title": title, "selected_solution": selected})
    return repository.get_run(tenant_id, run_id)


def install_history_metadata() -> None:
    global _INSTALLED
    if _INSTALLED: return
    TenantRunRepository.save_run = _save_run
    TenantRunRepository.list_runs = _list_runs
    TenantRunRepository.get_run = _get_run
    _INSTALLED = True
