"""Hermetic proofs for the segment-to-declaration draft, without Ergasterion."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from evorthon_data.delivery import declaration_draft as module
from evorthon_data.delivery.declaration_draft import (
    LAYER_PROFILES,
    DeclarationDraftError,
    LayerProfile,
    ProductPin,
    ProposedCalculatedField,
    draft_declaration,
)
from evorthon_data.delivery.ergasterion import GenerationDisposition
from evorthon_data.engagement import ReferenceKind, StoredColumnName
from evorthon_data.engagement.use_case import (
    BuildRoute,
    BuildRouteDeclaration,
    CONDITION_DEFAULTS,
    ConditionKey,
    ConsumerDependency,
    SegmentBoundary,
)
from evorthon_data.verification.domain.contracts import SchemaValueType

from declaration_draft_support import (
    INTERMEDIATE_ID,
    SEGMENT_ID,
    SOURCE_ID,
    booked_on_calculation,
    build_route,
    declared_condition,
    fixture_input,
    frozen_dataset,
    identity,
    intermediate_result,
    model,
    overridden_condition,
    provenance,
    reference,
    request,
    request_with_no_calculation,
    schema_field,
    segment,
    target_output,
    unknown_condition,
)

PUBLICATION_PHASE = ["data_contracts", "lineage_capture", "metadata_capture", "schema_publish", "data_publish"]


def patterns_of(draft) -> list[str]:
    return [step["pattern"] for step in draft.document["steps"]]


def step_named(draft, pattern: str) -> dict:
    [found] = [step for step in draft.document["steps"] if step["pattern"] == pattern]
    return found


def module_imports() -> list[str]:
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            names.append(node.module)
    return names


def test_the_module_never_imports_ergasterion_or_the_synthetic_generator():
    names = module_imports()
    assert not any(name == "ergasterion" or name.startswith("ergasterion.") for name in names)
    assert not any("synthetic" in name for name in names)


def test_the_module_reaches_no_filesystem_or_process_capability():
    names = module_imports()
    assert not {"os", "io", "pathlib", "shutil", "subprocess", "tempfile"} & set(names)


def test_a_generated_route_with_a_domain_drafts_the_product_block():
    draft = draft_declaration(request())

    assert draft.document["product"] == {
        "name": SEGMENT_ID,
        "domain": "risk",
        "version": "1.0",
        "layer": "derived",
        "owner": "accepting-authority",
    }
    assert draft.file_name == f"{SEGMENT_ID}.yml"
    assert draft.checkpoint is False


def test_fixture_backed_source_carries_fields_from_the_schema_declaration():
    draft = draft_declaration(request())

    [source] = draft.document["sources"]
    assert source["kind"] == "fixture"
    assert source["contract"] == "risk.position_feed@1"
    assert source["fixture"]["relation"] == "raw_risk_position_feed"
    assert source["fixture"]["fields"] == [
        {"name": "position_id", "type": "string"},
        {"name": "booked_at", "type": "timestamp"},
    ]


def test_an_input_with_a_stored_name_carries_its_physical_name():
    fixture = fixture_input(
        stored_column_names=(StoredColumnName(field_id="position_id", stored_name="POS_ID"),)
    )

    draft = draft_declaration(request(fixture_inputs={SOURCE_ID: fixture}))

    [source] = draft.document["sources"]
    named = {entry["name"]: entry.get("physical_name") for entry in source["fixture"]["fields"]}
    assert named["position_id"] == "POS_ID"
    assert named["booked_at"] is None


def consumer_dependency() -> ConsumerDependency:
    return ConsumerDependency(
        provider=reference(ReferenceKind.USE_CASE, "uc-upstream"),
        product_id="risk.exposure_summary",
        major_version="v2",
        provenance=provenance(),
    )


def test_an_upstream_pin_renders_as_a_contract_reference():
    pin = ProductPin(domain="risk", product="settled_positions", major_version=1, expected_fields=("position_id",))

    assert module._pin_source(pin) == {
        "contract": "risk.settled_positions@1",
        "expect": {"fields": ["position_id"]},
    }


def test_a_consumer_dependency_renders_as_a_contract_reference_without_its_leading_v():
    assert module._dependency_source(consumer_dependency()) == {"contract": "risk.exposure_summary@2"}


def test_a_consumer_dependency_that_is_not_a_declared_dependency_is_refused():
    with pytest.raises(DeclarationDraftError, match="declared consumer dependency"):
        draft_declaration(request(consumer_dependencies=("risk.exposure_summary@2",)))


def test_a_consumer_dependency_beside_a_fixture_source_is_refused():
    with pytest.raises(DeclarationDraftError, match="states no method for combining them"):
        draft_declaration(request(consumer_dependencies=(consumer_dependency(),)))


def test_an_upstream_pin_alongside_a_fixture_is_refused():
    with pytest.raises(DeclarationDraftError, match="consumes 2 sources"):
        draft_declaration(
            request(
                segment=segment(sources=(SOURCE_ID, "upstream-checkpoint")),
                upstream_pins={
                    "upstream-checkpoint": ProductPin(domain="risk", product="settled_positions", major_version=1)
                },
            )
        )


def test_a_value_that_is_not_a_segment_is_refused():
    with pytest.raises(DeclarationDraftError, match="derived use-case segment"):
        draft_declaration(request(segment=SEGMENT_ID))


def test_a_segment_identity_that_cannot_name_a_file_is_refused():
    with pytest.raises(DeclarationDraftError, match="cannot name a declaration file"):
        draft_declaration(
            request(
                segment=segment(segment_id="risk/settled", route=build_route(segment_id="risk/settled")),
                target_output=target_output(output_id="risk/settled"),
            )
        )


def test_an_engineered_route_is_refused():
    engineered = segment(
        route=BuildRouteDeclaration(segment_id=SEGMENT_ID, route=BuildRoute.ENGINEERED, provenance=provenance())
    )

    with pytest.raises(DeclarationDraftError, match="only a generated route"):
        draft_declaration(request(segment=engineered))


def test_a_segment_with_no_build_route_is_refused():
    with pytest.raises(DeclarationDraftError, match="no declared build route"):
        draft_declaration(request(segment=segment(route=None)))


def test_a_generated_route_with_no_layer_is_refused():
    with pytest.raises(DeclarationDraftError, match="names no layer label"):
        draft_declaration(request(segment=segment(route=build_route(layer=None))))


def test_a_layer_the_profile_table_does_not_map_is_refused():
    with pytest.raises(DeclarationDraftError, match="no profile mapping"):
        draft_declaration(request(segment=segment(route=build_route(layer="curated"))))


def test_no_accepting_authority_is_refused():
    with pytest.raises(DeclarationDraftError, match="accepting authority"):
        draft_declaration(request(authorities=()))


def test_a_source_with_no_fixture_or_pin_is_refused():
    with pytest.raises(DeclarationDraftError, match="has no frozen input or contract pin"):
        draft_declaration(request(fixture_inputs={}))


def test_a_segment_with_no_source_at_all_is_refused_by_the_profile():
    with pytest.raises(DeclarationDraftError, match="requires pattern 'batch_transfer'"):
        draft_declaration(request(segment=segment(sources=()), fixture_inputs={}))


def test_a_fixture_whose_relation_is_unnamed_is_refused():
    with pytest.raises(DeclarationDraftError, match="fixture relation name is required"):
        draft_declaration(request(fixture_inputs={SOURCE_ID: fixture_input(relation="")}))


def test_a_frozen_input_with_no_schema_declaration_is_refused():
    fixture = fixture_input(dataset=frozen_dataset(()))

    with pytest.raises(DeclarationDraftError, match="no schema declaration"):
        draft_declaration(request(fixture_inputs={SOURCE_ID: fixture}))


def test_an_unmappable_field_type_is_refused():
    fixture = fixture_input(dataset=frozen_dataset((schema_field("blob", SchemaValueType.BINARY, nullable=True),)))

    with pytest.raises(DeclarationDraftError, match="cannot accept"):
        draft_declaration(request(fixture_inputs={SOURCE_ID: fixture}))


def checkpoint_request(**overrides):
    checkpoint_segment = segment(reaches=SegmentBoundary.INTERMEDIATE_RESULT)
    declared = {
        "segment": checkpoint_segment,
        "target_output": None,
        "boundary_result": intermediate_result(),
    }
    declared.update(overrides)
    return request(**declared)


def test_a_checkpoint_candidate_boundary_sets_checkpoint_true():
    draft = draft_declaration(checkpoint_request())

    assert draft.checkpoint is True
    assert draft.document["checkpointing"]["checkpoint"] is True


def test_a_boundary_that_is_not_a_checkpoint_candidate_carries_no_checkpoint_key():
    draft = draft_declaration(checkpoint_request(boundary_result=intermediate_result(checkpoint_candidate=False)))

    assert draft.checkpoint is False
    assert "checkpoint" not in draft.document["checkpointing"]


def test_a_checkpoint_segment_with_no_declared_intermediate_result_is_refused():
    with pytest.raises(DeclarationDraftError, match="needs the declared intermediate result it reaches"):
        draft_declaration(checkpoint_request(boundary_result=None))


def test_target_output_on_a_checkpoint_segment_is_refused():
    with pytest.raises(DeclarationDraftError, match="carries no target output"):
        draft_declaration(checkpoint_request(target_output=target_output()))


def test_an_intermediate_result_on_a_target_output_segment_is_refused():
    with pytest.raises(DeclarationDraftError, match="carries no intermediate result"):
        draft_declaration(request(boundary_result=intermediate_result()))


def test_target_output_mismatch_is_refused():
    with pytest.raises(DeclarationDraftError, match="needs its own declared target output"):
        draft_declaration(request(target_output=target_output(output_id="something-else")))


def test_checkpointing_defaults_when_undeclared():
    draft = draft_declaration(request())

    assert draft.document["checkpointing"] == {"granularity": "step", "max_retries": 3, "backoff": "exponential"}


@pytest.mark.parametrize(
    ("key", "value", "match"),
    [
        (ConditionKey.CHECKPOINT_GRANULARITY, "batch", "granularity"),
        (ConditionKey.BACKOFF, "linear", "backoff"),
        (ConditionKey.MAX_RETRIES, "many", "non-negative integer"),
    ],
)
def test_an_unmappable_run_policy_value_is_refused(key, value, match):
    with pytest.raises(DeclarationDraftError, match=match):
        draft_declaration(request(conditions=(declared_condition(key, value),)))


def test_the_step_list_is_exactly_what_the_declarations_imply():
    draft = draft_declaration(request())

    assert patterns_of(draft) == ["batch_transfer", "data_validation", "calculated_fields", *PUBLICATION_PHASE]


def test_an_intermediate_result_carries_the_calculated_field_that_realises_it():
    draft = draft_declaration(request())

    assert step_named(draft, "calculated_fields")["fields"] == [
        {"name": "booked_on", "type": "date", "expression": "CAST(booked_at AS DATE)"}
    ]


def test_a_caller_computed_field_extends_the_calculation_the_intermediate_implies():
    extra = ProposedCalculatedField(
        field_id="exposure_amount",
        value_type=SchemaValueType.DECIMAL,
        expression="CAST(1 AS NUMERIC)",
        precision=18,
        scale=2,
    )

    draft = draft_declaration(request(computed_fields=(extra,)))

    fields = step_named(draft, "calculated_fields")["fields"]
    assert [entry["name"] for entry in fields] == ["booked_on", "exposure_amount"]
    assert fields[1]["type"] == {"name": "decimal", "precision": 18, "scale": 2}


def test_a_segment_whose_declarations_imply_no_calculation_is_refused():
    with pytest.raises(DeclarationDraftError, match="requires pattern 'calculated_fields'"):
        draft_declaration(request_with_no_calculation())


def test_an_intermediate_result_with_no_supplied_calculation_is_refused():
    with pytest.raises(DeclarationDraftError, match="no calculated field is supplied to realise it"):
        draft_declaration(request(intermediate_calculations={INTERMEDIATE_ID: ()}))


def test_a_calculation_for_an_intermediate_the_span_does_not_pass_is_refused():
    with pytest.raises(DeclarationDraftError, match="does not pass through"):
        draft_declaration(
            request(
                intermediate_calculations={
                    INTERMEDIATE_ID: (booked_on_calculation(),),
                    "unlisted-step": (booked_on_calculation(),),
                }
            )
        )


def test_a_computed_field_that_is_not_a_proposed_calculated_field_is_refused():
    with pytest.raises(DeclarationDraftError, match="proposed calculated field"):
        draft_declaration(request(computed_fields=("booked_on",)))


def test_a_computed_decimal_field_needs_precision_and_scale():
    computed = (
        ProposedCalculatedField(
            field_id="exposure_amount", value_type=SchemaValueType.DECIMAL, expression="CAST(1 AS NUMERIC)"
        ),
    )

    with pytest.raises(DeclarationDraftError, match="no precision and scale"):
        draft_declaration(request(computed_fields=computed))


def test_duplicate_computed_field_ids_are_refused():
    with pytest.raises(DeclarationDraftError, match="declared twice"):
        draft_declaration(request(computed_fields=(booked_on_calculation(),)))


def test_data_validation_rules_come_from_non_nullable_fixture_fields():
    draft = draft_declaration(request())

    validation = step_named(draft, "data_validation")
    assert validation["rules"] == [{"field": "position_id", "completeness": 1.0}]
    assert validation["on_failure"] == "abort"
    assert "error_threshold" not in validation


def test_no_required_field_to_validate_is_refused_by_the_profile():
    fixture = fixture_input(dataset=frozen_dataset((schema_field("note", nullable=True),)))

    with pytest.raises(DeclarationDraftError, match="requires pattern 'data_validation'"):
        draft_declaration(request(fixture_inputs={SOURCE_ID: fixture}))


def test_a_quarantine_policy_carries_the_accepted_source_defects_as_its_threshold():
    conditions = (
        declared_condition(ConditionKey.WARNING_AND_FAILURE_CLASSES, "quarantine"),
        declared_condition(ConditionKey.ACCEPTED_SOURCE_DEFECTS, "0.01"),
    )

    draft = draft_declaration(request(conditions=conditions))

    validation = step_named(draft, "data_validation")
    assert validation["on_failure"] == "quarantine"
    assert validation["error_threshold"] == 0.01


def test_the_completeness_expectation_sets_the_rule_completeness():
    conditions = (declared_condition(ConditionKey.COMPLETENESS_EXPECTATION, "0.99"),)

    draft = draft_declaration(request(conditions=conditions))

    assert step_named(draft, "data_validation")["rules"][0]["completeness"] == 0.99


@pytest.mark.parametrize(
    ("key", "value", "match"),
    [
        (ConditionKey.WARNING_AND_FAILURE_CLASSES, "raise a ticket", "no failure policy"),
        (ConditionKey.COMPLETENESS_EXPECTATION, "most rows", "no proportion"),
    ],
)
def test_an_unreadable_quality_condition_is_refused(key, value, match):
    with pytest.raises(DeclarationDraftError, match=match):
        draft_declaration(request(conditions=(declared_condition(key, value),)))


def test_an_unreadable_accepted_defect_proportion_is_refused_under_quarantine():
    conditions = (
        declared_condition(ConditionKey.WARNING_AND_FAILURE_CLASSES, "quarantine"),
        declared_condition(ConditionKey.ACCEPTED_SOURCE_DEFECTS, "a handful"),
    )

    with pytest.raises(DeclarationDraftError, match="no proportion"):
        draft_declaration(request(conditions=conditions))


def test_the_target_contract_freshness_comes_from_the_freshness_deadline():
    conditions = (declared_condition(ConditionKey.FRESHNESS_DEADLINE, "daily by 06:00 UTC"),)

    draft = draft_declaration(request(conditions=conditions))

    assert draft.document["target"]["contract"]["freshness"] == "daily by 06:00 UTC"


def test_the_recorded_freshness_default_is_carried_when_undeclared():
    draft = draft_declaration(request())

    assert draft.document["target"]["contract"]["freshness"] == CONDITION_DEFAULTS[ConditionKey.FRESHNESS_DEADLINE]


def test_a_cut_use_case_version_is_the_product_version():
    cut = reference(ReferenceKind.USE_CASE_VERSION, "uc-risk-positions")

    draft = draft_declaration(request(cut_version=cut, draft_version=None))

    assert draft.document["product"]["version"] == "v1"
    assert "product version: v1 (the use case's cut version)" in draft.proposal_notes


def test_a_draft_version_is_labelled_as_one_in_the_proposal_notes():
    draft = draft_declaration(request())

    assert (
        "product version: 1.0 (a caller-supplied draft version; no use-case version has been cut)"
        in draft.proposal_notes
    )


def test_a_cut_version_and_a_draft_version_together_are_refused():
    cut = reference(ReferenceKind.USE_CASE_VERSION, "uc-risk-positions")

    with pytest.raises(DeclarationDraftError, match="no separate draft version"):
        draft_declaration(request(cut_version=cut))


def test_no_cut_version_and_no_draft_version_is_refused():
    with pytest.raises(DeclarationDraftError, match="draft product version is required"):
        draft_declaration(request(draft_version=None))


def test_an_empty_draft_version_is_refused():
    with pytest.raises(DeclarationDraftError, match="draft product version is required"):
        draft_declaration(request(draft_version=""))


def test_a_cut_version_that_is_not_a_use_case_version_is_refused():
    with pytest.raises(DeclarationDraftError, match="use_case_version identity"):
        draft_declaration(
            request(cut_version=reference(ReferenceKind.USE_CASE, "uc-risk"), draft_version=None)
        )


def test_the_run_policy_and_uncarried_conditions_are_named_in_the_proposal_notes():
    conditions = (
        declared_condition(ConditionKey.CHECKPOINT_GRANULARITY, "composition"),
        declared_condition(ConditionKey.RETENTION_WINDOW, "seven years"),
    )

    draft = draft_declaration(request(conditions=conditions))

    assert "checkpoint_granularity: composition (declared), carried as checkpointing.granularity" in draft.proposal_notes
    assert "max_retries: 3 (default), carried as checkpointing.max_retries" in draft.proposal_notes
    assert "backoff: exponential (default), carried as checkpointing.backoff" in draft.proposal_notes
    assert (
        "retention_window: seven years (declared), not carried: the declaration schema has no slot for it"
        in draft.proposal_notes
    )
    classification = CONDITION_DEFAULTS[ConditionKey.HANDLING_CLASSIFICATION]
    assert (
        f"handling_classification: {classification} (default), not carried: "
        "the declaration schema has no slot for it" in draft.proposal_notes
    )


def test_every_derived_operational_value_is_named_in_the_proposal_notes():
    draft = draft_declaration(request())

    assert (
        "publication_mode: atomic (no standing condition owns it; it is the only mode the "
        "declaration schema admits without a declared unique key)" in draft.proposal_notes
    )
    assert (
        "warning_and_failure_classes: every difference is a failure (default), "
        "carried as data_validation.on_failure abort" in draft.proposal_notes
    )
    assert (
        "accepted_source_defects: none (default), not carried: the abort policy takes no error threshold"
        in draft.proposal_notes
    )
    assert (
        "completeness_expectation: every declared row (default), carried as the "
        "data_validation completeness 1.0" in draft.proposal_notes
    )
    assert (
        f"freshness_deadline: {CONDITION_DEFAULTS[ConditionKey.FRESHNESS_DEADLINE]} (default), "
        "carried as target.contract.freshness" in draft.proposal_notes
    )


def test_an_overridden_condition_note_names_the_human_who_overrode_it():
    conditions = (overridden_condition(ConditionKey.RETENTION_WINDOW, "seven years", author="data-steward"),)

    draft = draft_declaration(request(conditions=conditions))

    assert (
        "retention_window: seven years (overridden by data-steward), not carried: "
        "the declaration schema has no slot for it" in draft.proposal_notes
    )


def test_an_unanswered_condition_with_no_override_is_still_named_a_default():
    conditions = (unknown_condition(ConditionKey.RETENTION_WINDOW),)

    draft = draft_declaration(request(conditions=conditions))

    default = CONDITION_DEFAULTS[ConditionKey.RETENTION_WINDOW]
    assert (
        f"retention_window: {default} (default), not carried: the declaration schema has no slot for it"
        in draft.proposal_notes
    )


def test_historisation_kind_selects_the_shape_when_the_route_leaves_it_open():
    draft = draft_declaration(request(segment=segment(route=build_route(target_shape=None))))

    assert draft.document["target"]["shape"] == "declared"


def test_the_route_own_target_shape_wins_over_historisation_kind():
    conditions = (declared_condition(ConditionKey.HISTORISATION_KIND, "snapshots"),)

    draft = draft_declaration(request(segment=segment(route=build_route(target_shape="dimensional")), conditions=conditions))

    assert draft.document["target"]["shape"] == "dimensional"


def test_an_unmappable_historisation_kind_is_refused_when_the_route_leaves_shape_open():
    conditions = (declared_condition(ConditionKey.HISTORISATION_KIND, "snapshots"),)

    with pytest.raises(DeclarationDraftError, match="historisation kind"):
        draft_declaration(request(segment=segment(route=build_route(target_shape=None)), conditions=conditions))


def test_physical_block_from_stored_names():
    output = target_output(
        stored_name="TBL_SETTLED_POSITIONS",
        stored_column_names=(StoredColumnName(field_id="position_id", stored_name="POS_ID"),),
    )

    draft = draft_declaration(request(target_output=output))

    assert draft.document["physical"] == {
        "name": "TBL_SETTLED_POSITIONS",
        "fields": [{"name": "position_id", "physical_name": "POS_ID"}],
    }


def test_no_physical_block_when_nothing_declared():
    assert "physical" not in draft_declaration(request()).document


def test_metadata_capture_carries_the_accepting_authority_as_owner():
    draft = draft_declaration(request())

    assert step_named(draft, "metadata_capture")["ownership"] == "accepting-authority"
    assert step_named(draft, "data_publish") == {"pattern": "data_publish", "publication_mode": "atomic"}


def test_yaml_text_round_trips_to_the_document():
    draft = draft_declaration(request())

    assert json.loads(draft.yaml_text) == draft.document


def test_the_layer_table_records_the_derivation_composition():
    profile = LAYER_PROFILES["derived"]

    assert profile.profile == "derivation"
    assert "calculated_fields" in profile.mandatory
    assert profile.forbidden == ("batch_ingestion", "data_curation")
    assert profile.ordering.index("data_validation") < profile.ordering.index("calculated_fields")


def landing_shaped_profile() -> LayerProfile:
    """A second profile shape, so the table's own checks are proved, not assumed."""
    return LayerProfile(
        profile="landing",
        mandatory=("batch_ingestion", "data_publish"),
        optional=("batch_transfer",),
        forbidden=("calculated_fields",),
        ordering=("batch_ingestion", "batch_transfer", "data_publish"),
    )


