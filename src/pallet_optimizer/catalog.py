from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .domain import AxleSpec, Diagnostic, DomainError, Rect, VehicleVersion, ZoneSpec


_MODEL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")
_STANDARD_EXTERIOR_MM = {
    "semi_trailer": (13800, 2550, 4000),
    "rigid_20m3": (6500, 2200, 3200),
    "container_20ft": (6058, 2438, 2591),
    "container_40ft": (12192, 2438, 2591),
}


def default_vehicle_catalog() -> tuple[VehicleVersion, ...]:
    """Demo catalogue. Dimensions must be validated by each operator before production use."""
    return (
        VehicleVersion(model_id="semi_trailer", version=1, name="Semi-remorque standard (démo)",
            interior_length_mm=13600, interior_width_mm=2450, interior_height_mm=2700,
            linear_meter_width_mm=2400, payload_kg=24000, door_width_mm=2450, door_height_mm=2700,
            axles=(AxleSpec("groupe_arriere", 0, 18000), AxleSpec("sellette", 13600, 12000)),
            exterior_length_mm=13800, exterior_width_mm=2550, exterior_height_mm=4000,
            source_note="Modèle de démonstration non réglementaire. Dimensions extérieures indicatives à valider selon tracteur, remorque et pays."),
        VehicleVersion(model_id="rigid_20m3", version=1, name="Porteur 20 m³ (démo)",
            interior_length_mm=4200, interior_width_mm=2100, interior_height_mm=2250,
            linear_meter_width_mm=2100, payload_kg=3500, door_width_mm=2050, door_height_mm=2200,
            axles=(AxleSpec("essieu_arriere", 0, 2600), AxleSpec("essieu_avant", 4200, 1900)),
            exterior_length_mm=6500, exterior_width_mm=2200, exterior_height_mm=3200,
            obstacles=(Rect(0, 2850, 180, 900, 450, "passage_roue_gauche"), Rect(1920, 2850, 180, 900, 450, "passage_roue_droit")),
            source_note="Modèle de démonstration non réglementaire. À valider sur la carte grise et la carrosserie."),
        VehicleVersion(model_id="container_20ft", version=1, name="Conteneur dry 20 pieds (configuration standard)",
            interior_length_mm=5900, interior_width_mm=2352, interior_height_mm=2395,
            linear_meter_width_mm=2352, payload_kg=28130, door_width_mm=2340, door_height_mm=2292,
            axles=(), exterior_length_mm=6058, exterior_width_mm=2438, exterior_height_mm=2591,
            source_note=("Configuration indicative d’un conteneur dry 20 pieds : dimensions extérieures ISO 6 058 × 2 438 × 2 591 mm. "
                         "Les dimensions intérieures et la charge utile varient selon le fabricant et l’unité ; contrôler la plaque CSC.")),
        VehicleVersion(model_id="container_40ft", version=1, name="Conteneur dry 40 pieds (configuration standard)",
            interior_length_mm=12032, interior_width_mm=2352, interior_height_mm=2395,
            linear_meter_width_mm=2352, payload_kg=28750, door_width_mm=2340, door_height_mm=2292,
            axles=(), exterior_length_mm=12192, exterior_width_mm=2438, exterior_height_mm=2591,
            source_note=("Configuration indicative d’un conteneur dry 40 pieds : dimensions extérieures ISO 12 192 × 2 438 × 2 591 mm. "
                         "Les dimensions intérieures et la charge utile varient selon le fabricant et l’unité ; contrôler la plaque CSC.")),
    )


def find_vehicle(version_id_or_model: str, catalog: tuple[VehicleVersion, ...] | None = None) -> VehicleVersion:
    catalog = catalog or default_vehicle_catalog()
    for vehicle in catalog:
        if version_id_or_model in {vehicle.model_id, vehicle.version_id}:
            return vehicle
    raise KeyError(version_id_or_model)


def vehicle_to_payload(vehicle: VehicleVersion) -> dict[str, Any]:
    return {
        "model_id": vehicle.model_id, "version": vehicle.version, "name": vehicle.name,
        "interior_length_mm": vehicle.interior_length_mm, "interior_width_mm": vehicle.interior_width_mm,
        "interior_height_mm": vehicle.interior_height_mm, "exterior_length_mm": vehicle.exterior_length_mm,
        "exterior_width_mm": vehicle.exterior_width_mm, "exterior_height_mm": vehicle.exterior_height_mm,
        "linear_meter_width_mm": vehicle.linear_meter_width_mm, "payload_kg": vehicle.payload_kg,
        "door_width_mm": vehicle.door_width_mm, "door_height_mm": vehicle.door_height_mm,
        "axles": [{"id": axle.id, "position_mm": axle.position_mm, "max_load_kg": axle.max_load_kg} for axle in vehicle.axles],
        "obstacles": [{"id": obstacle.id, "x_mm": obstacle.x_mm, "y_mm": obstacle.y_mm, "width_mm": obstacle.width_mm,
                       "length_mm": obstacle.length_mm, "height_mm": obstacle.height_mm} for obstacle in vehicle.obstacles],
        "zones": [{"id": zone.id, "rect": {"id": zone.rect.id, "x_mm": zone.rect.x_mm, "y_mm": zone.rect.y_mm,
                   "width_mm": zone.rect.width_mm, "length_mm": zone.rect.length_mm, "height_mm": zone.rect.height_mm}}
                  for zone in vehicle.zones],
        "source_note": vehicle.source_note,
    }


