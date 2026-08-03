from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "pallet_optimizer" / "static"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_three_main_workspaces_are_declared() -> None:
    script = _read(STATIC / "document_control_experience_v2.js")
    assert 'data-workspace="database"' in script
    assert 'data-workspace="optimization"' in script
    assert 'data-workspace="documents"' in script
    assert "Base de données" in script
    assert "Optimisation" in script
    assert "Contrôle documentaire" in script
    assert "Nouveau contrôle" in script
    assert "Prompts" in script
    assert "workspace-group-hidden" in script


def test_circoe_palette_is_applied() -> None:
    stylesheet = _read(STATIC / "document_control_experience.css").lower()
    for color in ("#005696", "#f8af44", "#e73147", "#40b1a1", "#ece9e9"):
        assert color in stylesheet
    assert "workspace-database" in stylesheet
    assert "workspace-optimization" in stylesheet
    assert "workspace-documents" in stylesheet


def test_frontend_has_no_manual_superadmin_credential_flow() -> None:
    inspected = [
        STATIC / "admin.js",
        STATIC / "auth_experience.js",
        STATIC / "document_control_experience_v2.js",
        STATIC / "password_reset.js",
        ROOT / "src" / "pallet_optimizer" / "admin_service.py",
        ROOT / ".env.example",
    ]
    forbidden = (
        "PLO_SUPER_ADMIN_TOKEN",
        "axioload.admin.token",
        "Saisissez le jeton super administrateur",
    )
    combined = "\n".join(_read(path) for path in inspected)
    for marker in forbidden:
        assert marker not in combined


def test_global_locked_badge_is_not_generated() -> None:
    admin_script = _read(STATIC / "admin.js")
    assert "Global verrouillé" not in admin_script
    assert "Personnalisé" in admin_script


def test_runtime_scripts_do_not_watch_the_entire_document() -> None:
    scripts = (
        STATIC / "auth_experience.js",
        STATIC / "document_control_experience_v2.js",
        STATIC / "document_control_permission_ui.js",
        STATIC / "optimization_experience.js",
        STATIC / "password_reset.js",
        STATIC / "prompt_center_experience.js",
    )
    for script in scripts:
        content = _read(script)
        assert "observe(document.body" not in content, script.name
        assert "new MutationObserver(installAll)" not in content, script.name
    assert "observer.observe(body, {childList: true})" in _read(STATIC / "optimization_experience.js")
    assert ".observe(target, {childList: true, subtree: true})" in _read(STATIC / "password_reset.js")


def test_workspace_fallback_clicks_only_one_allowed_destination() -> None:
    script = _read(STATIC / "document_control_permission_ui.js")
    assert "optimizationWorkspace?.click() || databaseWorkspace?.click()" not in script
    assert "const fallback = [optimizationWorkspace, databaseWorkspace]" in script
    assert "!button.hidden && !button.disabled" in script


def test_changed_javascript_files_are_syntactically_valid() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js n’est pas disponible dans cet environnement")
    scripts = (
        STATIC / "admin.js",
        STATIC / "auth_experience.js",
        STATIC / "document_control_experience_v2.js",
        STATIC / "document_control_permission_ui.js",
        STATIC / "optimization_experience.js",
        STATIC / "password_reset.js",
        STATIC / "prompt_center_experience.js",
    )
    for script in scripts:
        result = subprocess.run(
            [node, "--check", str(script)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"{script.name}: {result.stderr}"


def test_versioned_assets_are_loaded(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))
    response = client.get("/")
    assert response.status_code == 200
    expected = (
        "/static/admin.js?v=0.18.0",
        "/static/auth_experience.css?v=0.19.4",
        "/static/auth_experience.js?v=0.19.4",
        "/static/document_control_experience.css?v=0.19.1",
        "/static/document_control_experience_v2.js?v=0.19.1",
        "/static/document_control_permission_ui.js?v=0.19.1",
        "/static/optimization_experience.css?v=0.19.1",
        "/static/optimization_experience.js?v=0.19.1",
        "/static/password_reset.css?v=0.19.1",
        "/static/password_reset.js?v=0.19.1",
    )
    for asset in expected:
        assert response.text.count(asset) == 1
    assert "document_control_experience.js?v=0.18.0" not in response.text
