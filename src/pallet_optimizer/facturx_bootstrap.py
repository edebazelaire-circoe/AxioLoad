from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from . import admin_base
from .admin_base import WebContext
from .company_ai_dual_mode import get_connection_config
from .document_control import DocumentControlRepository, MAX_FILE_BYTES, prepare_document
from .facturx import (
    FACTURX_PROFILES,
    PARTY_TYPES,
    FacturXRepository,
    build_facturx_xml,
    extract_invoice_with_ai,
    validate_invoice,
)

_PERMISSIONS = (
    {"key": "facturx.view", "module": "facturx", "label": "Accéder à la facturation électronique"},
    {"key": "facturx.edit", "module": "facturx", "label": "Créer et modifier des factures"},
    {"key": "facturx.validate", "module": "facturx", "label": "Valider une facture avant export"},
    {"key": "facturx.export", "module": "facturx", "label": "Exporter les fichiers de facturation"},
)


def install_facturx_permissions() -> None:
    existing = {entry["key"] for entry in admin_base.PERMISSION_CATALOG}
    additions = tuple(entry for entry in _PERMISSIONS if entry["key"] not in existing)
    if not additions:
        return
    admin_base.PERMISSION_CATALOG = admin_base.PERMISSION_CATALOG + additions
    admin_base.PERMISSION_KEYS.update(entry["key"] for entry in additions)
    admin_base.DEFAULT_NEW_COMPANY_PERMISSIONS.update({entry["key"]: True for entry in additions})


def _context(request: Request) -> WebContext:
    return request.app.state.admin.resolve_web_context(
        request.cookies.get("axioload_assistance"),
        request.cookies.get("axioload_session"),
    )


def _require(request: Request, permission: str, *, write: bool = False) -> WebContext:
    context = _context(request)
    try:
        request.app.state.admin.require_permission(context, permission, write=write)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    return context


def _repository(request: Request) -> FacturXRepository:
    return FacturXRepository(request.app.state.registry)


