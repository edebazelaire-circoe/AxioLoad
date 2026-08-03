from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from importlib import import_module
from typing import Callable

from .catalog import build_default_module_registry
from .modules import ModuleRegistry


class CompositionPhase(StrEnum):
    PERMISSIONS = "permissions"
    BACKEND = "backend"
    FRONTEND = "frontend"
    ROUTES = "routes"


_PHASE_ORDER = {
    CompositionPhase.PERMISSIONS: 0,
    CompositionPhase.BACKEND: 10,
    CompositionPhase.FRONTEND: 20,
    CompositionPhase.ROUTES: 30,
}


@dataclass(frozen=True, slots=True)
class RuntimeCompositionStep:
    name: str
    module_id: str
    phase: CompositionPhase
    target: str

    def resolve(self) -> Callable[[], None]:
        module_name, attribute = self.target.split(":", 1)
        module = import_module(module_name)
        installer = getattr(module, attribute)
        if not callable(installer):
            raise TypeError(f"Runtime composition target is not callable: {self.target}")
        return installer

    def to_manifest(self, executed: bool) -> dict[str, str | bool]:
        return {
            "name": self.name,
            "module_id": self.module_id,
            "phase": self.phase.value,
            "target": self.target,
            "executed": executed,
        }


RUNTIME_COMPOSITION_STEPS: tuple[RuntimeCompositionStep, ...] = (
    RuntimeCompositionStep(
        "document-permission-catalog",
        "document_control",
        CompositionPhase.PERMISSIONS,
        "pallet_optimizer.document_control_bootstrap:install_document_control_permissions",
    ),
    RuntimeCompositionStep(
        "document-permission-migration",
        "document_control",
        CompositionPhase.PERMISSIONS,
        "pallet_optimizer.document_control_permissions:install_document_control_permission_migration",
    ),
    RuntimeCompositionStep(
        "super-admin-routes",
        "core",
        CompositionPhase.BACKEND,
        "pallet_optimizer.super_admin_routes:install_super_admin_routes",
    ),
    RuntimeCompositionStep(
        "password-reset-system",
        "core",
        CompositionPhase.BACKEND,
        "pallet_optimizer.password_reset_system:install_password_reset_system",
    ),
    RuntimeCompositionStep(
        "fixed-test-accounts",
        "core",
        CompositionPhase.BACKEND,
        "pallet_optimizer.fixed_test_accounts:install_fixed_test_accounts",
    ),
    RuntimeCompositionStep(
        "client-grouping",
        "optimization",
        CompositionPhase.BACKEND,
        "pallet_optimizer.client_grouping:install_client_grouping",
    ),
    RuntimeCompositionStep(
        "optimization-portfolio",
        "optimization",
        CompositionPhase.BACKEND,
        "pallet_optimizer.optimization_portfolio:install_optimization_portfolio",
    ),
    RuntimeCompositionStep(
        "client-split-policy",
        "optimization",
        CompositionPhase.BACKEND,
        "pallet_optimizer.client_split_policy:install_client_split_policy",
    ),
    RuntimeCompositionStep(
        "unlimited-item-count",
        "optimization",
        CompositionPhase.BACKEND,
        "pallet_optimizer.scaling:install_unlimited_item_count",
    ),
    RuntimeCompositionStep(
        "admin-panel-assets",
        "management",
        CompositionPhase.FRONTEND,
        "pallet_optimizer.admin_panel:install_admin_panel_injection",
    ),
    RuntimeCompositionStep(
        "document-control-panel-assets",
        "document_control",
        CompositionPhase.FRONTEND,
        "pallet_optimizer.document_control_panel:install_document_control_panel_injection",
    ),
    RuntimeCompositionStep(
        "document-control-experience-assets",
        "document_control",
        CompositionPhase.FRONTEND,
        "pallet_optimizer.document_control_experience_panel:install_document_control_experience_injection",
    ),
    RuntimeCompositionStep(
        "optimization-experience-assets",
        "optimization",
        CompositionPhase.FRONTEND,
        "pallet_optimizer.optimization_experience_panel:install_optimization_experience_injection",
    ),
    RuntimeCompositionStep(
        "authentication-experience-assets",
        "core",
        CompositionPhase.FRONTEND,
        "pallet_optimizer.auth_experience_panel:install_auth_experience_injection",
    ),
    RuntimeCompositionStep(
        "password-reset-assets",
        "core",
        CompositionPhase.FRONTEND,
        "pallet_optimizer.password_reset_panel:install_password_reset_injection",
    ),
    RuntimeCompositionStep(
        "prompt-center-assets",
        "reference_data",
        CompositionPhase.FRONTEND,
        "pallet_optimizer.prompt_center_experience_panel:install_prompt_center_experience_injection",
    ),
    RuntimeCompositionStep(
        "document-control-routes",
        "document_control",
        CompositionPhase.ROUTES,
        "pallet_optimizer.document_control_bootstrap:install_document_control_routes",
    ),
    RuntimeCompositionStep(
        "document-control-system",
        "document_control",
        CompositionPhase.ROUTES,
        "pallet_optimizer.document_control_system:install_document_control_system",
    ),
    RuntimeCompositionStep(
        "prompt-center-system",
        "reference_data",
        CompositionPhase.ROUTES,
        "pallet_optimizer.platform.composition:_install_prompt_center_system",
    ),
)


