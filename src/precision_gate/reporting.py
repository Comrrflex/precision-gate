from __future__ import annotations

import json
import os
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from precision_gate.contracts import (
    InformationState,
    PrecisionEvent,
    SourceLayer,
    canonical_json,
    to_jsonable,
    utc_now,
)
from precision_gate.metrics import ValidationSummary
from precision_gate.pipeline import PipelineStage, PrecisionGatePipeline


class ReportingError(RuntimeError):
    """Raised when a final report cannot be produced without custody risk."""


@dataclass(frozen=True)
class ReportBundle:
    trace_id: str
    report_filename: str
    markdown_filename: str
    manifest_filename: str
    report_json: str
    report_markdown: str
    manifest_json: str
    report_sha256: str
    markdown_sha256: str
    manifest_sha256: str


@dataclass(frozen=True)
class ReportPaths:
    directory: Path
    report_json: Path
    report_markdown: Path
    manifest_json: Path


class FinalReportBuilder:
    """Build one consolidated report after the pipeline reaches finalization."""

    def build(
        self,
        pipeline: PrecisionGatePipeline,
        *,
        generated_at: str | None = None,
        validation: ValidationSummary | None = None,
    ) -> ReportBundle:
        if not isinstance(pipeline, PrecisionGatePipeline):
            raise ReportingError("pipeline must be a PrecisionGatePipeline.")
        if pipeline.stage is not PipelineStage.FINALIZED or pipeline.finalization is None:
            raise ReportingError("Formal reports may be built only after finalization.")
        verification = pipeline.trail.verify()
        if not verification.valid:
            raise ReportingError(
                "Custody chain verification failed: " + "; ".join(verification.errors)
            )

        finalization = pipeline.finalization
        events = pipeline.trail.events
        sources = _sources(events)
        state_counts = Counter(event.information_state.value for event in events)
        report = {
            "schema_version": "1.0",
            "report_type": "precision_gate.final_report",
            "generated_at": generated_at or utc_now(),
            "trace_id": pipeline.trace_id,
            "product_boundary": {
                "authority": "non_authoritative_reference",
                "final_decision_remains_human": True,
                "released_meaning": (
                    "Eligible delivery to the responsible human or institutional flow; "
                    "not an autonomous decision about rights or material consequences."
                ),
            },
            "outcome": finalization.to_dict(),
            "custody_verification": to_jsonable(verification),
            "sources": sources,
            "state_counts": dict(sorted(state_counts.items())),
            "supported_facts": _event_refs(events, {InformationState.FACT_SUPPORTED}),
            "allegations": _event_refs(events, {InformationState.ALLEGATION}),
            "hypotheses": _event_refs(events, {InformationState.HYPOTHESIS}),
            "signals": _event_refs(
                events,
                {InformationState.SIGNAL_PENDING, InformationState.TCRIA_SIGNAL},
            ),
            "api_interpretations": _api_event_refs(events),
            "pending_or_review": _event_refs(
                events,
                {
                    InformationState.PENDING,
                    InformationState.HUMAN_REVIEW_REQUIRED,
                    InformationState.RETURNED_FOR_CORRECTION,
                },
            ),
            "blocked_or_unreadable": _event_refs(
                events,
                {
                    InformationState.BLOCKED,
                    InformationState.EXTRACTION_FAILED,
                    InformationState.OCR_FAILED,
                    InformationState.UNREADABLE,
                },
            ),
            "released": _event_refs(events, {InformationState.RELEASED}),
            "coherence_alerts": [alert.to_dict() for alert in finalization.assessment.alerts],
            "human_reviews": [
                event.to_dict()
                for event in events
                if event.source_layer is SourceLayer.HUMAN_REVIEW
            ],
            "remaining_uncertainties": _remaining_uncertainties(events),
            "validation": validation.to_dict() if validation is not None else None,
            "custody_trail": pipeline.trail.to_dict(),
        }
        report_json = _pretty_json(report)
        report_markdown = _render_markdown(report)
        report_sha256 = _text_sha256(report_json)
        markdown_sha256 = _text_sha256(report_markdown)
        safe_trace_id = _safe_segment(pipeline.trace_id)
        report_filename = f"{safe_trace_id}_precision_report.json"
        markdown_filename = f"{safe_trace_id}_precision_report.md"
        manifest_filename = f"{safe_trace_id}_manifest.json"
        manifest_without_digest = {
            "schema_version": "1.0",
            "trace_id": pipeline.trace_id,
            "final_chain_sha256": pipeline.trail.final_chain_sha256,
            "files": [
                {"path": report_filename, "sha256": report_sha256},
                {"path": markdown_filename, "sha256": markdown_sha256},
            ],
            "notice": (
                "Derived audit artifacts only. Source evidence remains external and unchanged."
            ),
        }
        manifest_sha256 = sha256(
            canonical_json(manifest_without_digest).encode("utf-8")
        ).hexdigest()
        manifest = {
            **manifest_without_digest,
            "manifest_sha256": manifest_sha256,
        }
        return ReportBundle(
            trace_id=pipeline.trace_id,
            report_filename=report_filename,
            markdown_filename=markdown_filename,
            manifest_filename=manifest_filename,
            report_json=report_json,
            report_markdown=report_markdown,
            manifest_json=_pretty_json(manifest),
            report_sha256=report_sha256,
            markdown_sha256=markdown_sha256,
            manifest_sha256=manifest_sha256,
        )


