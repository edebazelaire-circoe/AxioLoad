from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.templating import Jinja2Templates

from .fixed_test_accounts import fixed_test_accounts_enabled

_ADMIN_STYLE = b'<link rel="stylesheet" href="/static/admin.css?v=0.18.0">'
_WORKFLOW_STYLE = b'<link rel="stylesheet" href="/static/workflow_layout.css?v=0.18.0">'
_RESULTS_STYLE = b'<link rel="stylesheet" href="/static/results_enhancements.css?v=0.18.0">'
_UNITS_IMPORT_SCRIPT = b'<script src="/static/units_import.js?v=0.18.0"></script>'
_WORKFLOW_SCRIPT = b'<script src="/static/workflow_layout.js?v=0.18.0"></script>'
_RESULTS_SCRIPT = b'<script src="/static/results_enhancements.js?v=0.18.0"></script>'
_ADMIN_SCRIPT = b'<script src="/static/admin.js?v=0.18.0"></script>'
_FIXED_TEST_SCRIPT = b'<script src="/static/fixed_test_accounts_ui.js?v=0.19.5"></script>'
_OLD_FIXED_TEST_SCRIPT = b'<script src="/static/fixed_test_accounts_ui.js?v=0.19.2"></script>'
_original_template_response: Callable[..., Any] = Jinja2Templates.TemplateResponse


def install_admin_panel_injection() -> None:
    """Load administration, workflow and result enhancements without duplicating the main template."""
    if getattr(Jinja2Templates.TemplateResponse, "_axioload_admin_injection", False):
        return

    def template_response(self: Jinja2Templates, *args: Any, **kwargs: Any) -> Any:
        response = _original_template_response(self, *args, **kwargs)
        body = getattr(response, "body", b"")
        if b'id="open-settings"' in body:
            for style in (_ADMIN_STYLE, _WORKFLOW_STYLE, _RESULTS_STYLE):
                if style not in body:
                    body = body.replace(b"</head>", style + b"</head>")
            scripts = _UNITS_IMPORT_SCRIPT + _WORKFLOW_SCRIPT + _RESULTS_SCRIPT + _ADMIN_SCRIPT
            body = body.replace(_OLD_FIXED_TEST_SCRIPT, b"")
            body = body.replace(_FIXED_TEST_SCRIPT, b"")
            if fixed_test_accounts_enabled():
                scripts += _FIXED_TEST_SCRIPT
            for script in (_UNITS_IMPORT_SCRIPT, _WORKFLOW_SCRIPT, _RESULTS_SCRIPT, _ADMIN_SCRIPT):
                body = body.replace(script, b"")
            body = body.replace(b"</body>", scripts + b"</body>")
            response.body = body
            response.headers["content-length"] = str(len(body))
        return response

    template_response._axioload_admin_injection = True  # type: ignore[attr-defined]
    Jinja2Templates.TemplateResponse = template_response  # type: ignore[method-assign]
