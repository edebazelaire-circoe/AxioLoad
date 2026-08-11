from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.templating import Jinja2Templates

_STYLE = b'<link rel="stylesheet" href="/static/circoe_workspace_v3.css?v=0.20.0">'
_SCRIPT = b'<script src="/static/circoe_workspace_v3.js?v=0.20.0"></script>'
_original_template_response: Callable[..., Any] | None = None


def install_circoe_workspace_v3() -> None:
    """Install the eight-workspace CIRCOE shell without replacing business panels."""
    global _original_template_response
    if getattr(Jinja2Templates.TemplateResponse, "_axioload_circoe_workspace_v3", False):
        return

    _original_template_response = Jinja2Templates.TemplateResponse

    def template_response(self: Jinja2Templates, *args: Any, **kwargs: Any) -> Any:
        assert _original_template_response is not None
        response = _original_template_response(self, *args, **kwargs)
        body = getattr(response, "body", b"")
        if b'id="open-settings"' in body:
            body = body.replace(_STYLE, b"").replace(_SCRIPT, b"")
            body = body.replace(b"</head>", _STYLE + b"</head>")
            body = body.replace(b"</body>", _SCRIPT + b"</body>")
            response.body = body
            response.headers["content-length"] = str(len(body))
        return response

    template_response._axioload_circoe_workspace_v3 = True  # type: ignore[attr-defined]
    Jinja2Templates.TemplateResponse = template_response  # type: ignore[method-assign]
