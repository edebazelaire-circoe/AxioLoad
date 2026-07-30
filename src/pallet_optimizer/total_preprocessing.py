from __future__ import annotations

import copy
import time
from collections import Counter, defaultdict
from dataclasses import replace
from typing import Any, Iterable, Mapping

from .domain import CargoItem, Severity, VehicleVersion
from .normalization import normalize_payload
from .optimization_methods import METHOD_BY_CODE, pack_with_method
from .packing import estimate_vehicle_lower_bound, partition_items
from .total_optimization import TotalOptimizationError, optimise_total
from .validation import (
    calculate_weight,
    has_errors,
    validate_compatibility,
    validate_delivery_access,
    validate_geometry,
)


_PREPARATION_METHODS = ("block_layers", "extreme_points", "skyline_blf", "brkga_hybrid")
_MAX_TOTAL_ROUTE_NODES = 35


def _validated_pack(
    items: tuple[CargoItem, ...],
    vehicle: VehicleVersion,
    seed: int,
    deadline: float,
) -> bool:
    """Return True only when one of the 3D packers produces a fully valid floor plan."""
    normalized_items = tuple(replace(item, delivery_order=1) for item in items)
    item_map = {item.id: item for item in normalized_items}
    for method_index, code in enumerate(_PREPARATION_METHODS):
        if time.perf_counter() >= deadline:
            return False
        method = METHOD_BY_CODE[code]
        attempt_deadline = min(
            deadline,
            time.perf_counter() + min(0.9, 0.18 + len(normalized_items) * 0.012),
        )
        placements, _ = pack_with_method(
            method,
            normalized_items,
            vehicle,
            seed + method_index * 1009,
            attempt_deadline,
        )
        if placements is None:
            continue
        diagnostics = (
            *validate_geometry(vehicle, placements, item_map),
            *validate_delivery_access(placements),
        )
        _, weight_diagnostics, _ = calculate_weight(vehicle, placements)
        diagnostics = (
            *diagnostics,
            *weight_diagnostics,
            *validate_compatibility((placements,), item_map),
        )
        if not has_errors(tuple(diagnostics)):
            return True
    return False


def _partition_oversized_client(
    *,
    client: str,
    items: tuple[CargoItem, ...],
    vehicle: VehicleVersion,
    max_vehicles: int,
    max_chunks: int,
    seed: int,
    deadline: float,
) -> tuple[tuple[CargoItem, ...], ...]:
    """
    Keep a client in one delivery lot whenever possible.

    When that is physically impossible, create smaller indivisible lots. The route
    optimizers can then recombine those lots with nearby clients while still using
    at most ``max_vehicles`` actual routes.
    """
    client_items = tuple(replace(item, delivery_order=1) for item in items)
    if _validated_pack(client_items, vehicle, seed, deadline):
        return (items,)

    lower_bound = estimate_vehicle_lower_bound(client_items, vehicle)
    if lower_bound > max_vehicles:
        raise TotalOptimizationError(
            f"Les marchandises du client « {client} » nécessitent au minimum {lower_bound} véhicule(s) "
            f"de type « {vehicle.name} », mais seulement {max_vehicles} sont disponibles."
        )

    if max_chunks < lower_bound:
        raise TotalOptimizationError(
            f"Le client « {client} » doit être découpé en au moins {lower_bound} lots de livraison, "
            "mais le calcul dépasserait la limite de complexité de l’optimisation totale."
        )

    # Twice the physical lower bound gives ALNS and the genetic Split decoder enough
    # freedom to fill residual spaces with nearby clients instead of freezing one full
    # truck-sized lot too early. Explicit keep-together groups remain hard constraints.
    target_chunks = min(max_chunks, len(client_items), max(lower_bound, lower_bound * 2))
    original_by_id = {item.id: item for item in items}

    for chunk_count in range(target_chunks, max_chunks + 1):
        for variant in range(32):
            if time.perf_counter() >= deadline:
                break
            partition = partition_items(
                client_items,
                vehicle,
                chunk_count,
                seed=seed,
                variant=variant,
            )
            if partition is None:
                continue
            if not all(
                _validated_pack(tuple(chunk), vehicle, seed + variant * 211 + index * 37, deadline)
                for index, chunk in enumerate(partition)
            ):
                continue
            return tuple(
                tuple(original_by_id[item.id] for item in chunk)
                for chunk in partition
            )

    raise TotalOptimizationError(
        f"Les marchandises du client « {client} » ne tiennent pas dans un seul véhicule « {vehicle.name} » "
        f"et aucun découpage chargeable n’a été trouvé avec les {max_vehicles} véhicule(s) disponibles. "
        "Vérifiez le véhicule sélectionné, ses dimensions, sa charge utile et les marges de sécurité."
    )


