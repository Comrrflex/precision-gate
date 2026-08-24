from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
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
    execution_context: dict[str, Any]
    metrics: PrecisionMetrics
    alerts: tuple[str, ...]

    @property
    def upstream_context(self) -> dict[str, Any]:
        """Preferred read alias while preserving the versioned dataclass field."""
        return self.execution_context


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
        if not isinstance(execution_id, str) or not execution_id.strip():
            raise ValueError("execution_id must be a non-empty string")
        if quinta_decision is not None and quinta_decision.get("execution_id") != execution_id:
            raise ValueError("Quinta Ordem execution_id does not match the Precision execution")

        tcria_events = adapt_tcria_bundle(tcria_bundle)
        quinta_events = adapt_gate_decision(quinta_decision) if quinta_decision else ()
        api_events = adapt_api_outputs(api_outputs)

        # Authoritative order: TCRIA -> Quinta Ordem -> Precision.
        # Precision consumes both upstream products and adds its own derived view.
        # It does not construct a new Quinta Ordem input from Precision events.
        events = (*tcria_events, *quinta_events, *api_events)

        for event in events:
            event.assert_safe_promotion()

        execution_context = {
            "execution_id": execution_id,
            "flow": (
                "tcria->quinta_ordem->precision"
                if quinta_decision is not None
                else "tcria->precision"
            ),
            "flow_complete": quinta_decision is not None,
            "tcria_bundle": deepcopy(dict(tcria_bundle)),
            "quinta_decision": (
                deepcopy(dict(quinta_decision)) if quinta_decision is not None else None
            ),
            "api_output_count": len(api_outputs),
        }

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
