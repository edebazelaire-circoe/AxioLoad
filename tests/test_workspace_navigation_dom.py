from __future__ import annotations

from pathlib import Path


def test_workspace_switcher_opens_real_panels_through_internal_clicks() -> None:
    root = Path(__file__).parents[1] / "src/pallet_optimizer/static"
    guard = (root / "navigation_guard.js").read_text(encoding="utf-8")
    switcher = (root / "document_control_experience_v2.js").read_text(encoding="utf-8")

    assert "if (!event.isTrusted) return" in guard
    assert "target.click()" in switcher
    assert "documentTab.click()" in switcher
    assert "setWorkspaceVisual('optimization')" in switcher
    assert "setWorkspaceVisual('documents')" in switcher
