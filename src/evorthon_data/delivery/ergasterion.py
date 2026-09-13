"""Narrow public-CLI route from an approved generation contract to Ergasterion.

The route supplies declarations and reads back published artefacts. It never
reproduces the translation, never edits a generated artefact, and never keeps a
path in a record: an artefact is named by its estate-relative identity and its
content digest.

Only a contract that declares exact generation is accepted. Every other refusal
is an integrity refusal: a declaration the contract does not state exactly, a
consumer pin that disagrees with the producer major, a generated artefact that
is missing or malformed, or a reference to generated artefacts that no distinct
reviewer has adjudicated.
"""
# evorthon-implements: EVD-README-016
# evorthon-implements: EVD-README-008
from __future__ import annotations

# evorthon-component: delivery_adapters

import csv
import hashlib
import io
import json
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from ..verification.domain import (
    CanonicalisationDeclaration,
    Checkpoint,
    EvidenceReference,
    GrainDeclaration,
    Identity,
    LineageDefinition,
    OutputLineageBinding,
    SchemaDeclaration,
    SchemaField,
    SchemaValueType,
)

DISTRIBUTION = "ergasterion-factory"

# The public commands this adapter contract names. Presence of every one of
# them in the installed command set is the compatibility contract; no version
# is asserted anywhere.
REQUIRED_COMMANDS: tuple[str, ...] = (
    "init",
    "validate",
    "emit-products",
    "product-graph",
    "contracts",
    "lint",
)

GRAPH_SCHEMA = "ergasterion.product-graph/v1"
DECLARATION_DIRECTORY = "declarations/products"
SEED_DIRECTORY = "seeds"
GRAPH_DESCRIPTION = "graphs/products/product-graph.json"
NODE_TABLE = "graphs/products/product-nodes.csv"
EDGE_TABLE = "graphs/products/product-edges.csv"
FIELD_LINEAGE_TABLE = "graphs/products/product-field-lineage.csv"
READ_DIRECTORIES: tuple[str, ...] = ("graphs/products", "manifests/products", "contracts/products")

NODE_HEADER = (
    "id",
    "name",
    "domain",
    "layer",
    "profile",
    "shape",
    "generation",
    "relations",
    "materialisation",
    "checkpoint",
)
EDGE_HEADER = ("edge_id", "src", "dst", "kind", "contract", "relation")
FIELD_LINEAGE_HEADER = (
    "edge_id",
    "product",
    "target_field",
    "source_kind",
    "source_product",
    "source",
    "occurrence",
    "transform",
)

# The neutral scalar type names a published contract carries, and the one
# object form. Anything else is an artefact this route cannot map.
SCALAR_VALUE_TYPES: Mapping[str, SchemaValueType] = {
    "string": SchemaValueType.STRING,
    "integer": SchemaValueType.INTEGER,
    "boolean": SchemaValueType.BOOLEAN,
    "date": SchemaValueType.DATE,
    "timestamp": SchemaValueType.TIMESTAMP,
}
DECIMAL_TYPE_NAME = "decimal"
DECLARED_FIELD_ROLE = "declared"


class ErgasterionRouteError(ValueError):
    """Raised when generation cannot proceed or a generated artefact fails integrity."""


class ErgasterionRunner(Protocol):
    """The small released-CLI capability required by this adapter."""

    def run(self, arguments: Sequence[str], *, working_directory: Path | None) -> str:
        """Run one public Ergasterion command and return its standard output."""


