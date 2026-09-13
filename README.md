# Evorthon Data

Data platform delivery is often split across discovery, architecture, engineering, verification, governance and handover. Each group works through its own documents and tools, which slows decisions and loses context between stages. AI can speed up individual tasks while leaving that delivery system unchanged.
<!-- evorthon-claim: EVD-README-036 -->

Evorthon Data is an end-to-end AI coworker and delivery platform for modernising an existing data estate or building a new one. It combines a specialist data coworker with governed delivery tooling so a team can move from a business outcome to an accepted platform at AI-era speed.
<!-- evorthon-claim: EVD-README-037 -->

People remain in control. They set the outcome, boundaries, policies, evidence requirements and acceptance rules. Evorthon Data makes those decisions explicit, applies them through delivery and retains the evidence needed for human acceptance.
<!-- evorthon-claim: EVD-README-038 -->

This README defines the product boundary and required behaviour. The implementation and its verification evidence must support every claim below.
<!-- evorthon-claim: EVD-README-039 -->

> **Build status.** This is the binding product contract, not a claim that every capability is already available. The [capability status guide](docs/product/capability-status.md) explains the status terms, and the [claim registry](docs/product/readme-claim-registry.toml) maps each stable claim identifier to its current implementation and evidence state. A claim the registry marks **in development** is approved product behaviour that is not yet shipped; no claim carries that mark today.
<!-- evorthon-claim: EVD-README-001 -->

## What you can watch it do

The included [customer service modernisation example](examples/modernisation/customer-service-reporting/outcome-brief.md) begins with service leaders needing a trusted daily view by 09:00. It traces separate case, interaction and workforce feeds, preserves the existing cutoff and metric definitions, and replaces manual reconciliation with a deterministic control.
<!-- evorthon-claim: EVD-README-002 -->

Verification blocks publication when a key is missing, an aggregate changes or the population does not reconcile. A named sponsor accepts the delivery only after two synthetic daily publications meet the agreed checks.
<!-- evorthon-claim: EVD-README-003 -->

A complete Evorthon Data engagement:
<!-- evorthon-claim: EVD-README-040 -->

1. Defines the business outcome, measurable signals, scope and decision authorities.
<!-- evorthon-claim: EVD-README-004 -->
2. Establishes the starting point. A modernisation maps the current estate and continuity needs; a greenfield delivery records capabilities and constraints without inventing a legacy estate.
<!-- evorthon-claim: EVD-README-005 -->
3. Designs the target platform, operating model, transition and delivery increments.
<!-- evorthon-claim: EVD-README-006 -->
4. Converts the accepted design into an executable work graph with visible dependencies and gates.
<!-- evorthon-claim: EVD-README-007 -->
5. Builds the platform through bounded increments. Where the contract supports exact generation, the same approved input produces the same declared artefact.
<!-- evorthon-claim: EVD-README-008 -->
6. Builds and runs the verification engine needed for that platform, including checks, fixtures, evidence paths, fault localisation and acceptance gates.
<!-- evorthon-claim: EVD-README-009 -->
7. Presents machine evidence, review findings and remaining uncertainty to the named people who accept the outcome.
<!-- evorthon-claim: EVD-README-010 -->

The delivery contract keeps these stages aligned. It records decisions and constraints so the coworker, tools, reviewers and people work from the same approved intent.
<!-- evorthon-claim: EVD-README-041 -->

## Two delivery modes

### Modernise an existing estate

The coworker traces the current processing, data, interfaces, controls and operational constraints before proposing a target. It separates continuity needs from accidental legacy behaviour, then defines a safe transition in independently accepted increments.
<!-- evorthon-claim: EVD-README-011 -->

### Build a greenfield platform

The coworker begins with the required outcomes, capabilities, constraints and operating model. It creates no fictional current estate or parity requirement. The platform is designed and delivered in independently accepted increments from the start.
<!-- evorthon-claim: EVD-README-012 -->

## How delivery works

An engagement begins with the people who own the business outcome, source evidence, technical decisions and final acceptance. Their decisions are recorded in plain, reviewable form before work enters delivery.
<!-- evorthon-claim: EVD-README-013 -->

An engagement holds many use cases. A use case carries one consumer outcome with its target outputs, inputs and reference data, a lineage draft with named intermediate results, its scenarios, authorities, conditions and versions. It is the unit of intake, readiness, build and acceptance, and packages remain the unit of build work inside it.
<!-- evorthon-claim: EVD-README-043 -->

