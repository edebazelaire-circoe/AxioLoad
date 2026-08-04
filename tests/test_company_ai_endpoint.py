from __future__ import annotations

import io
import json

from fastapi.testclient import TestClient
from PIL import Image

from pallet_optimizer.api import create_app
from pallet_optimizer.company_ai_dual_mode import ALLOWED_OPENAI_MODELS
from pallet_optimizer.document_control import DocumentControlRepository
from pallet_optimizer.persistence import _connect


class _FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size: int = -1) -> bytes:
        raw = json.dumps(self.payload).encode("utf-8")
        return raw if size < 0 else raw[:size]


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (48, 48), "white").save(output, format="PNG")
    return output.getvalue()


def test_primary_manager_can_manage_endpoint_mode(tmp_path):
    client = TestClient(create_app(tmp_path))

    initial = client.get("/api/company/document-ai-config")
    assert initial.status_code == 200
    assert initial.json()["connection_mode"] == "endpoint"
    assert initial.json()["configured"] is False
    assert len(initial.json()["allowed_models"]) == len(ALLOWED_OPENAI_MODELS)

    saved = client.put(
        "/api/company/document-ai-config",
        json={
            "connection_mode": "endpoint",
            "endpoint_url": "https://gateway.example/axioload/document-control",
        },
    )
    assert saved.status_code == 200, saved.text
    payload = saved.json()
    assert payload["configured"] is True
    assert payload["connection_mode"] == "endpoint"
    assert payload["endpoint_url"] == "https://gateway.example/axioload/document-control"
    assert payload["endpoint_host"] == "gateway.example"
    assert payload["provider"] == "client_endpoint"
    assert "api_key" not in payload

    fetched = client.get("/api/company/document-ai-config")
    assert fetched.status_code == 200
    assert fetched.headers["cache-control"] == "no-store"
    assert fetched.json()["endpoint_url"] == payload["endpoint_url"]

    legacy_endpoint = client.get("/api/company/document-ai-endpoint")
    assert legacy_endpoint.status_code == 200
    assert legacy_endpoint.json()["configured"] is True

    deleted = client.delete("/api/company/document-ai-config")
    assert deleted.status_code == 204
    assert client.get("/api/company/document-ai-config").json()["configured"] is False


def test_primary_manager_can_use_encrypted_openai_key_and_allowed_model(tmp_path, monkeypatch):
    monkeypatch.setenv("PLO_DOCUMENT_SECRET_KEY", "axioload-test-secret-for-document-ai")
    client = TestClient(create_app(tmp_path))
    raw_key = "sk-proj-test-key-abcdefghijklmnopqrstuvwxyz"

    saved = client.put(
        "/api/company/document-ai-config",
        json={
            "connection_mode": "openai_api_key",
            "model": "gpt-5-mini",
            "api_key": raw_key,
            "vendor_zero_retention_confirmed": True,
        },
    )
    assert saved.status_code == 200, saved.text
    payload = saved.json()
    assert payload["configured"] is True
    assert payload["connection_mode"] == "openai_api_key"
    assert payload["provider"] == "openai"
    assert payload["model"] == "gpt-5-mini"
    assert payload["api_key_configured"] is True
    assert payload["api_key_hint"] == raw_key[-4:]
    assert "api_key" not in payload
    assert {item["id"] for item in payload["allowed_models"]} == ALLOWED_OPENAI_MODELS

    repository = DocumentControlRepository(client.app.state.registry)
    internal = repository.get_connection_config(  # type: ignore[attr-defined]
        "local",
        include_secret=True,
    )
    assert internal["api_key"] == raw_key

    changed_model = client.put(
        "/api/company/document-ai-config",
        json={
            "connection_mode": "openai_api_key",
            "model": "gpt-4.1",
            "api_key": "",
            "vendor_zero_retention_confirmed": True,
        },
    )
    assert changed_model.status_code == 200, changed_model.text
    assert changed_model.json()["model"] == "gpt-4.1"
    assert repository.get_connection_config(  # type: ignore[attr-defined]
        "local",
        include_secret=True,
    )["api_key"] == raw_key


