from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Annotated, Any, Mapping

from fastapi import FastAPI, Header, HTTPException, Request

from . import document_control as dc
from . import document_control_bootstrap as dcb
from .document_control import DocumentControlRepository
from .persistence import TenantRegistry, _connect, utc_now

SYSTEM_PROMPT_VERSION = "document-control-v1.1"

PROFILE_DEFINITIONS: tuple[dict[str, str | None], ...] = (
    {
        "key": "generic",
        "left_type": None,
        "right_type": None,
        "title": "Contrôle générique",
        "description": "Base utilisée lorsqu’aucun cas spécialisé ne correspond.",
    },
    {
        "key": "transport_order__cmr",
        "left_type": "transport_order",
        "right_type": "cmr",
        "title": "Ordre de transport ↔ CMR",
        "description": "Références, acteurs, lieux, dates, marchandises, poids et réserves.",
    },
    {
        "key": "cmr__proof_of_delivery",
        "left_type": "cmr",
        "right_type": "proof_of_delivery",
        "title": "CMR ↔ preuve de livraison",
        "description": "Livraison, date, quantités, signature et réserves.",
    },
    {
        "key": "transport_order__carrier_invoice",
        "left_type": "transport_order",
        "right_type": "carrier_invoice",
        "title": "Ordre de transport ↔ facture transporteur",
        "description": "Trajet, prestations, prix, surcharges, TVA et total.",
    },
    {
        "key": "carrier_invoice__delivery_note",
        "left_type": "carrier_invoice",
        "right_type": "delivery_note",
        "title": "Facture transporteur ↔ bon de livraison",
        "description": "Références, marchandises, quantités, poids et frais associés.",
    },
    {
        "key": "commercial_invoice__packing_list",
        "left_type": "commercial_invoice",
        "right_type": "packing_list",
        "title": "Facture commerciale ↔ packing list",
        "description": "Marchandises, colis, quantités, poids, origine et valeur.",
    },
    {
        "key": "commercial_invoice__customs_document",
        "left_type": "commercial_invoice",
        "right_type": "customs_document",
        "title": "Facture commerciale ↔ document douanier",
        "description": "Origine, incoterm, codes douaniers, poids, valeur et devise.",
    },
)
PROFILE_BY_KEY = {str(item["key"]): item for item in PROFILE_DEFINITIONS}

GENERIC_DEFAULT = """Compare toutes les informations réellement présentes dans les deux documents.
Commence par identifier les références, les parties, les lieux, les dates, les marchandises, les quantités, les poids, les montants et les validations.
Distingue clairement une absence, une différence certaine et une information illisible ou ambiguë.
Ajoute toute information pertinente qui ne figure pas dans la grille standard du cas."""


def _default_instructions(profile: Mapping[str, str | None]) -> str:
    left_type = profile.get("left_type")
    right_type = profile.get("right_type")
    if not left_type or not right_type:
        return GENERIC_DEFAULT
    fields = dc.STANDARD_FIELDS.get((str(left_type), str(right_type)), ())
    field_text = ", ".join(fields) if fields else "toutes les informations comparables"
    return (
        f"Pour le rapprochement {dc._document_label(str(left_type))} ↔ "
        f"{dc._document_label(str(right_type))}, contrôle en priorité : {field_text}.\n"
        "Vérifie aussi les incohérences supplémentaires visibles dans les documents, même si elles ne figurent pas dans cette liste."
    )


