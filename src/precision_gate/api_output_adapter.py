from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import Any

from precision_gate._validation import (
    optional_mapping,
    optional_text,
    require_string_list,
    require_text,
    strict_snapshot,
)
from precision_gate.contracts import (
    API_OUTPUT_PROFILE,
    ContractError,
    CustodyState,
    HumanReviewState,
    InformationState,
    PrecisionEvent,
    SourceLayer,
    SourceReference,
    canonical_json,
    validate_sha256,
)


class APIOutputAdapterError(ContractError):
    """Raised when an external API output envelope is incomplete or unsafe."""


_ALLOWED_FIELDS = {
    "contract_profile",
    "output_id",
    "input_refs",
    "provider",
    "model",
    "prompt_ref",
    "prompt_sha256",
    "response_id",
    "output_ref",
    "output_sha256",
    "output_type",
    "claim_relations",
    "response_metadata",
    "producer_revision",
}
_FORBIDDEN_METADATA_KEYS = {
    "chain_of_thought",
    "reasoning",
    "reasoning_content",
    "hidden_reasoning",
}


class APIOutputAdapter:
    """Observe an externally produced, provider-neutral API output by reference."""

    def adapt(
        self,
        envelope: Mapping[str, Any],
        *,
        trace_id: str,
        observed_at: str,
    ) -> PrecisionEvent:
        snapshot = strict_snapshot(envelope, name="API output envelope")
        extra_fields = sorted(set(snapshot) - _ALLOWED_FIELDS)
        if extra_fields:
            raise APIOutputAdapterError(
                "Unknown API output envelope fields: " + ", ".join(extra_fields) + "."
            )
        profile = require_text(snapshot, "contract_profile")
        if profile != API_OUTPUT_PROFILE:
            raise APIOutputAdapterError(f"Unsupported API output profile: {profile!r}.")

        output_id = require_text(snapshot, "output_id")
        input_refs = require_string_list(snapshot, "input_refs")
        if not input_refs:
            raise APIOutputAdapterError("input_refs must contain at least one source reference.")
        provider = require_text(snapshot, "provider")
        model = require_text(snapshot, "model")
        prompt_ref = require_text(snapshot, "prompt_ref")
        prompt_sha256 = optional_text(snapshot, "prompt_sha256")
        if prompt_sha256 is not None:
            prompt_sha256 = validate_sha256(prompt_sha256, field_name="prompt_sha256")
        response_id = require_text(snapshot, "response_id")
        output_ref = require_text(snapshot, "output_ref")
        output_sha256 = validate_sha256(
            require_text(snapshot, "output_sha256"),
            field_name="output_sha256",
        )
        output_type = require_text(snapshot, "output_type").lower()
        state_by_type = {
            "null": InformationState.NULL_RESULT,
            "null_result": InformationState.NULL_RESULT,
            "opinion": InformationState.API_OPINION,
            "api_opinion": InformationState.API_OPINION,
            "inference": InformationState.API_INFERENCE,
            "api_inference": InformationState.API_INFERENCE,
            "hypothesis": InformationState.HYPOTHESIS,
        }
        if output_type not in state_by_type:
            raise APIOutputAdapterError(f"Unknown API output_type: {output_type!r}.")

        response_metadata = optional_mapping(snapshot, "response_metadata")
        _reject_hidden_reasoning(response_metadata, path="response_metadata")
        claim_relations = _claim_relations(snapshot)
        payload_sha256 = sha256(canonical_json(snapshot).encode("utf-8")).hexdigest()
        source_reference = SourceReference(
            source_id=output_id,
            source_ref=output_ref,
            artifact_sha256=output_sha256,
            payload_sha256=payload_sha256,
            contract_profile=profile,
            schema_version="1",
            producer_revision=optional_text(snapshot, "producer_revision"),
        )
        return PrecisionEvent(
            event_id=f"{trace_id}:api:{output_id}",
            source_layer=SourceLayer.API,
            information_id=output_id,
            information_state=state_by_type[output_type],
            custody_state=CustodyState.HASHED,
            summary=f"Observed external API output {output_id} as {output_type}.",
            support_refs=input_refs,
            sha256=output_sha256,
            requires_human_review=True,
            promotable_as_fact=False,
            details={
                "provider": provider,
                "model": model,
                "prompt_ref": prompt_ref,
                "prompt_sha256": prompt_sha256,
                "response_id": response_id,
                "response_metadata": response_metadata,
                "claim_relations": claim_relations,
                "internal_reasoning_observed": False,
            },
            trace_id=trace_id,
            observed_at=observed_at,
            source_reference=source_reference,
            human_review_state=HumanReviewState.REQUIRED,
        )


def _reject_hidden_reasoning(value: Mapping[str, Any], *, path: str) -> None:
    for key, item in value.items():
        if key.lower() in _FORBIDDEN_METADATA_KEYS:
            raise APIOutputAdapterError(
                f"{path}.{key} must not contain hidden or internal model reasoning."
            )
        if isinstance(item, Mapping):
            _reject_hidden_reasoning(item, path=f"{path}.{key}")
        elif isinstance(item, list):
            for index, nested in enumerate(item):
                if isinstance(nested, Mapping):
                    _reject_hidden_reasoning(nested, path=f"{path}.{key}[{index}]")


def _claim_relations(payload: Mapping[str, Any]) -> tuple[dict[str, str], ...]:
    value = payload.get("claim_relations", [])
    if not isinstance(value, list):
        raise APIOutputAdapterError("claim_relations must be a list.")
    relations: list[dict[str, str]] = []
    allowed_relations = {"supports", "contradicts", "mentions", "omits", "unseen"}
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise APIOutputAdapterError(f"claim_relations[{index}] must be a mapping.")
        extra = set(item) - {"information_id", "relation", "asserted_state"}
        if extra:
            raise APIOutputAdapterError(
                f"claim_relations[{index}] contains unknown fields: "
                + ", ".join(sorted(extra))
                + "."
            )
        information_id = item.get("information_id")
        relation = item.get("relation")
        if not isinstance(information_id, str) or not information_id.strip():
            raise APIOutputAdapterError(
                f"claim_relations[{index}].information_id must be non-empty text."
            )
        if not isinstance(relation, str) or relation.strip().lower() not in allowed_relations:
            raise APIOutputAdapterError(f"claim_relations[{index}].relation is not supported.")
        normalized = {
            "information_id": information_id.strip(),
            "relation": relation.strip().lower(),
        }
        asserted_state = item.get("asserted_state")
        if asserted_state is not None:
            if not isinstance(asserted_state, str):
                raise APIOutputAdapterError(
                    f"claim_relations[{index}].asserted_state must be text or null."
                )
            try:
                normalized["asserted_state"] = InformationState(asserted_state).value
            except ValueError as exc:
                raise APIOutputAdapterError(
                    f"claim_relations[{index}].asserted_state is unknown."
                ) from exc
        relations.append(normalized)
    return tuple(relations)
