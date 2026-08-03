from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "pallet_optimizer" / "static"


def test_page_loads_the_new_role_control_assets(tmp_path: Path) -> None:
    response = TestClient(create_app(tmp_path)).get("/")
    assert response.status_code == 200
    assert '/static/auth_experience.css?v=0.19.3' in response.text
    assert '/static/auth_experience.js?v=0.19.3' in response.text
    assert '/static/auth_experience.js?v=0.19.1' not in response.text


def test_role_controls_are_explicit_and_separate() -> None:
    source = (STATIC / "auth_experience.js").read_text(encoding="utf-8")

    assert "setControlVisibility(q('#open-settings'), true)" in source
    assert "setControlVisibility(q('#open-admin'), managementAllowed)" in source
    assert "const managementAllowed = directAdmin || assistance" in source
    assert "if (directAdmin)" in source
    assert "bindDirectAdminWorkspaceNavigation()" in source


def test_super_admin_workspace_mapping_targets_the_correct_panels() -> None:
    source = (STATIC / "auth_experience.js").read_text(encoding="utf-8")

    assert "database: ['vehicles', 'prompts']" in source
    assert "optimization: ['data', 'results', 'history', 'route', 'total']" in source
    assert "documents: ['document-control']" in source
    assert "qa('.tab-panel').forEach(panel => panel.classList.toggle('active', panel === targetPanel))" in source
    assert "window.setTimeout(() => activateWorkspacePanel(workspace), 0)" in source


def test_super_admin_navigation_does_not_block_existing_click_handlers() -> None:
    source = (STATIC / "auth_experience.js").read_text(encoding="utf-8")
    start = source.index("function bindDirectAdminWorkspaceNavigation")
    end = source.index("async function installApplicationSession", start)
    navigation = source[start:end]

    assert "preventDefault" not in navigation
    assert "stopPropagation" not in navigation
    assert "stopImmediatePropagation" not in navigation
    assert "capture: true" not in navigation


def test_super_admin_settings_cannot_be_hidden_by_the_prompt_script() -> None:
    stylesheet = (STATIC / "auth_experience.css").read_text(encoding="utf-8")
    assert 'body[data-super-admin-workspace-navigation="true"] #open-settings{display:flex!important}' in stylesheet
    assert 'body[data-super-admin-workspace-navigation="true"] #open-settings.hidden{display:flex!important}' in stylesheet


def test_auth_experience_javascript_is_valid() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js n’est pas disponible dans cet environnement")
    subprocess.run(
        [node, "--check", str(STATIC / "auth_experience.js")],
        check=True,
        capture_output=True,
        text=True,
    )
