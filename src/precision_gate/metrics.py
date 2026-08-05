from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from precision_gate.custody_state import CustodyState, InformationState, PrecisionEvent


_SAFE_CUSTODY = {
    CustodyState.PRESERVED,
    CustodyState.REFERENCED,
    CustodyState.HASHED,
    CustodyState.MANIFESTED,
}


@dataclass(frozen=True)
class PrecisionMetrics:
    total_events: int
    supported: int
    pending: int
    blocked: int
    returned: int
    inferred: int
    human_review_required: int
    custody_integrity_rate: float
    operational_precision: float
    release_safety_rate: float
    unsafe_promotion_attempts: int

    def as_dict(self) -> dict[str, int | float]:
        return asdict(self)


def calculate_metrics(events: Iterable[PrecisionEvent]) -> PrecisionMetrics:
    """Calculate transparent operational metrics from classified events.

    ``operational_precision`` measures safely grounded supported facts among all
    fact-like candidates. ``release_safety_rate`` measures safe candidates among
    events marked released or promotable. These are engineering metrics, not a
    claim of legal, scientific, or absolute truth.
    """

    items = tuple(events)
    total = len(items)
    supported_items = [
        event
        for event in items
        if event.information_state is InformationState.FACT_SUPPORTED
    ]
    safe_supported = [event for event in supported_items if _is_safe_fact(event)]
    unsafe_fact_candidates = [event for event in supported_items if not _is_safe_fact(event)]
    unsafe_promotions = [
        event for event in items if event.promotable_as_fact and not _is_safe_fact(event)
    ]
    release_candidates = [
        event
        for event in items
        if event.promotable_as_fact or event.information_state is InformationState.RELEASED
    ]
    unsafe_releases = [event for event in release_candidates if not _release_is_safe(event)]

    custody_rate = _ratio(
        sum(event.custody_state in _SAFE_CUSTODY for event in items),
        total,
        empty=1.0,
    )
    operational_precision = _ratio(
        len(safe_supported),
        len(safe_supported) + len(unsafe_fact_candidates),
        empty=1.0,
    )
    release_safety = _ratio(
        len(release_candidates) - len(unsafe_releases),
        len(release_candidates),
        empty=1.0,
    )

    return PrecisionMetrics(
        total_events=total,
        supported=len(supported_items),
        pending=_count(items, InformationState.PENDING),
        blocked=_count(items, InformationState.BLOCKED),
        returned=_count(items, InformationState.RETURNED_FOR_CORRECTION),
        inferred=sum(
            event.information_state
            in {InformationState.API_INFERENCE, InformationState.API_OPINION}
            for event in items
        ),
        human_review_required=sum(event.requires_human_review for event in items),
        custody_integrity_rate=custody_rate,
        operational_precision=operational_precision,
        release_safety_rate=release_safety,
        unsafe_promotion_attempts=len(unsafe_promotions),
    )


def _is_safe_fact(event: PrecisionEvent) -> bool:
    return (
        event.information_state is InformationState.FACT_SUPPORTED
        and event.custody_state in _SAFE_CUSTODY
        and bool(event.support_refs)
    )


def _release_is_safe(event: PrecisionEvent) -> bool:
    if event.promotable_as_fact:
        return _is_safe_fact(event)
    return (
        event.information_state is InformationState.RELEASED
        and event.custody_state in _SAFE_CUSTODY
        and bool(event.support_refs)
    )


def _count(events: tuple[PrecisionEvent, ...], state: InformationState) -> int:
    return sum(event.information_state is state for event in events)


def _ratio(numerator: int, denominator: int, *, empty: float) -> float:
    if denominator == 0:
        return empty
    return round(numerator / denominator, 4)
