from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.templating import Jinja2Templates

_STYLE = b'<link rel="stylesheet" href="/static/facturx.css?v=0.20.3">'
_SCRIPT = b'<script src="/static/facturx.js?v=0.20.3"></script>'
_FINAL_STYLE = b'<link rel="stylesheet" href="/static/facturx_final.css?v=0.20.4">'
_VIEW_SCRIPT = b'<script src="/static/facturx_view_modes.js?v=0.20.4"></script>'
_original_template_response: Callable[..., Any] | None = None


def install_facturx_panel_injection() -> None:
    global _original_template_response
    if getattr(Jinja2Templates.TemplateResponse, "_logipilot_facturx_injection", False):
        return
    _original_template_response = Jinja2Templates.TemplateResponse

    def template_response(self: Jinja2Templates, *args: Any, **kwargs: Any) -> Any:
        assert _original_template_response is not None
        response = _original_template_response(self, *args, **kwargs)
        body = getattr(response, "body", b"")
        if b'id="open-settings"' in body:
            for version in (b"0.20.0", b"0.20.1", b"0.20.2", b"0.20.3"):
                body = body.replace(b'<link rel="stylesheet" href="/static/facturx.css?v=' + version + b'">', b"")
                body = body.replace(b'<script src="/static/facturx.js?v=' + version + b'"></script>', b"")
            for asset in (_FINAL_STYLE, _VIEW_SCRIPT):
                body = body.replace(asset, b"")
            body = body.replace(b"</head>", _STYLE + _FINAL_STYLE + b"</head>")
            body = body.replace(b"</body>", _SCRIPT + _VIEW_SCRIPT + b"</body>")
            response.body = body
            response.headers["content-length"] = str(len(body))
        return response

    template_response._logipilot_facturx_injection = True  # type: ignore[attr-defined]
    Jinja2Templates.TemplateResponse = template_response  # type: ignore[method-assign]
