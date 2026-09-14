# AutoBuild contract

An item must have approval, boundaries, dependencies, and deterministic
validators before AutoBuild is considered. Operational sequencing remains
AutoBuild-owned. Everything named below is a public command, option, or a
field of the command's own reported result.

## Commands Evorthon invokes

- `autobuild --help` and `autobuild run --help` are the compatibility
  contract's own read surface: the route checks the installed subcommand set,
  the installed `run` option set, and the installed `--delivery-mode` choices
  against them before it ever composes a live run. Presence of every name
  below is what the route asserts; no version is asserted anywhere.
- `autobuild run` runs the approved queue of one repository. Evorthon always
  composes `--delivery-mode current-branch-pr`; no other mode is ever
  selected by this route.
  - `--repository` names the repository whose queue is run.
  - `--profile` names the project profile that supplies the seat tiers and lane
    settings.
  - `--harness` names the coding assistant that runs the builder and reviewer
    seats.
  - `--delivery-mode` selects how an accepted item is delivered.
  - `--allow-item` and `--exclude-item` select the queue. Selection is a flat
    allow-and-exclude list of item identities. There is no subtree or prefix
    scope, so a subset is named item by item. Evorthon composes `--allow-item`
    once per approved, ready item; it never composes `--exclude-item` itself,
    but the installed command must still support it.
  - `--allow-delivery` permits the delivery step for the named target. Evorthon
    composes it only when the caller supplies an explicit, identified delivery
    authority; without one, the flag is never added.
- `autobuild watch` reports the live progress of a running campaign. Evorthon
  does not invoke it; it is named here for completeness of the public surface.

## The result Evorthon reads

`autobuild run` prints one JSON object to standard output. Evorthon reads it
by field name, never by re-deriving it, and refuses anything that fails this
shape:

- `schema` must be `autobuild.campaign-result.v1`. This names a result shape,
  never a tool version.
- `campaign_id` and `stop_reason` are read as plain text identities.
- `items` is a list; each entry carries `item_id`, `disposition`,
  `item_commit`, `tracker_commit`, `merged_commit` (each a commit identity or
  null) and `pushed` (a boolean).
- The result also carries `repository`, `scratch_root`, `report_ref`,
  `repository_report_ref` and `progress_ref`, each a filesystem path in the
  released report. Evorthon never retains any of them: its own run record
  keeps only the fields above and a content digest of the exact reported
  result, never a path.

## Boundary

AutoBuild owns the build sequence, the seat dispatch, and the tracker writes it
makes on the queue it runs. It commits and pushes the tracker itself from the
primary checkout, so a caller must not also write the tracker for the same item.
Evorthon supplies an approved queue and reads the outcome; it does not
reimplement selection, sequencing, or acceptance. No version is named in this
contract: `pyproject.toml` owns the lower bound and
`uv.lock` records resolved versions; `docs/dependency-contracts.md` explains the version policy.
