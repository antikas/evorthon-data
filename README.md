# Evorthon Data Harness

Delivering a data platform means carrying business definitions, design decisions and evidence from discovery through engineering to acceptance. When that work is split across documents and tools, teams spend time reconstructing what was agreed and how to check it.
<!-- evorthon-claim: EVD-README-036 -->

Evorthon Data Harness is a **data engineering harness**: software and a specialist AI coworker that help a team turn a business outcome into reviewed, built and verified data products. It supports both modernising an existing estate and building a new platform.
<!-- evorthon-claim: EVD-README-037 -->

People set the outcome, scope, policies and acceptance rules. Evorthon Data Harness records those decisions, carries them through delivery and retains the evidence for a named person to accept the result.
<!-- evorthon-claim: EVD-README-038 -->

## Delivery example

The included [customer service reporting example](examples/modernisation/customer-service-reporting/outcome-brief.md) starts with service leaders needing a daily view by 09:00. It uses synthetic case, interaction and workforce data, preserving the existing cutoff and metric definitions.
<!-- evorthon-claim: EVD-README-002 -->

Its agreed checks detect missing keys, changed totals and populations that fail to reconcile. The example requires two successful synthetic daily publications before its named sponsor accepts delivery.
<!-- evorthon-claim: EVD-README-003 -->

The engagement follows these stages:
<!-- evorthon-claim: EVD-README-040 -->

1. Record the business outcome, measurable success criteria, scope and decision owners.
<!-- evorthon-claim: EVD-README-004 -->
2. Establish the starting point: the current estate for modernisation, or required capabilities and constraints for a new platform.
<!-- evorthon-claim: EVD-README-005 -->
3. Design the platform and operating model, including the transition and delivery increments.
<!-- evorthon-claim: EVD-README-006 -->
4. Turn the accepted design into tracked work with dependencies and approval points.
<!-- evorthon-claim: EVD-README-007 -->
5. Build in bounded increments. Suitable contracts can generate repeatable outputs from the same approved inputs.
<!-- evorthon-claim: EVD-README-008 -->
6. Configure and run verification, including expected results, failure cases and checkpoints that help locate differences.
<!-- evorthon-claim: EVD-README-009 -->
7. Present the results, review findings and remaining uncertainty to the people responsible for acceptance.
<!-- evorthon-claim: EVD-README-010 -->

The agreed decisions and constraints form a delivery contract that the coworker, tools and reviewers use throughout the work.
<!-- evorthon-claim: EVD-README-041 -->

## Two delivery modes

### Modernise an existing estate

For modernisation, the coworker examines existing processing, data, interfaces and controls. The team identifies behaviour that must continue and agrees a transition in separately accepted increments.
<!-- evorthon-claim: EVD-README-011 -->

### Build a greenfield platform

For greenfield delivery, the team starts with required outcomes, capabilities, constraints and operating needs. The [renewable asset example](examples/greenfield/renewable-asset-observability/outcome-brief.md) follows this route, using approved scenarios to check a new platform.
<!-- evorthon-claim: EVD-README-012 -->

## Delivery workflow

An engagement records who owns the business outcome, source evidence, technical decisions and final acceptance. Those people review the decisions before work enters delivery.
<!-- evorthon-claim: EVD-README-013 -->

Each consumer outcome has a use-case record containing its outputs, inputs, reference data, processing steps, scenarios and versions. An engagement can contain several use cases, each split into packages of build work.
<!-- evorthon-claim: EVD-README-043 -->

The specialist coworker helps gather requirements, draft delivery records and link decisions to evidence. Each generation step has a separate review. The supplied prompts and templates define this role, called the Koine data coworker.
<!-- evorthon-claim: EVD-README-014 -->

Intake starts with existing schemas, extracts, transformations, reports and schedules. Recorded facts identify their source and location, who extracted them, and whether they are extracted, inferred or confirmed. The coworker asks about gaps left by that material.
<!-- evorthon-claim: EVD-README-044 -->

