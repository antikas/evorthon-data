# Implementation plan — renewable asset observability

## Approved increments

- **Package inventory:** five bounded packages below have canonical IDs, owners and validators.
- **Dependency inventory:** dependencies below use package IDs only; Pinax may project them without interpreting prose.
- **Gate inventory:** each package has a stable gate ID and explicit blocking requirement.
- **Exclusions:** production asset feeds and any invented current-estate investigation are outside this synthetic engagement.
- **Acceptance:** each package has a named gate and Elena Brooks authorises the outcome.
- **Evidence:** `EVD-GRN-010` approved frame; `EVD-GRN-011` synthetic asset-event contract; `EVD-GRN-012` escalation policy.
- **Verification case intent:** contract conformance against approved golden scenarios, without a historic comparison route.
- **Check families:** conformance; invariant.
- **Lineage/checkpoint expectations:** consumer view — Dev Malik owns the synthetic evidence checkpoint.
- **Acceptance rules:** approved golden scenarios and invariants pass before Elena Brooks accepts the consumer view.
| Package ID | Summary | Owner | Validator | Depends on | Gate ID | Gate requirement |
| --- | --- | --- | --- | --- | --- | --- |
| asset-event-contract | Approve the asset-event contract | dev-malik | asset-identity-validator | — | asset-event-contract-reviewed | Contract review accepts `EVD-GRN-020`. |
| ingestion-quality | Implement ingestion and quality controls | dev-malik | ingestion-quality-validator | asset-event-contract | ingestion-quality-reviewed | Quality review accepts `EVD-GRN-021`. |
| production-measures | Deliver condition and production measures | elena-brooks | production-measures-validator | ingestion-quality | production-measures-reviewed | Consumer review accepts `EVD-GRN-022`. |
| alert-controls | Implement the approved alert controls | elena-brooks | alert-controls-validator | production-measures | alert-controls-accepted | Alert acceptance confirms `EVD-GRN-012`. |
| consumer-view | Deliver the contract-valid consumer view | elena-brooks | consumer-view-validator | alert-controls | consumer-view-accepted | Named human acceptance accepts `EVD-GRN-023`. |

## Paired review

- **Paired review:** completed before execution.
- **Reviewer:** build-data-platform reviewer.
- **Finding:** the alert increment lacked a failure route.
- **Disposition:** resolved — Dev Malik receives rejected-observation evidence.
- **Finding B-02:** a baseline comparison was implied by a draft validator.
- **Disposition:** resolved — validators test conformance to the approved contract only.

## Acceptance

Elena Brooks authorises these synthetic greenfield increments.
