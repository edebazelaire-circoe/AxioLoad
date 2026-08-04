from __future__ import annotations

import io
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from pallet_optimizer.api import create_app
from pallet_optimizer.document_control import prepare_document


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "pallet_optimizer" / "static"


def test_vertical_result_and_camera_assets_are_injected_once(tmp_path: Path) -> None:
    response = TestClient(create_app(tmp_path)).get("/")

    assert response.status_code == 200
    expected = (
        "/static/vertical_results.css?v=0.19.3",
        "/static/vertical_results.js?v=0.19.3",
        "/static/document_camera.css?v=0.19.3",
        "/static/document_camera.js?v=0.19.3",
    )
    for asset in expected:
        assert response.text.count(asset) == 1


def test_vertical_results_script_pairs_each_solution_with_its_model() -> None:
    script = (STATIC / "vertical_results.js").read_text(encoding="utf-8")

    assert "opx-model-solution-stack" in script
    assert "buildSolutionRow" in script
    assert "solution.method_code" in script
    assert "q('.opx-solution-slot', row).append(card)" in script
    assert "without-solution" in script
    assert "Les résultats sont classés du meilleur plan" in script


def test_document_camera_requests_rear_camera_and_transfers_a_jpeg() -> None:
    script = (STATIC / "document_camera.js").read_text(encoding="utf-8")

    assert 'accept="image/*"' in script
    assert 'capture="environment"' in script
    assert "new DataTransfer()" in script
    assert "normalizeCameraPhoto" in script
    assert "target.required = false" in script
    assert "observer.observe(main" in script
    assert "observe(document.body" not in script


def test_camera_jpeg_is_accepted_by_document_preparation() -> None:
    source = io.BytesIO()
    Image.new("RGB", (1600, 1200), "white").save(source, format="JPEG", quality=95)

    prepared = prepare_document("photo-document-1.jpg", "image/jpeg", source.getvalue())

    assert prepared.media_type == "image/jpeg"
    assert prepared.filename.endswith(".jpg")
    assert prepared.page_count == 1
    assert prepared.content


def test_new_javascript_assets_are_syntactically_valid() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js n’est pas disponible dans cet environnement")

    for filename in ("vertical_results.js", "document_camera.js"):
        result = subprocess.run(
            [node, "--check", str(STATIC / filename)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"{filename}: {result.stderr}"
