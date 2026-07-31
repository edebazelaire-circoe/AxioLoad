from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.templating import Jinja2Templates

_ADMIN_STYLE = b'<link rel="stylesheet" href="/static/admin.css?v=0.12.0">'
_HISTORY_STABILITY_SCRIPT = b'<script src="/static/history_stability.js?v=0.12.0"></script>'
_ADMIN_SCRIPT = b'<script src="/static/admin.js?v=0.12.0"></script>'
_original_template_response: Callable[..., Any] = Jinja2Templates.TemplateResponse


def install_admin_panel_injection() -> None:
    """Load the administration workspace without duplicating the large main template."""
    if getattr(Jinja2Templates.TemplateResponse, "_axioload_admin_injection", False):
        return

    def template_response(self: Jinja2Templates, *args: Any, **kwargs: Any) -> Any:
        response = _original_template_response(self, *args, **kwargs)
        body = getattr(response, "body", b"")
        if b'id="open-settings"' in body:
            if _ADMIN_STYLE not in body:
                body = body.replace(b"</head>", _ADMIN_STYLE + b"</head>")
            scripts = _HISTORY_STABILITY_SCRIPT + _ADMIN_SCRIPT
            if _HISTORY_STABILITY_SCRIPT not in body and _ADMIN_SCRIPT not in body:
                body = body.replace(b"</body>", scripts + b"</body>")
            elif _HISTORY_STABILITY_SCRIPT not in body:
                body = body.replace(_ADMIN_SCRIPT, _HISTORY_STABILITY_SCRIPT + _ADMIN_SCRIPT)
            elif _ADMIN_SCRIPT not in body:
                body = body.replace(b"</body>", _ADMIN_SCRIPT + b"</body>")
            response.body = body
            response.headers["content-length"] = str(len(body))
        return response

    template_response._axioload_admin_injection = True  # type: ignore[attr-defined]
    Jinja2Templates.TemplateResponse = template_response  # type: ignore[method-assign]
