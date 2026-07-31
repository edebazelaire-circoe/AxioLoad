from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from fastapi import FastAPI, HTTPException, Request

from . import document_control as dc
from . import document_control_bootstrap as dcb
from .document_control import DOCUMENT_TYPE_KEYS, DocumentControlRepository
from .document_control_system import PROFILE_DEFINITIONS, SYSTEM_PROMPT_VERSION, SystemPromptRepository
from .persistence import TenantRegistry, _connect, utc_now

_DEFAULT_CORE_PROMPT = dc.LOCKED_SYSTEM_PROMPT
_original_fastapi_init = FastAPI.__init__


def _ensure_core(registry_path: Path) -> dict[str, Any]:
    with _connect(registry_path) as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS document_system_prompt_core (
                id TEXT PRIMARY KEY,
                instructions TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                updated_by TEXT NOT NULL
            )
            """
        )
        db.execute(
            """INSERT OR IGNORE INTO document_system_prompt_core(
                   id,instructions,version,updated_at,updated_by
               ) VALUES ('core',?,1,?,?)""",
            (_DEFAULT_CORE_PROMPT, utc_now(), "system"),
        )
        row = db.execute(
            "SELECT instructions,version,updated_at,updated_by FROM document_system_prompt_core WHERE id='core'"
        ).fetchone()
    return {
        "instructions": str(row["instructions"]),
        "version": int(row["version"]),
        "updated_at": str(row["updated_at"]),
        "updated_by": str(row["updated_by"]),
        "is_default": str(row["updated_by"]) == "system" and int(row["version"]) == 1,
    }


class PromptCoreRepository:
    def __init__(self, registry: TenantRegistry):
        self.registry = registry
        self.get()

    def get(self) -> dict[str, Any]:
        return _ensure_core(self.registry.registry_path)

    def save(self, instructions: str, actor: str) -> dict[str, Any]:
        normalized = instructions.strip()
        if not normalized:
            raise ValueError("Le socle commun ne peut pas être vide")
        if len(normalized) > 20000:
            raise ValueError("Le socle commun est limité à 20 000 caractères")
        current = self.get()
        with _connect(self.registry.registry_path) as db:
            db.execute(
                """UPDATE document_system_prompt_core
                   SET instructions=?,version=?,updated_at=?,updated_by=?
                   WHERE id='core'""",
                (normalized, int(current["version"]) + 1, utc_now(), actor),
            )
        result = self.get()
        dc.LOCKED_SYSTEM_PROMPT = result["instructions"]
        dcb.LOCKED_SYSTEM_PROMPT = result["instructions"]
        return result


def _context(request: Request):
    return request.app.state.admin.resolve_web_context(
        request.cookies.get("axioload_assistance"),
        request.cookies.get("axioload_session"),
    )


def _is_primary(request: Request, context: Any) -> bool:
    if context.actor_id == "local-user":
        return True
    if context.actor_type != "user":
        return False
    try:
        return request.app.state.admin.get_user(context.actor_id)["role"] == "primary"
    except KeyError:
        return False


def _require_permission(request: Request, context: Any, permission: str, *, write: bool = False) -> None:
    try:
        request.app.state.admin.require_permission(context, permission, write=write)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


def _system_payload(request: Request) -> dict[str, Any]:
    core = PromptCoreRepository(request.app.state.registry).get()
    dc.LOCKED_SYSTEM_PROMPT = core["instructions"]
    dcb.LOCKED_SYSTEM_PROMPT = core["instructions"]
    return {
        "mode": "super_admin",
        "system_prompt_version": SYSTEM_PROMPT_VERSION,
        "core": core,
        "profiles": SystemPromptRepository(request.app.state.registry).list_profiles(),
    }


def _company_payload(request: Request, context: Any) -> dict[str, Any]:
    _require_permission(request, context, "document_control.view")
    repository = DocumentControlRepository(request.app.state.registry)
    profiles: list[dict[str, Any]] = []
    for definition in PROFILE_DEFINITIONS:
        left_type = definition.get("left_type")
        right_type = definition.get("right_type")
        if not left_type or not right_type:
            continue
        prompt = repository.get_prompt(context.tenant_id, str(left_type), str(right_type))
        profiles.append(
            {
                "key": definition["key"],
                "title": definition["title"],
                "description": definition["description"],
                "left_type": left_type,
                "right_type": right_type,
                "system_instructions": prompt.get("system_base_prompt", ""),
                "system_version": prompt.get("system_base_prompt_version", 1),
                "company_instructions": prompt.get("admin_instructions", ""),
                "company_version": prompt.get("version", 1),
                "configured": bool(prompt.get("configured")),
                "updated_by": prompt.get("updated_by", ""),
            }
        )
    return {
        "mode": "company",
        "company": {"id": context.tenant_id, "name": request.app.state.admin.get_company(context.tenant_id)["name"]},
        "is_primary_admin": _is_primary(request, context),
        "system_prompt_version": SYSTEM_PROMPT_VERSION,
        "profiles": profiles,
    }


def register_prompt_center_routes(app: FastAPI) -> None:
    if getattr(app.state, "_prompt_center_registered", False):
        return
    app.state._prompt_center_registered = True

    @app.get("/api/prompt-center")
    def prompt_center_get(request: Request) -> dict[str, Any]:
        context = _context(request)
        if context.is_super_admin:
            return _system_payload(request)
        return _company_payload(request, context)

    @app.put("/api/prompt-center/core")
    async def prompt_center_core_save(request: Request) -> dict[str, Any]:
        context = _context(request)
        if not context.is_super_admin:
            raise HTTPException(403, "Seul le Centre de gestion peut modifier le socle commun")
        payload = await request.json()
        try:
            result = PromptCoreRepository(request.app.state.registry).save(
                str(payload.get("instructions") or ""), context.actor_label
            )
            request.app.state.admin.audit(
                None,
                context.actor_label,
                "document_prompt.core.updated",
                "core",
                {},
                {"version": result["version"]},
            )
            return result
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.put("/api/prompt-center/system/{profile_key}")
    async def prompt_center_system_save(request: Request, profile_key: str) -> dict[str, Any]:
        context = _context(request)
        if not context.is_super_admin:
            raise HTTPException(403, "Seul le Centre de gestion peut modifier les prompts système")
        payload = await request.json()
        try:
            result = SystemPromptRepository(request.app.state.registry).save_profile(
                profile_key,
                str(payload.get("instructions") or ""),
                context.actor_label,
            )
            request.app.state.admin.audit(
                None,
                context.actor_label,
                "document_prompt.system.updated",
                profile_key,
                {},
                {"version": result["version"]},
            )
            return result
        except KeyError as exc:
            raise HTTPException(404, "Cas documentaire inconnu") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.put("/api/prompt-center/company/{left_type}/{right_type}")
    async def prompt_center_company_save(request: Request, left_type: str, right_type: str) -> dict[str, Any]:
        context = _context(request)
        if context.is_super_admin:
            raise HTTPException(403, "Utilisez les prompts système depuis le compte du Centre de gestion")
        _require_permission(request, context, "document_control.run", write=True)
        if not _is_primary(request, context):
            raise HTTPException(403, "Seul l’administrateur principal de l’entreprise peut modifier ce complément")
        if left_type not in DOCUMENT_TYPE_KEYS or right_type not in DOCUMENT_TYPE_KEYS:
            raise HTTPException(422, "Type de document inconnu")
        payload = await request.json()
        try:
            return DocumentControlRepository(request.app.state.registry).save_prompt(
                context.tenant_id,
                left_type,
                right_type,
                str(payload.get("instructions") or ""),
                context.actor_label,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc


def install_prompt_center_system() -> None:
    if getattr(FastAPI.__init__, "_axioload_prompt_center", False):
        return

    previous_call = dcb.call_openai

    def call_with_editable_core(
        config: Mapping[str, Any],
        left: dc.PreparedDocument,
        right: dc.PreparedDocument,
        left_type: str,
        right_type: str,
        company_prompt: str,
        user_instruction: str,
    ) -> dict[str, Any]:
        registry_path = str(config.get("_registry_path") or "")
        if registry_path:
            core = _ensure_core(Path(registry_path))
            dc.LOCKED_SYSTEM_PROMPT = core["instructions"]
            dcb.LOCKED_SYSTEM_PROMPT = core["instructions"]
        return previous_call(
            config,
            left,
            right,
            left_type,
            right_type,
            company_prompt,
            user_instruction,
        )

    dcb.call_openai = call_with_editable_core

    def init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        _original_fastapi_init(self, *args, **kwargs)
        register_prompt_center_routes(self)

    init._axioload_prompt_center = True  # type: ignore[attr-defined]
    FastAPI.__init__ = init  # type: ignore[method-assign]
