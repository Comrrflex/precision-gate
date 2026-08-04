from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from types import MappingProxyType
from typing import Any

SCHEMA_VERSION = "1.0"
TCRIA_AUDIT_BUNDLE_PROFILE = "tcria.audit_bundle.v1"
API_OUTPUT_PROFILE = "precision.api_output.v1"
QUINTA_EXECUTION_CONTEXT_VERSION = "1.0"

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ContractError(ValueError):
    """Raised when an integration payload violates a documented contract."""


class PromotionError(ValueError):
    """Raised when information is promoted or released beyond its support."""


class SourceLayer(str, Enum):
    TCRIA = "tcria"
    API = "api"
    QUINTA_ORDEM = "quinta_ordem"
    PRECISION_GATE = "precision_gate"
    PRECISION_GATE_DESIGN = "precision_gate_design"
    HUMAN_REVIEW = "human_review"
    OCR = "ocr"


class InformationState(str, Enum):
    ORIGINAL_PRESERVED = "original_preserved"
    DERIVED_COPY = "derived_copy"
    EXTRACTION_FAILED = "extraction_failed"
    OCR_FAILED = "ocr_failed"
    UNREADABLE = "unreadable"
    NULL_RESULT = "null_result"
    API_OPINION = "api_opinion"
    API_INFERENCE = "api_inference"
    TCRIA_SIGNAL = "tcria_signal"
    SIGNAL_PENDING = "signal_pending"
    ALLEGATION = "allegation"
    HYPOTHESIS = "hypothesis"
    FACT_SUPPORTED = "fact_supported"
    PENDING = "pending"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    RETURNED_FOR_CORRECTION = "returned_for_correction"
    BLOCKED = "blocked"
    RELEASED = "released"


class CustodyState(str, Enum):
    PRESERVED = "preserved"
    DERIVED = "derived"
    REFERENCED = "referenced"
    HASHED = "hashed"
    MANIFESTED = "manifested"
    BROKEN = "broken"
    UNKNOWN = "unknown"


class GateStatus(str, Enum):
    APPROVED = "approved"
    CONDITIONAL = "conditional"
    RETURNED = "returned_for_correction"
    BLOCKED = "blocked"
    NOT_EVALUATED = "not_evaluated"


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


class HumanReviewState(str, Enum):
    NOT_REQUIRED = "not_required"
    REQUIRED = "required"
    PENDING = "pending"
    COMPLETED = "completed"


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def validate_sha256(value: str, *, field_name: str = "sha256") -> str:
    normalized = value.strip().lower()
    if not _SHA256_PATTERN.fullmatch(normalized):
        raise ContractError(f"{field_name} must be a 64-character hexadecimal SHA-256.")
    return normalized


@dataclass(frozen=True)
class SourceReference:
    """Reference to an immutable source artifact outside Precision Gate."""

    source_id: str
    source_ref: str
    artifact_sha256: str
    payload_sha256: str | None = None
    contract_profile: str | None = None
    schema_version: str | None = None
    producer_revision: str | None = None

    def __post_init__(self) -> None:
        for name in ("source_id", "source_ref"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"{name} must be a non-empty string.")
            object.__setattr__(self, name, value.strip())
        object.__setattr__(
            self,
            "artifact_sha256",
            validate_sha256(self.artifact_sha256, field_name="artifact_sha256"),
        )
        if self.payload_sha256 is not None:
            object.__setattr__(
                self,
                "payload_sha256",
                validate_sha256(self.payload_sha256, field_name="payload_sha256"),
            )


