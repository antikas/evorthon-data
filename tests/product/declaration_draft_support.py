"""Declared values the declaration-draft proofs are built from.

One owner for the builders both the hermetic proof and the live proof need,
so the two never drift. Nothing here imports a delivery tool, a schema
library or the synthetic generator at module level: the public candidate
imports this module while it runs the suite without any of them.
"""
from __future__ import annotations

from evorthon_data.delivery.declaration_draft import (
    FixtureInput,
    ProductPin,
    ProposedCalculatedField,
    SegmentDeclarationRequest,
)
from evorthon_data.engagement import (
    Actor,
    ActorKind,
    FactLocator,
    FactProvenance,
    FactStatus,
    ImmutableReference,
    ReferenceKind,
    TargetOutput,
)
from evorthon_data.engagement.use_case import (
    Authority,
    AuthorityRole,
    BuildRoute,
    BuildRouteDeclaration,
    CONDITION_DEFAULTS,
    ConditionDeclaration,
    ConditionKey,
    ConditionOverride,
    ConditionState,
    IntermediateResult,
    Segment,
    SegmentBoundary,
)
from evorthon_data.verification.domain.contracts import (
    CanonicalisationDeclaration,
    DatasetProvenance,
    DatasetRole,
    FrozenDataset,
    GrainDeclaration,
    Identity,
    SchemaDeclaration,
    SchemaField,
    SchemaValueType,
)

SEGMENT_ID = "risk-settled-positions"
SOURCE_ID = "raw-risk-position-feed"
INTERMEDIATE_ID = "settlement-normalisation"


def reference(kind: ReferenceKind, identifier: str) -> ImmutableReference:
    return ImmutableReference(kind=kind, identifier=identifier, version="v1", digest=f"digest-{identifier}")


def identity(identifier: str, version: str = "v1") -> Identity:
    return Identity(identifier=identifier, version=version, digest=f"digest-{identifier}")


def human(name: str = "accepting-authority") -> Actor:
    return Actor(identity=name, kind=ActorKind.HUMAN)


def model(name: str = "intake-coworker") -> Actor:
    return Actor(identity=name, kind=ActorKind.MODEL)


def provenance(status: FactStatus = FactStatus.EXTRACTED) -> FactProvenance:
    locator = FactLocator(
        artefact=reference(ReferenceKind.INTAKE_ARTEFACT, "source-workbook"),
        position="sheet=positions;row=1",
    )
    return FactProvenance(locator=locator, extracted_by=model(), status=status)


def schema_field(field_id: str, value_type: SchemaValueType = SchemaValueType.STRING, **overrides) -> SchemaField:
    declared = {
        "field_id": field_id,
        "value_type": value_type,
        "nullable": False,
        "semantic_role": "declared",
        "precision": None,
        "scale": None,
    }
    declared.update(overrides)
    return SchemaField(**declared)


def schema(fields: tuple[SchemaField, ...], schema_id: str = SOURCE_ID) -> SchemaDeclaration:
    return SchemaDeclaration(schema_id=schema_id, version="v1", fields=tuple(fields), format_name="tabular")


def grain(key_fields: tuple[str, ...] = ("position_id",)) -> GrainDeclaration:
    return GrainDeclaration(
        grain_id="one-row-per-position",
        version="v1",
        key_fields=key_fields,
        population_description="settled positions",
        duplicate_keys_permitted=False,
    )


def canonicalisation() -> CanonicalisationDeclaration:
    return CanonicalisationDeclaration(
        canonicalisation_id="risk-canonicalisation",
        version="v1",
        unicode_normalisation="NFC",
        null_representation="empty",
        decimal_scale=2,
        timestamp_precision="second",
        timezone="UTC",
        signed_zero_representation="unsigned",
        non_finite_number_policy="rejected",
    )


def frozen_dataset(fields: tuple[SchemaField, ...], dataset_id: str = SOURCE_ID) -> FrozenDataset:
    return FrozenDataset(
        dataset_id=dataset_id,
        version="v1",
        role=DatasetRole.INPUT,
        provenance=DatasetProvenance.REAL,
        synthetic_provenance=None,
        content_digest="sha256:" + "0" * 64,
        schema=schema(fields, schema_id=dataset_id),
        grain=grain(),
        canonicalisation=canonicalisation(),
        row_count=2,
        approved_summary="two settled positions",
    )