The specialist AI coworker interviews those people, creates the required delivery records, keeps decisions linked to evidence and pairs every generation step with an independent review. It maintains the delivery conversation from outcome framing through design, build, verification and acceptance. This is the Koine data coworker.
<!-- evorthon-claim: EVD-README-014 -->

Intake works from the artefacts a team already has. The coworker reads schemas, data extracts, transformations, reports, schedules and catalogue exports with its ordinary file, data and query tools, and asks only the questions those artefacts leave open. Every recorded fact names the artefact it came from, its position inside that artefact, the actor that extracted it, and whether it is extracted, inferred or confirmed. No parser or import adapter is built for an artefact shape that is not in hand.
<!-- evorthon-claim: EVD-README-044 -->

Every model call travels through one authorization gateway, and what each route carries is declared. A generation or review call carries record identities, digests, declared facts and the questions still open. A locator among them is logical, naming the artefact and the position inside it: the record refuses a locator that carries an address under any scheme, a path from the root of a machine, a lettered volume, a share host, a written home directory, a climb out of where it starts, or a path written with a machine path's separator. A locator that reads like a dotted server name followed by a path or a port, or like a connection string, is admitted and the round reports a warning on it, because a dotted name cannot be told from an ordinary written name. Connection details belong in the adopting environment's configuration and not in a record, and a locator that reads like one is admitted with a warning rather than refused. On the intake route an admitted artefact's text crosses only as a bounded sample, cut to a declared number of rows and characters, and only where the artefact's handling classification is at or below the level the authorization's field scope names. A higher classification crosses no text at all, and the round continues on that artefact's digest and the record. The round reports how much of each artefact crossed and the closed reason where none of it did. The independent review route carries no artefact text at any classification. The diagnostic adviser is the third route that calls a model, and it carries only the declared text fields of a fault packet the privacy gate has already passed, together with the two lists of evidence identities that packet cites. Its reply is recorded as inert text, so nothing in the product executes, applies or forwards it.
<!-- evorthon-claim: EVD-README-050 -->

Readiness is computed from those facts rather than kept by hand, and it is computed for each segment of the lineage, meaning a span from available inputs to a declared output or checkpoint. A segment needs only its own facts, and the one fact it cannot do without is the definition of its output: schema, grain and keys. Every other missing fact has a labelled substitute or becomes tracked work under the use case, so a use case is never blocked as a whole and whatever is buildable is built.
<!-- evorthon-claim: EVD-README-045 -->

Accepted work enters a live work graph. Dependencies, readiness, claims, gates and completion stay visible there, while durable product knowledge remains in its owning documents. Pinax owns this operational state.
<!-- evorthon-claim: EVD-README-015 -->

Every change to that state is recorded and shared as it is made, so a claim, a completion or a new item is visible on every machine at once without a coordinator in between. A claim reads the shared state first, and a claim that loses a race is reported and refused rather than silently overwritten.
<!-- evorthon-claim: EVD-README-046 -->

Approved work can then use deterministic generation and autonomous engineering. Ergasterion generates declared artefacts from suitable contracts. AutoBuild executes eligible work through bounded build, review and acceptance cycles. Both remain separately released tools with their own responsibilities.
<!-- evorthon-claim: EVD-README-016 -->

Verification starts during framing because the team defines success signals, evidence ownership and failure conditions before implementation. Evorthon Data provides the portable comparison core and builds the contracts, checks and environment adapters required by the platform.
<!-- evorthon-claim: EVD-README-017 -->

Named people accept the result after the deterministic checks and independent reviews complete. The system records their decision and the evidence that supported it. A model recommendation cannot accept its own work.
<!-- evorthon-claim: EVD-README-018 -->

A version is an acceptance boundary and may cover a single buildable slice. Every acceptance record states which segments and outputs the version covers, which scenarios ran and on what kind of data, and which segments stay outside it. Consumers work with accepted products rather than versions, so an accepted intermediate product is available to another use case as soon as it is accepted.
<!-- evorthon-claim: EVD-README-047 -->

## Verification is part of the delivery

The verification engine is built around an approved, versioned verification case. The case freezes input, reference and enrichment data, expected output, comparison rules, and lineage or checkpoint evidence. Its owners can read and change those rules before a run.
<!-- evorthon-claim: EVD-README-019 -->

Where real inputs, reference data or expected output are not available, a case can be filled with synthetic data generated to the declared schema, grain and keys and constrained by whatever real data exists. Such a dataset is stored like any other frozen dataset, labelled synthetic and carrying its seed, the generator that produced it and the constraints it honoured. A pass against a synthetic oracle is labelled progress on the case, the result and the acceptance record, and is never presented as parity with real data. A complete build on synthetic data before a final run on real data is a normal route, and so is a delivery whose real data never arrives.
<!-- evorthon-claim: EVD-README-048 -->

