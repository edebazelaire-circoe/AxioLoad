from __future__ import annotations

import importlib
import os
from importlib.metadata import PackageNotFoundError, version as distribution_version
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from . import admin_base

_STYLE = b'<link rel="stylesheet" href="/static/admin_coherence.css?v=0.20.0">'
_SCRIPT = b'<script src="/static/admin_coherence.js?v=0.20.0"></script>'
_original_fastapi_init = FastAPI.__init__
_original_template_response = Jinja2Templates.TemplateResponse


def _enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _runtime_version() -> str:
    try:
        package = importlib.import_module("pallet_optimizer")
        return str(getattr(package, "__version__", "unknown"))
    except Exception:
        return "unknown"


def _distribution_version() -> str:
    try:
        return distribution_version("pallet-loading-optimizer")
    except PackageNotFoundError:
        return "unknown"


def _modules() -> list[dict[str, Any]]:
    permissions = {entry["key"] for entry in admin_base.PERMISSION_CATALOG}
    definitions = (
        ("loading", "Optimisation de chargement", ("vehicles.view", "data.view", "results.run")),
        ("history", "Historique et validation", ("history.view", "history.validate")),
        ("route", "Itinéraires", ("route.view", "route.run")),
        ("total", "Optimisation totale", ("total.view", "total.run")),
        ("document_control", "Contrôle documentaire", ("document_control.view", "document_control.run")),
        ("facturx", "Factur-X", ("facturx.view", "facturx.edit", "facturx.validate", "facturx.export")),
        ("api", "API publique", ("api.use", "results.run")),
    )
    return [
        {
            "key": key,
            "label": label,
            "permissions": list(required),
            "available": all(permission in permissions for permission in required),
        }
        for key, label, required in definitions
    ]


def _snapshot(app: FastAPI) -> dict[str, Any]:
    runtime = _runtime_version()
    distribution = _distribution_version()
    api_version = str(getattr(app, "version", "unknown"))
    versions = {
        "runtime": runtime,
        "distribution": distribution,
        "api": api_version,
    }
    known_versions = {value for value in versions.values() if value and value != "unknown"}

    test_mode = _enabled(os.getenv("PLO_TEST_ACCOUNTS_ONLY"))
    cookie_secure = _enabled(os.getenv("PLO_COOKIE_SECURE"))
    super_admin_password_configured = bool(os.getenv("PLO_SUPER_ADMIN_PASSWORD", "").strip())
    document_secret_configured = bool(os.getenv("PLO_DOCUMENT_SECRET_KEY", "").strip())

    warnings: list[dict[str, str]] = []
    if len(known_versions) > 1:
        warnings.append(
            {
                "severity": "warning",
                "code": "version_drift",
                "message": "Les versions runtime, distribution et API ne sont pas alignées.",
            }
        )
    if test_mode:
        warnings.append(
            {
                "severity": "critical",
                "code": "test_accounts_enabled",
                "message": "Le mode de comptes de test est actif. Il doit rester désactivé en production.",
            }
        )
    if not super_admin_password_configured:
        warnings.append(
            {
                "severity": "critical",
                "code": "super_admin_secret_missing",
                "message": "Aucun secret super-administrateur externe n'est configuré.",
            }
        )
    if not cookie_secure:
        warnings.append(
            {
                "severity": "warning",
                "code": "secure_cookie_disabled",
                "message": "PLO_COOKIE_SECURE n'est pas activé. Utilisez HTTPS et des cookies Secure en production.",
            }
        )
    if not document_secret_configured:
        warnings.append(
            {
                "severity": "warning",
                "code": "document_secret_missing",
                "message": "PLO_DOCUMENT_SECRET_KEY n'est pas configurée : le mode IA par clé API ne peut pas chiffrer ses secrets.",
            }
        )

    return {
        "versions": versions,
        "modules": _modules(),
        "deployment": {
            "test_accounts_enabled": test_mode,
            "cookie_secure": cookie_secure,
            "super_admin_secret_configured": super_admin_password_configured,
            "document_secret_configured": document_secret_configured,
            "osrm_url": os.getenv("AXIOLOAD_OSRM_URL", "https://router.project-osrm.org"),
            "nominatim_url": os.getenv("AXIOLOAD_NOMINATIM_URL", "https://nominatim.openstreetmap.org"),
        },
        "warnings": warnings,
    }


def register_admin_coherence_routes(app: FastAPI) -> None:
    if getattr(app.state, "_admin_coherence_registered", False):
        return
    app.state._admin_coherence_registered = True

    @app.get("/api/admin/coherence", include_in_schema=False)
    def admin_coherence(request: Request) -> JSONResponse:
        context = request.app.state.admin.resolve_user_session(
            request.cookies.get("axioload_session")
        )
        if not context or not context.is_super_admin:
            raise HTTPException(401, "Connexion super administrateur requise")
        return JSONResponse(_snapshot(request.app), headers={"Cache-Control": "no-store"})


def _install_assets() -> None:
    if getattr(Jinja2Templates.TemplateResponse, "_axioload_admin_coherence", False):
        return

    previous = Jinja2Templates.TemplateResponse

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

    template_response._axioload_admin_coherence = True  # type: ignore[attr-defined]
    Jinja2Templates.TemplateResponse = template_response  # type: ignore[method-assign]


def install_admin_coherence() -> None:
    if getattr(FastAPI.__init__, "_axioload_admin_coherence", False):
        return
    _install_assets()
    previous_init = FastAPI.__init__

    def init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        previous_init(self, *args, **kwargs)
        register_admin_coherence_routes(self)

    init._axioload_admin_coherence = True  # type: ignore[attr-defined]
    FastAPI.__init__ = init  # type: ignore[method-assign]
