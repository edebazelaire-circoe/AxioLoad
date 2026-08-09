from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_SESSION_COOKIES = ("axioload_session", "axioload_assistance")


def _request_is_https(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip().lower() == "https"
    return request.url.scheme.lower() == "https"


def _has_browser_session(request: Request) -> bool:
    return any(request.cookies.get(name) for name in _SESSION_COOKIES)


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
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    request_host = request.headers.get("host", "").strip().lower()
    return bool(request_host) and parsed.netloc.lower() == request_host


def _secure_session_cookies(response: Response) -> None:
    secured: list[tuple[bytes, bytes]] = []
    for name, value in response.raw_headers:
        if name.lower() == b"set-cookie":
            lower_value = value.lower()
            is_session = any(lower_value.startswith(cookie.encode("ascii") + b"=") for cookie in _SESSION_COOKIES)
            if is_session and b"; secure" not in lower_value:
                value = value + b"; Secure"
        secured.append((name, value))
    response.raw_headers = secured


class SecurityHardeningMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if (
            request.method.upper() in _UNSAFE_METHODS
            and _has_browser_session(request)
            and not _origin_matches_host(request)
        ):
            return JSONResponse(
                {"detail": "Origine de requête refusée"},
                status_code=403,
                headers={"Cache-Control": "no-store"},
            )

        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )

        if _request_is_https(request):
            _secure_session_cookies(response)
        return response


def install_security_hardening() -> None:
    if getattr(FastAPI.__init__, "_logipilot_security_hardening", False):
        return

    previous_init = FastAPI.__init__

    def init(self: FastAPI, *args, **kwargs) -> None:
        previous_init(self, *args, **kwargs)
        self.add_middleware(SecurityHardeningMiddleware)

    init._logipilot_security_hardening = True  # type: ignore[attr-defined]
    FastAPI.__init__ = init  # type: ignore[method-assign]
