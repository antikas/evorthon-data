# Pinax contract

Use the public `pinax` command and declared use-case scope. Evorthon passes the
use-case record, the readiness reading of that same use case, the packages the
use case has approved, and the iterations in flight on its spans. It does not
copy readiness, claims, completion or any other live state into its own store,
and it does not couple verification semantics to a tracker.

## What the projection creates

- One parent item for each use case, titled with a stable namespace built from
  the engagement identity and the use-case identity. The namespace carries no
  digest and no revision, so the same use case keeps the same items as its
  readiness changes.
- One child item for each approved package, each readiness gap and each
  iteration on a span. An iteration child has the same shape as a package
  child.
- Each gap child is titled with that namespace followed by the suggested item
  title exactly as readiness wrote it. Readiness owns that wording.

A gap is projected as work under the use case. It is never a block on the use
case, and a gap synthetic data can fill is labelled rather than refused.

## Typed edges

- `parent-child` from the use-case parent to every child.
- `blocks` from a package to each package that depends on it.
- `blocks` from a gap to the items on the span it names. A gap that names no
  span gates nothing and hangs on the parent alone.
- `blocks` from the producing use case's item on the span that reaches a
  consumed product to the consuming use case's items on the spans that read
  that product, for every consumer dependency the record declares.

An edge joins two items the projection creates. A declaration that names no item
at one of its ends, such as a consumed product with no iteration declared on
either side of it, creates no edge rather than an invented one.

## Notes

Each gap item carries one note. Its `--ref` is
`koine://use-case/<use case>/readiness/<projection digest>`, which points at the
reading the gap came from and never at a stored document or an environment
route. Its caption names the gap kind, the suggested owner and whether
synthetic data can fill the gap, within the tracker's 200-character cap. The
note is written once; a later reading is surfaced in the report rather than by
writing a second note.

## Re-projection

Re-projection is idempotent while the already projected graph is still the exact
declared scope: it adds no item, edge or note and changes no state. Pinax gate
resolution afterwards is left untouched.

Re-projection reports, without changing anything, every open gap item whose fact
the current reading no longer states, and every open gap item whose kind,
suggested owner or synthetic-fillability no longer matches its note. Closing
such an item is a tracker decision, not the projection's.

## Refusals

The projection refuses only integrity failures, and every refusal about the
declared scope happens before the first tracker command:

- an item in the managed namespace that the use case does not declare and that
  the projection did not write as a gap;
- a dependency edge in scope that the declared graph does not state;
- a package the use case has not approved, an iteration on a span the use case
  does not have, or a consumed product the two records do not agree on;
- a machine route in a reference or a caption, a caption over the tracker cap,
  or a gap kind the projection has no wording for;
- an actor handle that is not a role and a host.

## Commands Evorthon invokes

These six are the whole command surface the projection composes.

- `init` creates the tracker in a repository.
- `board --json` reads the folded board state: the items, the typed edges and
  the notes. It is the only way Evorthon reads the tracker.
- `add` creates an item.
- `block --gate scope` records an item as blocked while a gate the projection
  declares is not yet recorded, so a half-built graph never reads as ready.
- `note add` attaches a note to an item. Its `--ref` must start with `koine://`,
  `~/knowledge/`, `projects/` or `docs/`, and a caption is at most 200
  characters. Evorthon emits only the `koine://` form, so no environment route
  reaches the tracker.
- `dep add --type` records a typed edge between two items.

## Commands Evorthon does not invoke

Pinax offers these to the people and agents working the board. Evorthon issues
none of them, and depends only on their meaning staying as described.

- `claim` takes an item for one actor, `done` completes an item and `park` sets
  one aside. Every state after the graph exists is recorded this way.
- `ready --json`, `next --json` and `status --json` read folded state as JSON:
  what can start now, what to take next, and the current state of the work.
- `verify` checks the tracker's own integrity.

## Boundary

Pinax owns readiness, claims, completion and gate resolution. Evorthon reads
folded state back through the board response and never reads a tracker file.
Evorthon stores opaque returned item identities, not tracker state. There is no
retitle command, so an item title is decided when the item is created. No
version is named in this contract: `pyproject.toml` owns the lower bound and
`docs/dependency-contracts.md` records the dated resolution.
