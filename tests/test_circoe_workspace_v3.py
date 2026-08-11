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


def test_eight_circoe_workspaces_are_declared_without_fake_regulatory_data() -> None:
    script = _read("circoe_workspace_v3.js")
    for label in (
        "1. Base de données",
        "2. Optimisation",
        "3. Contrôle documentaire",
        "4. Contrôle réglementaire",
        "5. Facturation électronique / Factur-X",
        "6. Historique & traçabilité",
        "7. Paramètres & IA",
        "8. Super Admin",
    ):
        assert label in script
    assert "Préparé · non actif" in script
    assert "Aucune règle réglementaire n’est activée dans cette version." in script
    assert "conformité supposée" in script


def test_circoe_palette_and_sidebar_are_explicit() -> None:
    css = _read("circoe_workspace_v3.css").lower()
    for color in ("#005696", "#f8af44", "#e73147", "#40b1a1", "#ece9e9"):
        assert color in css
    assert "circoe-v3-sidebar" in css
    assert "--circoe-sidebar" in css


def test_ui_shell_does_not_reimplement_optimization_algorithms() -> None:
    shell = _read("circoe_workspace_v3.js")
    forbidden = (
        "cp_sat",
        "extreme_points",
        "brkga_hybrid",
        "tabu_search",
        "routing_hybrid",
        "solutions.sort",
        "method_outcomes.sort",
    )
    for marker in forbidden:
        assert marker not in shell


def test_existing_result_renderer_still_binds_plans_by_method_code() -> None:
    renderer = _read("vertical_results.js")
    assert "solution?.method_code" in renderer
    assert "entriesByMethod = new Map" in renderer
    assert "entriesByMethod.get(outcome.code)" in renderer
    assert "orderedOutcomes(solutions, outcomes)" in renderer
    assert "Résultat des cinq modèles" in renderer


def test_new_assets_are_injected_once(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    response = client.get("/")
    assert response.status_code == 200
    assert response.text.count("/static/circoe_workspace_v3.css?v=0.20.0") == 1
    assert response.text.count("/static/circoe_workspace_v3.js?v=0.20.0") == 1


def test_new_javascript_is_syntactically_valid() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js n’est pas disponible dans cet environnement")
    result = subprocess.run(
        [node, "--check", str(STATIC / "circoe_workspace_v3.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
