from precision_gate.custody_state import InformationState
from precision_gate.pipeline import PrecisionPipeline


def test_pipeline_composes_tcria_api_and_quinta_without_deciding() -> None:
    result = PrecisionPipeline().run(
        execution_id="case-1",
        tcria_bundle={
            "accusation_set": [],
            "non_accusation_set": [
                {
                    "file_name": "case.md",
                    "sha256": "1" * 64,
                    "extraction_status": "ok",
                    "classification": "fact_supported",
                    "information_state": "fact_supported",
                    "evidence_refs": ["EVD-1"],
                    "summary": "Supported source fact.",
                }
            ],
        },
        api_outputs=[
            {
                "output_id": "api-1",
                "content": "Possible synthesis.",
                "kind": "synthesis",
                "support_refs": ["EVD-1"],
            }
        ],
        quinta_decision={
            "execution_id": "case-1",
            "status": "conditional",
            "confidence": 0.8,
            "findings": [
                {
                    "verifier": "resolution",
                    "code": "OPEN_POINT",
                    "severity": "warning",
                    "message": "Point remains unresolved.",
                    "point_id": "open-1",
                    "evidence_refs": ["EVD-1"],
                    "return_to": "human_review",
                    "required_action": "Resolve or formally accept uncertainty.",
                }
            ],
            "remaining_uncertainties": ["open-1"],
            "human_review_required": True,
        },
    )

    states = {event.information_state for event in result.events}
    assert InformationState.FACT_SUPPORTED in states
    assert InformationState.API_INFERENCE in states
    assert InformationState.HUMAN_REVIEW_REQUIRED in states
    assert result.execution_context["execution_id"] == "case-1"
    assert result.metrics.human_review_required >= 1
    assert any("human review" in alert for alert in result.alerts)