@dataclass(frozen=True)
class SubprocessErgasterionRunner:
    """Run the released Ergasterion command without importing tool internals.

    The command is a vector so that the same released entry point can be
    reached through its console script or through the interpreter that holds
    it. The environment owns which one is available.
    """

    command: tuple[str, ...] = ("ergasterion",)

    def run(self, arguments: Sequence[str], *, working_directory: Path | None) -> str:
        if not self.command or not all(isinstance(part, str) and part.strip() for part in self.command):
            raise ErgasterionRouteError("an Ergasterion command is required")
        try:
            completed = subprocess.run(
                [*self.command, *arguments],
                cwd=None if working_directory is None else str(working_directory),
                capture_output=True,
                check=False,
                text=True,
            )
        except OSError as exc:
            raise ErgasterionRouteError("the released Ergasterion command is unavailable") from exc
        if completed.returncode:
            detail = (completed.stderr or completed.stdout).strip()
            raise ErgasterionRouteError(f"Ergasterion command failed: {detail or 'unknown error'}")
        return completed.stdout


@dataclass(frozen=True)
class ProductDeclaration:
    """One product declaration, stated exactly as the text the estate receives."""

    file_name: str
    document: str


@dataclass(frozen=True)
class FixtureSeed:
    """One fixture seed table, stated exactly as the text the estate receives."""

    file_name: str
    document: str


@dataclass(frozen=True)
class ExactGenerationContract:
    """An approved declaration of exact generation.

    Exact means every generated product is stated by the contract: the whole
    declaration text, the whole seed text, and the canonicalisation the
    resulting lineage carries. Nothing is inferred and nothing is templated.
    """

    identity: Identity
    declarations: tuple[ProductDeclaration, ...]
    seeds: tuple[FixtureSeed, ...]
    canonicalisation: CanonicalisationDeclaration


@dataclass(frozen=True)
class ProductNodeRecord:
    """One published product, exactly as the emitted node table states it."""

    published_name: str
    name: str
    domain: str
    layer: str
    profile: str
    shape: str
    generation: str
    relations: tuple[str, ...]
    materialisation: str
    checkpoint: bool


@dataclass(frozen=True)
class ProductEdgeRecord:
    """One contract edge, exactly as the emitted edge table states it."""

    edge_id: str
    source: str
    target: str
    kind: str
    contract_reference: str
    relation: str


@dataclass(frozen=True)
class FieldLineageRecord:
    """One field-lineage row, exactly as the emitted lineage table states it."""

    edge_id: str
    product: str
    target_field: str
    source_kind: str
    source_product: str
    source: str
    occurrence: str
    transform: str


@dataclass(frozen=True)
class AuxiliaryLineageRecord:
    """One translator-private relation the estate registers outside a contract."""

    product: str
    relation: str
    translator: str
    purpose: str


@dataclass(frozen=True)
class ProductGraphReading:
    """The emitted product graph as read, before any mapping."""

    schema: str
    order: tuple[str, ...]
    nodes: tuple[ProductNodeRecord, ...]
    edges: tuple[ProductEdgeRecord, ...]
    field_lineage: tuple[FieldLineageRecord, ...]
    checkpoint_relations: tuple[str, ...]
    auxiliary_relations: tuple[AuxiliaryLineageRecord, ...]


class GenerationDisposition(str, Enum):
    """The adjudicated standing of one generation."""

    PENDING = "pending-adjudication"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class AdjudicatedGeneration:
    """A generation with its reviewer identity and adjudicated disposition."""

    estate: GeneratedEstate
    reviewer: Identity
    disposition: GenerationDisposition

    def build_evidence(self) -> tuple[EvidenceReference, ...]:
        """Reference the generated artefacts as evidence, once they are accepted."""
        if self.disposition is not GenerationDisposition.ACCEPTED:
            raise ErgasterionRouteError(
                "generated artefacts are referenced as build evidence only after an accepted adjudication"
            )
        return tuple(
            EvidenceReference(
                evidence_id=identity,
                version=self.estate.contract_identity.version,
                digest=digest,
                summary=(
                    f"generated by {self.estate.generated_by} and reviewed by {self.reviewer.identifier}"
                ),
            )
            for identity, digest in self.estate.artefact_digests
        )


