"""Project one use-case segment into an Ergasterion product declaration draft.

The draft is a proposal, never a live declaration. It is recorded as a
proposal reference carrying a reviewer identity and an adjudicated
disposition, and nothing here writes into an estate: this module imports no
filesystem, process or delivery-tool module at all. A separate, later route
generates from an approved declaration once a distinct reviewer has accepted
one.

Nothing is invented. Every step the draft emits is implied by a declaration
the segment carries, every operational value it states comes from a standing
condition or its recorded default, and a value with no owning condition is
named in the proposal notes rather than carried in silence. A calculated
field's expression is never derived from an intermediate result's
description: it is supplied whole by the caller, because a separate, narrow
capability owns parsing a transformation rule into one.

Which declaration implies which pattern is stated once, in
``PATTERN_IMPLICATIONS``. Which patterns a layer's composition profile makes
mandatory and forbids is adapter knowledge, stated once in
``LAYER_PROFILES``: a layer that table does not name is refused, never
accepted unchecked, and a mandatory pattern no declaration implies is
refused naming the declaration that is missing.

The rendered document is written as indented JSON, which is one valid form of
YAML, rather than through a hand-rolled YAML serializer or an added YAML
library dependency in the base package. The installed Ergasterion reads it
exactly like any other declaration file.

The retention, classification and volume/performance ("layout") standing
conditions carry no slot in the installed declaration schema, so they are
never dropped: they are named in the draft's proposal notes alongside every
condition the draft did carry, so a reviewer sees every fact in force without
consulting the use case again.
"""
from __future__ import annotations

# evorthon-component: delivery_adapters

import hashlib
import json
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from ..engagement.aggregate import ImmutableReference, ReferenceKind
from ..engagement.use_case import (
    Authority,
    AuthorityRole,
    BuildRoute,
    BuildRouteDeclaration,
    CONDITION_DEFAULTS,
    ConditionDeclaration,
    ConditionKey,
    ConditionState,
    ConsumerDependency,
    IntermediateResult,
    Segment,
    SegmentBoundary,
    StoredColumnName,
    TargetOutput,
)
from ..verification.domain import (
    EvidenceReference,
    FrozenDataset,
    Identity,
    SchemaField,
    SchemaValueType,
)
from .ergasterion import (
    DECIMAL_TYPE_NAME,
    GenerationDisposition,
    SCALAR_VALUE_TYPES,
    required_text,
)

# The neutral type names Ergasterion's declaration schema accepts, in the
# direction this module needs: writing a declared value type forward. Built
# from the generation route's own reading map so the vocabulary can never
# drift between the two directions.
WRITTEN_SCALAR_TYPES: Mapping[SchemaValueType, str] = MappingProxyType(
    {value: key for key, value in SCALAR_VALUE_TYPES.items()}
)

# The historisation kinds the intake record's block 11 declares (shaping
# record, "History and time"). Only "current only" maps to a shape this
# module can state without inventing entity, dimension or vault modelling
# content the use case does not carry; the other kinds are a refusal until
# the segment's own build route states a target shape directly.
HISTORISATION_SHAPE_MAP: Mapping[str, str] = MappingProxyType({"current only": "declared"})

# The closed value sets the installed pattern schemas state.
GRANULARITY_VALUES: tuple[str, ...] = ("step", "composition")
BACKOFF_VALUES: tuple[str, ...] = ("none", "fixed", "exponential")
FAILURE_POLICIES: tuple[str, ...] = ("quarantine", "abort", "warn")
QUARANTINE_POLICY = "quarantine"

# The publication mode has no owning standing condition, and translation
# refuses a data_publish occurrence that declares none. A whole-relation
# swap is the only mode the declaration schema admits without a declared
# unique key, so it is what the draft carries, stated in the proposal notes
# rather than applied in silence.
STATED_PUBLICATION_MODE = "atomic"

# checkpoint_retries is the one pattern that is never a step: it is the
# top-level checkpointing block.
CHECKPOINT_RETRIES = "checkpoint_retries"


