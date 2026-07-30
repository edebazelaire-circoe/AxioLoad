from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Iterable


class Shape(StrEnum):
    PALLET = "pallet"
    BOX = "box"
    ROLL = "roll"
    CYLINDER = "cylinder"
    SHEET = "sheet"
    POST = "post"
    BAR_RECT = "bar_rect"
    BAR_CYL = "bar_cyl"
    IRREGULAR = "irregular"


class RunStatus(StrEnum):
    COMPLETED = "completed"
    COMPLETED_WITH_TIME_LIMIT = "completed_with_time_limit"
    INFEASIBLE = "infeasible"
    INVALID_INPUT = "invalid_input"
    INTERNAL_ERROR = "internal_error"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    message: str
    severity: Severity = Severity.ERROR
    field_path: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class DomainError(ValueError):
    def __init__(self, diagnostic: Diagnostic):
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


@dataclass(frozen=True, slots=True)
class Margins:
    left_mm: int = 0
    right_mm: int = 0
    front_mm: int = 0
    rear_mm: int = 0
    top_mm: int = 0

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if value < 0:
                raise DomainError(Diagnostic("NEGATIVE_MARGIN", f"{name} must be non-negative", field_path=name))


@dataclass(frozen=True, slots=True)
class Rect:
    x_mm: int
    y_mm: int
    width_mm: int
    length_mm: int
    height_mm: int = 0
    id: str = ""

    def __post_init__(self) -> None:
        if self.x_mm < 0 or self.y_mm < 0 or self.width_mm <= 0 or self.length_mm <= 0 or self.height_mm < 0:
            raise DomainError(Diagnostic("INVALID_RECT", "Rectangle dimensions and coordinates are invalid"))


@dataclass(frozen=True, slots=True)
class ZoneSpec:
    id: str
    rect: Rect

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise DomainError(Diagnostic("INVALID_ZONE", "Zone id is required"))


@dataclass(frozen=True, slots=True)
class AxleSpec:
    id: str
    position_mm: int
    max_load_kg: float

    def __post_init__(self) -> None:
        if self.position_mm < 0 or self.max_load_kg <= 0:
            raise DomainError(Diagnostic("INVALID_AXLE", f"Invalid axle {self.id}"))


@dataclass(frozen=True, slots=True)
class VehicleVersion:
    model_id: str
    version: int
    name: str
    interior_length_mm: int
    interior_width_mm: int
    interior_height_mm: int
    linear_meter_width_mm: int
    payload_kg: float
    door_width_mm: int
    door_height_mm: int
    axles: tuple[AxleSpec, ...]
    obstacles: tuple[Rect, ...] = ()
    zones: tuple[ZoneSpec, ...] = ()
    source_note: str = ""

    def __post_init__(self) -> None:
        dimensions = (self.interior_length_mm, self.interior_width_mm, self.interior_height_mm,
                      self.linear_meter_width_mm, self.door_width_mm, self.door_height_mm)
        if any(v <= 0 for v in dimensions) or self.payload_kg <= 0:
            raise DomainError(Diagnostic("INVALID_VEHICLE", f"Invalid vehicle version {self.model_id}@{self.version}"))
        if self.door_width_mm > self.interior_width_mm or self.door_height_mm > self.interior_height_mm:
            raise DomainError(Diagnostic("INVALID_OPENING", "Door opening cannot exceed interior dimensions"))
        if len(self.axles) not in (0, 2):
            raise DomainError(Diagnostic("AXLE_MODEL_UNSUPPORTED", "V1 supports zero or two axle support points"))
        if len(self.axles) == 2 and self.axles[0].position_mm >= self.axles[1].position_mm:
            raise DomainError(Diagnostic("INVALID_AXLE_ORDER", "Axles must be ordered from front support to rear support"))

    @property
    def version_id(self) -> str:
        return f"{self.model_id}@{self.version}"


@dataclass(frozen=True, slots=True)
class CargoItem:
    id: str
    source_id: str
    input_index: int
    shape: Shape
    length_mm: int
    width_mm: int
    height_mm: int
    weight_kg: float
    destination: str
    delivery_order: int
    rotation_allowed: bool = True
    margins: Margins = Margins()
    compatibility_tags: tuple[str, ...] = ()
    incompatible_tags: tuple[str, ...] = ()
    keep_together_group: str | None = None
    separate_group: str | None = None
    separation_mm: int = 0
    zone: str | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise DomainError(Diagnostic("MISSING_ITEM_ID", "Cargo item id is required", field_path="id"))
        if min(self.length_mm, self.width_mm, self.height_mm) <= 0:
            raise DomainError(Diagnostic("INVALID_DIMENSION", f"Item {self.id} dimensions must be positive"))
        if self.weight_kg <= 0:
            raise DomainError(Diagnostic("INVALID_WEIGHT", f"Item {self.id} weight must be positive"))
        if self.delivery_order < 0 or self.input_index < 0 or self.separation_mm < 0:
            raise DomainError(Diagnostic("INVALID_ORDER_OR_SEPARATION", f"Item {self.id} has invalid ordering data"))

    def oriented_dimensions(self, orientation_deg: int) -> tuple[int, int, int, int]:
        if orientation_deg not in (0, 90):
            raise DomainError(Diagnostic("INVALID_ROTATION", "Only 0 and 90 degree rotations are supported"))
        if orientation_deg == 90 and not self.rotation_allowed:
            raise DomainError(Diagnostic("ROTATION_LOCKED", f"Item {self.id} cannot rotate"))
        actual_length, actual_width = (self.length_mm, self.width_mm) if orientation_deg == 0 else (self.width_mm, self.length_mm)
        envelope_length = actual_length + self.margins.front_mm + self.margins.rear_mm
        envelope_width = actual_width + self.margins.left_mm + self.margins.right_mm
        return actual_length, actual_width, envelope_length, envelope_width


