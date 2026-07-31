from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.templating import Jinja2Templates

_STYLE = b'<link rel="stylesheet" href="/static/prompt_center_experience.css?v=0.19.0">'
_GUARD_SCRIPT = b'<script src="/static/prompt_center_guard.js?v=0.19.0"></script>'
_SCRIPT = b'<script src="/static/prompt_center_experience.js?v=0.19.0"></script>'
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
            if _STYLE not in body:
                body = body.replace(b"</head>", _STYLE + b"</head>")
            for script in (_GUARD_SCRIPT, _SCRIPT):
                body = body.replace(script, b"")
            body = body.replace(b"</body>", _GUARD_SCRIPT + _SCRIPT + b"</body>")
            response.body = body
            response.headers["content-length"] = str(len(body))
        return response

    template_response._axioload_prompt_center_experience = True  # type: ignore[attr-defined]
    Jinja2Templates.TemplateResponse = template_response  # type: ignore[method-assign]