@dataclass(frozen=True)
class LayerProfile:
    """What one estate layer label's composition profile admits.

    The installed profile files are the source; this table is the adapter's
    record of them, so a draft is refused here for the same reason the tool
    would refuse it, before any estate exists. ``mandatory``, ``optional``,
    ``forbidden`` and ``ordering`` are carried exactly as the profile states
    them; a pattern in none of the three dispositions is one the profile
    leaves unclassified, and the draft never emits it.
    """

    profile: str
    mandatory: tuple[str, ...]
    optional: tuple[str, ...]
    forbidden: tuple[str, ...]
    ordering: tuple[str, ...]

    def refuse_unadmitted(self, patterns: Iterable[str], *, layer: str) -> None:
        """Refuse a pattern this profile forbids or does not classify."""
        for pattern in patterns:
            if pattern in self.forbidden:
                raise DeclarationDraftError(
                    f"layer {layer!r} composes profile {self.profile!r}, which forbids pattern {pattern!r}"
                )
            if pattern not in self.mandatory and pattern not in self.optional:
                raise DeclarationDraftError(
                    f"layer {layer!r} composes profile {self.profile!r}, which does not classify pattern {pattern!r}"
                )

    def refuse_missing_mandatory(self, patterns: Iterable[str], *, layer: str) -> None:
        """Refuse when a mandatory pattern no declaration implies is absent."""
        implied = set(patterns)
        for pattern in self.mandatory:
            if pattern == CHECKPOINT_RETRIES or pattern in implied:
                continue
            implication = PATTERN_IMPLICATIONS.get(pattern)
            missing = f"; this segment declares no {implication}" if implication else ""
            raise DeclarationDraftError(
                f"layer {layer!r} composes profile {self.profile!r}, which requires pattern "
                f"{pattern!r}{missing}"
            )

    def ordered(self, bodies: Mapping[str, dict[str, Any]]) -> list[dict[str, Any]]:
        """The implied steps in the order this profile composes them."""
        return [bodies[pattern] for pattern in self.ordering if pattern in bodies]


# This adapter supports the estate's derivation profile.
# An unmapped layer is refused with a closed reason.
LAYER_PROFILES: Mapping[str, LayerProfile] = MappingProxyType(
    {
        "derived": LayerProfile(
            profile="derivation",
            mandatory=(
                "batch_transfer",
                "data_validation",
                "calculated_fields",
                "data_contracts",
                "lineage_capture",
                "metadata_capture",
                "schema_publish",
                "data_publish",
                CHECKPOINT_RETRIES,
            ),
            optional=("data_enrichment", "data_aggregation", "data_filtering"),
            forbidden=("batch_ingestion", "data_curation"),
            ordering=(
                "batch_transfer",
                "data_validation",
                "calculated_fields",
                "data_enrichment",
                "data_filtering",
                "data_aggregation",
                "data_contracts",
                "lineage_capture",
                "metadata_capture",
                "schema_publish",
                "data_publish",
                CHECKPOINT_RETRIES,
            ),
        )
    }
)

# The declaration each pattern is emitted for. A pattern whose declaration
# the segment does not carry is not emitted, and a mandatory one that is not
# implied is refused naming the entry below.
PATTERN_IMPLICATIONS: Mapping[str, str] = MappingProxyType(
    {
        "batch_transfer": "consumed source: no frozen input, contract pin or consumer dependency backs one",
        "data_validation": "schema expectation: no frozen input declares a field that cannot be null",
        "calculated_fields": (
            "calculation: the span passes through no intermediate result, and the "
            "caller supplies no computed field"
        ),
        "data_contracts": "target contract",
        "lineage_capture": "target contract",
        "metadata_capture": "accepting authority to own the published product",
        "schema_publish": "target shape",
        "data_publish": "target shape",
        CHECKPOINT_RETRIES: "run policy for the checkpointing block",
    }
)

# The standing conditions the installed declaration schema has no slot for
# at all. They are named in the proposal notes and nowhere else.
UNCARRIED_CONDITION_KEYS: tuple[ConditionKey, ...] = (
    ConditionKey.RETENTION_WINDOW,
    ConditionKey.HANDLING_CLASSIFICATION,
    ConditionKey.LOAD_VOLUME,
    ConditionKey.GROWTH_AND_PEAKS,
    ConditionKey.QUERY_PATTERN,
    ConditionKey.COST_CEILING,
)


class DeclarationDraftError(ValueError):
    """Raised when a segment cannot be projected, or a needed fact is missing."""


@dataclass(frozen=True)
class ProductPin:
    """A consumed contract this segment reads without a local fixture.

    ``expected_fields`` is optional: it names the fields this segment reads
    from the pinned contract when the caller already knows them, and is
    omitted from the rendered source otherwise.
    """

    domain: str
    product: str
    major_version: int
    expected_fields: tuple[str, ...] = ()

    @property
    def reference(self) -> str:
        """The ``domain.product@N`` contract reference this pin renders as."""
        return f"{self.domain}.{self.product}@{self.major_version}"


