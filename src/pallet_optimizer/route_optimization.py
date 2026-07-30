from __future__ import annotations

import json
import math
import os
import random
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable, Sequence


EARTH_RADIUS_M = 6_371_008.8
DEFAULT_OSRM_URL = os.getenv("AXIOLOAD_OSRM_URL", "https://router.project-osrm.org").rstrip("/")
DEFAULT_NOMINATIM_URL = os.getenv(
    "AXIOLOAD_NOMINATIM_URL", "https://nominatim.openstreetmap.org"
).rstrip("/")
USER_AGENT = "AxioLoad/0.10 route-planning (local application)"


class RouteInputError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Point:
    lat: float
    lon: float
    label: str = ""


@dataclass(frozen=True, slots=True)
class RouteJob:
    id: str
    client: str
    reference: str
    pickup: Point
    delivery: Point
    weight_kg: float = 0.0
    quantity: int = 1
    unit_type: str = "unité"


@dataclass(frozen=True, slots=True)
class MatrixData:
    distances_m: tuple[tuple[float, ...], ...]
    durations_s: tuple[tuple[float, ...], ...]
    provider: str
    warning: str | None = None


def _json_request(url: str, *, timeout: float = 15.0) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - configured public services
        return json.loads(response.read().decode("utf-8"))


def geocode(query: str, *, limit: int = 5) -> list[dict[str, Any]]:
    query = query.strip()
    if len(query) < 3:
        raise RouteInputError("L’adresse doit contenir au moins trois caractères.")
    params = urllib.parse.urlencode(
        {
            "q": query,
            "format": "jsonv2",
            "limit": max(1, min(int(limit), 8)),
            "addressdetails": 1,
            "countrycodes": os.getenv("AXIOLOAD_GEOCODE_COUNTRIES", "fr,be,nl,de,es,it,lu,ch"),
        }
    )
    payload = _json_request(f"{DEFAULT_NOMINATIM_URL}/search?{params}")
    return [
        {
            "display_name": item.get("display_name", query),
            "lat": float(item["lat"]),
            "lon": float(item["lon"]),
            "type": item.get("type", ""),
        }
        for item in payload
        if "lat" in item and "lon" in item
    ]


def haversine_m(a: Point, b: Point) -> float:
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    d_lat = lat2 - lat1
    d_lon = math.radians(b.lon - a.lon)
    h = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def _fallback_matrix(points: Sequence[Point]) -> MatrixData:
    # A road correction factor gives a more realistic estimate than pure great-circle
    # distance while keeping the route tab usable if OSRM is temporarily unavailable.
    road_factor = 1.28
    speed_m_s = 50_000 / 3_600
    distances = []
    durations = []
    for origin in points:
        distance_row = []
        duration_row = []
        for destination in points:
            distance = 0.0 if origin == destination else haversine_m(origin, destination) * road_factor
            distance_row.append(distance)
            duration_row.append(distance / speed_m_s if distance else 0.0)
        distances.append(tuple(distance_row))
        durations.append(tuple(duration_row))
    return MatrixData(
        tuple(distances),
        tuple(durations),
        "estimation géodésique locale",
        "Le service routier OSRM était indisponible. Les distances sont estimées à vol d’oiseau avec un coefficient routier de 1,28.",
    )


def road_matrix(points: Sequence[Point]) -> MatrixData:
    if len(points) < 2:
        raise RouteInputError("Au moins deux points sont requis pour calculer un itinéraire.")
    if len(points) > 80:
        raise RouteInputError(
            "La version utilisant le service OSRM public est limitée à 80 points physiques. "
            "Pour des volumes supérieurs, configurez une instance OSRM dédiée."
        )
    coordinates = ";".join(f"{point.lon:.7f},{point.lat:.7f}" for point in points)
    params = urllib.parse.urlencode({"annotations": "distance,duration"})
    url = f"{DEFAULT_OSRM_URL}/table/v1/driving/{coordinates}?{params}"
    try:
        payload = _json_request(url, timeout=20.0)
        if payload.get("code") != "Ok":
            raise RuntimeError(payload.get("message") or payload.get("code") or "Réponse OSRM invalide")
        raw_distances = payload.get("distances")
        raw_durations = payload.get("durations")
        if not raw_distances or not raw_durations:
            raise RuntimeError("La matrice OSRM est incomplète")
        if any(value is None for row in raw_distances for value in row):
            raise RuntimeError("Certains points ne sont pas reliés par le réseau routier")
        distances = tuple(tuple(float(value) for value in row) for row in raw_distances)
        durations = tuple(tuple(float(value) for value in row) for row in raw_durations)
        return MatrixData(distances, durations, "OSRM / OpenStreetMap")
    except Exception:
        return _fallback_matrix(points)


def route_geometry(points: Sequence[Point]) -> tuple[list[list[float]], float, float, str, str | None]:
    if len(points) < 2:
        return [[point.lat, point.lon] for point in points], 0.0, 0.0, "local", None
    coordinates = ";".join(f"{point.lon:.7f},{point.lat:.7f}" for point in points)
    params = urllib.parse.urlencode(
        {
            "overview": "full",
            "geometries": "geojson",
            "steps": "false",
            "annotations": "false",
        }
    )
    url = f"{DEFAULT_OSRM_URL}/route/v1/driving/{coordinates}?{params}"
    try:
        payload = _json_request(url, timeout=25.0)
        if payload.get("code") != "Ok" or not payload.get("routes"):
            raise RuntimeError(payload.get("message") or "Aucun tracé OSRM")
        route = payload["routes"][0]
        geometry = [
            [float(lat), float(lon)]
            for lon, lat in route["geometry"]["coordinates"]
        ]
        return geometry, float(route["distance"]), float(route["duration"]), "OSRM / OpenStreetMap", None
    except Exception:
        matrix = _fallback_matrix(points)
        distance = sum(matrix.distances_m[idx][idx + 1] for idx in range(len(points) - 1))
        duration = sum(matrix.durations_s[idx][idx + 1] for idx in range(len(points) - 1))
        return (
            [[point.lat, point.lon] for point in points],
            distance,
            duration,
            matrix.provider,
            matrix.warning,
        )


