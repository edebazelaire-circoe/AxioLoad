from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, replace
from typing import Any, Iterable, Sequence

from .domain import CargoItem, Severity, VehiclePlan, VehicleVersion, to_primitive
from .metrics import calculate_length_metrics
from .normalization import normalize_payload
from .optimization_methods import METHODS, pack_with_method
from .route_optimization import MatrixData, Point, RouteInputError, road_matrix, route_geometry
from .validation import calculate_weight, has_errors, validate_compatibility, validate_delivery_access, validate_geometry

METHODS_BY_CODE = {method.code: method for method in METHODS}
ALNS_ORACLE_METHODS = ("extreme_points", "block_layers", "skyline_blf")
GENETIC_ORACLE_METHODS = ("extreme_points", "block_layers", "brkga_hybrid")


class TotalOptimizationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TotalClient:
    id: str
    client: str
    pickup: Point
    delivery: Point
    source_ids: tuple[str, ...]
    quantity: int
    unit_type: str
    weight_kg: float


@dataclass(frozen=True, slots=True)
class OracleResult:
    feasible: bool
    plan: dict[str, Any] | None
    method_code: str = ""
    method_name: str = ""
    occupied_length_m: float = 0.0
    linear_meters: float = 0.0
    total_weight_kg: float = 0.0
    diagnostics: tuple[str, ...] = ()


@dataclass(slots=True)
class TotalProblem:
    loading_payload: dict[str, Any]
    clients: tuple[TotalClient, ...]
    depot: Point
    return_to_depot: bool
    vehicle: VehicleVersion
    expanded_items: tuple[CargoItem, ...]
    distance_matrix: MatrixData
    time_limit_s: float
    seed: int
    max_vehicles: int
    fetch_geometry: bool

    @property
    def n(self) -> int:
        return len(self.clients)

    def pickup_index(self, client_index: int) -> int:
        return 1 + 2 * client_index

    def delivery_index(self, client_index: int) -> int:
        return 2 + 2 * client_index

    def route_physical_indices(self, delivery_order: Sequence[int]) -> list[int]:
        indices = [0]
        indices.extend(self.pickup_index(index) for index in reversed(delivery_order))
        indices.extend(self.delivery_index(index) for index in delivery_order)
        if self.return_to_depot:
            indices.append(0)
        return indices

    def route_points(self, delivery_order: Sequence[int]) -> list[Point]:
        points = [self.depot]
        points.extend(self.clients[index].pickup for index in reversed(delivery_order))
        points.extend(self.clients[index].delivery for index in delivery_order)
        if self.return_to_depot:
            points.append(self.depot)
        return points

    def route_distance_m(self, delivery_order: Sequence[int]) -> float:
        indices = self.route_physical_indices(delivery_order)
        return sum(self.distance_matrix.distances_m[a][b] for a, b in zip(indices, indices[1:]))

    def route_duration_s(self, delivery_order: Sequence[int]) -> float:
        indices = self.route_physical_indices(delivery_order)
        return sum(self.distance_matrix.durations_s[a][b] for a, b in zip(indices, indices[1:]))