def _job_source_ids(job: Mapping[str, Any]) -> tuple[str, ...]:
    raw = job.get("item_ids") or [job.get("reference") or job.get("id")]
    return tuple(str(value).strip() for value in raw if str(value or "").strip())


def _expand_matrix(raw: Any, original_job_count: int, job_origins: list[int]) -> Any:
    """Duplicate pickup/delivery rows for synthetic lots when a matrix was supplied."""
    if not isinstance(raw, list):
        return raw
    original_size = 1 + 2 * original_job_count
    expanded_size = 1 + 2 * len(job_origins)
    if len(raw) == expanded_size:
        return raw
    if len(raw) != original_size or any(not isinstance(row, list) or len(row) != original_size for row in raw):
        return raw

    physical_indices = [0]
    for original_index in job_origins:
        physical_indices.extend((1 + 2 * original_index, 2 + 2 * original_index))
    return [
        [raw[source][target] for target in physical_indices]
        for source in physical_indices
    ]


def _copy_rows_for_chunk(
    *,
    chunk: tuple[CargoItem, ...],
    raw_items: dict[str, dict[str, Any]],
    job_index: int,
    lot_index: int,
    lot_count: int,
    lot_client: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    counts = Counter(item.source_id for item in chunk)
    rows: list[dict[str, Any]] = []
    synthetic_ids: list[str] = []
    for source_index, (source_id, quantity) in enumerate(sorted(counts.items())):
        raw = copy.deepcopy(raw_items[source_id])
        synthetic_id = f"{source_id}__job{job_index + 1}_lot{lot_index + 1}_{source_index + 1}"
        raw["id"] = synthetic_id
        raw["quantity"] = quantity
        raw["destination"] = lot_client
        rows.append(raw)
        synthetic_ids.append(synthetic_id)
    return rows, synthetic_ids


def prepare_total_payload(
    payload: dict[str, Any],
    catalog: tuple[VehicleVersion, ...],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Prepare split-delivery lots only for clients that cannot fit in one vehicle."""
    prepared = copy.deepcopy(payload)
    loading = prepared.get("loading")
    route = prepared.get("route")
    if not isinstance(loading, dict) or not isinstance(route, dict):
        return prepared, []
    jobs = route.get("jobs")
    raw_loading_items = loading.get("items")
    if not isinstance(jobs, list) or not jobs or not isinstance(raw_loading_items, list):
        return prepared, []

    problem = normalize_payload(loading, requested_solutions=1, catalog=catalog)
    if len(problem.vehicles) != 1:
        return prepared, []
    vehicle = problem.vehicles[0]
    max_vehicles = max(1, int(loading.get("vehicle_policy", {}).get("max_vehicles") or 1))

    global_lower_bound = estimate_vehicle_lower_bound(problem.items, vehicle)
    if global_lower_bound > max_vehicles:
        total_weight = sum(item.weight_kg for item in problem.items)
        raise TotalOptimizationError(
            f"L’ensemble du chargement nécessite au minimum {global_lower_bound} véhicule(s) « {vehicle.name} » "
            f"selon la surface au sol et le poids ({total_weight:.0f} kg), mais seulement {max_vehicles} sont disponibles."
        )

    raw_by_id = {
        str(item.get("id") or "").strip(): copy.deepcopy(item)
        for item in raw_loading_items
        if isinstance(item, Mapping) and str(item.get("id") or "").strip()
    }
    expanded_by_source: dict[str, list[CargoItem]] = defaultdict(list)
    for item in problem.items:
        expanded_by_source[item.source_id].append(item)

    requested_seconds = float(payload.get("time_limit_s") or loading.get("budget_seconds") or 30.0)
    preparation_seconds = min(8.0, max(2.0, requested_seconds * 0.25))
    deadline = time.perf_counter() + preparation_seconds

    split_sources: set[str] = set()
    synthetic_rows: list[dict[str, Any]] = []
    prepared_jobs: list[dict[str, Any]] = []
    job_origins: list[int] = []
    split_summary: list[dict[str, Any]] = []

    for job_index, raw_job in enumerate(jobs):
        if not isinstance(raw_job, Mapping):
            prepared_jobs.append(copy.deepcopy(raw_job))
            job_origins.append(job_index)
            continue
        source_ids = _job_source_ids(raw_job)
        unknown = [source_id for source_id in source_ids if source_id not in expanded_by_source or source_id not in raw_by_id]
        if unknown:
            raise TotalOptimizationError("Référence de marchandise inconnue : " + ", ".join(unknown))
        client = str(raw_job.get("client") or raw_job.get("destination") or f"Client {job_index + 1}").strip()
        client_items = tuple(item for source_id in source_ids for item in expanded_by_source[source_id])

        remaining_original_jobs = len(jobs) - job_index - 1
        current_nodes = len(prepared_jobs)
        max_chunks = min(
            len(client_items),
            _MAX_TOTAL_ROUTE_NODES - current_nodes - remaining_original_jobs,
        )
        chunks = _partition_oversized_client(
            client=client,
            items=client_items,
            vehicle=vehicle,
            max_vehicles=max_vehicles,
            max_chunks=max_chunks,
            seed=int(loading.get("seed") or payload.get("seed") or 1) + job_index * 401,
            deadline=deadline,
        )

        if len(chunks) == 1:
            prepared_jobs.append(copy.deepcopy(dict(raw_job)))
            job_origins.append(job_index)
            continue

        split_sources.update(source_ids)
        split_summary.append({
            "client": client,
            "lot_count": len(chunks),
            "quantity": len(client_items),
            "weight_kg": sum(item.weight_kg for item in client_items),
        })
        for lot_index, chunk in enumerate(chunks):
            lot_client = f"{client} · lot {lot_index + 1}/{len(chunks)}"
            rows, synthetic_ids = _copy_rows_for_chunk(
                chunk=chunk,
                raw_items=raw_by_id,
                job_index=job_index,
                lot_index=lot_index,
                lot_count=len(chunks),
                lot_client=lot_client,
            )
            synthetic_rows.extend(rows)
            job = copy.deepcopy(dict(raw_job))
            job["id"] = f"{raw_job.get('id') or f'JOB-{job_index + 1}'}-LOT-{lot_index + 1}"
            job["client"] = lot_client
            job["original_client"] = client
            job["item_ids"] = synthetic_ids
            job["reference"] = ", ".join(synthetic_ids)
            job["quantity"] = len(chunk)
            job["weight_kg"] = sum(item.weight_kg for item in chunk)
            prepared_jobs.append(job)
            job_origins.append(job_index)

    if len(prepared_jobs) > _MAX_TOTAL_ROUTE_NODES:
        raise TotalOptimizationError(
            f"Le découpage des chargements produit {len(prepared_jobs)} lots, au-delà de la limite de "
            f"{_MAX_TOTAL_ROUTE_NODES} lots par optimisation totale."
        )

    untouched_rows = [
        copy.deepcopy(item)
        for item in raw_loading_items
        if isinstance(item, Mapping) and str(item.get("id") or "").strip() not in split_sources
    ]
    loading["items"] = untouched_rows + synthetic_rows
    route["jobs"] = prepared_jobs
    route["distance_matrix_m"] = _expand_matrix(route.get("distance_matrix_m"), len(jobs), job_origins)
    route["duration_matrix_s"] = _expand_matrix(route.get("duration_matrix_s"), len(jobs), job_origins)
    return prepared, split_summary


def optimise_total_prepared(
    payload: dict[str, Any],
    catalog: tuple[VehicleVersion, ...],
) -> dict[str, Any]:
    prepared, split_summary = prepare_total_payload(payload, catalog)
    result = optimise_total(prepared, catalog)
    if not split_summary:
        return result

    result["split_clients"] = split_summary
    split_note = (
        " Les clients qui ne pouvaient pas tenir physiquement dans un seul véhicule ont été découpés en lots "
        "indivisibles. ALNS et le décodeur génétique peuvent recombiner ces lots avec les clients proches afin "
        "de minimiser le nombre réel de camions."
    )
    result["model_note"] = str(result.get("model_note") or "") + split_note
    warning = "Découpage nécessaire : " + "; ".join(
        f"{entry['client']} en {entry['lot_count']} lots"
        for entry in split_summary
    )
    for solution in result.get("solutions", []):
        solution.setdefault("warnings", []).append(warning)
    return result