def write_report_bundle(
    bundle: ReportBundle,
    output_dir: str | Path,
    *,
    forbidden_roots: Sequence[str | Path] = (),
) -> ReportPaths:
    if not isinstance(bundle, ReportBundle):
        raise ReportingError("bundle must be a ReportBundle.")
    root = Path(output_dir).expanduser().resolve()
    for forbidden in forbidden_roots:
        forbidden_root = Path(forbidden).expanduser().resolve()
        if root == forbidden_root or forbidden_root in root.parents:
            raise ReportingError(
                f"Output directory must not be inside source evidence root {forbidden_root}."
            )
    directory = root / _safe_segment(bundle.trace_id)
    directory.mkdir(parents=True, exist_ok=True)
    if directory.is_symlink():
        raise ReportingError("Report directory must not be a symbolic link.")

    report_path = directory / bundle.report_filename
    markdown_path = directory / bundle.markdown_filename
    manifest_path = directory / bundle.manifest_filename
    _write_exact(report_path, bundle.report_json.encode("utf-8"))
    _write_exact(markdown_path, bundle.report_markdown.encode("utf-8"))
    _write_exact(manifest_path, bundle.manifest_json.encode("utf-8"))

    if _file_sha256(report_path) != bundle.report_sha256:
        raise ReportingError("Written JSON report digest does not match the manifest.")
    if _file_sha256(markdown_path) != bundle.markdown_sha256:
        raise ReportingError("Written Markdown report digest does not match the manifest.")
    return ReportPaths(
        directory=directory,
        report_json=report_path,
        report_markdown=markdown_path,
        manifest_json=manifest_path,
    )


