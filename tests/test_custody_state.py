import pytest

from precision_gate.custody_state import CustodyState, InformationState, PrecisionEvent


def test_supported_fact_with_refs_can_be_promoted() -> None:
    event = PrecisionEvent(
        event_id="evt-1",
        source_layer="tcria",
        information_id="fact-1",
        information_state=InformationState.FACT_SUPPORTED,
        custody_state=CustodyState.HASHED,
        summary="Supported fact carried through the trail.",
        support_refs=("EVD-001",),
        promotable_as_fact=True,
    )

    event.assert_safe_promotion()


def test_api_opinion_cannot_be_promoted_as_fact() -> None:
    event = PrecisionEvent(
        event_id="evt-2",
        source_layer="api",
        information_id="api-output-1",
        information_state=InformationState.API_OPINION,
        custody_state=CustodyState.REFERENCED,
        summary="API output is an opinion, not a supported fact.",
        support_refs=("TCRIA-BUNDLE-1",),
        promotable_as_fact=True,
    )

    with pytest.raises(ValueError, match="Only fact_supported"):
        event.assert_safe_promotion()


def test_promotable_fact_requires_support_refs() -> None:
    event = PrecisionEvent(
        event_id="evt-3",
        source_layer="tcria",
        information_id="fact-2",
        information_state=InformationState.FACT_SUPPORTED,
        custody_state=CustodyState.HASHED,
        summary="A claimed fact without explicit references.",
        promotable_as_fact=True,
    )

    with pytest.raises(ValueError, match="support_refs"):
        event.assert_safe_promotion()


def test_broken_custody_cannot_be_promoted() -> None:
    event = PrecisionEvent(
        event_id="evt-4",
        source_layer="ocr",
        information_id="doc-1",
        information_state=InformationState.FACT_SUPPORTED,
        custody_state=CustodyState.BROKEN,
        summary="Broken custody cannot support promotion.",
        support_refs=("EVD-001",),
        promotable_as_fact=True,
    )

    with pytest.raises(ValueError, match="custody"):
        event.assert_safe_promotion()
