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

    def read(self, size: int = -1) -> bytes:
        raw = json.dumps(self.payload).encode("utf-8")
        return raw if size < 0 else raw[:size]


def test_superadmin_system_prompts_are_seeded_and_versioned(tmp_path):
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


def test_company_endpoint_healthcheck_has_no_provider_key(tmp_path, monkeypatch):
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
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        captured["timeout"] = timeout
        return _FakeResponse({"ok": True, "message": "Passerelle prête"})

    monkeypatch.setattr("pallet_optimizer.company_ai_endpoint._assert_public_destination", lambda value: None)
    monkeypatch.setattr("pallet_optimizer.company_ai_endpoint.urllib.request.urlopen", fake_urlopen)
    response = client.post("/api/company/document-ai-endpoint/test", json={})

    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True
    assert captured["url"] == "https://gateway.example/axioload/document-control"
    assert captured["payload"]["contract_version"] == "axioload.document-control.v1"
    assert captured["payload"]["action"] == "healthcheck"
    assert "authorization" not in captured["headers"]
    assert "api_key" not in captured["payload"]
    assert "model" not in captured["payload"]
    assert "provider" not in captured["payload"]


def test_legacy_superadmin_provider_configuration_is_rejected(tmp_path):
    client = TestClient(create_app(tmp_path))

    response = client.put(
        "/api/admin/companies/local/document-ai",
        json={"provider": "openai", "model": "gpt-test", "api_key": "sk-test"},
    )

    assert response.status_code == 422
    assert "responsable de l’entreprise" in response.json()["detail"]
    exposed = client.get("/api/admin/companies/local/document-ai")
    assert exposed.status_code == 200
    assert "endpoint_url" not in exposed.json()
    assert "api_key" not in exposed.json()


def test_experience_assets_are_injected(tmp_path):
    client = TestClient(create_app(tmp_path))
    page = client.get("/")
    assert page.status_code == 200
    assert page.text.count("/static/document_control_experience.css?v=0.19.1") == 1
    assert page.text.count("/static/document_control_experience_v2.js?v=0.19.1") == 1
    assert page.text.count("/static/document_control_permission_ui.js?v=0.19.1") == 1
    assert page.text.count("/static/company_ai_endpoint.css?v=0.19.6") == 1
    assert page.text.count("/static/company_ai_endpoint.js?v=0.19.6") == 1
    assert "/static/company_ai_endpoint.css?v=0.19.5" not in page.text
    assert "/static/company_ai_endpoint.js?v=0.19.5" not in page.text
    assert "document_control_experience.js?v=0.18.0" not in page.text