@dataclass(frozen=True)
class FixtureInput:
    """One frozen input dataset behind a fixture-backed source.

    ``pin`` is the declared contract reference the fixture stands in for
    locally (the installed schema requires one even for a fixture-kind
    source); its ``expected_fields`` is unused here, because a fixture
    source's visible fields are exactly the ones it declares, never a
    separately named subset. ``stored_column_names`` mirrors block 2's
    stored-name mechanism, applied here to this input's own fixture fields
    where the intake record declared one.
    """

    relation: str
    dataset: FrozenDataset
    pin: ProductPin
    stored_column_names: tuple[StoredColumnName, ...] = ()


@dataclass(frozen=True)
class ProposedCalculatedField:
    """One computed field a caller supplies whole for a segment's declaration.

    This module never derives ``expression`` from an intermediate result's
    description: a computed field is handed over complete by whichever
    capability already knows the transformation, a distinct, narrow adapter
    beside this one and the other delivery routes.
    """

    field_id: str
    value_type: SchemaValueType
    expression: str
    precision: int | None = None
    scale: int | None = None


@dataclass(frozen=True)
class SegmentDeclarationRequest:
    """Everything one segment's declaration draft is built from.

    ``fixture_inputs`` and ``upstream_pins`` are keyed by the source id
    ``segment.sources`` names; every id there must resolve through exactly
    one of them. ``intermediate_calculations`` is keyed by the intermediate
    result id ``segment.passes_through`` names: an intermediate result is a
    declared calculation on the span, so each one carries the calculated
    fields that realise it, and ``computed_fields`` extends the same step
    with fields no intermediate names.

    ``cut_version`` is the use case's version identifier once a version has
    been cut; when none has, ``draft_version`` carries a caller-supplied
    draft version and the proposal notes label it as one. Exactly one of the
    two is supplied.
    """

    segment: Segment
    authorities: tuple[Authority, ...] = ()
    cut_version: ImmutableReference | None = None
    draft_version: str | None = None
    fixture_inputs: Mapping[str, FixtureInput] = field(default_factory=dict)
    upstream_pins: Mapping[str, ProductPin] = field(default_factory=dict)
    consumer_dependencies: tuple[ConsumerDependency, ...] = ()
    conditions: tuple[ConditionDeclaration, ...] = ()
    target_output: TargetOutput | None = None
    boundary_result: IntermediateResult | None = None
    intermediate_calculations: Mapping[str, tuple[ProposedCalculatedField, ...]] = field(default_factory=dict)
    computed_fields: tuple[ProposedCalculatedField, ...] = ()


@dataclass(frozen=True)
class AdjudicatedDeclaration:
    """A proposed declaration with its reviewer identity and disposition.

    The disposition vocabulary is the Ergasterion adapter's, so a draft and a
    generation are adjudicated in one language and there is one owner of what
    a disposition means.
    """

    proposal: ProposedDeclaration
    reviewer: Identity
    disposition: GenerationDisposition

    def proposal_evidence(self) -> EvidenceReference:
        """Reference the drafted declaration as evidence, once it is accepted."""
        if self.disposition is not GenerationDisposition.ACCEPTED:
            raise DeclarationDraftError(
                "a declaration draft is referenced as evidence only after an accepted adjudication"
            )
        return EvidenceReference(
            evidence_id=self.proposal.reference.identifier,
            version=self.proposal.reference.version,
            digest=self.proposal.reference.digest,
            summary=(
                f"drafted by {self.proposal.drafted_by} and reviewed by {self.reviewer.identifier}"
            ),
        )


@dataclass(frozen=True)
class ProposedDeclaration:
    """One declaration draft recorded as a proposal reference.

    The reference names the drafted document by identity, version and content
    digest. Nothing is written anywhere: the record is the proposal, and the
    estate only ever sees a declaration a reviewer has accepted.
    """

    draft: ProductDeclarationDraft
    reference: Identity
    drafted_by: str

    def adjudicated(
        self, *, reviewer: Identity, disposition: GenerationDisposition
    ) -> AdjudicatedDeclaration:
        """Attach a distinct reviewer identity and an adjudicated disposition."""
        if not isinstance(reviewer, Identity):
            raise DeclarationDraftError("a declaration draft reviewer must be a declared identity")
        _nonempty_text(reviewer.identifier, "declaration draft reviewer identifier")
        _nonempty_text(reviewer.version, "declaration draft reviewer version")
        _nonempty_text(reviewer.digest, "declaration draft reviewer digest")
        if not isinstance(disposition, GenerationDisposition):
            raise DeclarationDraftError("a declaration draft disposition must be an adjudicated disposition")
        if reviewer.identifier == self.drafted_by:
            raise DeclarationDraftError(
                "a declaration draft reviewer must be distinct from the drafting actor"
            )
        return AdjudicatedDeclaration(proposal=self, reviewer=reviewer, disposition=disposition)


