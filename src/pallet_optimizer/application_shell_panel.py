from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.templating import Jinja2Templates

_STYLE = b'<link rel="stylesheet" href="/static/application_shell.css?v=0.19.5">'
_SCRIPT = b'<script src="/static/application_shell.js?v=0.19.5"></script>'
_PERMISSION_BOOTSTRAP = b'''<script id="axioload-permission-bootstrap">
(() => {
  'use strict';
  if (window.AxioLoadContextPromise) return;
  const nativeFetch = window.fetch.bind(window);
  const contextPromise = nativeFetch('/api/company/context', {credentials: 'same-origin'})
    .then(response => response.ok ? response.json() : null)
    .catch(() => null);
  window.AxioLoadContextPromise = contextPromise;
  window.AxioLoadNativeFetch = nativeFetch;
  window.fetch = async (input, init = {}) => {
    const inputMethod = typeof input === 'object' && input ? input.method : null;
    const method = String(init.method || inputMethod || 'GET').toUpperCase();
    const rawUrl = typeof input === 'string' || input instanceof URL ? input : input?.url;
    const url = new URL(String(rawUrl || ''), window.location.href);
    if (method === 'GET' && url.origin === window.location.origin && url.pathname === '/api/history') {
      const context = await contextPromise;
      if (context?.permissions?.['history.view'] === false) {
        return new Response('[]', {
          status: 200,
          headers: {'Content-Type': 'application/json', 'X-AxioLoad-Suppressed': 'history.view'}
        });
      }
    }
    return nativeFetch(input, init);
  };
})();
</script>'''
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

        for asset in (_STYLE, _SCRIPT, _PERMISSION_BOOTSTRAP):
            body = body.replace(asset, b"")
        if b'id="site-logout"' not in body:
            body = body.replace(b"</header>", _LOGOUT_BUTTON + b"</header>", 1)
        body = body.replace(b"</head>", _STYLE + _PERMISSION_BOOTSTRAP + b"</head>")
        body = body.replace(b"</body>", _SCRIPT + b"</body>")
        response.body = body
        response.headers["content-length"] = str(len(body))
        return response

    template_response._axioload_application_shell = True  # type: ignore[attr-defined]
    Jinja2Templates.TemplateResponse = template_response  # type: ignore[method-assign]
