from __future__ import annotations

import json

from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app
from pallet_optimizer.document_control import DocumentControlRepository


class _FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_superadmin_system_prompts_are_seeded_and_versioned(tmp_path, monkeypatch):
    monkeypatch.setenv("PLO_DOCUMENT_SECRET_KEY", "test-document-secret")
    client = TestClient(create_app(tmp_path))

    response = client.get("/api/admin/document-prompts")
    assert response.status_code == 200
    payload = response.json()
    assert payload["system_prompt_version"] == "document-control-v1.1"
    assert len(payload["profiles"]) == 7
    assert payload["profiles"][0]["key"] == "generic"

    updated = client.put(
        "/api/admin/document-prompts/transport_order__cmr",
        json={"instructions": "Contrôler aussi la référence interne AXIO."},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2

    prompt = DocumentControlRepository(client.app.state.registry).get_prompt(
        "local", "transport_order", "cmr"
    )
    assert prompt["system_base_prompt_version"] == 2
    assert "AXIO" in prompt["system_base_prompt"]


def test_api_test_calls_responses_endpoint_with_store_false(tmp_path, monkeypatch):
    monkeypatch.setenv("PLO_DOCUMENT_SECRET_KEY", "test-document-secret")
    client = TestClient(create_app(tmp_path))
    repository = DocumentControlRepository(client.app.state.registry)
    repository.save_ai_config(
        "local",
        {
            "provider": "openai",
            "model": "gpt-test",
            "api_key": "sk-test",
            "retention_months": 6,
            "vendor_zero_retention_confirmed": True,
        },
        "superadmin",
    )
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeResponse({"id": "resp_test", "output_text": "OK"})

    monkeypatch.setattr("pallet_optimizer.document_control_system.urllib.request.urlopen", fake_urlopen)
    response = client.post(
        "/api/admin/companies/local/document-ai/test",
        json={"provider": "openai", "model": "gpt-test", "api_key": ""},
    )
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True
    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["payload"]["store"] is False
    assert captured["payload"]["model"] == "gpt-test"


def test_experience_assets_are_injected(tmp_path, monkeypatch):
    monkeypatch.setenv("PLO_DOCUMENT_SECRET_KEY", "test-document-secret")
    client = TestClient(create_app(tmp_path))
    page = client.get("/")
    assert page.status_code == 200
    assert "/static/document_control_experience.css?v=0.14.0" in page.text
    assert "/static/document_control_experience.js?v=0.14.0" in page.text