@dataclass(frozen=True)
class ProductDeclarationDraft:
    """A draft product declaration: its rendered document and its structure.

    ``document`` is the plain nested mapping the installed product-declaration
    JSON schema validates directly. ``yaml_text`` is that same document
    rendered for the file an estate would read. ``proposal_notes`` names every
    standing condition the draft carried and every one it could not, and every
    value the draft states that no condition owns.
    """

    file_name: str
    document: Mapping[str, Any]
    yaml_text: str
    proposal_notes: tuple[str, ...]
    checkpoint: bool

    @property
    def content_digest(self) -> str:
        """The digest of the drafted document, as the proposal reference states it."""
        return "sha256:" + hashlib.sha256(self.yaml_text.encode("utf-8")).hexdigest()

    def proposed(self, *, proposal_id: str, version: str, drafted_by: str) -> ProposedDeclaration:
        """Record this draft as a proposal reference, awaiting adjudication."""
        reference = Identity(
            identifier=_nonempty_text(proposal_id, "declaration proposal identifier"),
            version=_nonempty_text(version, "declaration proposal version"),
            digest=self.content_digest,
        )
        return ProposedDeclaration(
            draft=self,
            reference=reference,
            drafted_by=_nonempty_text(drafted_by, "declaration drafting actor"),
        )


def draft_declaration(request: SegmentDeclarationRequest) -> ProductDeclarationDraft:
    """Draft one product declaration from an already-resolved segment request.

    Refuses, by reason, a segment with no build route, a route that is not
    generated, a layer no profile table maps, a missing accepting authority, a
    source with nothing to declare it, a frozen input with no schema
    declaration, an unmappable field type, an unmappable historisation kind
    where the route leaves the shape open, a standing condition value the
    installed pattern schemas cannot accept, and a mandatory pattern the
    segment's declarations do not imply.
    """
    segment = _segment(request.segment)
    route = _generated_route(segment)
    profile = _layer_profile(route)
    owner = _owner(request.authorities)
    _validate_boundary(segment, request)
    conditions = request.conditions

    name = _file_stem(segment.segment_id)
    fixtures = _ordered_fixtures(request)
    sources = _sources(request, fixtures)
    steps = _steps(request, fixtures, sources, profile=profile, layer=route.layer, owner=owner)
    document: dict[str, Any] = {
        "product": {
            "name": name,
            "domain": route.product_domain,
            "version": _product_version(request),
            "layer": route.layer,
            "owner": owner,
        },
        "sources": sources,
        "steps": steps,
        "target": {
            "shape": _resolve_shape(route, conditions),
            "contract": {"freshness": _condition_text(conditions, ConditionKey.FRESHNESS_DEADLINE)},
        },
        "checkpointing": _checkpointing_block(conditions, request.boundary_result),
    }
    physical = _physical_block(request.target_output)
    if physical is not None:
        document["physical"] = physical

    return ProductDeclarationDraft(
        file_name=f"{name}.yml",
        document=document,
        yaml_text=json.dumps(document, indent=2) + "\n",
        proposal_notes=_proposal_notes(request, steps),
        checkpoint=_is_checkpoint(request.boundary_result),
    )


def _nonempty_text(value: object, label: str) -> str:
    return required_text(value, label, error=DeclarationDraftError)


def _segment(value: object) -> Segment:
    if not isinstance(value, Segment):
        raise DeclarationDraftError("a declaration draft requires a derived use-case segment")
    return value


def _generated_route(segment: Segment) -> BuildRouteDeclaration:
    route = segment.route
    if route is None:
        raise DeclarationDraftError(f"segment {segment.segment_id!r} has no declared build route")
    if not isinstance(route, BuildRouteDeclaration) or route.route is not BuildRoute.GENERATED:
        raise DeclarationDraftError(
            f"segment {segment.segment_id!r} is not a generated segment; "
            "only a generated route projects into an Ergasterion declaration draft"
        )
    if not route.layer:
        raise DeclarationDraftError(f"segment {segment.segment_id!r} names no layer label to generate into")
    return route


def _layer_profile(route: BuildRouteDeclaration) -> LayerProfile:
    profile = LAYER_PROFILES.get(str(route.layer))
    if profile is None:
        raise DeclarationDraftError(
            f"layer {route.layer!r} has no profile mapping; this adapter maps "
            + ", ".join(sorted(LAYER_PROFILES))
        )
    return profile


def _owner(authorities: tuple[Authority, ...]) -> str:
    for authority in authorities:
        if isinstance(authority, Authority) and authority.role is AuthorityRole.ACCEPTING:
            return authority.actor.identity
    raise DeclarationDraftError("a generated segment needs a named accepting authority to draft a product owner")


