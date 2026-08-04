"""Precision Gate.

Mobile custody and operational precision layer for TCRIA + Quinta Ordem Gate.
"""

from precision_gate.contracts import (
    API_OUTPUT_PROFILE,
    QUINTA_EXECUTION_CONTEXT_VERSION,
    SCHEMA_VERSION,
    TCRIA_AUDIT_BUNDLE_PROFILE,
    AlertSeverity,
    CoherenceAlert,
    ContractError,
    CustodyState,
    GateStatus,
    HumanReviewState,
    InformationState,
    PrecisionEvent,
    PromotionError,
    SourceLayer,
    SourceReference,
)
from precision_gate.custody_state import require_owner_decision
from precision_gate.ledger import ChainVerification, CustodyTrail, LedgerError, TrailReceipt
from precision_gate.metrics import (
    DEFAULT_VALIDATION_TARGET,
    MetricResult,
    ValidationCase,
    ValidationSummary,
    evaluate_validation,
)
from precision_gate.pipeline import (
    HumanReviewOutcome,
    PipelineFinalization,
    PipelineStage,
    PrecisionGatePipeline,
)

__all__ = [
    "API_OUTPUT_PROFILE",
    "QUINTA_EXECUTION_CONTEXT_VERSION",
    "SCHEMA_VERSION",
    "TCRIA_AUDIT_BUNDLE_PROFILE",
    "AlertSeverity",
    "ChainVerification",
    "CoherenceAlert",
    "ContractError",
    "CustodyTrail",
    "CustodyState",
    "DEFAULT_VALIDATION_TARGET",
    "GateStatus",
    "HumanReviewOutcome",
    "HumanReviewState",
    "InformationState",
    "LedgerError",
    "MetricResult",
    "PipelineFinalization",
    "PipelineStage",
    "PrecisionEvent",
    "PrecisionGatePipeline",
    "PromotionError",
    "SourceLayer",
    "SourceReference",
    "TrailReceipt",
    "ValidationCase",
    "ValidationSummary",
    "evaluate_validation",
    "require_owner_decision",
]
