from __future__ import annotations

from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app


def test_navigation_integrity_assets_are_loaded(tmp_path) -> None:
    response = TestClient(create_app(tmp_path)).get("/")
    assert response.status_code == 200
    assert response.text.count("/static/navigation_guard.css?v=0.19.1") == 1
    assert response.text.count("/static/navigation_guard.js?v=0.19.1") == 1
    assert response.text.count("/static/ui_integrity.css?v=0.19.3") == 1
    assert response.text.count("/static/ui_integrity.js?v=0.19.3") == 1


def test_navigation_guard_never_delays_valid_clicks() -> None:
    source = (
        __import__("pathlib").Path(__file__).parents[1]
        / "src/pallet_optimizer/static/navigation_guard.js"
    ).read_text(encoding="utf-8")
    assert "setTimeout" not in source
    assert "LOCK_MS" not in source
    assert "queuedControl" not in source
    assert "event.stopImmediatePropagation()" in source
    assert "aria-disabled" in source


def test_ui_integrity_covers_cards_and_single_active_panel() -> None:
    root = __import__("pathlib").Path(__file__).parents[1]
    script = (root / "src/pallet_optimizer/static/ui_integrity.js").read_text(encoding="utf-8")
    stylesheet = (root / "src/pallet_optimizer/static/ui_integrity.css").read_text(encoding="utf-8")
    assert "activateChoiceFromCard" in script
    assert "label.theme-choice" in script
    assert "label.total-mode-toggle" in script
    assert "activePanels.length > 1" in script
    assert "aria-hidden" in script
    assert ".workspace-group-hidden" in stylesheet
    assert "pointer-events: none" in stylesheet
