# Intake a use case

Fill the sixteen blocks of the use-case intake record. Work artefact-first. Read what the team already has before asking anyone anything, and ask only what no artefact answers.

## Read the artefacts with base tools

Use your base tools only: ordinary file reading, a data frame or spreadsheet reader, a SQL reader, a query tool against a supplied extract, and plain text. Expect schemas, sample extracts, data dictionaries, table definitions, query and transformation code, project definitions, exported job definitions, reports, schedules and catalogue exports. Read each one as it is.

Never propose a parser. No parser, conformance suite or artefact adapter is built for a shape that is not in hand. If a shape resists your base tools, record what you could read, record the rest as a gap, and say plainly that the remainder was not read. A repeated shape that becomes the bottleneck is a separate, sized piece of work for a human to approve, never something you build inside an intake round.

`../../method/artefact-first-intake.md` lists what to look for in each artefact class.

## Work from the sample you are given

What you receive for each artefact is a bounded sample of its text, never the whole artefact: the first rows up to a declared number of rows, cut again at a declared number of characters. It is the start of the artefact, not a representative selection from it, and the last line you see may be cut off in the middle. Read what is in front of you and record only what it actually shows. Do not extrapolate a row count, a date range, a distribution or a distinct-value set from the first rows of a file; record what the sample shows and record the rest as a gap.

Some artefacts arrive with no text at all, only their identity, digest, handling classification and locator. That is the classification gate: an artefact classified above the level the round is authorized for never has its text sent, and where no authorization names a level, no artefact text is sent. Treat such an artefact as unread. Record no fact against it, say plainly that it was not read, and put what it would have answered into the residual questions with the artefact named as its likely source. Never guess its contents from its name, its locator or its classification.

## Record every fact with its provenance and status

Every value you write carries four things: the artefact identity it was read from, the position inside the artefact, who or what extracted it, and a status of extracted, inferred or confirmed.

- Extracted means you read the value in the artefact at the position you name.
- Inferred means you concluded it from what you read, and a human has not yet agreed.
- Confirmed means a named human agreed the value.

A locator is logical. Name the artefact and the position inside it, such as a sheet and a cell range, a table and a column, or a statement and a line. Never write a drive letter, a network location or an absolute path.

Freeze each artefact you read with a digest and classify it on intake. An unknown classification is handled as confidential. A file holding real personal data stays with the adopting team; the record carries its digest, its schema and the summaries a human approved, never its rows. The same rule holds for what you are sent: a bounded sample crosses, the whole artefact never does, and the round reports how much of each artefact crossed.

## Confirm inferred facts in bulk

Do not interrupt with one question per inference. Collect the inferences from a whole reading pass and put them to the human as one list to confirm, correct or reject in a single round. Confirmed entries become confirmed facts; corrected entries become confirmed facts with the human's value; rejected entries become gaps.

## Ask only residual questions

After the reading pass and the bulk confirmation, ask only what remains unanswered. Blocks one and eight are conversational and always asked. Every other block is read from artefacts first, confirmed in bulk, and asked only as residual questions.

"I do not know yet" is a first-class answer. It creates a gap with a suggested owner and a note on whether labelled synthetic data can fill it. It is never a refusal, never a blocker, and never a reason to stop the round. A block can be answered partly and revisited in a later round.

## Apply the mode differences

A modernisation use case records, for each target output, the existing output it replaces and where that output lives. It asks whether each named step is continuity worth keeping or an accident of the old run. It defaults an expected value to a capture of the old run on a named date, and it asks the parity questions of the last block, the parallel run period, the cutover criteria, the decommission owner and the rollback.

A greenfield use case never asks a parity question. It has no replaced output, no continuity label, no capture of an old run and no cutover condition. Its expected values come from a specification, a golden example or a reference implementation.

## Close the round

Finish the round by reading the readiness projection. The product computes it per segment from the recorded facts, so readiness is never kept by hand. It shows three lists: what is buildable now and on which fallbacks, the gaps with their suggested owners and whether synthetic data can fill them, and the open questions. A use case is never blocked as a whole. The human decides what to obtain, what to synthesise and what to leave. Then run the paired reviewer.
