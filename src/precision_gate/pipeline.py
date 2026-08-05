from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from precision_gate.api_output_adapter import adapt_api_outputs
from precision_gate.custody_state import CustodyState, InformationState, PrecisionEvent
from precision_gate.metrics import PrecisionMetrics, calculate_metrics
from precision_gate.quinta_adapter import adapt_gate_decision, build_execution_context_payload
from precision_gate.tcria_adapter import adapt_tcria_bundle


@dataclass(frozen=True)
class PipelineResult:
    execution_id: str
    events: tuple[PrecisionEvent, ...]
    execution_context: dict[str, Any]
    metrics: PrecisionMetrics
    alerts: tuple[str, ...]


class PrecisionPipeline:
    """Orchestrate the trail without making the final human decision."""

    def run(
        self,
        *,
        execution_id: str,
        tcria_bundle: Mapping[str, Any],
        api_outputs: Sequence[Mapping[str, Any]] = (),
        quinta_decision: Mapping[str, Any] | None = None,
    ) -> PipelineResult:
        tcria_events = adapt_tcria_bundle(tcria_bundle)
        api_events = adapt_api_outputs(api_outputs)
        pre_gate_events = (*tcria_events, *api_events)
        execution_context = build_execution_context_payload(
            pre_gate_events,
            execution_id=execution_id,
            metadata={"source": "precision_gate_pipeline"},
        )
        quinta_events = adapt_gate_decision(quinta_decision) if quinta_decision else ()
        events = (*pre_gate_events, *quinta_events)

        for event in events:
            event.assert_safe_promotion()

        return PipelineResult(
            execution_id=execution_id,
            events=events,
            execution_context=execution_context,
            metrics=calculate_metrics(events),
            alerts=_alerts(events),
        )


def _alerts(events: tuple[PrecisionEvent, ...]) -> tuple[str, ...]:
    alerts: list[str] = []
    for event in events:
        if event.custody_state in {CustodyState.BROKEN, CustodyState.UNKNOWN}:
            alerts.append(
                f"{event.event_id}: custody is {event.custody_state.value}; review the trail."
            )
        if event.requires_human_review:
            alerts.append(f"{event.event_id}: human review is required.")
        if event.information_state in {
            InformationState.BLOCKED,
            InformationState.RETURNED_FOR_CORRECTION,
        }:
            alerts.append(
                f"{event.event_id}: state is {event.information_state.value}; "
                "do not release silently."
            )
    return tuple(dict.fromkeys(alerts))
