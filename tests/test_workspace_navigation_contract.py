from __future__ import annotations

from pathlib import Path


def test_workspace_navigation_keeps_internal_tab_clicks_available() -> None:
    root = Path(__file__).parents[1] / "src/pallet_optimizer/static"
    guard = (root / "navigation_guard.js").read_text(encoding="utf-8")
    workspace = (root / "document_control_experience_v2.js").read_text(encoding="utf-8")

    assert "if (!event.isTrusted) return" in guard
    assert "target.click()" in workspace
    assert "documentTab.click()" in workspace
    assert "setWorkspaceVisual('optimization')" in workspace
    assert "setWorkspaceVisual('documents')" in workspace
