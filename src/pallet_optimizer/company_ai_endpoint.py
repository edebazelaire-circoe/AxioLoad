from __future__ import annotations

import base64
import ipaddress
import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates

from . import document_control as dc
from . import document_control_bootstrap as dcb
from . import document_control_system as dcs
from .document_control import DocumentControlRepository, PreparedDocument
from .persistence import _connect, utc_now

CONTRACT_VERSION = "axioload.document-control.v1"
MAX_ENDPOINT_RESPONSE_BYTES = 10 * 1024 * 1024
ENDPOINT_EXPLANATION = (
    "AxioLoad n’enregistre aucune clé d’accès à votre fournisseur d’IA. "
    "Seul le responsable de l’entreprise peut consulter, modifier ou supprimer cet endpoint. "
    "La passerelle de votre entreprise conserve la maîtrise de l’authentification, du modèle, "
    "des quotas et de la facturation."
)

_STYLE = b'<link rel="stylesheet" href="/static/company_ai_endpoint.css?v=0.19.5">'
_SCRIPT = b'<script src="/static/company_ai_endpoint.js?v=0.19.5"></script>'


def _allow_private_endpoints() -> bool:
    return os.getenv("PLO_ALLOW_PRIVATE_AI_ENDPOINTS", "").strip() == "1"


def _allow_insecure_endpoints() -> bool:
    return os.getenv("PLO_ALLOW_INSECURE_AI_ENDPOINTS", "").strip() == "1"


def validate_endpoint_url(value: str) -> tuple[str, str]:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("L’endpoint de la passerelle IA doit être renseigné")
    if len(raw) > 2048:
        raise ValueError("L’adresse de l’endpoint est trop longue")

    try:
        parsed = urllib.parse.urlsplit(raw)
    except ValueError as exc:
        raise ValueError("L’adresse de l’endpoint est invalide") from exc

    allowed_schemes = {"https"}
    if _allow_insecure_endpoints():
        allowed_schemes.add("http")
    if parsed.scheme.lower() not in allowed_schemes:
        raise ValueError("L’endpoint doit utiliser HTTPS")
    if not parsed.hostname:
        raise ValueError("L’endpoint doit contenir un nom d’hôte")
    if parsed.username or parsed.password:
        raise ValueError("Les identifiants ne doivent pas être placés dans l’URL")
    if parsed.query or parsed.fragment:
        raise ValueError("L’endpoint ne doit contenir ni paramètre de requête ni fragment")

    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        if not _allow_private_endpoints():
            raise ValueError("Les endpoints locaux sont désactivés par sécurité")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and not _allow_private_endpoints():
        if any(
            (
                address.is_private,
                address.is_loopback,
                address.is_link_local,
                address.is_multicast,
                address.is_reserved,
                address.is_unspecified,
            )
        ):
            raise ValueError("Les adresses réseau privées ou locales sont désactivées par sécurité")

    path = parsed.path or "/"
    normalized = urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc, path, "", ""))
    return normalized, host


def _assert_public_destination(endpoint_url: str) -> None:
    if _allow_private_endpoints():
        return
    parsed = urllib.parse.urlsplit(endpoint_url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise RuntimeError("Le nom d’hôte de la passerelle IA ne peut pas être résolu") from exc
    if not addresses:
        raise RuntimeError("Le nom d’hôte de la passerelle IA ne renvoie aucune adresse")
    for entry in addresses:
        address = ipaddress.ip_address(entry[4][0])
        if any(
            (
                address.is_private,
                address.is_loopback,
                address.is_link_local,
                address.is_multicast,
                address.is_reserved,
                address.is_unspecified,
            )
        ):
            raise RuntimeError("La passerelle IA résout vers une adresse réseau non autorisée")


def _migrate_endpoint_config(repository: DocumentControlRepository) -> None:
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
        }
        for name, declaration in additions.items():
            if name not in columns:
                db.execute(f"ALTER TABLE document_ai_config ADD COLUMN {name} {declaration}")
        # Les anciennes clés fournisseur ne sont plus nécessaires dans l’architecture endpoint-only.
        db.execute(
            """UPDATE document_ai_config
               SET encrypted_api_key=NULL,key_hint=NULL,
                   provider='client_endpoint',model='managed_by_company'
               WHERE encrypted_api_key IS NOT NULL OR key_hint IS NOT NULL
                  OR provider!='client_endpoint' OR model!='managed_by_company'"""
        )


