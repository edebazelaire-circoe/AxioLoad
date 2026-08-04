from __future__ import annotations

from pathlib import Path


def test_internal_workspace_clicks_are_not_blocked() -> None:
    root = Path(__file__).parents[1] / "src/pallet_optimizer/static"
    guard = (root / "navigation_guard.js").read_text(encoding="utf-8")
    switcher = (root / "document_control_experience_v2.js").read_text(encoding="utf-8")

    assert "if (!event.isTrusted) return" in guard
    assert "target.click()" in switcher
    assert "documentTab.click()" in switcher
