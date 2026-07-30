from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from pallet_optimizer.api import create_app
from pallet_optimizer.catalog import default_vehicle_catalog


def test_default_catalog_contains_standard_20ft_and_40ft_containers():
    vehicles = {vehicle.model_id: vehicle for vehicle in default_vehicle_catalog()}

    assert set(vehicles) >= {"semi_trailer", "rigid_20m3", "container_20ft", "container_40ft"}
    assert vehicles["container_20ft"].interior_length_mm == 5900
    assert vehicles["container_20ft"].interior_width_mm == 2352
    assert vehicles["container_40ft"].interior_length_mm == 12032
    assert vehicles["container_40ft"].door_width_mm == 2340


def test_loading_ui_total_mode_features_are_exposed(tmp_path):
    client = TestClient(create_app(tmp_path))
    html = client.get("/").text
    javascript = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "pallet_optimizer"
        / "static"
        / "total.js"
    ).read_text(encoding="utf-8")

    assert 'data-tab="results"' in html
    assert "results:'Chargement'" in javascript
    assert "['vehicles','data','results','route','total','history']" in javascript
    assert "Temps de calcul" in javascript
    assert "total-available-vehicles" in javascript
    assert "toggleOrderColumn" in javascript
    assert "groupedJobs" in javascript
    assert "Les produits d’un même client restent toujours dans le même camion" in javascript


def test_cargo_observer_does_not_watch_status_mutations_recursively():
    javascript = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "pallet_optimizer"
        / "static"
        / "total.js"
    ).read_text(encoding="utf-8")

    assert "observer.observe(cargoBody,{childList:true});" in javascript
    assert "observer.observe(cargoBody,{childList:true,subtree:true});" not in javascript
