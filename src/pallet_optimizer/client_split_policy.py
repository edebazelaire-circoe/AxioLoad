from __future__ import annotations

from dataclasses import replace
from typing import Any

from .domain import Diagnostic, Severity


def install_client_split_policy() -> None:
    """Report a necessary destination split without invalidating the plan.

    Explicit keep_together_group violations stay errors through the historical
    KEEP_TOGETHER_SPLIT diagnostic. CLIENT_GROUP_SPLIT is emitted only for the
    automatic destination rule and therefore becomes a warning when the client
    physically requires several vehicles.
    """
    from . import engine

    current = engine.validate_compatibility
    if getattr(current, "_axioload_client_split_policy", False):
        return

    def validate_with_split_policy(*args: Any, **kwargs: Any) -> tuple[Diagnostic, ...]:
        diagnostics = current(*args, **kwargs)
        return tuple(
            replace(diagnostic, severity=Severity.WARNING)
            if diagnostic.code == "CLIENT_GROUP_SPLIT" else diagnostic
            for diagnostic in diagnostics
        )

    validate_with_split_policy._axioload_client_split_policy = True  # type: ignore[attr-defined]
    engine.validate_compatibility = validate_with_split_policy  # type: ignore[assignment]
