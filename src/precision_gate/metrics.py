from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from precision_gate.contracts import ContractError, to_jsonable

DEFAULT_VALIDATION_TARGET = 0.95


class MetricsError(ContractError):
    """Raised when validation labels or targets are invalid."""


@dataclass(frozen=True)
class ValidationCase:
    case_id: str
    expected_release_supported: bool
    actual_released: bool
    expected_human_review: bool
    actual_human_review_required: bool
    custody_chain_valid: bool
    finalized: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not self.case_id.strip():
            raise MetricsError("case_id must be a non-empty string.")
        object.__setattr__(self, "case_id", self.case_id.strip())
        for field_name in (
            "expected_release_supported",
            "actual_released",
            "expected_human_review",
            "actual_human_review_required",
            "custody_chain_valid",
            "finalized",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise MetricsError(f"{field_name} must be a boolean.")


@dataclass(frozen=True)
class MetricResult:
    name: str
    numerator: int
    denominator: int
    sample_size: int
    value: float | None
    target: float
    passed: bool | None
    status: str

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class ValidationSummary:
    target: float
    case_count: int
    metrics: tuple[MetricResult, ...]
    target_met: bool | None

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


def evaluate_validation(
    cases: tuple[ValidationCase, ...] | list[ValidationCase],
    *,
    target: float = DEFAULT_VALIDATION_TARGET,
) -> ValidationSummary:
    normalized_target = _target(target)
    normalized_cases = tuple(cases)
    if not all(isinstance(case, ValidationCase) for case in normalized_cases):
        raise MetricsError("cases must contain only ValidationCase values.")
    case_ids = [case.case_id for case in normalized_cases]
    if len(set(case_ids)) != len(case_ids):
        raise MetricsError("Validation case_id values must be unique.")

    released = [case for case in normalized_cases if case.actual_released]
    unsupported = [case for case in normalized_cases if not case.expected_release_supported]
    expected_reviews = [case for case in normalized_cases if case.expected_human_review]
    safe_finalizations = [
        case
        for case in normalized_cases
        if case.finalized
        and case.custody_chain_valid
        and (not case.actual_released or case.expected_release_supported)
        and (not case.expected_human_review or case.actual_human_review_required)
    ]
    sample_size = len(normalized_cases)
    metrics = (
        _metric(
            "supported_release_precision",
            sum(case.expected_release_supported for case in released),
            len(released),
            sample_size,
            normalized_target,
        ),
        _metric(
            "unsupported_promotion_prevention",
            sum(not case.actual_released for case in unsupported),
            len(unsupported),
            sample_size,
            normalized_target,
        ),
        _metric(
            "custody_chain_integrity",
            sum(case.custody_chain_valid for case in normalized_cases),
            sample_size,
            sample_size,
            normalized_target,
        ),
        _metric(
            "required_review_capture",
            sum(case.actual_human_review_required for case in expected_reviews),
            len(expected_reviews),
            sample_size,
            normalized_target,
        ),
        _metric(
            "safe_finalization_rate",
            len(safe_finalizations),
            sample_size,
            sample_size,
            normalized_target,
        ),
    )
    evaluated = [metric for metric in metrics if metric.passed is not None]
    target_met = None if not evaluated else all(metric.passed for metric in evaluated)
    return ValidationSummary(
        target=normalized_target,
        case_count=sample_size,
        metrics=metrics,
        target_met=target_met,
    )


def _metric(
    name: str,
    numerator: int,
    denominator: int,
    sample_size: int,
    target: float,
) -> MetricResult:
    if denominator == 0:
        return MetricResult(
            name=name,
            numerator=numerator,
            denominator=denominator,
            sample_size=sample_size,
            value=None,
            target=target,
            passed=None,
            status="not_evaluated",
        )
    value = numerator / denominator
    return MetricResult(
        name=name,
        numerator=numerator,
        denominator=denominator,
        sample_size=sample_size,
        value=value,
        target=target,
        passed=value >= target,
        status="passed" if value >= target else "below_target",
    )


def _target(value: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise MetricsError("target must be numeric.")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
        raise MetricsError("target must be between 0 and 1.")
    return normalized