@dataclass(frozen=True)
class CoherenceAlert:
    alert_id: str
    code: str
    severity: AlertSeverity
    message: str
    event_ids: tuple[str, ...] = ()
    information_ids: tuple[str, ...] = ()
    requires_human_review: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("alert_id", "code", "message"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"{name} must be a non-empty string.")
            object.__setattr__(self, name, value.strip())
        object.__setattr__(self, "severity", _coerce_enum(AlertSeverity, self.severity, "severity"))
        object.__setattr__(self, "event_ids", _string_tuple(self.event_ids, "event_ids"))
        object.__setattr__(
            self,
            "information_ids",
            _string_tuple(self.information_ids, "information_ids"),
        )
        object.__setattr__(self, "details", _freeze_mapping(self.details, "details"))

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class PrecisionEvent:
    """One immutable observation in the mobile custody trail.

    The original constructor fields remain stable for compatibility. New trace fields
    make the event suitable for canonical serialization and append-only custody.
    """

    event_id: str
    source_layer: SourceLayer | str
    information_id: str
    information_state: InformationState
    custody_state: CustodyState
    summary: str
    support_refs: tuple[str, ...] = ()
    sha256: str | None = None
    requires_human_review: bool = False
    promotable_as_fact: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION
    trace_id: str | None = None
    sequence: int | None = None
    observed_at: str = field(default_factory=utc_now)
    caused_by: tuple[str, ...] = ()
    resolves: tuple[str, ...] = ()
    source_reference: SourceReference | None = None
    gate_status: GateStatus | None = None
    human_review_state: HumanReviewState = HumanReviewState.NOT_REQUIRED

    def __post_init__(self) -> None:
        for name in ("event_id", "information_id", "summary", "schema_version", "observed_at"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"{name} must be a non-empty string.")
            object.__setattr__(self, name, value.strip())

        source_layer: SourceLayer | str = self.source_layer
        if isinstance(source_layer, str):
            source_layer = source_layer.strip()
            if not source_layer:
                raise ContractError("source_layer must be a non-empty string.")
            try:
                source_layer = SourceLayer(source_layer)
            except ValueError:
                pass
        else:
            source_layer = _coerce_enum(SourceLayer, source_layer, "source_layer")
        object.__setattr__(self, "source_layer", source_layer)

        object.__setattr__(
            self,
            "information_state",
            _coerce_enum(InformationState, self.information_state, "information_state"),
        )
        object.__setattr__(
            self,
            "custody_state",
            _coerce_enum(CustodyState, self.custody_state, "custody_state"),
        )
        if self.gate_status is not None:
            object.__setattr__(
                self,
                "gate_status",
                _coerce_enum(GateStatus, self.gate_status, "gate_status"),
            )
        object.__setattr__(
            self,
            "human_review_state",
            _coerce_enum(HumanReviewState, self.human_review_state, "human_review_state"),
        )

        if self.trace_id is not None:
            if not isinstance(self.trace_id, str) or not self.trace_id.strip():
                raise ContractError("trace_id must be a non-empty string when provided.")
            object.__setattr__(self, "trace_id", self.trace_id.strip())
        if self.sequence is not None and (not isinstance(self.sequence, int) or self.sequence < 1):
            raise ContractError("sequence must be a positive integer when provided.")
        if self.sha256 is not None:
            object.__setattr__(self, "sha256", validate_sha256(self.sha256))

        object.__setattr__(self, "support_refs", _string_tuple(self.support_refs, "support_refs"))
        object.__setattr__(self, "caused_by", _string_tuple(self.caused_by, "caused_by"))
        object.__setattr__(self, "resolves", _string_tuple(self.resolves, "resolves"))
        object.__setattr__(self, "details", _freeze_mapping(self.details, "details"))

        if self.requires_human_review and self.human_review_state is HumanReviewState.NOT_REQUIRED:
            object.__setattr__(self, "human_review_state", HumanReviewState.REQUIRED)

    def assert_safe_promotion(
        self,
        *,
        active_blocks: Iterable[str] = (),
        failed_dependencies: Iterable[str] = (),
        gate_status: GateStatus | str | None = None,
    ) -> None:
        """Raise when an event is marked promotable beyond its explicit support."""

        if not self.promotable_as_fact:
            return
        if self.information_state is not InformationState.FACT_SUPPORTED:
            raise PromotionError("Only fact_supported events may be promotable as fact.")
        if self.custody_state not in {
            CustodyState.PRESERVED,
            CustodyState.REFERENCED,
            CustodyState.HASHED,
            CustodyState.MANIFESTED,
        }:
            raise PromotionError("Promotable fact requires preserved or traceable custody.")
        if not self.support_refs:
            raise PromotionError("Promotable fact requires explicit support_refs.")

        unresolved_blocks = tuple(active_blocks)
        if unresolved_blocks:
            raise PromotionError(
                "Promotable fact has unresolved blocks: " + ", ".join(unresolved_blocks)
            )
        failures = tuple(failed_dependencies)
        if failures:
            raise PromotionError(
                "Promotable fact depends on unreadable or failed extraction: " + ", ".join(failures)
            )

        effective_gate_status = gate_status or self.gate_status
        if effective_gate_status is not None:
            normalized = _coerce_enum(GateStatus, effective_gate_status, "gate_status")
            if normalized is not GateStatus.APPROVED:
                raise PromotionError("Promotable fact requires an approved gate decision.")

    def assert_safe_release(
        self,
        *,
        active_blocks: Iterable[str] = (),
        active_reviews: Iterable[str] = (),
    ) -> None:
        if self.information_state is not InformationState.RELEASED:
            raise PromotionError("Release guard requires a released event.")
        if self.gate_status is not GateStatus.APPROVED:
            raise PromotionError("Released output requires an approved gate decision.")
        blocks = tuple(active_blocks)
        if blocks:
            raise PromotionError("Released output has unresolved blocks: " + ", ".join(blocks))
        reviews = tuple(active_reviews)
        if reviews:
            raise PromotionError(
                "Released output has unresolved human review requirements: " + ", ".join(reviews)
            )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