def _validate_boundary(segment: Segment, request: SegmentDeclarationRequest) -> None:
    """Check the segment's own boundary declaration against what was supplied."""
    if segment.reaches is SegmentBoundary.TARGET_OUTPUT:
        target = request.target_output
        if not isinstance(target, TargetOutput) or target.output_id != segment.segment_id:
            raise DeclarationDraftError(f"segment {segment.segment_id!r} needs its own declared target output")
        if request.boundary_result is not None:
            raise DeclarationDraftError(
                f"segment {segment.segment_id!r} reaches a target output and carries no intermediate result"
            )
        return
    result = request.boundary_result
    if not isinstance(result, IntermediateResult) or result.result_id != segment.segment_id:
        raise DeclarationDraftError(
            f"segment {segment.segment_id!r} needs the declared intermediate result it reaches"
        )
    if request.target_output is not None:
        raise DeclarationDraftError(f"segment {segment.segment_id!r} is a checkpoint and carries no target output")


def _is_checkpoint(boundary_result: IntermediateResult | None) -> bool:
    return isinstance(boundary_result, IntermediateResult) and boundary_result.checkpoint_candidate


def _product_version(request: SegmentDeclarationRequest) -> str:
    cut = request.cut_version
    if cut is not None:
        if not isinstance(cut, ImmutableReference) or cut.kind is not ReferenceKind.USE_CASE_VERSION:
            raise DeclarationDraftError("a cut version must be named by use_case_version identity")
        if request.draft_version is not None:
            raise DeclarationDraftError(
                "a segment whose use case has a cut version carries no separate draft version"
            )
        return cut.version
    return _nonempty_text(request.draft_version, "draft product version")


def _file_stem(segment_id: str) -> str:
    _nonempty_text(segment_id, "segment identity")
    if "/" in segment_id or "\\" in segment_id or segment_id.startswith("."):
        raise DeclarationDraftError(f"segment identity {segment_id!r} cannot name a declaration file")
    return segment_id


def _written_type(value_type: SchemaValueType, precision: int | None, scale: int | None, field_id: str) -> object:
    if value_type is SchemaValueType.DECIMAL:
        if precision is None or scale is None:
            raise DeclarationDraftError(f"field {field_id!r} declares a decimal with no precision and scale")
        return {"name": DECIMAL_TYPE_NAME, "precision": precision, "scale": scale}
    written = WRITTEN_SCALAR_TYPES.get(value_type)
    if written is None:
        value_name = getattr(value_type, "value", value_type)
        raise DeclarationDraftError(f"field {field_id!r} declares a value type Ergasterion cannot accept: {value_name!r}")
    return written


def _ordered_fixtures(request: SegmentDeclarationRequest) -> tuple[FixtureInput, ...]:
    """The fixture-backed inputs in the order the segment names its sources."""
    return tuple(
        request.fixture_inputs[source_id]
        for source_id in request.segment.sources
        if source_id in request.fixture_inputs
    )


def _fixture_source(fixture: FixtureInput) -> dict[str, Any]:
    if not isinstance(fixture.dataset, FrozenDataset) or not fixture.dataset.schema.fields:
        raise DeclarationDraftError("a frozen input with no schema declaration cannot back a fixture source")
    stored = {column.field_id: column.stored_name for column in fixture.stored_column_names}
    fields: list[dict[str, Any]] = []
    for schema_field in fixture.dataset.schema.fields:
        if not isinstance(schema_field, SchemaField):
            raise DeclarationDraftError("a frozen input with no schema declaration cannot back a fixture source")
        entry: dict[str, Any] = {
            "name": schema_field.field_id,
            "type": _written_type(schema_field.value_type, schema_field.precision, schema_field.scale, schema_field.field_id),
        }
        physical_name = stored.get(schema_field.field_id)
        if physical_name is not None:
            entry["physical_name"] = physical_name
        fields.append(entry)
    return {
        "contract": fixture.pin.reference,
        "kind": "fixture",
        "fixture": {"relation": _nonempty_text(fixture.relation, "fixture relation name"), "fields": fields},
        # Every field the fixture declares must be named here: a later step
        # can reference a source field only when it is visible, and
        # visibility is exactly this declared field list, never inferred.
        "expect": {"fields": [entry["name"] for entry in fields]},
    }


def _pin_source(pin: ProductPin) -> dict[str, Any]:
    source: dict[str, Any] = {"contract": pin.reference}
    if pin.expected_fields:
        source["expect"] = {"fields": list(pin.expected_fields)}
    return source


def _dependency_source(dependency: ConsumerDependency) -> dict[str, Any]:
    if not isinstance(dependency, ConsumerDependency):
        raise DeclarationDraftError("a consumer dependency must be a declared consumer dependency")
    major_text = dependency.major_version[1:] if dependency.major_version[:1] == "v" else dependency.major_version
    return {"contract": f"{dependency.product_id}@{major_text}"}


