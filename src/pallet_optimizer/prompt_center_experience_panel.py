from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.templating import Jinja2Templates

from .version import APP_VERSION

_STYLE = f'<link rel="stylesheet" href="/static/prompt_center_experience.css?v={APP_VERSION}">'.encode()
_SCRIPT = f'<script src="/static/prompt_center_experience.js?v={APP_VERSION}"></script>'.encode()
_LEGACY_ASSETS = (
    b'<link rel="stylesheet" href="/static/prompt_center_experience.css?v=0.19.0">',
    b'<script src="/static/prompt_center_guard.js?v=0.19.0"></script>',
    b'<script src="/static/prompt_center_experience.js?v=0.19.0"></script>',
    b'<link rel="stylesheet" href="/static/prompt_center_experience.css?v=0.19.1">',
    b'<script src="/static/prompt_center_experience.js?v=0.19.1"></script>',
)
_original_template_response: Callable[..., Any] | None = None


def install_prompt_center_experience_injection() -> None:
    global _original_template_response
    if getattr(Jinja2Templates.TemplateResponse, "_axioload_prompt_center_experience", False):
        return
    _original_template_response = Jinja2Templates.TemplateResponse

    def template_response(self: Jinja2Templates, *args: Any, **kwargs: Any) -> Any:
        assert _original_template_response is not None
        response = _original_template_response(self, *args, **kwargs)
        body = getattr(response, "body", b"")
        if b'id="open-settings"' in body:
            for asset in (*_LEGACY_ASSETS, _STYLE, _SCRIPT):
                body = body.replace(asset, b"")
            body = body.replace(b"</head>", _STYLE + b"</head>")
            body = body.replace(b"</body>", _SCRIPT + b"</body>")
            response.body = body
            response.headers["content-length"] = str(len(body))
        return response

    template_response._axioload_prompt_center_experience = True  # type: ignore[attr-defined]
    Jinja2Templates.TemplateResponse = template_response  # type: ignore[method-assign]
