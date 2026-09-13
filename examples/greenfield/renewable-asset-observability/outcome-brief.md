# Frame record — renewable asset observability

## Outcome contract

- **Consumer outcome:** operations teams receive timely, trustworthy asset-condition and production signals.
- **Success signals:** approved golden scenarios pass; platform invariants pass for each accepted consumer view.
- **Success criteria:** {"acceptance_rule":"approved golden scenarios and invariants pass before Elena Brooks accepts the consumer view","check_family":"conformance","evidence":[{"digest":"digest-evd-grn-005","identifier":"EVD-GRN-005","version":"v1"}],"required_result":"pass","signal":"approved golden scenarios pass","validator":{"digest":"digest-golden-scenario-validator","identifier":"golden-scenario-validator","kind":"validator_specification","version":"v1"}}
- **Success criteria:** {"acceptance_rule":"approved golden scenarios and invariants pass before Elena Brooks accepts the consumer view","check_family":"invariant","evidence":[{"digest":"digest-evd-grn-006","identifier":"EVD-GRN-006","version":"v1"}],"required_result":"pass","signal":"platform invariants pass for each accepted consumer view","validator":{"digest":"digest-platform-invariant-validator","identifier":"platform-invariant-validator","kind":"validator_specification","version":"v1"}}
- **Scope:** synthetic asset events, quality controls, measures, alerts and consumer views.
- **Authorities:** Elena Brooks accepts consumer outcomes and Dev Malik owns synthetic source evidence.
- **Measures:** declared source latency, contract-valid observations and explainable alert delivery.
- **Evidence:** `EVD-GRN-001` requirement workshop; `EVD-GRN-002` asset-event glossary; `EVD-GRN-003` consumer scenario; `EVD-GRN-005@v1#digest-evd-grn-005` golden scenarios; `EVD-GRN-006@v1#digest-evd-grn-006` invariant specification; `golden-scenario-validator@v1#digest-golden-scenario-validator`; `platform-invariant-validator@v1#digest-platform-invariant-validator`.
- **Constraints:** all data and evidence are synthetic; alert policy is consumer-owned.
- **Open questions:** alert acceptance and timing evidence ownership are resolved in review.
- **Verification case intent:** contract conformance against approved golden scenarios, without a historic comparison route.
- **Check families:** conformance; invariant.
- **Lineage/checkpoint expectations:** consumer view — Dev Malik owns the synthetic evidence checkpoint.
- **Acceptance rules:** approved golden scenarios and invariants pass before Elena Brooks accepts the consumer view.
- **Greenfield boundary:** no current estate, no legacy pipeline, continuity requirement or parity baseline is invented.
- **Decision:** start from approved capabilities and constraints, not a fictional replacement landscape.

## Paired review

- **Paired review:** completed before design.
- **Reviewer:** frame-platform-outcome reviewer.
- **Finding:** alert acceptance authority was missing.
- **Disposition:** resolved — Elena Brooks owns alert acceptance in `EVD-GRN-004`.
- **Finding F-02:** source-latency measure had no evidence owner.
- **Disposition:** resolved — Dev Malik owns fixture timing evidence.

## Acceptance

Elena Brooks accepts the synthetic greenfield frame.
