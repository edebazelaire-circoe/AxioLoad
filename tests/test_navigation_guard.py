from __future__ import annotations

from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app


def test_navigation_guard_assets_are_loaded(tmp_path) -> None:
    response = TestClient(create_app(tmp_path)).get("/")
    assert response.status_code == 200
    assert response.text.count("/static/navigation_guard.css?v=0.19.1") == 1
    assert response.text.count("/static/navigation_guard.js?v=0.19.1") == 1


def test_navigation_guard_replays_latest_click_and_has_safety_release() -> None:
    source = (
        __import__("pathlib").Path(__file__).parents[1]
        / "src/pallet_optimizer/static/navigation_guard.js"
    ).read_text(encoding="utf-8")
    assert "LOCK_MS = 250" in source
    assert "SAFETY_MS = 1800" in source
    assert "queuedControl = control" in source
    assert "replayQueuedNavigation" in source
    assert "control.click()" in source
    assert "event.stopImmediatePropagation()" in source
    assert "navigation-loading-indicator" in source
    assert "MutationObserver" not in source
