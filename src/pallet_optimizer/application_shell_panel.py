from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.templating import Jinja2Templates

_STYLE = b'<link rel="stylesheet" href="/static/application_shell.css?v=0.19.5">'
_SCRIPT = b'<script src="/static/application_shell.js?v=0.19.5"></script>'
_LOGOUT_BUTTON = b'''<button id="site-logout" class="settings-access auth-logout" type="button" data-shell-control="logout" aria-label="Se d\xc3\xa9connecter">
  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 5H5v14h5M14 8l4 4-4 4M8 12h10"/></svg>
  <span>Se d\xc3\xa9connecter</span>
</button>'''
_original_template_response: Callable[..., Any] | None = None


def install_application_shell_injection() -> None:
    """Inject the permanent session control and the single navigation shell last."""
    global _original_template_response
    if getattr(Jinja2Templates.TemplateResponse, "_axioload_application_shell", False):
        return
    _original_template_response = Jinja2Templates.TemplateResponse

    def template_response(self: Jinja2Templates, *args: Any, **kwargs: Any) -> Any:
        assert _original_template_response is not None
        response = _original_template_response(self, *args, **kwargs)
        body = getattr(response, "body", b"")
        if b'id="open-settings"' not in body:
            return response

        body = body.replace(_STYLE, b"").replace(_SCRIPT, b"")
        if b'id="site-logout"' not in body:
            body = body.replace(b"</header>", _LOGOUT_BUTTON + b"</header>", 1)
        body = body.replace(b"</head>", _STYLE + b"</head>")
        body = body.replace(b"</body>", _SCRIPT + b"</body>")
        response.body = body
        response.headers["content-length"] = str(len(body))
        return response

    template_response._axioload_application_shell = True  # type: ignore[attr-defined]
    Jinja2Templates.TemplateResponse = template_response  # type: ignore[method-assign]