def _endpoint_config(
    repository: DocumentControlRepository,
    tenant_id: str,
    *,
    include_url: bool = False,
) -> dict[str, Any]:
    _migrate_endpoint_config(repository)
    with _connect(repository.registry.registry_path) as db:
        row = db.execute(
            "SELECT * FROM document_ai_config WHERE tenant_id=?",
            (tenant_id,),
        ).fetchone()
    if not row:
        result: dict[str, Any] = {
            "configured": False,
            "endpoint_host": "",
            "endpoint_verified_at": None,
            "endpoint_last_error": "",
            "updated_at": None,
            "retention_months": 6,
        }
        if include_url:
            result["endpoint_url"] = ""
        return result
    result = {
        "configured": bool(row["endpoint_url"]),
        "endpoint_host": str(row["endpoint_host"] or ""),
        "endpoint_verified_at": row["endpoint_verified_at"],
        "endpoint_last_error": str(row["endpoint_last_error"] or ""),
        "updated_at": row["updated_at"],
        "retention_months": int(row["retention_months"] or 6),
    }
    if include_url:
        result["endpoint_url"] = str(row["endpoint_url"] or "")
    return result


def _save_endpoint_config(
    repository: DocumentControlRepository,
    tenant_id: str,
    endpoint_url: str,
    actor: str,
) -> dict[str, Any]:
    normalized, host = validate_endpoint_url(endpoint_url)
    _migrate_endpoint_config(repository)
    existing = _endpoint_config(repository, tenant_id)
    retention = int(existing.get("retention_months") or 6)
    with _connect(repository.registry.registry_path) as db:
        db.execute(
            """INSERT INTO document_ai_config(
                   tenant_id,provider,model,encrypted_api_key,key_hint,
                   retention_months,vendor_zero_retention_confirmed,
                   updated_at,updated_by,endpoint_url,endpoint_host,
                   endpoint_verified_at,endpoint_last_error
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(tenant_id) DO UPDATE SET
                   provider=excluded.provider,
                   model=excluded.model,
                   encrypted_api_key=NULL,
                   key_hint=NULL,
                   updated_at=excluded.updated_at,
                   updated_by=excluded.updated_by,
                   endpoint_url=excluded.endpoint_url,
                   endpoint_host=excluded.endpoint_host,
                   endpoint_verified_at=NULL,
                   endpoint_last_error=''""",
            (
                tenant_id,
                "client_endpoint",
                "managed_by_company",
                None,
                None,
                retention,
                1,
                utc_now(),
                actor,
                normalized,
                host,
                None,
                "",
            ),
        )
    return _endpoint_config(repository, tenant_id, include_url=True)


def _clear_endpoint_config(
    repository: DocumentControlRepository,
    tenant_id: str,
    actor: str,
) -> None:
    _migrate_endpoint_config(repository)
    with _connect(repository.registry.registry_path) as db:
        db.execute(
            """UPDATE document_ai_config
               SET endpoint_url=NULL,endpoint_host=NULL,endpoint_verified_at=NULL,
                   endpoint_last_error='',encrypted_api_key=NULL,key_hint=NULL,
                   updated_at=?,updated_by=?
               WHERE tenant_id=?""",
            (utc_now(), actor, tenant_id),
        )


def _record_endpoint_test(
    repository: DocumentControlRepository,
    tenant_id: str,
    *,
    success: bool,
    error: str = "",
) -> None:
    _migrate_endpoint_config(repository)
    with _connect(repository.registry.registry_path) as db:
        db.execute(
            """UPDATE document_ai_config
               SET endpoint_verified_at=?,endpoint_last_error=?
               WHERE tenant_id=?""",
            (utc_now() if success else None, error[:1000], tenant_id),
        )


def _document_payload(side: str, document: PreparedDocument) -> dict[str, Any]:
    return {
        "side": side,
        "filename": document.filename,
        "media_type": document.media_type,
        "page_count": document.page_count,
        "content_base64": base64.b64encode(document.content).decode("ascii"),
    }


