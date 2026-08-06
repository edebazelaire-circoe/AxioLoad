from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "pallet_optimizer" / "static"


def test_logipilot_and_vehicle_viewer_assets_are_injected_once(tmp_path: Path) -> None:
    response = TestClient(create_app(tmp_path)).get("/")

    assert response.status_code == 200
    expected = (
        "/static/viewer_vehicle_enhancements.css?v=0.19.8",
        "/static/logipilot_branding.css?v=0.19.8",
        "/static/viewer_vehicle_enhancements.js?v=0.19.8",
        "/static/logipilot_branding.js?v=0.19.8",
    )
    for asset in expected:
        assert response.text.count(asset) == 1


def test_viewer_keeps_a_fixed_vertical_perspective_and_opaque_cargo() -> None:
    script = (STATIC / "viewer_vehicle_enhancements.js").read_text(encoding="utf-8")
    stylesheet = (STATIC / "viewer_vehicle_enhancements.css").read_text(encoding="utf-8")

    for token in (
        "FIXED_TILT = 0.52",
        "state.tilt = FIXED_TILT",
        "event.stopImmediatePropagation()",
        "drawTrailerBody",
        "drawCab",
        "drawWheel",
        "Number(alpha) >= 0.4 ? 1 : alpha",
        "Glisser horizontalement pour tourner",
    ):
        assert token in script

    assert "aspect-ratio: 1000 / 620" in stylesheet
    assert "resize: none" in stylesheet
    assert "touch-action: none" in stylesheet


def test_logipilot_branding_uses_the_validated_name_tagline_and_circoe_colors() -> None:
    script = (STATIC / "logipilot_branding.js").read_text(encoding="utf-8")
    horizontal = (STATIC / "brand" / "logipilot-horizontal-dark.svg").read_text(encoding="utf-8")
    icon = (STATIC / "brand" / "logipilot-icon.svg").read_text(encoding="utf-8")

    assert "const BRAND_NAME = 'LogiPilot'" in script
    assert "planification d’itinéraires et contrôle documentaire" in script
    assert "logipilot-horizontal-dark.svg" in script
    assert "logipilot-icon.svg" in script

    for color in ("#0F3D3E", "#1DAA8A", "#F5B400", "#E63946"):
        assert color in horizontal or color in icon


def test_new_javascript_assets_are_syntactically_valid() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js n’est pas disponible dans cet environnement")

    for filename in ("viewer_vehicle_enhancements.js", "logipilot_branding.js"):
        result = subprocess.run(
            [node, "--check", str(STATIC / filename)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"{filename}: {result.stderr}"
