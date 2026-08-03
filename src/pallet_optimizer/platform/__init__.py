"""AxioLoad modular-platform contracts.

This package is deliberately independent from the business engines. It describes
module boundaries before the legacy code is migrated behind them.
"""

from .catalog import build_default_module_registry
from .modules import MigrationState, ModuleDescriptor, ModuleKind, ModuleRegistry

__all__ = [
    "MigrationState",
    "ModuleDescriptor",
    "ModuleKind",
    "ModuleRegistry",
    "build_default_module_registry",
]
