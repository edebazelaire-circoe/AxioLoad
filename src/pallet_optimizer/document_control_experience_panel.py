from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.templating import Jinja2Templates

_STYLE = b'<link rel="stylesheet" href="/static/document_control_experience.css?v=0.19.1">'
_SCRIPT = b'<script src="/static/document_control_experience_v2.js?v=0.19.1"></script>'
_PERMISSION_SCRIPT = b'<script src="/static/document_control_permission_ui.js?v=0.19.1"></script>'
_OLD_STYLE = b'<link rel="stylesheet" href="/static/document_control_experience.css?v=0.18.0">'
_OLD_SCRIPT = b'<script src="/static/document_control_experience.js?v=0.18.0"></script>'
_OLD_PERMISSION_SCRIPT = b'<script src="/static/document_control_permission_ui.js?v=0.18.0"></script>'
_original_template_response: Callable[..., Any] | None = None


def install_document_control_experience_injection() -> None:
    global _original_template_response
    if getattr(Jinja2Templates.TemplateResponse, "_axioload_document_experience", False):
        return
    _original_template_response = Jinja2Templates.TemplateResponse

    def template_response(self: Jinja2Templates, *args: Any, **kwargs: Any) -> Any:
        assert _original_template_response is not None
        response = _original_template_response(self, *args, **kwargs)
        body = getattr(response, "body", b"")
        if b'id="open-settings"' in body:
            for asset in (
                _OLD_STYLE,
                _OLD_SCRIPT,
                _OLD_PERMISSION_SCRIPT,
                _STYLE,
                _SCRIPT,
                _PERMISSION_SCRIPT,
            ):
                body = body.replace(asset, b"")
            body = body.replace(b"</head>", _STYLE + b"</head>")
            body = body.replace(b"</body>", _SCRIPT + _PERMISSION_SCRIPT + b"</body>")
            response.body = body
            response.headers["content-length"] = str(len(body))
        return response

    template_response._axioload_document_experience = True  # type: ignore[attr-defined]
    Jinja2Templates.TemplateResponse = template_response  # type: ignore[method-assign]
