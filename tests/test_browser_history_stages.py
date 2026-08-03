from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import Browser

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_browser_navigation_e2e import (  # noqa: E402
    _exercise_all_navigation_controls,
    _exercise_rapid_clicks,
    _logout_and_check,
    _open_authenticated_page,
)


def test_user_has_no_forbidden_history_call_at_each_browser_stage(
    browser: Browser,
    live_server: str,
) -> None:
    page, errors = _open_authenticated_page(browser, live_server, super_admin=False)
    try:
        assert errors == [], {"stage": "initial-load", "errors": errors}

        _exercise_all_navigation_controls(page, super_admin=False)
        assert errors == [], {"stage": "button-by-button", "errors": errors}

        _exercise_rapid_clicks(page)
        assert errors == [], {"stage": "rapid-clicks", "errors": errors}

        _logout_and_check(page, live_server)
        assert errors == [], {"stage": "logout", "errors": errors}
    finally:
        page.context.close()
