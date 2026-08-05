# Precision Gate

> Mobile custody and operational precision layer for TCRIA + Quinta Ordem Gate.

Precision Gate is a third product. It is not a copy of TCRIA, not a replacement for Quinta Ordem Gate, not an API wrapper, and not an autonomous decision-maker.

It is a **mobile custody, precision, alert, and reporting layer** that follows information as it moves through an audit trail, preserving provenance, state, support, warnings, gate decisions, and human-review requirements.

## Current status

The repository now contains an executable first implementation of the architecture described in this manual:

- mobile information and custody states;
- TCRIA audit-bundle adapter;
- external AI/API output adapter;
- Quinta Ordem `ExecutionContext` payload adapter;
- Quinta Ordem `GateDecision` ingestion;
- orchestration pipeline that does not take the final decision;
- transparent operational metrics;
- consolidated Markdown reporting;
- eight derived Markdown report views;
- automated tests and CI.

This is an **initial integration implementation**, not a claim of complete empirical validation. Real-case, adversarial, scale, and independent validation remain necessary before consequential production use.

## Core idea

Precision Gate tracks outputs from:

- **TCRIA**, as the informational producer and governance/audit organizer;
- **Quinta Ordem Gate**, as the deterministic verification engine;
- **API outputs**, when an external model or service produces a synthesis, opinion, inference, institutional output, or final text.

Its job is to preserve the trail and point to where operational truth is best supported.

It does not force a decision. The final decision remains human.

## Product flow

```text
TCRIA audit bundle
    -> Precision TCRIA adapter
    -> classified mobile-custody events

AI/API output
    -> Precision API adapter
    -> opinion, inference, pending, null, or explicitly supported fact

Precision events
    -> Quinta Ordem ExecutionContext payload
    -> Quinta Ordem deterministic evaluation
    -> findings, status, confidence, uncertainty, and human review

All classified events
    -> Precision metrics, alerts, and Markdown reports
    -> human decision
```

## Golden rule

Precision Gate follows the TCRIA golden rule:

> Analyze carefully, preserve custody, classify uncertainty, and keep the flow moving — unless evidence reading itself fails.

The flow may continue through nulls, opinions, hypotheses, warnings, signals, pending points, and returns. However, no output may be promoted beyond the support it has.

If OCR or evidence extraction fails, the system must not pretend that the evidence was read. The trail may continue as a failure record, but the content cannot be promoted as reliable textual evidence.

## Implemented package

```text
src/precision_gate/
├── __init__.py
├── custody_state.py       # mobile information and custody states
├── tcria_adapter.py       # TCRIA audit bundle -> Precision events
├── api_output_adapter.py  # AI/API output -> classified Precision event
├── quinta_adapter.py      # Precision events <-> Quinta Ordem contracts
├── pipeline.py            # orchestration without final decision authority
├── metrics.py             # operational precision and release-safety metrics
└── reporting.py           # consolidated and categorized Markdown reports
```

## Quick start

Requirements:

- Python 3.11 or later;
- no runtime dependency outside the standard library;
- `pytest` and `ruff` for development.

```bash
python -m pip install -e ".[dev]"
pytest -q
```

Run the synthetic integration example:

```bash
python examples/run_precision_gate.py
```

The example uses synthetic data only and writes derived reports to `outputs/`.

## Minimal use

```python
from precision_gate import PrecisionPipeline, write_report_bundle

result = PrecisionPipeline().run(
    execution_id="case-001",
    tcria_bundle={
        "accusation_set": [],
        "non_accusation_set": [
            {
                "file_name": "case.md",
                "sha256": "0" * 64,
                "extraction_status": "ok",
                "classification": "fact_supported",
                "information_state": "fact_supported",
                "evidence_refs": ["EVD-001"],
                "summary": "Fact explicitly supported by the documented trail.",
            }
        ],
    },
    api_outputs=[
        {
            "output_id": "api-001",
            "kind": "synthesis",
            "content": "A model-generated reading that remains an inference.",
            "support_refs": ["EVD-001"],
            "requires_human_review": True,
        }
    ],
)

write_report_bundle(result, "outputs")
```

An API synthesis remains an inference unless it is explicitly classified as `fact_supported`, has explicit support references, and preserves a permitted custody state.

## Quinta Ordem integration

`build_execution_context_payload(...)` creates a detached dictionary compatible with the documented Quinta Ordem `ExecutionContext` fields:

- `execution_id`;
- `evidence`;
- `artifacts`;
- `gate_results`;
- `logs`;
- `decisions`;
- `metadata`.

`to_quinta_execution_context(...)` creates the concrete Quinta Ordem dataclass when the `quinta_ordem` package is available in the same Python environment.

`adapt_gate_decision(...)` reads a serialized Quinta Ordem decision and preserves:

- status;
- confidence and verifier breakdown;
- findings;
- severity;
- required action;
- remaining uncertainties;
- execution-context hash;
- human-review requirements.

## Markdown outputs

`write_report_bundle(...)` writes eight derived `.md` views:

```text
precision_summary.md
precision_custody.md
precision_supported.md
precision_pending.md
precision_blocked.md
precision_returned.md
precision_inferred.md
precision_human_review.md
```

Every output is marked as a derived analytical artifact. Reports do not modify, replace, or become part of the original evidence.

## Metrics

The initial metrics are deliberately transparent:

- **custody integrity rate**: proportion of events with preserved, referenced, hashed, or manifested custody;
- **operational precision**: safely grounded supported facts among fact-like candidates;
- **release safety rate**: safe candidates among events marked released or promotable;
- counts for pending, blocked, returned, inferred, and human-review-required states.

These are engineering measurements. They are not guarantees of absolute, legal, scientific, or factual truth.

## Product boundaries

TCRIA remains the original product.

Fifth Order / Quinta Ordem Gate remains the deterministic gate product.

Precision Gate is the third product that composes both while preserving their boundaries.

No TCRIA principle may be abandoned, weakened, replaced, or silently bypassed without explicit owner consent.

## Chain-of-custody boundary

This repository must not contain original real evidence, identifiable documents, unredacted private records, or confidential process material.

Allowed repository material includes:

- code and documentation;
- synthetic fixtures;
- anonymized examples;
- hashes and manifests;
- schemas;
- derived reports;
- validation summaries.

## Human decision

Precision Gate informs, classifies, alerts, measures, and preserves custody.

It does not replace human judgment, institutional authority, legal review, medical review, credit review, or any final decision affecting rights, health, liberty, finance, employment, or third parties.

## Initial integration sources

- TCRIA base: `batt1984rodrigo-del/tcria-09215b00`
- Quinta Ordem base: `batt1984rodrigo-del/Fifth-order/tree/main/quinta-ordem-gate`

## Validation status and next work

The local suite currently contains 20 passing tests covering the custody core, adapters, Quinta Ordem contract mapping, metrics, orchestration, and Markdown generation.

The next validation phase should add:

1. retrospective real cases with lawful and controlled access;
2. malformed, incomplete, contradictory, and adversarial inputs;
3. mutation and property-based tests;
4. direct integration runs against installed TCRIA and Quinta Ordem packages;
5. performance, scale, privacy, and reproducibility measurements;
6. independent human review and baseline comparison.

The product is now executable as an initial integration layer. It is not yet represented as fully validated for consequential production decisions.
