from __future__ import annotations

from copy import deepcopy
from hashlib import sha256

import pytest

from precision_gate import API_OUTPUT_PROFILE
from precision_gate.api_output_adapter import APIOutputAdapter, APIOutputAdapterError
from precision_gate.contracts import (
    CustodyState,
    GateStatus,
    HumanReviewState,
    InformationState,
    PrecisionEvent,
)
from precision_gate.quinta_adapter import QuintaAdapterError, QuintaExecutionContextAdapter
from precision_gate.tcria_adapter import TCRIAAdapterError, TCRIAAuditBundleAdapter


def _adapt_tcria(bundle: dict) -> object:
    return TCRIAAuditBundleAdapter().adapt(
        bundle,
        trace_id="trace-1",
        observed_at="2026-08-04T10:00:00Z",
        source_id="bundle-1",
        source_ref="memory://tcria/bundle-1",
    )


def _api_envelope(**overrides: object) -> dict:
    payload = {
        "contract_profile": API_OUTPUT_PROFILE,
        "output_id": "api-output-1",
        "input_refs": ["bundle-1"],
        "provider": "synthetic-provider",
        "model": "synthetic-model",
        "prompt_ref": "preset:synthetic-v1",
        "prompt_sha256": sha256(b"synthetic prompt").hexdigest(),
        "response_id": "response-1",
        "output_ref": "memory://api/output-1",
        "output_sha256": sha256(b"synthetic output").hexdigest(),
        "output_type": "inference",
        "response_metadata": {"input_tokens": 10, "output_tokens": 5},
    }
    payload.update(overrides)
    return payload


def test_tcria_adapter_is_pure_and_never_copies_document_text(make_tcria_bundle) -> None:
    source = make_tcria_bundle()
    before = deepcopy(source)

    adaptation = _adapt_tcria(source)

    assert source == before
    assert adaptation.records_observed == 1
    assert len(adaptation.events) == 7
    assert "SYNTHETIC SOURCE TEXT" not in str(adaptation.to_dict())
    record_event = next(event for event in adaptation.events if event.event_id.endswith(":record"))
    assert record_event.information_state is InformationState.FACT_SUPPORTED
    assert record_event.promotable_as_fact is True


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("count", "total_files_scanned"),
        ("hash", "conflicting"),
        ("partition", "conflicts with its published collection"),
        ("missing_gate", "missing required gates"),
    ],
)
def test_tcria_adapter_rejects_inconsistent_contracts(
    make_tcria_bundle,
    mutation: str,
    message: str,
) -> None:
    bundle = make_tcria_bundle(raises_accusation=mutation == "missing_gate")
    record = (bundle["accusation_set"] or bundle["non_accusation_set"])[0]
    if mutation == "count":
        bundle["total_files_scanned"] = 2
    elif mutation == "hash":
        record["document"]["sha256"] = sha256(b"other").hexdigest()
    elif mutation == "partition":
        record["raises_accusation"] = True
    else:
        del record["gates"]["traceabilityCheck"]

    with pytest.raises(TCRIAAdapterError, match=message):
        _adapt_tcria(bundle)


@pytest.mark.parametrize(
    ("status", "expected_state"),
    [
        ("error", InformationState.EXTRACTION_FAILED),
        ("ocr_failed", InformationState.OCR_FAILED),
        ("unsupported", InformationState.UNREADABLE),
        ("skipped", InformationState.PENDING),
    ],
)
def test_tcria_adapter_preserves_extraction_failure_states(
    make_tcria_bundle,
    status: str,
    expected_state: InformationState,
) -> None:
    adaptation = _adapt_tcria(
        make_tcria_bundle(
            classification="fact_supported",
            extraction_status=status,
        )
    )
    record_event = next(event for event in adaptation.events if event.event_id.endswith(":record"))

    assert record_event.information_state is expected_state
    assert record_event.promotable_as_fact is False
    assert record_event.requires_human_review is True


def test_tcria_adapter_rejects_conflicting_duplicate_extraction_status(
    make_tcria_bundle,
) -> None:
    bundle = make_tcria_bundle(extraction_status="ok")
    bundle["non_accusation_set"][0]["document"]["extraction_status"] = "ocr_failed"

    with pytest.raises(TCRIAAdapterError, match="conflicting extraction_status"):
        _adapt_tcria(bundle)


def test_unknown_tcria_gate_status_fails_closed_but_preserves_source(
    make_tcria_bundle,
) -> None:
    bundle = make_tcria_bundle()
    record = bundle["non_accusation_set"][0]
    record["gates"]["prescriptiveGate"]["status"] = "FUTURE_STATUS"

    adaptation = _adapt_tcria(bundle)
    event = next(
        event
        for event in adaptation.events
        if event.details.get("gate_name") == "prescriptiveGate"
    )

    assert event.gate_status is GateStatus.BLOCKED
    assert event.details["source_status"] == "FUTURE_STATUS"
    assert event.details["unknown_source_status"] is True


def test_blocked_source_gate_makes_supported_record_non_promotable(
    make_tcria_bundle,
) -> None:
    bundle = make_tcria_bundle(
        gate_statuses={
            "prescriptiveGate": "BLOCKED",
            "complianceGate": "PASS",
            "traceabilityCheck": "PASS",
            "maturityGate": "PASS",
            "ledgerRuntimeCheck": "PASS",
        }
    )

    adaptation = _adapt_tcria(bundle)
    record = next(event for event in adaptation.events if event.event_id.endswith(":record"))

    assert record.information_state is InformationState.FACT_SUPPORTED
    assert record.gate_status is GateStatus.BLOCKED
    assert record.promotable_as_fact is False
    assert record.requires_human_review is True


