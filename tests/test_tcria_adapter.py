import pytest

from precision_gate.custody_state import CustodyState, InformationState
from precision_gate.tcria_adapter import TCRIAAdapterError, adapt_tcria_bundle


def _bundle(record: dict, *, accusation: bool = False) -> dict:
    return {
        "generated_at": "2026-08-05T00:00:00",
        "accusation_set": [record] if accusation else [],
        "non_accusation_set": [] if accusation else [record],
    }


def test_tcria_supported_fact_is_preserved_with_hash_and_reference() -> None:
    events = adapt_tcria_bundle(
        _bundle(
            {
                "file_name": "case.md",
                "sha256": "a" * 64,
                "extraction_status": "ok",
                "classification": "fact_supported",
                "information_state": "fact_supported",
                "evidence_refs": ["EVD-001"],
                "summary": "Fact supported by the source trail.",
            }
        )
    )

    event = events[0]
    assert event.information_state is InformationState.FACT_SUPPORTED
    assert event.custody_state is CustodyState.HASHED
    assert event.promotable_as_fact is True
    assert event.support_refs == ("EVD-001",)


def test_tcria_accusation_remains_allegation() -> None:
    event = adapt_tcria_bundle(
        _bundle(
            {
                "file_name": "statement.md",
                "sha256": "b" * 64,
                "extraction_status": "ok",
                "classification": "accusatory",
                "raises_accusation": True,
            },
            accusation=True,
        )
    )[0]

    assert event.information_state is InformationState.ALLEGATION
    assert event.promotable_as_fact is False


def test_tcria_ocr_failure_is_not_readable_evidence() -> None:
    event = adapt_tcria_bundle(
        _bundle(
            {
                "file_name": "scan.pdf",
                "sha256": "c" * 64,
                "extraction_status": "ocr_failed",
                "classification": "unknown",
            }
        )
    )[0]

    assert event.information_state is InformationState.OCR_FAILED
    assert event.requires_human_review is True
    assert event.promotable_as_fact is False


def test_tcria_bundle_requires_records() -> None:
    with pytest.raises(TCRIAAdapterError, match="at least one"):
        adapt_tcria_bundle({"accusation_set": [], "non_accusation_set": []})
