# Precision Gate Product Architecture

## Product identity

Precision Gate is a third product.

It is not TCRIA.
It is not Quinta Ordem Gate.
It is not an API wrapper.
It is not an autonomous decision engine.

It is a mobile custody, precision, and alert layer that follows information across the audit trail.

## Product triangle

```text
TCRIA
  -> produces structured audit information, signals, gates, classifications, bundles, and institutional outputs

Quinta Ordem Gate
  -> verifies integrity, traceability, evidence support, logical consistency, and resolution

Precision Gate
  -> tracks the information in motion, classifies its state, preserves custody, alerts inconsistencies, and supports human decision
```

## Flow rule

The flow does not stop merely because a layer returns null, warning, opinion, hypothesis, or pending signal.

The flow continues, but the state travels with the information.

```text
information item
  -> source state
  -> TCRIA state
  -> API state
  -> Quinta Ordem state
  -> Precision Gate state
  -> human-review state
```

## Non-coercive reference rule

Precision Gate can alert, classify, and point.

It can say:

- this is supported;
- this is unsupported;
- this is pending;
- this is blocked;
- this is an API inference;
- this is a TCRIA signal;
- this is not readable evidence;
- this contradiction should be reviewed;
- this output appears to rely on weak support.

It cannot force a final decision.

The final decision remains human.

## API transparency rule

Precision Gate must not assume that an API will explain its internal reasoning.

When an API returns only a final result, Precision Gate tracks the external relation between:

- input payload;
- TCRIA bundle;
- API prompt or preset;
- API model and response metadata;
- API output;
- Quinta Ordem evaluation;
- Precision Gate state.

The API may be silent internally. The custody trail must remain externally auditable.

## Alert behavior

Precision Gate must be able to warn the surrounding system when a responsibility, inconsistency, omission, or unsupported promotion appears in the trail.

It points to operational responsibility, not final legal guilt.

Example alert language:

```text
A conclusion appears to rely on a signal that was not promoted to fact.
A previous block is present and must not be erased.
A document was unreadable; textual support cannot be presumed.
An API conclusion diverges from the TCRIA gate state.
A pending human review point was ignored by a later output.
```

## First technical components

```text
src/precision_gate/
├── custody_state.py       # mobile information states
├── tcria_adapter.py       # TCRIA bundle/contracts -> Precision events
├── api_output_adapter.py  # API response output -> Precision events
├── quinta_adapter.py      # Precision events -> Quinta Ordem ExecutionContext
├── pipeline.py            # orchestration without taking final decision
├── metrics.py             # operational precision and release-safety metrics
└── reporting.py           # final audit/reference report
```

## Design stop rule

If any component cannot preserve TCRIA principles, evidence custody, human decision, or state distinction, the implementation must stop and ask the owner for a decision.