def test_a_profile_refuses_a_pattern_it_forbids():
    with pytest.raises(DeclarationDraftError, match="forbids pattern 'calculated_fields'"):
        landing_shaped_profile().refuse_unadmitted(["calculated_fields"], layer="reference")


def test_a_profile_refuses_a_pattern_it_does_not_classify():
    with pytest.raises(DeclarationDraftError, match="does not classify pattern 'data_curation'"):
        landing_shaped_profile().refuse_unadmitted(["data_curation"], layer="reference")


def test_a_profile_refuses_a_mandatory_pattern_no_declaration_implies():
    with pytest.raises(DeclarationDraftError, match="requires pattern 'batch_ingestion'"):
        landing_shaped_profile().refuse_missing_mandatory(["data_publish"], layer="reference")


def proposed():
    return draft_declaration(request()).proposed(
        proposal_id="risk-settled-positions-declaration", version="v1", drafted_by="declaration-drafter"
    )


def test_a_draft_is_recorded_as_a_proposal_reference_over_its_own_document():
    draft = draft_declaration(request())

    proposal = draft.proposed(proposal_id="p1", version="v1", drafted_by="declaration-drafter")

    assert proposal.reference.identifier == "p1"
    assert proposal.reference.digest == draft.content_digest
    assert proposal.reference.digest.startswith("sha256:")


