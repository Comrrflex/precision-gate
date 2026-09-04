from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any
import json
import hmac
import os
import hashlib

from precision_gate.custody_state import CustodyState, InformationState, PrecisionEvent


class APIOutputAdapterError(ValueError):
    """Raised when an API output cannot be classified without unsafe promotion."""


def adapt_api_output(payload: Mapping[str, Any]) -> PrecisionEvent:
    """Convert one external AI/API output into a classified Precision event."""

    if not isinstance(payload, Mapping):
        raise APIOutputAdapterError("API output must be a mapping.")

    source = deepcopy(dict(payload))
    # Verify HMAC signature before trusting identifier-like fields from upstream
    _verify_hmac_signature(source)

    output_id = _identifier(source)
    summary = _summary(source)
    state = _state(source)
    support_refs = _support_refs(source.get("support_refs", source.get("evidence_refs", [])))
    sha256 = _optional_string(source.get("sha256"))
    custody = _custody(source, sha256=sha256, support_refs=support_refs)
    requested_promotion = bool(source.get("promotable_as_fact", False))

    if requested_promotion and state is not InformationState.FACT_SUPPORTED:
        raise APIOutputAdapterError(
            "API output may be promotable only when information_state is fact_supported."
        )

    event = PrecisionEvent(
        event_id=f"api:{output_id}",
        source_layer=_optional_string(source.get("source_layer")) or "api",
        information_id=output_id,
        information_state=state,
        custody_state=custody,
        summary=summary,
        support_refs=support_refs,
        sha256=sha256,
        requires_human_review=bool(source.get("requires_human_review", False)),
        promotable_as_fact=requested_promotion,
        details={"model": source.get("model"), "metadata": deepcopy(source.get("metadata", {}))},
    )
    try:
        event.assert_safe_promotion()
    except ValueError as exc:
        raise APIOutputAdapterError(str(exc)) from exc
    return event


def adapt_api_outputs(payloads: Sequence[Mapping[str, Any]]) -> tuple[PrecisionEvent, ...]:
    """Convert multiple API outputs while preserving their order."""

    if isinstance(payloads, (str, bytes)) or not isinstance(payloads, Sequence):
        raise APIOutputAdapterError("API outputs must be a sequence of mappings.")
    return tuple(adapt_api_output(payload) for payload in payloads)


def _verify_hmac_signature(payload: dict[str, Any]) -> None:
    """Verify an HMAC-SHA256 signature on the payload.

    Expects the upstream sender to include a hex HMAC in the field
    "signature_hmac" (or "hmac"). The HMAC is computed over the canonical
    JSON representation (sorted keys, compact separators) of the payload with
    the signature fields removed unless a `signed_body` field is explicitly
    provided.

    The shared secret must be available in the PRECISION_GATE_HMAC_SECRET
    environment variable.
    """

    sig = _optional_string(payload.get("signature_hmac") or payload.get("hmac"))
    if not sig:
        raise APIOutputAdapterError("Missing signature_hmac.")

    secret = os.environ.get("PRECISION_GATE_HMAC_SECRET")
    if not secret:
        raise APIOutputAdapterError("HMAC secret not configured (PRECISION_GATE_HMAC_SECRET).")

    signed = payload.get("signed_body")
    if signed is None:
        signed = dict(payload)
        # remove signature fields before canonicalizing
        signed.pop("signature_hmac", None)
        signed.pop("hmac", None)

    try:
        canonical = json.dumps(signed, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        raise APIOutputAdapterError("Unable to canonicalize payload for signature verification.")

    expected = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise APIOutputAdapterError("Invalid signature_hmac.")


def _identifier(payload: dict[str, Any]) -> str:
    for key in ("output_id", "id", "information_id"):
        value = _optional_string(payload.get(key))
        if value:
            return value
    raise APIOutputAdapterError("API output requires output_id, id, or information_id.")


def _summary(payload: dict[str, Any]) -> str:
    for key in ("summary", "content", "text", "message"):
        value = _optional_string(payload.get(key))
        if value:
            return value
    raise APIOutputAdapterError("API output requires summary, content, text, or message.")


def _state(payload: dict[str, Any]) -> InformationState:
    declared = _optional_string(payload.get("information_state"))
    if declared:
        try:
            state = InformationState(declared.lower())
        except ValueError as exc:
            raise APIOutputAdapterError(f"Unknown information_state: {declared!r}.") from exc
        if state not in {
            InformationState.API_OPINION,
            InformationState.API_INFERENCE,
            InformationState.FACT_SUPPORTED,
            InformationState.NULL_RESULT,
            InformationState.PENDING,
            InformationState.HUMAN_REVIEW_REQUIRED,
        }:
            raise APIOutputAdapterError(f"State {state.value!r} is not valid for an API output.")
        return state

    kind = (_optional_string(payload.get("kind")) or "inference").lower()
    if kind == "opinion":
        return InformationState.API_OPINION
    if kind in {"null", "no_conclusion"}:
        return InformationState.NULL_RESULT
    if kind in {"pending", "review"}:
        return InformationState.PENDING
    if kind in {"inference", "prediction", "synthesis", "final_text"}:
        return InformationState.API_INFERENCE
    raise APIOutputAdapterError(f"Unknown API output kind: {kind!r}.")


def _support_refs(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise APIOutputAdapterError("support_refs must be a list or tuple of strings.")
    refs: list[str] = []
    for index, item in enumerate(value):
        text = _optional_string(item)
        if text is None:
            raise APIOutputAdapterError(f"support_refs[{index}] must be a non-empty string.")
        refs.append(text)
    return tuple(refs)


def _custody(
    payload: dict[str, Any], *, sha256: str | None, support_refs: tuple[str, ...]
) -> CustodyState:
    declared = _optional_string(payload.get("custody_state"))
    if declared:
        try:
            return CustodyState(declared.lower())
        except ValueError as exc:
            raise APIOutputAdapterError(f"Unknown custody_state: {declared!r}.") from exc
    if sha256:
        return CustodyState.HASHED
    if support_refs:
        return CustodyState.REFERENCED
    return CustodyState.UNKNOWN


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