def register_facturx_routes(app: FastAPI) -> None:
    if getattr(app.state, "_facturx_registered", False):
        return
    app.state._facturx_registered = True

    @app.get("/api/facturx/bootstrap")
    def facturx_bootstrap(request: Request) -> dict[str, Any]:
        _require(request, "facturx.view")
        return {
            "profiles": list(FACTURX_PROFILES),
            "directions": ["outgoing", "incoming"],
            "document_types": ["invoice", "credit_note", "advance_invoice"],
            "party_types": list(PARTY_TYPES),
            "accepted_sources": ["pdf", "jpg", "jpeg", "png"],
            "source_policy": "deleted_after_extraction",
            "human_validation_required": True,
            "exports": ["facturx", "xml", "pdf", "compliance_report"],
            "platform_connection": False,
            "scope": ["B2B", "B2C", "international", "credit_notes", "advance_invoices", "reverse_charge"],
        }

    @app.get("/api/facturx/parties")
    def facturx_parties(request: Request, party_type: str | None = None) -> list[dict[str, Any]]:
        context = _require(request, "facturx.view")
        return _repository(request).list_parties(context.tenant_id, party_type)

    @app.post("/api/facturx/parties")
    async def facturx_party_create(request: Request) -> dict[str, Any]:
        context = _require(request, "facturx.edit", write=True)
        payload = await request.json()
        try:
            return _repository(request).save_party(context.tenant_id, payload)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.put("/api/facturx/parties/{party_id}")
    async def facturx_party_update(request: Request, party_id: str) -> dict[str, Any]:
        context = _require(request, "facturx.edit", write=True)
        payload = await request.json()
        try:
            return _repository(request).save_party(context.tenant_id, payload, party_id=party_id)
        except KeyError as exc:
            raise HTTPException(404, "Tiers inconnu") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.delete("/api/facturx/parties/{party_id}", status_code=204)
    def facturx_party_delete(request: Request, party_id: str) -> Response:
        context = _require(request, "facturx.edit", write=True)
        try:
            _repository(request).deactivate_party(context.tenant_id, party_id)
        except KeyError as exc:
            raise HTTPException(404, "Tiers inconnu") from exc
        return Response(status_code=204)

    @app.post("/api/facturx/extract")
    async def facturx_extract(
        request: Request,
        file: UploadFile = File(...),
        direction: str = Form("outgoing"),
    ) -> dict[str, Any]:
        context = _require(request, "facturx.edit", write=True)
        raw = await file.read(MAX_FILE_BYTES + 1)
        try:
            document = prepare_document(file.filename or "facture", file.content_type, raw)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

        document_repository = DocumentControlRepository(request.app.state.registry)
        config = get_connection_config(
            document_repository,
            context.tenant_id,
            include_secret=True,
            reveal_endpoint=True,
        )
        if not config.get("configured"):
            raise HTTPException(
                409,
                "La connexion IA de l’entreprise doit être configurée dans Paramètres avant l’analyse d’une facture.",
            )
        repository = _repository(request)
        parties = repository.list_parties(context.tenant_id)
        try:
            payload = extract_invoice_with_ai(
                config,
                document,
                direction=direction,
                parties=parties,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(502, str(exc)) from exc
        return {
            "payload": payload,
            "source_name": document.filename,
            "source_deleted": True,
            "message": "Document analysé. Le fichier source n’a pas été conservé ; vérifiez les données préremplies avant enregistrement.",
        }

    @app.get("/api/facturx/invoices")
    def facturx_list(request: Request) -> list[dict[str, Any]]:
        context = _require(request, "facturx.view")
        return _repository(request).list_invoices(context.tenant_id)

    @app.post("/api/facturx/invoices")
    async def facturx_create(request: Request) -> dict[str, Any]:
        context = _require(request, "facturx.edit", write=True)
        payload = await request.json()
        try:
            return _repository(request).create_invoice(context.tenant_id, context.actor_id, payload)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/facturx/invoices/{invoice_id}")
    def facturx_detail(request: Request, invoice_id: str) -> dict[str, Any]:
        context = _require(request, "facturx.view")
        try:
            return _repository(request).get_invoice(context.tenant_id, invoice_id)
        except KeyError as exc:
            raise HTTPException(404, "Facture inconnue") from exc

    @app.post("/api/facturx/invoices/{invoice_id}/validate")
    def facturx_validate(request: Request, invoice_id: str) -> dict[str, Any]:
        context = _require(request, "facturx.validate", write=True)
        try:
            return _repository(request).validate_human(context.tenant_id, invoice_id, context.actor_id)
        except KeyError as exc:
            raise HTTPException(404, "Facture inconnue") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/facturx/invoices/{invoice_id}/validation-report.json")
    def facturx_report(request: Request, invoice_id: str) -> Response:
        context = _require(request, "facturx.export")
        try:
            invoice = _repository(request).get_invoice(context.tenant_id, invoice_id)
        except KeyError as exc:
            raise HTTPException(404, "Facture inconnue") from exc
        report = validate_invoice(invoice["payload"])
        return Response(
            json.dumps(report, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{invoice_id}-conformite.json"', "Cache-Control": "no-store"},
        )

    @app.get("/api/facturx/invoices/{invoice_id}/factur-x.xml")
    def facturx_xml(request: Request, invoice_id: str) -> Response:
        context = _require(request, "facturx.export")
        try:
            invoice = _repository(request).get_invoice(context.tenant_id, invoice_id)
        except KeyError as exc:
            raise HTTPException(404, "Facture inconnue") from exc
        if invoice["status"] != "validated":
            raise HTTPException(409, "Une validation humaine est obligatoire avant export")
        try:
            content = build_facturx_xml(invoice["payload"])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return Response(
            content,
            media_type="application/xml",
            headers={"Content-Disposition": 'attachment; filename="factur-x.xml"', "Cache-Control": "no-store"},
        )


def install_facturx_routes() -> None:
    if getattr(FastAPI.__init__, "_axioload_facturx", False):
        return

    previous_init = FastAPI.__init__

    def init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        previous_init(self, *args, **kwargs)
        register_facturx_routes(self)

    init._axioload_facturx = True  # type: ignore[attr-defined]
    FastAPI.__init__ = init  # type: ignore[method-assign]
