from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class InformationState(str, Enum):
    """State carried by an information item as the audit trail continues."""

    ORIGINAL_PRESERVED = "original_preserved"
    DERIVED_COPY = "derived_copy"
    EXTRACTION_FAILED = "extraction_failed"
    OCR_FAILED = "ocr_failed"
    UNREADABLE = "unreadable"
    NULL_RESULT = "null_result"
    API_OPINION = "api_opinion"
    API_INFERENCE = "api_inference"
    TCRIA_SIGNAL = "tcria_signal"
    ALLEGATION = "allegation"
    HYPOTHESIS = "hypothesis"
    FACT_SUPPORTED = "fact_supported"
    PENDING = "pending"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    RETURNED_FOR_CORRECTION = "returned_for_correction"
    BLOCKED = "blocked"
    RELEASED = "released"


class CustodyState(str, Enum):
    """Custody condition of the information item."""

    PRESERVED = "preserved"
    DERIVED = "derived"
    REFERENCED = "referenced"
    HASHED = "hashed"
    MANIFESTED = "manifested"
    BROKEN = "broken"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PrecisionEvent:
    """One step in the mobile custody trail.

    The event does not decide the final human outcome. It records what happened,
    which layer produced it, and how far the information may be promoted.
    """

    event_id: str
    source_layer: str
    information_id: str
    information_state: InformationState
    custody_state: CustodyState
    summary: str
    support_refs: tuple[str, ...] = ()
    sha256: str | None = None
    requires_human_review: bool = False
    promotable_as_fact: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def assert_safe_promotion(self) -> None:
        """Raise when an event is incorrectly marked as promotable.

        Promotion is allowed only for explicitly supported fact states with preserved,
        referenced, hashed, or manifested custody.
        """

        if not self.promotable_as_fact:
            return
        if self.information_state is not InformationState.FACT_SUPPORTED:
            raise ValueError("Only fact_supported events may be promotable as fact.")
        if self.custody_state not in {
            CustodyState.PRESERVED,
            CustodyState.REFERENCED,
            CustodyState.HASHED,
            CustodyState.MANIFESTED,
        }:
            raise ValueError("Promotable fact requires preserved or traceable custody.")
        if not self.support_refs:
            raise ValueError("Promotable fact requires explicit support_refs.")


def require_owner_decision(reason: str) -> PrecisionEvent:
    """Create a design-stop event when a TCRIA principle cannot be preserved."""

    return PrecisionEvent(
        event_id="owner-decision-required",
        source_layer="precision_gate_design",
        information_id="architecture",
        information_state=InformationState.HUMAN_REVIEW_REQUIRED,
        custody_state=CustodyState.UNKNOWN,
        summary=reason,
        requires_human_review=True,
        promotable_as_fact=False,
        details={"owner_decision_required": True},
    )
