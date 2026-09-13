# Capability status
<!-- evorthon-implements: EVD-README-001 -->

Evorthon Data is in an approved product-build programme. The README remains the binding product contract; this page says what each claim's status means and where a claim's boundary lies.

## Status terms

- **Available** means the repository contains the stated capability and a focused check named by the claim registry verifies it.
- **In development** means the behaviour is approved product scope but is not yet an available capability. It has no implementation or verification reference in the registry until that changes.
- **Environment owned** means the product intentionally does not provide the stated capability. It sits outside the product boundary: the adopting environment or a separately released tool owns it, or the claim describes the delivery situation a team already has. The product must not imply otherwise.

The available surface is the whole delivery route. It carries the specialist co-worker pack and its templates, the governed engagement lifecycle, the use-case record with its per-segment readiness, artefact-first intake, synthetic dataset generation, version cutting and named acceptance, the narrow routes to the released tracker, generator and build tools, the deterministic verification engine with its intake, reconciliation, localisation, replay, delivery-contract and remediation steps, the diagnostic adviser, the environment-adapter kit, dependency diagnostics, repository checks and private-to-public projection machinery. Both shipped examples run that route end to end on frozen synthetic material.

Every claim the product provides is available and carries its implementation and evidence references in the [claim registry](readme-claim-registry.toml). No claim carries the in-development mark today.

The claims outside the product boundary are environment owned. EVD-README-029 and EVD-README-031 keep technology selection, live connections, credentials, protected data and certified evidence stores inside the adopting environment. EVD-README-046 describes shared tracker state, which the released Pinax distribution owns and this product never copies into a store of its own. EVD-README-028 places a generic delivery product outside this boundary, and EVD-README-036 describes the split delivery system a team already has before it adopts the product.

The claim registry is relational: it records only stable README identifiers, states and implementation/evidence references. It deliberately does not restate the product claims. This keeps the README as their single textual source.

Two claims bound what an available implementation may do: EVD-README-049 names the classes that fail closed, and EVD-README-045 governs how readiness is computed. The README remains the single textual source for both rules.

The verification engine rests on a versioned, frozen verification case. Deterministic code reconciles actual and expected outputs and reports the evidence-supported divergence; an AI adviser may propose a remedy but a person remains responsible for deciding whether it enters delivery.
