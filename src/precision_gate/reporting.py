from __future__ import annotations

from pathlib import Path
from typing import Callable

from precision_gate.custody_state import InformationState, PrecisionEvent
from precision_gate.pipeline import PipelineResult


REPORT_FILENAMES = (
    "precision_summary.md",
    "precision_custody.md",
    "precision_supported.md",
    "precision_pending.md",
    "precision_blocked.md",
    "precision_returned.md",
    "precision_inferred.md",
    "precision_human_review.md",
)


def render_markdown(result: PipelineResult) -> str:
    """Render one consolidated, derived Markdown report."""

    sections = [
        "# Precision Gate Report",
        "",
        _notice(),
        "",
        f"- Execution ID: `{result.execution_id}`",
        f"- Total events: {result.metrics.total_events}",
        f"- Operational precision: {result.metrics.operational_precision:.2%}",
        f"- Custody integrity: {result.metrics.custody_integrity_rate:.2%}",
        f"- Release safety: {result.metrics.release_safety_rate:.2%}",
        "",
        _event_section(
            "Supported",
            result.events,
            lambda event: event.information_state is InformationState.FACT_SUPPORTED,
        ),
        _event_section(
            "Pending",
            result.events,
            lambda event: event.information_state is InformationState.PENDING,
        ),
        _event_section(
            "Blocked",
            result.events,
            lambda event: event.information_state is InformationState.BLOCKED,
        ),
        _event_section(
            "Returned for correction",
            result.events,
            lambda event: event.information_state is InformationState.RETURNED_FOR_CORRECTION,
        ),
        _event_section(
            "AI/API inferences and opinions",
            result.events,
            lambda event: event.information_state
            in {InformationState.API_INFERENCE, InformationState.API_OPINION},
        ),
        _event_section(
            "Human review required",
            result.events,
            lambda event: event.requires_human_review,
        ),
        "## Alerts",
        "",
        *(f"- {alert}" for alert in result.alerts),
    ]
    if not result.alerts:
        sections.append("- No alerts generated.")
    return "\n".join(sections).rstrip() + "\n"


def write_markdown_report(result: PipelineResult, path: str | Path) -> Path:
    """Write the consolidated Markdown report and return its path."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_markdown(result), encoding="utf-8")
    return target


def write_report_bundle(result: PipelineResult, output_dir: str | Path) -> tuple[Path, ...]:
    """Write eight derived Markdown views without storing original evidence."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    renderers: dict[str, Callable[[PipelineResult], str]] = {
        "precision_summary.md": _summary_report,
        "precision_custody.md": _custody_report,
        "precision_supported.md": lambda item: _single_section_report(
            item,
            "Supported",
            lambda event: event.information_state is InformationState.FACT_SUPPORTED,
        ),
        "precision_pending.md": lambda item: _single_section_report(
            item,
            "Pending",
            lambda event: event.information_state is InformationState.PENDING,
        ),
        "precision_blocked.md": lambda item: _single_section_report(
            item,
            "Blocked",
            lambda event: event.information_state is InformationState.BLOCKED,
        ),
        "precision_returned.md": lambda item: _single_section_report(
            item,
            "Returned for correction",
            lambda event: event.information_state is InformationState.RETURNED_FOR_CORRECTION,
        ),
        "precision_inferred.md": lambda item: _single_section_report(
            item,
            "AI/API inferences and opinions",
            lambda event: event.information_state
            in {InformationState.API_INFERENCE, InformationState.API_OPINION},
        ),
        "precision_human_review.md": lambda item: _single_section_report(
            item,
            "Human review required",
            lambda event: event.requires_human_review,
        ),
    }
    paths: list[Path] = []
    for filename in REPORT_FILENAMES:
        path = directory / filename
        path.write_text(renderers[filename](result), encoding="utf-8")
        paths.append(path)
    return tuple(paths)


def _summary_report(result: PipelineResult) -> str:
    return (
        "# Precision Gate Summary\n\n"
        f"{_notice()}\n\n"
        f"- Execution ID: `{result.execution_id}`\n"
        f"- Total events: {result.metrics.total_events}\n"
        f"- Supported: {result.metrics.supported}\n"
        f"- Pending: {result.metrics.pending}\n"
        f"- Blocked: {result.metrics.blocked}\n"
        f"- Returned: {result.metrics.returned}\n"
        f"- Inferred/opinion: {result.metrics.inferred}\n"
        f"- Human review required: {result.metrics.human_review_required}\n"
        f"- Operational precision: {result.metrics.operational_precision:.2%}\n"
        f"- Custody integrity: {result.metrics.custody_integrity_rate:.2%}\n"
        f"- Release safety: {result.metrics.release_safety_rate:.2%}\n"
    )


def _custody_report(result: PipelineResult) -> str:
    lines = ["# Precision Gate Custody", "", _notice(), ""]
    for event in result.events:
        lines.extend(
            [
                f"## `{event.event_id}`",
                "",
                f"- Information state: `{event.information_state.value}`",
                f"- Custody state: `{event.custody_state.value}`",
                f"- SHA-256: `{event.sha256 or 'not provided'}`",
                f"- Support references: {', '.join(event.support_refs) or 'none'}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _single_section_report(
    result: PipelineResult,
    title: str,
    predicate: Callable[[PrecisionEvent], bool],
) -> str:
    return (
        f"# Precision Gate — {title}\n\n"
        f"{_notice()}\n\n"
        f"{_event_section(title, result.events, predicate)}"
    )


def _event_section(
    title: str,
    events: tuple[PrecisionEvent, ...],
    predicate: Callable[[PrecisionEvent], bool],
) -> str:
    selected = [event for event in events if predicate(event)]
    lines = [f"## {title}", ""]
    if not selected:
        lines.extend(["- None.", ""])
        return "\n".join(lines)
    for event in selected:
        refs = ", ".join(event.support_refs) or "none"
        lines.extend(
            [
                f"- **{event.event_id}** — {event.summary}",
                f"  - state: `{event.information_state.value}`",
                f"  - custody: `{event.custody_state.value}`",
                f"  - support: {refs}",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def _notice() -> str:
    return (
        "> Derived analytical artifact. This report does not modify, replace, or become "
        "part of the original evidence. Final authority remains human."
    )
