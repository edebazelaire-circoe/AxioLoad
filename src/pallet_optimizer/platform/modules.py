from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Mapping


class ModuleKind(StrEnum):
    CORE = "core"
    WORKSPACE = "workspace"
    MANAGEMENT = "management"


class MigrationState(StrEnum):
    LEGACY = "legacy"
    FOUNDATION = "foundation"
    MODULAR = "modular"


@dataclass(frozen=True, slots=True)
class ModuleDescriptor:
    """Stable description of one AxioLoad module boundary."""

    module_id: str
    label: str
    kind: ModuleKind
    order: int
    depends_on: tuple[str, ...] = ()
    permission_prefixes: tuple[str, ...] = ()
    route_prefixes: tuple[str, ...] = ()
    backend_packages: tuple[str, ...] = ()
    frontend_assets: tuple[str, ...] = ()
    migration_state: MigrationState = MigrationState.LEGACY

    def __post_init__(self) -> None:
        if not self.module_id or not self.module_id.replace("_", "").isalnum():
            raise ValueError(f"Invalid module id: {self.module_id!r}")
        if not self.label.strip():
            raise ValueError(f"Module {self.module_id!r} requires a label")
        if self.order < 0:
            raise ValueError(f"Module {self.module_id!r} requires a non-negative order")
        for prefix in self.permission_prefixes:
            if not prefix or "." in prefix:
                raise ValueError(f"Invalid permission prefix {prefix!r} for {self.module_id}")
        for prefix in self.route_prefixes:
            if not prefix.startswith("/"):
                raise ValueError(f"Route prefix {prefix!r} must start with '/' for {self.module_id}")

    def is_available(self, permissions: Mapping[str, bool], *, is_super_admin: bool = False) -> bool:
        if self.kind is ModuleKind.CORE:
            return True
        if self.kind is ModuleKind.MANAGEMENT:
            return is_super_admin
        if not self.permission_prefixes:
            return True
        return any(
            enabled and permission.split(".", 1)[0] in self.permission_prefixes
            for permission, enabled in permissions.items()
        )

    def to_manifest(self, permissions: Mapping[str, bool], *, is_super_admin: bool = False) -> dict[str, object]:
        return {
            "id": self.module_id,
            "label": self.label,
            "kind": self.kind.value,
            "order": self.order,
            "depends_on": list(self.depends_on),
            "migration_state": self.migration_state.value,
            "available": self.is_available(permissions, is_super_admin=is_super_admin),
        }


class ModuleRegistry:
    """Validated registry used as the future composition root of AxioLoad."""

    def __init__(self, modules: Iterable[ModuleDescriptor]):
        self._modules = tuple(modules)
        self._by_id = {module.module_id: module for module in self._modules}
        self._validate()

    def _validate(self) -> None:
        if len(self._by_id) != len(self._modules):
            raise ValueError("Module ids must be unique")
        for module in self._modules:
            unknown = set(module.depends_on) - set(self._by_id)
            if unknown:
                raise ValueError(
                    f"Module {module.module_id!r} depends on unknown modules: {sorted(unknown)}"
                )
            if module.module_id in module.depends_on:
                raise ValueError(f"Module {module.module_id!r} cannot depend on itself")
        self._assert_acyclic()

    def _assert_acyclic(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(module_id: str) -> None:
            if module_id in visited:
                return
            if module_id in visiting:
                raise ValueError(f"Cyclic module dependency involving {module_id!r}")
            visiting.add(module_id)
            for dependency in self._by_id[module_id].depends_on:
                visit(dependency)
            visiting.remove(module_id)
            visited.add(module_id)

        for module_id in self._by_id:
            visit(module_id)

    def get(self, module_id: str) -> ModuleDescriptor:
        try:
            return self._by_id[module_id]
        except KeyError as exc:
            raise KeyError(f"Unknown AxioLoad module: {module_id}") from exc

    def ordered(self) -> tuple[ModuleDescriptor, ...]:
        return tuple(sorted(self._modules, key=lambda module: (module.order, module.module_id)))

    def manifest(
        self,
        permissions: Mapping[str, bool] | None = None,
        *,
        is_super_admin: bool = False,
    ) -> list[dict[str, object]]:
        permission_map = permissions or {}
        return [
            module.to_manifest(permission_map, is_super_admin=is_super_admin)
            for module in self.ordered()
        ]

    def topological_order(self) -> tuple[str, ...]:
        output: list[str] = []
        visited: set[str] = set()

        def visit(module_id: str) -> None:
            if module_id in visited:
                return
            for dependency in self._by_id[module_id].depends_on:
                visit(dependency)
            visited.add(module_id)
            output.append(module_id)

        for module in self.ordered():
            visit(module.module_id)
        return tuple(output)
