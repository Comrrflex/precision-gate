from precision_gate.custody_state import CustodyState, InformationState, PrecisionEvent
from precision_gate.metrics import calculate_metrics


def test_metrics_are_transparent_and_non_absolute() -> None:
    events = (
        PrecisionEvent(
            event_id="safe",
            source_layer="tcria",
            information_id="safe",
            information_state=InformationState.FACT_SUPPORTED,
            custody_state=CustodyState.HASHED,
            summary="Safe supported fact.",
            support_refs=("EVD-1",),
            promotable_as_fact=True,
        ),
        PrecisionEvent(
            event_id="pending",
            source_layer="quinta_ordem",
            information_id="pending",
            information_state=InformationState.PENDING,
            custody_state=CustodyState.REFERENCED,
            summary="Pending point.",
            support_refs=("EVD-2",),
            requires_human_review=True,
        ),
    )

    metrics = calculate_metrics(events)

    assert metrics.total_events == 2
    assert metrics.supported == 1
    assert metrics.pending == 1
    assert metrics.operational_precision == 1.0
    assert metrics.release_safety_rate == 1.0
    assert metrics.custody_integrity_rate == 1.0
