from fastapi import HTTPException

from precision_gate.api import PrecisionRunRequest, health, run_precision
from precision_gate.audit import verify_audit_record


def _bundle() -> dict[str, object]:
    return {
        "accusation_set": [],
        "non_accusation_set": [
            {
                "file_name": "case.md",
                "sha256": "3" * 64,
                "extraction_status": "ok",
                "classification": "signal",
            }
        ],
    }


def test_health_endpoint() -> None:
    assert health() == {"status": "ok", "product": "precision-gate"}


def test_run_requires_matching_quinta_execution() -> None:
    payload = PrecisionRunRequest(
        execution_id="case-a",
        tcria_bundle=_bundle(),
        quinta_decision={"execution_id": "case-b", "status": "approved", "findings": []},
    )

    try:
        run_precision(payload)
    except HTTPException as exc:
        assert exc.status_code == 422
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Cross-case input must be rejected")


def test_run_returns_eight_markdown_reports() -> None:
    payload = PrecisionRunRequest(
        execution_id="case-a",
        tcria_bundle=_bundle(),
        quinta_decision={"execution_id": "case-a", "status": "approved", "findings": []},
    )

    response = run_precision(payload)

    assert response["flow"] == "tcria->quinta_ordem->precision"
    assert len(response["markdown_reports"]) == 8
    assert verify_audit_record(response["audit_record"])