Model calls require authorization from the adopting environment. Intake may send a bounded sample of permitted artefact text; independent review receives recorded facts and references. Diagnostic advice remains text for a person to assess. The [adoption guide](ADOPTION-GUIDE.md#model-access) explains each route and its limits.
<!-- evorthon-claim: EVD-README-050 -->

Readiness is calculated for each span of processing, called a segment. Its output definition must specify fields, what one row represents and identifying keys. Other missing facts receive labelled substitutes or tracked follow-up work, allowing ready segments to proceed.
<!-- evorthon-claim: EVD-README-045 -->

The work tracker holds dependencies, readiness, claims and completion. Evorthon Data Harness uses the separately released Pinax tracker for this shared operational record.
<!-- evorthon-claim: EVD-README-015 -->

Pinax shares state changes through Git. It reads shared state before claiming work and refuses a claim that loses a race with another worker.
<!-- evorthon-claim: EVD-README-046 -->

Two further tools support delivery: Ergasterion generates outputs from suitable contracts, and AutoBuild runs eligible work through build and review cycles. Evorthon Data Harness connects to their released packages through narrow adapters.
<!-- evorthon-claim: EVD-README-016 -->

Verification begins when the team defines success, evidence ownership and failure conditions. The product provides the comparison engine; platform delivery includes the contracts, checks and environment adapters needed to use it.
<!-- evorthon-claim: EVD-README-017 -->

A named person accepts delivery with its check results and review findings attached. A model cannot accept its own work.
<!-- evorthon-claim: EVD-README-018 -->

Acceptance can cover one segment. The version records included outputs, scenarios, data provenance and excluded work. An accepted intermediate product can then serve another use case.
<!-- evorthon-claim: EVD-README-047 -->

## Verification

A verification case freezes the inputs, reference data, expected outputs, comparison rules and available checkpoints for a run. The responsible people can read and change those rules before running the case.
<!-- evorthon-claim: EVD-README-019 -->

Where data is missing, the team can generate synthetic datasets with recorded seeds and constraints. Cases, results and acceptance records retain that label. Passing synthetic checks establishes progress against those scenarios; demonstrating parity with real data requires real evidence.
<!-- evorthon-claim: EVD-README-048 -->

The engine runs the candidate against frozen evidence, compares actual and expected outputs, and reports the earliest confirmed difference. Gaps between checkpoints remain explicitly unknown. Routine verification works without a live legacy system.
<!-- evorthon-claim: EVD-README-020 -->

Portable verification records hold identifiers, fingerprints, counts and approved summaries. The adopting environment owns raw data access, credentials, storage, signing, retention and certification.
<!-- evorthon-claim: EVD-README-021 -->

A failed comparison produces a fault record naming the affected checkpoint and supporting evidence. A diagnostic adviser may propose a correction. It cannot change tolerances, replace evidence, execute work or accept the outcome.
<!-- evorthon-claim: EVD-README-022 -->

## Checks and acceptance

- People set and can inspect the outcome, scope, policies, tolerances and acceptance rules.
<!-- evorthon-claim: EVD-README-023 -->
- Generation and review are separate. A named authority resolves or accepts review findings.
<!-- evorthon-claim: EVD-README-024 -->
- Approved work enters the tracker before execution, with an explicit scope.
<!-- evorthon-claim: EVD-README-025 -->
- Tests cover successful cases and deliberate failures to check that defects are detected.
<!-- evorthon-claim: EVD-README-026 -->
- Verification reports evidence gaps and uncertainty for human acceptance.
<!-- evorthon-claim: EVD-README-027 -->
- Readiness, provenance and assurance inform decisions. People may accept synthetic or incomplete evidence. Integrity checks refuse contradictory records, mismatched evidence digests, stored credentials, actors of the wrong kind and changes to immutable records.
<!-- evorthon-claim: EVD-README-049 -->

Comparison results come from deterministic checks against the case's declared rules.
<!-- evorthon-claim: EVD-README-042 -->

## Scope and limits

Evorthon Data Harness is specific to data-platform delivery.
<!-- evorthon-claim: EVD-README-028 -->

The adopting team chooses its cloud, processing engine, storage and target architecture.
<!-- evorthon-claim: EVD-README-029 -->

Platform engineers, data owners, security teams and operators remain responsible for their decisions and the delivered platform.
<!-- evorthon-claim: EVD-README-030 -->

Live connections, credentials, protected data and certified evidence stores remain under the adopting environment's control. Connecting them requires environment-owned adapters. The synthetic examples provide no certification of a live platform.
<!-- evorthon-claim: EVD-README-031 -->

## For engineers

Start with the [adoption guide](ADOPTION-GUIDE.md) and a [worked example](examples/INDEX.md). The [architecture record](docs/architecture/solution-architecture.md) explains component responsibilities. The [coworker pack](koine/INDEX.md) contains the method, prompts and templates.
<!-- evorthon-claim: EVD-README-032 -->

The Python package requires Python 3.11 or later. Optional delivery dependencies provide the tracker, generator and build runner; their declared minimum versions follow the interfaces this product uses.
<!-- evorthon-claim: EVD-README-033 -->

Use `evorthon-data-harness diagnose` to inspect installed delivery capabilities. To run the repository's fast checks with [uv](https://docs.astral.sh/uv/):
<!-- evorthon-claim: EVD-README-034 -->

```text
uv run --locked --group dev python scripts/run_tests.py --lane fast
```

To check that a downloaded public copy matches its published file list, run:
<!-- evorthon-claim: EVD-README-035 -->

```text
python scripts/check_public_candidate.py
```

Implementation and test references are checked for consistency.
<!-- evorthon-claim: EVD-README-039 -->

See [capabilities and evidence](docs/product/capability-status.md) for implementation and test references.
<!-- evorthon-claim: EVD-README-001 -->