def test_switching_to_endpoint_removes_dormant_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("PLO_DOCUMENT_SECRET_KEY", "axioload-test-secret-for-document-ai")
    client = TestClient(create_app(tmp_path))
    client.put(
        "/api/company/document-ai-config",
        json={
            "connection_mode": "openai_api_key",
            "model": "gpt-5-mini",
            "api_key": "sk-proj-test-key-abcdefghijklmnopqrstuvwxyz",
            "vendor_zero_retention_confirmed": True,
        },
    )

    switched = client.put(
        "/api/company/document-ai-config",
        json={
            "connection_mode": "endpoint",
            "endpoint_url": "https://gateway.example/axioload/document-control",
        },
    )
    assert switched.status_code == 200
    with _connect(client.app.state.registry.registry_path) as db:
        row = db.execute(
            "SELECT encrypted_api_key,key_hint,connection_mode FROM document_ai_config WHERE tenant_id='local'"
        ).fetchone()
    assert row["connection_mode"] == "endpoint"
    assert row["encrypted_api_key"] is None
    assert row["key_hint"] is None


def test_non_primary_user_cannot_read_or_change_ai_connection(tmp_path, monkeypatch):
    client = TestClient(create_app(tmp_path))
    monkeypatch.setattr(
        "pallet_optimizer.document_control_bootstrap._primary",
        lambda request, context: False,
    )

    get_response = client.get("/api/company/document-ai-config")
    put_response = client.put(
        "/api/company/document-ai-config",
        json={
            "connection_mode": "endpoint",
            "endpoint_url": "https://gateway.example/axioload/document-control",
        },
    )
    delete_response = client.delete("/api/company/document-ai-config")

    assert get_response.status_code == 403
    assert put_response.status_code == 403
    assert delete_response.status_code == 403
    assert "responsable principal" in get_response.json()["detail"]


def test_endpoint_validation_rejects_credentials_queries_and_private_hosts(tmp_path):
    client = TestClient(create_app(tmp_path))
    invalid_urls = (
        "http://gateway.example/axioload",
        "https://user:secret@gateway.example/axioload",
        "https://gateway.example/axioload?token=secret",
        "https://127.0.0.1:8443/axioload",
        "https://localhost/axioload",
    )

    for endpoint_url in invalid_urls:
        response = client.put(
            "/api/company/document-ai-config",
            json={"connection_mode": "endpoint", "endpoint_url": endpoint_url},
        )
        assert response.status_code == 422, endpoint_url


def test_openai_mode_rejects_unapproved_model_and_missing_confirmation(tmp_path, monkeypatch):
    monkeypatch.setenv("PLO_DOCUMENT_SECRET_KEY", "axioload-test-secret-for-document-ai")
    client = TestClient(create_app(tmp_path))
    base = {
        "connection_mode": "openai_api_key",
        "api_key": "sk-proj-test-key-abcdefghijklmnopqrstuvwxyz",
        "vendor_zero_retention_confirmed": True,
    }

    unsupported = client.put(
        "/api/company/document-ai-config",
        json=base | {"model": "gpt-uncontrolled-latest"},
    )
    assert unsupported.status_code == 422
    assert "n’est pas autorisé" in unsupported.json()["detail"]

    unconfirmed = client.put(
        "/api/company/document-ai-config",
        json=base | {
            "model": "gpt-5-mini",
            "vendor_zero_retention_confirmed": False,
        },
    )
    assert unconfirmed.status_code == 422
    assert "politique de conservation" in unconfirmed.json()["detail"]


