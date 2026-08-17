"""Precision Gate.

Mobile custody and operational precision layer for TCRIA + Quinta Ordem Gate.
"""

from precision_gate.api_output_adapter import adapt_api_output, adapt_api_outputs
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
    PrecisionMetrics,
    ValidationCase,
    ValidationSummary,
    calculate_metrics,
    evaluate_validation,
)
from precision_gate.pipeline import (
    HumanReviewOutcome,
    PipelineFinalization,
    PipelineResult,
    PipelineStage,
    PrecisionGatePipeline,
    PrecisionPipeline,
)
from precision_gate.quinta_adapter import (
    adapt_gate_decision,
    build_execution_context_payload,
    to_quinta_execution_context,
)
from precision_gate.reporting import (
    render_markdown,
    write_markdown_report,
    write_report_bundle,
)
from precision_gate.tcria_adapter import adapt_tcria_bundle

__all__ = [
    "API_OUTPUT_PROFILE",
    "DEFAULT_VALIDATION_TARGET",
    "QUINTA_EXECUTION_CONTEXT_VERSION",
    "SCHEMA_VERSION",
    "TCRIA_AUDIT_BUNDLE_PROFILE",
    "AlertSeverity",
    "ChainVerification",
    "CoherenceAlert",
    "ContractError",
    "CustodyState",
    "CustodyTrail",
    "GateStatus",
    "HumanReviewOutcome",
    "HumanReviewState",
    "InformationState",
    "LedgerError",
    "MetricResult",
    "PipelineFinalization",
    "PipelineResult",
    "PipelineStage",
    "PrecisionEvent",
    "PrecisionGatePipeline",
    "PrecisionMetrics",
    "PrecisionPipeline",
    "PromotionError",
    "SourceLayer",
    "SourceReference",
    "TrailReceipt",
    "ValidationCase",
    "ValidationSummary",
    "adapt_api_output",
    "adapt_api_outputs",
    "adapt_gate_decision",
    "adapt_tcria_bundle",
    "build_execution_context_payload",
    "calculate_metrics",
    "evaluate_validation",
    "render_markdown",
    "require_owner_decision",
    "to_quinta_execution_context",
    "write_markdown_report",
    "write_report_bundle",
]