def _sources(events: Sequence[PrecisionEvent]) -> list[dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.source_reference is None:
            continue
        payload = event.source_reference
        item = to_jsonable(payload)
        existing = sources.get(payload.source_id)
        if existing is not None and existing != item:
            raise ReportingError(f"Source {payload.source_id!r} has conflicting report references.")
        sources[payload.source_id] = item
    return [sources[key] for key in sorted(sources)]


def _event_refs(
    events: Sequence[PrecisionEvent],
    states: set[InformationState],
) -> list[dict[str, Any]]:
    return [
        {
            "event_id": event.event_id,
            "information_id": event.information_id,
            "state": event.information_state.value,
            "summary": event.summary,
            "support_refs": list(event.support_refs),
        }
        for event in events
        if event.information_state in states
    ]


def _api_event_refs(events: Sequence[PrecisionEvent]) -> list[dict[str, Any]]:
    return [
        {
            "event_id": event.event_id,
            "information_id": event.information_id,
            "state": event.information_state.value,
            "summary": event.summary,
            "support_refs": list(event.support_refs),
            "provider": event.details.get("provider"),
            "model": event.details.get("model"),
        }
        for event in events
        if event.source_layer is SourceLayer.API
    ]


def _remaining_uncertainties(events: Sequence[PrecisionEvent]) -> list[str]:
    uncertainties: list[str] = []
    for event in events:
        value = event.details.get("remaining_uncertainties", ())
        if not isinstance(value, tuple):
            continue
        for item in value:
            if isinstance(item, str) and item not in uncertainties:
                uncertainties.append(item)
    return uncertainties


def _render_markdown(report: Mapping[str, Any]) -> str:
    outcome = report["outcome"]
    verification = report["custody_verification"]
    lines = [
        "# Precision Gate Final Report",
        "",
        f"- **Trace:** `{report['trace_id']}`",
        f"- **Generated:** `{report['generated_at']}`",
        f"- **Released to human/institutional flow:** `{outcome['released']}`",
        (
            "- **All released facts approved by their source gates:** "
            f"`{outcome['source_facts_gate_approved']}`"
        ),
        f"- **Quinta Ordem status:** `{outcome['gate_status']}`",
        f"- **Human outcome:** `{outcome['human_outcome']}`",
        "",
        "> This is a non-authoritative operational reference. The final decision remains human.",
        "",
        "## Custody verification",
        "",
        f"- **Valid:** `{verification['valid']}`",
        f"- **Events:** `{verification['checkpoint_count']}`",
        f"- **Final chain SHA-256:** `{verification['final_chain_sha256']}`",
        "",
        "## Best-supported operational reading",
        "",
        f"- **Support tier:** `{outcome['assessment']['support_tier']}`",
        (
            "- **Events:** "
            + (
                ", ".join(
                    f"`{event_id}`"
                    for event_id in outcome["assessment"]["best_supported_event_ids"]
                )
                or "None"
            )
        ),
        f"- **Conflict:** `{outcome['assessment']['conflict']}`",
        "",
        "## Informational states",
        "",
        "| State | Count |",
        "|---|---:|",
    ]
    for state, count in report["state_counts"].items():
        lines.append(f"| `{state}` | {count} |")

    lines.extend(["", "## Coherence alerts", ""])
    alerts = report["coherence_alerts"]
    if alerts:
        for alert in alerts:
            lines.append(f"- **{alert['severity']} / `{alert['code']}`:** {alert['message']}")
    else:
        lines.append("- None.")

    lines.extend(["", "## Remaining uncertainties", ""])
    uncertainties = report["remaining_uncertainties"]
    if uncertainties:
        lines.extend(f"- {item}" for item in uncertainties)
    else:
        lines.append("- None recorded.")

    lines.extend(
        [
            "",
            "## Human review",
            "",
            f"- **Recorded review events:** {len(report['human_reviews'])}",
            (f"- **Review still required:** `{outcome['assessment']['requires_human_review']}`"),
            "",
            "## Validation",
            "",
        ]
    )
    validation = report["validation"]
    if validation is None:
        lines.append("- No labeled validation set was attached to this execution.")
    else:
        lines.append(f"- **Observed target:** `{validation['target']}`")
        lines.append(f"- **Cases:** `{validation['case_count']}`")
        lines.append(f"- **All evaluated metrics met target:** `{validation['target_met']}`")
        for metric in validation["metrics"]:
            lines.append(
                f"- `{metric['name']}`: {metric['numerator']}/{metric['denominator']} "
                f"({metric['status']})"
            )
    lines.extend(
        [
            "",
            "The 95% target, when used, is an observed validation threshold over labeled cases.",
            "It is not a promise of absolute truth or autonomous decision correctness.",
            "",
        ]
    )
    return "\n".join(lines)


def _pretty_json(value: Any) -> str:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _text_sha256(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _safe_segment(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    if not normalized:
        normalized = "precision-trace"
    suffix = sha256(value.encode("utf-8")).hexdigest()[:10]
    return f"{normalized[:80]}-{suffix}"


def _write_exact(path: Path, content: bytes) -> None:
    if path.exists():
        if not path.is_file() or path.is_symlink():
            raise ReportingError(f"Refusing to replace non-regular report path: {path}")
        if path.read_bytes() != content:
            raise ReportingError(f"Refusing to overwrite different report content: {path}")
        return
    try:
        with path.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise ReportingError(f"Could not write report artifact: {path}") from exc


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
