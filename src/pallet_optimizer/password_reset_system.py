from __future__ import annotations

import secrets
import string
import uuid
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Cookie, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from . import admin_api
from .admin_service import AdminRepository, SUPER_ADMIN_USER_ID
from .persistence import _connect, _hash_secret, _verify_secret, utc_now

APP_VERSION = "0.17.0"
GENERIC_REQUEST_MESSAGE = (
    "Si ce compte existe, la demande a été transmise au super administrateur. "
    "Un mot de passe temporaire vous sera communiqué par le canal habituel."
)

_original_register: Callable[..., Any] | None = None
_original_get_user: Callable[..., Any] | None = None
_original_authenticate: Callable[..., Any] | None = None


def _ensure_schema(admin: AdminRepository) -> None:
    with _connect(admin.registry.registry_path) as db:
        columns = {
            str(row["name"])
            for row in db.execute("PRAGMA table_info(company_users)").fetchall()
        }
        if "must_change_password" not in columns:
            db.execute(
                "ALTER TABLE company_users "
                "ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0"
            )
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS password_reset_requests (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL REFERENCES tenants(id),
                user_id TEXT NOT NULL REFERENCES company_users(id),
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                resolved_at TEXT,
                resolved_by TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_password_reset_pending
                ON password_reset_requests(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_password_reset_user
                ON password_reset_requests(user_id, status);
            """
        )


def _install_repository_extensions() -> None:
    global _original_get_user, _original_authenticate
    if getattr(AdminRepository, "_axioload_password_reset", False):
        return

    _original_get_user = AdminRepository.get_user
    _original_authenticate = AdminRepository.authenticate

    def get_user(self: AdminRepository, user_id: str) -> dict[str, Any]:
        assert _original_get_user is not None
        result = _original_get_user(self, user_id)
        _ensure_schema(self)
        with _connect(self.registry.registry_path) as db:
            row = db.execute(
                "SELECT must_change_password FROM company_users WHERE id=?",
                (user_id,),
            ).fetchone()
        result["must_change_password"] = bool(row and row["must_change_password"])
        return result

    def authenticate(
        self: AdminRepository,
        tenant_id: str,
        email: str,
        password: str,
    ) -> dict[str, Any]:
        assert _original_authenticate is not None
        result = _original_authenticate(self, tenant_id, email, password)
        result["must_change_password"] = bool(
            result.get("user", {}).get("must_change_password", False)
        )
        return result

    AdminRepository.get_user = get_user  # type: ignore[method-assign]
    AdminRepository.authenticate = authenticate  # type: ignore[method-assign]
    AdminRepository._axioload_password_reset = True  # type: ignore[attr-defined]


def _super_admin(
    request: Request,
    admin: AdminRepository,
    token: str | None,
    authorization: str | None,
) -> str:
    candidate = token or authorization or request.cookies.get("axioload_session")
    try:
        return admin.super_admin_actor(candidate)
    except PermissionError as exc:
        raise HTTPException(401, str(exc)) from exc


def _temporary_password() -> str:
    alphabet = string.ascii_letters + string.digits
    body = "".join(secrets.choice(alphabet) for _ in range(14))
    return f"Axio-{body}!"


def install_password_reset_system() -> None:
    global _original_register
    if getattr(admin_api.register_admin_routes, "_axioload_password_reset", False):
        return

    _install_repository_extensions()
    _original_register = admin_api.register_admin_routes

    def register_admin_routes(
        app: FastAPI,
        admin: AdminRepository,
        templates: Jinja2Templates,
    ) -> None:
        assert _original_register is not None
        _ensure_schema(admin)
        _original_register(app, admin, templates)

        @app.get("/change-password", response_class=HTMLResponse, include_in_schema=False)
        def change_password_page(
            request: Request,
            axioload_session: Annotated[str | None, Cookie()] = None,
        ) -> HTMLResponse:
            context = admin.resolve_user_session(axioload_session)
            if not context or context.is_super_admin:
                raise HTTPException(401, "Connexion utilisateur requise")
            return templates.TemplateResponse(
                request,
                "change_password.html",
                {"app_version": APP_VERSION, "actor": context.actor_label},
            )

        @app.post("/api/auth/forgot-password")
        async def forgot_password(request: Request) -> dict[str, str]:
            payload = await request.json()
            tenant_id = str(payload.get("tenant_id") or "").strip()
            email = str(payload.get("email") or "").strip().lower()
            if tenant_id and email and "@" in email:
                with _connect(admin.registry.registry_path) as db:
                    user = db.execute(
                        """SELECT id FROM company_users
                           WHERE tenant_id=? AND email=? AND active=1
                             AND role <> 'super_admin'""",
                        (tenant_id, email),
                    ).fetchone()
                    if user:
                        now = utc_now()
                        db.execute(
                            """UPDATE password_reset_requests
                               SET status='superseded',resolved_at=?,resolved_by='new_request'
                               WHERE user_id=? AND status='pending'""",
                            (now, user["id"]),
                        )
                        request_id = str(uuid.uuid4())
                        db.execute(
                            """INSERT INTO password_reset_requests(
                                   id,tenant_id,user_id,status,created_at
                               ) VALUES (?,?,?,'pending',?)""",
                            (request_id, tenant_id, user["id"], now),
                        )
                        admin.audit(
                            tenant_id,
                            email,
                            "password_reset.requested",
                            str(user["id"]),
                            {},
                            {"request_id": request_id},
                        )
            return {"message": GENERIC_REQUEST_MESSAGE}

        @app.get("/api/admin/password-reset-requests")
        def password_reset_requests(
            request: Request,
            status: str = "pending",
            x_axioload_super_admin: Annotated[str | None, Header()] = None,
            authorization: Annotated[str | None, Header()] = None,
        ) -> dict[str, Any]:
            _super_admin(
                request,
                admin,
                x_axioload_super_admin,
                authorization,
            )
            requested_status = status if status in {"pending", "resolved", "all"} else "pending"
            where = "" if requested_status == "all" else "WHERE r.status=?"
            params: tuple[Any, ...] = () if requested_status == "all" else (requested_status,)
            with _connect(admin.registry.registry_path) as db:
                rows = db.execute(
                    f"""SELECT r.*,u.first_name,u.last_name,u.email,u.active,
                               t.name AS company_name
                        FROM password_reset_requests r
                        JOIN company_users u ON u.id=r.user_id
                        JOIN tenants t ON t.id=r.tenant_id
                        {where}
                        ORDER BY r.created_at DESC
                        LIMIT 200""",
                    params,
                ).fetchall()
            return {
                "requests": [
                    {
                        "id": row["id"],
                        "tenant_id": row["tenant_id"],
                        "company_name": row["company_name"],
                        "user_id": row["user_id"],
                        "user_name": f"{row['first_name']} {row['last_name']}".strip(),
                        "email": row["email"],
                        "active": bool(row["active"]),
                        "status": row["status"],
                        "created_at": row["created_at"],
                        "resolved_at": row["resolved_at"],
                        "resolved_by": row["resolved_by"],
                    }
                    for row in rows
                ]
            }

        @app.post("/api/admin/users/{user_id}/password-reset")
        def reset_user_password(
            request: Request,
            user_id: str,
            x_axioload_super_admin: Annotated[str | None, Header()] = None,
            authorization: Annotated[str | None, Header()] = None,
        ) -> dict[str, Any]:
            actor = _super_admin(
                request,
                admin,
                x_axioload_super_admin,
                authorization,
            )
            if user_id == SUPER_ADMIN_USER_ID:
                raise HTTPException(422, "Le compte super administrateur se configure sur le serveur")
            with _connect(admin.registry.registry_path) as db:
                user = db.execute(
                    "SELECT * FROM company_users WHERE id=?",
                    (user_id,),
                ).fetchone()
                if not user:
                    raise HTTPException(404, "Utilisateur inconnu")
                if not user["active"]:
                    raise HTTPException(422, "Seul un utilisateur actif peut recevoir un mot de passe temporaire")
                temporary_password = _temporary_password()
                salt, digest = _hash_secret(temporary_password)
                now = utc_now()
                db.execute(
                    """UPDATE company_users
                       SET password_salt=?,password_digest=?,must_change_password=1
                       WHERE id=?""",
                    (salt, digest, user_id),
                )
                db.execute(
                    "UPDATE user_sessions SET ended_at=? WHERE user_id=? AND ended_at IS NULL",
                    (now, user_id),
                )
                db.execute(
                    """UPDATE password_reset_requests
                       SET status='resolved',resolved_at=?,resolved_by=?
                       WHERE user_id=? AND status='pending'""",
                    (now, actor, user_id),
                )
            admin.audit(
                str(user["tenant_id"]),
                actor,
                "password_reset.admin_completed",
                user_id,
                {},
                {"temporary_password": "visible_once", "must_change_password": True},
            )
            return {
                "user": admin.get_user(user_id),
                "temporary_password": temporary_password,
                "visible_once": True,
            }

        @app.post("/api/auth/change-password")
        async def change_password(
            request: Request,
            axioload_session: Annotated[str | None, Cookie()] = None,
        ) -> dict[str, Any]:
            context = admin.resolve_user_session(axioload_session)
            if not context or context.is_super_admin:
                raise HTTPException(401, "Connexion utilisateur requise")
            payload = await request.json()
            current_password = str(payload.get("current_password") or "")
            new_password = str(payload.get("new_password") or "")
            if len(new_password) < 10:
                raise HTTPException(422, "Le nouveau mot de passe doit contenir au moins 10 caractères")
            if new_password == current_password:
                raise HTTPException(422, "Le nouveau mot de passe doit être différent du mot de passe temporaire")
            with _connect(admin.registry.registry_path) as db:
                user = db.execute(
                    "SELECT * FROM company_users WHERE id=? AND active=1",
                    (context.actor_id,),
                ).fetchone()
                if not user or not user["password_salt"] or not _verify_secret(
                    current_password,
                    user["password_salt"],
                    user["password_digest"],
                ):
                    raise HTTPException(401, "Mot de passe actuel invalide")
                salt, digest = _hash_secret(new_password)
                now = utc_now()
                db.execute(
                    """UPDATE company_users
                       SET password_salt=?,password_digest=?,must_change_password=0
                       WHERE id=?""",
                    (salt, digest, context.actor_id),
                )
                db.execute(
                    """UPDATE user_sessions SET ended_at=?
                       WHERE user_id=? AND id<>? AND ended_at IS NULL""",
                    (now, context.actor_id, axioload_session),
                )
            admin.audit(
                context.tenant_id,
                context.actor_label,
                "password_reset.user_changed",
                context.actor_id,
                {},
                {"must_change_password": False},
            )
            return {"success": True, "user": admin.get_user(context.actor_id)}

    register_admin_routes._axioload_password_reset = True  # type: ignore[attr-defined]
    admin_api.register_admin_routes = register_admin_routes
