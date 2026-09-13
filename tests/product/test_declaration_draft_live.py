"""Live proofs of the declaration draft against the installed Ergasterion wheel.

The declaration schema check needs ``jsonschema`` and the profile check needs
a YAML reader; both reach this environment only through the delivery extra
(ground truth 9), so they are imported inside the test body for the same
reason a delivery tool is: the public candidate installs with no delivery
extra, and a module-level import would be a collection error there. Every
Ergasterion import happens the same way, or through ``pytest.importorskip``.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from evorthon_data.delivery import (
    ExactGenerationContract,
    ErgasterionGenerationRoute,
    FixtureSeed,
    ProductDeclaration,
    SubprocessErgasterionRunner,
)
from evorthon_data.delivery.declaration_draft import (
    LAYER_PROFILES,
    DeclarationDraftError,
    FixtureInput,
    ProductPin,
    ProposedCalculatedField,
    SegmentDeclarationRequest,
    draft_declaration,
)
from evorthon_data.engagement.use_case import (
    Authority,
    AuthorityRole,
    BuildRoute,
    BuildRouteDeclaration,
    Segment,
    SegmentBoundary,
)
from evorthon_data.verification.domain import (
    GrainDeclaration,
    Identity,
    SchemaDeclaration,
    SchemaField,
    SchemaValueType,
)
from evorthon_data.verification.domain.contracts import DatasetRole

from declaration_draft_support import human, intermediate_result, provenance

FIXTURE_RELATION = "raw_risk_position_feed"
FIXTURE_DATASET_ID = "raw-risk-position-feed"
BOOKED_ON = ProposedCalculatedField(
    field_id="booked_on", value_type=SchemaValueType.DATE, expression="CAST(booked_at AS DATE)"
)
EXPOSURE_AMOUNT = ProposedCalculatedField(
    field_id="exposure_amount",
    value_type=SchemaValueType.DECIMAL,
    expression="CAST(1 AS NUMERIC)",
    precision=18,
    scale=2,
)


def released_command() -> tuple[str, ...]:
    import shutil
    import sys

    found = shutil.which("ergasterion")
    return (found,) if found else (sys.executable, "-m", "ergasterion")


def capability_report() -> dict:
    from evorthon_data.dependencies import installed_capabilities

    return installed_capabilities()


def fixture_schema() -> SchemaDeclaration:
    return SchemaDeclaration(
        schema_id=FIXTURE_RELATION,
        version="v1",
        fields=(
            SchemaField(
                field_id="position_id", value_type=SchemaValueType.STRING, nullable=False,
                semantic_role="position key", precision=None, scale=None,
            ),
            SchemaField(
                field_id="booked_at", value_type=SchemaValueType.TIMESTAMP, nullable=True,
                semantic_role="booking instant", precision=None, scale=None,
            ),
        ),
        format_name="tabular",
    )


def fixture_grain() -> GrainDeclaration:
    return GrainDeclaration(
        grain_id="one-row-per-position", version="v1", key_fields=("position_id",),
        population_description="settled positions", duplicate_keys_permitted=False,
    )


def generated_fixture_dataset():
    """A synthetically generated frozen dataset and its CSV bytes for the fixture seed."""
    import datetime

    from evorthon_data.synthetic.generator import (
        FieldConstraint,
        SyntheticDatasetConstraints,
        ValueRule,
        generate,
    )

    constraints = SyntheticDatasetConstraints(
        constraints_id="raw-risk-position-feed-constraints",
        version="v1",
        dataset_id=FIXTURE_DATASET_ID,
        role=DatasetRole.INPUT,
        row_count=2,
        approved_summary="two settled positions for the declaration draft live proof",
        fields=(
            FieldConstraint(
                field_id="position_id", rule=ValueRule.SEQUENCE, lower="p-", upper=None,
                categories=(), key_list_id=None, cardinality=None, null_rate=0.0, null_rate_tolerance=0.0,
            ),
            FieldConstraint(
                field_id="booked_at", rule=ValueRule.RANGE,
                lower=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
                upper=datetime.datetime(2026, 1, 2, tzinfo=datetime.timezone.utc),
                categories=(), key_list_id=None, cardinality=None, null_rate=0.0, null_rate_tolerance=0.0,
            ),
        ),
    )
    return generate(
        schema=fixture_schema(),
        grain=fixture_grain(),
        keys=(),
        constraints=constraints,
        seed="declaration-draft-live-proof",
        generator_version="v1",
    )


def live_request(
    *,
    product_name: str,
    reaches: SegmentBoundary = SegmentBoundary.TARGET_OUTPUT,
    passes_through: tuple[str, ...] = ("settlement_normalisation",),
    intermediate_calculations=None,
    computed_fields: tuple[ProposedCalculatedField, ...] = (),
) -> SegmentDeclarationRequest:
    route = BuildRouteDeclaration(
        segment_id=product_name,
        route=BuildRoute.GENERATED,
        provenance=provenance(),
        target_shape="declared",
        layer="derived",
        product_domain="risk",
    )
    segment = Segment(
        segment_id=product_name,
        sources=(FIXTURE_DATASET_ID,),
        passes_through=passes_through,
        reaches=reaches,
        route=route,
    )
    fixture = FixtureInput(
        relation=FIXTURE_RELATION,
        dataset=generated_fixture_dataset().dataset,
        pin=ProductPin(domain="risk", product="position_feed", major_version=1),
    )
    target_output = None
    boundary_result = None
    if reaches is SegmentBoundary.TARGET_OUTPUT:
        target_output = live_target_output(product_name, computed_fields)
    else:
        boundary_result = intermediate_result(result_id=product_name)
    if intermediate_calculations is None:
        intermediate_calculations = {name: (BOOKED_ON,) for name in passes_through}
    return SegmentDeclarationRequest(
        segment=segment,
        draft_version="1.0",
        authorities=(Authority(role=AuthorityRole.ACCEPTING, actor=human("platform-team"), provenance=provenance()),),
        fixture_inputs={FIXTURE_DATASET_ID: fixture},
        target_output=target_output,
        boundary_result=boundary_result,
        intermediate_calculations=intermediate_calculations,
        computed_fields=computed_fields,
    )


def live_target_output(product_name: str, computed_fields):
    from evorthon_data.engagement import TargetOutput

    extra = tuple(
        SchemaField(
            field_id=computed.field_id, value_type=computed.value_type, nullable=True,
            semantic_role="calculated", precision=computed.precision, scale=computed.scale,
        )
        for computed in (BOOKED_ON, *computed_fields)
    )
    schema = SchemaDeclaration(
        schema_id=product_name, version="v1", fields=fixture_schema().fields + extra, format_name="tabular"
    )
    return TargetOutput(
        output_id=product_name,
        kind="table",
        schema=schema,
        grain=fixture_grain(),
        cadence="daily",
        cutoff_semantics="rows settled before 22:00 UTC",
        effective_time_semantics="effective-dated on the settlement date",
        provenance=provenance(),
    )


def generate_text(estate: Path, file_name: str, document_text: str, identifier: str):
    seed_text = generated_fixture_dataset().csv_bytes.decode("utf-8")
    assert seed_text.startswith("position_id,booked_at\r\n") or seed_text.startswith("position_id,booked_at\n")
    contract = ExactGenerationContract(
        identity=Identity(identifier=identifier, version="v1", digest=f"sha256:{identifier}-digest"),
        declarations=(ProductDeclaration(file_name, document_text),),
        seeds=(FixtureSeed(f"{FIXTURE_RELATION}.csv", seed_text),),
        canonicalisation=generated_fixture_dataset().dataset.canonicalisation,
    )
    route = ErgasterionGenerationRoute(
        SubprocessErgasterionRunner(command=released_command()),
        actor="declaration-draft-live-proof",
        capabilities=capability_report(),
    )
    return route.generate(contract, estate=estate)


def generate_into(estate: Path, draft, identifier: str):
    return generate_text(estate, draft.file_name, draft.yaml_text, identifier)


def generate_document(estate: Path, file_name: str, document: dict, identifier: str):
    return generate_text(estate, file_name, json.dumps(document, indent=2) + "\n", identifier)


@pytest.mark.deep
@pytest.mark.timeout(300)
def test_the_draft_validates_against_the_installed_product_declaration_schema():
    pytest.importorskip("ergasterion")
    import jsonschema
    import ergasterion

    schema_path = Path(ergasterion.__file__).parent / "schemas" / "product-declaration-v1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    for request in (
        live_request(product_name="settled_positions"),
        live_request(product_name="settled_positions", computed_fields=(EXPOSURE_AMOUNT,)),
    ):
        jsonschema.validate(instance=draft_declaration(request).document, schema=schema)


@pytest.mark.deep
@pytest.mark.timeout(300)
def test_the_layer_table_matches_the_installed_profile_the_label_admits():
    pytest.importorskip("ergasterion")
    import yaml
    import ergasterion

    mapped = LAYER_PROFILES["derived"]
    document = yaml.safe_load(
        (Path(ergasterion.__file__).parent / "profiles" / f"{mapped.profile}.yml").read_text(encoding="utf-8")
    )

    assert tuple(document["mandatory"]) == mapped.mandatory
    assert tuple(document["optional"]) == mapped.optional
    assert tuple(document["forbidden"]) == mapped.forbidden
    assert tuple(document["ordering"]) == mapped.ordering


@pytest.mark.deep
@pytest.mark.timeout(300)
def test_a_segment_whose_intermediate_implies_the_calculation_validates_and_emits(tmp_path):
    pytest.importorskip("ergasterion")

    draft = draft_declaration(live_request(product_name="settled_positions"))
    assert [step["pattern"] for step in draft.document["steps"]][:3] == [
        "batch_transfer",
        "data_validation",
        "calculated_fields",
    ]

    result = generate_into(tmp_path / "estate", draft, "implied-calculation-live-proof")

    assert [node.published_name for node in result.graph.nodes] == ["risk.settled_positions"]
    assert dict(result.artefact_digests)["graphs/products/product-graph.json"].startswith("sha256:")


@pytest.mark.deep
@pytest.mark.timeout(300)
def test_a_segment_with_caller_computed_fields_validates_and_emits(tmp_path):
    pytest.importorskip("ergasterion")

    draft = draft_declaration(
        live_request(product_name="settled_positions", computed_fields=(EXPOSURE_AMOUNT,))
    )
    [calculated] = [step for step in draft.document["steps"] if step["pattern"] == "calculated_fields"]
    assert [entry["name"] for entry in calculated["fields"]] == ["booked_on", "exposure_amount"]

    result = generate_into(tmp_path / "estate", draft, "computed-fields-live-proof")

    assert [node.published_name for node in result.graph.nodes] == ["risk.settled_positions"]


@pytest.mark.deep
@pytest.mark.timeout(300)
def test_a_checkpointed_intermediate_registers_a_checkpoint_relation(tmp_path):
    pytest.importorskip("ergasterion")

    draft = draft_declaration(
        live_request(product_name="settled_positions_checkpoint", reaches=SegmentBoundary.INTERMEDIATE_RESULT)
    )
    assert draft.checkpoint is True
    assert draft.document["checkpointing"]["checkpoint"] is True

    result = generate_into(tmp_path / "estate", draft, "checkpoint-live-proof")

    assert result.graph.checkpoint_relations
    assert [node.published_name for node in result.graph.nodes] == ["risk.settled_positions_checkpoint"]


@pytest.mark.deep
@pytest.mark.timeout(300)
def test_a_segment_implying_no_calculation_is_refused_before_any_tool_call():
    """The shape the installed derivation profile refuses never reaches the tool."""
    pytest.importorskip("ergasterion")

    with pytest.raises(DeclarationDraftError, match="requires pattern 'calculated_fields'"):
        draft_declaration(
            live_request(product_name="settled_positions", passes_through=(), intermediate_calculations={})
        )


@pytest.mark.deep
@pytest.mark.timeout(300)
def test_a_second_source_is_refused_before_any_tool_call():
    """Nothing the use case declares says how two sources combine, so none is drafted."""
    pytest.importorskip("ergasterion")

    from evorthon_data.engagement import ImmutableReference, ReferenceKind
    from evorthon_data.engagement.use_case import ConsumerDependency

    dependency = ConsumerDependency(
        provider=ImmutableReference(
            kind=ReferenceKind.USE_CASE, identifier="uc-upstream", version="v1", digest="digest-uc-upstream"
        ),
        product_id="risk.exposure_summary",
        major_version="v2",
        provenance=provenance(),
    )
    request = live_request(product_name="settled_positions")

    with pytest.raises(DeclarationDraftError, match="states no method for combining them"):
        draft_declaration(replace(request, consumer_dependencies=(dependency,)))


@pytest.mark.deep
@pytest.mark.timeout(300)
def test_the_installed_tool_refuses_that_same_two_source_shape(tmp_path):
    """The refusal above is the tool's own rule, not this adapter's preference."""
    pytest.importorskip("ergasterion")

    draft = draft_declaration(live_request(product_name="settled_positions"))
    document = json.loads(draft.yaml_text)
    document["sources"].append({"contract": "risk.exposure_summary@2"})

    with pytest.raises(Exception) as refusal:
        generate_document(tmp_path / "estate", draft.file_name, document, "two-source-live-proof")

    assert "undeclared_composition" in str(refusal.value)


@pytest.mark.deep
@pytest.mark.timeout(300)
def test_the_installed_tool_refuses_that_same_shape_when_the_step_is_removed(tmp_path):
    """The refusal above is the tool's own rule, not this adapter's preference."""
    pytest.importorskip("ergasterion")

    draft = draft_declaration(live_request(product_name="settled_positions"))
    document = json.loads(draft.yaml_text)
    document["steps"] = [step for step in document["steps"] if step["pattern"] != "calculated_fields"]

    with pytest.raises(Exception) as refusal:
        generate_document(tmp_path / "estate", draft.file_name, document, "stripped-live-proof")

    assert "missing_mandatory_pattern" in str(refusal.value)
