from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from . import admin_api
from .admin_service import AdminRepository
from .fixed_test_accounts import (
    DEFAULT_TEST_USER_EMAIL,
    DEFAULT_TEST_USER_PASSWORD,
    TEST_COMPANY_NAME,
    TEST_TENANT_ID,
    fixed_test_accounts_enabled,
)

_original_register: Callable[..., Any] | None = None

_PUBLIC_PATHS = {
    "/health",
    "/login",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/super-admin-login",
    "/api/auth/test-accounts",
    "/docs",
    "/openapi.json",
    "/redoc",
}


def _test_user_credentials() -> tuple[str, str]:
    email = (
        os.getenv("PLO_TEST_USER_EMAIL", DEFAULT_TEST_USER_EMAIL).strip().lower()
        or DEFAULT_TEST_USER_EMAIL
    )
    password = os.getenv("PLO_TEST_USER_PASSWORD", DEFAULT_TEST_USER_PASSWORD)
    return email, password or DEFAULT_TEST_USER_PASSWORD


def install_fixed_test_login_gate() -> None:
    """Require one of the two fixed accounts before opening the test application."""
    global _original_register
    if getattr(admin_api.register_admin_routes, "_axioload_fixed_test_login_gate", False):
        return
    _original_register = admin_api.register_admin_routes

    def register_admin_routes(
        app: FastAPI,
        admin: AdminRepository,
        templates: Jinja2Templates,
    ) -> None:
        assert _original_register is not None
        _original_register(app, admin, templates)

        @app.get("/api/auth/test-accounts", include_in_schema=False)
        def test_accounts() -> dict[str, Any]:
            if not fixed_test_accounts_enabled():
                raise HTTPException(404, "Mode de test inactif")
            admin_email, admin_username, admin_password = admin.super_admin_credentials()
            company_email, company_password = _test_user_credentials()
            return {
                "enabled": True,
                "accounts": [
                    {
                        "key": "super_admin",
                        "mode": "super_admin",
                        "label": "Super administrateur",
                        "description": "Vision globale : entreprises, utilisateurs et configuration générale.",
                        "identifier": admin_email,
                        "username": admin_username,
                        "password": admin_password,
                    },
                    {
                        "key": "company_admin",
                        "mode": "user",
                        "label": "Administrateur principal d’entreprise",
                        "description": "Vision complète de sa propre entreprise, sans accès au Centre de gestion.",
                        "tenant_id": TEST_TENANT_ID,
                        "company_name": TEST_COMPANY_NAME,
                        "identifier": company_email,
                        "password": company_password,
                    },
                ],
            }

        @app.middleware("http")
        async def fixed_test_authentication_gate(request: Request, call_next) -> Response:
            if not fixed_test_accounts_enabled():
                return await call_next(request)

            path = request.url.path
            if path.startswith("/static/") or path in _PUBLIC_PATHS:
                return await call_next(request)

            session = admin.resolve_user_session(request.cookies.get("axioload_session"))
            if session:
                return await call_next(request)

            accepts_html = "text/html" in request.headers.get("accept", "")
            if request.method == "GET" and (path == "/" or accepts_html):
                return RedirectResponse("/login", status_code=303)
            return JSONResponse({"detail": "Connexion requise"}, status_code=401)

    register_admin_routes._axioload_fixed_test_login_gate = True  # type: ignore[attr-defined]
    admin_api.register_admin_routes = register_admin_routes