def _integer(raw: Mapping[str, Any], key: str, fallback: int | None = None) -> int:
    value = raw.get(key, fallback)
    try: parsed = int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError) as exc:
        raise DomainError(Diagnostic("INVALID_VEHICLE_NUMBER", f"{key} doit être numérique", field_path=key)) from exc
    if parsed <= 0: raise DomainError(Diagnostic("INVALID_VEHICLE_NUMBER", f"{key} doit être strictement positif", field_path=key))
    return parsed


def _float(raw: Mapping[str, Any], key: str, fallback: float | None = None) -> float:
    value = raw.get(key, fallback)
    try: parsed = float(str(value).replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise DomainError(Diagnostic("INVALID_VEHICLE_NUMBER", f"{key} doit être numérique", field_path=key)) from exc
    if parsed <= 0: raise DomainError(Diagnostic("INVALID_VEHICLE_NUMBER", f"{key} doit être strictement positif", field_path=key))
    return parsed


def _exterior_value(merged: Mapping[str, Any], model_id: str, key: str, interior: int, offset: int) -> int:
    if merged.get(key) not in (None, ""): return _integer(merged, key)
    standard = _STANDARD_EXTERIOR_MM.get(model_id)
    if standard: return standard[{"exterior_length_mm": 0, "exterior_width_mm": 1, "exterior_height_mm": 2}[key]]
    return interior + offset


def vehicle_from_payload(raw: Mapping[str, Any], *, current: VehicleVersion | None = None, next_version: int | None = None) -> VehicleVersion:
    model_id = str(raw.get("model_id") or (current.model_id if current else "")).strip().lower()
    if not _MODEL_ID_RE.fullmatch(model_id):
        raise DomainError(Diagnostic("INVALID_VEHICLE_ID", "L’identifiant véhicule doit contenir 2 à 63 lettres minuscules, chiffres, tirets ou underscores.", field_path="model_id"))
    name = str(raw.get("name") or (current.name if current else "")).strip()
    if not name: raise DomainError(Diagnostic("INVALID_VEHICLE_NAME", "Le nom du véhicule est obligatoire", field_path="name"))
    merged = {**(vehicle_to_payload(current) if current else {}), **dict(raw)}
    axles_raw = [dict(a) for a in (merged.get("axles", []) or [])]
    new_length, new_width, new_height = (_integer(merged, "interior_length_mm"), _integer(merged, "interior_width_mm"), _integer(merged, "interior_height_mm"))
    if (current is not None and len(axles_raw) == 2 and current.axles[0].position_mm == 0
            and current.axles[1].position_mm == current.interior_length_mm
            and int(axles_raw[1].get("position_mm", current.interior_length_mm)) == current.interior_length_mm):
        axles_raw[1]["position_mm"] = new_length
    axles = tuple(AxleSpec(str(a["id"]), int(a["position_mm"]), float(a["max_load_kg"])) for a in axles_raw)
    obstacles = tuple(Rect(int(o["x_mm"]), int(o["y_mm"]), int(o["width_mm"]), int(o["length_mm"]), int(o.get("height_mm", 0)), str(o.get("id", ""))) for o in (merged.get("obstacles", []) or []))
    zones = []
    for z in (merged.get("zones", []) or []):
        rect = z.get("rect", z)
        zones.append(ZoneSpec(str(z["id"]), Rect(int(rect["x_mm"]), int(rect["y_mm"]), int(rect["width_mm"]), int(rect["length_mm"]), int(rect.get("height_mm", 0)), str(rect.get("id", z["id"])))))
    version = next_version if next_version is not None else int(merged.get("version", 1))
    return VehicleVersion(model_id=model_id, version=version, name=name, interior_length_mm=new_length, interior_width_mm=new_width,
        interior_height_mm=new_height, linear_meter_width_mm=_integer(merged, "linear_meter_width_mm", new_width), payload_kg=_float(merged, "payload_kg"),
        door_width_mm=_integer(merged, "door_width_mm", new_width), door_height_mm=_integer(merged, "door_height_mm", new_height), axles=axles,
        exterior_length_mm=_exterior_value(merged, model_id, "exterior_length_mm", new_length, 300),
        exterior_width_mm=_exterior_value(merged, model_id, "exterior_width_mm", new_width, 100),
        exterior_height_mm=_exterior_value(merged, model_id, "exterior_height_mm", new_height, 300),
        obstacles=obstacles, zones=tuple(zones), source_note=str(merged.get("source_note", "Dimensions configurées par l’utilisateur.")))
