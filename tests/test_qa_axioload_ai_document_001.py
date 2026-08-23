from __future__ import annotations

import io

from fastapi.testclient import TestClient
from PIL import Image

from pallet_optimizer.api import create_app
from pallet_optimizer.document_control import DocumentControlRepository, PreparedDocument


SCENARIO_ID = "AXIOLOAD-AI-DOCUMENT-001"
FIXTURE_ID = "AXIOLOAD-DOC-001"
EXPECTED_FIELDS = {"Référence dossier", "Poids brut", "Réserves"}


def _png() -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(stream, format="PNG")
    return stream.getvalue()


def test_axioload_ai_document_001_transcribes_only_supported_facts_and_persists_result(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    client = TestClient(app)
    repository = DocumentControlRepository(app.state.registry)
    repository.save_endpoint_config(  # type: ignore[attr-defined]
        "local",
        "https://gateway.example/axioload/document-control",
        "qa-control",
    )

    calls: list[dict[str, object]] = []

    def controlled_ai_stub(config, left, right, left_type, right_type, company_prompt, user_instruction):
        # The external AI boundary is replaced before any network operation. The
        # rest of the production upload -> preparation -> normalization ->
        # persistence path remains unchanged.
        assert isinstance(left, PreparedDocument)
        assert isinstance(right, PreparedDocument)
        assert left.media_type == "image/jpeg"
        assert right.media_type == "image/jpeg"
        assert left.page_count == 1 and right.page_count == 1
        assert left.content and right.content
        assert left_type == "transport_order"
        assert right_type == "cmr"
        assert config["configured"] is True
        calls.append({
            "left_type": left_type,
            "right_type": right_type,
            "instruction": user_instruction,
        })
        return {
            "summary": f"{FIXTURE_ID}: deux correspondances et une réserve absente du CMR.",
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

    monkeypatch.setattr("pallet_optimizer.document_control_bootstrap.call_openai", controlled_ai_stub)

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
    assert control["reference"].startswith("CTRL-")
    assert control["provider"] == "client_endpoint"
    assert control["model"] == "managed_by_company"
    assert control["final_status"] == "review"

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
    assert by_field["Réserves"]["right_value"] == ""
    assert by_field["Réserves"]["ai_status"] == "missing"

    # Source documents and source filenames must not be retained in the
    # persisted control object.
    serialized = str(control)
    assert "qa-transport-order.png" not in serialized
    assert "qa-cmr.png" not in serialized

    history = client.get(f"/api/document-control/history/{control['id']}")
    assert history.status_code == 200
    persisted = history.json()
    assert persisted["id"] == control["id"]
    assert persisted["summary"] == control["summary"]
    assert {item["field_name"] for item in persisted["items"]} == EXPECTED_FIELDS
    assert "qa-transport-order.png" not in str(persisted)
    assert "qa-cmr.png" not in str(persisted)
