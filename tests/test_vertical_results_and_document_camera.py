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
        "/static/vertical_results.css?v=0.19.4",
        "/static/vertical_results.js?v=0.19.4",
        "/static/results_compact.css?v=0.19.5",
        "/static/results_compact.js?v=0.19.5",
        "/static/document_camera.css?v=0.19.6",
        "/static/document_camera.js?v=0.19.6",
    )
    for asset in expected:
        assert response.text.count(asset) == 1

    assert response.text.index("vertical_results.js?v=0.19.4") < response.text.index("results_compact.js?v=0.19.5")


def test_results_keep_two_aligned_rows_of_five_slots() -> None:
    script = (STATIC / "vertical_results.js").read_text(encoding="utf-8")
    stylesheet = (STATIC / "vertical_results.css").read_text(encoding="utf-8")

    assert "opx-model-row" in script
    assert "opx-solution-row" in script
    assert "buildSolutionCell" in script
    assert "buildFailureCell" in script
    assert "solution.method_code" in script
    assert "Les cinq modèles restent dans le premier bloc" in script
    assert "grid-template-columns: repeat(5" in stylesheet
    assert "opx-comparison-scroll" in stylesheet
    assert "scroll-snap-type: x proximity" in stylesheet


def test_result_comparison_is_compact_collapsible_and_removes_redundant_status() -> None:
    script = (STATIC / "results_compact.js").read_text(encoding="utf-8")
    stylesheet = (STATIC / "results_compact.css").read_text(encoding="utf-8")

    for token in (
        "removeLegacyStatusPanel",
        "method-status-panel",
        "Voir le détail des modèles",
        "Masquer les modèles",
        "aria-expanded",
        "localStorage",
        "MutationObserver",
    ):
        assert token in script

    for token in (
        "#method-status-panel",
        ".opx-model-toggle",
        ".opx-solution-cell",
        "min-height: 168px",
        "padding: 14px 16px",
    ):
        assert token in stylesheet


def test_document_camera_requests_rear_camera_and_transfers_a_jpeg() -> None:
    script = (STATIC / "document_camera.js").read_text(encoding="utf-8")

    assert "camera.accept = 'image/*'" in script
    assert "camera.setAttribute('capture', 'environment')" in script
    assert "document.body.append(camera)" in script
    assert "data-dc-camera-trigger" in script
    assert "new DataTransfer()" in script
    assert "normalizeCameraPhoto" in script
    assert "target.required = false" in script
    assert "observer.observe(main" in script
    assert "observe(document.body" not in script
    assert "dc-camera-hint" not in script
    assert 'dc-camera-status dc-hidden' in script


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

    for filename in ("vertical_results.js", "results_compact.js", "document_camera.js"):
        result = subprocess.run(
            [node, "--check", str(STATIC / filename)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"{filename}: {result.stderr}"