def _as_point(raw: Any, field: str) -> Point:
    try:
        lat = float(raw["lat"])
        lon = float(raw["lon"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RouteInputError(f"Coordonnées invalides pour {field}.") from exc
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise RouteInputError(f"Coordonnées hors limites pour {field}.")
    return Point(lat, lon, str(raw.get("label") or raw.get("address") or field))


def parse_problem(payload: dict[str, Any]) -> tuple[Point, list[RouteJob], dict[str, Any]]:
    depot = _as_point(payload.get("depot") or {}, "le point de départ")
    raw_jobs = payload.get("jobs")
    if not isinstance(raw_jobs, list) or not raw_jobs:
        raise RouteInputError("Ajoutez au moins une marchandise avec un enlèvement et une livraison.")
    if len(raw_jobs) > 500:
        raise RouteInputError("La limite de cette version est fixée à 500 missions par calcul.")
    jobs: list[RouteJob] = []
    identifiers: set[str] = set()
    for index, raw in enumerate(raw_jobs):
        if not isinstance(raw, dict):
            raise RouteInputError(f"La mission {index + 1} est invalide.")
        identifier = str(raw.get("id") or f"JOB-{index + 1:03d}").strip()
        if not identifier:
            raise RouteInputError(f"La mission {index + 1} doit avoir un identifiant.")
        if identifier in identifiers:
            raise RouteInputError(f"L’identifiant {identifier} est présent plusieurs fois.")
        identifiers.add(identifier)
        pickup = _as_point(raw.get("pickup") or {}, f"l’enlèvement de {identifier}")
        delivery = _as_point(raw.get("delivery") or {}, f"la livraison de {identifier}")
        try:
            weight = max(0.0, float(raw.get("weight_kg") or 0.0))
        except (TypeError, ValueError) as exc:
            raise RouteInputError(f"Poids invalide pour {identifier}.") from exc
        try:
            raw_quantity = raw.get("quantity", 1)
            quantity = max(0, int(1 if raw_quantity in (None, "") else raw_quantity))
        except (TypeError, ValueError) as exc:
            raise RouteInputError(f"Quantité invalide pour {identifier}.") from exc
        unit_type = str(raw.get("unit_type") or "unité").strip().lower()
        if unit_type not in {"palette", "colis", "unité", "unités mixtes"}:
            unit_type = "unité"
        jobs.append(
            RouteJob(
                identifier,
                str(raw.get("client") or identifier).strip(),
                str(raw.get("reference") or identifier).strip(),
                pickup,
                delivery,
                weight,
                quantity,
                unit_type,
            )
        )
    settings = {
        "method": str(payload.get("method") or "hgs").lower(),
        "return_to_depot": bool(payload.get("return_to_depot", True)),
        "time_limit_s": min(60.0, max(0.2, float(payload.get("time_limit_s") or 5.0))),
        "seed": int(payload.get("seed") or 1),
        "capacity_kg": max(0.0, float(payload.get("capacity_kg") or 0.0)),
    }
    if settings["method"] not in {"hgs", "alns"}:
        raise RouteInputError("Méthode inconnue. Utilisez « hgs » ou « alns ».")
    if settings["capacity_kg"]:
        too_heavy = [job.id for job in jobs if job.weight_kg > settings["capacity_kg"] + 1e-9]
        if too_heavy:
            raise RouteInputError(
                "Le poids d’une mission dépasse la capacité du véhicule : " + ", ".join(too_heavy)
            )
    return depot, jobs, settings


def physical_points(depot: Point, jobs: Sequence[RouteJob]) -> list[Point]:
    points = [depot]
    for job in jobs:
        points.extend((job.pickup, job.delivery))
    return points


def job_cost_matrix(
    physical: MatrixData,
    jobs: Sequence[RouteJob],
    *,
    return_to_depot: bool,
) -> tuple[tuple[float, ...], ...]:
    size = len(jobs) + 1
    matrix = [[0.0] * size for _ in range(size)]
    for target in range(len(jobs)):
        pickup_target = 1 + 2 * target
        delivery_target = pickup_target + 1
        matrix[0][target + 1] = (
            physical.distances_m[0][pickup_target]
            + physical.distances_m[pickup_target][delivery_target]
        )
    for source in range(len(jobs)):
        delivery_source = 2 + 2 * source
        matrix[source + 1][0] = physical.distances_m[delivery_source][0] if return_to_depot else 0.0
        for target in range(len(jobs)):
            if source == target:
                continue
            pickup_target = 1 + 2 * target
            delivery_target = pickup_target + 1
            matrix[source + 1][target + 1] = (
                physical.distances_m[delivery_source][pickup_target]
                + physical.distances_m[pickup_target][delivery_target]
            )
    return tuple(tuple(row) for row in matrix)


def route_cost(order: Sequence[int], matrix: Sequence[Sequence[float]]) -> float:
    if not order:
        return 0.0
    total = matrix[0][order[0] + 1]
    total += sum(matrix[a + 1][b + 1] for a, b in zip(order, order[1:]))
    total += matrix[order[-1] + 1][0]
    return float(total)


def nearest_neighbour(matrix: Sequence[Sequence[float]]) -> list[int]:
    unvisited = set(range(len(matrix) - 1))
    order: list[int] = []
    current = 0
    while unvisited:
        next_job = min(unvisited, key=lambda job: (matrix[current][job + 1], job))
        order.append(next_job)
        unvisited.remove(next_job)
        current = next_job + 1
    return order


def improve_order(order: Sequence[int], matrix: Sequence[Sequence[float]]) -> list[int]:
    best = list(order)
    best_cost = route_cost(best, matrix)
    improved = True
    passes = 0
    while improved and passes < 4:
        improved = False
        passes += 1
        # Relocate one mission.
        for source in range(len(best)):
            node = best[source]
            reduced = best[:source] + best[source + 1 :]
            for target in range(len(best)):
                candidate = reduced[:target] + [node] + reduced[target:]
                candidate_cost = route_cost(candidate, matrix)
                if candidate_cost + 1e-6 < best_cost:
                    best, best_cost, improved = candidate, candidate_cost, True
                    break
            if improved:
                break
        if improved:
            continue
        # Reverse a subsequence (2-opt-like for the asymmetric job graph).
        for left in range(len(best) - 1):
            for right in range(left + 2, len(best) + 1):
                candidate = best[:left] + list(reversed(best[left:right])) + best[right:]
                candidate_cost = route_cost(candidate, matrix)
                if candidate_cost + 1e-6 < best_cost:
                    best, best_cost, improved = candidate, candidate_cost, True
                    break
            if improved:
                break
    return best


def _order_crossover(parent_a: Sequence[int], parent_b: Sequence[int], rng: random.Random) -> list[int]:
    length = len(parent_a)
    if length < 2:
        return list(parent_a)
    left, right = sorted(rng.sample(range(length), 2))
    right += 1
    child: list[int | None] = [None] * length
    child[left:right] = parent_a[left:right]
    remaining = [gene for gene in parent_b if gene not in child]
    positions = [idx for idx, gene in enumerate(child) if gene is None]
    for position, gene in zip(positions, remaining):
        child[position] = gene
    return [int(gene) for gene in child]


def _mutate(order: list[int], rng: random.Random) -> list[int]:
    mutated = list(order)
    if len(mutated) < 2:
        return mutated
    operation = rng.choice(("swap", "reverse", "relocate"))
    a, b = sorted(rng.sample(range(len(mutated)), 2))
    if operation == "swap":
        mutated[a], mutated[b] = mutated[b], mutated[a]
    elif operation == "reverse":
        mutated[a : b + 1] = reversed(mutated[a : b + 1])
    else:
        node = mutated.pop(b)
        mutated.insert(a, node)
    return mutated


def _hgs_fallback(
    matrix: Sequence[Sequence[float]], *, time_limit_s: float, seed: int
) -> tuple[list[int], int, str]:
    rng = random.Random(seed)
    n_jobs = len(matrix) - 1
    base = improve_order(nearest_neighbour(matrix), matrix)
    population_size = max(12, min(60, n_jobs * 4))
    population: list[list[int]] = [base]
    while len(population) < population_size:
        candidate = list(range(n_jobs))
        rng.shuffle(candidate)
        population.append(improve_order(candidate, matrix))
    deadline = overall_deadline
    iterations = 0
    while time.perf_counter() < deadline:
        ranked = sorted(population, key=lambda order: route_cost(order, matrix))
        elite_size = max(2, population_size // 5)
        elite = ranked[:elite_size]
        next_population = [list(order) for order in elite]
        signatures = {tuple(order) for order in next_population}
        while len(next_population) < population_size and time.perf_counter() < deadline:
            parent_a = rng.choice(elite)
            parent_b = rng.choice(ranked[: max(elite_size + 2, population_size // 2)])
            child = _order_crossover(parent_a, parent_b, rng)
            if rng.random() < 0.75:
                child = _mutate(child, rng)
            child = improve_order(child, matrix)
            signature = tuple(child)
            if signature not in signatures or rng.random() < 0.08:
                next_population.append(child)
                signatures.add(signature)
            iterations += 1
        population = next_population or ranked
    best = min(population, key=lambda order: route_cost(order, matrix))
    return best, iterations, "HGS intégré (génétique + recherche locale)"


def solve_hgs(
    matrix: Sequence[Sequence[float]], *, time_limit_s: float, seed: int
) -> tuple[list[int], int, str, str | None]:
    try:
        import pyvrp  # type: ignore
        from pyvrp.stop import MaxRuntime  # type: ignore

        model = pyvrp.Model()
        depot = model.add_depot(x=0, y=0, name="Départ")
        clients = [model.add_client(x=index + 1, y=0, name=f"Mission {index + 1}") for index in range(len(matrix) - 1)]
        model.add_vehicle_type(1, start_depot=depot, end_depot=depot)
        locations = [depot, *clients]
        for source_idx, source in enumerate(locations):
            for target_idx, target in enumerate(locations):
                if source_idx == target_idx:
                    continue
                model.add_edge(
                    source,
                    target,
                    distance=max(0, int(round(matrix[source_idx][target_idx]))),
                )
        result = model.solve(stop=MaxRuntime(time_limit_s), seed=seed, display=False)
        best_routes = result.best.routes()
        if not best_routes:
            raise RuntimeError("PyVRP n’a retourné aucune tournée")
        route = best_routes[0]
        order: list[int] = []
        if hasattr(route, "visits"):
            visits = list(route.visits())
            # PyVRP uses global location indices: depot first, then clients.
            order = [int(visit) - 1 for visit in visits if int(visit) > 0]
        if not order:
            for activity in route:
                if getattr(activity, "is_depot", lambda: False)():
                    continue
                order.append(int(activity.idx))
        if sorted(order) != list(range(len(matrix) - 1)):
            raise RuntimeError("Ordre PyVRP incomplet")
        iterations = int(getattr(result, "num_iterations", 0) or 0)
        return order, iterations, "PyVRP HGS", None
    except Exception as exc:
        order, iterations, engine = _hgs_fallback(matrix, time_limit_s=time_limit_s, seed=seed)
        warning = (
            "PyVRP n’est pas disponible dans cet environnement ou n’a pas pu résoudre ce cas. "
            "AxioLoad a utilisé son moteur HGS intégré compatible avec le même modèle de missions. "
            f"Détail technique : {type(exc).__name__}."
        )
        return order, iterations, engine, warning


def _greedy_insert(partial: Sequence[int], removed: Iterable[int], matrix: Sequence[Sequence[float]]) -> list[int]:
    route = list(partial)
    remaining = list(removed)
    while remaining:
        best: tuple[float, int, int] | None = None
        for job in remaining:
            for position in range(len(route) + 1):
                candidate = route[:position] + [job] + route[position:]
                score = route_cost(candidate, matrix)
                proposal = (score, job, position)
                if best is None or proposal < best:
                    best = proposal
        assert best is not None
        _, job, position = best
        route.insert(position, job)
        remaining.remove(job)
    return route


def _regret_insert(partial: Sequence[int], removed: Iterable[int], matrix: Sequence[Sequence[float]]) -> list[int]:
    route = list(partial)
    remaining = list(removed)
    while remaining:
        selected: tuple[float, int, int] | None = None
        for job in remaining:
            options: list[tuple[float, int]] = []
            for position in range(len(route) + 1):
                candidate = route[:position] + [job] + route[position:]
                options.append((route_cost(candidate, matrix), position))
            options.sort()
            regret = (options[1][0] - options[0][0]) if len(options) > 1 else 1e12
            proposal = (-regret, job, options[0][1])
            if selected is None or proposal < selected:
                selected = proposal
        assert selected is not None
        _, job, position = selected
        route.insert(position, job)
        remaining.remove(job)
    return route


def _destroy_random(order: Sequence[int], count: int, rng: random.Random, _matrix: Sequence[Sequence[float]]) -> tuple[list[int], list[int]]:
    removed = rng.sample(list(order), min(count, len(order)))
    removed_set = set(removed)
    return [job for job in order if job not in removed_set], removed


def _destroy_worst(order: Sequence[int], count: int, rng: random.Random, matrix: Sequence[Sequence[float]]) -> tuple[list[int], list[int]]:
    baseline = route_cost(order, matrix)
    savings = []
    for position, job in enumerate(order):
        reduced = list(order[:position]) + list(order[position + 1 :])
        savings.append((baseline - route_cost(reduced, matrix), rng.random(), job))
    savings.sort(reverse=True)
    removed = [entry[2] for entry in savings[:count]]
    removed_set = set(removed)
    return [job for job in order if job not in removed_set], removed


def _destroy_related(order: Sequence[int], count: int, rng: random.Random, matrix: Sequence[Sequence[float]]) -> tuple[list[int], list[int]]:
    if not order:
        return [], []
    seed_job = rng.choice(list(order))
    related = sorted(
        order,
        key=lambda job: matrix[seed_job + 1][job + 1] + matrix[job + 1][seed_job + 1],
    )
    removed = related[:count]
    removed_set = set(removed)
    return [job for job in order if job not in removed_set], list(removed)


def solve_alns(
    matrix: Sequence[Sequence[float]], *, time_limit_s: float, seed: int
) -> tuple[list[int], int, str]:
    rng = random.Random(seed)
    current = improve_order(nearest_neighbour(matrix), matrix)
    current_cost = route_cost(current, matrix)
    best = list(current)
    best_cost = current_cost
    destroy_ops = (_destroy_random, _destroy_worst, _destroy_related)
    repair_ops = (_greedy_insert, _regret_insert)
    destroy_weights = [1.0] * len(destroy_ops)
    repair_weights = [1.0] * len(repair_ops)
    destroy_scores = [0.0] * len(destroy_ops)
    repair_scores = [0.0] * len(repair_ops)
    destroy_uses = [0] * len(destroy_ops)
    repair_uses = [0] * len(repair_ops)
    deadline = time.perf_counter() + time_limit_s
    temperature = max(1.0, current_cost * 0.025)
    cooling = 0.997
    iterations = 0
    segment = 40
    while time.perf_counter() < deadline:
        destroy_idx = rng.choices(range(len(destroy_ops)), weights=destroy_weights, k=1)[0]
        repair_idx = rng.choices(range(len(repair_ops)), weights=repair_weights, k=1)[0]
        removal_ratio = rng.uniform(0.1, 0.3)
        count = max(1, min(len(current), round(len(current) * removal_ratio)))
        partial, removed = destroy_ops[destroy_idx](current, count, rng, matrix)
        candidate = repair_ops[repair_idx](partial, removed, matrix)
        if rng.random() < 0.45:
            candidate = improve_order(candidate, matrix)
        candidate_cost = route_cost(candidate, matrix)
        delta = candidate_cost - current_cost
        accepted = delta <= 0 or rng.random() < math.exp(-delta / max(temperature, 1e-9))
        reward = 0.0
        if candidate_cost + 1e-6 < best_cost:
            best, best_cost = list(candidate), candidate_cost
            reward = 8.0
        elif candidate_cost + 1e-6 < current_cost:
            reward = 4.0
        elif accepted:
            reward = 1.0
        if accepted:
            current, current_cost = candidate, candidate_cost
        destroy_scores[destroy_idx] += reward
        repair_scores[repair_idx] += reward
        destroy_uses[destroy_idx] += 1
        repair_uses[repair_idx] += 1
        iterations += 1
        temperature *= cooling
        if iterations % segment == 0:
            reaction = 0.25
            for idx in range(len(destroy_ops)):
                performance = destroy_scores[idx] / max(1, destroy_uses[idx])
                destroy_weights[idx] = max(0.15, (1 - reaction) * destroy_weights[idx] + reaction * performance)
                destroy_scores[idx] = 0.0
                destroy_uses[idx] = 0
            for idx in range(len(repair_ops)):
                performance = repair_scores[idx] / max(1, repair_uses[idx])
                repair_weights[idx] = max(0.15, (1 - reaction) * repair_weights[idx] + reaction * performance)
                repair_scores[idx] = 0.0
                repair_uses[idx] = 0
            if current_cost > best_cost * 1.08:
                current, current_cost = list(best), best_cost
    return best, iterations, "ALNS adaptatif intégré"



Stop = tuple[int, int]  # (job index, 0 = pickup, 1 = delivery)


def stop_physical_index(stop: Stop) -> int:
    job_index, stop_type = stop
    return 1 + 2 * job_index + stop_type


def stop_sequence_cost(
    sequence: Sequence[Stop],
    physical: MatrixData,
    *,
    return_to_depot: bool,
) -> float:
    previous = 0
    total = 0.0
    for stop in sequence:
        current = stop_physical_index(stop)
        total += physical.distances_m[previous][current]
        previous = current
    if sequence and return_to_depot:
        total += physical.distances_m[previous][0]
    return total


def stop_sequence_feasible(
    sequence: Sequence[Stop], jobs: Sequence[RouteJob], capacity_kg: float
) -> bool:
    picked: set[int] = set()
    delivered: set[int] = set()
    load = 0.0
    capacity = capacity_kg if capacity_kg > 0 else math.inf
    for job_index, stop_type in sequence:
        if not (0 <= job_index < len(jobs)):
            return False
        if stop_type == 0:
            if job_index in picked:
                return False
            picked.add(job_index)
            load += jobs[job_index].weight_kg
            if load > capacity + 1e-9:
                return False
        elif stop_type == 1:
            if job_index not in picked or job_index in delivered:
                return False
            delivered.add(job_index)
            load -= jobs[job_index].weight_kg
            if load < -1e-9:
                return False
        else:
            return False
    return (
        len(picked) == len(jobs)
        and len(delivered) == len(jobs)
        and abs(load) <= 1e-6
    )


def _remove_job_pair(sequence: Sequence[Stop], job_index: int) -> list[Stop]:
    return [stop for stop in sequence if stop[0] != job_index]


def best_pair_insertion(
    sequence: Sequence[Stop],
    job_index: int,
    physical: MatrixData,
    jobs: Sequence[RouteJob],
    *,
    capacity_kg: float,
    return_to_depot: bool,
) -> tuple[list[Stop], float]:
    base = _remove_job_pair(sequence, job_index)
    best_sequence: list[Stop] | None = None
    best_cost = math.inf
    for pickup_position in range(len(base) + 1):
        with_pickup = base[:pickup_position] + [(job_index, 0)] + base[pickup_position:]
        for delivery_position in range(pickup_position + 1, len(with_pickup) + 1):
            candidate = (
                with_pickup[:delivery_position]
                + [(job_index, 1)]
                + with_pickup[delivery_position:]
            )
            # During partial construction, feasibility only needs to hold for inserted jobs.
            partial_jobs = {stop[0] for stop in candidate}
            picked: set[int] = set()
            delivered: set[int] = set()
            load = 0.0
            capacity = capacity_kg if capacity_kg > 0 else math.inf
            feasible = True
            for candidate_job, stop_type in candidate:
                if stop_type == 0:
                    if candidate_job in picked:
                        feasible = False
                        break
                    picked.add(candidate_job)
                    load += jobs[candidate_job].weight_kg
                    if load > capacity + 1e-9:
                        feasible = False
                        break
                else:
                    if candidate_job not in picked or candidate_job in delivered:
                        feasible = False
                        break
                    delivered.add(candidate_job)
                    load -= jobs[candidate_job].weight_kg
            if not feasible or picked != partial_jobs or delivered != partial_jobs:
                continue
            cost = stop_sequence_cost(candidate, physical, return_to_depot=return_to_depot)
            if cost + 1e-9 < best_cost:
                best_sequence, best_cost = candidate, cost
    if best_sequence is None:
        raise RouteInputError(
            f"La mission {jobs[job_index].id} ne peut pas être insérée sans dépasser la capacité du véhicule."
        )
    return best_sequence, best_cost


def decode_job_order(
    order: Sequence[int],
    physical: MatrixData,
    jobs: Sequence[RouteJob],
    *,
    capacity_kg: float,
    return_to_depot: bool,
) -> list[Stop]:
    sequence: list[Stop] = []
    for job_index in order:
        sequence, _ = best_pair_insertion(
            sequence,
            job_index,
            physical,
            jobs,
            capacity_kg=capacity_kg,
            return_to_depot=return_to_depot,
        )
    return sequence


def improve_job_order_for_pairs(
    order: Sequence[int],
    physical: MatrixData,
    jobs: Sequence[RouteJob],
    *,
    capacity_kg: float,
    return_to_depot: bool,
    max_passes: int = 3,
) -> list[int]:
    cache: dict[tuple[int, ...], float] = {}

    def cost(candidate: Sequence[int]) -> float:
        key = tuple(candidate)
        if key not in cache:
            sequence = decode_job_order(
                candidate,
                physical,
                jobs,
                capacity_kg=capacity_kg,
                return_to_depot=return_to_depot,
            )
            cache[key] = stop_sequence_cost(
                sequence, physical, return_to_depot=return_to_depot
            )
        return cache[key]

    best = list(order)
    best_cost = cost(best)
    for _ in range(max_passes):
        improved = False
        for source in range(len(best)):
            node = best[source]
            reduced = best[:source] + best[source + 1 :]
            for target in range(len(best)):
                candidate = reduced[:target] + [node] + reduced[target:]
                candidate_cost = cost(candidate)
                if candidate_cost + 1e-6 < best_cost:
                    best, best_cost, improved = candidate, candidate_cost, True
                    break
            if improved:
                break
        if not improved:
            for left in range(len(best) - 1):
                for right in range(left + 2, len(best) + 1):
                    candidate = best[:left] + list(reversed(best[left:right])) + best[right:]
                    candidate_cost = cost(candidate)
                    if candidate_cost + 1e-6 < best_cost:
                        best, best_cost, improved = candidate, candidate_cost, True
                        break
                if improved:
                    break
        if not improved:
            break
    return best


def _pyvrp_seed_order(
    matrix: Sequence[Sequence[float]], *, time_limit_s: float, seed: int
) -> tuple[list[int] | None, str | None]:
    try:
        import pyvrp  # type: ignore
        from pyvrp.stop import MaxRuntime  # type: ignore

        model = pyvrp.Model()
        depot = model.add_depot(x=0, y=0, name="Départ")
        clients = [
            model.add_client(x=index + 1, y=0, name=f"Mission {index + 1}")
            for index in range(len(matrix) - 1)
        ]
        model.add_vehicle_type(1, start_depot=depot, end_depot=depot)
        locations = [depot, *clients]
        for source_idx, source in enumerate(locations):
            for target_idx, target in enumerate(locations):
                if source_idx == target_idx:
                    continue
                model.add_edge(
                    source,
                    target,
                    distance=max(0, int(round(matrix[source_idx][target_idx]))),
                )
        result = model.solve(
            stop=MaxRuntime(max(0.1, time_limit_s)), seed=seed, display=False
        )
        routes = result.best.routes()
        if not routes:
            return None, "PyVRP n’a retourné aucune tournée."
        route = routes[0]
        if hasattr(route, "visits"):
            visits = [int(visit) for visit in route.visits()]
            order = [visit - 1 for visit in visits if visit > 0]
        else:
            order = [
                int(activity.idx)
                for activity in route
                if not getattr(activity, "is_depot", lambda: False)()
            ]
        if sorted(order) != list(range(len(matrix) - 1)):
            return None, "L’ordre PyVRP est incomplet."
        return order, None
    except Exception as exc:
        return None, (
            "PyVRP n’est pas disponible dans cet environnement. "
            f"Le moteur HGS intégré prend le relais ({type(exc).__name__})."
        )


def solve_hgs_pickup_delivery(
    physical: MatrixData,
    jobs: Sequence[RouteJob],
    *,
    capacity_kg: float,
    return_to_depot: bool,
    time_limit_s: float,
    seed: int,
) -> tuple[list[Stop], int, str, str | None]:
    rng = random.Random(seed)
    overall_deadline = time.perf_counter() + time_limit_s
    macro = job_cost_matrix(physical, jobs, return_to_depot=return_to_depot)
    nearest = nearest_neighbour(macro)
    pyvrp_order, pyvrp_warning = _pyvrp_seed_order(
        macro, time_limit_s=min(1.0, time_limit_s * 0.25), seed=seed
    )
    seed_orders = [nearest]
    if pyvrp_order is not None:
        seed_orders.insert(0, pyvrp_order)

    cache: dict[tuple[int, ...], tuple[float, list[Stop]]] = {}

    def evaluate(order: Sequence[int]) -> tuple[float, list[Stop]]:
        key = tuple(order)
        if key not in cache:
            sequence = decode_job_order(
                order,
                physical,
                jobs,
                capacity_kg=capacity_kg,
                return_to_depot=return_to_depot,
            )
            cache[key] = (
                stop_sequence_cost(sequence, physical, return_to_depot=return_to_depot),
                sequence,
            )
        return cache[key]

    population_size = max(12, min(50, len(jobs) * 4))
    population: list[list[int]] = []
    for order in seed_orders:
        population.append(
            improve_job_order_for_pairs(
                order,
                physical,
                jobs,
                capacity_kg=capacity_kg,
                return_to_depot=return_to_depot,
                max_passes=2,
            )
        )
    while len(population) < population_size:
        candidate = list(range(len(jobs)))
        rng.shuffle(candidate)
        population.append(candidate)

    deadline = overall_deadline
    iterations = 0
    while time.perf_counter() < deadline:
        ranked = sorted(population, key=lambda order: evaluate(order)[0])
        elite_size = max(2, population_size // 5)
        elite = ranked[:elite_size]
        next_population = [list(order) for order in elite]
        signatures = {tuple(order) for order in next_population}
        while len(next_population) < population_size and time.perf_counter() < deadline:
            parent_a = rng.choice(elite)
            parent_b = rng.choice(ranked[: max(elite_size + 2, population_size // 2)])
            child = _order_crossover(parent_a, parent_b, rng)
            if rng.random() < 0.78:
                child = _mutate(child, rng)
            if rng.random() < 0.42:
                child = improve_job_order_for_pairs(
                    child,
                    physical,
                    jobs,
                    capacity_kg=capacity_kg,
                    return_to_depot=return_to_depot,
                    max_passes=1,
                )
            signature = tuple(child)
            if signature not in signatures or rng.random() < 0.06:
                next_population.append(child)
                signatures.add(signature)
            iterations += 1
        population = next_population or ranked
    best_order = min(population, key=lambda order: evaluate(order)[0])
    best_sequence = evaluate(best_order)[1]
    engine = (
        "PyVRP HGS + décodeur pickup-delivery"
        if pyvrp_order is not None
        else "HGS intégré (génétique + recherche locale + décodeur pickup-delivery)"
    )
    return best_sequence, iterations, engine, pyvrp_warning


def _pair_remove_jobs(sequence: Sequence[Stop], jobs_to_remove: Iterable[int]) -> tuple[list[Stop], list[int]]:
    removed = list(dict.fromkeys(jobs_to_remove))
    removed_set = set(removed)
    return [stop for stop in sequence if stop[0] not in removed_set], removed


def _pair_destroy_random(
    sequence: Sequence[Stop], count: int, rng: random.Random, _physical: MatrixData, _jobs: Sequence[RouteJob], _return: bool
) -> tuple[list[Stop], list[int]]:
    job_ids = sorted({stop[0] for stop in sequence})
    return _pair_remove_jobs(sequence, rng.sample(job_ids, min(count, len(job_ids))))


def _pair_destroy_worst(
    sequence: Sequence[Stop], count: int, rng: random.Random, physical: MatrixData, jobs: Sequence[RouteJob], return_to_depot: bool
) -> tuple[list[Stop], list[int]]:
    baseline = stop_sequence_cost(sequence, physical, return_to_depot=return_to_depot)
    savings = []
    for job_index in sorted({stop[0] for stop in sequence}):
        reduced = _remove_job_pair(sequence, job_index)
        saving = baseline - stop_sequence_cost(reduced, physical, return_to_depot=return_to_depot)
        savings.append((saving, rng.random(), job_index))
    savings.sort(reverse=True)
    return _pair_remove_jobs(sequence, [item[2] for item in savings[:count]])


def _pair_destroy_related(
    sequence: Sequence[Stop], count: int, rng: random.Random, physical: MatrixData, jobs: Sequence[RouteJob], _return: bool
) -> tuple[list[Stop], list[int]]:
    job_ids = sorted({stop[0] for stop in sequence})
    seed_job = rng.choice(job_ids)
    seed_pickup = 1 + 2 * seed_job
    seed_delivery = seed_pickup + 1
    related = sorted(
        job_ids,
        key=lambda job_index: (
            physical.distances_m[seed_pickup][1 + 2 * job_index]
            + physical.distances_m[seed_delivery][2 + 2 * job_index]
        ),
    )
    return _pair_remove_jobs(sequence, related[:count])


def _pair_greedy_repair(
    sequence: Sequence[Stop], removed: Iterable[int], physical: MatrixData, jobs: Sequence[RouteJob], *, capacity_kg: float, return_to_depot: bool
) -> list[Stop]:
    repaired = list(sequence)
    remaining = list(removed)
    while remaining:
        best: tuple[float, int, list[Stop]] | None = None
        for job_index in remaining:
            candidate, cost = best_pair_insertion(
                repaired,
                job_index,
                physical,
                jobs,
                capacity_kg=capacity_kg,
                return_to_depot=return_to_depot,
            )
            proposal = (cost, job_index, candidate)
            if best is None or proposal[0:2] < best[0:2]:
                best = proposal
        assert best is not None
        _, job_index, repaired = best
        remaining.remove(job_index)
    return repaired


def _pair_regret_repair(
    sequence: Sequence[Stop], removed: Iterable[int], physical: MatrixData, jobs: Sequence[RouteJob], *, capacity_kg: float, return_to_depot: bool
) -> list[Stop]:
    repaired = list(sequence)
    remaining = list(removed)
    while remaining:
        choices: list[tuple[float, int, list[Stop]]] = []
        for job_index in remaining:
            candidates: list[tuple[float, list[Stop]]] = []
            base = _remove_job_pair(repaired, job_index)
            for pickup_position in range(len(base) + 1):
                with_pickup = base[:pickup_position] + [(job_index, 0)] + base[pickup_position:]
                for delivery_position in range(pickup_position + 1, len(with_pickup) + 1):
                    candidate = with_pickup[:delivery_position] + [(job_index, 1)] + with_pickup[delivery_position:]
                    partial_ids = {stop[0] for stop in candidate}
                    if len(partial_ids) != len(candidate) // 2:
                        continue
                    # Complete the missing jobs only for feasibility evaluation.
                    if not stop_sequence_feasible(candidate, [jobs[idx] for idx in range(len(jobs))], capacity_kg):
                        # stop_sequence_feasible expects all jobs, so use a lightweight check here.
                        load = 0.0
                        picked: set[int] = set()
                        feasible = True
                        capacity = capacity_kg if capacity_kg > 0 else math.inf
                        for current_job, stop_type in candidate:
                            if stop_type == 0:
                                picked.add(current_job)
                                load += jobs[current_job].weight_kg
                                if load > capacity + 1e-9:
                                    feasible = False
                                    break
                            elif current_job not in picked:
                                feasible = False
                                break
                            else:
                                load -= jobs[current_job].weight_kg
                        if not feasible:
                            continue
                    candidates.append((stop_sequence_cost(candidate, physical, return_to_depot=return_to_depot), candidate))
            candidates.sort(key=lambda entry: entry[0])
            if not candidates:
                continue
            regret = (candidates[1][0] - candidates[0][0]) if len(candidates) > 1 else 1e12
            choices.append((-regret, job_index, candidates[0][1]))
        if not choices:
            raise RouteInputError("ALNS ne parvient pas à réparer une tournée respectant la capacité.")
        choices.sort(key=lambda entry: (entry[0], entry[1]))
        _, job_index, repaired = choices[0]
        remaining.remove(job_index)
    return repaired


def improve_pair_sequence(
    sequence: Sequence[Stop],
    physical: MatrixData,
    jobs: Sequence[RouteJob],
    *,
    capacity_kg: float,
    return_to_depot: bool,
    max_moves: int = 3,
) -> list[Stop]:
    best = list(sequence)
    best_cost = stop_sequence_cost(best, physical, return_to_depot=return_to_depot)
    for _ in range(max_moves):
        improved = False
        job_order = list(dict.fromkeys(stop[0] for stop in best if stop[1] == 0))
        for job_index in job_order:
            reduced = _remove_job_pair(best, job_index)
            candidate, cost = best_pair_insertion(
                reduced,
                job_index,
                physical,
                jobs,
                capacity_kg=capacity_kg,
                return_to_depot=return_to_depot,
            )
            if cost + 1e-6 < best_cost:
                best, best_cost, improved = candidate, cost, True
                break
        if not improved:
            break
    return best


def solve_alns_pickup_delivery(
    physical: MatrixData,
    jobs: Sequence[RouteJob],
    *,
    capacity_kg: float,
    return_to_depot: bool,
    time_limit_s: float,
    seed: int,
) -> tuple[list[Stop], int, str]:
    rng = random.Random(seed)
    macro = job_cost_matrix(physical, jobs, return_to_depot=return_to_depot)
    current = decode_job_order(
        nearest_neighbour(macro),
        physical,
        jobs,
        capacity_kg=capacity_kg,
        return_to_depot=return_to_depot,
    )
    current = improve_pair_sequence(
        current,
        physical,
        jobs,
        capacity_kg=capacity_kg,
        return_to_depot=return_to_depot,
    )
    current_cost = stop_sequence_cost(current, physical, return_to_depot=return_to_depot)
    best = list(current)
    best_cost = current_cost
    destroy_ops = (_pair_destroy_random, _pair_destroy_worst, _pair_destroy_related)
    repair_ops = (_pair_greedy_repair, _pair_regret_repair)
    destroy_weights = [1.0] * len(destroy_ops)
    repair_weights = [1.0] * len(repair_ops)
    destroy_scores = [0.0] * len(destroy_ops)
    repair_scores = [0.0] * len(repair_ops)
    destroy_uses = [0] * len(destroy_ops)
    repair_uses = [0] * len(repair_ops)
    deadline = time.perf_counter() + time_limit_s
    temperature = max(1.0, current_cost * 0.025)
    iterations = 0
    while time.perf_counter() < deadline:
        destroy_idx = rng.choices(range(len(destroy_ops)), weights=destroy_weights, k=1)[0]
        repair_idx = rng.choices(range(len(repair_ops)), weights=repair_weights, k=1)[0]
        count = max(1, min(len(jobs), round(len(jobs) * rng.uniform(0.1, 0.3))))
        partial, removed = destroy_ops[destroy_idx](
            current, count, rng, physical, jobs, return_to_depot
        )
        candidate = repair_ops[repair_idx](
            partial,
            removed,
            physical,
            jobs,
            capacity_kg=capacity_kg,
            return_to_depot=return_to_depot,
        )
        if rng.random() < 0.35:
            candidate = improve_pair_sequence(
                candidate,
                physical,
                jobs,
                capacity_kg=capacity_kg,
                return_to_depot=return_to_depot,
                max_moves=1,
            )
        candidate_cost = stop_sequence_cost(
            candidate, physical, return_to_depot=return_to_depot
        )
        delta = candidate_cost - current_cost
        accepted = delta <= 0 or rng.random() < math.exp(-delta / max(temperature, 1e-9))
        reward = 0.0
        if candidate_cost + 1e-6 < best_cost:
            best, best_cost = list(candidate), candidate_cost
            reward = 8.0
        elif candidate_cost + 1e-6 < current_cost:
            reward = 4.0
        elif accepted:
            reward = 1.0
        if accepted:
            current, current_cost = candidate, candidate_cost
        destroy_scores[destroy_idx] += reward
        repair_scores[repair_idx] += reward
        destroy_uses[destroy_idx] += 1
        repair_uses[repair_idx] += 1
        iterations += 1
        temperature *= 0.997
        if iterations % 40 == 0:
            reaction = 0.25
            for idx in range(len(destroy_ops)):
                score = destroy_scores[idx] / max(1, destroy_uses[idx])
                destroy_weights[idx] = max(0.15, (1 - reaction) * destroy_weights[idx] + reaction * score)
                destroy_scores[idx] = 0.0
                destroy_uses[idx] = 0
            for idx in range(len(repair_ops)):
                score = repair_scores[idx] / max(1, repair_uses[idx])
                repair_weights[idx] = max(0.15, (1 - reaction) * repair_weights[idx] + reaction * score)
                repair_scores[idx] = 0.0
                repair_uses[idx] = 0
            if current_cost > best_cost * 1.08:
                current, current_cost = list(best), best_cost
    if not stop_sequence_feasible(best, jobs, capacity_kg):
        raise RuntimeError("ALNS a produit une tournée non réalisable")
    return best, iterations, "ALNS adaptatif pickup-delivery"


def sequence_to_points_and_stops(
    depot: Point,
    jobs: Sequence[RouteJob],
    sequence: Sequence[Stop],
    *,
    return_to_depot: bool,
) -> tuple[list[Point], list[dict[str, Any]], list[int]]:
    points = [depot]
    physical_indices = [0]
    stops: list[dict[str, Any]] = [
        {
            "sequence": 0,
            "type": "start",
            "job_id": None,
            "client": "Départ",
            "reference": "",
            "label": depot.label,
            "lat": depot.lat,
            "lon": depot.lon,
            "weight_kg": 0.0,
        }
    ]
    load = 0.0
    for sequence_index, (job_index, stop_type) in enumerate(sequence, start=1):
        job = jobs[job_index]
        if stop_type == 0:
            point = job.pickup
            label = "pickup"
            load += job.weight_kg
        else:
            point = job.delivery
            label = "delivery"
            load -= job.weight_kg
        points.append(point)
        physical_indices.append(stop_physical_index((job_index, stop_type)))
        stops.append(
            {
                "sequence": sequence_index,
                "type": label,
                "job_id": job.id,
                "client": job.client,
                "reference": job.reference,
                "label": point.label,
                "lat": point.lat,
                "lon": point.lon,
                "weight_kg": job.weight_kg,
                "quantity": job.quantity,
                "unit_type": job.unit_type,
                "load_after_kg": max(0.0, load),
            }
        )
    if return_to_depot:
        sequence_index = len(stops)
        points.append(depot)
        physical_indices.append(0)
        stops.append(
            {
                "sequence": sequence_index,
                "type": "return",
                "job_id": None,
                "client": "Retour au départ",
                "reference": "",
                "label": depot.label,
                "lat": depot.lat,
                "lon": depot.lon,
                "weight_kg": 0.0,
                "load_after_kg": 0.0,
            }
        )
    return points, stops, physical_indices


def _physical_index_for_job(job_index: int, stop_type: str) -> int:
    return 1 + 2 * job_index + (1 if stop_type == "delivery" else 0)


def _sequence_points(
    depot: Point,
    jobs: Sequence[RouteJob],
    order: Sequence[int],
    *,
    return_to_depot: bool,
) -> tuple[list[Point], list[dict[str, Any]], list[int]]:
    points = [depot]
    stops: list[dict[str, Any]] = [
        {
            "sequence": 0,
            "type": "start",
            "job_id": None,
            "client": "Départ",
            "reference": "",
            "label": depot.label,
            "lat": depot.lat,
            "lon": depot.lon,
            "weight_kg": 0.0,
        }
    ]
    physical_indices = [0]
    sequence = 1
    for job_index in order:
        job = jobs[job_index]
        for stop_type, point in (("pickup", job.pickup), ("delivery", job.delivery)):
            points.append(point)
            physical_indices.append(_physical_index_for_job(job_index, stop_type))
            stops.append(
                {
                    "sequence": sequence,
                    "type": stop_type,
                    "job_id": job.id,
                    "client": job.client,
                    "reference": job.reference,
                    "label": point.label,
                    "lat": point.lat,
                    "lon": point.lon,
                    "weight_kg": job.weight_kg,
                    "quantity": job.quantity,
                    "unit_type": job.unit_type,
                }
            )
            sequence += 1
    if return_to_depot:
        points.append(depot)
        physical_indices.append(0)
        stops.append(
            {
                "sequence": sequence,
                "type": "return",
                "job_id": None,
                "client": "Retour au départ",
                "reference": "",
                "label": depot.label,
                "lat": depot.lat,
                "lon": depot.lon,
                "weight_kg": 0.0,
            }
        )
    return points, stops, physical_indices


def _matrix_from_payload(raw: Any, size: int, name: str) -> tuple[tuple[float, ...], ...] | None:
    if raw is None:
        return None
    if not isinstance(raw, list) or len(raw) != size or any(not isinstance(row, list) or len(row) != size for row in raw):
        raise RouteInputError(f"La matrice {name} doit être carrée et contenir {size} lignes.")
    try:
        return tuple(tuple(float(value) for value in row) for row in raw)
    except (TypeError, ValueError) as exc:
        raise RouteInputError(f"La matrice {name} contient une valeur invalide.") from exc


def optimise(payload: dict[str, Any]) -> dict[str, Any]:
    depot, jobs, settings = parse_problem(payload)
    points = physical_points(depot, jobs)
    supplied_distances = _matrix_from_payload(payload.get("distance_matrix_m"), len(points), "des distances")
    supplied_durations = _matrix_from_payload(payload.get("duration_matrix_s"), len(points), "des durées")
    if supplied_distances is not None:
        if supplied_durations is None:
            supplied_durations = tuple(tuple(value / (50_000 / 3_600) for value in row) for row in supplied_distances)
        physical = MatrixData(
            supplied_distances,
            supplied_durations,
            str(payload.get("_matrix_provider") or "matrice fournie"),
            str(payload.get("_matrix_warning")) if payload.get("_matrix_warning") else None,
        )
    else:
        physical = road_matrix(points)
    method_warning = None
    started = time.perf_counter()
    if settings["method"] == "hgs":
        sequence, iterations, engine, method_warning = solve_hgs_pickup_delivery(
            physical,
            jobs,
            capacity_kg=settings["capacity_kg"],
            return_to_depot=settings["return_to_depot"],
            time_limit_s=settings["time_limit_s"],
            seed=settings["seed"],
        )
        method_name = "HGS / PyVRP"
        method_description = (
            "Recherche génétique hybride : PyVRP peut fournir une graine HGS, puis AxioLoad croise et améliore "
            "les ordres de missions avec un décodeur qui place séparément chaque enlèvement et chaque livraison "
            "en respectant la précédence et la capacité du camion."
        )
    else:
        sequence, iterations, engine = solve_alns_pickup_delivery(
            physical,
            jobs,
            capacity_kg=settings["capacity_kg"],
            return_to_depot=settings["return_to_depot"],
            time_limit_s=settings["time_limit_s"],
            seed=settings["seed"],
        )
        method_name = "ALNS"
        method_description = (
            "Recherche adaptative par grands voisinages : le moteur retire des couples enlèvement-livraison, "
            "les réinsère à des positions distinctes et renforce les opérateurs qui réduisent la distance tout "
            "en respectant précédence et capacité."
        )
    elapsed = time.perf_counter() - started
    ordered_points, stops, physical_indices = sequence_to_points_and_stops(
        depot,
        jobs,
        sequence,
        return_to_depot=settings["return_to_depot"],
    )
    if supplied_distances is None or payload.get("_fetch_geometry"):
        geometry, geometry_distance, geometry_duration, geometry_provider, geometry_warning = route_geometry(ordered_points)
    else:
        geometry = [[point.lat, point.lon] for point in ordered_points]
        geometry_distance = sum(
            physical.distances_m[a][b] for a, b in zip(physical_indices, physical_indices[1:])
        )
        geometry_duration = sum(
            physical.durations_s[a][b] for a, b in zip(physical_indices, physical_indices[1:])
        )
        geometry_provider = physical.provider
        geometry_warning = None
    legs = []
    for index, (source_idx, target_idx) in enumerate(zip(physical_indices, physical_indices[1:])):
        legs.append(
            {
                "from_sequence": index,
                "to_sequence": index + 1,
                "distance_km": physical.distances_m[source_idx][target_idx] / 1000,
                "duration_min": physical.durations_s[source_idx][target_idx] / 60,
            }
        )
    # Prefer the matrix total for comparability between methods. The geometry service may snap
    # points slightly differently and is retained as a display/control value.
    total_distance_m = sum(physical.distances_m[a][b] for a, b in zip(physical_indices, physical_indices[1:]))
    total_duration_s = sum(physical.durations_s[a][b] for a, b in zip(physical_indices, physical_indices[1:]))
    warnings = list(dict.fromkeys(warning for warning in (physical.warning, method_warning, geometry_warning) if warning))
    jobs_summary = []
    for job_index, job in enumerate(jobs):
        pickup_index = 1 + 2 * job_index
        delivery_index = pickup_index + 1
        jobs_summary.append(
            {
                "job_id": job.id,
                "client": job.client,
                "reference": job.reference,
                "pickup_label": job.pickup.label,
                "delivery_label": job.delivery.label,
                "quantity": job.quantity,
                "unit_type": job.unit_type,
                "weight_kg": job.weight_kg,
                "direct_distance_km": physical.distances_m[pickup_index][delivery_index] / 1000,
                "direct_duration_min": physical.durations_s[pickup_index][delivery_index] / 60,
            }
        )
    return {
        "method": settings["method"],
        "method_name": method_name,
        "method_description": method_description,
        "engine": engine,
        "provider": physical.provider,
        "geometry_provider": geometry_provider,
        "elapsed_seconds": elapsed,
        "iterations": iterations,
        "return_to_depot": settings["return_to_depot"],
        "job_count": len(jobs),
        "stop_count": len(stops),
        "total_distance_km": total_distance_m / 1000,
        "total_duration_min": total_duration_s / 60,
        "geometry_distance_km": geometry_distance / 1000,
        "geometry_duration_min": geometry_duration / 60,
        "order": [stop["job_id"] for stop in stops if stop["type"] == "delivery"],
        "stops": stops,
        "legs": legs,
        "geometry": geometry,
        "jobs_summary": jobs_summary,
        "total_weight_kg": sum(job.weight_kg for job in jobs),
        "total_handling_units": sum(job.quantity for job in jobs),
        "warnings": warnings,
        "model_note": (
            "Chaque mission comporte un enlèvement et une livraison liés. Les arrêts de plusieurs missions peuvent "
            "être entrelacés lorsque cela réduit le trajet, mais chaque enlèvement reste obligatoirement placé avant "
            "sa livraison et la charge en cours ne dépasse jamais la capacité saisie."
        ),
    }


def compare(payload: dict[str, Any]) -> dict[str, Any]:
    depot, jobs, _settings = parse_problem({**payload, "method": "hgs"})
    points = physical_points(depot, jobs)
    supplied_distances = _matrix_from_payload(payload.get("distance_matrix_m"), len(points), "des distances")
    supplied_durations = _matrix_from_payload(payload.get("duration_matrix_s"), len(points), "des durées")
    if supplied_distances is not None:
        if supplied_durations is None:
            supplied_durations = tuple(tuple(value / (50_000 / 3_600) for value in row) for row in supplied_distances)
        matrix = MatrixData(supplied_distances, supplied_durations, "matrice fournie")
        fetch_geometry = False
    else:
        matrix = road_matrix(points)
        fetch_geometry = True
    common = {
        **payload,
        "distance_matrix_m": [list(row) for row in matrix.distances_m],
        "duration_matrix_s": [list(row) for row in matrix.durations_s],
        "_matrix_provider": matrix.provider,
        "_matrix_warning": matrix.warning,
        "_fetch_geometry": fetch_geometry,
    }
    results = [optimise({**common, "method": method}) for method in ("hgs", "alns")]
    return {
        "provider": matrix.provider,
        "warning": matrix.warning,
        "results": results,
    }
