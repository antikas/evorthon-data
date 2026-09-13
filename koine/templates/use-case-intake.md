# Use-case intake

One record per use case, sixteen blocks. Read the artefacts first and ask only what no artefact answers. Repeat a block for every item it holds, one target output, one dataset, one step, one scenario, one authority, one segment at a time.

Every recorded value carries the artefact it was read from, the position inside that artefact, who or what extracted it, and whether it is extracted, inferred or confirmed. An unanswered field is a gap, never a stop. Any block can be answered partly and revisited later.

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

Repeat for each input dataset. Availability says whether a frozen extract is in hand, expected by a date, absent, or filled with labelled synthetic data. An absent input is a recorded fact, not a refusal.

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

The same fields as an input, with the role naming which it is. Whether it changes over time, and whether the output depends on which version was in force, has no field of its own here yet, so record it as a residual question and carry it in the gap list until one exists.

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

The normal case first, then late-arriving rows, missing keys, duplicates, corrections and restatements, period boundaries, empty inputs, and a reference-data version change. Each scenario is one case held by identity and version. The case registry owns the frozen inputs, the expected output and its origin, and none of that content is copied here.

- **Scenario case identity:**
- **Scenario case version:**
- **Artefact:**
- **Position in artefact:**
- **Extracted by:**
- **Fact status:**

## 7. Comparison policy

How a scenario result is judged, exact or within a tolerance per column and per aggregate, ordering, formatting, exclusions with their reasons, and control totals. The comparison rules belong to the named case, so this block records the case that carries them and copies none of the rules.

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

A standing condition is asked once and may be answered at any time. An unanswered condition falls back to a visible default that a named human may override, and the default is recorded so nothing is applied that the record does not show. This block also records every artefact intake read, with its identity and digest, its classification, and its logical locator. An unknown classification is handled as confidential.

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

Asked once, answered whenever. An unanswered condition records the default it falls back to.

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

Asked once, answered whenever. These answers become the operational evidence the consumer expects and the runtime settings the build uses.

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

Asked once, answered whenever. A declared cost ceiling earns a scenario of its own.

- **Load volume:**
- **Growth and peaks:**
- **Query pattern:**
- **Cost ceiling:**
- **Artefact:**
- **Position in artefact:**
- **Extracted by:**
- **Fact status:**

## 14. Access and consumption

Asked once, answered whenever. Access rules stay owned by the adopting environment and are named here by identity alone. This block also pins every product this use case consumes from another use case, by the providing use case and a major version, says which of the fields read from a pinned product can be empty, and, where a segment reads more than one source, says how those sources combine: the method, and for a merge the keys it merges on and which rows it keeps.

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

Asked once, answered whenever. Known source defects that the consumer already accepts belong here, not in a scenario.

- **Accepted source defects:**
- **Warning and failure classes:**
- **Completeness expectation:**
- **Artefact:**
- **Position in artefact:**
- **Extracted by:**
- **Fact status:**

## 16. Change, audit and transition

Asked once, answered whenever. The last four conditions belong to a modernisation use case alone; a greenfield use case leaves them empty and is never asked a cutover question.

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
