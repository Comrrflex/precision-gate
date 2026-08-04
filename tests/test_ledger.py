from __future__ import annotations

from copy import deepcopy
from hashlib import sha256

import pytest

from precision_gate import (
    CustodyState,
    HumanReviewState,
    InformationState,
    PrecisionEvent,
    SourceLayer,
)
from precision_gate.ledger import CustodyTrail, LedgerError


def _event(
    event_id: str,
    *,
    information_id: str = "info-1",
    state: InformationState = InformationState.PENDING,
    review: bool = False,
    support_refs: tuple[str, ...] = (),
    resolves: tuple[str, ...] = (),
    promotable: bool = False,
) -> PrecisionEvent:
    return PrecisionEvent(
        event_id=event_id,
        source_layer=SourceLayer.TCRIA,
        information_id=information_id,
        information_state=state,
        custody_state=CustodyState.HASHED,
        summary=f"Synthetic event {event_id}.",
        support_refs=support_refs,
        sha256=sha256(event_id.encode()).hexdigest(),
        requires_human_review=review,
        promotable_as_fact=promotable,
        resolves=resolves,
    )


def test_chain_verifies_and_detects_tampering_reordering_and_removal() -> None:
    trail = CustodyTrail("trace-1", created_at="2026-08-04T10:00:00Z")
    trail.append(_event("evt-1"))
    trail.append(_event("evt-2"))
    payload = trail.to_dict()

    assert trail.verify().valid is True

    tampered = deepcopy(payload)
    tampered["receipts"][0]["event"]["summary"] = "Changed."
    assert CustodyTrail.verify_payload(tampered).valid is False

    reordered = deepcopy(payload)
    reordered["receipts"].reverse()
    assert CustodyTrail.verify_payload(reordered).valid is False

    removed = deepcopy(payload)
    removed["receipts"].pop()
    assert CustodyTrail.verify_payload(removed).valid is False


def test_duplicate_event_and_wrong_trace_are_rejected() -> None:
    trail = CustodyTrail("trace-1")
    trail.append(_event("evt-1"))

    with pytest.raises(LedgerError, match="Duplicate"):
        trail.append(_event("evt-1"))
    with pytest.raises(LedgerError, match="does not match"):
        trail.append(
            PrecisionEvent(
                **{
                    **_event("evt-2").__dict__,
                    "trace_id": "another-trace",
                }
            )
        )


def test_block_remains_active_until_explicit_resolution() -> None:
    trail = CustodyTrail("trace-1")
    trail.append(
        _event(
            "block-1",
            state=InformationState.BLOCKED,
            review=True,
        )
    )

    with pytest.raises(ValueError, match="unresolved blocks"):
        trail.append(
            _event(
                "fact-1",
                state=InformationState.FACT_SUPPORTED,
                support_refs=("DOC-1",),
                promotable=True,
            )
        )

    trail.append(
        PrecisionEvent(
            event_id="human-1",
            source_layer=SourceLayer.HUMAN_REVIEW,
            information_id="review-1",
            information_state=InformationState.ORIGINAL_PRESERVED,
            custody_state=CustodyState.REFERENCED,
            summary="Human resolved the synthetic block.",
            resolves=("block-1",),
            human_review_state=HumanReviewState.COMPLETED,
        )
    )
    trail.append(
        _event(
            "fact-2",
            state=InformationState.FACT_SUPPORTED,
            support_refs=("DOC-1",),
            promotable=True,
        )
    )

    assert trail.active_blocks == ()
    assert trail.active_reviews == ()


def test_read_failure_resolution_requires_replacement_support() -> None:
    trail = CustodyTrail("trace-1")
    trail.append(
        _event(
            "ocr-failure",
            state=InformationState.OCR_FAILED,
            review=True,
        )
    )

    with pytest.raises(LedgerError, match="support_refs"):
        trail.append(
            PrecisionEvent(
                event_id="human-without-support",
                source_layer=SourceLayer.HUMAN_REVIEW,
                information_id="review-1",
                information_state=InformationState.ORIGINAL_PRESERVED,
                custody_state=CustodyState.REFERENCED,
                summary="Attempted resolution.",
                resolves=("ocr-failure",),
                human_review_state=HumanReviewState.COMPLETED,
            )
        )

    trail.append(
        PrecisionEvent(
            event_id="human-with-support",
            source_layer=SourceLayer.HUMAN_REVIEW,
            information_id="review-1",
            information_state=InformationState.ORIGINAL_PRESERVED,
            custody_state=CustodyState.REFERENCED,
            summary="Replacement reading reviewed by a human.",
            support_refs=("HUMAN-READ-1",),
            resolves=("ocr-failure",),
            human_review_state=HumanReviewState.COMPLETED,
        )
    )

    assert trail.active_read_failures == ()
