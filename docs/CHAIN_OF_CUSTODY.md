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