def _sources(request: SegmentDeclarationRequest, fixtures: tuple[FixtureInput, ...]) -> list[dict[str, Any]]:
    """Every consumed source the span declares, refused when more than one is declared.

    A declaration that consumes two or more sources must also say how they
    combine, and the use case declares nothing that says: no intermediate
    result kind, no build-route field and no target-output definition source
    states a combination method. The draft therefore refuses a span with more
    than one source rather than emitting a declaration the estate would
    reject. Each source is still declared and checked first, so a malformed
    one is refused as malformed.
    """
    sources: list[dict[str, Any]] = []
    for source_id in request.segment.sources:
        if source_id in request.fixture_inputs:
            sources.append(_fixture_source(request.fixture_inputs[source_id]))
        elif source_id in request.upstream_pins:
            sources.append(_pin_source(request.upstream_pins[source_id]))
        else:
            raise DeclarationDraftError(
                f"segment source {source_id!r} has no frozen input or contract pin to declare it with"
            )
    for dependency in request.consumer_dependencies:
        sources.append(_dependency_source(dependency))
    if len(sources) > 1:
        raise DeclarationDraftError(
            f"segment {request.segment.segment_id!r} consumes {len(sources)} sources, and the use "
            "case states no method for combining them; a declaration over more than one source "
            "needs a declared combination, and the intake record carries none"
        )
    return sources


def _validation_rules(fixtures: tuple[FixtureInput, ...], completeness: float) -> list[dict[str, Any]]:
    """One completeness rule per fixture field the frozen input says cannot be null."""
    rules: dict[str, dict[str, Any]] = {}
    for fixture in fixtures:
        for schema_field in fixture.dataset.schema.fields:
            if not schema_field.nullable and schema_field.field_id not in rules:
                rules[schema_field.field_id] = {"field": schema_field.field_id, "completeness": completeness}
    return list(rules.values())


def _calculated_field(computed: object) -> dict[str, Any]:
    if not isinstance(computed, ProposedCalculatedField):
        raise DeclarationDraftError("a computed field must be a proposed calculated field")
    field_id = _nonempty_text(computed.field_id, "computed field identity")
    return {
        "name": field_id,
        "type": _written_type(computed.value_type, computed.precision, computed.scale, field_id),
        "expression": _nonempty_text(computed.expression, f"computed field {field_id!r} expression"),
    }


def _calculated_fields(request: SegmentDeclarationRequest) -> list[dict[str, Any]]:
    """The calculation the span declares: its intermediate results, then the caller's own fields.

    Each intermediate result the span passes through is a declared
    calculation, so each carries the calculated fields that realise it. An
    intermediate with none supplied is an integrity refusal: the declaration
    the span carries has no answer, and inventing one from its description is
    not this module's to do.
    """
    supplied = request.intermediate_calculations
    passes_through = request.segment.passes_through
    unknown = [result_id for result_id in supplied if result_id not in passes_through]
    if unknown:
        raise DeclarationDraftError(
            f"calculated fields are supplied for {unknown[0]!r}, which segment "
            f"{request.segment.segment_id!r} does not pass through"
        )
    fields: list[dict[str, Any]] = []
    seen: set[str] = set()
    for result_id in passes_through:
        realised = supplied.get(result_id)
        if not realised:
            raise DeclarationDraftError(
                f"intermediate result {result_id!r} declares a calculation, and no calculated "
                "field is supplied to realise it"
            )
        for computed in realised:
            fields.append(_calculated_field(computed))
    for computed in request.computed_fields:
        fields.append(_calculated_field(computed))
    for entry in fields:
        if entry["name"] in seen:
            raise DeclarationDraftError(f"computed field {entry['name']!r} is declared twice")
        seen.add(entry["name"])
    return fields


