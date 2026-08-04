from __future__ import annotations

from dataclasses import replace
from typing import Any

from .domain import Diagnostic, OptimizationResult, RunStatus, Severity
from .engine import OptimizationEngine

_INSTALLED = False


def _portfolio_outcomes(result: OptimizationResult) -> list[dict[str, Any]]:
    for diagnostic in result.diagnostics:
        if diagnostic.code == "METHOD_PORTFOLIO":
            outcomes = diagnostic.details.get("outcomes")
            if isinstance(outcomes, list):
                return [dict(outcome) for outcome in outcomes if isinstance(outcome, dict)]
    return []


def _make_non_blocking(diagnostic: Diagnostic) -> Diagnostic:
    if diagnostic.severity != Severity.ERROR:
        return diagnostic
    return replace(
        diagnostic,
        severity=Severity.WARNING,
        details={
            **diagnostic.details,
            "original_severity": Severity.ERROR.value,
            "non_blocking": True,
            "discarded_candidate": True,
        },
    )


def _partial_success_summary(result: OptimizationResult) -> Diagnostic | None:
    outcomes = _portfolio_outcomes(result)
    failed = [
        outcome
        for outcome in outcomes
        if outcome.get("status") in {"failure", "timeout", "not_run"}
    ]
    if not failed:
        return None
    successful = [outcome for outcome in outcomes if outcome.get("status") == "success"]
    failed_names = [str(outcome.get("name") or outcome.get("code") or "Modèle") for outcome in failed]
    return Diagnostic(
        "PORTFOLIO_PARTIAL_SUCCESS",
        (
            f"{len(successful)} modèle(s) ont produit une solution valide. "
            f"Les {len(failed)} autre(s) modèle(s) n'ont pas abouti, sans bloquer le résultat retenu."
        ),
        severity=Severity.WARNING,
        details={
            "successful_models": [outcome.get("code") for outcome in successful],
            "failed_models": [outcome.get("code") for outcome in failed],
            "failed_model_names": failed_names,
            "result_accepted": True,
        },
    )


def install_partial_model_success_policy() -> None:
    """Accept the best valid solution even when another model fails.

    Top-level errors produced by discarded model attempts are useful diagnostics,
    but they must not invalidate a result when at least one independently
    validated solution exists. Selected-solution diagnostics remain untouched.
    """

    global _INSTALLED
    if _INSTALLED:
        return

    original_optimize = OptimizationEngine.optimize
    if getattr(original_optimize, "_axioload_partial_model_success", False):
        _INSTALLED = True
        return

    def optimize_with_partial_success(self: OptimizationEngine, problem: Any) -> OptimizationResult:
        result = original_optimize(self, problem)
        if not result.solutions:
            return result

        diagnostics = [_make_non_blocking(diagnostic) for diagnostic in result.diagnostics]
        summary = _partial_success_summary(result)
        if summary and not any(diagnostic.code == summary.code for diagnostic in diagnostics):
            diagnostics.append(summary)

        status = (
            RunStatus.COMPLETED_WITH_TIME_LIMIT
            if result.time_limit_reached
            else RunStatus.COMPLETED
        )
        return replace(result, status=status, diagnostics=tuple(diagnostics))

    optimize_with_partial_success._axioload_partial_model_success = True  # type: ignore[attr-defined]
    OptimizationEngine.optimize = optimize_with_partial_success  # type: ignore[method-assign]
    _INSTALLED = True