@dataclass(frozen=True)
class GeneratedEstate:
    """What one generation produced: the reading, the mapping, and the digests."""

    contract_identity: Identity
    generated_by: str
    graph: ProductGraphReading
    lineage: LineageDefinition
    artefact_digests: tuple[tuple[str, str], ...]

    @property
    def auxiliary_lineage(self) -> tuple[AuxiliaryLineageRecord, ...]:
        """The auxiliary lineage: relations no product contract publishes."""
        return self.graph.auxiliary_relations

    def adjudicated(self, *, reviewer: Identity, disposition: GenerationDisposition) -> AdjudicatedGeneration:
        """Attach a distinct reviewer identity and an adjudicated disposition."""
        reviewer = _identity(reviewer, "generated artefact reviewer")
        if not isinstance(disposition, GenerationDisposition):
            raise ErgasterionRouteError("a generated artefact disposition must be an adjudicated disposition")
        if reviewer.identifier == self.generated_by:
            raise ErgasterionRouteError(
                "a generated artefact reviewer must be distinct from the generating actor"
            )
        return AdjudicatedGeneration(estate=self, reviewer=reviewer, disposition=disposition)


class ErgasterionGenerationRoute:
    """Drive the released Ergasterion commands over an exact generation contract."""

    def __init__(
        self,
        runner: ErgasterionRunner,
        *,
        actor: str,
        capabilities: Mapping[str, Any],
    ) -> None:
        self._runner = runner
        self._actor = _nonempty_text(actor, "generation actor")
        if not isinstance(capabilities, Mapping):
            raise ErgasterionRouteError("an installed capability report is required")
        self._capabilities = capabilities

    def assert_supported(self) -> tuple[str, ...]:
        """Check the compatibility contract: the distribution and its commands."""
        record = self._capabilities.get(DISTRIBUTION)
        if not isinstance(record, Mapping) or record.get("installed") is not True:
            raise ErgasterionRouteError(
                f"the Ergasterion generation capability is unavailable: {DISTRIBUTION} is not installed"
            )
        supported = _supported_commands(self._runner.run(("--help",), working_directory=None))
        missing = tuple(name for name in REQUIRED_COMMANDS if name not in supported)
        if missing:
            raise ErgasterionRouteError(
                "the installed Ergasterion command set does not support: " + ", ".join(missing)
            )
        return REQUIRED_COMMANDS

    def generate(self, contract: object, *, estate: Path) -> GeneratedEstate:
        """Generate the declared products into one scratch estate and map the result."""
        declaration = _exact_generation_contract(contract)
        estate = Path(estate)
        self.assert_supported()
        self._prepare(estate)
        self._runner.run(("init", str(estate)), working_directory=estate.parent)
        self._install(declaration, estate)
        for arguments in (
            ("validate", "--estate-root", str(estate)),
            ("emit-products", "--estate-root", str(estate)),
            ("emit-products", "--check", "--estate-root", str(estate)),
            ("product-graph", "--check", "--estate-root", str(estate)),
            ("contracts", "--check", "--estate-root", str(estate)),
        ):
            self._runner.run(arguments, working_directory=estate)
        return _read_generation(declaration, estate, actor=self._actor)

    @staticmethod
    def _prepare(estate: Path) -> None:
        if not estate.parent.is_dir():
            raise ErgasterionRouteError("the generation estate needs an existing parent directory")
        if estate.exists() and (not estate.is_dir() or any(estate.iterdir())):
            raise ErgasterionRouteError("the generation estate must be an empty directory")

    @staticmethod
    def _install(declaration: ExactGenerationContract, estate: Path) -> None:
        """Leave the estate holding exactly the declared products and seeds.

        The scaffold seeds a walkthrough declaration of its own. It is removed
        so that the estate generates the declared products and nothing else.
        """
        products = estate / DECLARATION_DIRECTORY
        seeds = estate / SEED_DIRECTORY
        if not products.is_dir() or not seeds.is_dir():
            raise ErgasterionRouteError("the scaffolded estate does not carry the declaration layout")
        for path in sorted(products.iterdir()):
            if not path.is_file():
                raise ErgasterionRouteError("the scaffolded declaration directory is not a flat file set")
            path.unlink()
        for product in declaration.declarations:
            (products / product.file_name).write_text(product.document, encoding="utf-8", newline="\n")
        for seed in declaration.seeds:
            (seeds / seed.file_name).write_text(seed.document, encoding="utf-8", newline="\n")


