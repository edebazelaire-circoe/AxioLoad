from __future__ import annotations

from .domain import Diagnostic, DomainError, OptimizationProblem


def install_unlimited_item_count() -> None:
    """Remove the former item limit and allow bounded runs up to 60 seconds.

    The optimization budget and packing heuristics remain responsible for keeping
    large cases bounded in time. All other domain validations are preserved.
    """
    if getattr(OptimizationProblem.__post_init__, "_axioload_unlimited", False):
        return

    def validate(self: OptimizationProblem) -> None:
        if not self.items:
            raise DomainError(Diagnostic("EMPTY_LOAD", "At least one cargo item is required"))
        if not self.vehicles:
            raise DomainError(Diagnostic("NO_VEHICLE", "At least one vehicle version is required"))
        if not 0 < self.budget_seconds <= 60:
            raise DomainError(Diagnostic("INVALID_TIME_BUDGET", "budget_seconds must be in ]0, 60]"))
        if not 1 <= self.requested_solutions <= 5:
            raise DomainError(Diagnostic("INVALID_SOLUTION_COUNT", "requested_solutions must be between 1 and 5"))
        ids = [item.id for item in self.items]
        if len(ids) != len(set(ids)):
            raise DomainError(Diagnostic("DUPLICATE_ITEM_ID", "Expanded cargo item ids must be unique"))

    validate._axioload_unlimited = True  # type: ignore[attr-defined]
    OptimizationProblem.__post_init__ = validate  # type: ignore[method-assign]
