from __future__ import annotations

import traceback
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .domain import Diagnostic, DomainError, OptimizationResult, RunStatus, VehicleVersion
from .engine import OptimizationEngine
from .normalization import normalize_payload


class RunRepository(Protocol):
    def save_run(self, tenant_id: str, request_payload: Mapping[str, Any], result: OptimizationResult, channel: str = "interactive") -> str: ...


@dataclass(slots=True)
class OptimizationService:
    engine: OptimizationEngine
    repository: RunRepository | None = None
    vehicle_catalog_provider: Callable[[str], tuple[VehicleVersion, ...]] | None = None

    def execute(
        self,
        payload: Mapping[str, Any],
        *,
        tenant_id: str = "demo",
        interactive: bool = True,
        channel: str = "interactive",
    ) -> tuple[OptimizationResult, str | None]:
        try:
            catalog = self.vehicle_catalog_provider(tenant_id) if self.vehicle_catalog_provider else None
            problem = normalize_payload(
                payload,
                requested_solutions=5 if interactive else 1,
                catalog=catalog,
            )
            result = self.engine.optimize(problem)
        except DomainError as exc:
            result = OptimizationResult(
                status=RunStatus.INVALID_INPUT,
                solutions=(),
                diagnostics=(exc.diagnostic,),
                time_limit_reached=False,
                optimality_guaranteed=False,
                elapsed_seconds=0.0,
                seed=int(payload.get("seed", 1)) if isinstance(payload, Mapping) else 1,
                engine_version=self.engine.version,
            )
        except Exception as exc:  # defensive application boundary
            result = OptimizationResult(
                status=RunStatus.INTERNAL_ERROR,
                solutions=(),
                diagnostics=(Diagnostic(
                    "INTERNAL_ERROR",
                    "Le moteur a rencontré une erreur inattendue.",
                    details={"type": type(exc).__name__},
                ),),
                time_limit_reached=False,
                optimality_guaranteed=False,
                elapsed_seconds=0.0,
                seed=1,
                engine_version=self.engine.version,
            )
            traceback.print_exc()
        run_id = None
        if self.repository is not None:
            run_id = self.repository.save_run(tenant_id, payload, result, channel)
        return result, run_id
