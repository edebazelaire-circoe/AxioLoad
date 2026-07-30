from __future__ import annotations

from typing import Annotated, Any

from fastapi import Cookie, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

from .admin_service import AdminRepository, PERMISSION_CATALOG, WebContext


def _problem(exc: Exception, default_status: int = 422) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(404, "Ressource inconnue")
    if isinstance(exc, PermissionError):
        return HTTPException(403, str(exc))
    return HTTPException(default_status, str(exc))


def register_admin_routes(app: FastAPI, admin: AdminRepository, templates: Jinja2Templates) -> None:
    def admin_actor(
        x_axioload_super_admin: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> str:
        try:
            return admin.super_admin_actor(x_axioload_super_admin or authorization)
        except PermissionError as exc:
            raise HTTPException(401, str(exc)) from exc

    def request_context(request: Request) -> WebContext:
        return admin.resolve_web_context(
            request.cookies.get("axioload_assistance"),
            request.cookies.get("axioload_session"),
        )

    @app.get("/activate", response_class=HTMLResponse, include_in_schema=False)
    def activation_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "activate.html", {"app_version": "0.12.0"})

    @app.get("/login", response_class=HTMLResponse, include_in_schema=False)
    def login_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "login.html", {"app_version": "0.12.0"})

    @app.post("/api/auth/logout", status_code=204)
    def logout(axioload_session: Annotated[str | None, Cookie()] = None) -> Response:
        admin.end_user_session(axioload_session)
        response = Response(status_code=204)
        response.delete_cookie("axioload_session")
        return response

    @app.get("/api/invitations/preview")
    def invitation_preview(token: str = Query(..., min_length=20)) -> dict[str, Any]:
        try:
            return admin.invitation_preview(token)
        except (ValueError, KeyError) as exc:
            raise _problem(exc) from exc

    @app.post("/api/invitations/activate")
    def invitation_activate(payload: dict[str, Any]) -> JSONResponse:
        try:
            result = admin.activate_invitation(str(payload.get("token") or ""), str(payload.get("password") or ""))
        except (ValueError, KeyError) as exc:
            raise _problem(exc) from exc
        session_token = result.pop("session_token")
        response = JSONResponse(result)
        response.set_cookie("axioload_session", session_token, httponly=True, secure=False, samesite="lax", max_age=30 * 86400)
        return response

    @app.post("/api/auth/login")
    def login(payload: dict[str, Any]) -> JSONResponse:
        try:
            result = admin.authenticate(
                str(payload.get("tenant_id") or ""),
                str(payload.get("email") or ""),
                str(payload.get("password") or ""),
            )
        except ValueError as exc:
            raise HTTPException(401, str(exc)) from exc
        session_token = result.pop("session_token")
        response = JSONResponse(result)
        response.set_cookie("axioload_session", session_token, httponly=True, secure=False, samesite="lax", max_age=30 * 86400)
        return response

    @app.get("/api/company/context")
    def company_context(request: Request) -> dict[str, Any]:
        context = request_context(request)
        company = admin.get_company(context.tenant_id)
        user = None
        if context.actor_type == "user" and context.actor_id != "local-user":
            try:
                user = admin.get_user(context.actor_id)
            except KeyError:
                user = None
        return {
            "mode": "assistance" if context.is_super_admin else "user",
            "company": company,
            "user": user,
            "actor": context.actor_label,
            "permissions": {key: True for key in company["permissions"]}
            if context.is_super_admin
            else admin.effective_permissions(context.tenant_id, None if context.actor_id == "local-user" else context.actor_id),
        }

    @app.get("/api/company/profile")
    def company_profile(request: Request) -> dict[str, Any]:
        context = request_context(request)
        return admin.get_company(context.tenant_id)

    @app.put("/api/company/profile")
    def company_profile_update(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        context = request_context(request)
        try:
            return admin.submit_profile(context, payload)
        except (ValueError, PermissionError) as exc:
            raise _problem(exc) from exc

    @app.post("/api/company/activity", status_code=204)
    def company_activity(request: Request, payload: dict[str, Any]) -> Response:
        context = request_context(request)
        admin.record_activity(
            context.tenant_id,
            None if context.actor_id == "local-user" else context.actor_id,
            int(payload.get("active_seconds") or 0),
            str(payload.get("event_type") or "activity")[:50],
        )
        return Response(status_code=204)

    @app.get("/api/admin/bootstrap")
    def admin_bootstrap(
        actor: str = Header(default=None, alias="X-Resolved-Admin", include_in_schema=False),
        x_axioload_super_admin: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
        date_from: str | None = Query(None, alias="from"),
        date_to: str | None = Query(None, alias="to"),
    ) -> dict[str, Any]:
        del actor
        resolved = admin.super_admin_actor(x_axioload_super_admin or authorization)
        return {
            "actor": resolved,
            "permissions": list(PERMISSION_CATALOG),
            "companies": admin.list_companies(),
            "dashboard": admin.dashboard(tenant_id=None, start=date_from, end=date_to),
            "email": admin.email_configuration(),
            "audit": admin.list_audit(limit=40),
        }

    @app.get("/api/admin/dashboard")
    def admin_dashboard(
        tenant_id: str | None = None,
        date_from: str | None = Query(None, alias="from"),
        date_to: str | None = Query(None, alias="to"),
        users: str | None = None,
        actor: str = Header(default=None, alias="X-Resolved-Admin", include_in_schema=False),
        x_axioload_super_admin: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        del actor
        admin.super_admin_actor(x_axioload_super_admin or authorization)
        user_ids = [value for value in (users or "").split(",") if value]
        return admin.dashboard(tenant_id=tenant_id, start=date_from, end=date_to, user_ids=user_ids)

    @app.post("/api/admin/companies", status_code=201)
    def company_create(
        request: Request,
        payload: dict[str, Any],
        actor: str = Header(default=None, alias="X-Resolved-Admin", include_in_schema=False),
        x_axioload_super_admin: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        del actor
        resolved = admin.super_admin_actor(x_axioload_super_admin or authorization)
        try:
            return admin.create_company_invitation(
                str(payload.get("company_name") or ""),
                str(payload.get("email") or ""),
                str(payload.get("first_name") or ""),
                str(payload.get("last_name") or ""),
                payload.get("permissions") if isinstance(payload.get("permissions"), dict) else None,
                resolved,
                str(request.base_url),
            )
        except (ValueError, KeyError) as exc:
            raise _problem(exc) from exc

    @app.get("/api/admin/companies/{tenant_id}")
    def company_detail(
        tenant_id: str,
        x_axioload_super_admin: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        admin.super_admin_actor(x_axioload_super_admin or authorization)
        try:
            return {
                "company": admin.get_company(tenant_id),
                "users": admin.list_users(tenant_id),
                "api_keys": admin.list_api_keys(tenant_id),
                "dashboard": admin.dashboard(tenant_id=tenant_id, start=None, end=None),
                "audit": admin.list_audit(tenant_id, 80),
            }
        except KeyError as exc:
            raise _problem(exc) from exc

    @app.put("/api/admin/companies/{tenant_id}/permissions")
    def company_permissions_update(
        tenant_id: str,
        payload: dict[str, Any],
        x_axioload_super_admin: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, bool]:
        actor = admin.super_admin_actor(x_axioload_super_admin or authorization)
        try:
            return admin.set_company_permissions(tenant_id, payload, actor=actor)
        except (ValueError, KeyError) as exc:
            raise _problem(exc) from exc

    @app.post("/api/admin/companies/{tenant_id}/status")
    def company_status_update(
        tenant_id: str,
        payload: dict[str, Any],
        x_axioload_super_admin: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        actor = admin.super_admin_actor(x_axioload_super_admin or authorization)
        try:
            return admin.update_company_status(
                tenant_id,
                str(payload.get("status") or ""),
                actor=actor,
                suspension_mode=str(payload.get("suspension_mode") or "block"),
                reactivate_keys=bool(payload.get("reactivate_keys", False)),
            )
        except (ValueError, KeyError) as exc:
            raise _problem(exc) from exc

    @app.post("/api/admin/companies/{tenant_id}/profile-decision")
    def company_profile_decision(
        tenant_id: str,
        payload: dict[str, Any],
        x_axioload_super_admin: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        actor = admin.super_admin_actor(x_axioload_super_admin or authorization)
        try:
            return admin.decide_profile(
                tenant_id,
                str(payload.get("decision") or ""),
                str(payload.get("comment") or ""),
                actor,
            )
        except (ValueError, KeyError) as exc:
            raise _problem(exc) from exc

    @app.post("/api/admin/companies/{tenant_id}/users", status_code=201)
    def company_user_invite(
        request: Request,
        tenant_id: str,
        payload: dict[str, Any],
        x_axioload_super_admin: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        actor = admin.super_admin_actor(x_axioload_super_admin or authorization)
        try:
            return admin.invite_user(
                tenant_id,
                first_name=str(payload.get("first_name") or ""),
                last_name=str(payload.get("last_name") or ""),
                email=str(payload.get("email") or ""),
                overrides=payload.get("permissions") if isinstance(payload.get("permissions"), dict) else None,
                actor=actor,
                base_url=str(request.base_url),
            )
        except (ValueError, KeyError) as exc:
            raise _problem(exc) from exc

    @app.put("/api/admin/companies/{tenant_id}/users/{user_id}/permissions")
    def user_permissions_update(
        tenant_id: str,
        user_id: str,
        payload: dict[str, Any],
        x_axioload_super_admin: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, str]:
        actor = admin.super_admin_actor(x_axioload_super_admin or authorization)
        try:
            user = admin.get_user(user_id)
            if user["tenant_id"] != tenant_id:
                raise KeyError(user_id)
            return admin.set_user_permissions(user_id, payload, actor=actor)
        except (ValueError, KeyError) as exc:
            raise _problem(exc) from exc

    @app.post("/api/admin/companies/{tenant_id}/users/{user_id}/disable")
    def user_disable(
        tenant_id: str,
        user_id: str,
        payload: dict[str, Any],
        x_axioload_super_admin: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        actor = admin.super_admin_actor(x_axioload_super_admin or authorization)
        try:
            return admin.disable_user(tenant_id, user_id, actor, payload.get("transfer_to_user_id"))
        except (ValueError, KeyError) as exc:
            raise _problem(exc) from exc

    @app.post("/api/admin/companies/{tenant_id}/users/{user_id}/resend")
    def invitation_resend(
        request: Request,
        tenant_id: str,
        user_id: str,
        x_axioload_super_admin: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        actor = admin.super_admin_actor(x_axioload_super_admin or authorization)
        try:
            return admin.resend_invitation(tenant_id, user_id, actor, str(request.base_url))
        except (ValueError, KeyError) as exc:
            raise _problem(exc) from exc

    @app.post("/api/admin/companies/{tenant_id}/api-keys", status_code=201)
    def api_key_create(
        tenant_id: str,
        payload: dict[str, Any],
        x_axioload_super_admin: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        actor = admin.super_admin_actor(x_axioload_super_admin or authorization)
        try:
            return admin.create_api_key(
                tenant_id,
                str(payload.get("label") or ""),
                payload.get("scopes") if isinstance(payload.get("scopes"), list) else [],
                str(payload.get("expires_at")) if payload.get("expires_at") else None,
                actor,
            )
        except (ValueError, KeyError) as exc:
            raise _problem(exc) from exc

    @app.delete("/api/admin/companies/{tenant_id}/api-keys/{key_id}", status_code=204)
    def api_key_revoke(
        tenant_id: str,
        key_id: str,
        x_axioload_super_admin: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> Response:
        actor = admin.super_admin_actor(x_axioload_super_admin or authorization)
        try:
            admin.revoke_api_key(tenant_id, key_id, actor)
        except KeyError as exc:
            raise _problem(exc) from exc
        return Response(status_code=204)

    @app.post("/api/admin/companies/{tenant_id}/assistance")
    def assistance_start(
        tenant_id: str,
        x_axioload_super_admin: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> JSONResponse:
        actor = admin.super_admin_actor(x_axioload_super_admin or authorization)
        try:
            token = admin.start_assistance(tenant_id, actor)
        except KeyError as exc:
            raise _problem(exc) from exc
        response = JSONResponse({"tenant_id": tenant_id, "mode": "assistance"})
        response.set_cookie("axioload_assistance", token, httponly=True, secure=False, samesite="lax", max_age=8 * 3600)
        return response

    @app.post("/api/admin/assistance/exit", status_code=204)
    def assistance_exit(
        axioload_assistance: Annotated[str | None, Cookie()] = None,
    ) -> Response:
        admin.end_assistance(axioload_assistance)
        response = Response(status_code=204)
        response.delete_cookie("axioload_assistance")
        return response

    @app.get("/api/admin/audit")
    def audit_list(
        tenant_id: str | None = None,
        limit: int = Query(100, ge=1, le=500),
        x_axioload_super_admin: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> list[dict[str, Any]]:
        admin.super_admin_actor(x_axioload_super_admin or authorization)
        return admin.list_audit(tenant_id, limit)
