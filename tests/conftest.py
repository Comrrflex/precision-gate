from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from typing import Any

import pytest


GATE_NAMES = (
    "prescriptiveGate",
    "complianceGate",
    "traceabilityCheck",
    "maturityGate",
    "ledgerRuntimeCheck",
)
FIXED_TIME = "2026-08-04T10:00:00Z"


@pytest.fixture
def make_tcria_bundle() -> Callable[..., dict[str, Any]]:
    def factory(
        *,
        classification: str = "fact_supported",
        extraction_status: str = "ok",
        raises_accusation: bool = False,
        gate_statuses: dict[str, str] | None = None,
        signals: dict[str, Any] | None = None,
        interpretation: dict[str, Any] | None = None,
        content: bytes = b"synthetic document",
    ) -> dict[str, Any]:
        document_sha256 = sha256(content).hexdigest()
        statuses = gate_statuses or {name: "PASS" for name in GATE_NAMES}
        gates = {
            name: {
                "status": status,
                "reason": f"Synthetic {name} result.",
                "evidence": None,
            }
            for name, status in statuses.items()
        }
        record = {
            "file_name": "synthetic.txt",
            "file_path": "/external/source/synthetic.txt",
            "sha256": document_sha256,
            "extraction_status": extraction_status,
            "extraction_method": "synthetic",
            "text_quality": "high",
            "document": {
                "relative_path": "case/synthetic.txt",
                "sha256": document_sha256,
                "extraction_status": extraction_status,
                "extraction_method": "synthetic",
                "text": "SYNTHETIC SOURCE TEXT MUST NOT BE COPIED",
            },
            "classification": classification,
            "artifact_type": "synthetic_fixture",
            "artifact_type_reason": "Test-only data.",
            "interpretation": interpretation,
            "raises_accusation": raises_accusation,
            "classification_reasons": ["Explicit synthetic classification."],
            "key_signals": signals or {},
            "gates": gates,
            "overall_outcome": "PASS",
        }
        accusation_set = [record] if raises_accusation else []
        non_accusation_set = [] if raises_accusation else [record]
        return {
            "generated_at": "2026-08-04T09:59:59",
            "audit_basis": "Synthetic TCRIA audit fixture",
            "mode": "strict-explicit-decision-record",
            "total_files_scanned": 1,
            "accusation_set_count": len(accusation_set),
            "classification_counts": {classification: 1},
            "accusation_set": accusation_set,
            "non_accusation_set": non_accusation_set,
        }

    return factory


@pytest.fixture
def make_quinta_decision() -> Callable[..., dict[str, Any]]:
    def factory(
        *,
        trace_id: str = "trace-1",
        status: str = "approved",
        human_review_required: bool | None = None,
        confidence: float = 1.0,
    ) -> dict[str, Any]:
        if human_review_required is None:
            human_review_required = status != "approved"
        return {
            "schema_version": "1.0",
            "execution_id": trace_id,
            "status": status,
            "confidence": confidence,
            "breakdown": {
                "integrity": confidence,
                "traceability": confidence,
                "evidence_support": confidence,
                "logical_consistency": confidence,
                "resolution": confidence,
            },
            "findings": [] if status == "approved" else [{"code": "SYNTHETIC_FINDING"}],
            "remaining_uncertainties": (
                [] if status == "approved" else ["Synthetic unresolved point."]
            ),
            "human_review_required": human_review_required,
            "evaluated_verifiers": [
                "integrity",
                "traceability",
                "evidence_support",
                "logical_consistency",
                "resolution",
            ],
            "execution_context_sha256": sha256(b"synthetic context").hexdigest(),
        }

    return factory
