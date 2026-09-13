# Design record — renewable asset observability

## Target contract

- **Architecture:** source contracts, quality checks, observability measures and alert controls form the target design.
- **Operating model:** Dev Malik owns rejected-observation evidence and Elena Brooks owns consumer acceptance.
- **Contracts:** asset identity, event-time, measurement range, metric and alert-severity rules are explicit.
- **Transition:** accept bounded contract, quality, measure, alert and view increments without a legacy cutover or parity route.
- **Increments:** contracts, quality, measures, alerts and consumer view are independently gated.
- **Risks:** unknown identity, invalid range and unowned severity stop publication.
- **Acceptance signals:** contract-valid observations, explainable alerts and named consumer approval are required.
- **Verification case intent:** contract conformance against approved golden scenarios, without a historic comparison route.
- **Check families:** conformance; invariant.
- **Lineage/checkpoint expectations:** consumer view — Dev Malik owns the synthetic evidence checkpoint.
- **Acceptance rules:** approved golden scenarios and invariants pass before Elena Brooks accepts the consumer view.
- **Evidence:** `EVD-GRN-010` approved frame; `EVD-GRN-011` synthetic asset-event contract.
- **Design:** source contracts establish asset identity and event time; quality checks reject unknown identity and invalid measurement ranges; an observability layer produces condition and production measures; alert controls record the rule and recipient decision.
- **Constraints:** all records are synthetic, consumer metrics are contract-owned, and no legacy schema is treated as a design input.
- **Decision:** asset identity is the join authority; alert severity is a declared consumer policy.

## Paired review

- **Paired review:** completed before implementation planning.
- **Reviewer:** design-data-platform reviewer.
- **Finding:** alert escalation evidence was missing.
- **Disposition:** resolved — `EVD-GRN-012` records the synthetic escalation policy.
- **Finding D-02:** quality disposition was not explicit.
- **Disposition:** visible disposition — invalid observations are rejected and reported to Dev Malik.

## Acceptance

Elena Brooks accepts the greenfield target design.
