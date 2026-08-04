from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates

from . import company_ai_endpoint as endpoint
from . import document_control as dc
from . import document_control_bootstrap as dcb
from . import document_control_system as dcs
from .document_control import DocumentControlRepository, PreparedDocument
from .persistence import _connect, utc_now

CONNECTION_MODES = {"endpoint", "openai_api_key"}
DEFAULT_OPENAI_MODEL = "gpt-5-mini"
OPENAI_MODELS: tuple[dict[str, Any], ...] = (
    {
        "id": "gpt-5-mini",
        "label": "GPT-5 mini",
        "description": "Recommandé pour le meilleur équilibre entre qualité, vitesse et coût.",
        "recommended": True,
    },
    {
        "id": "gpt-5.1",
        "label": "GPT-5.1",
        "description": "Qualité maximale pour les dossiers complexes et les documents difficiles à lire.",
        "recommended": False,
    },
    {
        "id": "gpt-5",
        "label": "GPT-5",
        "description": "Modèle généraliste haut de gamme, conservé pour compatibilité.",
        "recommended": False,
    },
    {
        "id": "gpt-4.1",
        "label": "GPT-4.1",
        "description": "Modèle fiable pour l’analyse structurée de documents.",
        "recommended": False,
    },
    {
        "id": "gpt-4.1-mini",
        "label": "GPT-4.1 mini",
        "description": "Option économique pour les contrôles documentaires courants.",
        "recommended": False,
    },
    {
        "id": "gpt-4o",
        "label": "GPT-4o",
        "description": "Option multimodale de compatibilité pour les images et documents existants.",
        "recommended": False,
    },
    {
        "id": "gpt-4o-mini",
        "label": "GPT-4o mini",
        "description": "Option à faible coût pour les contrôles simples.",
        "recommended": False,
    },
)
ALLOWED_OPENAI_MODELS = frozenset(item["id"] for item in OPENAI_MODELS)

CONFIG_EXPLANATION = (
    "Deux modes sont disponibles. La passerelle d’entreprise laisse votre infrastructure gérer "
    "l’authentification et le fournisseur. La connexion directe permet d’utiliser une clé API "
    "OpenAI chiffrée dans AxioLoad. Dans les deux cas, seul le responsable principal de "
    "l’entreprise peut consulter ou modifier la configuration."
)

_OLD_STYLE = b'<link rel="stylesheet" href="/static/company_ai_endpoint.css?v=0.19.5">'
_NEW_STYLE = b'<link rel="stylesheet" href="/static/company_ai_endpoint.css?v=0.19.6">'
_OLD_SCRIPT = b'<script src="/static/company_ai_endpoint.js?v=0.19.5"></script>'
_NEW_SCRIPT = b'<script src="/static/company_ai_endpoint.js?v=0.19.6"></script>'


def _migrate_connection_config(repository: DocumentControlRepository) -> None:
    with _connect(repository.registry.registry_path) as db:
        columns = {
            str(row["name"])
            for row in db.execute("PRAGMA table_info(document_ai_config)").fetchall()
        }
        additions = {
            "endpoint_url": "TEXT",
            "endpoint_host": "TEXT",
            "endpoint_verified_at": "TEXT",
            "endpoint_last_error": "TEXT",
            "connection_mode": "TEXT NOT NULL DEFAULT 'endpoint'",
            "api_verified_at": "TEXT",
            "api_last_error": "TEXT",
        }
        for name, declaration in additions.items():
            if name not in columns:
                db.execute(f"ALTER TABLE document_ai_config ADD COLUMN {name} {declaration}")

        db.execute(
            """UPDATE document_ai_config
               SET connection_mode = CASE
                   WHEN endpoint_url IS NOT NULL AND TRIM(endpoint_url) != '' THEN 'endpoint'
                   WHEN encrypted_api_key IS NOT NULL AND TRIM(encrypted_api_key) != '' THEN 'openai_api_key'
                   ELSE 'endpoint'
               END
               WHERE connection_mode IS NULL
                  OR connection_mode NOT IN ('endpoint','openai_api_key')
                  OR TRIM(connection_mode) = ''"""
        )
        placeholders = ",".join("?" for _ in ALLOWED_OPENAI_MODELS)
        db.execute(
            f"""UPDATE document_ai_config
                SET model=?
                WHERE connection_mode='openai_api_key'
                  AND model NOT IN ({placeholders})""",
            (DEFAULT_OPENAI_MODEL, *sorted(ALLOWED_OPENAI_MODELS)),
        )
        db.execute(
            """UPDATE document_ai_config
               SET provider='client_endpoint',model='managed_by_company'
               WHERE connection_mode='endpoint'
                 AND endpoint_url IS NOT NULL AND TRIM(endpoint_url) != ''"""
        )


