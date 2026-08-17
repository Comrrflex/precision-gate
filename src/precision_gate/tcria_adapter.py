from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, ClassVar

from precision_gate._validation import (
    canonical_sha256,
    optional_mapping,
    optional_text,
    require_bool,
    require_mapping,
    require_mapping_list,
    require_non_negative_int,
    require_text,
    strict_snapshot,
)
from precision_gate.contracts import (
    TCRIA_AUDIT_BUNDLE_PROFILE,
    ContractError,
    CustodyState,
    GateStatus,
    HumanReviewState,
    InformationState,
    PrecisionEvent,
    SourceLayer,
    SourceReference,
    to_jsonable,
    validate_sha256,
)


class TCRIAAdapterError(ContractError):
    """Raised when a TCRIA bundle cannot be observed without inference."""


@dataclass(frozen=True)
class TCRIAAdaptation:
    source_reference: SourceReference
    events: tuple[PrecisionEvent, ...]
    records_observed: int
    payload_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


class TCRIAAuditBundleAdapter:
    """Pure observer for the completed official TCRIA audit bundle."""

    canonical_gate_order: ClassVar[tuple[str, ...]] = (
        "prescriptiveGate",
        "complianceGate",
        "traceabilityCheck",
        "maturityGate",
        "ledgerRuntimeCheck",
    )

    def adapt(
        self,
        bundle: Mapping[str, Any],
        *,
        trace_id: str,
        observed_at: str,
        source_id: str,
        source_ref: str,
        source_artifact_sha256: str | None = None,
        producer_revision: str | None = None,
        contract_profile: str = TCRIA_AUDIT_BUNDLE_PROFILE,
    ) -> TCRIAAdaptation:
        if contract_profile != TCRIA_AUDIT_BUNDLE_PROFILE:
            raise TCRIAAdapterError(f"Unsupported TCRIA contract profile: {contract_profile!r}.")
        snapshot = strict_snapshot(bundle, name="TCRIA bundle")
        payload_sha256 = canonical_sha256(snapshot)
        artifact_sha256 = (
            validate_sha256(source_artifact_sha256, field_name="source_artifact_sha256")
            if source_artifact_sha256 is not None
            else payload_sha256
        )
        source_reference = SourceReference(
            source_id=source_id,
            source_ref=source_ref,
            artifact_sha256=artifact_sha256,
            payload_sha256=payload_sha256,
            contract_profile=contract_profile,
            schema_version="1",
            producer_revision=producer_revision,
        )

        accusation_set = require_mapping_list(snapshot, "accusation_set")
        non_accusation_set = require_mapping_list(snapshot, "non_accusation_set")
        declared_accusations = require_non_negative_int(snapshot, "accusation_set_count")
        declared_total = require_non_negative_int(snapshot, "total_files_scanned")
        if declared_accusations != len(accusation_set):
            raise TCRIAAdapterError(
                "accusation_set_count does not match the published accusation_set."
            )
        if declared_total != len(accusation_set) + len(non_accusation_set):
            raise TCRIAAdapterError(
                "total_files_scanned does not match the published record collections."
            )

        events = [
            PrecisionEvent(
                event_id=f"{trace_id}:tcria:bundle",
                source_layer=SourceLayer.TCRIA,
                information_id=source_id,
                information_state=InformationState.ORIGINAL_PRESERVED,
                custody_state=CustodyState.HASHED,
                summary="Observed the completed official TCRIA audit bundle.",
                sha256=artifact_sha256,
                details={
                    "audit_basis": optional_text(snapshot, "audit_basis"),
                    "generated_at": optional_text(snapshot, "generated_at"),
                    "mode": optional_text(snapshot, "mode"),
                    "records_observed": declared_total,
                    "accusation_records": declared_accusations,
                },
                trace_id=trace_id,
                observed_at=observed_at,
                source_reference=source_reference,
            )
        ]

        observed_classifications: Counter[str] = Counter()
        for partition, records in (
            ("accusation_set", accusation_set),
            ("non_accusation_set", non_accusation_set),
        ):
            for index, record in enumerate(records):
                expected_accusation = partition == "accusation_set"
                record_events, classification = self._adapt_record(
                    record,
                    partition=partition,
                    index=index,
                    expected_accusation=expected_accusation,
                    trace_id=trace_id,
                    observed_at=observed_at,
                    source_reference=source_reference,
                )
                observed_classifications[classification] += 1
                events.extend(record_events)

        self._validate_classification_counts(snapshot, observed_classifications)
        return TCRIAAdaptation(
            source_reference=source_reference,
            events=tuple(events),
            records_observed=declared_total,
            payload_sha256=payload_sha256,
        )

    def _adapt_record(
        self,
        record: Mapping[str, Any],
        *,
        partition: str,
        index: int,
        expected_accusation: bool,
        trace_id: str,
        observed_at: str,
        source_reference: SourceReference,
    ) -> tuple[list[PrecisionEvent], str]:
        path = f"{partition}[{index}]"
        raises_accusation = require_bool(record, "raises_accusation")
        if raises_accusation is not expected_accusation:
            raise TCRIAAdapterError(
                f"{path}.raises_accusation conflicts with its published collection."
            )
        classification = require_text(record, "classification")
        document = require_mapping(record, "document")
        document_sha256 = validate_sha256(
            require_text(record, "sha256"),
            field_name=f"{path}.sha256",
        )
        nested_sha256 = validate_sha256(
            require_text(document, "sha256"),
            field_name=f"{path}.document.sha256",
        )
        if document_sha256 != nested_sha256:
            raise TCRIAAdapterError(f"{path} contains conflicting document SHA-256 values.")

        document_ref = _document_reference(record, document, path)
        extraction_status = _extraction_status(record, document, path)
        extraction_method = _optional_record_text(record, document, "extraction_method")
        classification_reasons = _classification_reasons(record, path)
        state = _record_state(classification, raises_accusation, extraction_status)
        information_id = f"{source_reference.source_id}:{partition}:{index}"
        gate_events = self._gate_events(
            record,
            trace_id=trace_id,
            observed_at=observed_at,
            information_id=information_id,
            document_ref=document_ref,
            document_sha256=document_sha256,
            partition=partition,
            index=index,
            raises_accusation=raises_accusation,
            source_reference=source_reference,
        )
        record_gate_status = _aggregate_gate_status(gate_events)
        overall_outcome = optional_text(record, "overall_outcome")
        overall_outcome_status, unknown_overall_outcome = _overall_outcome_status(
            overall_outcome
        )
        record_gate_status = _stricter_gate_status(
            record_gate_status,
            overall_outcome_status,
        )
        trace_observation = _trace_observation(record)
        unexplained_omission = (
            trace_observation.get("observed") is True
            and trace_observation.get("mentioned") is False
            and not trace_observation.get("omission_reason")
        )
        requires_review = unexplained_omission or state in {
            InformationState.EXTRACTION_FAILED,
            InformationState.OCR_FAILED,
            InformationState.UNREADABLE,
            InformationState.NULL_RESULT,
            InformationState.ALLEGATION,
            InformationState.HYPOTHESIS,
            InformationState.SIGNAL_PENDING,
            InformationState.PENDING,
        }
        if record_gate_status is not GateStatus.APPROVED:
            requires_review = True
        is_supported_fact = state is InformationState.FACT_SUPPORTED
        promotable_fact = is_supported_fact and record_gate_status is GateStatus.APPROVED
        support_refs = (document_ref,) if is_supported_fact else ()

        events = [
            PrecisionEvent(
                event_id=f"{trace_id}:tcria:{partition}:{index}:record",
                source_layer=SourceLayer.TCRIA,
                information_id=information_id,
                information_state=state,
                custody_state=CustodyState.HASHED,
                summary=f"TCRIA classified {document_ref} as {classification}.",
                support_refs=support_refs,
                sha256=document_sha256,
                requires_human_review=requires_review,
                promotable_as_fact=promotable_fact,
                details={
                    "source_partition": partition,
                    "source_record_index": index,
                    "document_ref": document_ref,
                    "source_classification": classification,
                    "classification_reasons": classification_reasons,
                    "raises_accusation": raises_accusation,
                    "artifact_type": optional_text(record, "artifact_type"),
                    "artifact_type_reason": optional_text(record, "artifact_type_reason"),
                    "overall_outcome": overall_outcome,
                    "unknown_overall_outcome": unknown_overall_outcome,
                    "extraction_status": extraction_status,
                    "extraction_method": extraction_method,
                    "text_quality": optional_text(record, "text_quality"),
                    "trace_observation": trace_observation,
                    "record_gate_status": record_gate_status.value,
                    "record_gate_event_ids": tuple(
                        event.event_id for event in gate_events
                    ),
                },
                trace_id=trace_id,
                observed_at=observed_at,
                source_reference=source_reference,
                gate_status=record_gate_status,
                human_review_state=(
                    HumanReviewState.REQUIRED if requires_review else HumanReviewState.NOT_REQUIRED
                ),
            )
        ]
        events.extend(
            self._signal_events(
                record,
                trace_id=trace_id,
                observed_at=observed_at,
                information_id=information_id,
                document_ref=document_ref,
                document_sha256=document_sha256,
                partition=partition,
                index=index,
                source_reference=source_reference,
            )
        )
        events.extend(gate_events)
        return events, classification

    def _signal_events(
        self,
        record: Mapping[str, Any],
        *,
        trace_id: str,
        observed_at: str,
        information_id: str,
        document_ref: str,
        document_sha256: str,
        partition: str,
        index: int,
        source_reference: SourceReference,
    ) -> list[PrecisionEvent]:
        raw_signals = record.get("key_signals", record.get("signals", {}))
        if raw_signals is None:
            return []
        if not isinstance(raw_signals, Mapping):
            raise TCRIAAdapterError(f"{partition}[{index}].key_signals must be a mapping.")
        events: list[PrecisionEvent] = []
        for signal_name in sorted(raw_signals):
            if not isinstance(signal_name, str) or not signal_name.strip():
                raise TCRIAAdapterError("TCRIA signal names must be non-empty strings.")
            signal_value = raw_signals[signal_name]
            count = _signal_count(signal_value)
            if count == 0:
                continue
            signal_id = f"{information_id}:signal:{signal_name}"
            events.append(
                PrecisionEvent(
                    event_id=f"{trace_id}:tcria:{partition}:{index}:signal:{signal_name}",
                    source_layer=SourceLayer.TCRIA,
                    information_id=signal_id,
                    information_state=InformationState.SIGNAL_PENDING,
                    custody_state=CustodyState.REFERENCED,
                    summary=f"TCRIA recorded the {signal_name} signal for verification.",
                    support_refs=(document_ref,),
                    sha256=document_sha256,
                    requires_human_review=True,
                    details={
                        "signal_name": signal_name,
                        "signal_item_count": count,
                        "document_ref": document_ref,
                        "source_partition": partition,
                        "source_record_index": index,
                    },
                    trace_id=trace_id,
                    observed_at=observed_at,
                    caused_by=(f"{trace_id}:tcria:{partition}:{index}:record",),
                    source_reference=source_reference,
                    human_review_state=HumanReviewState.REQUIRED,
                )
            )
        return events

    def _gate_events(
        self,
        record: Mapping[str, Any],
        *,
        trace_id: str,
        observed_at: str,
        information_id: str,
        document_ref: str,
        document_sha256: str,
        partition: str,
        index: int,
        raises_accusation: bool,
        source_reference: SourceReference,
    ) -> list[PrecisionEvent]:
        raw_gates = record.get("gates")
        if raw_gates is None:
            if raises_accusation:
                raise TCRIAAdapterError(
                    f"{partition}[{index}].gates is required for an accusatory record."
                )
            return []
        if not isinstance(raw_gates, Mapping):
            raise TCRIAAdapterError(f"{partition}[{index}].gates must be a mapping or null.")
        if raises_accusation:
            missing = [name for name in self.canonical_gate_order if name not in raw_gates]
            if missing:
                raise TCRIAAdapterError(
                    f"{partition}[{index}].gates is missing required gates: "
                    + ", ".join(missing)
                    + "."
                )
        ordered_names = [
            *[name for name in self.canonical_gate_order if name in raw_gates],
            *sorted(name for name in raw_gates if name not in self.canonical_gate_order),
        ]
        events: list[PrecisionEvent] = []
        prior_blocked = False
        for gate_name in ordered_names:
            if not isinstance(gate_name, str) or not gate_name.strip():
                raise TCRIAAdapterError("TCRIA gate names must be non-empty strings.")
            gate = raw_gates[gate_name]
            if not isinstance(gate, Mapping):
                raise TCRIAAdapterError(
                    f"{partition}[{index}].gates.{gate_name} must be a mapping."
                )
            source_status = require_text(gate, "status")
            source_reason = require_text(gate, "reason")
            source_evidence = gate.get("evidence")
            if source_evidence is not None and not isinstance(source_evidence, str):
                raise TCRIAAdapterError(
                    f"{partition}[{index}].gates.{gate_name}.evidence must be text or null."
                )
            gate_status, unknown_status = _gate_status(source_status)
            blocked_before = prior_blocked
            if blocked_before:
                gate_status = GateStatus.BLOCKED
            prior_blocked = gate_status is GateStatus.BLOCKED
            state = {
                GateStatus.APPROVED: InformationState.ORIGINAL_PRESERVED,
                GateStatus.CONDITIONAL: InformationState.PENDING,
                GateStatus.RETURNED: InformationState.RETURNED_FOR_CORRECTION,
                GateStatus.BLOCKED: InformationState.BLOCKED,
                GateStatus.NOT_EVALUATED: InformationState.PENDING,
            }[gate_status]
            requires_review = gate_status is not GateStatus.APPROVED
            events.append(
                PrecisionEvent(
                    event_id=f"{trace_id}:tcria:{partition}:{index}:gate:{gate_name}",
                    source_layer=SourceLayer.TCRIA,
                    information_id=f"{information_id}:gate:{gate_name}",
                    information_state=state,
                    custody_state=CustodyState.REFERENCED,
                    summary=f"TCRIA gate {gate_name} returned {source_status}.",
                    support_refs=(document_ref,),
                    sha256=document_sha256,
                    requires_human_review=requires_review,
                    details={
                        "gate_name": gate_name,
                        "document_ref": document_ref,
                        "source_status": source_status,
                        "source_reason": source_reason,
                        "source_evidence": source_evidence,
                        "unknown_source_status": unknown_status,
                        "prior_block_preserved": blocked_before,
                    },
                    trace_id=trace_id,
                    observed_at=observed_at,
                    caused_by=(f"{trace_id}:tcria:{partition}:{index}:record",),
                    source_reference=source_reference,
                    gate_status=gate_status,
                    human_review_state=(
                        HumanReviewState.REQUIRED
                        if requires_review
                        else HumanReviewState.NOT_REQUIRED
                    ),
                )
            )
        return events

    def _validate_classification_counts(
        self,
        bundle: Mapping[str, Any],
        observed: Counter[str],
    ) -> None:
        if "classification_counts" not in bundle:
            return
        published = optional_mapping(bundle, "classification_counts")
        normalized: dict[str, int] = {}
        for classification, count in published.items():
            if not isinstance(classification, str):
                raise TCRIAAdapterError("classification_counts keys must be strings.")
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise TCRIAAdapterError(
                    "classification_counts values must be non-negative integers."
                )
            normalized[classification] = count
        if normalized != dict(observed):
            raise TCRIAAdapterError(
                "classification_counts does not match the published record collections."
            )