def is_read_failure(state: InformationState | str) -> bool:
    normalized = _coerce_enum(InformationState, state, "information_state")
    return normalized in {
        InformationState.EXTRACTION_FAILED,
        InformationState.OCR_FAILED,
        InformationState.UNREADABLE,
    }


def has_traceable_custody(state: CustodyState | str) -> bool:
    normalized = _coerce_enum(CustodyState, state, "custody_state")
    return normalized in {
        CustodyState.PRESERVED,
        CustodyState.REFERENCED,
        CustodyState.HASHED,
        CustodyState.MANIFESTED,
    }


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            to_jsonable(value),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ContractError("Value is not canonically JSON serializable.") from exc


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: to_jsonable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContractError("Canonical mapping keys must be strings.")
            result[key] = to_jsonable(item)
        return result
    if isinstance(value, (tuple, list)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        converted = [to_jsonable(item) for item in value]
        return sorted(converted, key=lambda item: canonical_json(item))
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ContractError("Naive datetime values are not allowed.")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError("NaN and infinity are not allowed.")
        return value
    raise ContractError(f"Unsupported canonical value type: {type(value).__name__}.")


def _coerce_enum(enum_type: type[Enum], value: Any, field_name: str) -> Any:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"Unknown {field_name}: {value!r}.") from exc


def _string_tuple(values: Iterable[str], field_name: str) -> tuple[str, ...]:
    normalized: list[str] = []
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value.strip():
            raise ContractError(f"{field_name}[{index}] must be a non-empty string.")
        normalized.append(value.strip())
    if len(set(normalized)) != len(normalized):
        raise ContractError(f"{field_name} must not contain duplicate values.")
    return tuple(normalized)


def _freeze_mapping(value: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{field_name} must be a mapping.")
    frozen: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ContractError(f"{field_name} keys must be strings.")
        frozen[key] = _freeze_value(item)
    return MappingProxyType(frozen)


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _freeze_mapping(value, "nested mapping")
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_freeze_value(item) for item in value), key=repr))
    return value