def _row(repository: DocumentControlRepository, tenant_id: str) -> Any:
    _migrate_connection_config(repository)
    with _connect(repository.registry.registry_path) as db:
        return db.execute(
            "SELECT * FROM document_ai_config WHERE tenant_id=?",
            (tenant_id,),
        ).fetchone()


def _base_config() -> dict[str, Any]:
    return {
        "connection_mode": "endpoint",
        "configured": False,
        "provider": "client_endpoint",
        "model": "managed_by_company",
        "endpoint_url": "",
        "endpoint_host": "",
        "endpoint_verified_at": None,
        "endpoint_last_error": "",
        "api_key_configured": False,
        "api_key_hint": "",
        "api_verified_at": None,
        "api_last_error": "",
        "vendor_zero_retention_confirmed": False,
        "retention_months": 6,
        "updated_at": None,
        "allowed_models": [dict(item) for item in OPENAI_MODELS],
        "contract_version": endpoint.CONTRACT_VERSION,
        "explanation": CONFIG_EXPLANATION,
    }


def get_connection_config(
    repository: DocumentControlRepository,
    tenant_id: str,
    *,
    include_secret: bool = False,
    reveal_endpoint: bool = False,
) -> dict[str, Any]:
    row = _row(repository, tenant_id)
    result = _base_config()
    if not row:
        if not reveal_endpoint and not include_secret:
            result.pop("endpoint_url", None)
        return result

    mode = str(row["connection_mode"] or "endpoint")
    if mode not in CONNECTION_MODES:
        mode = "endpoint"
    endpoint_url = str(row["endpoint_url"] or "")
    encrypted_key = str(row["encrypted_api_key"] or "")
    model = str(row["model"] or DEFAULT_OPENAI_MODEL)
    zero_retention = bool(row["vendor_zero_retention_confirmed"])
    endpoint_ready = bool(endpoint_url)
    api_ready = bool(encrypted_key) and model in ALLOWED_OPENAI_MODELS and zero_retention

    result.update(
        {
            "connection_mode": mode,
            "configured": endpoint_ready if mode == "endpoint" else api_ready,
            "provider": "client_endpoint" if mode == "endpoint" else "openai",
            "model": "managed_by_company" if mode == "endpoint" else model,
            "endpoint_host": str(row["endpoint_host"] or ""),
            "endpoint_verified_at": row["endpoint_verified_at"],
            "endpoint_last_error": str(row["endpoint_last_error"] or ""),
            "api_key_configured": bool(encrypted_key),
            "api_key_hint": str(row["key_hint"] or ""),
            "api_verified_at": row["api_verified_at"],
            "api_last_error": str(row["api_last_error"] or ""),
            "vendor_zero_retention_confirmed": zero_retention,
            "retention_months": int(row["retention_months"] or 6),
            "updated_at": row["updated_at"],
        }
    )
    if reveal_endpoint or include_secret:
        result["endpoint_url"] = endpoint_url
    else:
        result.pop("endpoint_url", None)
    if include_secret and mode == "openai_api_key" and encrypted_key:
        result["api_key"] = dc.decrypt_secret(encrypted_key)
    if include_secret:
        dcs.SystemPromptRepository(repository.registry)
        result["_registry_path"] = str(repository.registry.registry_path)
    return result