def test_document_analysis_is_sent_to_client_gateway_without_authorization(tmp_path, monkeypatch):
    client = TestClient(create_app(tmp_path))
    repository = DocumentControlRepository(client.app.state.registry)
    repository.save_endpoint_config(  # type: ignore[attr-defined]
        "local",
        "https://gateway.example/axioload/document-control",
        "responsable-test",
    )
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeResponse(
            {
                "result": {
                    "summary": "Les documents sont cohérents.",
                    "recommended_status": "validated",
                    "items": [
                        {
                            "field_name": "Référence",
                            "category": "Identification",
                            "left_value": "AX-001",
                            "right_value": "AX-001",
                            "status": "conform",
                            "confidence": "high",
                            "severity": "minor",
                            "explanation": "Les références sont identiques.",
                            "source": "standard",
                        }
                    ],
                }
            }
        )

    monkeypatch.setattr("pallet_optimizer.company_ai_endpoint._assert_public_destination", lambda value: None)
    monkeypatch.setattr("pallet_optimizer.company_ai_endpoint.urllib.request.urlopen", fake_urlopen)
    image = _png()
    response = client.post(
        "/api/document-control/analyze",
        data={
            "left_type": "transport_order",
            "right_type": "cmr",
            "title": "Test endpoint",
            "user_instruction": "",
        },
        files={
            "left_file": ("ordre.png", image, "image/png"),
            "right_file": ("cmr.png", image, "image/png"),
        },
    )

    assert response.status_code == 200, response.text
    assert captured["url"] == "https://gateway.example/axioload/document-control"
    assert captured["payload"]["contract_version"] == "axioload.document-control.v1"
    assert captured["payload"]["action"] == "analyze"
    assert captured["payload"]["store"] is False
    assert len(captured["payload"]["documents"]) == 2
    assert captured["payload"]["documents"][0]["content_base64"]
    assert "authorization" not in captured["headers"]
    serialized = json.dumps(captured["payload"])
    assert "api_key" not in serialized
    assert "sk-" not in serialized


def test_document_analysis_can_use_direct_openai_key(tmp_path, monkeypatch):
    monkeypatch.setenv("PLO_DOCUMENT_SECRET_KEY", "axioload-test-secret-for-document-ai")
    client = TestClient(create_app(tmp_path))
    raw_key = "sk-proj-test-key-abcdefghijklmnopqrstuvwxyz"
    saved = client.put(
        "/api/company/document-ai-config",
        json={
            "connection_mode": "openai_api_key",
            "model": "gpt-5-mini",
            "api_key": raw_key,
            "vendor_zero_retention_confirmed": True,
        },
    )
    assert saved.status_code == 200, saved.text
    captured = {}

    result_payload = {
        "summary": "Les documents sont cohérents.",
        "recommended_status": "validated",
        "items": [
            {
                "field_name": "Référence",
                "category": "Identification",
                "left_value": "AX-001",
                "right_value": "AX-001",
                "status": "conform",
                "confidence": "high",
                "severity": "minor",
                "explanation": "Les références sont identiques.",
                "source": "standard",
            }
        ],
    }

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeResponse({"output_text": json.dumps(result_payload)})

    monkeypatch.setattr(
        "pallet_optimizer.company_ai_dual_mode.urllib.request.urlopen",
        fake_urlopen,
    )
    image = _png()
    response = client.post(
        "/api/document-control/analyze",
        data={
            "left_type": "transport_order",
            "right_type": "cmr",
            "title": "Test OpenAI",
            "user_instruction": "",
        },
        files={
            "left_file": ("ordre.png", image, "image/png"),
            "right_file": ("cmr.png", image, "image/png"),
        },
    )

    assert response.status_code == 200, response.text
    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["headers"]["authorization"] == f"Bearer {raw_key}"
    assert captured["payload"]["model"] == "gpt-5-mini"
    assert captured["payload"]["store"] is False
    assert len(captured["payload"]["input"][1]["content"]) == 3
    assert response.json()["provider"] == "openai"
    assert response.json()["model"] == "gpt-5-mini"
