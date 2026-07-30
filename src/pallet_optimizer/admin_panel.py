from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.templating import Jinja2Templates


_ADMIN_SCRIPT = b'<script src="/static/admin.js"></script>'
_original_template_response: Callable[..., Any] = Jinja2Templates.TemplateResponse


def install_admin_panel_injection() -> None:
    """Load the preparatory admin UI without duplicating the large main template."""
    if getattr(Jinja2Templates.TemplateResponse, "_axioload_admin_injection", False):
        return

    def template_response(self: Jinja2Templates, *args: Any, **kwargs: Any) -> Any:
        response = _original_template_response(self, *args, **kwargs)
        body = getattr(response, "body", b"")
        if b'id="open-settings"' in body and _ADMIN_SCRIPT not in body:
            response.body = body.replace(b"</body>", _ADMIN_SCRIPT + b"</body>")
            response.headers["content-length"] = str(len(response.body))
        return response

    template_response._axioload_admin_injection = True  # type: ignore[attr-defined]
    Jinja2Templates.TemplateResponse = template_response  # type: ignore[method-assign]