def _validate_api_key(value: str) -> str:
    api_key = str(value or "").strip()
    if not api_key:
        return ""
    if len(api_key) < 20:
        raise ValueError("La clé API OpenAI paraît incomplète")
    if any(character.isspace() for character in api_key):
        raise ValueError("La clé API OpenAI ne doit contenir aucun espace")
    return api_key


def save_connection_config(
    repository: DocumentControlRepository,
    tenant_id: str,
    payload: Mapping[str, Any],
    actor: str,
) -> dict[str, Any]:
    mode = str(payload.get("connection_mode") or "endpoint").strip().lower()
    if mode not in CONNECTION_MODES:
        raise ValueError("Mode de connexion IA inconnu")
    _migrate_connection_config(repository)
    existing_row = _row(repository, tenant_id)
    existing_retention = int(existing_row["retention_months"] or 6) if existing_row else 6
    now = utc_now()

    if mode == "endpoint":
        normalized, host = endpoint.validate_endpoint_url(str(payload.get("endpoint_url") or ""))
        with _connect(repository.registry.registry_path) as db:
            db.execute(
                """INSERT INTO document_ai_config(
                       tenant_id,provider,model,encrypted_api_key,key_hint,
                       retention_months,vendor_zero_retention_confirmed,
                       updated_at,updated_by,endpoint_url,endpoint_host,
                       endpoint_verified_at,endpoint_last_error,connection_mode,
                       api_verified_at,api_last_error
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(tenant_id) DO UPDATE SET
                       provider=excluded.provider,
                       model=excluded.model,
                       encrypted_api_key=NULL,
                       key_hint=NULL,
                       retention_months=excluded.retention_months,
                       vendor_zero_retention_confirmed=1,
                       updated_at=excluded.updated_at,
                       updated_by=excluded.updated_by,
                       endpoint_url=excluded.endpoint_url,
                       endpoint_host=excluded.endpoint_host,
                       endpoint_verified_at=NULL,
                       endpoint_last_error='',
                       connection_mode='endpoint',
                       api_verified_at=NULL,
                       api_last_error=''""",
                (
                    tenant_id,
                    "client_endpoint",
                    "managed_by_company",
                    None,
                    None,
                    existing_retention,
                    1,
                    now,
                    actor,
                    normalized,
                    host,
                    None,
                    "",
                    "endpoint",
                    None,
                    "",
                ),
            )
        return get_connection_config(repository, tenant_id, reveal_endpoint=True)

    model = str(payload.get("model") or DEFAULT_OPENAI_MODEL).strip()
    if model not in ALLOWED_OPENAI_MODELS:
        raise ValueError("Le modèle OpenAI sélectionné n’est pas autorisé par AxioLoad")
    zero_retention = bool(payload.get("vendor_zero_retention_confirmed"))
    if not zero_retention:
        raise ValueError(
            "Confirmez avoir vérifié la politique de conservation des données de votre compte OpenAI"
        )
    submitted_key = _validate_api_key(str(payload.get("api_key") or ""))
    encrypted_key = ""
    key_hint = ""
    if submitted_key:
        encrypted_key = dc.encrypt_secret(submitted_key)
        key_hint = submitted_key[-4:]
    elif existing_row and str(existing_row["connection_mode"] or "") == "openai_api_key":
        encrypted_key = str(existing_row["encrypted_api_key"] or "")
        key_hint = str(existing_row["key_hint"] or "")
    if not encrypted_key:
        raise ValueError("Renseignez une clé API OpenAI pour activer cette connexion")

    with _connect(repository.registry.registry_path) as db:
        db.execute(
            """INSERT INTO document_ai_config(
                   tenant_id,provider,model,encrypted_api_key,key_hint,
                   retention_months,vendor_zero_retention_confirmed,
                   updated_at,updated_by,endpoint_url,endpoint_host,
                   endpoint_verified_at,endpoint_last_error,connection_mode,
                   api_verified_at,api_last_error
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(tenant_id) DO UPDATE SET
                   provider='openai',
                   model=excluded.model,
                   encrypted_api_key=excluded.encrypted_api_key,
                   key_hint=excluded.key_hint,
                   retention_months=excluded.retention_months,
                   vendor_zero_retention_confirmed=1,
                   updated_at=excluded.updated_at,
                   updated_by=excluded.updated_by,
                   endpoint_url=NULL,
                   endpoint_host=NULL,
                   endpoint_verified_at=NULL,
                   endpoint_last_error='',
                   connection_mode='openai_api_key',
                   api_verified_at=NULL,
                   api_last_error=''""",
            (
                tenant_id,
                "openai",
                model,
                encrypted_key,
                key_hint,
                existing_retention,
                1,
                now,
                actor,
                None,
                None,
                None,
                "",
                "openai_api_key",
                None,
                "",
            ),
        )
    return get_connection_config(repository, tenant_id, reveal_endpoint=True)