@dataclass(frozen=True, slots=True)
class VehiclePolicy:
    mode: str = "auto"
    forced_vehicle_id: str | None = None
    max_vehicles: int = 5

    def __post_init__(self) -> None:
        if self.mode not in {"auto", "forced"}:
            raise DomainError(Diagnostic("INVALID_VEHICLE_POLICY", "Vehicle policy mode must be auto or forced"))
        if self.mode == "forced" and not self.forced_vehicle_id:
            raise DomainError(Diagnostic("MISSING_FORCED_VEHICLE", "forced_vehicle_id is required"))
        if self.max_vehicles < 1:
            raise DomainError(Diagnostic("INVALID_MAX_VEHICLES", "max_vehicles must be at least 1"))


@dataclass(frozen=True, slots=True)
class OptimizationProblem:
    items: tuple[CargoItem, ...]
    vehicles: tuple[VehicleVersion, ...]
    vehicle_policy: VehiclePolicy = VehiclePolicy()
    seed: int = 1
    budget_seconds: float = 30.0
    requested_solutions: int = 5

    def __post_init__(self) -> None:
        if not self.items:
            raise DomainError(Diagnostic("EMPTY_LOAD", "At least one cargo item is required"))
        if len(self.items) > 100:
            raise DomainError(Diagnostic("TOO_MANY_ITEMS", "V1 supports at most 100 expanded objects"))
        if not self.vehicles:
            raise DomainError(Diagnostic("NO_VEHICLE", "At least one vehicle version is required"))
        if not 0 < self.budget_seconds <= 30:
            raise DomainError(Diagnostic("INVALID_TIME_BUDGET", "budget_seconds must be in ]0, 30]"))
        if not 1 <= self.requested_solutions <= 5:
            raise DomainError(Diagnostic("INVALID_SOLUTION_COUNT", "requested_solutions must be between 1 and 5"))
        ids = [item.id for item in self.items]
        if len(ids) != len(set(ids)):
            raise DomainError(Diagnostic("DUPLICATE_ITEM_ID", "Expanded cargo item ids must be unique"))


@dataclass(frozen=True, slots=True)
class Placement:
    item_id: str
    source_id: str
    destination: str
    delivery_order: int
    x_mm: int
    y_mm: int
    z_mm: int
    orientation_deg: int
    actual_length_mm: int
    actual_width_mm: int
    actual_height_mm: int
    envelope_length_mm: int
    envelope_width_mm: int
    weight_kg: float

    @property
    def rect(self) -> Rect:
        return Rect(self.x_mm, self.y_mm, self.envelope_width_mm, self.envelope_length_mm,
                    self.actual_height_mm, self.item_id)


@dataclass(frozen=True, slots=True)
class WeightMetrics:
    total_weight_kg: float
    center_of_gravity_y_mm: float
    axle_loads_kg: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True, slots=True)
class VehiclePlan:
    vehicle_version_id: str
    vehicle_name: str
    placements: tuple[Placement, ...]
    linear_meters: float
    occupied_length_m: float
    weight: WeightMetrics
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class Solution:
    id: str
    rank: int
    vehicle_plans: tuple[VehiclePlan, ...]
    total_linear_meters: float
    occupied_length_m: float
    vehicle_count: int
    axle_penalty: float
    balance_penalty: float
    advantages: tuple[str, ...] = ()
    disadvantages: tuple[str, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    method_code: str = ""
    method_name: str = ""
    method_description: str = ""


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    status: RunStatus
    solutions: tuple[Solution, ...]
    diagnostics: tuple[Diagnostic, ...]
    time_limit_reached: bool
    optimality_guaranteed: bool
    elapsed_seconds: float
    seed: int
    engine_version: str = "0.10.0"


def to_primitive(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {k: to_primitive(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): to_primitive(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_primitive(v) for v in value]
    return value


def flatten_diagnostics(groups: Iterable[Iterable[Diagnostic]]) -> tuple[Diagnostic, ...]:
    return tuple(d for group in groups for d in group)