DEFAULT_FIXTURE_FIELDS = (
    schema_field("position_id"),
    schema_field("booked_at", SchemaValueType.TIMESTAMP, nullable=True),
)


def fixture_input(**overrides) -> FixtureInput:
    declared = {
        "relation": "raw_risk_position_feed",
        "dataset": frozen_dataset(DEFAULT_FIXTURE_FIELDS),
        "pin": ProductPin(domain="risk", product="position_feed", major_version=1),
    }
    declared.update(overrides)
    return FixtureInput(**declared)


def build_route(**overrides) -> BuildRouteDeclaration:
    declared = {
        "segment_id": SEGMENT_ID,
        "route": BuildRoute.GENERATED,
        "provenance": provenance(),
        "target_shape": "declared",
        "layer": "derived",
        "product_domain": "risk",
    }
    declared.update(overrides)
    return BuildRouteDeclaration(**declared)


def segment(**overrides) -> Segment:
    declared = {
        "segment_id": SEGMENT_ID,
        "sources": (SOURCE_ID,),
        "passes_through": (INTERMEDIATE_ID,),
        "reaches": SegmentBoundary.TARGET_OUTPUT,
        "route": build_route(),
    }
    declared.update(overrides)
    return Segment(**declared)


def intermediate_result(result_id: str = SEGMENT_ID, **overrides) -> IntermediateResult:
    declared = {
        "result_id": result_id,
        "description": "settled positions normalised onto the booking date",
        "evidence_owner": human("evidence-owner"),
        "provenance": provenance(),
    }
    declared.update(overrides)
    return IntermediateResult(**declared)


def target_output(**overrides) -> TargetOutput:
    declared = {
        "output_id": SEGMENT_ID,
        "kind": "table",
        "schema": schema(DEFAULT_FIXTURE_FIELDS, schema_id=SEGMENT_ID),
        "grain": grain(),
        "cadence": "daily",
        "cutoff_semantics": "rows settled before 22:00 UTC",
        "effective_time_semantics": "effective-dated on the settlement date",
        "provenance": provenance(),
    }
    declared.update(overrides)
    return TargetOutput(**declared)


def authority(**overrides) -> Authority:
    declared = {"role": AuthorityRole.ACCEPTING, "actor": human(), "provenance": provenance()}
    declared.update(overrides)
    return Authority(**declared)


def declared_condition(key: ConditionKey, value: str, **overrides) -> ConditionDeclaration:
    declared = {"key": key, "state": ConditionState.DECLARED, "provenance": provenance(), "value": value}
    declared.update(overrides)
    return ConditionDeclaration(**declared)


def unknown_condition(key: ConditionKey) -> ConditionDeclaration:
    """An unanswered condition falling back to the default it records."""
    return ConditionDeclaration(
        key=key, state=ConditionState.UNKNOWN, provenance=provenance(), default_value=CONDITION_DEFAULTS[key]
    )


def overridden_condition(key: ConditionKey, value: str, author: str = "data-steward") -> ConditionDeclaration:
    """An unanswered condition a named human replaced the default on."""
    return ConditionDeclaration(
        key=key,
        state=ConditionState.UNKNOWN,
        provenance=provenance(),
        default_value=CONDITION_DEFAULTS[key],
        override=ConditionOverride(value=value, author=human(author)),
    )


def booked_on_calculation() -> ProposedCalculatedField:
    return ProposedCalculatedField(
        field_id="booked_on", value_type=SchemaValueType.DATE, expression="CAST(booked_at AS DATE)"
    )


def request(**overrides) -> SegmentDeclarationRequest:
    """The declared segment request the proofs start from: one implied calculation."""
    declared = {
        "segment": segment(),
        "draft_version": "1.0",
        "authorities": (authority(),),
        "fixture_inputs": {SOURCE_ID: fixture_input()},
        "upstream_pins": {},
        "consumer_dependencies": (),
        "conditions": (),
        "target_output": target_output(),
        "intermediate_calculations": {INTERMEDIATE_ID: (booked_on_calculation(),)},
        "computed_fields": (),
    }
    declared.update(overrides)
    return SegmentDeclarationRequest(**declared)


def request_with_no_calculation(**overrides) -> SegmentDeclarationRequest:
    """A span that passes no intermediate result and supplies no computed field."""
    declared = {
        "segment": segment(passes_through=()),
        "intermediate_calculations": {},
        "computed_fields": (),
    }
    declared.update(overrides)
    return request(**declared)
