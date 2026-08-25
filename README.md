# Precision Gate

> Mobile custody and operational precision layer for the authoritative TCRIA -> Quinta Ordem -> Precision flow.

Precision Gate is the third independent product in the chain. It is not a copy of TCRIA, not a replacement for Quinta Ordem Gate, not an API wrapper, and not an autonomous decision-maker.

It follows the accumulated audit trail after TCRIA and Quinta Ordem have produced their own immutable outputs, preserving provenance, state, support, warnings, gate decisions, and human-review requirements.

## Authoritative product flow

```text
Document / Evidence
    -> TCRIA
    -> TCRIA bundle + states + trail + native outputs
    -> Quinta Ordem
    -> Quinta findings + decision + uncertainties + native outputs
    -> Precision
    -> custody state + promotion control + alerts + metrics + derived Markdown reports
    -> human decision
```

The execution is unidirectional. A later product may evaluate or disagree with an earlier state, but it does not rewrite the historical output of an earlier product.

Conceptually:

```text
S0 = original input
S1 = S0 + TCRIA output
S2 = S1 + Quinta Ordem output
S3 = S2 + Precision output
```

Each product remains independently executable and keeps its own native outputs.

## Current implementation

The repository contains:

- mobile information and custody states;
- TCRIA audit-bundle adapter;
- Quinta Ordem `GateDecision` ingestion;
- external AI/API output adapter;
- orchestration that consumes the upstream TCRIA + Quinta trail;
- transparent operational metrics;
- consolidated Markdown reporting;
- eight derived Markdown report views;
- automated tests and CI.

This is an initial integration implementation, not a claim of complete empirical validation.

## Important synchronization rule

Precision does **not** generate a Quinta Ordem input from Precision events in the authoritative execution path.

The `build_execution_context_payload(...)` and `to_quinta_execution_context(...)` helpers remain available only as compatibility/integration utilities for external callers. They are not used by `PrecisionPipeline.run(...)` to reverse the product order.

The authoritative order is always:

```text
TCRIA -> Quinta Ordem -> Precision
```

## Precision pipeline

### Container command

The image runs Precision only after receiving the native TCRIA bundle and Quinta Ordem decision
as read-only inputs:

```bash
docker build -t precision-gate .
docker run --rm --network none \
  -v "$PWD/upstream:/workspace/upstream:ro" \
  -v "$PWD/output:/workspace/output" \
  precision-gate \
  --execution-id case-001 \
  --tcria /workspace/upstream/tcria.json \
  --quinta /workspace/upstream/case-001_quinta_ordem.json \
  --output /workspace/output
```

The command rejects cross-case input when the Quinta Ordem `execution_id` differs and rejects a
TCRIA bundle whose canonical SHA-256 identity differs from the one evaluated by Quinta Ordem. It
writes the eight native Markdown views plus a Markdown SHA-256 manifest. Full multi-product
composition is owned by the TCRIA repository; Precision remains independently executable.

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
                "classification": "signal",
            }
        ],
    },
    quinta_decision={
        "execution_id": "case-001",
        "status": "conditional",
        "findings": [],
        "human_review_required": True,
    },
    api_outputs=[],
)

write_report_bundle(result, "outputs")
```

`result.execution_context` preserves the versioned dataclass contract. The preferred
`result.upstream_context` read alias exposes the same detached snapshot. A run is marked as the
authoritative flow only when a matching Quinta Ordem decision is present.

## Package

```text
src/precision_gate/
├── __init__.py
├── custody_state.py
├── tcria_adapter.py
├── api_output_adapter.py
├── quinta_adapter.py
├── pipeline.py
├── metrics.py
└── reporting.py
```

## Product responsibilities

### TCRIA

Organizes and qualifies the informational base: provenance, hashes, custody, traceability, conservative classification, failures, null states, and its own audit trail.

### Quinta Ordem

Consumes the TCRIA state and performs its own deterministic structural verification: integrity, traceability, evidence support, consistency, resolution, findings, uncertainty, and human-review requirements.

### Precision

Consumes the accumulated TCRIA + Quinta history and controls current operational state: custody continuity, legitimate promotion, divergence, alerts, metrics, uncertainty preservation, and derived reports.

A Precision classification never silently rewrites a TCRIA or Quinta result.

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

Every output is a derived analytical artifact and does not replace the original evidence or upstream native outputs.

## Metrics

The initial metrics include:

- custody integrity rate;
- operational precision;
- release safety rate;
- counts for pending, blocked, returned, inferred, and human-review-required states.

These are engineering measurements, not guarantees of absolute, legal, scientific, or factual truth.

## API / FastAPI boundary

FastAPI, MCP, CLIs, or other transport layers should remain thin interfaces around the independent products. They may start a run, pass versioned outputs forward, retrieve reports, and expose health/status endpoints, but they must not become the source of truth for audit logic or merge the three products into one implementation.

## Chain-of-custody boundary

This repository must not contain original real evidence, identifiable documents, unredacted private records, or confidential process material.

Allowed repository material includes code, documentation, synthetic fixtures, anonymized examples, hashes, manifests, schemas, derived reports, and validation summaries.

## Human decision

Precision Gate informs, classifies, alerts, measures, and preserves custody. It does not replace human judgment or final institutional authority.

## Integration sources

- TCRIA base: `batt1984rodrigo-del/tcria-09215b00`
- Quinta Ordem base: `batt1984rodrigo-del/Fifth-order/tree/main/quinta-ordem-gate`

## Next validation work

1. direct integration runs against current TCRIA and Quinta packages;
2. malformed, incomplete, contradictory, and adversarial inputs;
3. mutation/property-based tests;
4. performance, scale, privacy, and reproducibility measurements;
5. independent human review and baseline comparison;
6. versioned contract tests for every TCRIA -> Quinta -> Precision boundary.
