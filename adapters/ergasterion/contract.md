# Ergasterion contract

Evorthon supplies a declared generation contract and receives generated
artefacts. It does not embed, vendor, or inspect Ergasterion implementation.
Everything named below is a public command, a declaration key, or a published
output path.

## Commands Evorthon invokes

- `init` creates an estate with the directory layout the later commands assume.
- `validate` checks a product declaration against the declaration schema.
- `emit-products --check` translates the declarations and fails when a
  regenerated artefact would differ from the one on disk. This is how byte
  stability is proven for each emitter.
- `product-graph --check` regenerates the product graph and its lineage siblings
  and fails on any difference.
- `contracts --check` regenerates the consumer contracts and fails on any
  difference.
- `lint` reports declaration defects that are not schema violations.

Every `--check` form is the acceptance form. A difference is a declaration
defect.

The generation route uses a fixed order. It runs `init` in an empty scratch
directory, writes the declarations, and runs `validate`. It then runs
`emit-products` to generate the artefacts. The route follows with
`emit-products --check`, `product-graph --check`, and `contracts --check`.
Those checks prove that the generated set byte-matches the declarations. The
write form generates; the check forms accept. The compatibility contract
requires every command named in this section.

## Declaration keys Evorthon writes

A product declaration carries the top-level keys `product`, `sources`, `steps`,
`target`, `checkpointing`, and the optional `combine` and `physical`.

- `product` names the domain and product identity.
- `sources` lists the inputs. A fixture-backed input is `kind: fixture` with
  inline field declarations and a CSV under `seeds/`. A consumer pin is
  `contract: domain.product@N`, where `N` is the producer major. Resolution drops
  the major, so the consumer checks the major itself and treats a mismatch as a
  defect.
- `steps` carries the ordered transformation.
- `target.shape` declares the shape of the emitted relation.
- `checkpointing` is typed as a bare object by the declaration schema, and
  translation enforces three policy keys for every product: `granularity`,
  `max_retries` and `backoff`. A missing key is refused at translation, not at
  run time. The sibling `checkpoint: true` forces table materialisation for the
  relation and registers it under `checkpoint_relations` in the product graph.
- `combine` declares a multi-source combination.
- `physical` declares physical names and a schema only. It carries no partition,
  cluster, or retention key.

## Files Evorthon reads

- `graphs/products/product-graph.json`, schema `ergasterion.product-graph/v1`,
  carrying `order`, `generations`, `relations`, `auxiliary_relations`,
  `checkpoint_relations`, the emitted CSV header lists, the artefact counts, and
  `stored_relations` and `stored_fields` when a `physical` block is declared.
  `auxiliary_relations` is the estate's registry of translator-private
  relations; it is empty when no translator registers one, and each product's
  own auxiliary relations are named in its runtime manifest.
- `graphs/products/product-nodes.csv`, `graphs/products/product-edges.csv` and
  `graphs/products/product-field-lineage.csv`, the CSV siblings of the product
  graph. Nodes carry the published name, domain, layer, profile, shape,
  generation, relations, materialisation and checkpoint flag; edges carry the
  consumed contract reference; lineage rows live here and not in a runtime
  manifest. The estate also emits `product-validations.csv`, which the route
  does not read.
- `manifests/products/**`, the per-product runtime manifests. The route reads
  the materialisation block for the declared unique key and intent.
- `contracts/products/**`, the published consumer contracts that a downstream
  product pins. The route reads `contract.json` for `identity.major` and for
  the published relation's field names, types and required flags.

A missing or malformed file produces a refusal.
The route compares each consumed contract reference on an emitted edge with the
producer's own `identity.major` and refuses a mismatch, because resolution drops
the major.

## Estate and generated evidence

Generation runs in a scratch estate the environment owns. The route scaffolds
into an empty directory, replaces the scaffold's seeded declaration with exactly
the declared products, and refuses to scaffold over held content. The estate
path stays with the environment. Evorthon records each generated artefact by
its estate-relative identity and content digest.

Generated artefacts are referenced as build evidence only after a reviewer
identity distinct from the generating actor records an accepted disposition.
A pending or rejected disposition yields no evidence reference.

## Declaration drafts

`evorthon_data.delivery.declaration_draft` projects one use-case segment into
a product declaration draft: the same top-level keys named above, rendered as
indented JSON (one valid form of YAML) so the module needs no YAML library.
Only a segment whose build route is `generated` can be projected. The module
never imports the released `ergasterion` distribution, reaches no filesystem
or process capability at all, and never writes a draft into an estate.