Routine verification runs the candidate only and never depends on a live legacy route. It validates supplied evidence, independently confirms the candidate's input and context identities, reconciles actual and expected output at each declared checkpoint, and reports the earliest confirmed difference. Missing evidence leaves the space between the last confirmed match and first observed difference explicitly unknown.
<!-- evorthon-claim: EVD-README-020 -->

Portable verification records contain identifiers, cryptographic fingerprints, counts and approved summaries. Raw rows, credentials, private values and platform locations remain inside the adopting environment. Environment adapters own access, storage, signing, retention and any certification claim.
<!-- evorthon-claim: EVD-README-021 -->

A failed comparison produces a small, safe fault record with the affected checkpoint, diagnostic scope, supporting evidence and possible correction surface. Advice remains a proposal. It cannot alter tolerances, replace evidence, run work or accept an outcome.
<!-- evorthon-claim: EVD-README-022 -->

## What keeps it honest

- People set the outcome, boundaries, policies, tolerances and acceptance rules. Those decisions remain readable and changeable.
<!-- evorthon-claim: EVD-README-023 -->
- Generation and review are separate steps. Review findings must be resolved or accepted by a named authority.
<!-- evorthon-claim: EVD-README-024 -->
- Approved work is visible in the work graph before execution. Tools cannot silently enlarge the scope.
<!-- evorthon-claim: EVD-README-025 -->
- Deterministic checks include cases that must pass and deliberately failing cases that prove the failure path works.
<!-- evorthon-claim: EVD-README-026 -->
- Verification reports evidence gaps and uncertainty explicitly. Human acceptance follows the evidence.
<!-- evorthon-claim: EVD-README-027 -->
- Readiness, provenance and assurance are reported as labels and suggestions, never as policy gates that block progress. Only integrity checks fail closed: a record that contradicts itself, evidence that does not match its digest, a credential inside a stored artefact, an actor of the wrong kind, and a change to a record that is immutable. Accepting on synthetic or incomplete evidence is a named person's decision, recorded with the evidence it rested on.
<!-- evorthon-claim: EVD-README-049 -->

The checks do the trusting. Intentions and model confidence do not replace them.
<!-- evorthon-claim: EVD-README-042 -->

## What this is not

Evorthon Data is specific to data platforms. A future generic delivery product may reuse the method, but it is outside this product boundary.
<!-- evorthon-claim: EVD-README-028 -->

It does not impose one cloud, processing engine, storage product or target architecture. The adopting team selects technologies and owns the controls in its environment.
<!-- evorthon-claim: EVD-README-029 -->

It does not replace platform engineers, data owners, security teams, operators or acceptance authorities. The coworker and tools increase their delivery capacity while keeping their decisions visible.
<!-- evorthon-claim: EVD-README-030 -->

It does not move raw enterprise evidence into the portable product. Live connections, credentials, protected data and certified evidence stores stay under the adopting environment's control.
<!-- evorthon-claim: EVD-README-031 -->

## For engineers

Start with the [adoption guide](ADOPTION-GUIDE.md), then choose a [modernisation or greenfield example](examples/INDEX.md). The [architecture record](docs/architecture/solution-architecture.md) describes component ownership and the controlled delivery route. The [Koine projections](koine/INDEX.md) make the coworker records readable.
<!-- evorthon-claim: EVD-README-032 -->

Evorthon Data is a Python 3.11+ distribution. Pinax, AutoBuild and Ergasterion are consumed as released Python packages. The lock records the versions tested for a build; each delivery dependency declares a floor and no upper bound, and a floor rises only when the product calls a newer interface.
<!-- evorthon-claim: EVD-README-033 -->

Run `evorthon-data diagnose` to inspect installed dependency capabilities. Repository contributors can install [uv](https://docs.astral.sh/uv/) and run:
<!-- evorthon-claim: EVD-README-034 -->

```text
uv run --locked --group dev python scripts/run_tests.py --lane fast
```

A public candidate is independently checked with the command below. The check reads a finalized inventory, which publication writes, so it runs on a published candidate as it stands; a candidate that has not reached publication still carries a provisional inventory and is checked by adding `--allow-provisional`.
<!-- evorthon-claim: EVD-README-035 -->

```text
python scripts/check_public_candidate.py
```
