from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from precision_gate.contracts import (
    AlertSeverity,
    CoherenceAlert,
    CustodyState,
    GateStatus,
    InformationState,
    PrecisionEvent,
    PromotionError,
    SourceLayer,
    has_traceable_custody,
    is_read_failure,
    to_jsonable,
)


class SupportTier(str, Enum):
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    TRACEABLE = "traceable"
    SUPPORTED = "supported"
    GATE_VERIFIED = "gate_verified"


@dataclass(frozen=True)
class CoherenceAssessment:
    alerts: tuple[CoherenceAlert, ...]
    best_supported_event_ids: tuple[str, ...]
    support_tier: SupportTier
    conflict: bool
    active_condition_ids: tuple[str, ...]
    requires_human_review: bool

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


class CoherenceEvaluator:
    """Run deterministic cross-layer checks over an ordered Precision event trail."""

    def evaluate(self, events: Sequence[PrecisionEvent]) -> CoherenceAssessment:
        if not isinstance(events, Sequence) or isinstance(events, (str, bytes)):
            raise TypeError("events must be a sequence of PrecisionEvent values.")
        for index, event in enumerate(events):
            if not isinstance(event, PrecisionEvent):
                raise TypeError(f"events[{index}] must be a PrecisionEvent.")

        pending_alerts: list[dict[str, Any]] = []
        seen_alerts: set[tuple[str, tuple[str, ...]]] = set()
        by_information_id: dict[str, list[PrecisionEvent]] = {}
        active_blocks: dict[str, str] = {}
        active_reviews: dict[str, str] = {}
        active_failures: dict[str, str] = {}
        source_digests: dict[str, tuple[str, str | None]] = {}
        explicit_conflicts: set[frozenset[str]] = set()
        latest_quinta_status: GateStatus | None = None
        api_supports_anything = False

        def add_alert(
            code: str,
            severity: AlertSeverity,
            message: str,
            *,
            event_ids: tuple[str, ...] = (),
            information_ids: tuple[str, ...] = (),
            requires_human_review: bool = False,
            details: Mapping[str, Any] | None = None,
        ) -> None:
            key = (code, event_ids)
            if key in seen_alerts:
                return
            seen_alerts.add(key)
            pending_alerts.append(
                {
                    "code": code,
                    "severity": severity,
                    "message": message,
                    "event_ids": event_ids,
                    "information_ids": information_ids,
                    "requires_human_review": requires_human_review,
                    "details": details or {},
                }
            )

        for event in events:
            by_information_id.setdefault(event.information_id, []).append(event)
            for resolved in event.resolves:
                active_blocks.pop(resolved, None)
                active_reviews.pop(resolved, None)
                active_failures.pop(resolved, None)

            if event.source_reference is not None:
                source_id = event.source_reference.source_id
                digest_pair = (
                    event.source_reference.artifact_sha256,
                    event.source_reference.payload_sha256,
                )
                previous = source_digests.get(source_id)
                if previous is not None and previous != digest_pair:
                    add_alert(
                        "SOURCE_DIGEST_CONFLICT",
                        AlertSeverity.CRITICAL,
                        f"Source {source_id} appeared with conflicting digests.",
                        event_ids=(event.event_id,),
                        information_ids=(event.information_id,),
                        requires_human_review=True,
                    )
                source_digests[source_id] = digest_pair

            dependencies = _detail_string_set(
                event.details,
                "depends_on_information_ids",
            )
            related_information = {event.information_id, *dependencies}
            related_blocks = _conditions_for_information(active_blocks, related_information)
            related_failures = _conditions_for_information(active_failures, related_information)
            if event.promotable_as_fact:
                try:
                    event.assert_safe_promotion(
                        active_blocks=related_blocks,
                        failed_dependencies=related_failures,
                    )
                except PromotionError as exc:
                    add_alert(
                        "UNSUPPORTED_PROMOTION",
                        AlertSeverity.CRITICAL,
                        str(exc),
                        event_ids=(event.event_id,),
                        information_ids=(event.information_id,),
                        requires_human_review=True,
                    )

            if event.information_state is InformationState.FACT_SUPPORTED:
                if not event.support_refs or not has_traceable_custody(event.custody_state):
                    add_alert(
                        "FACT_WITHOUT_TRACEABLE_SUPPORT",
                        AlertSeverity.CRITICAL,
                        "A fact_supported event lacks explicit support or traceable custody.",
                        event_ids=(event.event_id,),
                        information_ids=(event.information_id,),
                        requires_human_review=True,
                    )
                if event.gate_status not in {None, GateStatus.APPROVED}:
                    gate_event_ids = _detail_string_tuple(
                        event.details,
                        "record_gate_event_ids",
                    )
                    add_alert(
                        "FACT_NOT_APPROVED_BY_SOURCE_GATE",
                        AlertSeverity.CRITICAL,
                        "A fact_supported record was not approved by its source gates.",
                        event_ids=(event.event_id, *gate_event_ids),
                        information_ids=(event.information_id,),
                        requires_human_review=True,
                        details={"gate_status": event.gate_status.value},
                    )
                if related_failures:
                    add_alert(
                        "FAILED_READING_USED_AS_FACT",
                        AlertSeverity.CRITICAL,
                        "A supported fact depends on unreadable or failed extraction.",
                        event_ids=(event.event_id, *related_failures),
                        information_ids=tuple(sorted(related_information)),
                        requires_human_review=True,
                    )

            if event.information_state is InformationState.RELEASED:
                if active_blocks:
                    add_alert(
                        "IGNORED_BLOCK",
                        AlertSeverity.CRITICAL,
                        "A release event ignored an earlier unresolved block.",
                        event_ids=(event.event_id, *active_blocks),
                        requires_human_review=True,
                    )
                if active_reviews:
                    add_alert(
                        "IGNORED_HUMAN_REVIEW",
                        AlertSeverity.CRITICAL,
                        "A release event ignored an earlier human-review requirement.",
                        event_ids=(event.event_id, *active_reviews),
                        requires_human_review=True,
                    )

            self._evaluate_omission(event, add_alert)
            api_supports_anything = (
                self._evaluate_api_relations(
                    event,
                    by_information_id,
                    explicit_conflicts,
                    add_alert,
                )
                or api_supports_anything
            )
            for target in _detail_string_set(event.details, "contradicts_information_ids"):
                explicit_conflicts.add(frozenset((event.information_id, target)))

            if event.source_layer is SourceLayer.QUINTA_ORDEM and event.gate_status is not None:
                latest_quinta_status = event.gate_status
                if event.gate_status is GateStatus.APPROVED and active_blocks:
                    add_alert(
                        "QUINTA_APPROVED_WITH_ACTIVE_BLOCK",
                        AlertSeverity.CRITICAL,
                        "Quinta Ordem approved a context that still carried an active block.",
                        event_ids=(event.event_id, *active_blocks),
                        requires_human_review=True,
                    )

            if event.information_state is InformationState.BLOCKED:
                active_blocks[event.event_id] = event.information_id
            if is_read_failure(event.information_state):
                active_failures[event.event_id] = event.information_id
            if event.requires_human_review:
                active_reviews[event.event_id] = event.information_id

        if (
            latest_quinta_status
            in {
                GateStatus.BLOCKED,
                GateStatus.RETURNED,
                GateStatus.CONDITIONAL,
            }
            and api_supports_anything
        ):
            add_alert(
                "API_QUINTA_DIVERGENCE",
                AlertSeverity.HIGH,
                "The API supported a reading while Quinta Ordem did not approve the context.",
                requires_human_review=True,
                details={"quinta_status": latest_quinta_status.value},
            )

        candidates = [
            event
            for event in events
            if (
                event.source_layer is SourceLayer.API
                or "source_partition" in event.details
            )
            if event.information_state
            not in {
                InformationState.BLOCKED,
                InformationState.RETURNED_FOR_CORRECTION,
                InformationState.EXTRACTION_FAILED,
                InformationState.OCR_FAILED,
                InformationState.UNREADABLE,
                InformationState.HUMAN_REVIEW_REQUIRED,
                InformationState.RELEASED,
            }
            and "gate_name" not in event.details
        ]
        best_events, support_tier = _best_supported(candidates)
        best_information_ids = {event.information_id for event in best_events}
        conflicting_pairs = [
            pair for pair in explicit_conflicts if pair.issubset(best_information_ids)
        ]
        conflict = bool(conflicting_pairs)
        if conflict:
            add_alert(
                "CONFLICTING_SUPPORTED_READINGS",
                AlertSeverity.CRITICAL,
                "The best-supported readings explicitly contradict each other.",
                event_ids=tuple(event.event_id for event in best_events),
                information_ids=tuple(sorted(best_information_ids)),
                requires_human_review=True,
            )

        alerts = tuple(
            CoherenceAlert(
                alert_id=f"alert-{index:04d}-{item['code'].lower()}",
                code=item["code"],
                severity=item["severity"],
                message=item["message"],
                event_ids=item["event_ids"],
                information_ids=item["information_ids"],
                requires_human_review=item["requires_human_review"],
                details=item["details"],
            )
            for index, item in enumerate(pending_alerts, start=1)
        )
        active_condition_ids = tuple(
            dict.fromkeys((*active_blocks, *active_reviews, *active_failures))
        )
        resolved_event_ids = {condition_id for event in events for condition_id in event.resolves}
        unresolved_alert_review = any(
            alert.requires_human_review
            and not set(alert.event_ids).intersection(resolved_event_ids)
            for alert in alerts
        )
        requires_human_review = bool(
            active_reviews or active_failures or conflict or unresolved_alert_review
        )
        return CoherenceAssessment(
            alerts=alerts,
            best_supported_event_ids=tuple(event.event_id for event in best_events),
            support_tier=support_tier,
            conflict=conflict,
            active_condition_ids=active_condition_ids,
            requires_human_review=requires_human_review,
        )

    def _evaluate_omission(
        self,
        event: PrecisionEvent,
        add_alert: Any,
    ) -> None:
        trace_observation = event.details.get("trace_observation")
        if not isinstance(trace_observation, Mapping):
            return
        observed = trace_observation.get("observed")
        mentioned = trace_observation.get("mentioned")
        if observed is True and mentioned is False:
            omission_reason = trace_observation.get("omission_reason")
            if isinstance(omission_reason, str) and omission_reason.strip():
                add_alert(
                    "DOCUMENTED_OMISSION",
                    AlertSeverity.INFO,
                    "TCRIA observed the information and documented why it was not mentioned.",
                    event_ids=(event.event_id,),
                    information_ids=(event.information_id,),
                    details={"omission_reason": omission_reason.strip()},
                )
            else:
                add_alert(
                    "UNEXPLAINED_OMISSION",
                    AlertSeverity.HIGH,
                    "TCRIA observed the information but no omission reason was recorded.",
                    event_ids=(event.event_id,),
                    information_ids=(event.information_id,),
                    requires_human_review=True,
                )

    def _evaluate_api_relations(
        self,
        event: PrecisionEvent,
        by_information_id: Mapping[str, list[PrecisionEvent]],
        explicit_conflicts: set[frozenset[str]],
        add_alert: Any,
    ) -> bool:
        if event.source_layer is not SourceLayer.API:
            return False
        raw_relations = event.details.get("claim_relations", ())
        if not isinstance(raw_relations, tuple):
            return False
        supports_anything = False
        for relation in raw_relations:
            if not isinstance(relation, Mapping):
                continue
            information_id = relation.get("information_id")
            relation_name = relation.get("relation")
            if not isinstance(information_id, str) or not isinstance(relation_name, str):
                continue
            targets = by_information_id.get(information_id, [])
            if relation_name == "supports":
                supports_anything = True
                if any(
                    target.information_state
                    in {
                        InformationState.BLOCKED,
                        InformationState.EXTRACTION_FAILED,
                        InformationState.OCR_FAILED,
                        InformationState.UNREADABLE,
                    }
                    for target in targets
                ):
                    add_alert(
                        "API_SUPPORTS_BLOCKED_INFORMATION",
                        AlertSeverity.CRITICAL,
                        "The API supported information that was blocked or unreadable.",
                        event_ids=(event.event_id, *(target.event_id for target in targets)),
                        information_ids=(information_id,),
                        requires_human_review=True,
                    )
            elif relation_name == "contradicts":
                explicit_conflicts.add(frozenset((event.information_id, information_id)))
                if any(
                    target.information_state is InformationState.FACT_SUPPORTED
                    for target in targets
                ):
                    add_alert(
                        "API_TCRIA_DIVERGENCE",
                        AlertSeverity.HIGH,
                        "The API contradicted an explicitly supported TCRIA fact.",
                        event_ids=(event.event_id, *(target.event_id for target in targets)),
                        information_ids=(event.information_id, information_id),
                        requires_human_review=True,
                    )
            elif relation_name == "unseen" and targets:
                add_alert(
                    "OBSERVED_ITEM_DESCRIBED_AS_UNSEEN",
                    AlertSeverity.HIGH,
                    "The API described an item as unseen although it exists in the TCRIA trail.",
                    event_ids=(event.event_id, *(target.event_id for target in targets)),
                    information_ids=(information_id,),
                    requires_human_review=True,
                )
        return supports_anything