def clear_connection_config(
    repository: DocumentControlRepository,
    tenant_id: str,
    actor: str,
) -> None:
    _migrate_connection_config(repository)
    with _connect(repository.registry.registry_path) as db:
        db.execute(
            """UPDATE document_ai_config
               SET provider='client_endpoint',model='managed_by_company',
                   encrypted_api_key=NULL,key_hint=NULL,
                   vendor_zero_retention_confirmed=0,
                   updated_at=?,updated_by=?,endpoint_url=NULL,endpoint_host=NULL,
                   endpoint_verified_at=NULL,endpoint_last_error='',
                   connection_mode='endpoint',api_verified_at=NULL,api_last_error=''
               WHERE tenant_id=?""",
            (utc_now(), actor, tenant_id),
        )


def _record_test(
    repository: DocumentControlRepository,
    tenant_id: str,
    mode: str,
    *,
    success: bool,
    error: str = "",
) -> None:
    _migrate_connection_config(repository)
    if mode == "endpoint":
        verified_column = "endpoint_verified_at"
        error_column = "endpoint_last_error"
    else:
        verified_column = "api_verified_at"
        error_column = "api_last_error"
    with _connect(repository.registry.registry_path) as db:
        db.execute(
            f"UPDATE document_ai_config SET {verified_column}=?,{error_column}=? WHERE tenant_id=?",
            (utc_now() if success else None, error[:1000], tenant_id),
        )


