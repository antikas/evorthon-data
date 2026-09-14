# Use-case intake

One record per use case, sixteen blocks. Read the artefacts first and ask only what no artefact answers. Repeat a block for every item it holds, one target output, one dataset, one step, one scenario, one authority, one segment at a time.

Every recorded value carries the artefact it was read from, the position inside that artefact, who or what extracted it, and whether it is extracted, inferred or confirmed. Record each unanswered field as a gap. A block can be answered partly and revisited later.

## 1. Outcome and consumer

Who consumes this use case, what decision or process it serves, how often it must arrive, and what done means in the consumer's own words.

- **Engagement identity:**
- **Engagement mode:**
- **Consumer:**
- **Outcome:**
- **Done definition:**
- **Cadence:**
- **Deadline:**
- **Artefact:**
- **Position in artefact:**
- **Extracted by:**
- **Fact status:**

## 2. Target outputs

What correct looks like. Repeat for each target output. A modernisation use case names the output it replaces and where that output lives; a greenfield use case names the specification or golden example that defines it and leaves the replaced output empty.

- **Output identity:**
- **Output kind:**
- **Schema:**
- **Grain:**
- **Keys:**
- **Output cadence:**
- **Cutoff semantics:**
- **Effective-time semantics:**
- **Stored name:**
- **Stored column names:**
- **Replaced output:**
- **Defining specification:**
- **Artefact:**
- **Position in artefact:**
- **Extracted by:**
- **Fact status:**

## 3. Inputs

Repeat for each input dataset. Availability says whether a frozen extract is in hand, expected by a date, absent or filled with labelled synthetic data. Record an absent input as a fact.

- **Dataset identity:**
- **Dataset role:**
- **Source system:**
- **Delivery mode:**
- **Dataset cadence:**
- **Access owner:**
- **Classification:**
- **Availability:**
- **Obtainable by:**
- **Artefact:**
- **Position in artefact:**
- **Extracted by:**
- **Fact status:**

## 4. Reference and enrichment data

Use the same fields as an input, with the role naming the reference or enrichment data. Record temporal changes and output dependence on the active version as residual questions. Keep each question in the gap list until a field exists.

- **Dataset identity:**
- **Dataset role:**
- **Source system:**
- **Delivery mode:**
- **Dataset cadence:**
- **Access owner:**
- **Classification:**
- **Availability:**
- **Obtainable by:**
- **Artefact:**
- **Position in artefact:**
- **Extracted by:**
- **Fact status:**

## 5. Intermediate steps

The named steps between the inputs and the outputs, in the words a human recognises. Each named step is a checkpoint candidate with an owner for the evidence at that point. A modernisation use case also labels each step continuity or accident, and may take an expected value from a capture of the old run.

- **Step identity:**
- **Step description:**
- **Evidence owner:**
- **Checkpoint candidate:**
- **Expected value origin:**
- **Continuity or accident:**
- **Artefact:**
- **Position in artefact:**
- **Extracted by:**
- **Fact status:**

## 6. Scenarios

The normal case first, then late-arriving rows, missing keys, duplicates, corrections and restatements, period boundaries, empty inputs and a reference-data version change. Each scenario is one case held by identity and version. The case registry owns the frozen inputs, expected output and output origin. This record carries the case identity and version.

- **Scenario case identity:**
- **Scenario case version:**
- **Artefact:**
- **Position in artefact:**
- **Extracted by:**
- **Fact status:**

## 7. Comparison policy

Declare exact comparisons or tolerances per column and aggregate, ordering, formatting, exclusions with their reasons and control totals. The named case owns the comparison rules. This block records the case identity and version.

- **Scenario case identity:**
- **Scenario case version:**
- **Artefact:**
- **Position in artefact:**
- **Extracted by:**
- **Fact status:**

## 8. Authorities

Who accepts the use case, who owns the evidence for a named subject, and who resolves ambiguity. Repeat for each authority. An accepting authority and an ambiguity resolver are named humans.

- **Authority role:**
- **Authority actor:**
- **Authority subject:**
- **Artefact:**
- **Position in artefact:**
- **Extracted by:**
- **Fact status:**

## 9. Build route

Per segment, whether it is generated from a declaration, engineered as an approved item of work, or already exists. A generated segment names the product domain it generates into.

- **Segment identity:**
- **Build route:**
- **Target shape:**
- **Layer:**
- **Product domain:**
- **Artefact:**
- **Position in artefact:**
- **Extracted by:**
- **Fact status:**

## 10. Classification and handling

A standing condition is asked once and may be answered at any time. Record the default for an unanswered condition; a named human may override it. This block also records every artefact intake read with its identity, digest, classification and logical locator. Handle an unknown classification as confidential.

- **Handling classification:**
- **Data owner:**
- **Data steward:**
- **Permitted purpose:**
- **Residency:**
- **Non production masking:**
- **Evidence visibility:**
- **Intake artefact identity:**
- **Intake artefact classification:**
- **Intake artefact locator:**
- **Artefact:**
- **Position in artefact:**
- **Extracted by:**
- **Fact status:**

## 11. History and time

Ask once and accept answers at any time. Record the default for an unanswered condition.

- **Retention window:**
- **Backfill depth:**
- **As of reproducibility:**
- **Historisation kind:**
- **Slowly changing attributes:**
- **Restatement handling:**
- **Archive or online:**
- **Erasure obligation:**
- **Artefact:**
- **Position in artefact:**
- **Extracted by:**
- **Fact status:**

## 12. Freshness and operations

Ask once and accept answers at any time. These answers become the operational evidence the consumer expects and the runtime settings the build uses.

- **Freshness deadline:**
- **Missed deadline response:**
- **Reconciliation controls:**
- **Operational owner:**
- **Monitoring:**
- **Checkpoint granularity:**
- **Max retries:**
- **Backoff:**
- **Artefact:**
- **Position in artefact:**
- **Extracted by:**
- **Fact status:**

## 13. Volume and performance

Ask once and accept answers at any time. A declared cost ceiling requires its own scenario.

- **Load volume:**
- **Growth and peaks:**
- **Query pattern:**
- **Cost ceiling:**
- **Artefact:**
- **Position in artefact:**
- **Extracted by:**
- **Fact status:**

## 14. Access and consumption

Ask once and accept answers at any time. The adopting environment owns access rules; record their identities here. This block also pins each consumed product to its providing use case and major version, records fields that may be empty, and records source-combination methods, merge keys and retained rows.

- **Consumption route:**
- **Authentication and authorisation:**
- **Row or column restrictions:**
- **Downstream consumers:**
- **Providing use case:**
- **Consumed product:**
- **Consumed major version:**
- **Source combination:**
- **Consumed field nullability:**
- **Artefact:**
- **Position in artefact:**
- **Extracted by:**
- **Fact status:**

## 15. Quality tolerances

Ask once and accept answers at any time. Record known source defects accepted by the consumer in this block.

- **Accepted source defects:**
- **Warning and failure classes:**
- **Completeness expectation:**
- **Artefact:**
- **Position in artefact:**
- **Extracted by:**
- **Fact status:**

## 16. Change, audit and transition

Ask once and accept answers at any time. The final four conditions apply to modernisation. Leave them empty for greenfield and do not ask a greenfield use case about cutover.

- **Change frequency:**
- **Change approver:**
- **Compatibility obligation:**
- **Audit evidence:**
- **Audit evidence retention:**
- **Parallel run period:**
- **Cutover criteria:**
- **Decommission owner:**
- **Rollback:**
- **Artefact:**
- **Position in artefact:**
- **Extracted by:**
- **Fact status:**
