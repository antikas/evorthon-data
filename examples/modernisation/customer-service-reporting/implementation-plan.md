# Implementation plan — customer service reporting

## Approved increments

- **Package inventory:** five bounded packages below have canonical IDs, owners and validators.
- **Dependency inventory:** dependencies below use package IDs only; Pinax may project them without interpreting prose.
- **Gate inventory:** each package has a stable gate ID and explicit blocking requirement.
- **Exclusions:** operational case handling and undocumented source changes are outside this plan.
- **Acceptance:** every package has a named gate and the sponsor authorises completion.
- **Evidence:** `EVD-MOD-020` approved outcome contract; `EVD-MOD-021` trace review disposition; `EVD-MOD-022` retirement criterion.
- **Verification case intent:** snapshot parity against the approved frozen expected daily output.
- **Check families:** parity; delivery integrity.
- **Lineage/checkpoint expectations:** published report — Ishan Rao owns the reconciliation evidence.
- **Acceptance rules:** two accepted synthetic daily publications and Maya Chen's named acceptance are required.
| Package ID | Summary | Owner | Validator | Depends on | Gate ID | Gate requirement |
| --- | --- | --- | --- | --- | --- | --- |
| source-contracts | Approve source contracts | ishan-rao | source-identity-validator | — | source-contracts-reviewed | Source owner review accepts `EVD-MOD-030`. |
| ingestion-quality | Implement ingestion quality controls | ishan-rao | ingestion-quality-validator | source-contracts | ingestion-quality-reviewed | Control review accepts `EVD-MOD-031`. |
| consumer-metrics | Deliver declared metrics and consumer view | maya-chen | consumer-metrics-validator | ingestion-quality | consumer-metrics-reviewed | Consumer review accepts `EVD-MOD-032`. |
| reconciliation | Run evidence-linked reconciliation | maya-chen | reconciliation-validator | consumer-metrics | reconciliation-accepted | Verification acceptance accepts `EVD-MOD-033`. |
| route-retirement | Retire the manual route | maya-chen | retirement-validator | reconciliation | route-retirement-accepted | Named human acceptance confirms `EVD-MOD-022` after two accepted publications. |

## Paired review

- **Paired review:** completed before execution.
- **Reviewer:** build-data-platform reviewer.
- **Finding:** the control increment had no failure owner.
- **Disposition:** resolved — Ishan Rao owns failed-control triage.
- **Finding B-02:** retirement could precede verification.
- **Disposition:** resolved — retirement is blocked by the verification-contract acceptance gate.

## Acceptance

Maya Chen authorises the bounded synthetic increments and their gates.
