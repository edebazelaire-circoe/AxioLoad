from __future__ import annotations

import io

from fastapi.testclient import TestClient
from PIL import Image

from pallet_optimizer.api import create_app
from pallet_optimizer.document_control import DocumentControlRepository


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(output, format="PNG")
    return output.getvalue()


def test_document_control_does_not_persist_sources_and_exports_history(tmp_path, monkeypatch):
    monkeypatch.setenv("PLO_DOCUMENT_SECRET_KEY", "test-document-secret")
    app = create_app(tmp_path)
    client = TestClient(app)
    document_repo = DocumentControlRepository(app.state.registry)
    document_repo.save_ai_config(
        "local",
        {"provider":"openai","model":"test-model","api_key":"sk-test-secret","retention_months":6,"vendor_zero_retention_confirmed":True},
        "test-superadmin",
    )

    def fake_call(*args, **kwargs):
        return {"summary":"Un écart de poids a été détecté.","recommended_status":"review","items":[{"field_name":"Poids brut","category":"Marchandise","left_value":"1000 kg","right_value":"990 kg","status":"different","confidence":"high","severity":"important","explanation":"Les valeurs diffèrent de 10 kg.","source":"standard"}]}

    monkeypatch.setattr("pallet_optimizer.document_control_bootstrap.call_openai", fake_call)
    image = _png()
    response = client.post(
        "/api/document-control/analyze",
        data={"left_type":"transport_order","right_type":"cmr","title":"Dossier test","user_instruction":"Contrôler les poids"},
        files={"left_file":("ordre.png",image,"image/png"),"right_file":("cmr.png",image,"image/png")},
    )
    assert response.status_code == 200, response.text
    control = response.json()
    assert control["reference"].startswith("CTRL-")
    assert "ordre.png" not in str(control)
    assert "cmr.png" not in str(control)

    update = client.put(
        f"/api/document-control/history/{control['id']}",
        json={"final_status":"validated","items":[{"id":control["items"][0]["id"],"included_in_report":False,"human_comment":"Écart accepté"}]},
    )
    assert update.status_code == 200
    assert update.json()["items"][0]["included_in_report"] is False
    assert client.get(f"/api/document-control/history/{control['id']}/export.pdf").content.startswith(b"%PDF")
    assert client.get(f"/api/document-control/history/{control['id']}/export.xlsx").content.startswith(b"PK")


def test_limits_and_locked_prompt_extension(tmp_path, monkeypatch):
    monkeypatch.setenv("PLO_DOCUMENT_SECRET_KEY", "test-document-secret")
    client = TestClient(create_app(tmp_path))
    bootstrap = client.get("/api/document-control/bootstrap")
    assert bootstrap.status_code == 200
    assert bootstrap.json()["limits"] == {"max_file_mb":10,"max_pdf_pages":20,"formats":["PDF","JPG","JPEG","PNG"]}
    saved = client.put("/api/document-control/prompts/transport_order/cmr", json={"admin_instructions":"REF EXP correspond à la référence d'expédition."})
    assert saved.status_code == 200
    assert saved.json()["version"] == 1
    fetched = client.get("/api/document-control/prompts/transport_order/cmr")
    assert fetched.status_code == 200
    assert fetched.json()["system_prompt_version"] == "document-control-v1.1"
    assert "moteur verrouillé" in fetched.json()["locked_prompt_preview"]
