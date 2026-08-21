from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from . import admin_integrations, admin_invitations, admin_service, fixed_test_accounts, password_reset_system, persistence
from .admin_service import AdminRepository, SUPER_ADMIN_USER_ID, WebContext
from .persistence import _connect, utc_now

_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_SESSION_COOKIES = ("axioload_session", "axioload_assistance")
_PUBLIC_PATHS = frozenset({
    "/health",
    "/login",
    "/activate",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/super-admin-login",
    "/api/auth/forgot-password",
    "/api/auth/test-accounts",
    "/api/invitations/preview",
    "/api/invitations/activate",
    "/docs",
    "/openapi.json",
    "/redoc",
})
_ARGON2 = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,
    parallelism=2,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


def _enabled(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _local_mode_enabled() -> bool:
    return _enabled("PLO_LOCAL_MODE", "0")


def _token_id(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _hash_secret_argon2(secret: str, salt: bytes | None = None) -> tuple[str, str]:
    del salt
    return "argon2id", _ARGON2.hash(secret)


def _verify_secret_compatible(secret: str, salt_value: str, digest_value: str) -> bool:
    if digest_value.startswith("$argon2"):
        try:
            return bool(_ARGON2.verify(digest_value, secret))
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
    try:
        salt = bytes.fromhex(salt_value)
        candidate = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, 200_000).hex()
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(candidate, digest_value)


def _rehash_company_user(admin: AdminRepository, user_id: str, password: str) -> None:
    with _connect(admin.registry.registry_path) as db:
        row = db.execute(
            "SELECT password_digest FROM company_users WHERE id=?",
            (user_id,),
        ).fetchone()
        if not row or str(row["password_digest"] or "").startswith("$argon2"):
            return
        salt, digest = _hash_secret_argon2(password)
        db.execute(
            "UPDATE company_users SET password_salt=?,password_digest=? WHERE id=?",
            (salt, digest, user_id),
        )


def _create_user_session(self: AdminRepository, tenant_id: str, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    with _connect(self.registry.registry_path) as db:
        user = db.execute(
            "SELECT tenant_id,active FROM company_users WHERE id=?",
            (user_id,),
        ).fetchone()
        if not user or not bool(user["active"]) or str(user["tenant_id"]) != tenant_id:
            raise PermissionError("Utilisateur invalide pour cette entreprise")
        db.execute(
            "INSERT INTO user_sessions(id,tenant_id,user_id,created_at,expires_at) VALUES (?,?,?,?,?)",
            (_token_id(token), tenant_id, user_id, now.isoformat(), (now + timedelta(hours=8)).isoformat()),
        )
    return token


def _resolve_user_session(self: AdminRepository, token: str | None) -> WebContext | None:
    if not token:
        return None
    digest = _token_id(token)
    with _connect(self.registry.registry_path) as db:
        row = db.execute(
            """SELECT s.*,u.first_name,u.last_name,u.email,u.active
               FROM user_sessions s
               JOIN company_users u ON u.id=s.user_id AND u.tenant_id=s.tenant_id
               WHERE s.id IN (?,?) AND s.ended_at IS NULL AND s.expires_at>?
               ORDER BY CASE WHEN s.id=? THEN 0 ELSE 1 END
               LIMIT 1""",
            (digest, token, utc_now(), digest),
        ).fetchone()
    if not row or not bool(row["active"]):
        return None
    return WebContext(
        tenant_id=str(row["tenant_id"]),
        actor_id=str(row["user_id"]),
        actor_label=f"{row['first_name']} {row['last_name']}".strip() or str(row["email"]),
        actor_type="user",
    )


def _end_user_session(self: AdminRepository, token: str | None) -> None:
    if not token:
        return
    with _connect(self.registry.registry_path) as db:
        db.execute(
            "UPDATE user_sessions SET ended_at=? WHERE id IN (?,?) AND ended_at IS NULL",
            (utc_now(), _token_id(token), token),
        )


def _start_assistance(self: AdminRepository, tenant_id: str, actor: str) -> str:
    self.get_company(tenant_id)
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    with _connect(self.registry.registry_path) as db:
        db.execute(
            "INSERT INTO assistance_sessions(id,tenant_id,actor,created_at,expires_at) VALUES (?,?,?,?,?)",
            (_token_id(token), tenant_id, actor, now.isoformat(), (now + timedelta(hours=2)).isoformat()),
        )
    self.audit(tenant_id, actor, "assistance.started", _token_id(token), {}, {})
    return token


def _resolve_assistance(self: AdminRepository, token: str | None) -> WebContext | None:
    if not token:
        return None
    digest = _token_id(token)
    with _connect(self.registry.registry_path) as db:
        row = db.execute(
            """SELECT * FROM assistance_sessions
               WHERE id IN (?,?) AND ended_at IS NULL AND expires_at>?
               ORDER BY CASE WHEN id=? THEN 0 ELSE 1 END
               LIMIT 1""",
            (digest, token, utc_now(), digest),
        ).fetchone()
    if not row:
        return None
    return WebContext(
        tenant_id=str(row["tenant_id"]),
        actor_id=str(row["actor"]),
        actor_label=str(row["actor"]),
        actor_type="super_admin",
        assistance_session_id=str(row["id"]),
    )


def _end_assistance(self: AdminRepository, token: str | None) -> None:
    if not token:
        return
    digest = _token_id(token)
    with _connect(self.registry.registry_path) as db:
        row = db.execute(
            "SELECT tenant_id,actor FROM assistance_sessions WHERE id IN (?,?) LIMIT 1",
            (digest, token),
        ).fetchone()
        db.execute(
            "UPDATE assistance_sessions SET ended_at=? WHERE id IN (?,?) AND ended_at IS NULL",
            (utc_now(), digest, token),
        )
    if row:
        self.audit(str(row["tenant_id"]), str(row["actor"]), "assistance.ended", digest, {}, {})


def _resolve_web_context(self: AdminRepository, assistance_token: str | None, user_session: str | None) -> WebContext:
    assistance = self.resolve_assistance(assistance_token)
    if assistance:
        return assistance
    user = self.resolve_user_session(user_session)
    if user:
        return user
    if _local_mode_enabled():
        return WebContext("local", "local-user", "Utilisateur local", "user")
    raise PermissionError("Connexion requise")


def _origin_matches_host(request: Request) -> bool:
    origin = request.headers.get("origin", "").strip()
    if not origin:
        return True
    if origin == "null":
        return False
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() == request.headers.get("host", "").strip().lower()


def _csrf_policy_allows(request: Request) -> bool:
    fetch_site = request.headers.get("sec-fetch-site", "").strip().lower()
    if fetch_site and fetch_site not in {"same-origin", "same-site", "none"}:
        return False
    return _origin_matches_host(request)


def _harden_cookies(response: Response) -> None:
    secure_required = _enabled("PLO_COOKIE_SECURE", "1")
    output: list[tuple[bytes, bytes]] = []
    for name, value in response.raw_headers:
        if name.lower() != b"set-cookie":
            output.append((name, value))
            continue
        lower = value.lower()
        if not any(lower.startswith(cookie.encode("ascii") + b"=") for cookie in _SESSION_COOKIES):
            output.append((name, value))
            continue
        parts = [part.strip() for part in value.split(b";")]
        filtered = [part for part in parts if not part.lower().startswith(b"samesite=") and part.lower() != b"secure"]
        filtered.append(b"SameSite=Strict")
        if secure_required:
            filtered.append(b"Secure")
        output.append((name, b"; ".join(filtered)))
    response.raw_headers = output


class SaaSSecurityBoundaryMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        public = path.startswith("/static/") or path in _PUBLIC_PATHS
        session = request.cookies.get("axioload_session")
        assistance = request.cookies.get("axioload_assistance")
        has_browser_session = bool(session or assistance)
        has_api_key = bool(request.headers.get("x-api-key"))

        if request.method.upper() in _UNSAFE_METHODS and has_browser_session and not _csrf_policy_allows(request):
            return JSONResponse({"detail": "Requête intersite refusée"}, status_code=403, headers={"Cache-Control": "no-store"})

        if not public and not has_api_key and not _local_mode_enabled():
            admin = request.app.state.admin
            context = admin.resolve_assistance(assistance) or admin.resolve_user_session(session)
            if context is None:
                accepts_html = "text/html" in request.headers.get("accept", "")
                if request.method == "GET" and (path == "/" or accepts_html):
                    return RedirectResponse("/login", status_code=303)
                return JSONResponse({"detail": "Connexion requise"}, status_code=401, headers={"Cache-Control": "no-store"})

        response = await call_next(request)
        _harden_cookies(response)
        if has_browser_session:
            response.headers.setdefault("Cache-Control", "no-store")
        return response


def _install_argon2() -> None:
    persistence._hash_secret = _hash_secret_argon2
    persistence._verify_secret = _verify_secret_compatible
    for module in (admin_integrations, admin_invitations, admin_service, fixed_test_accounts, password_reset_system):
        if hasattr(module, "_hash_secret"):
            module._hash_secret = _hash_secret_argon2
        if hasattr(module, "_verify_secret"):
            module._verify_secret = _verify_secret_compatible

    original_authenticate = AdminRepository.authenticate
    original_super_admin = AdminRepository.authenticate_super_admin

    def authenticate(self: AdminRepository, tenant_id: str, email: str, password: str):
        result = original_authenticate(self, tenant_id, email, password)
        user = result.get("user") if isinstance(result, dict) else None
        if isinstance(user, dict) and user.get("id"):
            _rehash_company_user(self, str(user["id"]), password)
        return result

    def authenticate_super_admin(self: AdminRepository, identifier: str, password: str):
        result = original_super_admin(self, identifier, password)
        _rehash_company_user(self, SUPER_ADMIN_USER_ID, password)
        return result

    AdminRepository.authenticate = authenticate  # type: ignore[method-assign]
    AdminRepository.authenticate_super_admin = authenticate_super_admin  # type: ignore[method-assign]


def _install_sessions() -> None:
    AdminRepository.create_user_session = _create_user_session  # type: ignore[method-assign]
    AdminRepository.resolve_user_session = _resolve_user_session  # type: ignore[method-assign]
    AdminRepository.end_user_session = _end_user_session  # type: ignore[method-assign]
    AdminRepository.start_assistance = _start_assistance  # type: ignore[method-assign]
    AdminRepository.resolve_assistance = _resolve_assistance  # type: ignore[method-assign]
    AdminRepository.end_assistance = _end_assistance  # type: ignore[method-assign]
    AdminRepository.resolve_web_context = _resolve_web_context  # type: ignore[method-assign]


def install_security_upgrade() -> None:
    if getattr(FastAPI.__init__, "_axioload_saas_security_upgrade", False):
        return
    _install_argon2()
    _install_sessions()
    previous_init = FastAPI.__init__

    def init(self: FastAPI, *args, **kwargs) -> None:
        previous_init(self, *args, **kwargs)
        self.add_middleware(SaaSSecurityBoundaryMiddleware)

    init._axioload_saas_security_upgrade = True  # type: ignore[attr-defined]
    FastAPI.__init__ = init  # type: ignore[method-assign]
