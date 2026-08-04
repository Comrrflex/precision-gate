# TCRIA Non-Abandonment Policy

## Principle

No principle, invariant, safety rule, custody rule, human-review rule, or governance assumption inherited from TCRIA may be abandoned, weakened, replaced, bypassed, or silently reinterpreted by Precision Gate without explicit owner consent.

Precision Gate is a new product, but it must not erase the foundations that make TCRIA reliable.

## Operational rule

If an integration, adapter, metric, report, or pipeline step cannot preserve a TCRIA principle, the implementation must stop at the design level and request owner decision.

The system must not solve such conflicts by silently simplifying, dropping fields, relaxing custody, treating uncertainty as fact, or converting missing support into confidence.

## Required escalation

Escalate to the owner before implementation when any of the following occurs:

- a TCRIA field cannot be mapped without loss;
- a TCRIA gate result conflicts with an API output;
- a TCRIA signal would need to be promoted to fact;
- a null result would be converted into a conclusion;
- a pending point would be ignored for convenience;
- OCR or extraction failure would need to be treated as readable content;
- original evidence would need to be moved, copied, overwritten, or stored in the public repository;
- a human-review requirement would be removed;
- a custody state would be simplified into a binary pass/fail result;
- a metric would imply certainty of truth instead of operational confidence.

## Preserved TCRIA foundations

Precision Gate must preserve at least these TCRIA foundations:

1. Decision is human.
2. The system supports review; it does not replace the reviewer.
3. The flow continues, but classification follows the information.
4. Information is not promoted beyond its support.
5. Evidence custody is preserved.
6. Originals are not modified.
7. OCR/extraction failure is not treated as successful reading.
8. Null, warning, signal, allegation, hypothesis, opinion, and fact are different states.
9. Traceability matters as much as the conclusion.
10. Uncertainty must be visible, not hidden.
11. API output is not automatically truth.
12. Prior blocks, warnings, or pending points must not be erased silently.

## Owner decision clause

When a conflict appears between product implementation and TCRIA principles, the owner decides.

Until the owner decides, the safest implementation is to preserve the TCRIA principle and mark the Precision Gate step as unresolved or blocked for design review.
