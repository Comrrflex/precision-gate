from __future__ import annotations

from hashlib import sha256

from precision_gate import (
    CustodyState,
    GateStatus,
    InformationState,
    PrecisionEvent,
    SourceLayer,
)
from precision_gate.coherence import CoherenceEvaluator, SupportTier


def _event(
    event_id: str,
    information_id: str,
    state: InformationState,
    *,
    source: SourceLayer = SourceLayer.TCRIA,
    details: dict | None = None,
    support_refs: tuple[str, ...] = (),
    review: bool = False,
) -> PrecisionEvent:
    return PrecisionEvent(
        event_id=event_id,
        source_layer=source,
        information_id=information_id,
        information_state=state,
        custody_state=CustodyState.HASHED,
        summary=f"Synthetic {event_id}.",
        support_refs=support_refs,
        sha256=sha256(event_id.encode()).hexdigest(),
        requires_human_review=review,
        details=details or {"source_partition": "non_accusation_set"},
    )


def test_supported_fact_is_selected_as_best_operational_reading() -> None:
    assessment = CoherenceEvaluator().evaluate(
        [
            _event("hypothesis", "h-1", InformationState.HYPOTHESIS),
            _event(
                "fact",
                "f-1",
                InformationState.FACT_SUPPORTED,
                support_refs=("DOC-1",),
            ),
        ]
    )

    assert assessment.best_supported_event_ids == ("fact",)
    assert assessment.support_tier is SupportTier.SUPPORTED
    assert assessment.conflict is False


def test_api_unseen_claim_against_tcria_trail_emits_alert() -> None:
    tcria = _event("tcria-1", "info-1", InformationState.PENDING)
    api = _event(
        "api-1",
        "api-output",
        InformationState.API_OPINION,
        source=SourceLayer.API,
        review=True,
        details={
            "claim_relations": (
                {"information_id": "info-1", "relation": "unseen"},
            )
        },
    )

    assessment = CoherenceEvaluator().evaluate([tcria, api])

    assert any(
        alert.code == "OBSERVED_ITEM_DESCRIBED_AS_UNSEEN"
        for alert in assessment.alerts
    )


def test_supported_fact_blocked_by_source_gate_is_not_a_supported_reading() -> None:
    event = PrecisionEvent(
        event_id="blocked-fact",
        source_layer=SourceLayer.TCRIA,
        information_id="fact-1",
        information_state=InformationState.FACT_SUPPORTED,
        custody_state=CustodyState.HASHED,
        summary="Synthetic fact blocked by its source gate.",
        support_refs=("DOC-1",),
        sha256=sha256(b"blocked-fact").hexdigest(),
        requires_human_review=True,
        details={
            "source_partition": "non_accusation_set",
            "record_gate_event_ids": ("source-gate-block",),
        },
        gate_status=GateStatus.BLOCKED,
    )

    assessment = CoherenceEvaluator().evaluate([event])

    assert assessment.support_tier is SupportTier.UNSUPPORTED
    assert any(
        alert.code == "FACT_NOT_APPROVED_BY_SOURCE_GATE"
        for alert in assessment.alerts
    )


def test_documented_and_unexplained_omissions_are_distinguished() -> None:
    documented = _event(
        "doc-1",
        "info-1",
        InformationState.PENDING,
        details={
            "source_partition": "non_accusation_set",
            "trace_observation": {
                "observed": True,
                "mentioned": False,
                "omission_reason": "Outside the mission scope.",
            },
        },
    )
    unexplained = _event(
        "doc-2",
        "info-2",
        InformationState.PENDING,
        review=True,
        details={
            "source_partition": "non_accusation_set",
            "trace_observation": {"observed": True, "mentioned": False},
        },
    )

    assessment = CoherenceEvaluator().evaluate([documented, unexplained])
    codes = {alert.code for alert in assessment.alerts}

    assert "DOCUMENTED_OMISSION" in codes
    assert "UNEXPLAINED_OMISSION" in codes


def test_explicitly_conflicting_supported_readings_require_human_review() -> None:
    first = _event(
        "fact-1",
        "info-1",
        InformationState.FACT_SUPPORTED,
        support_refs=("DOC-1",),
        details={
            "source_partition": "non_accusation_set",
            "contradicts_information_ids": ("info-2",),
        },
    )
    second = _event(
        "fact-2",
        "info-2",
        InformationState.FACT_SUPPORTED,
        support_refs=("DOC-2",),
    )

    assessment = CoherenceEvaluator().evaluate([first, second])

    assert assessment.conflict is True
    assert assessment.requires_human_review is True
    assert any(
        alert.code == "CONFLICTING_SUPPORTED_READINGS"
        for alert in assessment.alerts
    )
