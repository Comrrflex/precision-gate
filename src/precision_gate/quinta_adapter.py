from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import Any

from precision_gate.custody_state import CustodyState, InformationState, PrecisionEvent


class QuintaAdapterError(ValueError):
    """Raised when Precision and Quinta Ordem contracts cannot be mapped safely."""


class QuintaIntegrationUnavailable(RuntimeError):
    """Raised when the optional Quinta Ordem Python package is not installed."""


def build_execution_context_payload(
    events: Iterable[PrecisionEvent],
    *,
    execution_id: str,
    gate_results: list[dict[str, Any]] | None = None,
    logs: list[dict[str, Any]] | None = None,
    decisions: list[dict[str, Any]] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a detached payload compatible with Quinta Ordem ``ExecutionContext``."""

    if not isinstance(execution_id, str) or not execution_id.strip():
        raise QuintaAdapterError("execution_id is required.")

    event_list = tuple(events)
    evidence: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    precision_decisions = deepcopy(decisions or [])

    for event in event_list:
        event.assert_safe_promotion()
        artifact = {
            "artifact_id": event.information_id,
            "event_id": event.event_id,
            "source_layer": event.source_layer,
            "information_state": event.information_state.value,
            "custody_state": event.custody_state.value,
            "summary": event.summary,
            "support_refs": list(event.support_refs),
            "sha256": event.sha256,
            "derived": event.information_state is not InformationState.ORIGINAL_PRESERVED,
        }
        artifacts.append(artifact)
        if event.support_refs or event.sha256:
            evidence.append(
                {
                    "artifact_id": event.information_id,
                    "sha256": event.sha256,
                    "source": event.source_layer,
                    "support_refs": list(event.support_refs),
                    "state": event.information_state.value,
                }
            )
        precision_decisions.append(
            {
                "decision_id": event.event_id,
                "classification": event.information_state.value,
                "promoted": event.promotable_as_fact,
                "human_review_required": event.requires_human_review,
                "support_refs": list(event.support_refs),
            }
        )

    copied_metadata = deepcopy(dict(metadata or {}))
    copied_metadata.setdefault("precision_gate_schema_version", "1.0")
    copied_metadata.setdefault("human_decision_required", True)

    return {
        "execution_id": execution_id.strip(),
        "evidence": evidence,
        "artifacts": artifacts,
        "gate_results": deepcopy(gate_results or []),
        "logs": deepcopy(logs or []),
        "decisions": precision_decisions,
        "metadata": copied_metadata,
    }


def to_quinta_execution_context(payload: Mapping[str, Any]) -> Any:
    """Instantiate Quinta Ordem ``ExecutionContext`` when its package is installed."""

    try:
        from quinta_ordem.models import ExecutionContext
    except ImportError as exc:
        raise QuintaIntegrationUnavailable(
            "Install or expose the Quinta Ordem package before requesting a concrete "
            "ExecutionContext instance."
        ) from exc

    required = ("execution_id", "evidence", "artifacts", "gate_results", "logs", "decisions")
    missing = [key for key in required if key not in payload]
    if missing:
        raise QuintaAdapterError(f"ExecutionContext payload is missing: {', '.join(missing)}.")
    return ExecutionContext(
        execution_id=payload["execution_id"],
        evidence=deepcopy(payload["evidence"]),
        artifacts=deepcopy(payload["artifacts"]),
        gate_results=deepcopy(payload["gate_results"]),
        logs=deepcopy(payload["logs"]),
        decisions=deepcopy(payload["decisions"]),
        metadata=deepcopy(payload.get("metadata", {})),
    )


def adapt_gate_decision(payload: Mapping[str, Any]) -> tuple[PrecisionEvent, ...]:
    """Convert a serialized Quinta Ordem ``GateDecision`` into Precision events."""

    if not isinstance(payload, Mapping):
        raise QuintaAdapterError("Gate decision must be a mapping.")
    source = deepcopy(dict(payload))
    execution_id = _required_string(source, "execution_id")
    status = _required_string(source, "status").lower()
    findings = source.get("findings", [])
    if not isinstance(findings, list):
        raise QuintaAdapterError("findings must be a list.")

    events: list[PrecisionEvent] = [
        PrecisionEvent(
            event_id=f"quinta:{execution_id}:decision",
            source_layer="quinta_ordem",
            information_id=execution_id,
            information_state=_decision_state(status),
            custody_state=(
                CustodyState.HASHED
                if _optional_string(source.get("execution_context_sha256"))
                else CustodyState.REFERENCED
            ),
            summary=f"Quinta Ordem decision: {status}.",
            support_refs=(execution_id,),
            sha256=_optional_string(source.get("execution_context_sha256")),
            requires_human_review=bool(source.get("human_review_required", False)),
            promotable_as_fact=False,
            details={
                "confidence": source.get("confidence"),
                "breakdown": deepcopy(source.get("breakdown", {})),
                "remaining_uncertainties": deepcopy(
                    source.get("remaining_uncertainties", [])
                ),
                "evaluated_verifiers": deepcopy(source.get("evaluated_verifiers", [])),
            },
        )
    ]

    for index, raw_finding in enumerate(findings):
        if not isinstance(raw_finding, Mapping):
            raise QuintaAdapterError(f"findings[{index}] must be a mapping.")
        finding = deepcopy(dict(raw_finding))
        point_id = _required_string(finding, "point_id")
        message = _required_string(finding, "message")
        severity = (_optional_string(finding.get("severity")) or "warning").lower()
        support_refs = _finding_refs(finding.get("evidence_refs", []))
        state = _finding_state(finding, severity=severity)
        events.append(
            PrecisionEvent(
                event_id=f"quinta:{execution_id}:finding:{point_id}",
                source_layer="quinta_ordem",
                information_id=point_id,
                information_state=state,
                custody_state=(
                    CustodyState.REFERENCED if support_refs else CustodyState.UNKNOWN
                ),
                summary=message,
                support_refs=support_refs,
                requires_human_review=(
                    state
                    in {
                        InformationState.PENDING,
                        InformationState.BLOCKED,
                        InformationState.RETURNED_FOR_CORRECTION,
                        InformationState.HUMAN_REVIEW_REQUIRED,
                    }
                ),
                promotable_as_fact=False,
                details={
                    "verifier": finding.get("verifier"),
                    "code": finding.get("code"),
                    "severity": severity,
                    "return_to": finding.get("return_to"),
                    "required_action": finding.get("required_action"),
                    "details": deepcopy(finding.get("details", {})),
                },
            )
        )
    return tuple(events)


def _decision_state(status: str) -> InformationState:
    mapping = {
        "approved": InformationState.RELEASED,
        "conditional": InformationState.PENDING,
        "returned": InformationState.RETURNED_FOR_CORRECTION,
        "returned_for_correction": InformationState.RETURNED_FOR_CORRECTION,
        "blocked": InformationState.BLOCKED,
    }
    try:
        return mapping[status]
    except KeyError as exc:
        raise QuintaAdapterError(f"Unknown Quinta Ordem decision status: {status!r}.") from exc


def _finding_state(finding: dict[str, Any], *, severity: str) -> InformationState:
    return_to = (_optional_string(finding.get("return_to")) or "").lower()
    if return_to in {"human_review", "human-review"}:
        return InformationState.HUMAN_REVIEW_REQUIRED
    if return_to:
        return InformationState.RETURNED_FOR_CORRECTION
    if severity in {"critical", "high"}:
        return InformationState.BLOCKED
    return InformationState.PENDING


def _finding_refs(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise QuintaAdapterError("finding evidence_refs must be a list.")
    refs: list[str] = []
    for index, item in enumerate(value):
        if isinstance(item, str) and item.strip():
            refs.append(item.strip())
            continue
        if isinstance(item, Mapping):
            artifact_id = _optional_string(item.get("artifact_id"))
            if artifact_id:
                refs.append(artifact_id)
                continue
        raise QuintaAdapterError(
            f"finding evidence_refs[{index}] must be a string or artifact mapping."
        )
    return tuple(refs)


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = _optional_string(payload.get(key))
    if value is None:
        raise QuintaAdapterError(f"{key} is required.")
    return value


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
