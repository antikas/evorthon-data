# Design record — customer service reporting

## Target contract

- **Architecture:** contract-defined ingestion, quality controls, consumer metrics and evidence-linked reconciliation.
- **Operating model:** Ishan Rao triages exceptions and Maya Chen accepts business impact.
- **Contracts:** source identity, timing, population and consumer metric rules are declared.
- **Transition:** introduce source contracts, controls and reconciliation before retiring the manual route after acceptance.
- **Increments:** source contracts, quality controls, metrics, reconciliation and retirement are separately gated.
- **Risks:** an unreconciled publication or premature manual-route retirement is rejected.
- **Acceptance signals:** two accepted synthetic daily publications and named sponsor acceptance are required.
- **Verification case intent:** snapshot parity against the approved frozen expected daily output.
- **Check families:** parity; delivery integrity.
- **Lineage/checkpoint expectations:** published report — Ishan Rao owns the reconciliation evidence.
- **Acceptance rules:** two accepted synthetic daily publications and Maya Chen's named acceptance are required.
- **Evidence:** `EVD-MOD-020` approved outcome contract; `EVD-MOD-021` trace review disposition.
- **Design:** contract-defined ingestion validates source identity and timing; a quality layer measures population and key coverage; a consumer metric layer publishes declared demand, response and resolution measures; a reconciliation control records evidence before release.
- **Continuity:** preserve the business-day cut-off and metric definitions from the frame.
- **Target change:** replace manual population reconciliation with a deterministic, evidence-linked control; retire the synthetic manual route only after acceptance.
- **Decision:** the current-estate trace remains evidence, not a target-schema owner.

## Paired review

- **Paired review:** completed before implementation planning.
- **Reviewer:** design-data-platform reviewer.
- **Finding:** retirement criterion was missing.
- **Disposition:** resolved — retirement requires two accepted synthetic daily publications (`EVD-MOD-022`).
- **Finding D-02:** exception ownership was absent.
- **Disposition:** resolved — Ishan Rao owns exception triage; Maya Chen accepts business impact.

## Acceptance

Maya Chen accepts this target design for the synthetic engagement.
