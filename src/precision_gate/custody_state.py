from __future__ import annotations

from precision_gate.contracts import (
    CustodyState,
    HumanReviewState,
    InformationState,
    PrecisionEvent,
    SourceLayer,
)


def require_owner_decision(reason: str) -> PrecisionEvent:
    """Create a design-stop event when a TCRIA principle cannot be preserved."""

    return PrecisionEvent(
        event_id="owner-decision-required",
        source_layer=SourceLayer.PRECISION_GATE_DESIGN,
        information_id="architecture",
        information_state=InformationState.HUMAN_REVIEW_REQUIRED,
        custody_state=CustodyState.UNKNOWN,
        summary=reason,
        requires_human_review=True,
        promotable_as_fact=False,
        details={"owner_decision_required": True, "design_blocked": True},
        human_review_state=HumanReviewState.REQUIRED,
    )
