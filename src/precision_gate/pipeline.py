from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from precision_gate._validation import strict_snapshot
from precision_gate.api_output_adapter import APIOutputAdapter
from precision_gate.coherence import CoherenceAssessment, CoherenceEvaluator
from precision_gate.contracts import (
    CustodyState,
    GateStatus,
    HumanReviewState,
    InformationState,
    PrecisionEvent,
    SourceLayer,
    to_jsonable,
    utc_now,
)
from precision_gate.ledger import CustodyTrail
from precision_gate.quinta_adapter import QuintaExecutionContextAdapter
from precision_gate.tcria_adapter import TCRIAAdaptation, TCRIAAuditBundleAdapter


class PipelineError(RuntimeError):
    """Raised when callers attempt an invalid Precision Gate stage transition."""


class PipelineStage(str, Enum):
    CREATED = "created"
    TCRIA_OBSERVED = "tcria_observed"
    API_OBSERVED = "api_observed"
    QUINTA_CONTEXT_READY = "quinta_context_ready"
    QUINTA_DECIDED = "quinta_decided"
    HUMAN_REVIEWED = "human_reviewed"
    FINALIZED = "finalized"


class HumanReviewOutcome(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    RETURNED_FOR_CORRECTION = "returned_for_correction"


@dataclass(frozen=True)
class PipelineFinalization:
    trace_id: str
    released: bool
    gate_status: GateStatus
    human_outcome: HumanReviewOutcome
    final_chain_sha256: str
    assessment: CoherenceAssessment

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


class PrecisionGatePipeline:
    """Orchestrate external handoffs without embedding their decision logic."""

    def __init__(
        self,
        trace_id: str,
        *,
        created_at: str | None = None,
        clock: Callable[[], str] = utc_now,
        tcria_adapter: TCRIAAuditBundleAdapter | None = None,
        api_adapter: APIOutputAdapter | None = None,
        quinta_adapter: QuintaExecutionContextAdapter | None = None,
        coherence_evaluator: CoherenceEvaluator | None = None,
    ) -> None:
        self.trace_id = trace_id
        self.clock = clock
        self.trail = CustodyTrail(trace_id, created_at=created_at or clock())
        self.tcria_adapter = tcria_adapter or TCRIAAuditBundleAdapter()
        self.api_adapter = api_adapter or APIOutputAdapter()
        self.quinta_adapter = quinta_adapter or QuintaExecutionContextAdapter()
        self.coherence_evaluator = coherence_evaluator or CoherenceEvaluator()
        self.stage = PipelineStage.CREATED
        self._quinta_payload: dict[str, Any] | None = None
        self._quinta_decision_event: PrecisionEvent | None = None
        self._human_events: list[PrecisionEvent] = []
        self._human_outcome: HumanReviewOutcome | None = None
        self._finalization: PipelineFinalization | None = None

    @property
    def finalization(self) -> PipelineFinalization | None:
        return self._finalization

    def ingest_tcria(
        self,
        bundle: Mapping[str, Any],
        *,
        source_id: str,
        source_ref: str,
        source_artifact_sha256: str | None = None,
        producer_revision: str | None = None,
        observed_at: str | None = None,
    ) -> TCRIAAdaptation:
        self._require_stage(PipelineStage.CREATED)
        adaptation = self.tcria_adapter.adapt(
            bundle,
            trace_id=self.trace_id,
            observed_at=observed_at or self.clock(),
            source_id=source_id,
            source_ref=source_ref,
            source_artifact_sha256=source_artifact_sha256,
            producer_revision=producer_revision,
        )
        for event in adaptation.events:
            self.trail.append(event)
        self.stage = PipelineStage.TCRIA_OBSERVED
        return adaptation

    def observe_api(
        self,
        envelope: Mapping[str, Any],
        *,
        observed_at: str | None = None,
    ) -> PrecisionEvent:
        self._require_stage(PipelineStage.TCRIA_OBSERVED, PipelineStage.API_OBSERVED)
        event = self.api_adapter.adapt(
            envelope,
            trace_id=self.trace_id,
            observed_at=observed_at or self.clock(),
        )
        known_refs = {
            reference
            for existing in self.trail.events
            for reference in (
                existing.event_id,
                existing.information_id,
                *(
                    (existing.source_reference.source_id,)
                    if existing.source_reference is not None
                    else ()
                ),
            )
        }
        unknown_refs = sorted(set(event.support_refs) - known_refs)
        if unknown_refs:
            raise PipelineError(
                "API input_refs are not present in the observed trail: "
                + ", ".join(unknown_refs)
                + "."
            )
        appended = self.trail.append(event).event
        self.stage = PipelineStage.API_OBSERVED
        return appended

    def build_quinta_context(
        self,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_stage(PipelineStage.TCRIA_OBSERVED, PipelineStage.API_OBSERVED)
        self._quinta_payload = self.quinta_adapter.build_payload(
            self.trail.events,
            execution_id=self.trace_id,
            metadata=metadata,
        )
        self.stage = PipelineStage.QUINTA_CONTEXT_READY
        return strict_snapshot(self._quinta_payload, name="Quinta payload")

    def record_quinta_decision(
        self,
        decision: Mapping[str, Any],
        *,
        source_ref: str | None = None,
        observed_at: str | None = None,
    ) -> PrecisionEvent:
        self._require_stage(PipelineStage.QUINTA_CONTEXT_READY)
        event = self.quinta_adapter.adapt_decision(
            decision,
            trace_id=self.trace_id,
            observed_at=observed_at or self.clock(),
            source_ref=source_ref,
        )
        self._quinta_decision_event = self.trail.append(event).event
        self.stage = PipelineStage.QUINTA_DECIDED
        return self._quinta_decision_event

    def record_human_review(
        self,
        *,
        review_id: str,
        reviewer_ref: str,
        outcome: HumanReviewOutcome | str,
        summary: str,
        resolves: Sequence[str] = (),
        support_refs: Sequence[str] = (),
        observed_at: str | None = None,
    ) -> PrecisionEvent:
        self._require_stage(PipelineStage.QUINTA_DECIDED, PipelineStage.HUMAN_REVIEWED)
        if not isinstance(review_id, str) or not review_id.strip():
            raise PipelineError("review_id must be a non-empty string.")
        if not isinstance(reviewer_ref, str) or not reviewer_ref.strip():
            raise PipelineError("reviewer_ref must be a non-empty string.")
        if not isinstance(summary, str) or not summary.strip():
            raise PipelineError("summary must be a non-empty string.")
        try:
            normalized_outcome = HumanReviewOutcome(outcome)
        except ValueError as exc:
            raise PipelineError(f"Unknown human review outcome: {outcome!r}.") from exc

        normalized_resolves = _string_sequence(resolves, "resolves")
        normalized_support_refs = _string_sequence(support_refs, "support_refs")
        failed_resolutions = set(normalized_resolves).intersection(self.trail.active_read_failures)
        if failed_resolutions and not normalized_support_refs:
            raise PipelineError(
                "Resolving an extraction failure requires explicit human support references."
            )

        state = {
            HumanReviewOutcome.ACCEPTED: InformationState.ORIGINAL_PRESERVED,
            HumanReviewOutcome.REJECTED: InformationState.BLOCKED,
            HumanReviewOutcome.RETURNED_FOR_CORRECTION: (InformationState.RETURNED_FOR_CORRECTION),
        }[normalized_outcome]
        requires_review = normalized_outcome is HumanReviewOutcome.RETURNED_FOR_CORRECTION
        event = PrecisionEvent(
            event_id=f"{self.trace_id}:human:{review_id.strip()}",
            source_layer=SourceLayer.HUMAN_REVIEW,
            information_id=f"{self.trace_id}:human-review",
            information_state=state,
            custody_state=CustodyState.REFERENCED,
            summary=summary.strip(),
            support_refs=normalized_support_refs,
            requires_human_review=requires_review,
            details={
                "review_id": review_id.strip(),
                "reviewer_ref": reviewer_ref.strip(),
                "outcome": normalized_outcome.value,
            },
            trace_id=self.trace_id,
            observed_at=observed_at or self.clock(),
            caused_by=(
                (self._quinta_decision_event.event_id,)
                if self._quinta_decision_event is not None
                else ()
            ),
            resolves=normalized_resolves,
            human_review_state=(
                HumanReviewState.REQUIRED if requires_review else HumanReviewState.COMPLETED
            ),
        )
        appended = self.trail.append(event).event
        self._human_events.append(appended)
        self._human_outcome = normalized_outcome
        self.stage = PipelineStage.HUMAN_REVIEWED
        return appended

    def assess(self) -> CoherenceAssessment:
        return self.coherence_evaluator.evaluate(self.trail.events)

    def finalize(self, *, observed_at: str | None = None) -> PipelineFinalization:
        self._require_stage(PipelineStage.HUMAN_REVIEWED)
        if self._quinta_decision_event is None or self._quinta_decision_event.gate_status is None:
            raise PipelineError("A Quinta Ordem decision is required before finalization.")
        if self._human_outcome is None:
            raise PipelineError("A human review outcome is required before finalization.")

        gate_status = self._quinta_decision_event.gate_status
        assessment = self.assess()
        released = (
            gate_status is GateStatus.APPROVED
            and self._human_outcome is HumanReviewOutcome.ACCEPTED
            and not self.trail.active_blocks
            and not self.trail.active_reviews
            and not self.trail.active_read_failures
            and not assessment.conflict
            and not assessment.requires_human_review
        )
        if released:
            human_event = self._human_events[-1]
            release_event = PrecisionEvent(
                event_id=f"{self.trace_id}:precision:release",
                source_layer=SourceLayer.PRECISION_GATE,
                information_id=f"{self.trace_id}:release",
                information_state=InformationState.RELEASED,
                custody_state=CustodyState.REFERENCED,
                summary=(
                    "Output is eligible for delivery to the responsible human or "
                    "institutional flow."
                ),
                support_refs=(
                    self._quinta_decision_event.event_id,
                    human_event.event_id,
                    self.trail.final_chain_sha256,
                ),
                requires_human_review=False,
                details={
                    "release_scope": "delivery_to_responsible_human_or_institution",
                    "not_a_final_rights_decision": True,
                },
                trace_id=self.trace_id,
                observed_at=observed_at or self.clock(),
                caused_by=(self._quinta_decision_event.event_id, human_event.event_id),
                gate_status=GateStatus.APPROVED,
                human_review_state=HumanReviewState.COMPLETED,
            )
            self.trail.append(release_event)
            assessment = self.assess()

        self.stage = PipelineStage.FINALIZED
        self._finalization = PipelineFinalization(
            trace_id=self.trace_id,
            released=released,
            gate_status=gate_status,
            human_outcome=self._human_outcome,
            final_chain_sha256=self.trail.final_chain_sha256,
            assessment=assessment,
        )
        return self._finalization

    def _require_stage(self, *allowed: PipelineStage) -> None:
        if self.stage not in allowed:
            expected = ", ".join(stage.value for stage in allowed)
            raise PipelineError(
                f"Operation is not allowed in stage {self.stage.value}; expected {expected}."
            )


def _string_sequence(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise PipelineError(f"{field_name} must be a sequence of strings.")
    normalized: list[str] = []
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value.strip():
            raise PipelineError(f"{field_name}[{index}] must be a non-empty string.")
        normalized.append(value.strip())
    if len(set(normalized)) != len(normalized):
        raise PipelineError(f"{field_name} must not contain duplicates.")
    return tuple(normalized)
