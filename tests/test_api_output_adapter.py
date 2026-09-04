import pytest

from precision_gate.api_output_adapter import APIOutputAdapterError, adapt_api_output
from precision_gate.custody_state import CustodyState, InformationState


def test_api_output_defaults_to_inference(sign_api_output) -> None:
    event = adapt_api_output(sign_api_output({"output_id": "api-1", "content": "Possible interpretation."}))

    assert event.information_state is InformationState.API_INFERENCE
    assert event.custody_state is CustodyState.UNKNOWN
    assert event.promotable_as_fact is False


def test_api_opinion_remains_opinion(sign_api_output) -> None:
    event = adapt_api_output(
        sign_api_output({
            "output_id": "api-2",
            "content": "Opinion based on a supplied bundle.",
            "kind": "opinion",
            "support_refs": ["TCRIA-BUNDLE-1"],
        })
    )

    assert event.information_state is InformationState.API_OPINION
    assert event.custody_state is CustodyState.REFERENCED


def test_api_output_cannot_request_fact_promotion_without_fact_state(sign_api_output) -> None:
    with pytest.raises(APIOutputAdapterError, match="fact_supported"):
        adapt_api_output(
            sign_api_output({
                "output_id": "api-3",
                "content": "Unsupported conclusion.",
                "promotable_as_fact": True,
            })
        )


def test_api_supported_fact_requires_explicit_support(sign_api_output) -> None:
    with pytest.raises(APIOutputAdapterError, match="support_refs"):
        adapt_api_output(
            sign_api_output({
                "output_id": "api-4",
                "content": "Claimed fact.",
                "information_state": "fact_supported",
                "custody_state": "hashed",
                "sha256": "d" * 64,
                "promotable_as_fact": True,
            })
        )


def test_unsigned_api_output_is_rejected(sign_api_output) -> None:
    with pytest.raises(APIOutputAdapterError, match="Missing signature_hmac"):
        adapt_api_output({"output_id": "unsigned", "content": "Unsigned reading."})


def test_tampered_api_output_is_rejected(sign_api_output) -> None:
    payload = sign_api_output({"output_id": "signed", "content": "Original reading."})
    payload["content"] = "Changed reading."
    with pytest.raises(APIOutputAdapterError, match="Invalid signature_hmac"):
        adapt_api_output(payload)


def test_invalid_key_configuration_is_rejected(sign_api_output, monkeypatch) -> None:
    payload = sign_api_output({"output_id": "signed", "content": "Original reading."})
    monkeypatch.setenv("PRECISION_GATE_HMAC_SECRETS", "[]")
    with pytest.raises(APIOutputAdapterError, match="Invalid PRECISION_GATE_HMAC_SECRETS"):
        adapt_api_output(payload)
