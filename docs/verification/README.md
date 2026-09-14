# Verifying a data product

A team needs to know whether a candidate data product produces the agreed results, and where differences arise. Evorthon Data compares candidate outputs with expected outputs under rules that the responsible people can read and change before a run.

## Freeze the comparison

A versioned verification case records input, reference and enrichment data, expected outputs, comparison rules and available processing checkpoints. Routine runs use those frozen facts without depending on a live legacy system.

The Python domain contract defines the case format. Its generated [JSON Schema](schemas/verification-domain.schema.json) and [serialization projection](schemas/verification-serialization.json) describe the portable records. Repository checks detect stale projections.

Validation rejects inconsistent records, including unknown schema versions or fields, unresolved or cyclic processing lineage, missing required dataset roles, ambiguous row definitions and contradictory assurance or provenance declarations. A policy already observed by a run can change only in a new case.

## Run the candidate and compare

Environment adapters supply stored evidence and candidate outputs. The engine checks evidence identities and digests, compares actual and expected outputs at declared checkpoints, and reports the earliest confirmed difference.

Where evidence cannot locate a difference exactly, the result identifies the unknown interval. Missing evidence is reported as insufficient evidence; the report retains what could and could not be established.

## Work with synthetic data

A case can use synthetic inputs, reference data or expected outputs. Each synthetic dataset records its generator, seed, constraints and the identities of any datasets used to constrain it. Expected outputs also declare their provenance and any synthetic derivation.

Cases, results and acceptance records show whether evidence is real, mixed or synthetic. A synthetic pass establishes progress against those scenarios. Demonstrating parity with real data requires real evidence.

## Connect evidence and candidate outputs

The adapter kit includes reference implementations using memory or a directory selected by the adopting team. Teams connect their own platforms through the [environment-adapter contract](environment-adapters.md).

Conformance checks compare an adapter's declared capabilities and assurance with its answers. They reject unsupported capabilities or contract versions, missing assurance inputs, invalid values, machine locations and credential patterns. Conformance checks validate digest format; the intake workflow checks the digest against the supplied material.

Portable verification records hold identifiers, fingerprints, counts and approved summaries. The adopting environment controls raw data access, credentials, storage, signing, retention and certification.

## Investigate and accept

A failed comparison can produce a fault packet for diagnostic advice. The [model-access rules](../../ADOPTION-GUIDE.md#model-access) describe the fields the adviser may receive. Its reply remains a proposal and cannot change the case, evidence, tolerances, candidate, tracker or acceptance outcome.

The team records the evidence, failure cases and review findings in its verification record. A named person accepts the result, including any decision to accept synthetic or incomplete evidence. The [integrity rules](../../README.md#checks-and-acceptance) define which conditions refuse an operation.
