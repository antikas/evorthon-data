# Adopting Evorthon Data Harness
<!-- evorthon-implements: EVD-README-032 -->

Start with a report, dataset or consumer view whose success you can describe and check. Gather the material that explains it and involve the people who can decide what should change.

Evorthon Data Harness provides a specialist AI coworker, delivery records and Python tools for recording and verifying the work. Adapters connect it to separately released delivery tools. The adopting team supplies platform access, model authorization and the people who accept the result.

## Work through an example

Choose the [customer service reporting example](examples/modernisation/customer-service-reporting/outcome-brief.md) for an existing estate, or the [renewable asset example](examples/greenfield/renewable-asset-observability/outcome-brief.md) for a new platform. Both use synthetic data and named fictional decision owners.

Read the outcome brief first, then follow the records in that example's directory through discovery, design, implementation planning and verification. Use them to understand what a completed record contains before adapting the [templates](koine/templates/) to your own work.

## Prepare the first use case

1. Name the consumer and the output they need. Record how often they need it, what success means and who can accept delivery.
2. Gather existing schemas, data extracts, transformations, reports, schedules and catalogue exports. Facts recorded from them retain their source and whether they are extracted, inferred or confirmed.
3. Define the output's fields, what each row represents and its identifying keys. These are the minimum facts needed to assess a segment of processing for build readiness.
4. Name the people responsible for source evidence, technical decisions, policies and acceptance. Record unresolved questions and constraints alongside the outcome.

For modernisation, document the current estate and the behaviour that must continue. For greenfield delivery, do not simply skip discovery: document required capabilities and constraints in a reviewed capability-discovery record. Both routes then produce a platform design, implementation plan, delivery contract and verification record.

Missing data can be filled with labelled synthetic datasets. Readiness is calculated per segment, so another segment's missing facts need not stop ready work. Acceptance records show what was covered, what evidence was used and what remains outside the accepted version.

## Use the coworker and delivery tools

The [Koine coworker pack](koine/INDEX.md) provides prompts and templates for the delivery conversation. A generation prompt drafts a record; a separate reviewer challenges it. People resolve the findings and approve the decisions.

Pinax holds work state and dependencies, while Ergasterion generates outputs from suitable contracts. Eligible, approved work can run through build and review cycles in AutoBuild. The [dependency contracts](docs/dependency-contracts.md) describe how Evorthon Data Harness connects to those separately released tools.

Use Python 3.11 or later in a virtual environment. From the root of a repository checkout, install the package and its delivery tools:

```text
python -m pip install ".[delivery]"
```

Inspect the available commands and delivery dependencies:

```text
evorthon-data-harness diagnose
evorthon-data-harness use-case --help
evorthon-data-harness verification --help
```

## Model access

Every model call passes through an authorization gateway. A call requires current, unrevoked authorization issued by your environment for the case, purpose, route, destination and exact fields. It also names the data class, retention policy and evidence policy.

A provider credential alone does not authorize sending material. The people responsible for model access control both the authorization and the provider account. They can inspect the permitted fields before use.

### Intake

The generator call carries the use-case identity, engagement mode, open questions, confirmed answers and admitted artefact references. Each reference includes its identity, version, digest, handling classification and logical location within the source.

It may also carry a bounded sample of artefact text, limited by a declared number of rows and characters. Text crosses only when its handling classification is permitted by the authorization's field scope. A small artefact may fit entirely within those limits.

For higher classifications, the round uses the digest and recorded facts without sending artefact text. Each round reports the amount sent for each artefact or the reason its text was withheld.

### Independent review

The review call carries recorded facts, their provenance, and artefact identities and digests. It carries no artefact text at any classification.

### Diagnostic advice

The diagnostic adviser receives declared text fields and evidence identities from a fault packet that has passed the privacy check. It receives no raw rows, keys, field values or approved case text.

The reply is stored as an inert advice record for a person to read. The product does not execute, apply or forward the reply.

### Source references and connection details

A logical locator names an artefact and a position within it. Connection details belong in your environment's configuration. The record refuses a locator containing any of these machine-location forms:

- an address under any scheme
- a path from the root of a machine
- a lettered volume
- a share host
- a written home directory
- a climb out of where it starts
- a path written with a machine path's separator

The same forms are refused in fault packets and tracker notes. The record admits a locator that reads like a dotted server name followed by a path or a port, or like a connection string. The intake round reports a warning on it.

These forms need human review because a dotted name cannot be told from an ordinary written name by the pattern check. The warning leaves the locator admitted. Keep actual connection details in environment configuration.

Credential-shaped patterns are refused before an artefact is admitted. These checks recognise declared patterns; they do not establish that arbitrary text contains no sensitive information. Review the material and authorize only the fields and samples suitable for your model provider.

## Connect your environment

Two adapter contracts connect verification to your material: one reads stored evidence and one produces candidate outputs. The adopting team implements the code that accesses its platform. Reference adapters can read values held in memory or material in a directory you select.

Each adapter declares its capabilities and the evidence supporting its answers. A conformance suite checks those declarations against the contract, including unsupported capabilities, missing assurance inputs, invalid values, machine locations and credential patterns.

Access, capture, credentials, signing, retention and certification belong to your environment. The [environment-adapter contract](docs/verification/environment-adapters.md) describes the interfaces and their conformance checks.

## Verify and accept

Agree the comparison rules and expected results before the run. The [verification engine](docs/verification/README.md) compares candidate outputs against frozen evidence and reports confirmed differences and evidence gaps.

A named person decides whether the result is acceptable, including when evidence is synthetic or incomplete. Keep live organisational evidence, review records, credentials and operational work state in your team's environment.
