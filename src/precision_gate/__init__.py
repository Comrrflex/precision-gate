"""Precision Gate.

Mobile custody and operational precision layer for TCRIA + Quinta Ordem Gate.
"""

from precision_gate.api_output_adapter import adapt_api_output, adapt_api_outputs
from precision_gate.custody_state import CustodyState, InformationState, PrecisionEvent
from precision_gate.metrics import PrecisionMetrics, calculate_metrics
from precision_gate.pipeline import PipelineResult, PrecisionPipeline
from precision_gate.quinta_adapter import (
    adapt_gate_decision,
    build_execution_context_payload,
    to_quinta_execution_context,
)
from precision_gate.reporting import render_markdown, write_markdown_report, write_report_bundle
from precision_gate.tcria_adapter import adapt_tcria_bundle

__all__ = [
    "CustodyState",
    "InformationState",
    "PipelineResult",
    "PrecisionEvent",
    "PrecisionMetrics",
    "PrecisionPipeline",
    "adapt_api_output",
    "adapt_api_outputs",
    "adapt_gate_decision",
    "adapt_tcria_bundle",
    "build_execution_context_payload",
    "calculate_metrics",
    "render_markdown",
    "to_quinta_execution_context",
    "write_markdown_report",
    "write_report_bundle",
]
