# Current-estate trace — customer service reporting

## Observed synthetic estate

- **Processing:** separate case, interaction and workforce extracts are reconciled before publication.
- **Data:** case, interaction and workforce records form the declared synthetic population.
- **Interfaces:** scheduled source extracts and the consumer reporting dataset are the observed interfaces.
- **Controls:** reconciliation evidence must exist before publication.
- **Pain:** interface timing is opaque and manual reconciliation is not repeatable.
- **Continuity needs:** retain the business-day cut-off, published metric names and explainable population differences.
- **Accidental legacy behaviour:** manual reconciliation and opaque source-timing assumptions are not target requirements.
- **Uncertainty:** source ownership required explicit evidence rather than inference.
- **Verification case intent:** snapshot parity against the approved frozen expected daily output.
- **Check families:** parity; delivery integrity.
- **Lineage/checkpoint expectations:** published report — Ishan Rao owns the reconciliation evidence.
- **Acceptance rules:** two accepted synthetic daily publications and Maya Chen's named acceptance are required.
- **Evidence:** `EVD-MOD-010` scheduled-extract inventory; `EVD-MOD-011` report lineage sample; `EVD-MOD-012` reconciliation log.
- **Flow:** case, interaction and workforce extracts arrive on separate schedules; a reporting dataset is reconciled manually before publication.
- **Controls and risks:** interface timing is opaque, key coverage is not measured, and the manual reconciliation has no repeatable evidence identifier.
- **Continuity requirements:** retain the business-day cut-off, published metric names and the ability to explain a population difference.
- **Not target design:** this trace records present constraints only; it does not prescribe the new platform.

## Paired review

- **Paired review:** completed before design.
- **Reviewer:** trace-current-estate reviewer.
- **Finding:** extract ownership was inferred rather than evidenced.
- **Disposition:** resolved — `EVD-MOD-013` assigns synthetic source ownership to Ishan Rao.
- **Finding T-02:** manual reconciliation lacked an explicit failure condition.
- **Disposition:** visible disposition — the implementation plan must reject an unreconciled population before publication.

## Acceptance

Ishan Rao accepts the trace as the bounded synthetic current-estate record.
