import pytest

from precision_gate.custody_state import CustodyState, InformationState, PrecisionEvent
from precision_gate.quinta_adapter import (
    QuintaAdapterError,
    adapt_gate_decision,
    build_execution_context_payload,
)


def test_execution_context_payload_matches_quinta_contract() -> None:
    event = PrecisionEvent(
        event_id="evt-1",
        source_layer="tcria",
        information_id="fact-1",
        information_state=InformationState.FACT_SUPPORTED,
        custody_state=CustodyState.HASHED,
        summary="Supported fact.",
        support_refs=("EVD-1",),
        sha256="e" * 64,
        promotable_as_fact=True,
    )

    payload = build_execution_context_payload([event], execution_id="run-1")

    assert set(payload) == {
        "execution_id",
        "evidence",
        "artifacts",
        "gate_results",
        "logs",
        "decisions",
        "metadata",
    }
    assert payload["execution_id"] == "run-1"
    assert payload["evidence"][0]["artifact_id"] == "fact-1"
    assert payload["metadata"]["human_decision_required"] is True


def test_quinta_blocked_decision_becomes_blocked_event() -> None:
    events = adapt_gate_decision(
        {
            "execution_id": "run-2",
            "status": "blocked",
            "confidence": 0.42,
            "breakdown": {"integrity": 1.0},
            "findings": [],
            "remaining_uncertainties": ["Open point"],
            "human_review_required": True,
            "execution_context_sha256": "f" * 64,
        }
    )

    assert events[0].information_state is InformationState.BLOCKED
    assert events[0].requires_human_review is True
    assert events[0].custody_state is CustodyState.HASHED


def test_quinta_finding_preserves_required_action_and_human_review() -> None:
    events = adapt_gate_decision(
        {
            "execution_id": "run-3",
            "status": "conditional",
            "findings": [
                {
                    "verifier": "resolution",
                    "code": "UNRESOLVED_POINT",
                    "severity": "warning",
                    "message": "Point remains unresolved.",
                    "point_id": "point-1",
                    "evidence_refs": [{"artifact_id": "EVD-1"}],
                    "return_to": "human_review",
                    "required_action": "Resolve or formally register uncertainty.",
                }
            ],
            "remaining_uncertainties": ["point-1"],
            "human_review_required": True,
        }
    )

    finding = events[1]
    assert finding.information_state is InformationState.HUMAN_REVIEW_REQUIRED
    assert finding.support_refs == ("EVD-1",)
    assert finding.details["required_action"].startswith("Resolve")


def test_quinta_unknown_status_is_rejected() -> None:
    with pytest.raises(QuintaAdapterError, match="Unknown"):
        adapt_gate_decision(
            {
                "execution_id": "run-4",
                "status": "maybe",
                "findings": [],
            }
        )
