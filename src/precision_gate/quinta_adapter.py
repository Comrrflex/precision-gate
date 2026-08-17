from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Any

from precision_gate._validation import (
    canonical_sha256,
    require_bool,
    require_mapping,
    require_mapping_list,
    require_text,
    strict_snapshot,
)
from precision_gate.contracts import (
    QUINTA_EXECUTION_CONTEXT_VERSION,
    ContractError,
    CustodyState,
    GateStatus,
    HumanReviewState,
    InformationState,
    PrecisionEvent,
    SourceLayer,
    SourceReference,
    canonical_json,
    validate_sha256,
)


class QuintaAdapterError(ContractError):
    """Raised when the Quinta Ordem handoff or decision violates version 1.0."""


_BREAKDOWN_FIELDS = (
    "integrity",
    "traceability",
    "evidence_support",
    "logical_consistency",
    "resolution",
)


class QuintaExecutionContextAdapter:
    """Build and observe the documented Quinta Ordem ExecutionContext contract."""

    def build_payload(
        self,
        events: Sequence[PrecisionEvent],
        *,
        execution_id: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(execution_id, str) or not execution_id.strip():
            raise QuintaAdapterError("execution_id must be a non-empty string.")
        if not isinstance(events, Sequence) or isinstance(events, (str, bytes)):
            raise QuintaAdapterError("events must be a sequence of PrecisionEvent values.")
        normalized_id = execution_id.strip()
        evidence_by_id: dict[str, dict[str, Any]] = {}
        artifacts: list[dict[str, Any]] = []
        gate_results: list[dict[str, Any]] = []
        logs: list[dict[str, Any]] = []
        decisions: list[dict[str, Any]] = []
        signals: list[dict[str, Any]] = []
        open_points: list[dict[str, Any]] = []

        for index, event in enumerate(events):
            if not isinstance(event, PrecisionEvent):
                raise QuintaAdapterError(f"events[{index}] must be a PrecisionEvent.")
            if event.trace_id not in {None, normalized_id}:
                raise QuintaAdapterError(f"events[{index}].trace_id does not match execution_id.")
            event_payload = event.to_dict()
            event_sha256 = canonical_sha256(event_payload)
            artifacts.append(
                {
                    "artifact_id": event.event_id,
                    "sha256": event_sha256,
                    "source": f"precision-event://{event.event_id}",
                    "derived": True,
                    "source_event_id": event.event_id,
                }
            )

            if event.sha256 is not None:
                evidence_id = _evidence_id(event)
                evidence_item = {
                    "artifact_id": evidence_id,
                    "sha256": event.sha256,
                    "source": (
                        event.source_reference.source_ref
                        if event.source_reference is not None
                        else f"precision-information://{event.information_id}"
                    ),
                    "custody_state": event.custody_state.value,
                }
                modified_original = event.details.get("modified_original")
                if modified_original is not None:
                    if not isinstance(modified_original, bool):
                        raise QuintaAdapterError(
                            f"Event {event.event_id!r} modified_original must be boolean."
                        )
                    evidence_item["modified_original"] = modified_original
                existing = evidence_by_id.get(evidence_id)
                if existing is not None and existing["sha256"] != event.sha256:
                    raise QuintaAdapterError(
                        f"Evidence {evidence_id!r} has conflicting SHA-256 values."
                    )
                evidence_by_id.setdefault(evidence_id, evidence_item)

            if event.gate_status is not None:
                gate_results.append(
                    {
                        "gate": str(event.details.get("gate_name", event.event_id)),
                        "status": event.gate_status.value,
                        "reason": str(event.details.get("source_reason", event.summary)),
                        "source_event_id": event.event_id,
                    }
                )

            logs.append(
                {
                    "event_id": event.event_id,
                    "source_layer": (
                        event.source_layer.value
                        if isinstance(event.source_layer, SourceLayer)
                        else event.source_layer
                    ),
                    "observed_at": event.observed_at,
                    "summary": event.summary,
                }
            )
            if event.information_state in {
                InformationState.SIGNAL_PENDING,
                InformationState.TCRIA_SIGNAL,
            }:
                signals.append(
                    {
                        "signal_id": event.event_id,
                        "support_level": "partial",
                        "evidence_refs": list(event.support_refs),
                        "message": event.summary,
                        "details": {"information_id": event.information_id},
                    }
                )
            else:
                decisions.append(
                    {
                        "decision_id": event.event_id,
                        "classification": event.information_state.value,
                        "support_level": (
                            "explicit"
                            if event.information_state is InformationState.FACT_SUPPORTED
                            else "unverified"
                        ),
                        "evidence_refs": list(event.support_refs),
                        "promoted": False,
                        "source_event_id": event.event_id,
                    }
                )
                if event.requires_human_review:
                    open_points.append(
                        {
                            "id": event.event_id,
                            "status": "open",
                            "return_to": "human_review",
                            "evidence_refs": list(event.support_refs),
                        }
                    )

        base_metadata = (
            strict_snapshot(metadata, name="Quinta metadata") if metadata is not None else {}
        )
        existing_open_points = base_metadata.get("open_points", [])
        if not isinstance(existing_open_points, list):
            raise QuintaAdapterError("metadata.open_points must be a list.")
        for index, item in enumerate(existing_open_points):
            if not isinstance(item, Mapping):
                raise QuintaAdapterError(f"metadata.open_points[{index}] must be a mapping.")
        base_metadata["open_points"] = [*existing_open_points, *open_points]
        base_metadata.update(
            {
                "precision_gate_schema_version": "1.0",
                "precision_event_count": len(events),
            }
        )
        payload = {
            "quinta_ordem_adapter_version": QUINTA_EXECUTION_CONTEXT_VERSION,
            "execution_id": normalized_id,
            "evidence": list(evidence_by_id.values()),
            "artifacts": artifacts,
            "gate_results": gate_results,
            "logs": logs,
            "decisions": decisions,
            "signals_for_verification": signals,
            "metadata": base_metadata,
        }
        return strict_snapshot(payload, name="Quinta ExecutionContext payload")

    def expected_context_sha256(self, payload: Mapping[str, Any]) -> str:
        """Hash the exact ExecutionContext produced by the published Quinta adapter."""

        snapshot = strict_snapshot(payload, name="Quinta adapter payload")
        version = require_text(snapshot, "quinta_ordem_adapter_version")
        if version != QUINTA_EXECUTION_CONTEXT_VERSION:
            raise QuintaAdapterError(
                f"Unsupported Quinta adapter version: {version!r}."
            )
        execution_id = require_text(snapshot, "execution_id")
        evidence = require_mapping_list(snapshot, "evidence")
        artifacts = require_mapping_list(snapshot, "artifacts")
        gate_results = require_mapping_list(snapshot, "gate_results")
        logs = require_mapping_list(snapshot, "logs")
        decisions = require_mapping_list(snapshot, "decisions")
        signals = require_mapping_list(snapshot, "signals_for_verification")
        metadata = require_mapping(snapshot, "metadata")
        open_points = metadata.get("open_points")
        if not isinstance(open_points, list):
            raise QuintaAdapterError("metadata.open_points must be a list.")
        context_open_points = list(open_points)

        for index, result in enumerate(gate_results):
            status = result.get("status")
            if not isinstance(status, str) or not status.strip():
                raise QuintaAdapterError(
                    f"gate_results[{index}].status must be non-empty text."
                )
            result["status"] = status.strip().lower()

        for index, signal in enumerate(signals):
            signal_id = signal.get("signal_id")
            if not isinstance(signal_id, str) or not signal_id.strip():
                raise QuintaAdapterError(
                    f"signals_for_verification[{index}].signal_id is required."
                )
            decision = {
                "decision_id": signal_id,
                "classification": "signal",
                "promoted": False,
            }
            for key in ("support_level", "evidence_refs", "message", "details"):
                if key in signal:
                    decision[key] = signal[key]
            decisions.append(decision)
            context_open_points.append(
                {
                    "id": signal_id,
                    "status": "open",
                    "return_to": "human_review",
                    "evidence_refs": signal.get("evidence_refs", []),
                }
            )
        metadata["open_points"] = context_open_points
        context = {
            "execution_id": execution_id,
            "evidence": evidence,
            "artifacts": artifacts,
            "gate_results": gate_results,
            "logs": logs,
            "decisions": decisions,
            "metadata": metadata,
        }
        encoded = (
            json.dumps(
                context,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        return sha256(encoded).hexdigest()

    def adapt_decision(
        self,
        decision: Mapping[str, Any],
        *,
        trace_id: str,
        observed_at: str,
        source_ref: str | None = None,
    ) -> PrecisionEvent:
        snapshot = strict_snapshot(decision, name="Quinta GateDecision")
        schema_version = require_text(snapshot, "schema_version")
        if schema_version != QUINTA_EXECUTION_CONTEXT_VERSION:
            raise QuintaAdapterError(
                f"Unsupported Quinta GateDecision schema_version: {schema_version!r}."
            )
        execution_id = require_text(snapshot, "execution_id")
        if execution_id != trace_id:
            raise QuintaAdapterError("GateDecision execution_id does not match trace_id.")
        gate_status = _decision_status(require_text(snapshot, "status"))
        confidence = _unit_interval(snapshot.get("confidence"), "confidence")
        breakdown = require_mapping(snapshot, "breakdown")
        normalized_breakdown = {
            field: _unit_interval(breakdown.get(field), f"breakdown.{field}")
            for field in _BREAKDOWN_FIELDS
        }
        findings = require_mapping_list(snapshot, "findings")
        uncertainties = snapshot.get("remaining_uncertainties")
        if not isinstance(uncertainties, list) or not all(
            isinstance(item, str) and item.strip() for item in uncertainties
        ):
            raise QuintaAdapterError("remaining_uncertainties must be a list of non-empty strings.")
        human_review_required = require_bool(snapshot, "human_review_required")
        if gate_status is GateStatus.APPROVED and human_review_required:
            raise QuintaAdapterError("Approved GateDecision cannot require human review.")
        if gate_status is not GateStatus.APPROVED and not human_review_required:
            raise QuintaAdapterError("Non-approved GateDecision must require human review.")

        evaluated_verifiers = snapshot.get("evaluated_verifiers")
        if not isinstance(evaluated_verifiers, list) or not all(
            isinstance(item, str) and item.strip() for item in evaluated_verifiers
        ):
            raise QuintaAdapterError("evaluated_verifiers must be a list of non-empty strings.")
        context_sha256 = snapshot.get("execution_context_sha256")
        if context_sha256 is not None:
            if not isinstance(context_sha256, str):
                raise QuintaAdapterError("execution_context_sha256 must be text or null.")
            context_sha256 = validate_sha256(
                context_sha256,
                field_name="execution_context_sha256",
            )
        elif gate_status is GateStatus.APPROVED:
            raise QuintaAdapterError("Approved GateDecision requires execution_context_sha256.")

        information_state = {
            GateStatus.APPROVED: InformationState.PENDING,
            GateStatus.CONDITIONAL: InformationState.HUMAN_REVIEW_REQUIRED,
            GateStatus.RETURNED: InformationState.RETURNED_FOR_CORRECTION,
            GateStatus.BLOCKED: InformationState.BLOCKED,
            GateStatus.NOT_EVALUATED: InformationState.HUMAN_REVIEW_REQUIRED,
        }[gate_status]
        decision_sha256 = sha256(canonical_json(snapshot).encode("utf-8")).hexdigest()
        resolved_source_ref = source_ref or f"memory://quinta-ordem/{execution_id}/decision"
        source_reference = SourceReference(
            source_id=f"{execution_id}:quinta-decision",
            source_ref=resolved_source_ref,
            artifact_sha256=decision_sha256,
            payload_sha256=decision_sha256,
            contract_profile="quinta.gate_decision.v1",
            schema_version=schema_version,
        )
        return PrecisionEvent(
            event_id=f"{trace_id}:quinta:decision",
            source_layer=SourceLayer.QUINTA_ORDEM,
            information_id=f"{execution_id}:gate-decision",
            information_state=information_state,
            custody_state=(
                CustodyState.HASHED if context_sha256 is not None else CustodyState.UNKNOWN
            ),
            summary=f"Quinta Ordem Gate returned {gate_status.value}.",
            support_refs=((context_sha256,) if context_sha256 is not None else ()),
            sha256=decision_sha256,
            requires_human_review=human_review_required,
            promotable_as_fact=False,
            details={
                "confidence_coverage": confidence,
                "breakdown": normalized_breakdown,
                "findings": findings,
                "remaining_uncertainties": tuple(item.strip() for item in uncertainties),
                "evaluated_verifiers": tuple(item.strip() for item in evaluated_verifiers),
                "execution_context_sha256": context_sha256,
            },
            trace_id=trace_id,
            observed_at=observed_at,
            source_reference=source_reference,
            gate_status=gate_status,
            human_review_state=(
                HumanReviewState.REQUIRED
                if human_review_required
                else HumanReviewState.NOT_REQUIRED
            ),
        )


def _evidence_id(event: PrecisionEvent) -> str:
    document_ref = event.details.get("document_ref")
    if isinstance(document_ref, str) and document_ref:
        return document_ref
    return event.information_id


def _decision_status(value: str) -> GateStatus:
    normalized = value.strip().lower()
    aliases = {
        "approved": GateStatus.APPROVED,
        "conditional": GateStatus.CONDITIONAL,
        "returned": GateStatus.RETURNED,
        "returned_for_correction": GateStatus.RETURNED,
        "blocked": GateStatus.BLOCKED,
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise QuintaAdapterError(f"Unknown Quinta decision status: {value!r}.") from exc


def _unit_interval(value: Any, field_name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise QuintaAdapterError(f"{field_name} must be numeric.")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
        raise QuintaAdapterError(f"{field_name} must be between 0 and 1.")
    return normalized