class SystemPromptRepository:
    def __init__(self, registry: TenantRegistry):
        self.registry = registry
        self._migrate()

    def _migrate(self) -> None:
        with _connect(self.registry.registry_path) as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS document_system_prompt_profiles (
                    profile_key TEXT PRIMARY KEY,
                    left_type TEXT,
                    right_type TEXT,
                    instructions TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL,
                    updated_by TEXT NOT NULL
                )
                """
            )
            for profile in PROFILE_DEFINITIONS:
                db.execute(
                    """INSERT OR IGNORE INTO document_system_prompt_profiles(
                           profile_key,left_type,right_type,instructions,version,updated_at,updated_by
                       ) VALUES (?,?,?,?,1,?,?)""",
                    (
                        profile["key"],
                        profile["left_type"],
                        profile["right_type"],
                        _default_instructions(profile),
                        utc_now(),
                        "system",
                    ),
                )

    def list_profiles(self) -> list[dict[str, Any]]:
        with _connect(self.registry.registry_path) as db:
            rows = {
                str(row["profile_key"]): row
                for row in db.execute(
                    "SELECT * FROM document_system_prompt_profiles ORDER BY profile_key"
                ).fetchall()
            }
        output: list[dict[str, Any]] = []
        for definition in PROFILE_DEFINITIONS:
            row = rows[str(definition["key"])]
            output.append(
                {
                    **definition,
                    "instructions": str(row["instructions"]),
                    "version": int(row["version"]),
                    "updated_at": row["updated_at"],
                    "updated_by": row["updated_by"],
                    "is_default": str(row["updated_by"]) == "system" and int(row["version"]) == 1,
                }
            )
        return output

    def get_profile(self, left_type: str, right_type: str) -> dict[str, Any]:
        exact_key = f"{left_type}__{right_type}"
        reverse_key = f"{right_type}__{left_type}"
        key = exact_key if exact_key in PROFILE_BY_KEY else reverse_key if reverse_key in PROFILE_BY_KEY else "generic"
        return next(profile for profile in self.list_profiles() if profile["key"] == key)

    def save_profile(self, profile_key: str, instructions: str, actor: str) -> dict[str, Any]:
        if profile_key not in PROFILE_BY_KEY:
            raise KeyError(profile_key)
        normalized = instructions.strip()
        if not normalized:
            raise ValueError("Le prompt de base ne peut pas être vide")
        if len(normalized) > 16000:
            raise ValueError("Le prompt de base est limité à 16 000 caractères")
        with _connect(self.registry.registry_path) as db:
            row = db.execute(
                "SELECT version FROM document_system_prompt_profiles WHERE profile_key=?",
                (profile_key,),
            ).fetchone()
            if not row:
                raise KeyError(profile_key)
            db.execute(
                """UPDATE document_system_prompt_profiles
                   SET instructions=?,version=?,updated_at=?,updated_by=?
                   WHERE profile_key=?""",
                (normalized, int(row["version"]) + 1, utc_now(), actor, profile_key),
            )
        return next(profile for profile in self.list_profiles() if profile["key"] == profile_key)


def _profile_from_registry_path(registry_path: str, left_type: str, right_type: str) -> dict[str, Any]:
    exact_key = f"{left_type}__{right_type}"
    reverse_key = f"{right_type}__{left_type}"
    preferred = exact_key if exact_key in PROFILE_BY_KEY else reverse_key if reverse_key in PROFILE_BY_KEY else "generic"
    with _connect(Path(registry_path)) as db:
        row = db.execute(
            "SELECT * FROM document_system_prompt_profiles WHERE profile_key=?",
            (preferred,),
        ).fetchone()
        if not row and preferred != "generic":
            row = db.execute(
                "SELECT * FROM document_system_prompt_profiles WHERE profile_key='generic'"
            ).fetchone()
    if not row:
        definition = PROFILE_BY_KEY[preferred]
        return {
            "key": preferred,
            "instructions": _default_instructions(definition),
            "version": 1,
        }
    return {
        "key": str(row["profile_key"]),
        "instructions": str(row["instructions"]),
        "version": int(row["version"]),
    }


def _extract_output_text(body: Mapping[str, Any]) -> str:
    text = body.get("output_text")
    if isinstance(text, str) and text:
        return text
    for output in body.get("output", []):
        if not isinstance(output, Mapping):
            continue
        for content in output.get("content", []):
            if isinstance(content, Mapping) and content.get("type") == "output_text":
                candidate = content.get("text")
                if isinstance(candidate, str) and candidate:
                    return candidate
    return ""


def _provider_error(exc: urllib.error.HTTPError) -> RuntimeError:
    detail = exc.read().decode("utf-8", errors="replace")[:2000]
    try:
        parsed = json.loads(detail)
        message = parsed.get("error", {}).get("message") or detail
    except (ValueError, TypeError):
        message = detail
    return RuntimeError(f"OpenAI a refusé la requête ({exc.code}) : {message}")


def call_openai_with_system_prompt(
    config: Mapping[str, Any],
    left: dc.PreparedDocument,
    right: dc.PreparedDocument,
    left_type: str,
    right_type: str,
    company_prompt: str,
    user_instruction: str,
) -> dict[str, Any]:
    if not config.get("vendor_zero_retention_confirmed"):
        raise ValueError(
            "Le superadministrateur doit confirmer la politique de non-conservation du fournisseur avant d'activer l'analyse"
        )
    if not config.get("api_key"):
        raise ValueError("Aucune clé API IA n'est configurée pour cette entreprise")
    if str(config.get("provider") or "openai") != "openai":
        raise ValueError("Cette version exécute uniquement le fournisseur OpenAI")

    registry_path = str(config.get("_registry_path") or "")
    system_profile = (
        _profile_from_registry_path(registry_path, left_type, right_type)
        if registry_path
        else {"key": "generic", "instructions": GENERIC_DEFAULT, "version": 1}
    )
    fields = dc.STANDARD_FIELDS.get((left_type, right_type)) or dc.STANDARD_FIELDS.get((right_type, left_type)) or ()
    instruction = (
        f"Document 1 : {dc._document_label(left_type)}. Document 2 : {dc._document_label(right_type)}.\n"
        f"Champs standards : {', '.join(fields) if fields else 'toutes les informations comparables'}.\n"
        f"Complément métier de l’entreprise : {company_prompt or 'aucun complément configuré'}.\n"
        f"Consigne ponctuelle : {user_instruction or 'aucune'}.\n"
        "Compare ensuite toutes les autres informations pertinentes détectables."
    )
    system_text = (
        dc.LOCKED_SYSTEM_PROMPT.strip()
        + "\n\nPROMPT DE BASE DU CAS, VERSION "
        + str(system_profile["version"])
        + ":\n"
        + str(system_profile["instructions"])
    )
    payload = {
        "model": config["model"],
        "store": False,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_text}]},
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": instruction},
                    dc._input_part(left),
                    dc._input_part(right),
                ],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "axioload_document_comparison",
                "strict": True,
                "schema": dc.COMPARISON_SCHEMA,
            }
        },
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise _provider_error(exc) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("Le fournisseur IA est temporairement inaccessible") from exc

    text = _extract_output_text(body)
    if not text:
        raise RuntimeError("Le fournisseur IA n'a renvoyé aucun résultat exploitable")
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("La réponse IA ne respecte pas le format structuré attendu") from exc
    result["items"] = dc.normalize_items(result.get("items", []))
    return result


def test_openai_connection(config: Mapping[str, Any]) -> dict[str, Any]:
    if str(config.get("provider") or "openai") != "openai":
        raise ValueError("Cette version exécute uniquement le fournisseur OpenAI")
    api_key = str(config.get("api_key") or "").strip()
    model = str(config.get("model") or "").strip()
    if not api_key:
        raise ValueError("Aucune clé API n'est disponible pour le test")
    if not model:
        raise ValueError("Le modèle doit être renseigné")

    payload = {
        "model": model,
        "store": False,
        "input": "Réponds uniquement par OK.",
        "max_output_tokens": 16,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise _provider_error(exc) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("OpenAI est inaccessible depuis le serveur AxioLoad") from exc
    latency_ms = round((time.perf_counter() - started) * 1000)
    return {
        "ok": True,
        "provider": "openai",
        "model": model,
        "latency_ms": latency_ms,
        "checked_at": utc_now(),
        "message": "Clé valide, modèle accessible et Responses API opérationnelle.",
        "response_id": str(body.get("id") or ""),
    }


def _install_repository_extensions() -> None:
    if getattr(DocumentControlRepository, "_axioload_system_prompts", False):
        return

    original_get_ai_config = DocumentControlRepository.get_ai_config
    original_get_prompt = DocumentControlRepository.get_prompt
    original_migrate_tenant = DocumentControlRepository._migrate_tenant
    original_create_control = DocumentControlRepository.create_control
    original_get_control = DocumentControlRepository.get_control

    def get_ai_config(self: DocumentControlRepository, tenant_id: str, *, include_secret: bool = False) -> dict[str, Any]:
        result = original_get_ai_config(self, tenant_id, include_secret=include_secret)
        if include_secret:
            SystemPromptRepository(self.registry)
            result["_registry_path"] = str(self.registry.registry_path)
        return result

    def get_prompt(self: DocumentControlRepository, tenant_id: str, left_type: str, right_type: str) -> dict[str, Any]:
        result = original_get_prompt(self, tenant_id, left_type, right_type)
        profile = SystemPromptRepository(self.registry).get_profile(left_type, right_type)
        result.update(
            {
                "system_base_prompt_key": profile["key"],
                "system_base_prompt": profile["instructions"],
                "system_base_prompt_version": profile["version"],
                "system_prompt_version": SYSTEM_PROMPT_VERSION,
            }
        )
        return result

    def migrate_tenant(self: DocumentControlRepository, tenant_id: str) -> None:
        original_migrate_tenant(self, tenant_id)
        with _connect(self.registry.tenant_path(tenant_id)) as db:
            existing = {
                str(row["name"])
                for row in db.execute("PRAGMA table_info(document_controls)").fetchall()
            }
            columns = {
                "system_base_prompt_key": "TEXT",
                "system_base_prompt_version": "INTEGER",
                "system_base_prompt_snapshot": "TEXT NOT NULL DEFAULT ''",
            }
            for name, declaration in columns.items():
                if name not in existing:
                    db.execute(f"ALTER TABLE document_controls ADD COLUMN {name} {declaration}")

    def create_control(self: DocumentControlRepository, tenant_id: str, **kwargs: Any) -> dict[str, Any]:
        prompt = kwargs.get("prompt") if isinstance(kwargs.get("prompt"), Mapping) else {}
        control = original_create_control(self, tenant_id, **kwargs)
        with _connect(self.registry.tenant_path(tenant_id)) as db:
            db.execute(
                """UPDATE document_controls
                   SET system_prompt_version=?,system_base_prompt_key=?,
                       system_base_prompt_version=?,system_base_prompt_snapshot=?
                   WHERE id=?""",
                (
                    SYSTEM_PROMPT_VERSION,
                    prompt.get("system_base_prompt_key"),
                    prompt.get("system_base_prompt_version"),
                    str(prompt.get("system_base_prompt") or ""),
                    control["id"],
                ),
            )
        return self.get_control(tenant_id, control["id"])

    def get_control(
        self: DocumentControlRepository,
        tenant_id: str,
        control_id: str,
        actor_id: str = "local-user",
        is_primary: bool = True,
    ) -> dict[str, Any]:
        result = original_get_control(self, tenant_id, control_id, actor_id, is_primary)
        with _connect(self.registry.tenant_path(tenant_id)) as db:
            row = db.execute(
                """SELECT system_base_prompt_key,system_base_prompt_version,
                          system_base_prompt_snapshot
                   FROM document_controls WHERE id=?""",
                (control_id,),
            ).fetchone()
        if row:
            result.update(
                {
                    "system_base_prompt_key": row["system_base_prompt_key"],
                    "system_base_prompt_version": row["system_base_prompt_version"],
                    "system_base_prompt_snapshot": row["system_base_prompt_snapshot"],
                }
            )
        return result

    DocumentControlRepository.get_ai_config = get_ai_config  # type: ignore[method-assign]
    DocumentControlRepository.get_prompt = get_prompt  # type: ignore[method-assign]
    DocumentControlRepository._migrate_tenant = migrate_tenant  # type: ignore[method-assign]
    DocumentControlRepository.create_control = create_control  # type: ignore[method-assign]
    DocumentControlRepository.get_control = get_control  # type: ignore[method-assign]
    DocumentControlRepository._axioload_system_prompts = True  # type: ignore[attr-defined]


def _super_admin(request: Request, token: str | None, authorization: str | None) -> str:
    try:
        return request.app.state.admin.super_admin_actor(token or authorization)
    except PermissionError as exc:
        raise HTTPException(401, str(exc)) from exc


def register_document_control_system_routes(app: FastAPI) -> None:
    if getattr(app.state, "_document_control_system_registered", False):
        return
    app.state._document_control_system_registered = True
    app.version = "0.14.0"

    @app.get("/api/admin/document-prompts")
    def admin_document_prompts(
        request: Request,
        x_axioload_super_admin: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        _super_admin(request, x_axioload_super_admin, authorization)
        repository = SystemPromptRepository(request.app.state.registry)
        return {
            "system_prompt_version": SYSTEM_PROMPT_VERSION,
            "locked_core_prompt": dc.LOCKED_SYSTEM_PROMPT,
            "profiles": repository.list_profiles(),
        }

    @app.put("/api/admin/document-prompts/{profile_key}")
    async def admin_document_prompt_save(
        request: Request,
        profile_key: str,
        x_axioload_super_admin: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        actor = _super_admin(request, x_axioload_super_admin, authorization)
        payload = await request.json()
        try:
            result = SystemPromptRepository(request.app.state.registry).save_profile(
                profile_key,
                str(payload.get("instructions") or ""),
                actor,
            )
            request.app.state.admin.audit(
                None,
                actor,
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

    @app.post("/api/admin/companies/{tenant_id}/document-ai/test")
    async def admin_document_ai_test(
        request: Request,
        tenant_id: str,
        x_axioload_super_admin: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        _super_admin(request, x_axioload_super_admin, authorization)
        payload = await request.json()
        repository = DocumentControlRepository(request.app.state.registry)
        try:
            request.app.state.admin.get_company(tenant_id)
            saved = repository.get_ai_config(tenant_id, include_secret=True)
            config = {
                **saved,
                "provider": str(payload.get("provider") or saved.get("provider") or "openai"),
                "model": str(payload.get("model") or saved.get("model") or ""),
                "api_key": str(payload.get("api_key") or saved.get("api_key") or ""),
            }
            return test_openai_connection(config)
        except KeyError as exc:
            raise HTTPException(404, "Entreprise inconnue") from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(422, str(exc)) from exc


def install_document_control_system() -> None:
    if getattr(FastAPI.__init__, "_axioload_document_control_system", False):
        return
    _install_repository_extensions()
    dc.SYSTEM_PROMPT_VERSION = SYSTEM_PROMPT_VERSION
    dcb.SYSTEM_PROMPT_VERSION = SYSTEM_PROMPT_VERSION
    dcb.call_openai = call_openai_with_system_prompt

    previous_fastapi_init = FastAPI.__init__

    def init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        previous_fastapi_init(self, *args, **kwargs)
        register_document_control_system_routes(self)

    init._axioload_document_control_system = True  # type: ignore[attr-defined]
    FastAPI.__init__ = init  # type: ignore[method-assign]
