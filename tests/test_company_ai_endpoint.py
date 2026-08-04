from __future__ import annotations

import io
import json

from fastapi.testclient import TestClient
from PIL import Image

from pallet_optimizer.api import create_app
from pallet_optimizer.document_control import DocumentControlRepository
from pallet_optimizer.persistence import _connect, utc_now


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


def test_primary_manager_can_manage_only_an_endpoint(tmp_path):
    client = TestClient(create_app(tmp_path))

    initial = client.get("/api/company/document-ai-endpoint")
    assert initial.status_code == 200
    assert initial.json()["configured"] is False
    assert "n’enregistre aucune clé" in initial.json()["explanation"]

    saved = client.put(
        "/api/company/document-ai-endpoint",
        json={"endpoint_url": "https://gateway.example/axioload/document-control"},
    )
    assert saved.status_code == 200, saved.text
    payload = saved.json()
    assert payload["configured"] is True
    assert payload["endpoint_url"] == "https://gateway.example/axioload/document-control"
    assert payload["endpoint_host"] == "gateway.example"
    assert "api_key" not in payload
    assert "provider" not in payload
    assert "model" not in payload

    fetched = client.get("/api/company/document-ai-endpoint")
    assert fetched.status_code == 200
    assert fetched.headers["cache-control"] == "no-store"
    assert fetched.json()["endpoint_url"] == payload["endpoint_url"]

    deleted = client.delete("/api/company/document-ai-endpoint")
    assert deleted.status_code == 204
    assert client.get("/api/company/document-ai-endpoint").json()["configured"] is False


def test_non_primary_user_cannot_read_or_change_endpoint(tmp_path, monkeypatch):
    client = TestClient(create_app(tmp_path))
    monkeypatch.setattr(
        "pallet_optimizer.document_control_bootstrap._primary",
        lambda request, context: False,
    )

    get_response = client.get("/api/company/document-ai-endpoint")
    put_response = client.put(
        "/api/company/document-ai-endpoint",
        json={"endpoint_url": "https://gateway.example/axioload/document-control"},
    )
    delete_response = client.delete("/api/company/document-ai-endpoint")

    assert get_response.status_code == 403
    assert put_response.status_code == 403
    assert delete_response.status_code == 403
    assert "responsable de l’entreprise" in get_response.json()["detail"]


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
            "/api/company/document-ai-endpoint",
            json={"endpoint_url": endpoint_url},
        )
        assert response.status_code == 422, endpoint_url


def test_legacy_provider_key_is_erased_during_endpoint_migration(tmp_path):
    app = create_app(tmp_path)
    repository = DocumentControlRepository(app.state.registry)
    with _connect(app.state.registry.registry_path) as db:
        db.execute(
            """INSERT INTO document_ai_config(
                   tenant_id,provider,model,encrypted_api_key,key_hint,
                   retention_months,vendor_zero_retention_confirmed,updated_at,updated_by
               ) VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(tenant_id) DO UPDATE SET
                   provider=excluded.provider,model=excluded.model,
                   encrypted_api_key=excluded.encrypted_api_key,key_hint=excluded.key_hint""",
            (
                "local",
                "openai",
                "gpt-5-mini",
                "legacy-encrypted-secret",
                "1234",
                6,
                1,
                utc_now(),
                "legacy-superadmin",
            ),
        )

    config = repository.get_endpoint_config("local", include_url=True)  # type: ignore[attr-defined]
    assert config["configured"] is False
    with _connect(app.state.registry.registry_path) as db:
        row = db.execute(
            "SELECT provider,model,encrypted_api_key,key_hint FROM document_ai_config WHERE tenant_id='local'"
        ).fetchone()
    assert row["provider"] == "client_endpoint"
    assert row["model"] == "managed_by_company"
    assert row["encrypted_api_key"] is None
    assert row["key_hint"] is None


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

    monkeypatch.setattr("pallet_optimizer.company_ai_endpoint._assert_public_destination", lambda endpoint: None)
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
