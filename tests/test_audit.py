from copy import deepcopy

from precision_gate.audit import build_audit_record, verify_audit_record
from precision_gate.pipeline import PrecisionPipeline


def _result():
    return PrecisionPipeline().run(
        execution_id="audit-1",
        tcria_bundle={
            "accusation_set": [],
            "non_accusation_set": [
                {"file_name": "synthetic.md", "sha256": "a" * 64, "classification": "signal"}
            ],
        },
        quinta_decision={"execution_id": "audit-1", "status": "approved", "findings": []},
    )


def test_audit_record_is_deterministic_and_verifiable() -> None:
    first = build_audit_record(_result())
    second = build_audit_record(_result())
    assert first == second
    assert verify_audit_record(first)
    assert first["upstream"]["tcria_bundle_sha256"]
    assert first["chain_head_sha256"] == first["events"][-1]["event_hash"]


def test_audit_record_detects_event_tampering() -> None:
    record = deepcopy(build_audit_record(_result()))
    record["events"][0]["event"]["summary"] = "tampered"
    assert not verify_audit_record(record)
