# Capability discovery — renewable asset observability

## Approved greenfield needs

- **Required capabilities:** validate synthetic asset identity and event time; reject invalid measurements; calculate approved observability measures; produce explainable alerts and consumer views.
- **Constraints:** all records and evidence remain synthetic; consumer policy owns alert severity; no current estate or historic comparison route is assumed.
- **Evidence:** `EVD-GRN-001` requirement workshop; `EVD-GRN-002` asset-event glossary; `EVD-GRN-003` consumer scenario.
- **Uncertainty:** consumer timing threshold is confirmed by Elena Brooks before the delivery contract is approved.
- **Verification case intent:** contract conformance against approved golden scenarios, without a historic comparison route.
- **Check families:** conformance; invariant.
- **Lineage/checkpoint expectations:** consumer view — Dev Malik owns the synthetic evidence checkpoint.
- **Acceptance rules:** approved golden scenarios and invariants pass before Elena Brooks accepts the consumer view.

## Paired review

- **Paired review:** completed before design.
- **Reviewer:** greenfield-capability reviewer.
- **Finding:** alert timing lacked a named evidence owner.
- **Disposition:** resolved — Dev Malik owns synthetic timing evidence in `EVD-GRN-004`.
