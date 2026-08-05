from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from precision_gate.custody_state import CustodyState, InformationState, PrecisionEvent


class TCRIAAdapterError(ValueError):
    """Raised when a TCRIA bundle cannot be mapped without silent inference."""


def adapt_tcria_bundle(payload: Mapping[str, Any]) -> tuple[PrecisionEvent, ...]:
    """Convert a TCRIA audit bundle into detached Precision events.

    The adapter accepts the documented TCRIA audit-bundle shape with
    ``accusation_set`` and ``non_accusation_set`` records. It never mutates the
    source payload and never promotes a signal, allegation, or inferred value to
    fact unless the record explicitly declares ``fact_supported``.
    """

    if not isinstance(payload, Mapping):
        raise TCRIAAdapterError("TCRIA payload must be a mapping.")

    source = deepcopy(dict(payload))
    records: list[tuple[str, dict[str, Any]]] = []
    for collection_name in ("accusation_set", "non_accusation_set"):
        value = source.get(collection_name, [])
        if not isinstance(value, list):
            raise TCRIAAdapterError(f"{collection_name} must be a list.")
        for index, item in enumerate(value):
            if not isinstance(item, Mapping):
                raise TCRIAAdapterError(f"{collection_name}[{index}] must be a mapping.")
            records.append((collection_name, deepcopy(dict(item))))

    if not records:
        raise TCRIAAdapterError(
            "TCRIA bundle must contain at least one accusation_set or non_accusation_set record."
        )

    return tuple(
        _record_to_event(record, collection_name=collection_name, index=index)
        for index, (collection_name, record) in enumerate(records)
    )


def _record_to_event(
    record: dict[str, Any], *, collection_name: str, index: int
) -> PrecisionEvent:
    extraction_status = str(record.get("extraction_status", "")).strip().lower()
    state = _information_state(record, extraction_status=extraction_status)

    sha256 = _non_empty_string(record.get("sha256"))
    file_name = _non_empty_string(record.get("file_name"))
    file_path = _non_empty_string(record.get("file_path"))
    information_id = sha256 or file_name or file_path or f"tcria-record-{index + 1}"

    explicit_refs = record.get("evidence_refs", [])
    support_refs = _string_tuple(explicit_refs, field_name="evidence_refs")
    if not support_refs and file_name:
        support_refs = (file_name,)

    custody_state = _custody_state(record, sha256=sha256, file_reference=file_name or file_path)
    summary = _summary(record, information_id=information_id)
    promotable = state is InformationState.FACT_SUPPORTED
    requires_human_review = state in {
        InformationState.EXTRACTION_FAILED,
        InformationState.OCR_FAILED,
        InformationState.UNREADABLE,
        InformationState.PENDING,
        InformationState.HUMAN_REVIEW_REQUIRED,
        InformationState.RETURNED_FOR_CORRECTION,
        InformationState.BLOCKED,
    }

    event = PrecisionEvent(
        event_id=f"tcria:{information_id}",
        source_layer="tcria",
        information_id=information_id,
        information_state=state,
        custody_state=custody_state,
        summary=summary,
        support_refs=support_refs,
        sha256=sha256,
        requires_human_review=requires_human_review,
        promotable_as_fact=promotable,
        details={
            "collection": collection_name,
            "classification": record.get("classification"),
            "artifact_type": record.get("artifact_type"),
            "raises_accusation": bool(record.get("raises_accusation", False)),
            "overall_outcome": record.get("overall_outcome"),
            "gates": deepcopy(record.get("gates")),
            "key_signals": deepcopy(record.get("key_signals", {})),
            "source_record": record,
        },
    )
    event.assert_safe_promotion()
    return event


def _information_state(
    record: dict[str, Any], *, extraction_status: str
) -> InformationState:
    declared = _non_empty_string(record.get("information_state"))
    if declared:
        try:
            return InformationState(declared.strip().lower())
        except ValueError as exc:
            raise TCRIAAdapterError(f"Unknown information_state: {declared!r}.") from exc

    if extraction_status in {"ocr_failed", "ocr-error", "ocr_error"}:
        return InformationState.OCR_FAILED
    if extraction_status in {"extraction_failed", "failed", "error"}:
        return InformationState.EXTRACTION_FAILED
    if extraction_status in {"unreadable", "empty", "none"}:
        return InformationState.UNREADABLE

    classification = str(record.get("classification", "")).strip().lower()
    if classification == InformationState.FACT_SUPPORTED.value:
        return InformationState.FACT_SUPPORTED
    if classification in {"pending", "open", "conditional"}:
        return InformationState.PENDING
    if classification in {"blocked", "rejected"}:
        return InformationState.BLOCKED
    if classification in {"returned", "returned_for_correction"}:
        return InformationState.RETURNED_FOR_CORRECTION
    if classification in {"null", "none", "no_conclusion"}:
        return InformationState.NULL_RESULT
    if bool(record.get("raises_accusation", False)):
        return InformationState.ALLEGATION
    return InformationState.TCRIA_SIGNAL


def _custody_state(
    record: dict[str, Any], *, sha256: str | None, file_reference: str | None
) -> CustodyState:
    declared = _non_empty_string(record.get("custody_state"))
    if declared:
        try:
            return CustodyState(declared.strip().lower())
        except ValueError as exc:
            raise TCRIAAdapterError(f"Unknown custody_state: {declared!r}.") from exc
    if sha256:
        return CustodyState.HASHED
    if file_reference:
        return CustodyState.REFERENCED
    return CustodyState.UNKNOWN


def _summary(record: dict[str, Any], *, information_id: str) -> str:
    for key in ("summary", "message", "artifact_type_reason"):
        value = _non_empty_string(record.get(key))
        if value:
            return value
    classification = _non_empty_string(record.get("classification")) or "unclassified"
    return f"TCRIA record {information_id} classified as {classification}."


def _string_tuple(value: Any, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise TCRIAAdapterError(f"{field_name} must be a list or tuple of strings.")
    result: list[str] = []
    for index, item in enumerate(value):
        text = _non_empty_string(item)
        if text is None:
            raise TCRIAAdapterError(f"{field_name}[{index}] must be a non-empty string.")
        result.append(text)
    return tuple(result)


def _non_empty_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
