from __future__ import annotations

from typing import Any, Mapping

from .catalog import find_vehicle
from .domain import CargoItem, VehicleVersion
from .normalization import normalize_payload
from .route_optimization import RouteInputError, compare as route_compare, optimise as route_optimise
from .stacking import can_pack_items

ROAD_GABARIT_WARNING = (
    "La faisabilité du chargement est contrôlée avec les dimensions intérieures du véhicule. "
    "Le service routier public OSRM utilise toutefois un profil automobile générique : les limitations "
    "routières de hauteur, largeur, longueur ou tonnage ne sont pas garanties sans moteur poids lourd dédié."
)


def _source_ids(job: Mapping[str, Any]) -> tuple[str, ...]:
    values = job.get("item_ids")
    if isinstance(values, list): return tuple(str(v).strip() for v in values if str(v or "").strip())
    return tuple(part.strip() for part in str(job.get("reference") or "").split(",") if part.strip())


def _vehicle(payload: Mapping[str, Any], catalog: tuple[VehicleVersion, ...]) -> VehicleVersion | None:
    model_id = str(payload.get("vehicle_id") or "").strip(); loading = payload.get("loading")
    if not model_id and isinstance(loading, Mapping) and isinstance(loading.get("vehicle_policy"), Mapping):
        model_id = str(loading["vehicle_policy"].get("forced_vehicle_id") or "").strip()
    if not model_id: return None
    try: return find_vehicle(model_id, catalog)
    except KeyError as exc: raise RouteInputError(f"Véhicule inconnu : {model_id}") from exc


def _active_sets(payload: Mapping[str, Any], result: Mapping[str, Any], expanded: Mapping[str, tuple[CargoItem, ...]]):
    jobs = payload.get("jobs")
    if not isinstance(jobs, list): return []
    job_sources = {str(job.get("id") or ""): _source_ids(job) for job in jobs if isinstance(job, Mapping)}
    active: set[str] = set(); checks = []
    for stop in result.get("stops") or []:
        if not isinstance(stop, Mapping): continue
        sources = job_sources.get(str(stop.get("job_id") or ""), ())
        if stop.get("type") == "pickup": active.update(sources)
        elif stop.get("type") == "delivery": active.difference_update(sources)
        current = tuple(item for source in sorted(active) for item in expanded.get(source, ()))
        if current: checks.append((str(stop.get("label") or stop.get("client") or "arrêt"), current))
    return checks


def _empty_distance(result: dict[str, Any]) -> None:
    stops, legs = result.get("stops") or [], result.get("legs") or []; empty_km = 0.0
    for index, leg in enumerate(legs):
        load = float(stops[index].get("load_after_kg") or 0.0) if index < len(stops) and isinstance(stops[index], Mapping) else 0.0
        if load <= 1e-9: empty_km += float(leg.get("distance_km") or 0.0)
    total = float(result.get("total_distance_km") or 0.0)
    result["empty_distance_km"] = empty_km; result["loaded_distance_km"] = max(0.0,total-empty_km)
    result["empty_distance_percent"] = empty_km / total * 100.0 if total > 0 else 0.0


def _validate_result(payload: Mapping[str, Any], result: dict[str, Any], catalog: tuple[VehicleVersion, ...]) -> dict[str, Any]:
    vehicle = _vehicle(payload, catalog); loading = payload.get("loading"); checked_sets = 0
    if vehicle is not None and isinstance(loading, Mapping) and isinstance(loading.get("items"), list):
        try: normalized = normalize_payload(loading, requested_solutions=1, catalog=catalog)
        except Exception as exc:
            message = getattr(getattr(exc,"diagnostic",None),"message",str(exc)); raise RouteInputError(message) from exc
        by_source: dict[str,list[CargoItem]] = {}
        for item in normalized.items: by_source.setdefault(item.source_id,[]).append(item)
        cache = {}
        for label, active in _active_sets(payload,result,{key:tuple(value) for key,value in by_source.items()}):
            signature = tuple(sorted(item.id for item in active))
            if signature not in cache: cache[signature] = can_pack_items(active,vehicle,budget_seconds=2.0)
            feasible, diagnostics = cache[signature]; checked_sets += 1
            if not feasible:
                detail = next((d.message for d in diagnostics if str(getattr(d,"severity","")) == "error"),"")
                raise RouteInputError(f"La charge présente dans le véhicule après l’arrêt « {label} » ne tient pas physiquement dans « {vehicle.name} ». Le trajet est rejeté avant validation." + (f" Détail : {detail}" if detail else ""))
    constraints = {}
    if vehicle is not None:
        constraints = {"vehicle_id":vehicle.model_id,"vehicle_name":vehicle.name,"interior_length_mm":vehicle.interior_length_mm,
            "interior_width_mm":vehicle.interior_width_mm,"interior_height_mm":vehicle.interior_height_mm,
            "exterior_length_mm":vehicle.exterior_length_mm,"exterior_width_mm":vehicle.exterior_width_mm,
            "exterior_height_mm":vehicle.exterior_height_mm,"payload_kg":vehicle.payload_kg,"road_restrictions_guaranteed":False}
    warnings = list(result.get("warnings") or [])
    if ROAD_GABARIT_WARNING not in warnings: warnings.append(ROAD_GABARIT_WARNING)
    result["warnings"] = warnings; result["vehicle_constraints"] = constraints
    result["loading_feasibility"] = {"checked":checked_sets>0,"checked_load_states":checked_sets,"feasible":True,"road_gabarit_guaranteed":False}
    _empty_distance(result); return result


def optimise_checked(payload: dict[str, Any], catalog: tuple[VehicleVersion, ...]) -> dict[str, Any]:
    return _validate_result(payload, route_optimise(payload), catalog)


def compare_checked(payload: dict[str, Any], catalog: tuple[VehicleVersion, ...]) -> dict[str, Any]:
    compared = route_compare(payload)
    compared["results"] = [_validate_result(payload,result,catalog) for result in compared.get("results") or []]
    return compared
