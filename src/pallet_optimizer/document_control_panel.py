from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.templating import Jinja2Templates

_STYLE = b'<link rel="stylesheet" href="/static/document_control.css?v=0.13.0">'
_SCRIPT = b'<script src="/static/document_control.js?v=0.13.0"></script>'
_CAMERA_STYLE = b'<link rel="stylesheet" href="/static/document_camera.css?v=0.19.6">'
_CAMERA_SCRIPT = b'<script src="/static/document_camera.js?v=0.19.6"></script>'
_OLD_CAMERA_STYLE = b'<link rel="stylesheet" href="/static/document_camera.css?v=0.19.3">'
_OLD_CAMERA_SCRIPT = b'<script src="/static/document_camera.js?v=0.19.3"></script>'
_original_template_response: Callable[..., Any] | None = None


def install_document_control_panel_injection() -> None:
    global _original_template_response
    if getattr(Jinja2Templates.TemplateResponse, "_axioload_document_control_injection", False):
        return
    _original_template_response = Jinja2Templates.TemplateResponse

    def template_response(self: Jinja2Templates, *args: Any, **kwargs: Any) -> Any:
        assert _original_template_response is not None
        response = _original_template_response(self, *args, **kwargs)
        body = getattr(response, "body", b"")
        if b'id="open-settings"' in body:
            for asset in (
                _STYLE,
                _SCRIPT,
                _OLD_CAMERA_STYLE,
                _OLD_CAMERA_SCRIPT,
                _CAMERA_STYLE,
                _CAMERA_SCRIPT,
            ):
                body = body.replace(asset, b"")
            body = body.replace(b"</head>", _STYLE + _CAMERA_STYLE + b"</head>")
            body = body.replace(b"</body>", _SCRIPT + _CAMERA_SCRIPT + b"</body>")
            response.body = body
            response.headers["content-length"] = str(len(body))
        return response

    template_response._axioload_document_control_injection = True  # type: ignore[attr-defined]
    Jinja2Templates.TemplateResponse = template_response  # type: ignore[method-assign]
