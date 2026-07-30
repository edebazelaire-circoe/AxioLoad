from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from pallet_optimizer.api import create_app
from pallet_optimizer.catalog import default_vehicle_catalog, vehicle_from_payload, vehicle_to_payload
from pallet_optimizer.import_template import TABLE_COLUMNS, build_import_template_xlsx
from pallet_optimizer.normalization import payload_from_xlsx


def test_container_20ft_has_internal_and_external_dimensions():
    vehicles={vehicle.model_id:vehicle for vehicle in default_vehicle_catalog()};container=vehicles["container_20ft"]
    assert (container.interior_length_mm,container.interior_width_mm,container.interior_height_mm)==(5900,2352,2395)
    assert (container.exterior_length_mm,container.exterior_width_mm,container.exterior_height_mm)==(6058,2438,2591)
    assert vehicle_from_payload(vehicle_to_payload(container))==container


def test_excel_template_matches_the_data_table_columns():
    content=build_import_template_xlsx();workbook=load_workbook(io.BytesIO(content),read_only=True,data_only=True)
    assert tuple(cell.value for cell in workbook.active[1])==TABLE_COLUMNS
    payload=payload_from_xlsx(content);item=payload["items"][0]
    assert item["id"]=="PAL-001";assert item["length"]==1200;assert item["width"]==800
    assert item["stackable"]=="Non";assert item["pickup_address"]=="49.493660, 0.114000"


def test_stackable_pallets_are_returned_at_multiple_heights(tmp_path):
    client=TestClient(create_app(tmp_path));payload={"budget_seconds":5,"requested_solutions":1,
        "vehicle_policy":{"mode":"forced","forced_vehicle_id":"semi_trailer","max_vehicles":1},
        "items":[{"id":"PAL-STACK","quantity":2,"shape":"pallet","length":1200,"width":800,"height":1000,"weight":500,
                  "destination":"Client A","delivery_order":1,"stackable":True}]}
    response=client.post("/local/optimize",json=payload);assert response.status_code==200,response.text;body=response.json()
    placements=body["solutions"][0]["vehicle_plans"][0]["placements"]
    assert sorted(placement["z_mm"] for placement in placements)==[0,1000]
    assert any(diagnostic["code"]=="STACKING_APPLIED" for diagnostic in body["diagnostics"])


def test_weight_concentration_warning_is_reported(tmp_path):
    client=TestClient(create_app(tmp_path));payload={"budget_seconds":3,"requested_solutions":1,
        "vehicle_policy":{"mode":"forced","forced_vehicle_id":"semi_trailer","max_vehicles":1},
        "items":[{"id":"PAL-HEAVY","quantity":2,"shape":"pallet","length":1200,"width":800,"height":900,"weight":1000,
                  "destination":"Client A","delivery_order":1,"stackable":True}]}
    body=client.post("/local/optimize",json=payload).json()
    assert any(diagnostic["code"]=="STACKING_LIMITED_BY_WEIGHT_CONCENTRATION" for diagnostic in body["diagnostics"])


def test_route_rejects_a_load_that_does_not_fit_selected_vehicle(tmp_path):
    client=TestClient(create_app(tmp_path));loading={"budget_seconds":2,
        "vehicle_policy":{"mode":"forced","forced_vehicle_id":"rigid_20m3","max_vehicles":1},
        "items":[{"id":"TOO-LONG","quantity":1,"shape":"pallet","length":9000,"width":800,"height":1000,"weight":300,
                  "destination":"Client A","delivery_order":1}]}
    payload={"method":"alns","vehicle_id":"rigid_20m3","loading":loading,
        "depot":{"lat":49.49,"lon":0.11,"label":"Dépôt"},
        "jobs":[{"id":"JOB-1","client":"Client A","reference":"TOO-LONG","item_ids":["TOO-LONG"],"weight_kg":300,
                 "quantity":1,"unit_type":"palette","pickup":{"lat":49.49,"lon":0.11,"label":"Dépôt"},
                 "delivery":{"lat":49.50,"lon":0.12,"label":"Client A"}}],
        "capacity_kg":3500,"return_to_depot":True,"time_limit_s":1,
        "distance_matrix_m":[[0,0,1000],[0,0,1000],[1000,1000,0]],
        "duration_matrix_s":[[0,0,60],[0,0,60],[60,60,0]]}
    response=client.post("/api/route/optimize",json=payload);assert response.status_code==422
    assert "ne tient pas physiquement" in response.json()["detail"]


def test_validation_title_and_status_are_persisted_for_route(tmp_path):
    client=TestClient(create_app(tmp_path));response=client.post("/api/history/validate",json={
        "optimization_type":"route","title":"Tournée clients Paris","user":"Testeur","selected_solution":0,
        "request":{"jobs":[]},"result":{"status":"completed","elapsed_seconds":1.2,"total_distance_km":42}})
    assert response.status_code==200,response.text;run=response.json();assert run["title"]=="Tournée clients Paris"
    assert run["validation_status"]=="validated";listed=client.get("/api/history").json()
    assert listed[0]["optimization_type"]=="route";assert listed[0]["title"]=="Tournée clients Paris"


def test_enhancement_assets_are_loaded_and_expose_requested_controls(tmp_path):
    client=TestClient(create_app(tmp_path));html=client.get("/").text
    assert "/static/enhancements.js" in html;assert "/static/enhancements.css" in html
    javascript=(Path(__file__).resolve().parents[1]/"src"/"pallet_optimizer"/"static"/"enhancements.js").read_text(encoding="utf-8")
    assert "Gerbable" in javascript;assert "Valider et enregistrer" in javascript
    assert "empty_distance_percent" in javascript;assert "vehicle-focused" in javascript