class PackingOracle:
    def __init__(self, problem: TotalProblem, deadline: float):
        self.problem = problem
        self.deadline = deadline
        self.cache: dict[tuple[tuple[int, ...], tuple[str, ...]], OracleResult] = {}
        self.calls = 0
        self.cache_hits = 0

    def _items_for_route(self, route: Sequence[int]) -> tuple[CargoItem, ...]:
        order_by_source: dict[str, int] = {}
        size = len(route)
        for position, client_index in enumerate(route):
            order = size - position
            for source_id in self.problem.clients[client_index].source_ids:
                order_by_source[source_id] = order
        return tuple(
            replace(item, delivery_order=order_by_source[item.source_id])
            for item in self.problem.expanded_items
            if item.source_id in order_by_source
        )

    def evaluate(self, route: Sequence[int], method_codes: Sequence[str], *, seed_offset: int = 0) -> OracleResult:
        signature = (tuple(route), tuple(method_codes))
        cached = self.cache.get(signature)
        if cached is not None:
            self.cache_hits += 1
            return cached
        self.calls += 1
        if not route or time.perf_counter() >= self.deadline:
            result = OracleResult(False, None, diagnostics=("Tournée vide ou budget épuisé",))
            self.cache[signature] = result
            return result
        items = self._items_for_route(route)
        item_map = {item.id: item for item in items}
        diagnostics: list[str] = []
        best: OracleResult | None = None
        for method_index, code in enumerate(method_codes):
            method = METHODS_BY_CODE.get(code)
            if method is None or time.perf_counter() >= self.deadline:
                continue
            attempt_deadline = min(self.deadline, time.perf_counter() + min(0.65, 0.12 + len(items) * 0.009))
            placements, pack_diagnostics = pack_with_method(
                method, items, self.problem.vehicle,
                self.problem.seed + seed_offset + method_index * 1009 + len(route) * 37,
                attempt_deadline,
            )
            if placements is None:
                diagnostics.extend(d.message for d in pack_diagnostics[:2])
                continue
            validation = (*validate_geometry(self.problem.vehicle, placements, item_map), *validate_delivery_access(placements))
            weight, weight_diagnostics, _ = calculate_weight(self.problem.vehicle, placements)
            validation = (*validation, *weight_diagnostics, *validate_compatibility((placements,), item_map))
            if has_errors(tuple(validation)):
                diagnostics.extend(d.message for d in validation if d.severity == Severity.ERROR)
                continue
            metrics = calculate_length_metrics(placements)
            plan = VehiclePlan(
                vehicle_version_id=self.problem.vehicle.version_id,
                vehicle_name=self.problem.vehicle.name,
                placements=placements,
                linear_meters=metrics.linear_meters,
                occupied_length_m=metrics.occupied_length_m,
                weight=weight,
                diagnostics=tuple(validation),
            )
            candidate = OracleResult(
                True, to_primitive(plan), method.code, method.name,
                metrics.occupied_length_m, metrics.linear_meters, weight.total_weight_kg,
                tuple(d.message for d in validation if d.severity == Severity.WARNING),
            )
            if best is None or (candidate.occupied_length_m, candidate.method_code) < (best.occupied_length_m, best.method_code):
                best = candidate
        result = best or OracleResult(False, None, diagnostics=tuple(dict.fromkeys(diagnostics))[:5] or ("Aucun placement LIFO valide",))
        self.cache[signature] = result
        return result