def required_text(value: object, label: str, *, error: type[Exception]) -> str:
    """The one owner of the declared single-line text check in this package.

    A declared name, identifier or document reference is a non-empty string
    with no surrounding blank space and no line break or null character. The
    caller passes the error class its own refusals carry, so one rule serves
    every delivery adapter without either of them copying it.
    """
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character in value for character in "\r\n\x00")
    ):
        raise error(f"{label} is required")
    return value


def _nonempty_text(value: object, label: str) -> str:
    return required_text(value, label, error=ErgasterionRouteError)


def _identity(value: object, label: str) -> Identity:
    if not isinstance(value, Identity):
        raise ErgasterionRouteError(f"{label} must be a declared identity")
    _nonempty_text(value.identifier, f"{label} identifier")
    _nonempty_text(value.version, f"{label} version")
    _nonempty_text(value.digest, f"{label} digest")
    return value


def _plain_file_name(value: object, suffix: str, label: str) -> str:
    name = _nonempty_text(value, label)
    if name != Path(name).name or name.startswith(".") or not name.endswith(suffix):
        raise ErgasterionRouteError(f"{label} must be a plain {suffix} file name")
    return name


def _document(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ErgasterionRouteError(f"{label} must be a stated document")
    return value


def _exact_generation_contract(source: object) -> ExactGenerationContract:
    """Accept an exact generation contract and refuse anything else by reason."""
    if not isinstance(source, ExactGenerationContract):
        raise ErgasterionRouteError("generation requires a contract that declares exact generation")
    _identity(source.identity, "approved generation contract identity")
    if not isinstance(source.canonicalisation, CanonicalisationDeclaration):
        raise ErgasterionRouteError("an exact generation contract must declare its canonicalisation")
    _nonempty_text(source.canonicalisation.canonicalisation_id, "generation canonicalisation identifier")
    _nonempty_text(source.canonicalisation.version, "generation canonicalisation version")
    if not isinstance(source.declarations, tuple) or not source.declarations:
        raise ErgasterionRouteError("an exact generation contract must declare at least one product")
    if not isinstance(source.seeds, tuple):
        raise ErgasterionRouteError("an exact generation contract must declare its fixture seeds")
    names: set[str] = set()
    for product in source.declarations:
        if not isinstance(product, ProductDeclaration):
            raise ErgasterionRouteError("every declared product must be a stated product declaration")
        name = _plain_file_name(product.file_name, ".yml", "a product declaration file name")
        _document(product.document, "a product declaration document")
        if name in names:
            raise ErgasterionRouteError("an exact generation contract must declare each product once")
        names.add(name)
    seed_names: set[str] = set()
    for seed in source.seeds:
        if not isinstance(seed, FixtureSeed):
            raise ErgasterionRouteError("every declared fixture seed must be a stated fixture seed")
        name = _plain_file_name(seed.file_name, ".csv", "a fixture seed file name")
        _document(seed.document, "a fixture seed document")
        if name in seed_names:
            raise ErgasterionRouteError("an exact generation contract must declare each fixture seed once")
        seed_names.add(name)
    return source


def _supported_commands(help_text: object) -> frozenset[str]:
    """Read the installed command set out of the tool's own help output."""
    if not isinstance(help_text, str):
        raise ErgasterionRouteError("the installed Ergasterion command set could not be read")
    for line in help_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("subcommands:"):
            listed = stripped.partition(":")[2]
            return frozenset(name.strip() for name in listed.split(",") if name.strip())
    raise ErgasterionRouteError("the installed Ergasterion command set could not be read")


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _artefact_bytes(estate: Path, relative: str) -> bytes:
    path = estate / relative
    if not path.is_file():
        raise ErgasterionRouteError(f"generated artefact is missing: {relative}")
    return path.read_bytes()


def _artefact_text(estate: Path, relative: str) -> str:
    try:
        return _artefact_bytes(estate, relative).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ErgasterionRouteError(f"generated artefact is not text: {relative}") from exc


def _artefact_json(estate: Path, relative: str) -> dict[str, Any]:
    try:
        parsed = json.loads(_artefact_text(estate, relative))
    except json.JSONDecodeError as exc:
        raise ErgasterionRouteError(f"generated artefact is not JSON: {relative}") from exc
    if not isinstance(parsed, dict):
        raise ErgasterionRouteError(f"generated artefact is not a JSON object: {relative}")
    return parsed


def _artefact_table(estate: Path, relative: str, header: tuple[str, ...]) -> tuple[dict[str, str], ...]:
    rows = list(csv.reader(io.StringIO(_artefact_text(estate, relative))))
    if not rows or tuple(rows[0]) != header:
        raise ErgasterionRouteError(f"generated table does not carry its declared header: {relative}")
    records: list[dict[str, str]] = []
    for row in rows[1:]:
        if len(row) != len(header):
            raise ErgasterionRouteError(f"generated table row does not match its header: {relative}")
        records.append(dict(zip(header, row)))
    return tuple(records)


def _text_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ErgasterionRouteError(f"generated product graph has an invalid {label}")
    return tuple(value)


def _boolean_cell(value: str, relative: str) -> bool:
    if value not in ("true", "false"):
        raise ErgasterionRouteError(f"generated table carries an invalid flag: {relative}")
    return value == "true"


def _read_product_graph(estate: Path) -> ProductGraphReading:
    """Read the emitted graph files exactly, refusing a missing or malformed one."""
    description = _artefact_json(estate, GRAPH_DESCRIPTION)
    if description.get("schema") != GRAPH_SCHEMA:
        raise ErgasterionRouteError("generated product graph does not declare its expected schema")
    nodes = tuple(
        ProductNodeRecord(
            published_name=row["id"],
            name=row["name"],
            domain=row["domain"],
            layer=row["layer"],
            profile=row["profile"],
            shape=row["shape"],
            generation=row["generation"],
            relations=tuple(part for part in row["relations"].split(";") if part),
            materialisation=row["materialisation"],
            checkpoint=_boolean_cell(row["checkpoint"], NODE_TABLE),
        )
        for row in _artefact_table(estate, NODE_TABLE, NODE_HEADER)
    )
    edges = tuple(
        ProductEdgeRecord(
            edge_id=row["edge_id"],
            source=row["src"],
            target=row["dst"],
            kind=row["kind"],
            contract_reference=row["contract"],
            relation=row["relation"],
        )
        for row in _artefact_table(estate, EDGE_TABLE, EDGE_HEADER)
    )
    field_lineage = tuple(
        FieldLineageRecord(
            edge_id=row["edge_id"],
            product=row["product"],
            target_field=row["target_field"],
            source_kind=row["source_kind"],
            source_product=row["source_product"],
            source=row["source"],
            occurrence=row["occurrence"],
            transform=row["transform"],
        )
        for row in _artefact_table(estate, FIELD_LINEAGE_TABLE, FIELD_LINEAGE_HEADER)
    )
    auxiliary = _read_auxiliary_relations(description.get("auxiliary_relations"))
    reading = ProductGraphReading(
        schema=GRAPH_SCHEMA,
        order=_text_list(description.get("order"), "build order"),
        nodes=nodes,
        edges=edges,
        field_lineage=field_lineage,
        checkpoint_relations=_text_list(description.get("checkpoint_relations"), "checkpoint relation list"),
        auxiliary_relations=auxiliary,
    )
    _assert_graph_coverage(description, reading)
    return reading


def _read_auxiliary_relations(value: object) -> tuple[AuxiliaryLineageRecord, ...]:
    if not isinstance(value, list):
        raise ErgasterionRouteError("generated product graph has an invalid auxiliary relation list")
    records: list[AuxiliaryLineageRecord] = []
    for entry in value:
        if not isinstance(entry, dict) or not all(
            isinstance(entry.get(key), str) and entry.get(key)
            for key in ("product", "relation", "translator", "purpose")
        ):
            raise ErgasterionRouteError("generated product graph has an invalid auxiliary relation")
        records.append(
            AuxiliaryLineageRecord(
                product=entry["product"],
                relation=entry["relation"],
                translator=entry["translator"],
                purpose=entry["purpose"],
            )
        )
    return tuple(records)


def _assert_graph_coverage(description: Mapping[str, Any], reading: ProductGraphReading) -> None:
    """Refuse a graph whose description and tables disagree."""
    counts = description.get("counts")
    if not isinstance(counts, dict):
        raise ErgasterionRouteError("generated product graph has no counts")
    observed = {
        "products": len(reading.nodes),
        "edges": len(reading.edges),
        "field_lineage": len(reading.field_lineage),
    }
    if any(counts.get(key) != value for key, value in observed.items()):
        raise ErgasterionRouteError("generated product graph counts do not match its tables")
    published = {node.published_name for node in reading.nodes}
    if set(reading.order) != published or len(reading.order) != len(reading.nodes):
        raise ErgasterionRouteError("generated product graph order does not cover its nodes")
    relations = description.get("relations")
    if not isinstance(relations, dict) or {
        node.published_name: list(node.relations) for node in reading.nodes
    } != relations:
        raise ErgasterionRouteError("generated product graph relations do not match its nodes")
    checkpointed = {relation for node in reading.nodes if node.checkpoint for relation in node.relations}
    if set(reading.checkpoint_relations) != checkpointed:
        raise ErgasterionRouteError("generated product graph checkpoint relations do not match its nodes")
    for edge in reading.edges:
        if edge.source not in published or edge.target not in published:
            raise ErgasterionRouteError("generated product graph has an edge outside its nodes")


@dataclass(frozen=True)
class _ProductArtefacts:
    contract_document: Mapping[str, Any]
    contract_digest: str
    manifest_document: Mapping[str, Any]
    manifest_digest: str


def _read_product_artefacts(estate: Path, node: ProductNodeRecord) -> _ProductArtefacts:
    contract_path = f"contracts/products/{node.domain}/{node.name}/contract.json"
    manifest_path = f"manifests/products/{node.domain}/{node.name}.json"
    return _ProductArtefacts(
        contract_document=_artefact_json(estate, contract_path),
        contract_digest=_digest(_artefact_bytes(estate, contract_path)),
        manifest_document=_artefact_json(estate, manifest_path),
        manifest_digest=_digest(_artefact_bytes(estate, manifest_path)),
    )


def _producer_major(artefacts: _ProductArtefacts, published_name: str) -> int:
    identity = artefacts.contract_document.get("identity")
    major = identity.get("major") if isinstance(identity, dict) else None
    if not isinstance(major, int) or isinstance(major, bool) or major < 0:
        raise ErgasterionRouteError(f"generated contract has no producer major: {published_name}")
    return major


def _refuse_consumer_pin_drift(
    reading: ProductGraphReading, products: Mapping[str, _ProductArtefacts]
) -> None:
    """Check each declared consumer pin against the producer major itself.

    Graph coverage has already refused an edge that names a product the estate
    does not publish, so every edge source resolves to a read producer here.
    """
    for edge in reading.edges:
        reference = edge.contract_reference
        producer, separator, major_text = reference.rpartition("@")
        if not separator or not major_text.isdigit() or producer != edge.source:
            raise ErgasterionRouteError(f"generated edge carries an unreadable consumer pin: {reference}")
        major = _producer_major(products[edge.source], edge.source)
        if int(major_text) != major:
            raise ErgasterionRouteError(
                f"declared consumer pin {reference} does not match the producer major {major}"
            )


def _value_type(declared: object, published_name: str) -> tuple[SchemaValueType, int | None, int | None]:
    if isinstance(declared, str) and declared in SCALAR_VALUE_TYPES:
        return SCALAR_VALUE_TYPES[declared], None, None
    if isinstance(declared, dict) and declared.get("name") == DECIMAL_TYPE_NAME:
        precision = declared.get("precision")
        scale = declared.get("scale")
        if (
            isinstance(precision, int)
            and not isinstance(precision, bool)
            and isinstance(scale, int)
            and not isinstance(scale, bool)
        ):
            return SchemaValueType.DECIMAL, precision, scale
    raise ErgasterionRouteError(f"generated contract declares an unmappable field type: {published_name}")


def _contract_relation(artefacts: _ProductArtefacts, relation: str) -> list[Any]:
    relations = artefacts.contract_document.get("relations")
    if isinstance(relations, list):
        for entry in relations:
            if isinstance(entry, dict) and entry.get("name") == relation:
                fields = entry.get("fields")
                if isinstance(fields, list) and fields:
                    return fields
    raise ErgasterionRouteError(f"generated contract does not publish the relation: {relation}")


def _schema_declaration(
    artefacts: _ProductArtefacts,
    relation: str,
    version: str,
    roles: Mapping[str, str],
) -> SchemaDeclaration:
    fields: list[SchemaField] = []
    for entry in _contract_relation(artefacts, relation):
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str) or not entry["name"]:
            raise ErgasterionRouteError(f"generated contract has an unnamed field: {relation}")
        value_type, precision, scale = _value_type(entry.get("type"), relation)
        fields.append(
            SchemaField(
                field_id=entry["name"],
                value_type=value_type,
                nullable=entry.get("required") is not True,
                semantic_role=roles.get(entry["name"], DECLARED_FIELD_ROLE),
                precision=precision,
                scale=scale,
            )
        )
    return SchemaDeclaration(
        schema_id=relation,
        version=version,
        fields=tuple(fields),
        format_name=str(artefacts.contract_document.get("schema", "")),
    )