def _post_endpoint(endpoint_url: str, payload: Mapping[str, Any], *, timeout: int) -> dict[str, Any]:
    _assert_public_destination(endpoint_url)
    request = urllib.request.Request(
        endpoint_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AxioLoad-document-control/0.19.5",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_ENDPOINT_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        detail = exc.read(2000).decode("utf-8", errors="replace")
        raise RuntimeError(
            f"La passerelle IA a refusé la requête ({exc.code}) : {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("La passerelle IA de l’entreprise est inaccessible") from exc
    if len(raw) > MAX_ENDPOINT_RESPONSE_BYTES:
        raise RuntimeError("La réponse de la passerelle IA dépasse la taille autorisée")
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("La passerelle IA n’a pas renvoyé un objet JSON valide") from exc
    if not isinstance(body, dict):
        raise RuntimeError("La passerelle IA doit renvoyer un objet JSON")
    return body


def call_company_endpoint(
    config: Mapping[str, Any],
    left: PreparedDocument,
    right: PreparedDocument,
    left_type: str,
    right_type: str,
    company_prompt: str,
    user_instruction: str,
) -> dict[str, Any]:
    endpoint_url = str(config.get("endpoint_url") or "").strip()
    if not endpoint_url:
        raise ValueError(
            "Le responsable de l’entreprise doit configurer la passerelle IA dans Paramètres"
        )

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
    payload = {
        "contract_version": CONTRACT_VERSION,
        "action": "analyze",
        "request_id": str(uuid.uuid4()),
        "store": False,
        "system_prompt": system_prompt,
        "instruction": instruction,
        "response_schema": dc.COMPARISON_SCHEMA,
        "documents": [
            _document_payload("left", left),
            _document_payload("right", right),
        ],
    }
    body = _post_endpoint(endpoint_url, payload, timeout=180)
    raw_result = body.get("result", body)
    if not isinstance(raw_result, Mapping):
        raise RuntimeError("La passerelle IA n’a pas renvoyé de résultat structuré")
    result = dict(raw_result)
    result["items"] = dc.normalize_items(result.get("items", []))
    if not isinstance(result.get("summary"), str):
        raise RuntimeError("Le résultat de la passerelle IA ne contient pas de synthèse")
    if str(result.get("recommended_status") or "") not in dc.FINAL_STATUS_VALUES:
        result["recommended_status"] = "review"
    return result


def test_company_endpoint(config: Mapping[str, Any]) -> dict[str, Any]:
    endpoint_url = str(config.get("endpoint_url") or "").strip()
    if not endpoint_url:
        raise ValueError("Aucun endpoint IA n’est configuré pour cette entreprise")
    started = time.perf_counter()
    body = _post_endpoint(
        endpoint_url,
        {
            "contract_version": CONTRACT_VERSION,
            "action": "healthcheck",
            "request_id": str(uuid.uuid4()),
        },
        timeout=35,
    )
    if body.get("ok") is False:
        raise RuntimeError(str(body.get("message") or "La passerelle a refusé le test"))
    return {
        "ok": True,
        "endpoint_host": urllib.parse.urlsplit(endpoint_url).hostname or "",
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "checked_at": utc_now(),
        "message": str(body.get("message") or "Passerelle accessible et contrat JSON accepté."),
    }


def _install_repository_contract() -> None:
    if getattr(DocumentControlRepository, "_axioload_company_endpoint", False):
        return

    def get_endpoint_config(
        self: DocumentControlRepository,
        tenant_id: str,
        *,
        include_url: bool = False,
    ) -> dict[str, Any]:
        return _endpoint_config(self, tenant_id, include_url=include_url)

    def save_endpoint_config(
        self: DocumentControlRepository,
        tenant_id: str,
        endpoint_url: str,
        actor: str,
    ) -> dict[str, Any]:
        return _save_endpoint_config(self, tenant_id, endpoint_url, actor)

    def clear_endpoint_config(
        self: DocumentControlRepository,
        tenant_id: str,
        actor: str,
    ) -> None:
        _clear_endpoint_config(self, tenant_id, actor)

    def get_ai_config(
        self: DocumentControlRepository,
        tenant_id: str,
        *,
        include_secret: bool = False,
    ) -> dict[str, Any]:
        endpoint = _endpoint_config(self, tenant_id, include_url=include_secret)
        result = {
            "provider": "client_endpoint",
            "model": "managed_by_company",
            "configured": endpoint["configured"],
            "key_hint": "",
            "retention_months": endpoint["retention_months"],
            "vendor_zero_retention_confirmed": True,
            "updated_at": endpoint["updated_at"],
        }
        if include_secret:
            dcs.SystemPromptRepository(self.registry)
            result["endpoint_url"] = endpoint.get("endpoint_url", "")
            result["_registry_path"] = str(self.registry.registry_path)
        return result

    def reject_legacy_ai_config(
        self: DocumentControlRepository,
        tenant_id: str,
        payload: Mapping[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        del self, tenant_id, payload, actor
        raise ValueError(
            "La connexion IA est désormais configurée par le responsable de l’entreprise dans Paramètres, avec un endpoint uniquement"
        )

    DocumentControlRepository.get_endpoint_config = get_endpoint_config  # type: ignore[attr-defined]
    DocumentControlRepository.save_endpoint_config = save_endpoint_config  # type: ignore[attr-defined]
    DocumentControlRepository.clear_endpoint_config = clear_endpoint_config  # type: ignore[attr-defined]
    DocumentControlRepository.get_ai_config = get_ai_config  # type: ignore[method-assign]
    DocumentControlRepository.save_ai_config = reject_legacy_ai_config  # type: ignore[method-assign]
    DocumentControlRepository._axioload_company_endpoint = True  # type: ignore[attr-defined]


def _primary_context(request: Request, *, write: bool = False) -> Any:
    context = dcb._require(
        request,
        "document_control.run" if write else "document_control.view",
        write=write,
    )
    if not dcb._primary(request, context):
        raise HTTPException(
            403,
            "Seul le responsable de l’entreprise peut accéder à la configuration de la passerelle IA",
        )
    return context


def register_company_ai_endpoint_routes(app: FastAPI) -> None:
    if getattr(app.state, "_company_ai_endpoint_registered", False):
        return
    app.state._company_ai_endpoint_registered = True

    @app.get("/api/company/document-ai-endpoint")
    def company_endpoint_get(request: Request) -> JSONResponse:
        context = _primary_context(request)
        repository = DocumentControlRepository(request.app.state.registry)
        payload = repository.get_endpoint_config(  # type: ignore[attr-defined]
            context.tenant_id,
            include_url=True,
        )
        payload["explanation"] = ENDPOINT_EXPLANATION
        payload["contract_version"] = CONTRACT_VERSION
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})

    @app.put("/api/company/document-ai-endpoint")
    async def company_endpoint_save(request: Request) -> JSONResponse:
        context = _primary_context(request, write=True)
        payload = await request.json()
        repository = DocumentControlRepository(request.app.state.registry)
        try:
            result = repository.save_endpoint_config(  # type: ignore[attr-defined]
                context.tenant_id,
                str(payload.get("endpoint_url") or ""),
                context.actor_label,
            )
            request.app.state.admin.audit(
                context.tenant_id,
                context.actor_label,
                "document_ai.endpoint.updated",
                context.tenant_id,
                {},
                {"endpoint_host": result["endpoint_host"]},
            )
            result["explanation"] = ENDPOINT_EXPLANATION
            result["contract_version"] = CONTRACT_VERSION
            return JSONResponse(result, headers={"Cache-Control": "no-store"})
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.delete("/api/company/document-ai-endpoint", status_code=204)
    def company_endpoint_delete(request: Request) -> Response:
        context = _primary_context(request, write=True)
        repository = DocumentControlRepository(request.app.state.registry)
        repository.clear_endpoint_config(  # type: ignore[attr-defined]
            context.tenant_id,
            context.actor_label,
        )
        request.app.state.admin.audit(
            context.tenant_id,
            context.actor_label,
            "document_ai.endpoint.deleted",
            context.tenant_id,
            {},
            {},
        )
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    @app.post("/api/company/document-ai-endpoint/test")
    def company_endpoint_test(request: Request) -> JSONResponse:
        context = _primary_context(request, write=True)
        repository = DocumentControlRepository(request.app.state.registry)
        config = repository.get_endpoint_config(  # type: ignore[attr-defined]
            context.tenant_id,
            include_url=True,
        )
        try:
            result = test_company_endpoint(config)
            _record_endpoint_test(repository, context.tenant_id, success=True)
            return JSONResponse(result, headers={"Cache-Control": "no-store"})
        except (ValueError, RuntimeError) as exc:
            _record_endpoint_test(
                repository,
                context.tenant_id,
                success=False,
                error=str(exc),
            )
            raise HTTPException(422, str(exc)) from exc


def _install_asset_injection() -> None:
    previous = Jinja2Templates.TemplateResponse
    if getattr(previous, "_axioload_company_ai_endpoint", False):
        return

    def template_response(self: Jinja2Templates, *args: Any, **kwargs: Any) -> Any:
        response = previous(self, *args, **kwargs)
        body = getattr(response, "body", b"")
        if b'id="open-settings"' in body:
            body = body.replace(_STYLE, b"").replace(_SCRIPT, b"")
            body = body.replace(b"</head>", _STYLE + b"</head>")
            body = body.replace(b"</body>", _SCRIPT + b"</body>")
            response.body = body
            response.headers["content-length"] = str(len(body))
        return response

    template_response._axioload_company_ai_endpoint = True  # type: ignore[attr-defined]
    Jinja2Templates.TemplateResponse = template_response  # type: ignore[method-assign]


def install_company_ai_endpoint() -> None:
    if getattr(FastAPI.__init__, "_axioload_company_ai_endpoint", False):
        return
    _install_repository_contract()
    dcb.call_openai = call_company_endpoint
    _install_asset_injection()

    previous_fastapi_init = FastAPI.__init__

    def init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        previous_fastapi_init(self, *args, **kwargs)
        register_company_ai_endpoint_routes(self)

    init._axioload_company_ai_endpoint = True  # type: ignore[attr-defined]
    FastAPI.__init__ = init  # type: ignore[method-assign]
