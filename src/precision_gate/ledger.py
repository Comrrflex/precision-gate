from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Any

from precision_gate.contracts import (
    ContractError,
    HumanReviewState,
    InformationState,
    PrecisionEvent,
    SourceLayer,
    canonical_json,
    is_read_failure,
    to_jsonable,
    utc_now,
    validate_sha256,
)


class LedgerError(ContractError):
    """Raised when an event would make the custody trail invalid."""


@dataclass(frozen=True)
class TrailReceipt:
    sequence: int
    event: PrecisionEvent
    previous_receipt_sha256: str
    receipt_sha256: str

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise LedgerError("Receipt sequence must be positive.")
        if self.event.sequence != self.sequence:
            raise LedgerError("Receipt and event sequences must match.")
        object.__setattr__(
            self,
            "previous_receipt_sha256",
            validate_sha256(
                self.previous_receipt_sha256,
                field_name="previous_receipt_sha256",
            ),
        )
        object.__setattr__(
            self,
            "receipt_sha256",
            validate_sha256(self.receipt_sha256, field_name="receipt_sha256"),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class ChainVerification:
    valid: bool
    checkpoint_count: int
    final_chain_sha256: str
    errors: tuple[str, ...]


class CustodyTrail:
    """Append-only, hash-linked custody trail for one Precision Gate execution."""

    def __init__(
        self,
        trace_id: str,
        *,
        created_at: str | None = None,
        schema_version: str = "1.0",
    ) -> None:
        if not isinstance(trace_id, str) or not trace_id.strip():
            raise LedgerError("trace_id must be a non-empty string.")
        if not isinstance(schema_version, str) or not schema_version.strip():
            raise LedgerError("schema_version must be a non-empty string.")
        self.trace_id = trace_id.strip()
        self.created_at = (created_at or utc_now()).strip()
        self.schema_version = schema_version.strip()
        if not self.created_at:
            raise LedgerError("created_at must be a non-empty string.")

        self._genesis_sha256 = _sha256(
            {
                "schema_version": self.schema_version,
                "trace_id": self.trace_id,
                "created_at": self.created_at,
            }
        )
        self._receipts: list[TrailReceipt] = []
        self._event_ids: set[str] = set()
        self._active_blocks: dict[str, str] = {}
        self._active_reviews: dict[str, str] = {}
        self._active_read_failures: dict[str, str] = {}

    @property
    def genesis_sha256(self) -> str:
        return self._genesis_sha256

    @property
    def final_chain_sha256(self) -> str:
        if not self._receipts:
            return self.genesis_sha256
        return self._receipts[-1].receipt_sha256

    @property
    def receipts(self) -> tuple[TrailReceipt, ...]:
        return tuple(self._receipts)

    @property
    def events(self) -> tuple[PrecisionEvent, ...]:
        return tuple(receipt.event for receipt in self._receipts)

    @property
    def active_blocks(self) -> tuple[str, ...]:
        return tuple(self._active_blocks)

    @property
    def active_reviews(self) -> tuple[str, ...]:
        return tuple(self._active_reviews)

    @property
    def active_read_failures(self) -> tuple[str, ...]:
        return tuple(self._active_read_failures)

    @property
    def active_condition_ids(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                (
                    *self._active_blocks,
                    *self._active_reviews,
                    *self._active_read_failures,
                )
            )
        )

    def append(self, event: PrecisionEvent) -> TrailReceipt:
        if not isinstance(event, PrecisionEvent):
            raise LedgerError("CustodyTrail accepts only PrecisionEvent values.")
        if event.event_id in self._event_ids:
            raise LedgerError(f"Duplicate event_id: {event.event_id}.")

        sequence = len(self._receipts) + 1
        if event.trace_id not in {None, self.trace_id}:
            raise LedgerError(
                f"Event trace_id {event.trace_id!r} does not match trail {self.trace_id!r}."
            )
        if event.sequence not in {None, sequence}:
            raise LedgerError(
                f"Event sequence {event.sequence!r} does not match expected {sequence}."
            )
        normalized = replace(event, trace_id=self.trace_id, sequence=sequence)

        self._validate_required_review(normalized)
        self._validate_resolutions(normalized)
        dependencies = set(_detail_refs(normalized.details, "depends_on_information_ids"))
        related_information = {normalized.information_id, *dependencies}
        related_blocks = _conditions_for_information(self._active_blocks, related_information)
        related_failures = _conditions_for_information(
            self._active_read_failures,
            related_information,
        )
        normalized.assert_safe_promotion(
            active_blocks=related_blocks,
            failed_dependencies=related_failures,
        )
        if normalized.information_state is InformationState.RELEASED:
            normalized.assert_safe_release(
                active_blocks=self._active_blocks,
                active_reviews=self._active_reviews,
            )

        previous_receipt = self.final_chain_sha256
        receipt_sha256 = _sha256(
            {
                "sequence": sequence,
                "event": normalized,
                "previous_receipt_sha256": previous_receipt,
            }
        )
        receipt = TrailReceipt(
            sequence=sequence,
            event=normalized,
            previous_receipt_sha256=previous_receipt,
            receipt_sha256=receipt_sha256,
        )

        self._receipts.append(receipt)
        self._event_ids.add(normalized.event_id)
        self._apply_condition_changes(normalized)
        return receipt

    def event_by_id(self, event_id: str) -> PrecisionEvent:
        for receipt in self._receipts:
            if receipt.event.event_id == event_id:
                return receipt.event
        raise KeyError(event_id)

    def verify(self) -> ChainVerification:
        return self.verify_payload(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "trace_id": self.trace_id,
            "created_at": self.created_at,
            "genesis_sha256": self.genesis_sha256,
            "checkpoint_count": len(self._receipts),
            "final_chain_sha256": self.final_chain_sha256,
            "receipts": [receipt.to_dict() for receipt in self._receipts],
        }

    @staticmethod
    def verify_payload(payload: Mapping[str, Any]) -> ChainVerification:
        errors: list[str] = []
        if not isinstance(payload, Mapping):
            return ChainVerification(
                valid=False,
                checkpoint_count=0,
                final_chain_sha256="",
                errors=("Trail payload must be a mapping.",),
            )

        schema_version = payload.get("schema_version")
        trace_id = payload.get("trace_id")
        created_at = payload.get("created_at")
        if not all(
            isinstance(value, str) and value for value in (schema_version, trace_id, created_at)
        ):
            errors.append("Trail identity fields are missing or invalid.")
            expected_genesis = ""
        else:
            expected_genesis = _sha256(
                {
                    "schema_version": schema_version,
                    "trace_id": trace_id,
                    "created_at": created_at,
                }
            )
        published_genesis = payload.get("genesis_sha256")
        if published_genesis != expected_genesis:
            errors.append("Genesis SHA-256 mismatch.")

        raw_receipts = payload.get("receipts")
        if not isinstance(raw_receipts, list):
            errors.append("receipts must be a list.")
            raw_receipts = []

        previous = expected_genesis
        event_ids: set[str] = set()
        for index, raw_receipt in enumerate(raw_receipts, start=1):
            if not isinstance(raw_receipt, Mapping):
                errors.append(f"Receipt {index} must be a mapping.")
                continue
            sequence = raw_receipt.get("sequence")
            event = raw_receipt.get("event")
            published_previous = raw_receipt.get("previous_receipt_sha256")
            published_receipt = raw_receipt.get("receipt_sha256")

            if sequence != index:
                errors.append(f"Receipt {index} has invalid sequence {sequence!r}.")
            if published_previous != previous:
                errors.append(f"Receipt {index} previous SHA-256 mismatch.")
            if not isinstance(event, Mapping):
                errors.append(f"Receipt {index} event must be a mapping.")
                continue
            if event.get("sequence") != index:
                errors.append(f"Receipt {index} event sequence mismatch.")
            if event.get("trace_id") != trace_id:
                errors.append(f"Receipt {index} event trace_id mismatch.")
            event_id = event.get("event_id")
            if not isinstance(event_id, str) or not event_id:
                errors.append(f"Receipt {index} event_id is missing.")
            elif event_id in event_ids:
                errors.append(f"Receipt {index} repeats event_id {event_id!r}.")
            else:
                event_ids.add(event_id)

            try:
                expected_receipt = _sha256(
                    {
                        "sequence": sequence,
                        "event": event,
                        "previous_receipt_sha256": published_previous,
                    }
                )
            except ContractError:
                errors.append(f"Receipt {index} contains non-canonical data.")
                expected_receipt = ""
            if published_receipt != expected_receipt:
                errors.append(f"Receipt {index} SHA-256 mismatch.")
            previous = expected_receipt

        published_count = payload.get("checkpoint_count")
        if published_count != len(raw_receipts):
            errors.append("checkpoint_count does not match receipts.")
        expected_final = previous if raw_receipts else expected_genesis
        if payload.get("final_chain_sha256") != expected_final:
            errors.append("Final chain SHA-256 mismatch.")

        return ChainVerification(
            valid=not errors,
            checkpoint_count=len(raw_receipts),
            final_chain_sha256=expected_final,
            errors=tuple(errors),
        )

    def _validate_required_review(self, event: PrecisionEvent) -> None:
        review_states = {
            InformationState.EXTRACTION_FAILED,
            InformationState.OCR_FAILED,
            InformationState.UNREADABLE,
            InformationState.HUMAN_REVIEW_REQUIRED,
            InformationState.RETURNED_FOR_CORRECTION,
            InformationState.BLOCKED,
        }
        if event.information_state in review_states and not event.requires_human_review:
            is_completed_human_block = (
                event.source_layer is SourceLayer.HUMAN_REVIEW
                and event.information_state is InformationState.BLOCKED
                and event.human_review_state is HumanReviewState.COMPLETED
            )
            if not is_completed_human_block:
                raise LedgerError(
                    f"{event.information_state.value} events must require human review."
                )
        if event.information_state is InformationState.RELEASED and event.requires_human_review:
            raise LedgerError("A released event cannot carry an unresolved review requirement.")

    def _validate_resolutions(self, event: PrecisionEvent) -> None:
        active = {
            *self._active_blocks,
            *self._active_reviews,
            *self._active_read_failures,
        }
        for condition_id in event.resolves:
            if condition_id not in active:
                raise LedgerError(f"Resolution references inactive condition: {condition_id}.")
            if condition_id in self._active_read_failures and not event.support_refs:
                raise LedgerError(
                    "Resolving an unreadable or failed extraction requires explicit support_refs."
                )

    def _apply_condition_changes(self, event: PrecisionEvent) -> None:
        for condition_id in event.resolves:
            self._active_blocks.pop(condition_id, None)
            self._active_reviews.pop(condition_id, None)
            self._active_read_failures.pop(condition_id, None)

        if event.information_state is InformationState.BLOCKED:
            self._active_blocks[event.event_id] = event.information_id
        if is_read_failure(event.information_state):
            self._active_read_failures[event.event_id] = event.information_id
        if (
            event.requires_human_review
            and event.human_review_state is not HumanReviewState.COMPLETED
        ):
            self._active_reviews[event.event_id] = event.information_id


def _conditions_for_information(
    conditions: Mapping[str, str],
    information_ids: set[str],
) -> tuple[str, ...]:
    return tuple(
        condition_id
        for condition_id, information_id in conditions.items()
        if information_id in information_ids
    )


def _detail_refs(details: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = details.get(key, ())
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise LedgerError(f"details.{key} must be a sequence of strings.")
    refs: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise LedgerError(f"details.{key}[{index}] must be a non-empty string.")
        refs.append(item.strip())
    return tuple(refs)


def _sha256(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()