def test_openai_api(config: Mapping[str, Any]) -> dict[str, Any]:
    api_key = str(config.get("api_key") or "")
    model = str(config.get("model") or "")
    if not api_key:
        raise ValueError("Aucune clé API OpenAI n’est configurée")
    if model not in ALLOWED_OPENAI_MODELS:
        raise ValueError("Le modèle OpenAI configuré n’est pas autorisé")
    started = time.perf_counter()
    request = urllib.request.Request(
        f"https://api.openai.com/v1/models/{urllib.parse.quote(model, safe='')}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "AxioLoad-document-control/0.19.6",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            body = json.loads(response.read(1024 * 1024).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read(2000).decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI a refusé la connexion ({exc.code}) : {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("OpenAI est temporairement inaccessible") from exc
    if str(body.get("id") or "") != model:
        raise RuntimeError("OpenAI n’a pas confirmé l’accès au modèle sélectionné")
    return {
        "ok": True,
        "connection_mode": "openai_api_key",
        "model": model,
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "checked_at": utc_now(),
        "message": "Clé API valide et modèle accessible.",
    }


def _system_and_instruction(
    config: Mapping[str, Any],
    left_type: str,
    right_type: str,
    company_prompt: str,
    user_instruction: str,
) -> tuple[str, str]:
    registry_path = str(config.get("_registry_path") or "")
    system_profile = (
        dcs._profile_from_registry_path(registry_path, left_type, right_type)
        if registry_path
        else {"key": "generic", "instructions": dcs.GENERIC_DEFAULT, "version": 1}
    )
    fields = (
        dc.STANDARD_FIELDS.get((left_type, right_type))
        or dc.STANDARD_FIELDS.get((right_type, left_type))
        or ()
    )
    instruction = (
        f"Document 1 : {dc._document_label(left_type)}. "
        f"Document 2 : {dc._document_label(right_type)}.\n"
        f"Champs standards : {', '.join(fields) if fields else 'toutes les informations comparables'}.\n"
        f"Complément métier de l’entreprise : {company_prompt or 'aucun complément configuré'}.\n"
        f"Consigne ponctuelle : {user_instruction or 'aucune'}.\n"
        "Compare ensuite toutes les autres informations pertinentes détectables."
    )
    system_prompt = (
        dc.LOCKED_SYSTEM_PROMPT.strip()
        + "\n\nPROMPT DE BASE DU CAS, VERSION "
        + str(system_profile["version"])
        + ":\n"
        + str(system_profile["instructions"])
    )
    return system_prompt, instruction


def call_openai_api(
    config: Mapping[str, Any],
    left: PreparedDocument,
    right: PreparedDocument,
    left_type: str,
    right_type: str,
    company_prompt: str,
    user_instruction: str,
) -> dict[str, Any]:
    if not config.get("vendor_zero_retention_confirmed"):
        raise ValueError(
            "Le responsable doit confirmer la politique de conservation du compte OpenAI"
        )
    api_key = str(config.get("api_key") or "")
    model = str(config.get("model") or "")
    if not api_key:
        raise ValueError("Aucune clé API OpenAI n’est configurée pour cette entreprise")
    if model not in ALLOWED_OPENAI_MODELS:
        raise ValueError("Le modèle OpenAI configuré n’est pas autorisé par AxioLoad")

    system_prompt, instruction = _system_and_instruction(
        config,
        left_type,
        right_type,
        company_prompt,
        user_instruction,
    )
    payload = {
        "model": model,
        "store": False,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
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
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AxioLoad-document-control/0.19.6",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read(2000).decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI a refusé l’analyse ({exc.code}) : {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("OpenAI est temporairement inaccessible") from exc

    text = body.get("output_text")
    if not text:
        for output in body.get("output", []):
            for content in output.get("content", []):
                if content.get("type") == "output_text":
                    text = content.get("text")
                    break
            if text:
                break
    if not text:
        raise RuntimeError("OpenAI n’a renvoyé aucun résultat exploitable")
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("La réponse OpenAI ne respecte pas le format structuré attendu") from exc
    result["items"] = dc.normalize_items(result.get("items", []))
    return result


def call_company_ai(
    config: Mapping[str, Any],
    left: PreparedDocument,
    right: PreparedDocument,
    left_type: str,
    right_type: str,
    company_prompt: str,
    user_instruction: str,
) -> dict[str, Any]:
    mode = str(config.get("connection_mode") or "")
    if not mode:
        mode = "endpoint" if config.get("endpoint_url") else "openai_api_key"
    if mode == "endpoint":
        return endpoint.call_company_endpoint(
            config,
            left,
            right,
            left_type,
            right_type,
            company_prompt,
            user_instruction,
        )
    if mode == "openai_api_key":
        return call_openai_api(
            config,
            left,
            right,
            left_type,
            right_type,
            company_prompt,
            user_instruction,
        )
    raise ValueError("Mode de connexion IA inconnu")


def _install_repository_contract() -> None:
    def repository_get_connection_config(
        self: DocumentControlRepository,
        tenant_id: str,
        *,
        include_secret: bool = False,
        reveal_endpoint: bool = False,
    ) -> dict[str, Any]:
        return get_connection_config(
            self,
            tenant_id,
            include_secret=include_secret,
            reveal_endpoint=reveal_endpoint,
        )

    def repository_save_connection_config(
        self: DocumentControlRepository,
        tenant_id: str,
        payload: Mapping[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        return save_connection_config(self, tenant_id, payload, actor)

    def repository_clear_connection_config(
        self: DocumentControlRepository,
        tenant_id: str,
        actor: str,
    ) -> None:
        clear_connection_config(self, tenant_id, actor)

    def repository_get_ai_config(
        self: DocumentControlRepository,
        tenant_id: str,
        *,
        include_secret: bool = False,
    ) -> dict[str, Any]:
        config = get_connection_config(
            self,
            tenant_id,
            include_secret=include_secret,
            reveal_endpoint=include_secret,
        )
        result = {
            "connection_mode": config["connection_mode"],
            "provider": config["provider"],
            "model": config["model"],
            "configured": config["configured"],
            "key_hint": config["api_key_hint"],
            "retention_months": config["retention_months"],
            "vendor_zero_retention_confirmed": config[
                "vendor_zero_retention_confirmed"
            ],
            "updated_at": config["updated_at"],
        }
        if include_secret:
            if config["connection_mode"] == "endpoint":
                result["endpoint_url"] = config.get("endpoint_url", "")
            else:
                result["api_key"] = config.get("api_key", "")
            result["_registry_path"] = config.get("_registry_path", "")
        return result

    def repository_reject_superadmin_save(
        self: DocumentControlRepository,
        tenant_id: str,
        payload: Mapping[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        del self, tenant_id, payload, actor
        raise ValueError(
            "La connexion IA est configurée uniquement par le responsable de l’entreprise dans Paramètres"
        )

    def repository_get_endpoint_config(
        self: DocumentControlRepository,
        tenant_id: str,
        *,
        include_url: bool = False,
    ) -> dict[str, Any]:
        config = get_connection_config(
            self,
            tenant_id,
            reveal_endpoint=include_url,
        )
        return {
            "configured": config["configured"]
            and config["connection_mode"] == "endpoint",
            "endpoint_url": config.get("endpoint_url", "") if include_url else "",
            "endpoint_host": config["endpoint_host"],
            "endpoint_verified_at": config["endpoint_verified_at"],
            "endpoint_last_error": config["endpoint_last_error"],
            "updated_at": config["updated_at"],
            "retention_months": config["retention_months"],
        }

    def repository_save_endpoint_config(
        self: DocumentControlRepository,
        tenant_id: str,
        endpoint_url: str,
        actor: str,
    ) -> dict[str, Any]:
        return save_connection_config(
            self,
            tenant_id,
            {"connection_mode": "endpoint", "endpoint_url": endpoint_url},
            actor,
        )

    def repository_clear_endpoint_config(
        self: DocumentControlRepository,
        tenant_id: str,
        actor: str,
    ) -> None:
        clear_connection_config(self, tenant_id, actor)

    DocumentControlRepository.get_connection_config = repository_get_connection_config  # type: ignore[attr-defined]
    DocumentControlRepository.save_connection_config = repository_save_connection_config  # type: ignore[attr-defined]
    DocumentControlRepository.clear_connection_config = repository_clear_connection_config  # type: ignore[attr-defined]
    DocumentControlRepository.get_ai_config = repository_get_ai_config  # type: ignore[method-assign]
    DocumentControlRepository.save_ai_config = repository_reject_superadmin_save  # type: ignore[method-assign]
    DocumentControlRepository.get_endpoint_config = repository_get_endpoint_config  # type: ignore[attr-defined]
    DocumentControlRepository.save_endpoint_config = repository_save_endpoint_config  # type: ignore[attr-defined]
    DocumentControlRepository.clear_endpoint_config = repository_clear_endpoint_config  # type: ignore[attr-defined]
    DocumentControlRepository._axioload_company_ai_dual_mode = True  # type: ignore[attr-defined]


def _primary_context(request: Request, *, write: bool = False) -> Any:
    context = dcb._require(
        request,
        "document_control.run" if write else "document_control.view",
        write=write,
    )
    if not dcb._primary(request, context):
        raise HTTPException(
            403,
            "Seul le responsable principal de l’entreprise peut accéder à la configuration IA",
        )
    return context


def register_company_ai_dual_mode_routes(app: FastAPI) -> None:
    if getattr(app.state, "_company_ai_dual_mode_registered", False):
        return
    app.state._company_ai_dual_mode_registered = True

    @app.get("/api/company/document-ai-config")
    def company_ai_config_get(request: Request) -> JSONResponse:
        context = _primary_context(request)
        repository = DocumentControlRepository(request.app.state.registry)
        payload = repository.get_connection_config(  # type: ignore[attr-defined]
            context.tenant_id,
            reveal_endpoint=True,
        )
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})

    @app.put("/api/company/document-ai-config")
    async def company_ai_config_save(request: Request) -> JSONResponse:
        context = _primary_context(request, write=True)
        payload = await request.json()
        repository = DocumentControlRepository(request.app.state.registry)
        try:
            before = repository.get_connection_config(context.tenant_id)  # type: ignore[attr-defined]
            result = repository.save_connection_config(  # type: ignore[attr-defined]
                context.tenant_id,
                payload,
                context.actor_label,
            )
            request.app.state.admin.audit(
                context.tenant_id,
                context.actor_label,
                "document_ai.connection.updated",
                context.tenant_id,
                {
                    "connection_mode": before.get("connection_mode"),
                    "provider": before.get("provider"),
                    "model": before.get("model"),
                },
                {
                    "connection_mode": result["connection_mode"],
                    "provider": result["provider"],
                    "model": result["model"],
                    "endpoint_host": result.get("endpoint_host", ""),
                    "api_key_hint": result.get("api_key_hint", ""),
                },
            )
            return JSONResponse(result, headers={"Cache-Control": "no-store"})
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.delete("/api/company/document-ai-config", status_code=204)
    def company_ai_config_delete(request: Request) -> Response:
        context = _primary_context(request, write=True)
        repository = DocumentControlRepository(request.app.state.registry)
        repository.clear_connection_config(  # type: ignore[attr-defined]
            context.tenant_id,
            context.actor_label,
        )
        request.app.state.admin.audit(
            context.tenant_id,
            context.actor_label,
            "document_ai.connection.deleted",
            context.tenant_id,
            {},
            {},
        )
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    @app.post("/api/company/document-ai-config/test")
    def company_ai_config_test(request: Request) -> JSONResponse:
        context = _primary_context(request, write=True)
        repository = DocumentControlRepository(request.app.state.registry)
        config = repository.get_connection_config(  # type: ignore[attr-defined]
            context.tenant_id,
            include_secret=True,
            reveal_endpoint=True,
        )
        mode = str(config.get("connection_mode") or "endpoint")
        try:
            if mode == "endpoint":
                result = endpoint.test_company_endpoint(config)
                result["connection_mode"] = "endpoint"
            else:
                result = test_openai_api(config)
            _record_test(repository, context.tenant_id, mode, success=True)
            return JSONResponse(result, headers={"Cache-Control": "no-store"})
        except (ValueError, RuntimeError) as exc:
            _record_test(
                repository,
                context.tenant_id,
                mode,
                success=False,
                error=str(exc),
            )
            raise HTTPException(422, str(exc)) from exc


def _install_asset_version() -> None:
    previous = Jinja2Templates.TemplateResponse
    if getattr(previous, "_axioload_company_ai_dual_mode", False):
        return

    def template_response(self: Jinja2Templates, *args: Any, **kwargs: Any) -> Any:
        response = previous(self, *args, **kwargs)
        body = getattr(response, "body", b"")
        if _OLD_STYLE in body or _OLD_SCRIPT in body:
            body = body.replace(_OLD_STYLE, _NEW_STYLE).replace(_OLD_SCRIPT, _NEW_SCRIPT)
            response.body = body
            response.headers["content-length"] = str(len(body))
        return response

    template_response._axioload_company_ai_dual_mode = True  # type: ignore[attr-defined]
    Jinja2Templates.TemplateResponse = template_response  # type: ignore[method-assign]


def install_company_ai_dual_mode() -> None:
    if getattr(FastAPI.__init__, "_axioload_company_ai_dual_mode", False):
        return
    endpoint._migrate_endpoint_config = _migrate_connection_config
    _install_repository_contract()
    dcb.call_openai = call_company_ai
    _install_asset_version()

    previous_fastapi_init = FastAPI.__init__

    def init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        previous_fastapi_init(self, *args, **kwargs)
        register_company_ai_dual_mode_routes(self)

    init._axioload_company_ai_dual_mode = True  # type: ignore[attr-defined]
    FastAPI.__init__ = init  # type: ignore[method-assign]