A draft is recorded as a proposal reference: the drafted document named by
identity, version and content digest, with the drafting actor. It is
adjudicated through the same disposition vocabulary a generation is, by a
reviewer identity distinct from the drafting actor, and it is referenced as
evidence only after an accepted disposition. A pending or rejected
adjudication yields no reference, and nothing reaches an estate until a
reviewer has accepted the declaration.

### Pattern mappings

The draft emits exactly the patterns listed below when their declarations
are present. A layer label does not add patterns.

| Pattern | The declaration it is emitted for |
| --- | --- |
| `batch_transfer` | a consumed source: a fixture-backed frozen input, an upstream contract pin, or a consumer dependency |
| `data_validation` | a schema expectation: a fixture field the frozen input declares cannot be null |
| `calculated_fields` | a calculation: an intermediate result the span passes through, extended by the computed fields the caller supplies |
| `data_contracts`, `lineage_capture` | the target contract the declaration carries |
| `metadata_capture` | the accepting authority the draft names as owner |
| `schema_publish`, `data_publish` | the target shape the declaration carries |
| `checkpoint_retries` | the run-policy conditions, carried in the top-level `checkpointing` block and never as a step |

An intermediate result is a declared calculation on the span, so each one
carries the calculated fields that realise it. The module never derives an
expression from an intermediate result's description: parsing a
transformation rule into one is a distinct, narrow adapter beside this one,
not built here, so an intermediate with no supplied calculated field is
refused. A span that passes no intermediate result and carries no supplied
computed field implies no calculation at all, and is refused before any
command runs.

### Source combinations

The use-case record can describe source combinations. The declaration-draft
adapter does not translate those records into `combine` declarations. It
accepts one consumed source and refuses any span with more than one source
before running commands. Each source is validated first, so a malformed
source is reported as malformed.

A pin carries the producer's contract without a shape. Validation for a pinned
source uses the consumed field expectations recorded for that source.

### Layer profiles

The adapter supports the layer profile below. It refuses any other layer.
The profile defines mandatory, optional and forbidden patterns.

| Layer label | Profile | Mandatory | Optional | Forbidden |
| --- | --- | --- | --- | --- |
| `derived` | `derivation` | `batch_transfer`, `data_validation`, `calculated_fields`, `data_contracts`, `lineage_capture`, `metadata_capture`, `schema_publish`, `data_publish`, `checkpoint_retries` | `data_enrichment`, `data_aggregation`, `data_filtering` | `batch_ingestion`, `data_curation` |

Steps are emitted in the profile's own composition order. A mandatory pattern
no declaration implies is refused naming the missing declaration; a pattern
the profile forbids or does not classify is refused naming the profile.

### Value sources

`product.version` is the use case's version identifier once a version has
been cut. Before then, it is a caller-supplied draft version named in the
proposal notes. `target.shape` comes from the segment's build route where
declared. Otherwise, it comes from the block 11 historisation kind. Only
`current only` maps to the `declared` shape this module can state.
`target.contract.freshness` comes from the freshness deadline condition or
its recorded default.

`data_validation` takes its rule completeness from the completeness
expectation, its `on_failure` policy from the warning and failure classes,
and, when that policy quarantines, its `error_threshold` from the accepted
source defects. A condition value none of those readings can accept produces a
refusal. `checkpointing` carries `granularity`,
`max_retries` and `backoff` from the block 12 run-policy keys, declared or
defaulted, and `checkpoint: true` when the intermediate result the segment
reaches is a checkpoint candidate. `physical` carries a target output's
declared stored name and stored column names, where block 2 declared one.

`data_publish.publication_mode` is the one value no standing condition owns,
and translation refuses an occurrence that declares none. The draft carries a
whole-relation swap, the only mode the declaration schema admits without a
declared unique key, and records that choice in the proposal notes.

### Proposal-note content

The retention, classification and volume/performance ("layout") standing
conditions have no slot in the installed declaration schema at all. They are
never dropped: the proposal notes name them, every condition the draft did
carry and where it carried it, the product version and how it was obtained,
and every stated value no condition owns. A reviewer sees the whole picture
without consulting the use case again.

## Boundary

Evorthon writes declarations and reads the outputs named above. It never reaches
into a working directory these paths do not name, and it never reproduces the
translation itself. No version is named in this contract: `pyproject.toml` owns
the lower bound and `uv.lock` records resolved versions; `docs/dependency-contracts.md` explains the version policy.
