from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.templating import Jinja2Templates

_STYLE = b'<link rel="stylesheet" href="/static/auth_experience.css?v=0.19.2">'
_SCRIPT = b'<script src="/static/auth_experience.js?v=0.19.2"></script>'
_OLD_STYLE = b'<link rel="stylesheet" href="/static/auth_experience.css?v=0.19.1">'
_OLD_SCRIPT = b'<script src="/static/auth_experience.js?v=0.19.1"></script>'
_original_template_response: Callable[..., Any] | None = None


def install_auth_experience_injection() -> None:
    global _original_template_response
    if getattr(Jinja2Templates.TemplateResponse, "_axioload_auth_experience", False):
        return
    _original_template_response = Jinja2Templates.TemplateResponse

    def template_response(self: Jinja2Templates, *args: Any, **kwargs: Any) -> Any:
        assert _original_template_response is not None
        response = _original_template_response(self, *args, **kwargs)
        body = getattr(response, "body", b"")
        if b'id="open-settings"' in body or b'id="login-form"' in body:
            for asset in (_OLD_STYLE, _OLD_SCRIPT, _STYLE, _SCRIPT):
                body = body.replace(asset, b"")
            body = body.replace(b"</head>", _STYLE + b"</head>")
            body = body.replace(b"</body>", _SCRIPT + b"</body>")
            response.body = body
            response.headers["content-length"] = str(len(body))
        return response

    template_response._axioload_auth_experience = True  # type: ignore[attr-defined]
    Jinja2Templates.TemplateResponse = template_response  # type: ignore[method-assign]