def _steps(
    request: SegmentDeclarationRequest,
    fixtures: tuple[FixtureInput, ...],
    sources: list[dict[str, Any]],
    *,
    profile: LayerProfile,
    layer: str,
    owner: str,
) -> list[dict[str, Any]]:
    """Exactly the steps the segment's declarations imply, in the profile's order."""
    conditions = request.conditions
    bodies: dict[str, dict[str, Any]] = {}
    if sources:
        bodies["batch_transfer"] = {"pattern": "batch_transfer"}
    rules = _validation_rules(fixtures, _completeness(conditions))
    if rules:
        validation: dict[str, Any] = {
            "pattern": "data_validation",
            "rules": rules,
            "on_failure": _failure_policy(conditions),
        }
        if validation["on_failure"] == QUARANTINE_POLICY:
            validation["error_threshold"] = _error_threshold(conditions)
        bodies["data_validation"] = validation
    calculated = _calculated_fields(request)
    if calculated:
        bodies["calculated_fields"] = {"pattern": "calculated_fields", "fields": calculated}
    # Every declaration carries a target block: a shape and the contract the
    # published product answers with. That target is what the publication
    # phase is emitted for, and the owner is what the metadata occurrence
    # records. A segment that cannot state one is already refused above.
    bodies["data_contracts"] = {"pattern": "data_contracts"}
    bodies["lineage_capture"] = {"pattern": "lineage_capture"}
    bodies["metadata_capture"] = {"pattern": "metadata_capture", "ownership": owner}
    bodies["schema_publish"] = {"pattern": "schema_publish"}
    bodies["data_publish"] = {"pattern": "data_publish", "publication_mode": STATED_PUBLICATION_MODE}
    profile.refuse_unadmitted(bodies, layer=layer)
    profile.refuse_missing_mandatory(bodies, layer=layer)
    return profile.ordered(bodies)


def _effective_condition(conditions: tuple[ConditionDeclaration, ...], key: ConditionKey) -> ConditionDeclaration | None:
    for condition in conditions:
        if isinstance(condition, ConditionDeclaration) and condition.key is key:
            return condition
    return None


def _condition_text(conditions: tuple[ConditionDeclaration, ...], key: ConditionKey) -> str:
    condition = _effective_condition(conditions, key)
    if condition is None:
        return CONDITION_DEFAULTS[key]
    return condition.effective_value


def _condition_note(conditions: tuple[ConditionDeclaration, ...], key: ConditionKey, carried: str) -> str:
    """One condition, the value in force, and where that value came from.

    An unanswered condition a named human overrode carries the override's
    value, so the note names its author rather than calling it a default.
    """
    condition = _effective_condition(conditions, key)
    if condition is None:
        label = "default"
    elif condition.state is ConditionState.DECLARED:
        label = "declared"
    elif condition.override is not None:
        label = f"overridden by {condition.override.author.identity}"
    else:
        label = "default"
    return f"{key.value}: {_condition_text(conditions, key)} ({label}), {carried}"


def _fraction(text: str) -> float | None:
    """A declared proportion between zero and one, or nothing when it is not one."""
    if not text.isascii():
        return None
    whole, dot, fractional = text.partition(".")
    if not whole.isdigit() or (dot and not fractional.isdigit()):
        return None
    value = float(text)
    return value if 0.0 <= value <= 1.0 else None


def _proportion(conditions: tuple[ConditionDeclaration, ...], key: ConditionKey, named_reading: float) -> float:
    """A quality condition read as the proportion the pattern schema takes."""
    text = _condition_text(conditions, key)
    if text == CONDITION_DEFAULTS[key]:
        return named_reading
    value = _fraction(text)
    if value is None:
        raise DeclarationDraftError(
            f"{key.value} {text!r} states no proportion Ergasterion can accept; declare "
            f"{CONDITION_DEFAULTS[key]!r} or a proportion between 0 and 1"
        )
    return value


def _completeness(conditions: tuple[ConditionDeclaration, ...]) -> float:
    """The completeness a validation rule requires, from the completeness expectation."""
    return _proportion(conditions, ConditionKey.COMPLETENESS_EXPECTATION, 1.0)


def _error_threshold(conditions: tuple[ConditionDeclaration, ...]) -> float:
    """The proportion of failing rows a quarantining run tolerates, from the accepted defects."""
    return _proportion(conditions, ConditionKey.ACCEPTED_SOURCE_DEFECTS, 0.0)


def _failure_policy(conditions: tuple[ConditionDeclaration, ...]) -> str:
    """The on-failure policy, from the declared warning and failure classes.

    The recorded default treats every difference as a failure, which is the
    policy that stops the run. A use case that answers with one of the
    policies by name states it directly; anything else is a refusal, because
    reading a policy out of free text would be an invention.
    """
    text = _condition_text(conditions, ConditionKey.WARNING_AND_FAILURE_CLASSES)
    if text == CONDITION_DEFAULTS[ConditionKey.WARNING_AND_FAILURE_CLASSES]:
        return "abort"
    if text in FAILURE_POLICIES:
        return text
    raise DeclarationDraftError(
        f"warning_and_failure_classes {text!r} states no failure policy Ergasterion can accept; "
        f"declare {CONDITION_DEFAULTS[ConditionKey.WARNING_AND_FAILURE_CLASSES]!r} or one of "
        + ", ".join(FAILURE_POLICIES)
    )