def _as_point(raw: Any, field: str) -> Point:
    try:
        lat, lon = float(raw["lat"]), float(raw["lon"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TotalOptimizationError(f"Coordonnées invalides pour {field}.") from exc
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise TotalOptimizationError(f"Coordonnées hors limites pour {field}.")
    return Point(lat, lon, str(raw.get("label") or raw.get("address") or field))


def _matrix(raw: Any, size: int, field: str) -> tuple[tuple[float, ...], ...] | None:
    if raw is None:
        return None
    if not isinstance(raw, list) or len(raw) != size:
        raise TotalOptimizationError(f"La matrice {field} doit contenir {size} lignes.")
    output = []
    for row in raw:
        if not isinstance(row, list) or len(row) != size:
            raise TotalOptimizationError(f"La matrice {field} doit être carrée ({size} × {size}).")
        try:
            output.append(tuple(max(0.0, float(value)) for value in row))
        except (TypeError, ValueError) as exc:
            raise TotalOptimizationError(f"Valeur invalide dans la matrice {field}.") from exc
    return tuple(output)


def _parse_problem(payload: dict[str, Any], catalog: tuple[VehicleVersion, ...]) -> TotalProblem:
    loading, route = payload.get("loading"), payload.get("route")
    if not isinstance(loading, dict) or not isinstance(route, dict):
        raise TotalOptimizationError("Les données de chargement et d’itinéraire sont requises.")
    try:
        normalized = normalize_payload(loading, requested_solutions=1, catalog=catalog)
    except Exception as exc:
        message = getattr(getattr(exc, "diagnostic", None), "message", str(exc))
        raise TotalOptimizationError(message) from exc
    if len(normalized.vehicles) != 1:
        raise TotalOptimizationError("L’optimisation totale nécessite un modèle de véhicule sélectionné.")
    vehicle = normalized.vehicles[0]
    depot = _as_point(route.get("depot") or {}, "le lieu actuel du camion")
    raw_jobs = route.get("jobs")
    if not isinstance(raw_jobs, list) or not raw_jobs:
        raise TotalOptimizationError("Ajoutez au moins un client avec un enlèvement et une livraison.")
    if len(raw_jobs) > 35:
        raise TotalOptimizationError("La version intégrée est limitée à 35 lignes clients par calcul total.")

    source_ids = {str(item.get("id") or "").strip() for item in loading.get("items", [])}
    source_ids.discard("")
    assigned: set[str] = set()
    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for index, raw in enumerate(raw_jobs):
        if not isinstance(raw, dict):
            raise TotalOptimizationError(f"La ligne itinéraire {index + 1} est invalide.")
        pickup = _as_point(raw.get("pickup") or {}, f"l’enlèvement de la ligne {index + 1}")
        delivery = _as_point(raw.get("delivery") or {}, f"la livraison de la ligne {index + 1}")
        item_ids = tuple(str(v).strip() for v in (raw.get("item_ids") or [raw.get("reference") or raw.get("id")]) if str(v or "").strip())
        unknown = [v for v in item_ids if v not in source_ids]
        if unknown:
            raise TotalOptimizationError("Référence de marchandise inconnue : " + ", ".join(unknown))
        duplicate = [v for v in item_ids if v in assigned]
        if duplicate:
            raise TotalOptimizationError("Une référence ne peut appartenir qu’à un seul client : " + ", ".join(duplicate))
        assigned.update(item_ids)
        client = str(raw.get("client") or raw.get("destination") or f"Client {index + 1}").strip()
        key = (client.casefold(), round(pickup.lat, 7), round(pickup.lon, 7), round(delivery.lat, 7), round(delivery.lon, 7))
        target = grouped.setdefault(key, {
            "id": str(raw.get("id") or f"CLIENT-{index + 1:03d}"), "client": client,
            "pickup": pickup, "delivery": delivery, "source_ids": [], "quantity": 0,
            "unit_types": set(), "weight_kg": 0.0,
        })
        target["source_ids"].extend(item_ids)
        target["quantity"] += max(0, int(raw.get("quantity") or 0))
        target["unit_types"].add(str(raw.get("unit_type") or "unité"))
        target["weight_kg"] += max(0.0, float(raw.get("weight_kg") or 0.0))
    missing = sorted(source_ids - assigned)
    if missing:
        raise TotalOptimizationError("Toutes les références doivent disposer d’un enlèvement et d’une livraison : " + ", ".join(missing))
    clients = tuple(TotalClient(
        id=str(v["id"]), client=str(v["client"]), pickup=v["pickup"], delivery=v["delivery"],
        source_ids=tuple(v["source_ids"]), quantity=int(v["quantity"]),
        unit_type=next(iter(v["unit_types"])) if len(v["unit_types"]) == 1 else "unités mixtes",
        weight_kg=float(v["weight_kg"]),
    ) for v in grouped.values())
    points = [depot]
    for client in clients:
        points.extend((client.pickup, client.delivery))
    distances = _matrix(route.get("distance_matrix_m"), len(points), "des distances")
    durations = _matrix(route.get("duration_matrix_s"), len(points), "des durées")
    if distances is not None:
        if durations is None:
            speed = 50_000 / 3_600
            durations = tuple(tuple(v / speed for v in row) for row in distances)
        matrix = MatrixData(distances, durations, "matrice fournie")
        fetch_geometry = bool(route.get("_fetch_geometry", False))
    else:
        try:
            matrix = road_matrix(points)
        except RouteInputError as exc:
            raise TotalOptimizationError(str(exc)) from exc
        fetch_geometry = bool(route.get("_fetch_geometry", True))
    return TotalProblem(
        loading, clients, depot, bool(route.get("return_to_depot", True)), vehicle, normalized.items, matrix,
        min(30.0, max(2.0, float(payload.get("time_limit_s") or loading.get("budget_seconds") or 30.0))),
        int(loading.get("seed") or payload.get("seed") or 1),
        min(len(clients), max(1, int(loading.get("vehicle_policy", {}).get("max_vehicles") or 5))),
        fetch_geometry,
    )


def _objective(problem: TotalProblem, routes: Sequence[Sequence[int]], oracle: PackingOracle, methods: Sequence[str]) -> tuple[int, float, float]:
    distance = sum(problem.route_distance_m(route) for route in routes)
    occupied = 0.0
    for route in routes:
        result = oracle.evaluate(route, methods)
        if not result.feasible:
            return 10_000, math.inf, math.inf
        occupied += result.occupied_length_m
    return len(routes), distance, occupied


def _scalar(problem: TotalProblem, objective: tuple[int, float, float]) -> float:
    max_edge = max(max(row) for row in problem.distance_matrix.distances_m)
    fleet_penalty = max(1_000_000.0, max_edge * (2 * problem.n + 4) + 1.0)
    return objective[0] * fleet_penalty + objective[1] + objective[2] * 100


def _greedy_initial(problem: TotalProblem, oracle: PackingOracle, methods: Sequence[str]) -> list[list[int]]:
    routes = [[i] for i in range(problem.n)]
    for route in routes:
        if not oracle.evaluate(route, methods).feasible:
            raise TotalOptimizationError(f"Les marchandises du client « {problem.clients[route[0]].client} » ne rentrent pas seules dans le véhicule.")
    while len(routes) > 1:
        best = None
        for a in range(len(routes)):
            for b in range(a + 1, len(routes)):
                for merged in (routes[a] + routes[b], routes[b] + routes[a]):
                    if not oracle.evaluate(merged, methods).feasible:
                        continue
                    candidate = [r for i, r in enumerate(routes) if i not in {a, b}] + [merged]
                    obj = _objective(problem, candidate, oracle, methods)
                    if best is None or obj < best[0]:
                        best = (obj, a, b, merged)
        if best is None:
            break
        _, a, b, merged = best
        routes = [r for i, r in enumerate(routes) if i not in {a, b}] + [merged]
    return routes


def _destroy(problem: TotalProblem, routes: Sequence[Sequence[int]], rng: random.Random, operator: str, count: int) -> set[int]:
    clients = [c for route in routes for c in route]
    count = min(max(1, count), len(clients))
    if operator == "random":
        return set(rng.sample(clients, count))
    if operator == "related":
        seed = rng.choice(clients)
        return set(sorted(clients, key=lambda c: (problem.distance_matrix.distances_m[problem.delivery_index(seed)][problem.delivery_index(c)], c))[:count])
    contributions = []
    for route in routes:
        base = problem.route_distance_m(route)
        for client in route:
            reduced = [v for v in route if v != client]
            contributions.append((base - (problem.route_distance_m(reduced) if reduced else 0), client))
    contributions.sort(reverse=True)
    return {c for _, c in contributions[:count]}


def _insert(problem: TotalProblem, routes: list[list[int]], client: int, oracle: PackingOracle, methods: Sequence[str]) -> list[list[int]]:
    best_routes, best_obj = None, None
    for ri, route in enumerate(routes):
        for pos in range(len(route) + 1):
            new_route = route[:pos] + [client] + route[pos:]
            if not oracle.evaluate(new_route, methods).feasible:
                continue
            candidate = [list(v) for v in routes]; candidate[ri] = new_route
            obj = _objective(problem, candidate, oracle, methods)
            if best_obj is None or obj < best_obj:
                best_routes, best_obj = candidate, obj
    if len(routes) < problem.max_vehicles and oracle.evaluate([client], methods).feasible:
        candidate = [list(v) for v in routes] + [[client]]
        obj = _objective(problem, candidate, oracle, methods)
        if best_obj is None or obj < best_obj:
            best_routes, best_obj = candidate, obj
    if best_routes is None:
        raise TotalOptimizationError(f"Impossible de réinsérer le client « {problem.clients[client].client} ».")
    return best_routes


def _local_search(problem: TotalProblem, routes: list[list[int]], oracle: PackingOracle, methods: Sequence[str]) -> list[list[int]]:
    best = [list(r) for r in routes]; best_obj = _objective(problem, best, oracle, methods)
    for ri, route in enumerate(list(best)):
        for left in range(len(route) - 1):
            for right in range(left + 2, len(route) + 1):
                new_route = route[:left] + list(reversed(route[left:right])) + route[right:]
                if not oracle.evaluate(new_route, methods).feasible:
                    continue
                candidate = [list(v) for v in best]; candidate[ri] = new_route
                obj = _objective(problem, candidate, oracle, methods)
                if obj < best_obj:
                    return candidate
    return best


def solve_coupled_alns(problem: TotalProblem, deadline: float) -> tuple[list[list[int]], int, PackingOracle]:
    rng = random.Random(problem.seed + 811)
    oracle = PackingOracle(problem, deadline)
    current = _local_search(problem, _greedy_initial(problem, oracle, ALNS_ORACLE_METHODS), oracle, ALNS_ORACLE_METHODS)
    best = [list(r) for r in current]
    current_obj = best_obj = _objective(problem, current, oracle, ALNS_ORACLE_METHODS)
    temperature = max(1.0, current_obj[1] * .03)
    destroy_weights = {"random": 1.0, "worst": 1.0, "related": 1.0}
    repair_weights = {"greedy": 1.0, "regret": 1.0}
    iterations = 0
    def choose(weights: dict[str, float]) -> str:
        draw = rng.random() * sum(weights.values()); cumulative = 0.0
        for key, value in weights.items():
            cumulative += value
            if draw <= cumulative: return key
        return next(iter(weights))
    while time.perf_counter() < deadline:
        iterations += 1
        dop, rop = choose(destroy_weights), choose(repair_weights)
        removed = _destroy(problem, current, rng, dop, max(1, round(problem.n * rng.uniform(.12, .30))))
        partial = [[c for c in route if c not in removed] for route in current]
        partial = [r for r in partial if r]
        ordered = list(removed)
        if rop == "regret":
            ordered.sort(key=lambda c: (-problem.clients[c].weight_kg, -len(problem.clients[c].source_ids), rng.random()))
        else: rng.shuffle(ordered)
        try:
            candidate = partial
            for client in ordered:
                candidate = _insert(problem, candidate, client, oracle, ALNS_ORACLE_METHODS)
        except TotalOptimizationError:
            continue
        if iterations % 5 == 0:
            candidate = _local_search(problem, candidate, oracle, ALNS_ORACLE_METHODS)
        obj = _objective(problem, candidate, oracle, ALNS_ORACLE_METHODS)
        delta = _scalar(problem, obj) - _scalar(problem, current_obj)
        accepted = obj < current_obj or rng.random() < math.exp(-max(0, delta) / max(1, temperature))
        if accepted:
            current, current_obj = candidate, obj
        if obj < best_obj:
            best, best_obj = [list(r) for r in candidate], obj
            destroy_weights[dop] += 4; repair_weights[rop] += 4
        elif accepted:
            destroy_weights[dop] += 1; repair_weights[rop] += 1
        temperature *= .997
    if len(best) > problem.max_vehicles:
        raise TotalOptimizationError(f"Le mode ALNS n’a pas pu respecter la limite de {problem.max_vehicles} véhicule(s).")
    return best, iterations, oracle


def _nearest_order(problem: TotalProblem) -> tuple[int, ...]:
    remaining = set(range(problem.n)); order = []; current = 0
    while remaining:
        nxt = min(remaining, key=lambda c: (problem.distance_matrix.distances_m[current][problem.delivery_index(c)], c))
        order.append(nxt); remaining.remove(nxt); current = problem.delivery_index(nxt)
    return tuple(order)


def _crossover(a: Sequence[int], b: Sequence[int], rng: random.Random) -> tuple[int, ...]:
    if len(a) < 2: return tuple(a)
    left, right = sorted(rng.sample(range(len(a)), 2)); right += 1
    child: list[int | None] = [None] * len(a); child[left:right] = a[left:right]
    remaining = iter(v for v in b if v not in child)
    for i, v in enumerate(child):
        if v is None: child[i] = next(remaining)
    return tuple(int(v) for v in child)


def _mutate(order: Sequence[int], rng: random.Random) -> tuple[int, ...]:
    result = list(order)
    if len(result) < 2: return tuple(result)
    a, b = sorted(rng.sample(range(len(result)), 2)); op = rng.choice(("swap", "reverse", "relocate"))
    if op == "swap": result[a], result[b] = result[b], result[a]
    elif op == "reverse": result[a:b+1] = reversed(result[a:b+1])
    else: result.insert(a, result.pop(b))
    return tuple(result)


def _decode(problem: TotalProblem, order: Sequence[int], oracle: PackingOracle, method: str):
    n = len(order); dp = [None] * (n + 1); dp[0] = ((0, 0.0, 0.0), [])
    for end in range(1, n + 1):
        best = None
        for start in range(end - 1, -1, -1):
            if dp[start] is None: continue
            route = list(order[start:end]); result = oracle.evaluate(route, (method,), seed_offset=start * 97 + end * 13)
            if not result.feasible: continue
            prev_obj, prev_routes = dp[start]
            obj = (prev_obj[0] + 1, prev_obj[1] + problem.route_distance_m(route), prev_obj[2] + result.occupied_length_m)
            if obj[0] > problem.max_vehicles: continue
            candidate = (obj, prev_routes + [route])
            if best is None or obj < best[0]: best = candidate
        dp[end] = best
    return dp[n]


def solve_bilevel_genetic(problem: TotalProblem, deadline: float):
    rng = random.Random(problem.seed + 1709); oracle = PackingOracle(problem, deadline)
    codes = list(GENETIC_ORACLE_METHODS); size = max(14, min(34, problem.n * 4)); nearest = _nearest_order(problem)
    population = [(nearest, code) for code in codes] + [(tuple(reversed(nearest)), codes[0])]
    while len(population) < size:
        order = list(range(problem.n)); rng.shuffle(order); population.append((tuple(order), rng.choice(codes)))
    cache = {}
    def evaluate(chrom):
        if chrom not in cache: cache[chrom] = _decode(problem, chrom[0], oracle, chrom[1])
        return cache[chrom]
    def fitness(chrom):
        value = evaluate(chrom); return value[0] if value else (10_000, math.inf, math.inf)
    best = min(population, key=fitness); iterations = 0
    while time.perf_counter() < deadline:
        iterations += 1; ranked = sorted(population, key=fitness)
        if fitness(ranked[0]) < fitness(best): best = ranked[0]
        elite_count = max(3, size // 5); elites = ranked[:elite_count]; next_pop = list(elites); signatures = set(next_pop)
        while len(next_pop) < size and time.perf_counter() < deadline:
            pa = min(rng.sample(ranked[:max(5, size//2)], min(3, len(ranked))), key=fitness)
            pb = min(rng.sample(ranked, min(3, len(ranked))), key=fitness)
            order = _crossover(pa[0], pb[0], rng)
            if rng.random() < .82: order = _mutate(order, rng)
            method = pa[1] if rng.random() < .68 else pb[1]
            if rng.random() < .18: method = rng.choice(codes)
            child = (order, method)
            if child not in signatures or rng.random() < .04: next_pop.append(child); signatures.add(child)
        population = next_pop or ranked
    best = min(population + [best], key=fitness); decoded = evaluate(best)
    if decoded is None: raise TotalOptimizationError("La co-évolution génétique n’a pas trouvé de partition chargeable.")
    return decoded[1], iterations, oracle, best[1]


def _stops(problem: TotalProblem, route: Sequence[int]) -> list[dict[str, Any]]:
    stops = [{"sequence": 1, "type": "start", "client": "", "label": problem.depot.label, "lat": problem.depot.lat, "lon": problem.depot.lon}]
    sequence = 2; load = 0.0
    for index in reversed(route):
        client = problem.clients[index]; load += client.weight_kg
        stops.append({"sequence": sequence, "type": "pickup", "client_id": client.id, "client": client.client, "label": client.pickup.label, "lat": client.pickup.lat, "lon": client.pickup.lon, "quantity": client.quantity, "unit_type": client.unit_type, "weight_kg": client.weight_kg, "load_after_kg": load}); sequence += 1
    for index in route:
        client = problem.clients[index]; load -= client.weight_kg
        stops.append({"sequence": sequence, "type": "delivery", "client_id": client.id, "client": client.client, "label": client.delivery.label, "lat": client.delivery.lat, "lon": client.delivery.lon, "quantity": client.quantity, "unit_type": client.unit_type, "weight_kg": client.weight_kg, "load_after_kg": max(0, load)}); sequence += 1
    if problem.return_to_depot:
        stops.append({"sequence": sequence, "type": "return", "client": "", "label": problem.depot.label, "lat": problem.depot.lat, "lon": problem.depot.lon})
    return stops


def _build_solution(problem: TotalProblem, routes: Sequence[Sequence[int]], oracle: PackingOracle, methods: Sequence[str], *, code: str, name: str, description: str, iterations: int, elapsed: float) -> dict[str, Any]:
    route_results = []; total_distance = total_duration = total_linear = 0.0; warnings = []
    for route_index, route in enumerate(routes):
        packed = oracle.evaluate(route, methods, seed_offset=route_index * 211)
        if not packed.feasible or packed.plan is None: raise TotalOptimizationError("Une tournée finale n’est plus chargeable.")
        distance, duration = problem.route_distance_m(route), problem.route_duration_s(route)
        points = problem.route_points(route)
        if problem.fetch_geometry:
            geometry, _, _, provider, warning = route_geometry(points)
            if warning: warnings.append(warning)
        else:
            geometry = [[p.lat, p.lon] for p in points]; provider = problem.distance_matrix.provider
        total_distance += distance; total_duration += duration; total_linear += packed.linear_meters
        route_results.append({
            "route_index": route_index, "vehicle_name": problem.vehicle.name, "vehicle_version_id": problem.vehicle.version_id,
            "clients": [{"id": problem.clients[i].id, "client": problem.clients[i].client, "quantity": problem.clients[i].quantity, "unit_type": problem.clients[i].unit_type, "weight_kg": problem.clients[i].weight_kg, "pickup_label": problem.clients[i].pickup.label, "delivery_label": problem.clients[i].delivery.label} for i in route],
            "pickup_order": [problem.clients[i].client for i in reversed(route)], "delivery_order": [problem.clients[i].client for i in route],
            "distance_km": distance / 1000, "duration_min": duration / 60, "weight_kg": packed.total_weight_kg,
            "linear_meters": packed.linear_meters, "occupied_length_m": packed.occupied_length_m,
            "loading_method_code": packed.method_code, "loading_method_name": packed.method_name, "loading_plan": packed.plan,
            "stops": _stops(problem, route), "geometry": geometry, "geometry_provider": provider,
        })
    return {
        "method": code, "method_name": name, "method_description": description,
        "objective_priority": "Nombre de véhicules, puis distance totale, puis longueur occupée",
        "vehicle_count": len(routes), "total_distance_km": total_distance / 1000, "total_duration_min": total_duration / 60,
        "total_linear_meters": total_linear, "total_weight_kg": sum(c.weight_kg for c in problem.clients),
        "total_handling_units": sum(c.quantity for c in problem.clients), "iterations": iterations, "elapsed_seconds": elapsed,
        "oracle_calls": oracle.calls, "oracle_cache_hits": oracle.cache_hits, "provider": problem.distance_matrix.provider,
        "routes": route_results, "objective": {"vehicle_count": len(routes), "distance_m": total_distance, "occupied_length_m": total_linear},
        "warnings": list(dict.fromkeys(warnings + ([problem.distance_matrix.warning] if problem.distance_matrix.warning else []))),
    }


def optimise_total(payload: dict[str, Any], catalog: tuple[VehicleVersion, ...]) -> dict[str, Any]:
    started = time.perf_counter(); problem = _parse_problem(payload, catalog); deadline = started + problem.time_limit_s
    split = started + problem.time_limit_s * .5
    alns_routes, alns_iterations, alns_oracle = solve_coupled_alns(problem, min(split, deadline)); alns_elapsed = time.perf_counter() - started
    genetic_started = time.perf_counter(); genetic_routes, genetic_iterations, genetic_oracle, genetic_method = solve_bilevel_genetic(problem, deadline); genetic_elapsed = time.perf_counter() - genetic_started
    solutions = [
        _build_solution(problem, alns_routes, alns_oracle, ALNS_ORACLE_METHODS, code="coupled_alns_3d_oracle", name="ALNS couplé + oracle de chargement LIFO", description="L’ALNS déplace des clients entre les tournées. Chaque insertion est acceptée uniquement si l’oracle produit un plan physique valide avec dimensions, poids, rotations et ordre LIFO. Un cache évite de recalculer les combinaisons déjà testées.", iterations=alns_iterations, elapsed=alns_elapsed),
        _build_solution(problem, genetic_routes, genetic_oracle, (genetic_method,), code="bilevel_genetic_3l_cvrp", name="Co-évolution génétique bi-niveau 3L-CVRP", description="Le chromosome fait évoluer l’ordre des clients et le moteur de rangement. Un décodeur Split découpe le parcours en tournées chargeables, en privilégiant le nombre de véhicules, puis les kilomètres et la longueur occupée.", iterations=genetic_iterations, elapsed=genetic_elapsed),
    ]
    solutions.sort(key=lambda s: (s["vehicle_count"], s["total_distance_km"], s["total_linear_meters"]))
    for rank, solution in enumerate(solutions, 1): solution["rank"] = rank
    return {
        "status": "completed", "engine_version": "0.10.0", "elapsed_seconds": time.perf_counter() - started,
        "solutions": solutions, "best_method": solutions[0]["method"],
        "model_note": "Adaptation gratuite du 3L-CVRP au modèle actuel d’AxioLoad. Chaque tournée effectue les enlèvements dans l’ordre inverse des livraisons, puis les livraisons LIFO. Le chargement reste au plancher, sans gerbage automatique.",
        "objective_note": "Comparaison lexicographique : réduire d’abord le nombre de véhicules, ensuite la distance totale, puis la longueur réellement occupée.",
    }
