# Precision Gate Integration Contracts

## Purpose

Precision Gate composes independently governed products through immutable artifacts and
versioned mappings.

```text
External product produces.
Precision Gate observes by reference.
Quinta Ordem verifies a normalized context.
Precision Gate consolidates.
Human authority decides.
```

No adapter may copy upstream decision logic or silently infer a missing field.

## TCRIA official audit bundle

**Profile:** `tcria.audit_bundle.v1`

Required bundle fields:

| Field | Precision use |
|---|---|
| `total_files_scanned` | Reconciled against both published record collections |
| `accusation_set_count` | Reconciled against `accusation_set` |
| `accusation_set` | Records whose `raises_accusation` must be `true` |
| `non_accusation_set` | Records whose `raises_accusation` must be `false` |

Required record fields include `sha256`, `document.sha256`, a relative document
reference, `extraction_status`, `classification`, `raises_accusation`,
`classification_reasons`, and `gates` where the TCRIA contract requires them.

The adapter:

- checks top-level and nested document hashes agree;
- rejects accusatory records without the five current TCRIA gates;
- requires non-empty gate status and reason;
- maps unknown gate status to a preserved source status plus a blocked Precision state;
- maps unknown classification to `pending`, never to fact;
- removes source `document.text` from all Precision artifacts;
- binds uninterpreted source fields through the bundle payload digest.

Current ordered TCRIA gates are:

1. `prescriptiveGate`
2. `complianceGate`
3. `traceabilityCheck`
4. `maturityGate`
5. `ledgerRuntimeCheck`

Later gates follow in lexical order. A block remains effective for all later gates in the
same record.

## External AI/API output

**Profile:** `precision.api_output.v1`

The first implementation is provider-neutral and makes no network call.

| Field | Required | Meaning |
|---|---:|---|
| `output_id` | Yes | Stable external output ID |
| `input_refs` | Yes | Existing IDs in the observed Precision trail |
| `provider`, `model` | Yes | External producer metadata |
| `prompt_ref` | Yes | Preset/template reference; prompt text is not required |
| `prompt_sha256` | No | Hash when the exact prompt artifact is retained externally |
| `response_id` | Yes | Provider response identifier |
| `output_ref`, `output_sha256` | Yes | External output custody reference |
| `output_type` | Yes | `null`, `opinion`, `inference`, or `hypothesis` |
| `claim_relations` | No | `supports`, `contradicts`, `mentions`, `omits`, or `unseen` |
| `response_metadata` | No | Operational metadata without hidden reasoning |

Unknown top-level fields and hidden-reasoning keys are rejected. Output content is kept
outside the Precision event; API output can never enter as `fact_supported`.

## Quinta Ordem ExecutionContext

**Adapter version:** `1.0`

Precision Gate produces the documented normalized fields:

```text
execution_id
evidence
artifacts
gate_results
logs
decisions
signals_for_verification
metadata.open_points
```

Rules:

- source evidence and derived event artifacts remain distinguishable;
- every derived artifact has a canonical event SHA-256;
- facts, allegations, opinions, and other states remain unpromoted decisions;
- signals use `signals_for_verification`, allowing the Quinta adapter to create one
  unpromoted decision and one open review point without duplication;
- all caller-owned data is detached through strict canonical serialization.

Precision Gate does not evaluate the context itself. A Quinta Ordem runtime evaluates it
outside this package.

## Quinta Ordem GateDecision

**Schema version:** `1.0`

Required fields are `execution_id`, `status`, `confidence`, the five-dimensional
`breakdown`, `findings`, `remaining_uncertainties`, `human_review_required`,
`evaluated_verifiers`, `execution_context_sha256`, and `schema_version`.

Status mapping:

| Quinta status | Precision state | Human review |
|---|---|---:|
| `approved` | `pending` until human review | No gate-mandated review |
| `conditional` | `human_review_required` | Required |
| `returned_for_correction` | `returned_for_correction` | Required |
| `blocked` | `blocked` | Required |

An approved decision must not require review and must contain the evaluated context hash.
Every other status must require review. Confidence remains labeled
`confidence_coverage`; it is not a probability that the conclusion is true.

## Human review

Human review records reviewer reference, outcome, summary, support references, and the
condition event IDs it resolves.

| Outcome | Effect |
|---|---|
| `accepted` | Completes the named review conditions |
| `rejected` | Adds a persistent block |
| `returned_for_correction` | Adds a new review requirement |

Accepting a read-failure resolution requires a replacement human support reference.
Review does not delete any preceding event.

## Final release

Final release is possible only when:

```text
Quinta status == approved
AND human outcome == accepted
AND active blocks == none
AND active read failures == none
AND active review requirements == none
AND unresolved coherence conflicts == none
AND custody chain verifies
```

Release means delivery eligibility, not autonomous disposition of a consequential case.

## Schema drift and owner escalation

An unsupported profile, version, field shape, state, or lossy mapping fails closed.
Precision Gate does not normalize contract drift into a successful result. If preserving
the source contract would require weakening a TCRIA principle, the pipeline emits or
records an owner-decision-required design block before implementation proceeds.