def validate_runtime_composition(
    steps: tuple[RuntimeCompositionStep, ...] = RUNTIME_COMPOSITION_STEPS,
    registry: ModuleRegistry | None = None,
) -> None:
    names = [step.name for step in steps]
    if len(names) != len(set(names)):
        raise ValueError("Runtime composition step names must be unique")

    module_registry = registry or build_default_module_registry()
    module_ids = {module.module_id for module in module_registry.ordered()}
    missing_modules = sorted({step.module_id for step in steps} - module_ids)
    if missing_modules:
        raise ValueError(f"Unknown modules in runtime composition: {', '.join(missing_modules)}")

    phases = [_PHASE_ORDER[step.phase] for step in steps]
    if phases != sorted(phases):
        raise ValueError("Runtime composition phases must remain ordered")


@dataclass(slots=True)
class ApplicationContainer:
    module_registry: ModuleRegistry = field(default_factory=build_default_module_registry)
    steps: tuple[RuntimeCompositionStep, ...] = RUNTIME_COMPOSITION_STEPS
    _executed_steps: list[str] = field(default_factory=list, init=False, repr=False)
    _composed: bool = field(default=False, init=False, repr=False)
    _composing: bool = field(default=False, init=False, repr=False)

    @property
    def composed(self) -> bool:
        return self._composed

    @property
    def executed_steps(self) -> tuple[str, ...]:
        return tuple(self._executed_steps)

    def compose(self) -> "ApplicationContainer":
        if self._composed or self._composing:
            return self
        validate_runtime_composition(self.steps, self.module_registry)
        self._composing = True
        try:
            for step in self.steps:
                step.resolve()()
                self._executed_steps.append(step.name)
            self._composed = True
        finally:
            self._composing = False
        return self

    def manifest(self) -> list[dict[str, str | bool]]:
        executed = set(self._executed_steps)
        return [step.to_manifest(step.name in executed) for step in self.steps]


def _install_prompt_center_system() -> None:
    from fastapi import FastAPI

    prompt_center_system = import_module("pallet_optimizer.prompt_center_system")
    prompt_center_system._original_fastapi_init = FastAPI.__init__
    prompt_center_system.install_prompt_center_system()


_APPLICATION_CONTAINER = ApplicationContainer()


def compose_runtime() -> ApplicationContainer:
    return _APPLICATION_CONTAINER.compose()


def get_application_container() -> ApplicationContainer:
    return _APPLICATION_CONTAINER
