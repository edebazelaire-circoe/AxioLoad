from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "pallet_optimizer" / "static"


def _read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_workspace_navigation_controller_is_loaded_last(tmp_path) -> None:
    response = TestClient(create_app(tmp_path)).get("/")
    assert response.status_code == 200
    prompt_asset = "/static/prompt_center_experience.js?v=0.19.1"
    navigation_asset = "/static/workspace_navigation_fix.js?v=0.19.4"
    assert response.text.count(navigation_asset) == 1
    assert response.text.index(prompt_asset) < response.text.index(navigation_asset)


def test_workspace_controller_owns_the_real_panel_change() -> None:
    source = _read("workspace_navigation_fix.js")
    assert "window.addEventListener('click', handleNavigation, true)" in source
    assert "event.stopImmediatePropagation()" in source
    assert "window.switchTab(name)" in source
    assert "directSwitchTab('vehicles')" in source
    assert "openDocumentWorkspace" in source
    assert "openPromptCenter" in source
    assert "restoreNavigation" in source
    assert "sessionStorage.setItem(STORAGE_KEY" in source


def test_navigation_does_not_use_browser_history_or_reload() -> None:
    source = _read("workspace_navigation_fix.js")
    forbidden = (
        "history.pushState",
        "history.replaceState",
        "popstate",
        "location.reload",
        "window.location.reload",
    )
    for marker in forbidden:
        assert marker not in source


def test_ui_integrity_is_passive_and_cannot_restore_an_old_panel() -> None:
    source = _read("ui_integrity.js")
    assert "MutationObserver" not in source
    assert "requestedPanel" not in source
    assert "reconcilePanels" not in source
    assert "classList.toggle('active'" not in source
    assert "axioload:navigation:changed" in source


def test_navigation_scripts_are_syntactically_valid() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js n’est pas disponible dans cet environnement")
    for name in ("workspace_navigation_fix.js", "ui_integrity.js"):
        result = subprocess.run(
            [node, "--check", str(STATIC / name)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"{name}: {result.stderr}"
