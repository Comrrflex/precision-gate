# Precision Gate

> Mobile custody and operational precision layer for TCRIA + Quinta Ordem Gate.

Precision Gate is a new product. It is not a copy of TCRIA, not a replacement for Quinta Ordem Gate, and not an autonomous decision-maker.

It is a **mobile custody reference layer** that follows information as it moves through an audit trail, preserving provenance, state, support, warnings, gate decisions, and human-review requirements.

## Core idea

Precision Gate tracks outputs from:

- TCRIA, as the informational producer and governance/audit organizer;
- Quinta Ordem Gate, as the deterministic verification engine;
- API outputs, when an external model or service produces a synthesis, opinion, institutional output, or final text.

Its job is to preserve the trail and point to where operational truth is best supported.

It does not force a decision.

The final decision remains human.

## Golden rule

Precision Gate follows the TCRIA golden rule:

> Analyze carefully, preserve custody, classify uncertainty, and keep the flow moving — unless evidence reading itself fails.

The flow may continue through nulls, opinions, hypotheses, warnings, signals, pending points, and returns. However, no output may be promoted beyond the support it has.

If OCR or evidence extraction fails, the system must not pretend that the evidence was read. The trail may continue as a failure record, but the content cannot be promoted as reliable textual evidence.

## Product boundaries

TCRIA remains the original product.

Fifth-order / Quinta Ordem Gate remains the deterministic gate product.

Precision Gate is the third product: the mobile custody, precision, alert, and reporting layer that composes both while preserving their boundaries.

No TCRIA principle may be abandoned, weakened, replaced, or silently bypassed without explicit owner consent.

## Human decision

Precision Gate informs, classifies, alerts, and preserves custody.

It does not replace human judgment, institutional authority, legal review, medical review, credit review, or any final decision affecting rights, health, liberty, finance, or third parties.

## Initial integration sources

- TCRIA base: `batt1984rodrigo-del/tcria-09215b00`
- Quinta Ordem base: `batt1984rodrigo-del/Fifth-order/tree/main/quinta-ordem-gate`

## First implementation direction

The first version should define:

- custody states;
- product boundaries;
- non-abandonment principles for TCRIA;
- adapters for TCRIA audit bundle and API output;
- adapter to Quinta Ordem `ExecutionContext`;
- reports that show what was supported, pending, blocked, returned, inferred, or human-review required;
- metrics for operational precision and release safety.