def _grain_declaration(
    artefacts: _ProductArtefacts, node: ProductNodeRecord, relation: str, version: str
) -> GrainDeclaration:
    materialisation = artefacts.manifest_document.get("materialisation")
    if not isinstance(materialisation, dict):
        raise ErgasterionRouteError(f"generated manifest has no materialisation: {node.published_name}")
    keys = materialisation.get("unique_key")
    if not isinstance(keys, list) or not all(isinstance(key, str) and key for key in keys):
        raise ErgasterionRouteError(f"generated manifest has an invalid unique key: {node.published_name}")
    return GrainDeclaration(
        grain_id=relation,
        version=version,
        key_fields=tuple(keys),
        population_description=(
            f"{node.generation} generation relation published by {node.published_name} "
            f"with {materialisation.get('intent', 'undeclared')} materialisation"
        ),
        duplicate_keys_permitted=not keys,
    )


def _adjacency(reading: ProductGraphReading) -> dict[str, tuple[str, ...]]:
    upstream: dict[str, list[str]] = {node.published_name: [] for node in reading.nodes}
    for edge in reading.edges:
        upstream[edge.target].append(edge.source)
    return {product: tuple(sources) for product, sources in upstream.items()}


def _nearest_checkpoint_relations(
    product: str,
    upstream: Mapping[str, tuple[str, ...]],
    checkpointed: Mapping[str, tuple[str, ...]],
    seen: frozenset[str],
) -> tuple[str, ...]:
    """The checkpointed relations closest above one product, following edges."""
    found: list[str] = []
    for source in upstream.get(product, ()):
        if source in seen:
            continue
        relations = checkpointed.get(source, ())
        if relations:
            found.extend(relations)
            continue
        found.extend(
            _nearest_checkpoint_relations(source, upstream, checkpointed, seen | {source})
        )
    return tuple(dict.fromkeys(found))


