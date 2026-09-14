# Customer service reporting - outcome
<!-- evorthon-implements: EVD-README-002 -->

## Outcome contract

- **Consumer outcome:** service leaders receive a daily view of demand, response and resolution by 09:00.
- **Success signals:** publication completes by 09:00; declared measures reconcile to the frozen expected output.
- **Success criteria:** {"acceptance_rule":"two accepted synthetic daily publications and Maya Chen's named acceptance are required","check_family":"delivery-integrity","evidence":[{"digest":"digest-evd-mod-006","identifier":"EVD-MOD-006","version":"v1"}],"required_result":"pass","signal":"publication completes by 09:00","validator":{"digest":"digest-publication-timing-validator","identifier":"publication-timing-validator","kind":"validator_specification","version":"v1"}}
- **Success criteria:** {"acceptance_rule":"two accepted synthetic daily publications and Maya Chen's named acceptance are required","check_family":"parity","evidence":[{"digest":"digest-evd-mod-005","identifier":"EVD-MOD-005","version":"v1"}],"required_result":"pass","signal":"declared measures reconcile to the frozen expected output","validator":{"digest":"digest-output-reconciliation-validator","identifier":"output-reconciliation-validator","kind":"validator_specification","version":"v1"}}
- **Scope:** reporting data products and their controls; operational case handling is excluded.
- **Authorities:** Maya Chen is the synthetic sponsor and Ishan Rao owns source-operating evidence.
- **Measures:** publication before 09:00; reconciled case population; response and resolution measures within declared business definitions.
- **Evidence:** `EVD-MOD-001` sponsor interview; `EVD-MOD-002` metric-definition workshop; `EVD-MOD-003` control inventory; `EVD-MOD-005@v1#digest-evd-mod-005` frozen expected output; `EVD-MOD-006@v1#digest-evd-mod-006` publication policy; `publication-timing-validator@v1#digest-publication-timing-validator`; `output-reconciliation-validator@v1#digest-output-reconciliation-validator`.
- **Constraints:** the business-day cut-off and declared metric definitions remain continuous.
- **Open questions:** the synthetic retention policy is resolved before implementation planning.
- **Verification case intent:** snapshot parity against the approved frozen expected daily output.
- **Check families:** parity; delivery integrity.
- **Lineage/checkpoint expectations:** published report @ Ishan Rao owns the reconciliation evidence.
- **Acceptance rules:** two accepted synthetic daily publications and Maya Chen's named acceptance are required.
- **Decision:** preserve the existing business-day cut-off. A declared control replaces manual reconciliation.

## Paired review

- **Paired review:** completed before design.
- **Reviewer:** frame-platform-outcome reviewer.
- **Finding:** retention ownership was not named.
- **Disposition:** resolved: Maya Chen owns the synthetic retention decision in `EVD-MOD-004`.
- **Finding F-02:** consumer acceptance authority was unnamed.
- **Disposition:** resolved: Maya Chen gives named acceptance after the verification record is accepted.

## Acceptance

Maya Chen accepts this synthetic outcome contract on the evidence above.