def _proposal_notes(request: SegmentDeclarationRequest, steps: list[dict[str, Any]]) -> tuple[str, ...]:
    """Every condition in force and every stated value no condition owns."""
    conditions = request.conditions
    notes: list[str] = []
    if request.cut_version is not None:
        notes.append(f"product version: {request.cut_version.version} (the use case's cut version)")
    else:
        notes.append(
            f"product version: {request.draft_version} (a caller-supplied draft version; "
            "no use-case version has been cut)"
        )
    notes.append(
        f"publication_mode: {STATED_PUBLICATION_MODE} (no standing condition owns it; it is the "
        "only mode the declaration schema admits without a declared unique key)"
    )
    notes.append(_condition_note(conditions, ConditionKey.FRESHNESS_DEADLINE, "carried as target.contract.freshness"))
    validation = next((step for step in steps if step["pattern"] == "data_validation"), None)
    if validation is None:
        notes.append(
            _condition_note(conditions, ConditionKey.WARNING_AND_FAILURE_CLASSES, "not carried: no validation occurrence")
        )
        notes.append(
            _condition_note(conditions, ConditionKey.ACCEPTED_SOURCE_DEFECTS, "not carried: no validation occurrence")
        )
        notes.append(
            _condition_note(conditions, ConditionKey.COMPLETENESS_EXPECTATION, "not carried: no validation occurrence")
        )
    else:
        notes.append(
            _condition_note(
                conditions,
                ConditionKey.WARNING_AND_FAILURE_CLASSES,
                f"carried as data_validation.on_failure {validation['on_failure']}",
            )
        )
        if "error_threshold" in validation:
            defects = f"carried as data_validation.error_threshold {validation['error_threshold']}"
        else:
            defects = f"not carried: the {validation['on_failure']} policy takes no error threshold"
        notes.append(_condition_note(conditions, ConditionKey.ACCEPTED_SOURCE_DEFECTS, defects))
        notes.append(
            _condition_note(
                conditions,
                ConditionKey.COMPLETENESS_EXPECTATION,
                f"carried as the data_validation completeness {validation['rules'][0]['completeness']}",
            )
        )
    for key, carried in (
        (ConditionKey.CHECKPOINT_GRANULARITY, "carried as checkpointing.granularity"),
        (ConditionKey.MAX_RETRIES, "carried as checkpointing.max_retries"),
        (ConditionKey.BACKOFF, "carried as checkpointing.backoff"),
    ):
        notes.append(_condition_note(conditions, key, carried))
    for key in UNCARRIED_CONDITION_KEYS:
        notes.append(_condition_note(conditions, key, "not carried: the declaration schema has no slot for it"))
    return tuple(notes)


def _resolve_shape(route: BuildRouteDeclaration, conditions: tuple[ConditionDeclaration, ...]) -> str:
    if route.target_shape:
        return route.target_shape
    value = _condition_text(conditions, ConditionKey.HISTORISATION_KIND)
    shape = HISTORISATION_SHAPE_MAP.get(value)
    if shape is None:
        raise DeclarationDraftError(
            f"historisation kind {value!r} has no mapped Ergasterion shape; "
            f"declare segment {route.segment_id!r}'s target shape directly"
        )
    return shape


def _checkpointing_block(
    conditions: tuple[ConditionDeclaration, ...], boundary_result: IntermediateResult | None
) -> dict[str, Any]:
    granularity = _condition_text(conditions, ConditionKey.CHECKPOINT_GRANULARITY)
    if granularity not in GRANULARITY_VALUES:
        raise DeclarationDraftError(f"checkpoint granularity {granularity!r} is not one Ergasterion accepts")
    backoff = _condition_text(conditions, ConditionKey.BACKOFF)
    if backoff not in BACKOFF_VALUES:
        raise DeclarationDraftError(f"backoff {backoff!r} is not one Ergasterion accepts")
    retries_text = _condition_text(conditions, ConditionKey.MAX_RETRIES)
    if not retries_text.isascii() or not retries_text.isdigit():
        raise DeclarationDraftError(f"max retries {retries_text!r} is not a declarable non-negative integer")
    block: dict[str, Any] = {"granularity": granularity, "max_retries": int(retries_text), "backoff": backoff}
    if _is_checkpoint(boundary_result):
        block["checkpoint"] = True
    return block


def _physical_block(target_output: TargetOutput | None) -> dict[str, Any] | None:
    if target_output is None:
        return None
    block: dict[str, Any] = {}
    if target_output.stored_name is not None:
        block["name"] = target_output.stored_name
    if target_output.stored_column_names:
        block["fields"] = [
            {"name": column.field_id, "physical_name": column.stored_name}
            for column in target_output.stored_column_names
        ]
    return block or None
