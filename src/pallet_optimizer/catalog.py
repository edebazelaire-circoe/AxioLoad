from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .domain import AxleSpec, Diagnostic, DomainError, Rect, VehicleVersion, ZoneSpec


_MODEL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")


def default_vehicle_catalog() -> tuple[VehicleVersion, ...]:
    """Demo catalogue. Dimensions must be validated by each operator before production use."""
    return (
        VehicleVersion(
            model_id="semi_trailer",
            version=1,
            name="Semi-remorque standard (démo)",
            interior_length_mm=13600,
            interior_width_mm=2450,
            interior_height_mm=2700,
            linear_meter_width_mm=2400,
            payload_kg=24000,
            door_width_mm=2450,
            door_height_mm=2700,
            axles=(
                AxleSpec("groupe_arriere", 0, 18000),
                AxleSpec("sellette", 13600, 12000),
            ),
            source_note="Modèle de démonstration non réglementaire. À valider selon véhicule et pays.",
        ),
        VehicleVersion(
            model_id="rigid_20m3",
            version=1,
            name="Porteur 20 m³ (démo)",
            interior_length_mm=4200,
            interior_width_mm=2100,
            interior_height_mm=2250,
            linear_meter_width_mm=2100,
            payload_kg=3500,
            door_width_mm=2050,
            door_height_mm=2200,
            axles=(
                AxleSpec("essieu_arriere", 0, 2600),
                AxleSpec("essieu_avant", 4200, 1900),
            ),
            obstacles=(
                Rect(0, 2850, 180, 900, 450, "passage_roue_gauche"),
                Rect(1920, 2850, 180, 900, 450, "passage_roue_droit"),
            ),
            source_note="Modèle de démonstration non réglementaire. À valider sur la carte grise et la carrosserie.",
        ),
        VehicleVersion(
            model_id="container_20ft",
            version=1,
            name="Conteneur dry 20 pieds (configuration standard)",
            interior_length_mm=5900,
            interior_width_mm=2352,
            interior_height_mm=2395,
            linear_meter_width_mm=2352,
            payload_kg=28130,
            door_width_mm=2340,
            door_height_mm=2292,
            axles=(),
            source_note=(
                "Configuration indicative d’un conteneur dry 20 pieds d’après les dimensions publiées "
                "par Hapag-Lloyd. Les dimensions et la charge utile varient selon le fabricant et l’unité."
            ),
        ),
        VehicleVersion(
            model_id="container_40ft",
            version=1,
            name="Conteneur dry 40 pieds (configuration standard)",
            interior_length_mm=12032,
            interior_width_mm=2352,
            interior_height_mm=2395,
            linear_meter_width_mm=2352,
            payload_kg=28750,
            door_width_mm=2340,
            door_height_mm=2292,
            axles=(),
            source_note=(
                "Configuration indicative d’un conteneur dry 40 pieds d’après les dimensions publiées "
                "par Hapag-Lloyd. Les dimensions et la charge utile varient selon le fabricant et l’unité."
            ),
        ),
    )


def find_vehicle(version_id_or_model: str, catalog: tuple[VehicleVersion, ...] | None = None) -> VehicleVersion:
    catalog = catalog or default_vehicle_catalog()
    for vehicle in catalog:
        if version_id_or_model in {vehicle.model_id, vehicle.version_id}:
            return vehicle
    raise KeyError(version_id_or_model)


def vehicle_to_payload(vehicle: VehicleVersion) -> dict[str, Any]:
    return {
        "model_id": vehicle.model_id,
        "version": vehicle.version,
        "name": vehicle.name,
        "interior_length_mm": vehicle.interior_length_mm,
        "interior_width_mm": vehicle.interior_width_mm,
        "interior_height_mm": vehicle.interior_height_mm,
        "linear_meter_width_mm": vehicle.linear_meter_width_mm,
        "payload_kg": vehicle.payload_kg,
        "door_width_mm": vehicle.door_width_mm,
        "door_height_mm": vehicle.door_height_mm,
        "axles": [
            {"id": axle.id, "position_mm": axle.position_mm, "max_load_kg": axle.max_load_kg}
            for axle in vehicle.axles
        ],
        "obstacles": [
            {
                "id": obstacle.id,
                "x_mm": obstacle.x_mm,
                "y_mm": obstacle.y_mm,
                "width_mm": obstacle.width_mm,
                "length_mm": obstacle.length_mm,
                "height_mm": obstacle.height_mm,
            }
            for obstacle in vehicle.obstacles
        ],
        "zones": [
            {
                "id": zone.id,
                "rect": {
                    "id": zone.rect.id,
                    "x_mm": zone.rect.x_mm,
                    "y_mm": zone.rect.y_mm,
                    "width_mm": zone.rect.width_mm,
                    "length_mm": zone.rect.length_mm,
                    "height_mm": zone.rect.height_mm,
                },
            }
            for zone in vehicle.zones
        ],
        "source_note": vehicle.source_note,
    }


