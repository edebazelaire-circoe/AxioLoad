from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.templating import Jinja2Templates

from .fixed_test_accounts import fixed_test_accounts_enabled

_STYLE = b'<link rel="stylesheet" href="/static/auth_experience.css?v=0.19.1">'
_SCRIPT = b'<script src="/static/auth_experience.js?v=0.19.1"></script>'
_NAV_STYLE = b'<link rel="stylesheet" href="/static/navigation_guard.css?v=0.19.1">'
_NAV_SCRIPT = b'<script src="/static/navigation_guard.js?v=0.19.1"></script>'
_INTEGRITY_STYLE = b'<link rel="stylesheet" href="/static/ui_integrity.css?v=0.19.3">'
_INTEGRITY_SCRIPT = b'<script src="/static/ui_integrity.js?v=0.19.3"></script>'
_FIXED_TEST_STYLE = b'<link rel="stylesheet" href="/static/fixed_test_accounts.css?v=0.19.5">'
_FIXED_TEST_SCRIPT = b'<script src="/static/fixed_test_accounts_ui.js?v=0.19.5"></script>'
_OLD_FIXED_TEST_STYLE = b'<link rel="stylesheet" href="/static/fixed_test_accounts.css?v=0.19.2">'
_OLD_FIXED_TEST_SCRIPT = b'<script src="/static/fixed_test_accounts_ui.js?v=0.19.2"></script>'
_OLD_STYLE = b'<link rel="stylesheet" href="/static/auth_experience.css?v=0.18.0">'
_OLD_SCRIPT = b'<script src="/static/auth_experience.js?v=0.18.0"></script>'
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
        is_login = b'id="login-form"' in body
        is_application = b'id="open-settings"' in body
        if is_application or is_login:
            for asset in (
                _OLD_STYLE,
                _OLD_SCRIPT,
                _STYLE,
                _SCRIPT,
                _NAV_STYLE,
                _NAV_SCRIPT,
                _INTEGRITY_STYLE,
                _INTEGRITY_SCRIPT,
                _OLD_FIXED_TEST_STYLE,
                _OLD_FIXED_TEST_SCRIPT,
                _FIXED_TEST_STYLE,
                _FIXED_TEST_SCRIPT,
            ):
                body = body.replace(asset, b"")
            styles = _STYLE + _NAV_STYLE + _INTEGRITY_STYLE
            scripts = _SCRIPT + _NAV_SCRIPT + _INTEGRITY_SCRIPT
            if fixed_test_accounts_enabled():
                scripts += _FIXED_TEST_SCRIPT
                if is_login:
                    styles += _FIXED_TEST_STYLE
            body = body.replace(b"</head>", styles + b"</head>")
            body = body.replace(b"</body>", scripts + b"</body>")
            response.body = body
            response.headers["content-length"] = str(len(body))
        return response

    template_response._axioload_auth_experience = True  # type: ignore[attr-defined]
    Jinja2Templates.TemplateResponse = template_response  # type: ignore[method-assign]