def test_an_adjudicated_draft_carries_the_reviewer_identity_and_the_disposition():
    adjudicated = proposed().adjudicated(
        reviewer=identity("declaration-reviewer"), disposition=GenerationDisposition.ACCEPTED
    )

    assert adjudicated.reviewer.identifier == "declaration-reviewer"
    assert adjudicated.disposition is GenerationDisposition.ACCEPTED
    evidence = adjudicated.proposal_evidence()
    assert evidence.summary == "drafted by declaration-drafter and reviewed by declaration-reviewer"


@pytest.mark.parametrize("disposition", [GenerationDisposition.PENDING, GenerationDisposition.REJECTED])
def test_an_unaccepted_draft_yields_no_evidence_reference(disposition):
    adjudicated = proposed().adjudicated(reviewer=identity("declaration-reviewer"), disposition=disposition)

    with pytest.raises(DeclarationDraftError, match="accepted adjudication"):
        adjudicated.proposal_evidence()


def test_the_drafting_actor_cannot_review_its_own_draft():
    with pytest.raises(DeclarationDraftError, match="distinct from the drafting actor"):
        proposed().adjudicated(
            reviewer=identity("declaration-drafter"), disposition=GenerationDisposition.ACCEPTED
        )


def test_a_model_actor_is_not_a_declared_reviewer_identity():
    with pytest.raises(DeclarationDraftError, match="must be a declared identity"):
        proposed().adjudicated(reviewer=model(), disposition=GenerationDisposition.ACCEPTED)


def test_an_undeclared_disposition_is_refused():
    with pytest.raises(DeclarationDraftError, match="adjudicated disposition"):
        proposed().adjudicated(reviewer=identity("declaration-reviewer"), disposition="accepted")


def test_a_proposal_needs_a_named_drafting_actor():
    draft = draft_declaration(request())

    with pytest.raises(DeclarationDraftError, match="drafting actor is required"):
        draft.proposed(proposal_id="p1", version="v1", drafted_by="")