def _integer(raw: Mapping[str, Any], key: str, fallback: int | None = None) -> int:
    value = raw.get(key, fallback)
    try:
        parsed = int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError) as exc:
        raise DomainError(Diagnostic("INVALID_VEHICLE_NUMBER", f"{key} doit être numérique", field_path=key)) from exc
    if parsed <= 0:
        raise DomainError(Diagnostic("INVALID_VEHICLE_NUMBER", f"{key} doit être strictement positif", field_path=key))
    return parsed


def _float(raw: Mapping[str, Any], key: str, fallback: float | None = None) -> float:
    value = raw.get(key, fallback)
    try:
        parsed = float(str(value).replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise DomainError(Diagnostic("INVALID_VEHICLE_NUMBER", f"{key} doit être numérique", field_path=key)) from exc
    if parsed <= 0:
        raise DomainError(Diagnostic("INVALID_VEHICLE_NUMBER", f"{key} doit être strictement positif", field_path=key))
    return parsed


def vehicle_from_payload(
    raw: Mapping[str, Any],
    *,
    current: VehicleVersion | None = None,
    next_version: int | None = None,
) -> VehicleVersion:
    model_id = str(raw.get("model_id") or (current.model_id if current else "")).strip().lower()
    if not _MODEL_ID_RE.fullmatch(model_id):
        raise DomainError(Diagnostic(
            "INVALID_VEHICLE_ID",
            "L’identifiant véhicule doit contenir 2 à 63 lettres minuscules, chiffres, tirets ou underscores.",
            field_path="model_id",
        ))
    name = str(raw.get("name") or (current.name if current else "")).strip()
    if not name:
        raise DomainError(Diagnostic("INVALID_VEHICLE_NAME", "Le nom du véhicule est obligatoire", field_path="name"))

    base = vehicle_to_payload(current) if current else {}
    merged = {**base, **dict(raw)}
    axles_raw = [dict(a) for a in (merged.get("axles", []) or [])]
    new_length = _integer(merged, "interior_length_mm")
    if (
        current is not None and len(axles_raw) == 2
        and current.axles[0].position_mm == 0
        and current.axles[1].position_mm == current.interior_length_mm
        and int(axles_raw[1].get("position_mm", current.interior_length_mm)) == current.interior_length_mm
    ):
        axles_raw[1]["position_mm"] = new_length
    axles = tuple(
        AxleSpec(str(a["id"]), int(a["position_mm"]), float(a["max_load_kg"]))
        for a in axles_raw
    )
    obstacles_raw = merged.get("obstacles", []) or []
    obstacles = tuple(
        Rect(
            int(o["x_mm"]), int(o["y_mm"]), int(o["width_mm"]), int(o["length_mm"]),
            int(o.get("height_mm", 0)), str(o.get("id", "")),
        )
        for o in obstacles_raw
    )
    zones_raw = merged.get("zones", []) or []
    zones: list[ZoneSpec] = []
    for z in zones_raw:
        rect = z.get("rect", z)
        zones.append(ZoneSpec(
            str(z["id"]),
            Rect(
                int(rect["x_mm"]), int(rect["y_mm"]), int(rect["width_mm"]), int(rect["length_mm"]),
                int(rect.get("height_mm", 0)), str(rect.get("id", z["id"])),
            ),
        ))

    version = next_version if next_version is not None else int(merged.get("version", 1))
    return VehicleVersion(
        model_id=model_id,
        version=version,
        name=name,
        interior_length_mm=new_length,
        interior_width_mm=_integer(merged, "interior_width_mm"),
        interior_height_mm=_integer(merged, "interior_height_mm"),
        linear_meter_width_mm=_integer(merged, "linear_meter_width_mm", _integer(merged, "interior_width_mm")),
        payload_kg=_float(merged, "payload_kg"),
        door_width_mm=_integer(merged, "door_width_mm", _integer(merged, "interior_width_mm")),
        door_height_mm=_integer(merged, "door_height_mm", _integer(merged, "interior_height_mm")),
        axles=axles,
        obstacles=obstacles,
        zones=tuple(zones),
        source_note=str(merged.get("source_note", "Dimensions configurées par l’utilisateur.")),
    )
