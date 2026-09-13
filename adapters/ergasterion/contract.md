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

Every `--check` form is the acceptance form. A difference is a defect in the
declaration, never acceptable drift.

The generation route drives them in one fixed order: `init` into an empty
scratch directory, then the declarations are written, then `validate`, then
`emit-products` to generate, then `emit-products --check`, `product-graph
--check` and `contracts --check` to prove the generated set byte-matches what
the declarations produce. The write form is what generates; the check forms are
what accept. The presence of every command named in this section is the
compatibility contract Evorthon asserts before it generates.

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

A missing or malformed file among these is a refusal, never an empty result.
The route compares each consumed contract reference on an emitted edge with the
producer's own `identity.major` and refuses a mismatch, because resolution drops
the major.

## Estate and generated evidence

Generation runs in a scratch estate the environment owns. The route scaffolds
into an empty directory, replaces the scaffold's seeded declaration with exactly
the declared products, and refuses to scaffold over held content. The estate
path stays with the environment: a generated artefact is recorded by its
estate-relative identity and its content digest, never by a path.

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

### Which declaration implies which pattern

The draft emits a step for a pattern the segment's own declarations imply,
and for no other. Nothing is emitted because a backbone says so.

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

### One source at a time

A declaration that consumes two or more sources must also declare how they
combine, and the use case declares nothing that says: no intermediate result
kind names a join or a union, the build route names no combination, and a
target output's definition source states none either. So the draft refuses a
span that consumes more than one source, naming the missing declaration,
rather than emitting a declaration the estate rejects with an undeclared
composition. Each source is declared and checked first, so a malformed one is
still refused as malformed.

The intake record now carries that declaration: a segment states how the
sources it reads combine, and the span carries the declaration recorded under
its own name. The draft change that consumes it is a registered follow-up,
not made here, and this is the mapping it takes:

| Declared value | Declaration key |
| --- | --- |
| the combination method, `union` or `merge` | `combine.method` |
| the keys a merge merges its sources on | `combine.keys` |
| which rows a merge keeps, `inner` or `outer` | `combine.join` |
| a union, which stacks rows and takes neither | `combine` with the method alone |

With that mapping the refusal inverts for a span that carries a declaration:
the draft emits every source it already checks, adds the `combine` block from
the declaration, and refuses only a span reading more than one source that
declares no combination. The declaration names the sources it combines and the
span refuses one it does not read, so the block cannot describe a source the
declaration would not emit. A pin still carries the producer's contract and no
shape of its own, so a validation rule for a pinned source comes from the
consumed field expectations the record now carries, never from the pin.

### Which patterns a layer's profile admits

The composition a layer label admits is the estate's routing policy, and each
admitted profile states the patterns it makes mandatory, the ones it leaves
optional and the ones it forbids. That table is adapter knowledge here: a
layer this table does not name is refused with a closed reason, never
accepted unchecked, and mapping a further layer is a registered follow-up.

| Layer label | Profile | Mandatory | Optional | Forbidden |
| --- | --- | --- | --- | --- |
| `derived` | `derivation` | `batch_transfer`, `data_validation`, `calculated_fields`, `data_contracts`, `lineage_capture`, `metadata_capture`, `schema_publish`, `data_publish`, `checkpoint_retries` | `data_enrichment`, `data_aggregation`, `data_filtering` | `batch_ingestion`, `data_curation` |

Steps are emitted in the profile's own composition order. A mandatory pattern
no declaration implies is refused naming the missing declaration; a pattern
the profile forbids or does not classify is refused naming the profile.

### Where each declared value comes from

`product.version` is the use case's version identifier once a version has
been cut, and otherwise a caller-supplied draft version that the proposal
notes label as one. `target.shape` comes from the segment's own build route
where declared, and otherwise from the block 11 historisation kind; only
`current only` maps to a shape (`declared`) this module can state without
inventing entity or dimension modelling content the use case does not carry.
`target.contract.freshness` comes from the freshness deadline condition or
its recorded default.

`data_validation` takes its rule completeness from the completeness
expectation, its `on_failure` policy from the warning and failure classes,
and, when that policy quarantines, its `error_threshold` from the accepted
source defects. A condition value none of those readings can accept is
refused rather than guessed. `checkpointing` carries `granularity`,
`max_retries` and `backoff` from the block 12 run-policy keys, declared or
defaulted, and `checkpoint: true` when the intermediate result the segment
reaches is a checkpoint candidate. `physical` carries a target output's
declared stored name and stored column names, where block 2 declared one.

`data_publish.publication_mode` is the one value no standing condition owns,
and translation refuses an occurrence that declares none. The draft carries a
whole-relation swap, the only mode the declaration schema admits without a
declared unique key, and names it in the proposal notes rather than applying
it in silence.

### What the proposal notes carry

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
the lower bound and `docs/dependency-contracts.md` records the dated resolution.
