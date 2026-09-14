# Capabilities and evidence
<!-- evorthon-implements: EVD-README-001 -->

A technical assessment needs to distinguish the product's own capabilities from the work an adopting team must supply. Evorthon Data Harness includes the coworker pack, engagement and use-case records, readiness calculation, synthetic data generation, verification engine, acceptance records and environment-adapter kit.

Its delivery adapters connect to the separately released tracker, generator and build runner. The adopting team supplies platform access, model authorization, protected data handling, evidence storage and any certification.

## Inspect the evidence

The [claim registry](readme-claim-registry.toml) connects stable references in the [README](../../README.md) to implementation files and focused tests. It stores those relationships without copying the claim text. Use it to find the code and checks supporting a capability you need to assess.

Repository validation checks that every marked claim has a registry entry, that its state is consistent, and that its references resolve to matching implementation and test markers. This check validates traceability; assessing a claim also requires reading its implementation and evidence.

## Registry terms

- **Available** means the repository contains the capability and the registry names implementation and focused verification references.
- **In development** means the behaviour is approved product scope but is not yet an available capability.
- **Environment owned** means the registry describes an external responsibility or context. This includes adopter controls, separately released tools and the delivery situation described in the introduction.

## Interpret the verification results

The [verification guide](../verification/README.md) explains frozen cases, comparisons and evidence gaps. Both [worked examples](../../examples/INDEX.md) exercise the delivery route using synthetic material.

Synthetic evidence remains labelled on cases, results and acceptance records. A successful synthetic run supports the declared scenario; it provides no certificate for a live platform. A named person decides whether the available evidence is sufficient for acceptance.

Readiness, provenance and assurance inform that decision. The [README](../../README.md#checks-and-acceptance) states the integrity conditions that refuse a record or operation.

## Check a public copy

Run `python scripts/check_public_candidate.py` from a public checkout to validate its contents against the published inventory.
