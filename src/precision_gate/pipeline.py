from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from precision_gate.api_output_adapter import adapt_api_outputs
from precision_gate.custody_state import CustodyState, InformationState, PrecisionEvent
from precision_gate.metrics import PrecisionMetrics, calculate_metrics
from precision_gate.quinta_adapter import adapt_gate_decision
from precision_gate.tcria_adapter import adapt_tcria_bundle


@dataclass(frozen=True)
class PipelineResult:
    execution_id: str
    events: tuple[PrecisionEvent, ...]
    upstream_context: dict[str, Any]
    metrics: PrecisionMetrics
    alerts: tuple[str, ...]

    @property
    def execution_context(self) -> dict[str, Any]:
        """Backward-compatible alias for callers that used the old field name."""
        return self.upstream_context


class PrecisionPipeline:
    """Consume the accumulated TCRIA -> Quinta Ordem trail without rewriting it."""

    def run(
        self,
        *,
        execution_id: str,
        tcria_bundle: Mapping[str, Any],
        quinta_decision: Mapping[str, Any] | None = None,
        api_outputs: Sequence[Mapping[str, Any]] = (),
    ) -> PipelineResult:
        tcria_events = adapt_tcria_bundle(tcria_bundle)
        quinta_events = adapt_gate_decision(quinta_decision) if quinta_decision else ()
        api_events = adapt_api_outputs(api_outputs)

        # Authoritative order: TCRIA -> Quinta Ordem -> Precision.
        # Precision consumes both upstream products and adds its own derived view.
        # It does not construct a new Quinta Ordem input from Precision events.
        events = (*tcria_events, *quinta_events, *api_events)

        for event in events:
            event.assert_safe_promotion()

        upstream_context = {
            "execution_id": execution_id,
            "flow": "tcria->quinta_ordem->precision",
            "tcria_bundle": dict(tcria_bundle),
            "quinta_decision": dict(quinta_decision) if quinta_decision else None,
            "api_output_count": len(api_outputs),
        }

        return PipelineResult(
            execution_id=execution_id,
            events=events,
            upstream_context=upstream_context,
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
