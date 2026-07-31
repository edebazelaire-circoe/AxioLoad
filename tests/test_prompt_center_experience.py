from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pallet_optimizer import document_control as dc
from pallet_optimizer.api import create_app


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "pallet_optimizer" / "static"


def _login_super_admin(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLO_SUPER_ADMIN_EMAIL", "b.olivier@circoe.com")
    monkeypatch.setenv("PLO_SUPER_ADMIN_USERNAME", "superadmn")
    monkeypatch.setenv("PLO_SUPER_ADMIN_PASSWORD", "1234")
    response = client.post(
        "/api/auth/super-admin-login",
        json={"identifier": "superadmn", "password": "1234"},
    )
    assert response.status_code == 200


def test_prompt_center_assets_are_injected(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    response = client.get("/")
    assert response.status_code == 200
    assert "/static/prompt_center_experience.css?v=0.19.0" in response.text
    assert "/static/prompt_center_experience.js?v=0.19.0" in response.text


def test_company_prompt_center_only_exposes_company_complements(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    response = client.get("/api/prompt-center")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "company"
    assert payload["is_primary_admin"] is True
    assert len(payload["profiles"]) == 6
    assert "core" not in payload
    assert all("system_instructions" in profile for profile in payload["profiles"])
    assert all("company_instructions" in profile for profile in payload["profiles"])

    saved = client.put(
        "/api/prompt-center/company/transport_order/cmr",
        json={"instructions": "Contrôler la référence interne CIRCOÉ."},
    )
    assert saved.status_code == 200
    refreshed = client.get("/api/prompt-center").json()
    profile = next(item for item in refreshed["profiles"] if item["key"] == "transport_order__cmr")
    assert "CIRCOÉ" in profile["company_instructions"]


def test_super_admin_can_edit_core_and_all_system_prompts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(create_app(tmp_path))
    _login_super_admin(client, monkeypatch)

    response = client.get("/api/prompt-center")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "super_admin"
    assert len(payload["profiles"]) == 7
    initial_version = payload["core"]["version"]

    updated = client.put(
        "/api/prompt-center/core",
        json={"instructions": "Socle commun modifiable du Centre de gestion."},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == initial_version + 1
    assert dc.LOCKED_SYSTEM_PROMPT == "Socle commun modifiable du Centre de gestion."

    profile = client.put(
        "/api/prompt-center/system/generic",
        json={"instructions": "Comparer tous les champs utiles sans inventer."},
    )
    assert profile.status_code == 200
    assert profile.json()["version"] == 2


def test_frontend_keeps_prompts_out_of_management_center() -> None:
    script = (STATIC / "prompt_center_experience.js").read_text(encoding="utf-8")
    assert "Centre de gestion" in script
    assert "Nuage des optimisations" in script
    assert "Métrage linéaire" in script
    assert "openAdmin.click" not in script
    assert "data-workspace-tab=\"prompts\"" in script
    assert "removeLegacyPromptAdminView" in script
    assert "Coûts" in script


def test_prompt_center_javascript_syntax() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js indisponible")
    subprocess.run(
        [node, "--check", str(STATIC / "prompt_center_experience.js")],
        check=True,
        capture_output=True,
        text=True,
    )