def test_blocked_overall_outcome_tightens_passed_source_gates(
    make_tcria_bundle,
) -> None:
    bundle = make_tcria_bundle()
    bundle["non_accusation_set"][0]["overall_outcome"] = "BLOCKED (syntheticOutcome)"

    adaptation = _adapt_tcria(bundle)
    record = next(event for event in adaptation.events if event.event_id.endswith(":record"))

    assert record.gate_status is GateStatus.BLOCKED
    assert record.promotable_as_fact is False


def test_tcria_adapter_marks_unexplained_omission_for_review(
    make_tcria_bundle,
) -> None:
    adaptation = _adapt_tcria(
        make_tcria_bundle(
            interpretation={"observed": True, "mentioned": False},
        )
    )
    record_event = next(event for event in adaptation.events if event.event_id.endswith(":record"))

    assert record_event.requires_human_review is True


def test_api_adapter_records_external_relation_without_hidden_reasoning() -> None:
    event = APIOutputAdapter().adapt(
        _api_envelope(
            claim_relations=[
                {
                    "information_id": "bundle-1:non_accusation_set:0",
                    "relation": "supports",
                }
            ]
        ),
        trace_id="trace-1",
        observed_at="2026-08-04T10:00:00Z",
    )

    assert event.information_state is InformationState.API_INFERENCE
    assert event.promotable_as_fact is False
    assert event.details["internal_reasoning_observed"] is False
    assert event.details["claim_relations"][0]["relation"] == "supports"


@pytest.mark.parametrize(
    "mutation",
    [
        {"output_type": "fact_supported"},
        {"response_metadata": {"reasoning": "hidden"}},
        {"unknown_field": True},
    ],
)
def test_api_adapter_rejects_fact_promotion_hidden_reasoning_and_unknown_fields(
    mutation: dict,
) -> None:
    with pytest.raises(APIOutputAdapterError):
        APIOutputAdapter().adapt(
            _api_envelope(**mutation),
            trace_id="trace-1",
            observed_at="2026-08-04T10:00:00Z",
        )


def test_quinta_handoff_keeps_signals_unpromoted_without_duplicate_decisions() -> None:
    signal = PrecisionEvent(
        event_id="signal-1",
        source_layer="tcria",
        information_id="signal-info-1",
        information_state=InformationState.SIGNAL_PENDING,
        custody_state=CustodyState.REFERENCED,
        summary="Synthetic signal.",
        support_refs=("DOC-1",),
        requires_human_review=True,
        trace_id="trace-1",
        human_review_state=HumanReviewState.REQUIRED,
    )

    payload = QuintaExecutionContextAdapter().build_payload(
        [signal],
        execution_id="trace-1",
    )

    assert payload["decisions"] == []
    assert [item["signal_id"] for item in payload["signals_for_verification"]] == [
        "signal-1"
    ]
    assert all(item.get("promoted") is not True for item in payload["decisions"])


def test_quinta_handoff_rejects_conflicting_evidence_hashes() -> None:
    events = [
        PrecisionEvent(
            event_id=f"evt-{index}",
            source_layer="tcria",
            information_id=f"info-{index}",
            information_state=InformationState.PENDING,
            custody_state=CustodyState.HASHED,
            summary="Synthetic event.",
            sha256=sha256(f"value-{index}".encode()).hexdigest(),
            details={"document_ref": "same-document"},
            trace_id="trace-1",
        )
        for index in range(2)
    ]

    with pytest.raises(QuintaAdapterError, match="conflicting"):
        QuintaExecutionContextAdapter().build_payload(events, execution_id="trace-1")


def test_quinta_handoff_does_not_infer_original_state_and_digest_is_stable() -> None:
    event = PrecisionEvent(
        event_id="evt-1",
        source_layer="tcria",
        information_id="info-1",
        information_state=InformationState.FACT_SUPPORTED,
        custody_state=CustodyState.HASHED,
        summary="Synthetic supported event.",
        support_refs=("DOC-1",),
        sha256=sha256(b"document").hexdigest(),
        trace_id="trace-1",
    )
    adapter = QuintaExecutionContextAdapter()
    payload = adapter.build_payload([event], execution_id="trace-1")

    first = adapter.expected_context_sha256(payload)
    second = adapter.expected_context_sha256(payload)

    assert "modified_original" not in payload["evidence"][0]
    assert first == second
    assert len(first) == 64


def test_quinta_decision_maps_status_and_enforces_review_consistency(
    make_quinta_decision,
) -> None:
    adapter = QuintaExecutionContextAdapter()
    event = adapter.adapt_decision(
        make_quinta_decision(status="blocked"),
        trace_id="trace-1",
        observed_at="2026-08-04T10:00:00Z",
    )

    assert event.information_state is InformationState.BLOCKED
    assert event.gate_status is GateStatus.BLOCKED
    assert event.requires_human_review is True

    with pytest.raises(QuintaAdapterError, match="Approved"):
        adapter.adapt_decision(
            make_quinta_decision(
                status="approved",
                human_review_required=True,
            ),
            trace_id="trace-1",
            observed_at="2026-08-04T10:00:00Z",
        )
