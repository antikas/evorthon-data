# Artefact-first intake

Schemas, data and transformations already exist somewhere before anyone is interviewed. Read them first with base tools, record what they say, and spend the conversation on what no artefact answers.

No parser, conformance suite or artefact adapter is built for a shape that is not in hand. Read what your base tools can read, record the rest as a gap, and say what you did not read. A repeated shape that becomes the bottleneck is a separate, sized piece of work a human approves.

## What to look for, by artefact class

- **Delimited extracts.** Column names and order, apparent types, null and sentinel values, row counts, the period the extract covers, and any header or footer that carries a run date. Work from the sample you are given; never copy raw rows into the record.
- **Spreadsheets.** Sheet names, the header row, merged cells and hidden columns, formulas that hold business rules, lookup tables on side sheets, and the manual steps a note in a cell describes.
- **Data dictionaries.** Field definitions, permitted values, ownership and stewardship, classification labels, and the fields the dictionary describes that the extract does not carry.
- **Table definitions.** Column names and types, keys and uniqueness, nullability, defaults, partitioning and clustering, and constraints that state an invariant the consumer relies on.
- **Query and transformation code.** Source tables, join keys and join kinds, filters, aggregations and their grain, window functions, deduplication rules, hard-coded dates and thresholds, and the order the steps run in.
- **Project definitions.** Model dependencies, materialisation choices, declared tests and their thresholds, documented descriptions, and the environment settings that change behaviour between runs.
- **Exported job definitions.** Step order and dependencies, source and target connections by name, transformations expressed as configuration, error handling, retry settings, and any credential that must be removed before the artefact is stored.
- **Reports.** The columns a consumer actually reads, the filters and parameters they set, totals and subtotals that act as control totals, formatting that carries meaning, and the refresh time printed on the page.
- **Schedules.** Trigger times and time zones, upstream dependencies, the window a run is expected to finish in, calendar exceptions, and what the schedule does when a run is late.
- **Catalogue exports.** Registered datasets and owners, classification and retention labels, declared lineage, freshness expectations, and the entries that name a system nobody mentioned.

## What every artefact contributes

Each artefact yields facts, and each fact carries the artefact identity, the position inside it, the extractor and a status of extracted, inferred or confirmed. Each artefact is frozen with a digest and classified on intake; an unknown classification is handled as confidential. Credentials found inside an exported artefact are removed before it is stored.

A fact locator is logical. It names an artefact and a position inside it, such as a sheet and a cell range, a table and a column, or a statement and a line. It is never a drive letter, a network location or an absolute path.

## What crosses to a model

Reading an artefact and sending it are two different acts. The artefact is read where it sits, and what reaches a model on an intake round is a bounded sample of its text: the first rows up to a declared number of rows, cut again at a declared number of characters. The sample is the start of the artefact, not a representative selection from it, and nothing beyond that prefix crosses. No artefact crosses whole, however small it looks.

The handling classification gates the crossing. An artefact classified at or below the level the round's authorization names crosses as a sample. An artefact above that level crosses no text at all: the round proceeds on its digest, its classification label and the record, and says so. An unknown classification is handled as confidential, so it crosses only where confidential text is authorized. Where no authorization names a level, no artefact text crosses at all.

The round reports, for each artefact, how much of it crossed or the closed reason none of it did. Nothing is refused for being synthetic. The independent review pass carries no artefact text at any classification; the reviewer opens the artefacts where they sit.
