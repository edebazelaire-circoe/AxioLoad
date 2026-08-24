from __future__ import annotations

import io
import socket
import threading
import time
import urllib.request
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient
from PIL import Image
from playwright.sync_api import sync_playwright

from pallet_optimizer.api import create_app
from pallet_optimizer.document_control import DocumentControlRepository, PreparedDocument


SCENARIO_ID = "AXIOLOAD-AI-DOCUMENT-001"
FIXTURE_ID = "AXIOLOAD-DOC-001"
EXPECTED_FIELDS = {"Référence dossier", "Poids brut", "Réserves"}
EXPECTED_SUMMARY = f"{FIXTURE_ID}: deux correspondances et une réserve absente du CMR."


def _png() -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(stream, format="PNG")
    return stream.getvalue()


def _ai_result() -> dict:
    return {
        "summary": EXPECTED_SUMMARY,
        "recommended_status": "review",
        "items": [
            {
                "field_name": "Référence dossier",
                "category": "Référence",
                "left_value": "QA-LOAD-001",
                "right_value": "QA-LOAD-001",
                "status": "conform",
                "confidence": "high",
                "severity": "minor",
                "explanation": "La référence est identique dans les deux documents.",
                "source": "standard",
            },
            {
                "field_name": "Poids brut",
                "category": "Marchandise",
                "left_value": "1 000 kg",
                "right_value": "990 kg",
                "status": "different",
                "confidence": "high",
                "severity": "important",
                "explanation": "Le CMR indique 10 kg de moins.",
                "source": "standard",
            },
            {
                "field_name": "Réserves",
                "category": "Validation",
                "left_value": "RAS",
                "right_value": "",
                "status": "missing",
                "confidence": "high",
                "severity": "minor",
                "explanation": "Aucune réserve n'est présente côté CMR.",
                "source": "standard",
            },
        ],
    }


def _controlled_ai_stub(calls: list[dict[str, object]]):
    def stub(config, left, right, left_type, right_type, company_prompt, user_instruction):
        # Replace only the external AI boundary. Document upload, image
        # preparation, normalization, application state and persistence all use
        # the real AxioLoad production path.
        assert isinstance(left, PreparedDocument)
        assert isinstance(right, PreparedDocument)
        assert left.media_type == "image/jpeg"
        assert right.media_type == "image/jpeg"
        assert left.page_count == 1 and right.page_count == 1
        assert left.content and right.content
        assert left_type == "transport_order"
        assert right_type == "cmr"
        assert config["configured"] is True
        calls.append(
            {
                "left_type": left_type,
                "right_type": right_type,
                "instruction": user_instruction,
            }
        )
        return _ai_result()

    return stub


def _configure_qa_endpoint(app) -> None:
    repository = DocumentControlRepository(app.state.registry)
    repository.save_endpoint_config(  # type: ignore[attr-defined]
        "local",
        "https://gateway.example/axioload/document-control",
        "qa-control",
    )


def _assert_structured_truth(control: dict) -> None:
    assert control["reference"].startswith("CTRL-")
    assert control["provider"] == "client_endpoint"
    assert control["model"] == "managed_by_company"
    assert control["final_status"] == "review"
    assert control["ai_summary"] == EXPECTED_SUMMARY

    items = control["items"]
    assert len(items) == 3
    assert {item["field_name"] for item in items} == EXPECTED_FIELDS
    assert all(item["field_name"] in EXPECTED_FIELDS for item in items)
    assert not any("invent" in str(item).lower() or "hallucin" in str(item).lower() for item in items)

    by_field = {item["field_name"]: item for item in items}
    assert by_field["Référence dossier"]["left_value"] == "QA-LOAD-001"
    assert by_field["Référence dossier"]["right_value"] == "QA-LOAD-001"
    assert by_field["Référence dossier"]["ai_status"] == "conform"
    assert by_field["Poids brut"]["left_value"] == "1 000 kg"
    assert by_field["Poids brut"]["right_value"] == "990 kg"
    assert by_field["Poids brut"]["ai_status"] == "different"
    assert by_field["Réserves"]["left_value"] == "RAS"
    assert by_field["Réserves"]["right_value"] == ""
    assert by_field["Réserves"]["ai_status"] == "missing"

    # Raw source documents and source filenames are not part of the retained
    # business result.
    serialized = str(control)
    assert "qa-transport-order.png" not in serialized
    assert "qa-cmr.png" not in serialized


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_server(app):
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=1) as response:
                if response.status == 200:
                    return server, thread, url
        except OSError:
            time.sleep(0.1)
    server.should_exit = True
    thread.join(timeout=5)
    pytest.fail(f"{SCENARIO_ID}: AxioLoad did not start for browser verification")


