from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from . import admin_api
from .admin_service import AdminRepository

_original_register: Callable[..., Any] | None = None


def install_super_admin_routes() -> None:
    """Extend the existing authentication routes without duplicating admin APIs."""
    global _original_register
    if getattr(admin_api.register_admin_routes, "_axioload_super_admin_login", False):
        return
    _original_register = admin_api.register_admin_routes

    def register_admin_routes(
        app: FastAPI,
        admin: AdminRepository,
        templates: Jinja2Templates,
    ) -> None:
        assert _original_register is not None
        _original_register(app, admin, templates)

        @app.middleware("http")
        async def super_admin_cookie_bridge(request: Request, call_next):
            """Allow admin dependencies to use the HttpOnly web session cookie."""
            existing = request.headers.get("X-AxioLoad-Super-Admin") or request.headers.get("Authorization")
            token = request.cookies.get("axioload_session")
            if not existing and token:
                context = admin.resolve_user_session(token)
                if context and context.is_super_admin:
                    headers = list(request.scope.get("headers", []))
                    headers.append((b"x-axioload-super-admin", token.encode("utf-8")))
                    request.scope["headers"] = headers
            return await call_next(request)

        @app.post("/api/auth/super-admin-login")
        def super_admin_login(payload: dict[str, Any]) -> JSONResponse:
            try:
                result = admin.authenticate_super_admin(
                    str(payload.get("identifier") or ""),
                    str(payload.get("password") or ""),
                )
            except ValueError as exc:
                raise HTTPException(401, str(exc)) from exc
            session_token = str(result.pop("session_token"))
            response = JSONResponse(result)
            response.set_cookie(
                "axioload_session",
                session_token,
                httponly=True,
                secure=os.getenv("PLO_COOKIE_SECURE", "0").strip() == "1",
                samesite="lax",
                max_age=30 * 86400,
            )
            response.delete_cookie("axioload_assistance")
            return response

    register_admin_routes._axioload_super_admin_login = True  # type: ignore[attr-defined]
    admin_api.register_admin_routes = register_admin_routes