def _document_reference(
    record: Mapping[str, Any],
    document: Mapping[str, Any],
    path: str,
) -> str:
    for key in ("relative_path",):
        value = document.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    value = record.get("file_name")
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise TCRIAAdapterError(f"{path} requires a relative document reference.")


def _extraction_status(
    record: Mapping[str, Any],
    document: Mapping[str, Any],
    path: str,
) -> str:
    record_value = record.get("extraction_status")
    document_value = document.get("extraction_status")
    if (
        record_value is not None
        and document_value is not None
        and _normalize_extraction_status(record_value, path)
        != _normalize_extraction_status(document_value, f"{path}.document")
    ):
        raise TCRIAAdapterError(f"{path} contains conflicting extraction_status values.")
    value = record_value if record_value is not None else document_value
    return _normalize_extraction_status(value, path)


def _normalize_extraction_status(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TCRIAAdapterError(f"{path}.extraction_status is required.")
    normalized = value.strip().lower()
    allowed = {
        "ok",
        "error",
        "skipped",
        "unsupported",
        "extraction_failed",
        "ocr_failed",
        "unreadable",
    }
    if normalized not in allowed:
        raise TCRIAAdapterError(f"{path} has unknown extraction_status {value!r}.")
    return normalized


def _optional_record_text(
    record: Mapping[str, Any],
    document: Mapping[str, Any],
    key: str,
) -> str | None:
    value = record.get(key, document.get(key))
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TCRIAAdapterError(f"{key} must be non-empty text when provided.")
    return value.strip()


def _classification_reasons(record: Mapping[str, Any], path: str) -> tuple[str, ...]:
    value = record.get("classification_reasons", [])
    if not isinstance(value, list):
        raise TCRIAAdapterError(f"{path}.classification_reasons must be a list.")
    reasons: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise TCRIAAdapterError(
                f"{path}.classification_reasons[{index}] must be non-empty text."
            )
        reasons.append(item.strip())
    return tuple(reasons)


def _record_state(
    classification: str,
    raises_accusation: bool,
    extraction_status: str,
) -> InformationState:
    if extraction_status in {"error", "extraction_failed"}:
        return InformationState.EXTRACTION_FAILED
    if extraction_status == "ocr_failed":
        return InformationState.OCR_FAILED
    if extraction_status in {"unsupported", "unreadable"}:
        return InformationState.UNREADABLE
    if extraction_status == "skipped":
        return InformationState.PENDING
    if raises_accusation:
        return InformationState.ALLEGATION

    normalized = classification.strip().lower()
    explicit = {
        "fact_supported": InformationState.FACT_SUPPORTED,
        "supported_fact": InformationState.FACT_SUPPORTED,
        "allegation": InformationState.ALLEGATION,
        "hypothesis": InformationState.HYPOTHESIS,
        "signal_pending": InformationState.SIGNAL_PENDING,
        "tcria_signal": InformationState.SIGNAL_PENDING,
        "null": InformationState.NULL_RESULT,
        "null_result": InformationState.NULL_RESULT,
        "original_preserved": InformationState.ORIGINAL_PRESERVED,
        "derived_copy": InformationState.DERIVED_COPY,
    }
    return explicit.get(normalized, InformationState.PENDING)


def _trace_observation(record: Mapping[str, Any]) -> dict[str, Any]:
    interpretation = record.get("interpretation")
    if interpretation is None:
        return {}
    if not isinstance(interpretation, Mapping):
        raise TCRIAAdapterError("interpretation must be a mapping or null.")
    allowed = {
        "route_selection",
        "document_role",
        "observed",
        "mentioned",
        "omission_reason",
        "mission_scope",
    }
    return {key: interpretation[key] for key in allowed if key in interpretation}


def _signal_count(value: Any) -> int:
    if value is None or value is False or value == "":
        return 0
    if isinstance(value, (list, tuple, set, Mapping)):
        return len(value)
    return 1


def _gate_status(source_status: str) -> tuple[GateStatus, bool]:
    mapping = {
        "PASS": GateStatus.APPROVED,
        "WARN": GateStatus.CONDITIONAL,
        "BLOCKED": GateStatus.BLOCKED,
        "NOT_EVALUATED": GateStatus.CONDITIONAL,
        "NOT_APPLICABLE": GateStatus.CONDITIONAL,
    }
    status = mapping.get(source_status)
    if status is None:
        return GateStatus.BLOCKED, True
    return status, False


def adapt_tcria_bundle(payload: Mapping[str, Any]) -> tuple[PrecisionEvent, ...]:
    """Adapt the base branch's lightweight TCRIA bundle without copying evidence."""

    if not isinstance(payload, Mapping):
        raise TCRIAAdapterError("TCRIA payload must be a mapping.")
    events: list[PrecisionEvent] = []
    for collection_name in ("accusation_set", "non_accusation_set"):
        records = payload.get(collection_name, [])
        if not isinstance(records, list):
            raise TCRIAAdapterError(f"{collection_name} must be a list.")
        for index, item in enumerate(records):
            if not isinstance(item, Mapping):
                raise TCRIAAdapterError(
                    f"{collection_name}[{index}] must be a mapping."
                )
            events.append(
                _compat_record_to_event(
                    dict(item),
                    collection_name=collection_name,
                    index=index,
                )
            )
    if not events:
        raise TCRIAAdapterError(
            "TCRIA bundle must contain at least one accusation_set or "
            "non_accusation_set record."
        )
    return tuple(events)


def _compat_record_to_event(
    record: dict[str, Any],
    *,
    collection_name: str,
    index: int,
) -> PrecisionEvent:
    extraction_status = str(record.get("extraction_status", "")).strip().lower()
    state = _compat_information_state(record, extraction_status)
    digest = _compat_optional_text(record.get("sha256"))
    if digest is not None:
        digest = validate_sha256(digest)
    file_name = _compat_optional_text(record.get("file_name"))
    file_path = _compat_optional_text(record.get("file_path"))
    information_id = digest or file_name or file_path or f"tcria-record-{index + 1}"
    support_refs = _compat_string_tuple(record.get("evidence_refs", []), "evidence_refs")
    if not support_refs and file_name:
        support_refs = (file_name,)
    custody_state = _compat_custody_state(
        record,
        digest=digest,
        file_reference=file_name or file_path,
    )
    summary = (
        _compat_optional_text(record.get("summary"))
        or _compat_optional_text(record.get("message"))
        or _compat_optional_text(record.get("artifact_type_reason"))
        or f"TCRIA record {information_id} classified as "
        f"{record.get('classification', 'unclassified')}."
    )
    promotable = state is InformationState.FACT_SUPPORTED
    requires_review = state in {
        InformationState.EXTRACTION_FAILED,
        InformationState.OCR_FAILED,
        InformationState.UNREADABLE,
        InformationState.PENDING,
        InformationState.HUMAN_REVIEW_REQUIRED,
        InformationState.RETURNED_FOR_CORRECTION,
        InformationState.BLOCKED,
        InformationState.ALLEGATION,
        InformationState.SIGNAL_PENDING,
        InformationState.TCRIA_SIGNAL,
    }
    event = PrecisionEvent(
        event_id=f"tcria:{collection_name}:{index}:{information_id}",
        source_layer=SourceLayer.TCRIA,
        information_id=information_id,
        information_state=state,
        custody_state=custody_state,
        summary=summary,
        support_refs=support_refs,
        sha256=digest,
        requires_human_review=requires_review,
        promotable_as_fact=promotable,
        details={
            "collection": collection_name,
            "classification": record.get("classification"),
            "artifact_type": record.get("artifact_type"),
            "raises_accusation": bool(record.get("raises_accusation", False)),
            "overall_outcome": record.get("overall_outcome"),
            "gates": deepcopy(record.get("gates")),
            "key_signals": deepcopy(record.get("key_signals", {})),
            "compatibility_profile": True,
        },
    )
    try:
        event.assert_safe_promotion()
    except ValueError as exc:
        raise TCRIAAdapterError(str(exc)) from exc
    return event


def _compat_information_state(
    record: Mapping[str, Any],
    extraction_status: str,
) -> InformationState:
    declared = _compat_optional_text(record.get("information_state"))
    if declared:
        try:
            return InformationState(declared.lower())
        except ValueError as exc:
            raise TCRIAAdapterError(
                f"Unknown information_state: {declared!r}."
            ) from exc
    if extraction_status in {"ocr_failed", "ocr-error", "ocr_error"}:
        return InformationState.OCR_FAILED
    if extraction_status in {"extraction_failed", "failed", "error"}:
        return InformationState.EXTRACTION_FAILED
    if extraction_status in {"unreadable", "empty", "none"}:
        return InformationState.UNREADABLE
    classification = str(record.get("classification", "")).strip().lower()
    mapping = {
        "fact_supported": InformationState.FACT_SUPPORTED,
        "pending": InformationState.PENDING,
        "open": InformationState.PENDING,
        "conditional": InformationState.PENDING,
        "blocked": InformationState.BLOCKED,
        "rejected": InformationState.BLOCKED,
        "returned": InformationState.RETURNED_FOR_CORRECTION,
        "returned_for_correction": InformationState.RETURNED_FOR_CORRECTION,
        "null": InformationState.NULL_RESULT,
        "none": InformationState.NULL_RESULT,
        "no_conclusion": InformationState.NULL_RESULT,
    }
    if classification in mapping:
        return mapping[classification]
    if bool(record.get("raises_accusation", False)):
        return InformationState.ALLEGATION
    return InformationState.TCRIA_SIGNAL


def _compat_custody_state(
    record: Mapping[str, Any],
    *,
    digest: str | None,
    file_reference: str | None,
) -> CustodyState:
    declared = _compat_optional_text(record.get("custody_state"))
    if declared:
        try:
            return CustodyState(declared.lower())
        except ValueError as exc:
            raise TCRIAAdapterError(
                f"Unknown custody_state: {declared!r}."
            ) from exc
    if digest:
        return CustodyState.HASHED
    if file_reference:
        return CustodyState.REFERENCED
    return CustodyState.UNKNOWN


def _compat_string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise TCRIAAdapterError(f"{field_name} must be a list or tuple of strings.")
    result: list[str] = []
    for index, item in enumerate(value):
        text = _compat_optional_text(item)
        if text is None:
            raise TCRIAAdapterError(
                f"{field_name}[{index}] must be a non-empty string."
            )
        result.append(text)
    return tuple(result)


def _compat_optional_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _aggregate_gate_status(events: list[PrecisionEvent]) -> GateStatus:
    if not events:
        return GateStatus.NOT_EVALUATED
    statuses = {event.gate_status for event in events}
    for status in (
        GateStatus.BLOCKED,
        GateStatus.RETURNED,
        GateStatus.CONDITIONAL,
        GateStatus.NOT_EVALUATED,
    ):
        if status in statuses:
            return status
    return GateStatus.APPROVED


def _overall_outcome_status(
    value: str | None,
) -> tuple[GateStatus | None, bool]:
    if value is None:
        return None, False
    token = value.strip().split(maxsplit=1)[0].split("(", maxsplit=1)[0].rstrip(":").upper()
    mapping = {
        "PASS": GateStatus.APPROVED,
        "APPROVED": GateStatus.APPROVED,
        "WARN": GateStatus.CONDITIONAL,
        "CONDITIONAL": GateStatus.CONDITIONAL,
        "NOT_EVALUATED": GateStatus.NOT_EVALUATED,
        "RETURNED": GateStatus.RETURNED,
        "RETURNED_FOR_CORRECTION": GateStatus.RETURNED,
        "BLOCKED": GateStatus.BLOCKED,
    }
    status = mapping.get(token)
    if status is None:
        return GateStatus.BLOCKED, True
    return status, False


def _stricter_gate_status(
    first: GateStatus,
    second: GateStatus | None,
) -> GateStatus:
    if second is None:
        return first
    severity = {
        GateStatus.APPROVED: 0,
        GateStatus.NOT_EVALUATED: 1,
        GateStatus.CONDITIONAL: 1,
        GateStatus.RETURNED: 2,
        GateStatus.BLOCKED: 3,
    }
    return first if severity[first] >= severity[second] else second