def _lineage_definition(
    declaration: ExactGenerationContract,
    reading: ProductGraphReading,
    products: Mapping[str, _ProductArtefacts],
    graph_digest: str,
) -> LineageDefinition:
    """Map nodes, edges, field lineage and checkpoint relations into the domain."""
    nodes = {node.published_name: node for node in reading.nodes}
    owner_of = {relation: node for node in reading.nodes for relation in node.relations}
    checkpointed = {
        node.published_name: tuple(relation for relation in node.relations if node.checkpoint)
        for node in reading.nodes
    }
    upstream = _adjacency(reading)
    roles: dict[str, dict[str, str]] = {}
    for row in reading.field_lineage:
        roles.setdefault(row.product, {})[row.target_field] = row.source_kind

    # Graph coverage has already refused a checkpoint relation that no node
    # publishes, so every checkpointed relation resolves to its owning product.
    checkpoints: list[Checkpoint] = []
    for relation in reading.checkpoint_relations:
        node = owner_of[relation]
        artefacts = products[node.published_name]
        version = f"v{_producer_major(artefacts, node.published_name)}"
        checkpoints.append(
            Checkpoint(
                checkpoint_id=relation,
                version=version,
                parent_ids=_nearest_checkpoint_relations(
                    node.published_name, upstream, checkpointed, frozenset({node.published_name})
                ),
                expected_state=Identity(
                    identifier=relation, version=version, digest=artefacts.contract_digest
                ),
                schema=_schema_declaration(
                    artefacts, relation, version, roles.get(node.published_name, {})
                ),
                grain=_grain_declaration(artefacts, node, relation, version),
                canonicalisation=declaration.canonicalisation,
                transformation=Identity(
                    identifier=node.published_name, version=version, digest=artefacts.manifest_digest
                ),
                provenance=Identity(
                    identifier=reading.schema,
                    version=declaration.identity.version,
                    digest=graph_digest,
                ),
                diagnostic_evidence=(),
                replay=None,
            )
        )

    sinks = {node.published_name for node in reading.nodes} - {edge.source for edge in reading.edges}
    bindings: list[OutputLineageBinding] = []
    for published_name in reading.order:
        if published_name not in sinks:
            continue
        node = nodes[published_name]
        for relation in node.relations:
            terminal = relation if node.checkpoint else None
            if terminal is None:
                nearest = _nearest_checkpoint_relations(
                    published_name, upstream, checkpointed, frozenset({published_name})
                )
                terminal = nearest[0] if nearest else None
            bindings.append(
                OutputLineageBinding(expected_output_id=relation, terminal_checkpoint_id=terminal)
            )
    return LineageDefinition(
        lineage_id=declaration.identity.identifier,
        version=declaration.identity.version,
        checkpoints=tuple(checkpoints),
        output_bindings=tuple(bindings),
    )


def _artefact_digests(estate: Path) -> tuple[tuple[str, str], ...]:
    """Digest every artefact this route reads, named by its estate identity."""
    digests: list[tuple[str, str]] = []
    for directory in READ_DIRECTORIES:
        root = estate / directory
        if not root.is_dir():
            raise ErgasterionRouteError(f"generated artefact directory is missing: {directory}")
        for path in sorted(root.rglob("*")):
            if path.is_file():
                digests.append(
                    (path.relative_to(estate).as_posix(), _digest(path.read_bytes()))
                )
    return tuple(digests)


def _read_generation(
    declaration: ExactGenerationContract, estate: Path, *, actor: str
) -> GeneratedEstate:
    reading = _read_product_graph(estate)
    digests = _artefact_digests(estate)
    products = {node.published_name: _read_product_artefacts(estate, node) for node in reading.nodes}
    _refuse_consumer_pin_drift(reading, products)
    graph_digest = _digest(_artefact_bytes(estate, GRAPH_DESCRIPTION))
    return GeneratedEstate(
        contract_identity=declaration.identity,
        generated_by=actor,
        graph=reading,
        lineage=_lineage_definition(declaration, reading, products, graph_digest),
        artefact_digests=digests,
    )
