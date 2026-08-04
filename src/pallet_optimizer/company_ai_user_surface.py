from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from . import document_control_bootstrap as dcb
from .document_control import DocumentControlRepository

_SURFACE_SCRIPT = b'<script src="/static/company_ai_user_surface.js?v=0.19.7"></script>'
_LEGACY_SCRIPTS = (
    b'<script src="/static/company_ai_endpoint.js?v=0.19.5"></script>',
    b'<script src="/static/company_ai_endpoint.js?v=0.19.6"></script>',
)


def register_company_ai_user_surface_routes(app: FastAPI) -> None:
    if getattr(app.state, "_company_ai_user_surface_registered", False):
        return
    app.state._company_ai_user_surface_registered = True

    @app.get("/api/company/document-ai-status")
    def company_ai_status(request: Request) -> JSONResponse:
        context = dcb._require(request, "document_control.view")
        repository = DocumentControlRepository(request.app.state.registry)
        config = repository.get_connection_config(context.tenant_id)  # type: ignore[attr-defined]
        payload = {
            "configured": bool(config.get("configured")),
            "connection_mode": str(config.get("connection_mode") or "endpoint"),
            "provider": str(config.get("provider") or ""),
            "model": str(config.get("model") or ""),
            "can_manage": dcb._primary(request, context),
            "explanation": (
                "La connexion au contrôle documentaire se configure dans les Paramètres "
                "de l’espace utilisateur. Seul le responsable principal de l’entreprise "
                "peut enregistrer ou remplacer une passerelle ou une clé API."
            ),
        }
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})


def _install_company_ai_user_surface_assets() -> None:
    previous = Jinja2Templates.TemplateResponse
    if getattr(previous, "_axioload_company_ai_user_surface", False):
        return

    def template_response(self: Jinja2Templates, *args: Any, **kwargs: Any) -> Any:
        response = previous(self, *args, **kwargs)
        body = getattr(response, "body", b"")
        if b"</body>" not in body:
            return response

        for legacy_script in _LEGACY_SCRIPTS:
            body = body.replace(legacy_script, b"")
        body = body.replace(_SURFACE_SCRIPT, b"")
        body = body.replace(b"</body>", _SURFACE_SCRIPT + b"</body>")
        response.body = body
        response.headers["content-length"] = str(len(body))
        return response

    template_response._axioload_company_ai_user_surface = True  # type: ignore[attr-defined]
    Jinja2Templates.TemplateResponse = template_response  # type: ignore[method-assign]


def install_company_ai_user_surface() -> None:
    if getattr(FastAPI.__init__, "_axioload_company_ai_user_surface", False):
        return

    _install_company_ai_user_surface_assets()
    previous_fastapi_init = FastAPI.__init__

    def init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        previous_fastapi_init(self, *args, **kwargs)
        register_company_ai_user_surface_routes(self)

    init._axioload_company_ai_user_surface = True  # type: ignore[attr-defined]
    FastAPI.__init__ = init  # type: ignore[method-assign]
