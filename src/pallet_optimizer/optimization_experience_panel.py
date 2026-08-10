from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.templating import Jinja2Templates

_STYLE = b'<link rel="stylesheet" href="/static/optimization_experience.css?v=0.19.1">'
_SCRIPT = b'<script src="/static/optimization_experience.js?v=0.19.1"></script>'
_RESILIENCE_STYLE = b'<link rel="stylesheet" href="/static/optimization_resilience.css?v=0.19.2">'
_RESILIENCE_SCRIPT = b'<script src="/static/optimization_resilience.js?v=0.19.2"></script>'
_VERTICAL_STYLE = b'<link rel="stylesheet" href="/static/vertical_results.css?v=0.19.4">'
_VERTICAL_SCRIPT = b'<script src="/static/vertical_results.js?v=0.19.4"></script>'
_COMPACT_STYLE = b'<link rel="stylesheet" href="/static/results_compact.css?v=0.19.5">'
_COMPACT_SCRIPT = b'<script src="/static/results_compact.js?v=0.19.5"></script>'
_VIEWER_STYLE = b'<link rel="stylesheet" href="/static/viewer_vehicle_enhancements.css?v=0.19.9">'
_VIEWER_SCRIPT = b'<script src="/static/viewer_vehicle_enhancements.js?v=0.19.9"></script>'
_BRAND_STYLE = b'<link rel="stylesheet" href="/static/logipilot_branding.css?v=0.19.8">'
_BRAND_SCRIPT = b'<script src="/static/logipilot_branding.js?v=0.19.8"></script>'
_OLD_STYLE = b'<link rel="stylesheet" href="/static/optimization_experience.css?v=0.18.0">'
_OLD_SCRIPT = b'<script src="/static/optimization_experience.js?v=0.18.0"></script>'
_original_template_response: Callable[..., Any] | None = None


def install_optimization_experience_injection() -> None:
    global _original_template_response
    if getattr(Jinja2Templates.TemplateResponse, "_axioload_optimization_experience", False):
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
                _STYLE,
                _SCRIPT,
                _RESILIENCE_STYLE,
                _RESILIENCE_SCRIPT,
                _VERTICAL_STYLE,
                _VERTICAL_SCRIPT,
                _COMPACT_STYLE,
                _COMPACT_SCRIPT,
                _VIEWER_STYLE,
                _VIEWER_SCRIPT,
                _BRAND_STYLE,
                _BRAND_SCRIPT,
            ):
                body = body.replace(asset, b"")
            body = body.replace(
                b"</head>",
                _STYLE + _RESILIENCE_STYLE + _VERTICAL_STYLE + _COMPACT_STYLE + _VIEWER_STYLE + _BRAND_STYLE + b"</head>",
            )
            body = body.replace(
                b"</body>",
                _SCRIPT + _RESILIENCE_SCRIPT + _VERTICAL_SCRIPT + _COMPACT_SCRIPT + _VIEWER_SCRIPT + _BRAND_SCRIPT + b"</body>",
            )
            response.body = body
            response.headers["content-length"] = str(len(body))
        return response

    template_response._axioload_optimization_experience = True  # type: ignore[attr-defined]
    Jinja2Templates.TemplateResponse = template_response  # type: ignore[method-assign]
