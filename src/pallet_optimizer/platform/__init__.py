"""AxioLoad modular-platform contracts.

This package is deliberately independent from the business engines. It describes
module boundaries and the explicit runtime composition used during migration.
"""

from .catalog import build_default_module_registry
from .composition import (
    ApplicationContainer,
    CompositionPhase,
    RuntimeCompositionStep,
    compose_runtime,
    get_application_container,
    validate_runtime_composition,
)
from .modules import MigrationState, ModuleDescriptor, ModuleKind, ModuleRegistry

__all__ = [
    "ApplicationContainer",
    "CompositionPhase",
    "MigrationState",
    "ModuleDescriptor",
    "ModuleKind",
    "ModuleRegistry",
    "RuntimeCompositionStep",
    "build_default_module_registry",
    "compose_runtime",
    "get_application_container",
    "validate_runtime_composition",
]