def test_axioload_ai_document_001_transcribes_only_supported_facts_and_persists_result(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    client = TestClient(app)
    _configure_qa_endpoint(app)
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "pallet_optimizer.document_control_bootstrap.call_openai",
        _controlled_ai_stub(calls),
    )

    source = _png()
    response = client.post(
        "/api/document-control/analyze",
        data={
            "left_type": "transport_order",
            "right_type": "cmr",
            "title": f"{FIXTURE_ID} contrôle QA",
            "user_instruction": "Comparer uniquement les faits présents dans les deux documents.",
        },
        files={
            "left_file": ("qa-transport-order.png", source, "image/png"),
            "right_file": ("qa-cmr.png", source, "image/png"),
        },
    )
    assert response.status_code == 200, f"{SCENARIO_ID}: {response.text}"
    assert len(calls) == 1, f"{SCENARIO_ID}: AI boundary must be invoked exactly once"

    control = response.json()
    _assert_structured_truth(control)

    history = client.get(f"/api/document-control/history/{control['id']}")
    assert history.status_code == 200
    persisted = history.json()
    assert persisted["id"] == control["id"]
    _assert_structured_truth(persisted)


def test_axioload_ai_document_001_visible_form_matches_analysis_and_reload(tmp_path: Path, monkeypatch):
    app = create_app(tmp_path)
    _configure_qa_endpoint(app)
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "pallet_optimizer.document_control_bootstrap.call_openai",
        _controlled_ai_stub(calls),
    )

    left_path = tmp_path / "qa-transport-order.png"
    right_path = tmp_path / "qa-cmr.png"
    left_path.write_bytes(_png())
    right_path.write_bytes(_png())

    server, thread, url = _start_server(app)
    page_errors: list[str] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.goto(url, wait_until="networkidle")

            # Use the visible workspace switcher installed by AxioLoad's normal
            # UI scripts rather than opening an internal API-only view.
            documents_workspace = page.get_by_role("button", name="Contrôle documentaire")
            documents_workspace.wait_for(state="visible")
            documents_workspace.click()
            page.locator("#dc-form").wait_for(state="visible")

            page.locator('select[name="left_type"]').select_option("transport_order")
            page.locator('select[name="right_type"]').select_option("cmr")
            page.locator('input[name="left_file"]').set_input_files(str(left_path))
            page.locator('input[name="right_file"]').set_input_files(str(right_path))
            page.locator('input[name="title"]').fill(f"{FIXTURE_ID} contrôle QA UI")
            page.locator('textarea[name="user_instruction"]').fill(
                "Comparer uniquement les faits présents dans les deux documents."
            )
            page.locator("#dc-analyze").click()

            page.wait_for_function(
                "() => document.querySelector('#dc-results') && !document.querySelector('#dc-results').classList.contains('dc-hidden')"
            )
            assert len(calls) == 1
            assert page.locator("#dc-final").input_value() == "review"
            assert EXPECTED_SUMMARY in page.locator("#dc-results").inner_text()
            assert page.locator("#dc-body tr").count() == 3

            expected_visible = {
                "Référence dossier": ("QA-LOAD-001", "QA-LOAD-001", "conform"),
                "Poids brut": ("1 000 kg", "990 kg", "different"),
                "Réserves": ("RAS", "", "missing"),
            }
            for field_name, (left_value, right_value, status) in expected_visible.items():
                row = page.locator("#dc-body tr", has_text=field_name)
                assert row.count() == 1
                assert row.locator('[data-field="left_value"]').input_value() == left_value
                assert row.locator('[data-field="right_value"]').input_value() == right_value
                assert row.locator('[data-field="final_status"]').input_value() == status

            page.locator("#dc-save").click()
            page.wait_for_function(
                "() => document.querySelector('#dc-message')?.textContent.includes('Corrections et exclusions enregistrées')"
            )

            # Start a fresh browser page state before verifying persistence. A
            # browser legitimately keeps the locally selected filename in the
            # file input until navigation/reload; that is not server persistence.
            # Reloading clears the local File objects, then the history workflow
            # must reconstruct the visible analysis entirely from persisted data.
            page.reload(wait_until="networkidle")
            documents_workspace = page.get_by_role("button", name="Contrôle documentaire")
            documents_workspace.wait_for(state="visible")
            documents_workspace.click()
            page.locator("#dc-form").wait_for(state="visible")
            assert page.locator('input[name="left_file"]').input_value() == ""
            assert page.locator('input[name="right_file"]').input_value() == ""

            page.locator("#dc-history-view").click()
            page.wait_for_function(
                f"() => document.querySelector('#dc-history-list')?.textContent.includes('{FIXTURE_ID}')"
            )
            history_item = page.locator("#dc-history-list .dc-history-item", has_text=FIXTURE_ID).first
            history_item.get_by_role("button", name="Ouvrir").click()
            page.wait_for_function(
                "() => document.querySelector('#dc-results') && !document.querySelector('#dc-results').classList.contains('dc-hidden')"
            )

            assert EXPECTED_SUMMARY in page.locator("#dc-results").inner_text()
            assert page.locator("#dc-body tr").count() == 3
            for field_name, (left_value, right_value, status) in expected_visible.items():
                row = page.locator("#dc-body tr", has_text=field_name)
                assert row.count() == 1
                assert row.locator('[data-field="left_value"]').input_value() == left_value
                assert row.locator('[data-field="right_value"]').input_value() == right_value
                assert row.locator('[data-field="final_status"]').input_value() == status

            assert "qa-transport-order.png" not in page.content()
            assert "qa-cmr.png" not in page.content()
            assert page_errors == [], f"{SCENARIO_ID}: browser errors: {page_errors}"
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()