def _detail_string_set(details: Mapping[str, Any], key: str) -> set[str]:
    value = details.get(key, ())
    if not isinstance(value, tuple):
        return set()
    return {item for item in value if isinstance(item, str) and item}


def _detail_string_tuple(details: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = details.get(key, ())
    if not isinstance(value, tuple):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def _conditions_for_information(
    conditions: Mapping[str, str],
    information_ids: set[str],
) -> tuple[str, ...]:
    return tuple(
        condition_id
        for condition_id, information_id in conditions.items()
        if information_id in information_ids
    )


def _best_supported(
    events: Sequence[PrecisionEvent],
) -> tuple[tuple[PrecisionEvent, ...], SupportTier]:
    if not events:
        return (), SupportTier.UNAVAILABLE
    scored = [(_support_score(event), event) for event in events]
    best_score = max(score for score, _ in scored)
    tier = {
        0: SupportTier.UNSUPPORTED,
        1: SupportTier.UNSUPPORTED,
        2: SupportTier.TRACEABLE,
        3: SupportTier.SUPPORTED,
        4: SupportTier.GATE_VERIFIED,
    }[best_score]
    return tuple(event for score, event in scored if score == best_score), tier


def _support_score(event: PrecisionEvent) -> int:
    if event.information_state is InformationState.FACT_SUPPORTED:
        if event.gate_status not in {None, GateStatus.APPROVED}:
            return 0
        if event.support_refs and has_traceable_custody(event.custody_state):
            return 4 if event.gate_status is GateStatus.APPROVED else 3
        return 0
    if event.information_state in {
        InformationState.ORIGINAL_PRESERVED,
        InformationState.DERIVED_COPY,
    } and event.custody_state not in {CustodyState.BROKEN, CustodyState.UNKNOWN}:
        return 2
    return 1
