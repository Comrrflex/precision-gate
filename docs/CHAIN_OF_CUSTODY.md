# Chain of Custody Policy

## Purpose

Precision Gate must preserve the custody trail of information as it moves through TCRIA, API outputs, Quinta Ordem Gate, and human review.

It is a mobile custody layer: it follows the information, records its state, and prevents unsupported promotion.

## Repository rule

This repository must not store original real evidence.

Allowed in this repository:

- code;
- documentation;
- synthetic fixtures;
- anonymized examples;
- hashes;
- manifests;
- schemas;
- derived reports;
- validation summaries.

Not allowed in this repository:

- identifiable real documents;
- original evidence files;
- unredacted PDFs;
- private personal data;
- confidential process records;
- uncontrolled copies of original evidence;
- files treated as originals after being derived.

## Custody model

Precision Gate works by:

- reference;
- hash;
- state;
- manifest;
- explicit source attribution;
- versioned execution context;
- reproducible derived bundles.

It must never require uncontrolled movement of original evidence.

### Source versus payload digests

Precision Gate distinguishes:

- `artifact_sha256`: the digest of the exact external artifact when raw bytes are
  available;
- `payload_sha256`: the digest of the validated canonical payload used by the adapter;
- `receipt_sha256`: the digest linking one immutable Precision event to the preceding
  receipt.

These digests answer different questions and must not be silently substituted.

### Append-only receipt chain

The genesis receipt binds the schema version, trace ID, and creation time. Each following
receipt binds:

1. the event sequence;
2. the complete canonical event;
3. the previous receipt SHA-256.

The final receipt is stored in the final report manifest. Chain verification must fail on
content mutation, insertion, removal, duplication, reordering, trace mismatch, or final
digest mismatch.

## Evidence reading rule

If OCR, parsing, extraction, or file loading fails, the system must not pretend that the evidence was read.

The flow may continue only as a failure-aware trail state, such as:

- `extraction_failed`;
- `ocr_failed`;
- `unreadable`;
- `human_review_required`;
- `not_promotable_as_fact`.

## Promotion rule

An information item may move through the flow even when uncertain, but it cannot be promoted beyond its support.

Examples:

- API opinion remains opinion or inference unless supported by evidence.
- TCRIA signal remains signal unless verified.
- Allegation remains allegation unless supported.
- Null remains absence of conclusion.
- Blocked state remains blocked unless resolved by an explicit later step.

A resolution event must name the prior condition event. A human reviewer may resolve an
OCR or extraction failure only by attaching an explicit support reference to the
replacement reading or review. The source failure remains in history.

`released` is an operational delivery state, not an information claim. It requires an
approved deterministic gate, completed human acceptance, and no unresolved custody,
coherence, or review condition.

## External handoff rule

TCRIA is observed through its completed official bundle. Precision Gate:

- verifies published counts, partitions, hashes, extraction states, and gate reasons;
- carries relative references and hashes, not source text;
- does not reopen paths published by the bundle;
- does not recalculate TCRIA governance outcomes.

External API output is observed by a provider-neutral reference envelope. Precision Gate
does not call the model or request hidden reasoning.

Quinta Ordem receives a derived `ExecutionContext` and returns a separately identified
`GateDecision`. Its confidence value is verification coverage, not factual probability.

## Derived artifact rule

Final reports must be written outside all declared source-evidence roots. Existing
different content is never overwritten. JSON and Markdown are written first, verified
against their expected hashes, and the manifest is written last.

## Audit aftermath rule

If something happens later, Precision Gate must be able to show:

- what entered the trail;
- where it came from;
- what hash or reference identified it;
- how TCRIA classified it;
- how the API responded;
- how Quinta Ordem Gate evaluated it;
- what was warned, returned, blocked, or released;
- what required human review;
- what was used as support for the final report;
- which uncertainties remained.

Precision Gate does not decide legal or institutional truth. It preserves the path showing where operational truth was best supported at the time of the trail.
