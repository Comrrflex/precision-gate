from __future__ import annotations

from hashlib import sha256

import pytest

from precision_gate import (
    ContractError,
    CustodyState,
    GateStatus,
    InformationState,
    PrecisionEvent,
    PromotionError,
    SourceReference,
    require_owner_decision,
)
from precision_gate.contracts import canonical_json


def test_event_detaches_nested_mutable_details() -> None:
    source = {"nested": {"items": ["one"]}}
    event = PrecisionEvent(
        event_id="evt-1",
        source_layer="tcria",
        information_id="info-1",
        information_state=InformationState.PENDING,
        custody_state=CustodyState.REFERENCED,
        summary="Pending synthetic item.",
        details=source,
    )

    source["nested"]["items"].append("two")

    assert event.details["nested"]["items"] == ("one",)
    with pytest.raises(TypeError):
        event.details["changed"] = True


def test_source_reference_requires_valid_sha256() -> None:
    with pytest.raises(ContractError, match="artifact_sha256"):
        SourceReference(
            source_id="source-1",
            source_ref="memory://source-1",
            artifact_sha256="not-a-digest",
        )


def test_canonical_json_rejects_nan_and_non_string_keys() -> None:
    with pytest.raises(ContractError):
        canonical_json({"value": float("nan")})
    with pytest.raises(ContractError):
        canonical_json({1: "not allowed"})


def test_promotion_requires_approved_gate_when_gate_is_present() -> None:
    event = PrecisionEvent(
        event_id="evt-2",
        source_layer="tcria",
        information_id="fact-1",
        information_state=InformationState.FACT_SUPPORTED,
        custody_state=CustodyState.HASHED,
        summary="Supported synthetic fact.",
        support_refs=("DOC-1",),
        sha256=sha256(b"fact").hexdigest(),
        promotable_as_fact=True,
        gate_status=GateStatus.CONDITIONAL,
    )

    with pytest.raises(PromotionError, match="approved"):
        event.assert_safe_promotion()


def test_owner_decision_event_is_a_visible_design_block() -> None:
    event = require_owner_decision("Mapping would weaken a TCRIA principle.")

    assert event.requires_human_review is True
    assert event.details["owner_decision_required"] is True
    assert event.details["design_blocked"] is True


def test_event_may_resolve_only_one_condition() -> None:
    with pytest.raises(ContractError, match="at most one"):
        PrecisionEvent(
            event_id="evt-bulk-resolution",
            source_layer="human_review",
            information_id="review-1",
            information_state=InformationState.ORIGINAL_PRESERVED,
            custody_state=CustodyState.REFERENCED,
            summary="Invalid bulk resolution.",
            support_refs=("REVIEW-BASIS-1",),
            resolves=("condition-1", "condition-2"),
        )


def test_human_review_flags_must_be_consistent() -> None:
    with pytest.raises(ContractError, match="completed"):
        PrecisionEvent(
            event_id="evt-review-conflict",
            source_layer="human_review",
            information_id="review-1",
            information_state=InformationState.PENDING,
            custody_state=CustodyState.REFERENCED,
            summary="Conflicting review state.",
            requires_human_review=True,
            human_review_state="completed",
        )
