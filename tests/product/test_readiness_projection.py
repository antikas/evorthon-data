"""Per-segment readiness: the fact table, the fallbacks, the gaps it suggests work for,
the two use-case statements, and the canonical bytes and digest the projection owns."""
# evorthon-verifies: EVD-README-049
# evorthon-verifies: EVD-README-045
import ast
import hashlib
import json
from pathlib import Path

import pytest

from evorthon_data import readiness
from evorthon_data.engagement.use_case import (
    AuthorityRole,
    AvailabilityState,
    BuildRoute,
    ConditionKey,
    ConditionOverride,
    DatasetAvailability,
    ReplacedOutput,
    SegmentBoundary,
    UseCase,
    UseCaseError,
)
from evorthon_data.readiness import projection as module
from evorthon_data.readiness import (
    AVAILABILITY_EVIDENCE,
    DATASET_FACT_KINDS,
    DIGEST_SIZE_BYTES,
    GAP_OWNER_ROLES,
    GAP_TITLE_ACTIONS,
    READINESS_PROJECTION_FORM,
    SYNTHETIC_FILLABLE,
    CaseDataset,
    CaseExpectedOutput,
    CaseFacts,
    FactEvidence,
    FactKind,
    OpenCondition,
    ReadinessError,
    ReadinessProjection,
    RefusalReason,
    SegmentState,
    project_readiness,
    projection_digest,
    render_projection,
    suggested_item_title,
)
from evorthon_data.verification.domain.contracts import (
    DOMAIN_ENUM_TYPES,
    DatasetProvenance,
    DatasetRole,
    DiagnosticStrength,
    ExpectedOutputOrigin,
    GrainDeclaration,
    SchemaDeclaration,
    VerificationStatus,
)

# The use-case aggregate's own fixture builders. Reusing them keeps one owner for
# the shape of a recorded use case.
from test_use_case_aggregate import (
    answered,
    authority,
    build_route,
    dataset,
    human,
    identity,
    intermediate,
    opened,
    scenario,
    scenario_result,
    source_combination,
    target_output,
    unanswered,
)


CASE = "case-normal-day"
STEP = "settled-orders"
OUTPUT = "daily-order-report"
INPUT_ID = "order-extract"
REFERENCE_ID = "product-master"
MODULE_SOURCE = Path(module.__file__).read_text(encoding="utf-8")
DOMAIN_ENUM_NAMES = {enumeration.__name__ for enumeration in DOMAIN_ENUM_TYPES}


def defined_output(**overrides):
    """A target output that names the specification it is built to."""
    declared = {"defined_by": identity("orders-specification")}
    declared.update(overrides)
    return target_output(**declared)


def reference_dataset(**overrides):
    declared = {"placeholder_id": REFERENCE_ID, "role": DatasetRole.REFERENCE}
    declared.update(overrides)
    return dataset(**declared)


def combination(segment_id: str = STEP, **overrides):
    """The declared merge over the two sources the first span reads."""
    declared = {"segment_id": segment_id, "sources": (INPUT_ID, REFERENCE_ID), "keys": ("order_id",)}
    declared.update(overrides)
    return source_combination(**declared)


def evidence_owner(subject: str = STEP):
    return authority(role=AuthorityRole.EVIDENCE_OWNER, actor=human("evidence-owner"), subject=subject)


def expected_by(day: str = "2026-10-01") -> DatasetAvailability:
    return DatasetAvailability(state=AvailabilityState.OBTAINABLE_BY, obtainable_by=day)


def absent() -> DatasetAvailability:
    return DatasetAvailability(state=AvailabilityState.UNOBTAINABLE)


def use_case_with(
    *,
    outputs=(),
    datasets=(),
    steps=(),
    routes=(),
    combinations=(),
    authorities=(),
    scenarios=(),
    conditions=(),
    results=(),
) -> UseCase:
    subject = opened()
    for output in outputs:
        subject = subject.record_target_output(output)
    for placeholder in datasets:
        subject = subject.record_dataset(placeholder)
    for step in steps:
        subject = subject.record_intermediate_result(step)
    for route in routes:
        subject = subject.record_build_route(route)
    for declared in combinations:
        subject = subject.record_source_combination(declared)
    for named in authorities:
        subject = subject.record_authority(named)
    for reference in scenarios:
        subject = subject.record_scenario(reference)
    for condition in conditions:
        subject = subject.record_condition(condition)
    for result in results:
        subject = subject.record_scenario_result(result)
    return subject


def full_use_case(**overrides) -> UseCase:
    """A use case whose every readiness fact is answered."""
    declared = {
        "outputs": (defined_output(),),
        "datasets": (dataset(), reference_dataset()),
        "steps": (intermediate(),),
        "routes": (build_route(segment_id=STEP), build_route(segment_id=OUTPUT)),
        "combinations": (combination(),),
        "authorities": (authority(), evidence_owner()),
        "scenarios": (scenario(CASE),),
    }
    declared.update(overrides)
    return use_case_with(**declared)


def full_index(**overrides):
    """A case index whose every supplied fact is real evidence."""
    declared = {
        "datasets": (
            CaseDataset(dataset_id=INPUT_ID, role=DatasetRole.INPUT, provenance=DatasetProvenance.REAL),
            CaseDataset(
                dataset_id=REFERENCE_ID, role=DatasetRole.REFERENCE, provenance=DatasetProvenance.REAL
            ),
        ),
        "expected_outputs": (
            CaseExpectedOutput(
                output_id=OUTPUT,
                provenance=DatasetProvenance.REAL,
                origin=ExpectedOutputOrigin.MODERNISATION_CAPTURE,
            ),
        ),
        "checkpoints": (STEP,),
        "result_status": VerificationStatus.PASS,
    }
    declared.update(overrides)
    return {identity(CASE): CaseFacts(**declared)}


def only(entries, kind: FactKind):
    """The one entry of the requested kind."""
    found = [entry for entry in entries if entry.kind is kind]
    assert len(found) == 1, f"expected one {kind.value} entry, found {len(found)}"
    return found[0]


def sorted_keys(node) -> bool:
    if isinstance(node, dict):
        return list(node) == sorted(node) and all(sorted_keys(value) for value in node.values())
    if isinstance(node, list):
        return all(sorted_keys(item) for item in node)
    return True


# --- the five fallback rows -------------------------------------------------


def test_a_defined_intermediate_with_no_target_output_leaves_one_buildable_segment_and_one_gap():
    subject = use_case_with(
        datasets=(dataset(),),
        steps=(intermediate(),),
        authorities=(authority(), evidence_owner()),
        scenarios=(scenario(CASE),),
    )
    result = project_readiness(subject, {identity(CASE): CaseFacts(checkpoints=(STEP,))})

    assert len(result.segments) == 1
    assert result.segments[0].segment_id == STEP
    assert result.segments[0].state is SegmentState.BUILDABLE
    assert result.segments[0].gaps == ()
    assert len(result.gaps) == 1
    gap = result.gaps[0]
    assert gap.kind is FactKind.OUTPUT_DEFINITION
    assert gap.synthetic_fillable is False
    assert gap.segment_id is None
    assert gap.suggested_owner == human()
    assert gap.suggested_title == "Define the target output uc-order-volume"


def test_a_missing_input_keeps_the_segment_building_on_a_synthetic_fill():
    subject = full_use_case(datasets=(dataset(availability=expected_by()), reference_dataset()))

    result = project_readiness(subject, full_index())

    first = result.segments[0]
    assert first.state is SegmentState.BUILDABLE_WITH_FALLBACKS
    assert only(first.facts, FactKind.INPUT_DATASET).evidence is FactEvidence.MISSING
    gap = only(first.gaps, FactKind.INPUT_DATASET)
    assert gap.synthetic_fillable is True
    assert gap.suggested_owner == human("data-owner")
    assert gap.segment_id == STEP
    assert gap.suggested_title == "Obtain the input dataset order-extract"


def test_a_missing_reference_dataset_is_a_synthetic_fillable_gap():
    subject = full_use_case(datasets=(dataset(), reference_dataset(availability=absent())))

    result = project_readiness(subject, full_index())

    first = result.segments[0]
    assert first.state is SegmentState.BUILDABLE_WITH_FALLBACKS
    gap = only(first.gaps, FactKind.REFERENCE_DATASET)
    assert gap.kind is FactKind.REFERENCE_DATASET
    assert gap.synthetic_fillable is True
    assert gap.suggested_owner == human("data-owner")
    assert gap.suggested_title == "Obtain the reference dataset product-master"


def test_an_expected_output_without_an_origin_is_filled_by_rule_derivation():
    without_origin = full_index(
        expected_outputs=(CaseExpectedOutput(output_id=OUTPUT, provenance=DatasetProvenance.REAL),)
    )

    result = project_readiness(full_use_case(), without_origin)

    reached = result.segments[-1]
    assert reached.reaches is SegmentBoundary.TARGET_OUTPUT
    assert only(reached.facts, FactKind.EXPECTED_OUTPUT).evidence is FactEvidence.MISSING
    gap = only(reached.gaps, FactKind.EXPECTED_OUTPUT)
    assert gap.synthetic_fillable is True
    assert gap.suggested_title == "Approve the expected output for daily-order-report"

    derived = full_index(
        expected_outputs=(
            CaseExpectedOutput(
                output_id=OUTPUT,
                provenance=DatasetProvenance.SYNTHETIC,
                origin=ExpectedOutputOrigin.SYNTHETIC_DERIVATION,
            ),
        )
    )
    filled = project_readiness(full_use_case(), derived).segments[-1]
    assert only(filled.facts, FactKind.EXPECTED_OUTPUT).evidence is FactEvidence.SYNTHETIC
    assert filled.state is SegmentState.BUILDABLE_WITH_FALLBACKS
    assert filled.gaps == ()


def test_an_intermediate_without_an_evidence_owner_stays_buildable_and_output_only():
    subject = full_use_case(authorities=(authority(),))

    result = project_readiness(subject, full_index())

    first = result.segments[0]
    assert first.state is SegmentState.BUILDABLE
    assert first.diagnostic_strength is DiagnosticStrength.OUTPUT_ONLY
    assert only(first.facts, FactKind.CHECKPOINT).evidence is FactEvidence.MISSING
    gap = only(first.gaps, FactKind.CHECKPOINT)
    assert gap.kind is FactKind.CHECKPOINT
    assert gap.synthetic_fillable is False
    assert gap.suggested_owner == human()
    assert gap.suggested_title == "Name the evidence owner for the checkpoint settled-orders"


def test_a_segment_reading_two_sources_with_no_declared_combination_carries_a_gap():
    subject = full_use_case(combinations=())

    result = project_readiness(subject, full_index())

    first = result.segments[0]
    assert subject.segments()[0].sources == (INPUT_ID, REFERENCE_ID)
    assert only(first.facts, FactKind.SOURCE_COMBINATION).evidence is FactEvidence.MISSING
    gap = only(first.gaps, FactKind.SOURCE_COMBINATION)
    assert gap.subject == STEP
    assert gap.segment_id == STEP
    assert gap.synthetic_fillable is False
    assert gap.suggested_owner == human()
    assert gap.suggested_title == "Declare how the sources combine for settled-orders"
    assert first.state is SegmentState.BUILDABLE
    assert result.buildable is True


def test_a_declared_combination_answers_the_row_and_one_source_is_never_read_for_it():
    declared = project_readiness(full_use_case(), full_index()).segments

    assert only(declared[0].facts, FactKind.SOURCE_COMBINATION).evidence is FactEvidence.REAL
    assert declared[0].gaps == ()
    # The second span reads the checkpoint the first reaches, so it reads one
    # source and carries no combination row at all.
    assert [fact.kind for fact in declared[1].facts if fact.kind is FactKind.SOURCE_COMBINATION] == []
    assert declared[1].state is SegmentState.BUILDABLE


def test_the_combination_gap_falls_to_the_ambiguity_resolver_before_the_accepting_authority():
    resolver = authority(role=AuthorityRole.AMBIGUITY_RESOLVER, actor=human("ambiguity-resolver"))
    subject = full_use_case(combinations=(), authorities=(authority(), evidence_owner(), resolver))

    result = project_readiness(subject, full_index())

    gap = only(result.segments[0].gaps, FactKind.SOURCE_COMBINATION)
    assert gap.suggested_owner == human("ambiguity-resolver")
    assert GAP_OWNER_ROLES[FactKind.SOURCE_COMBINATION] == (
        AuthorityRole.AMBIGUITY_RESOLVER,
        AuthorityRole.ACCEPTING,
    )


# --- the two use-case statements --------------------------------------------


def test_a_fully_specified_use_case_is_buildable():
    result = project_readiness(full_use_case(), full_index())

    assert [segment.segment_id for segment in result.segments] == [STEP, OUTPUT]
    assert [segment.state for segment in result.segments] == [SegmentState.BUILDABLE] * 2
    assert [segment.route for segment in result.segments] == [BuildRoute.ENGINEERED] * 2
    assert result.segments[0].diagnostic_strength is DiagnosticStrength.CHECKPOINTED
    assert result.gaps == ()
    assert result.buildable is True
    assert all(fact.evidence is FactEvidence.REAL for segment in result.segments for fact in segment.facts)


def test_passing_results_make_a_segment_acceptable_now():
    passing = project_readiness(full_use_case(), full_index())

    assert [segment.acceptable_now for segment in passing.segments] == [True, True]
    assert passing.acceptable_now is True

    failing = project_readiness(full_use_case(), full_index(result_status=VerificationStatus.FAIL))
    assert [segment.acceptable_now for segment in failing.segments] == [False, False]
    assert failing.acceptable_now is False

    unjudged = project_readiness(full_use_case(), {})
    assert unjudged.acceptable_now is False
    assert unjudged.buildable is True


def test_a_use_case_with_one_gapped_segment_still_reports_what_builds():
    subject = full_use_case(outputs=(target_output(),))

    result = project_readiness(subject, full_index())

    reached = result.segments[-1]
    assert reached.state is SegmentState.GAPPED
    assert reached.acceptable_now is False
    gap = only(reached.gaps, FactKind.OUTPUT_DEFINITION)
    assert gap.synthetic_fillable is False
    assert gap.segment_id == OUTPUT
    assert gap.suggested_owner == human()
    assert result.segments[0].state is SegmentState.BUILDABLE
    assert result.buildable is True


def test_a_modernisation_target_is_defined_by_the_output_it_replaces():
    replacing = target_output(
        replaces=ReplacedOutput(
            identity=identity("legacy-order-report"), system="reporting-mainframe", location="reports/daily"
        )
    )

    result = project_readiness(full_use_case(outputs=(replacing,)), full_index())

    assert result.segments[-1].state is SegmentState.BUILDABLE
    assert only(result.segments[-1].facts, FactKind.OUTPUT_DEFINITION).evidence is FactEvidence.REAL


def test_a_target_output_cannot_be_declared_without_its_shape():
    """The shape is part of the record, so the fact reads the part that can be absent."""
    empty_grain = GrainDeclaration(
        grain_id="one-row-per-order",
        version="v1",
        key_fields=(),
        population_description="settled orders",
        duplicate_keys_permitted=False,
    )
    with pytest.raises(UseCaseError, match="keys"):
        target_output(grain=empty_grain)
    with pytest.raises(UseCaseError, match="schema"):
        target_output(schema=SchemaDeclaration(schema_id="s", version="v1", fields=(), format_name="tabular"))


# --- open conditions --------------------------------------------------------


def test_open_conditions_carry_the_default_and_the_value_in_force():
    overridden = unanswered(
        ConditionKey.MONITORING, override=ConditionOverride(value="a daily check", author=human())
    )
    subject = full_use_case(
        conditions=(
            unanswered(ConditionKey.RETENTION_WINDOW),
            answered(ConditionKey.BACKFILL_DEPTH, value="two years"),
            overridden,
        )
    )

    result = project_readiness(subject, full_index())

    assert result.open_conditions == (
        OpenCondition(key=ConditionKey.RETENTION_WINDOW, default_value="keep everything", value="keep everything"),
        OpenCondition(key=ConditionKey.MONITORING, default_value="none", value="a daily check"),
    )


# --- the suggested disposition and the suggested titles ---------------------


def test_the_suggested_disposition_is_one_line_this_module_owns():
    result = project_readiness(full_use_case(), full_index())

    assert result.suggested_disposition == (
        "2 of 2 segments buildable; 0 built on labelled fallbacks; "
        "0 gaps outstanding; 0 conditions open; 2 acceptable now"
    )
    assert result.suggested_disposition.isascii()
    assert "\n" not in result.suggested_disposition
    assert result.suggested_disposition.encode("ascii") in render_projection(result)


def test_the_suggested_disposition_counts_what_the_projection_holds():
    subject = full_use_case(
        outputs=(target_output(),),
        datasets=(dataset(availability=expected_by()), reference_dataset()),
        conditions=(unanswered(ConditionKey.RETENTION_WINDOW),),
    )

    result = project_readiness(subject, full_index())

    assert result.suggested_disposition == (
        "1 of 2 segments buildable; 1 built on labelled fallbacks; "
        "2 gaps outstanding; 1 condition open; 1 acceptable now"
    )


def test_the_suggested_item_title_has_one_form_per_gap_kind():
    assert suggested_item_title(FactKind.INPUT_DATASET, INPUT_ID) == "Obtain the input dataset order-extract"
    assert (
        suggested_item_title(FactKind.REFERENCE_DATASET, REFERENCE_ID)
        == "Obtain the reference dataset product-master"
    )
    assert suggested_item_title(FactKind.OUTPUT_DEFINITION, OUTPUT) == "Define the target output daily-order-report"
    assert (
        suggested_item_title(FactKind.EXPECTED_OUTPUT, OUTPUT)
        == "Approve the expected output for daily-order-report"
    )
    assert (
        suggested_item_title(FactKind.CHECKPOINT, STEP)
        == "Name the evidence owner for the checkpoint settled-orders"
    )
    assert (
        suggested_item_title(FactKind.SOURCE_COMBINATION, STEP)
        == "Declare how the sources combine for settled-orders"
    )
    for kind in FactKind:
        title = suggested_item_title(kind, "a-subject")
        assert title == f"{GAP_TITLE_ACTIONS[kind]} a-subject"
        assert title.isascii()


def test_every_reported_gap_carries_the_title_of_its_own_kind_and_subject():
    result = project_readiness(every_gap_use_case(), {})

    for gap in result.gaps:
        assert gap.suggested_title == suggested_item_title(gap.kind, gap.subject)
        assert gap.synthetic_fillable is SYNTHETIC_FILLABLE[gap.kind]


# --- the canonical bytes and the digest --------------------------------------


def test_two_runs_render_identical_bytes():
    first = render_projection(project_readiness(full_use_case(), full_index()))
    second = render_projection(project_readiness(full_use_case(), full_index()))

    assert first == second
    assert projection_digest(project_readiness(full_use_case(), full_index())) == hashlib.blake2b(
        first, digest_size=DIGEST_SIZE_BYTES
    ).hexdigest()


def test_a_changed_fact_changes_the_digest():
    unchanged = project_readiness(full_use_case(), full_index())
    changed = project_readiness(
        full_use_case(datasets=(dataset(availability=expected_by()), reference_dataset())), full_index()
    )

    assert render_projection(unchanged) != render_projection(changed)
    assert projection_digest(unchanged) != projection_digest(changed)

    relabelled = project_readiness(
        full_use_case(),
        full_index(
            datasets=(
                CaseDataset(
                    dataset_id=INPUT_ID, role=DatasetRole.INPUT, provenance=DatasetProvenance.SYNTHETIC
                ),
            )
        ),
    )
    assert projection_digest(relabelled) != projection_digest(unchanged)


def test_the_digest_is_blake2b_over_exactly_the_rendered_bytes():
    result = project_readiness(full_use_case(), full_index())
    rendered = render_projection(result)

    assert projection_digest(result) == hashlib.blake2b(rendered, digest_size=32).hexdigest()
    assert len(projection_digest(result)) == 64
    assert projection_digest(result) != hashlib.blake2b(rendered + b" ", digest_size=32).hexdigest()


def test_the_rendered_bytes_are_sorted_ascii_keys_with_compact_separators_and_a_line_feed():
    rendered = render_projection(project_readiness(full_use_case(), full_index()))
    text = rendered.decode("ascii")

    assert rendered.endswith(b"\n")
    assert b"\r" not in rendered
    assert text.strip().startswith("{") and text.strip().endswith("}")
    assert ", " not in text and ": " not in text
    payload = json.loads(text)
    assert sorted_keys(payload)
    assert payload["form"] == READINESS_PROJECTION_FORM
    assert payload["use_case_id"] == "uc-order-volume"
    assert payload["buildable"] is True
    assert payload["acceptable_now"] is True
    assert payload["segments"][0]["state"] == "buildable"
    assert payload["segments"][0]["reaches"] == "intermediate_result"
    assert payload["segments"][0]["route"] == "engineered"
    assert payload["segments"][0]["diagnostic_strength"] == "checkpointed"


def test_the_rendered_leaf_values_are_the_declared_string_and_enum_forms():
    subject = full_use_case(
        datasets=(dataset(availability=expected_by()), reference_dataset()),
        conditions=(unanswered(ConditionKey.RETENTION_WINDOW),),
    )
    payload = json.loads(render_projection(project_readiness(subject, full_index())).decode("ascii"))

    facts = payload["segments"][0]["facts"]
    assert {fact["kind"] for fact in facts} == {kind.value for kind in FactKind} - {
        "expected_output",
    }
    assert {fact["evidence"] for fact in facts} <= {evidence.value for evidence in FactEvidence}
    gap = payload["segments"][0]["gaps"][0]
    assert gap["kind"] == FactKind.INPUT_DATASET.value
    assert gap["suggested_owner"] == "data-owner"
    assert gap["synthetic_fillable"] is True
    assert payload["open_conditions"] == [
        {
            "key": ConditionKey.RETENTION_WINDOW.value,
            "default_value": "keep everything",
            "value": "keep everything",
        }
    ]


# --- readiness is advice ------------------------------------------------------


def every_gap_use_case() -> UseCase:
    """A use case that carries every gap kind at once."""
    return use_case_with(
        outputs=(target_output(),),
        datasets=(dataset(availability=expected_by()), reference_dataset(availability=absent())),
        steps=(intermediate(),),
        authorities=(authority(),),
    )


def test_a_use_case_carrying_every_gap_kind_projects_without_raising():
    result = project_readiness(every_gap_use_case(), {})

    assert {gap.kind for gap in result.gaps} == set(FactKind)
    assert result.segments[0].state is SegmentState.BUILDABLE_WITH_FALLBACKS
    assert result.segments[-1].state is SegmentState.GAPPED
    assert result.buildable is True
    assert result.acceptable_now is False
    assert projection_digest(result)


def test_synthetic_evidence_is_labelled_and_never_refused():
    subject = full_use_case(
        datasets=(
            dataset(
                availability=DatasetAvailability(
                    state=AvailabilityState.SYNTHETIC_FILLED, dataset=identity("order-extract-synthetic")
                )
            ),
            reference_dataset(),
        )
    )

    result = project_readiness(subject, full_index())

    assert only(result.segments[0].facts, FactKind.INPUT_DATASET).evidence is FactEvidence.SYNTHETIC
    assert result.segments[0].state is SegmentState.BUILDABLE_WITH_FALLBACKS
    assert result.segments[0].gaps == ()


def test_a_case_that_declares_an_obtained_dataset_synthetic_labels_it_synthetic():
    relabelled = full_index(
        datasets=(
            CaseDataset(dataset_id=INPUT_ID, role=DatasetRole.INPUT, provenance=DatasetProvenance.DERIVED),
        )
    )

    result = project_readiness(full_use_case(), relabelled)

    assert only(result.segments[0].facts, FactKind.INPUT_DATASET).evidence is FactEvidence.SYNTHETIC
    assert only(result.segments[0].facts, FactKind.REFERENCE_DATASET).evidence is FactEvidence.REAL


def test_the_state_vocabulary_has_no_word_for_a_use_case_that_cannot_start():
    assert [state.value for state in SegmentState] == ["buildable", "buildable_with_fallbacks", "gapped"]
    forbidden = {"block", "blocked", "blocking", "halted", "stopped", "waiting", "unbuildable"}
    for state in SegmentState:
        assert not set(state.value.split("_")) & forbidden
        assert not set(state.name.lower().split("_")) & forbidden
    assert [name for name in dir(readiness) if "block" in name.lower()] == []


def test_every_refusal_reason_is_an_integrity_reason():
    assert {reason.value for reason in RefusalReason} == {
        "invalid-input",
        "unknown-case-identity",
        "contradictory-case-entry",
        "undeclared-representation",
    }
    advisory = {"provenance", "assurance", "synthetic", "readiness", "policy", "gap", "quality"}
    for reason in RefusalReason:
        assert not set(reason.value.split("-")) & advisory


# --- the rules are declared once and cover their vocabulary ------------------


def test_every_gap_kind_declares_a_fill_rule_an_owner_rule_and_a_title():
    assert set(SYNTHETIC_FILLABLE) == set(FactKind)
    assert set(GAP_OWNER_ROLES) == set(FactKind)
    assert set(GAP_TITLE_ACTIONS) == set(FactKind)
    assert SYNTHETIC_FILLABLE[FactKind.OUTPUT_DEFINITION] is False
    assert SYNTHETIC_FILLABLE[FactKind.CHECKPOINT] is False
    assert SYNTHETIC_FILLABLE[FactKind.SOURCE_COMBINATION] is False


def test_every_declared_availability_state_and_dataset_role_has_a_rule():
    assert set(AVAILABILITY_EVIDENCE) == set(AvailabilityState)
    assert set(DATASET_FACT_KINDS) == set(DatasetRole)


def test_the_projection_reports_the_spans_the_record_derives():
    subject = full_use_case()

    result = project_readiness(subject, full_index())

    assert [segment.segment_id for segment in result.segments] == [
        span.segment_id for span in subject.segments()
    ]
    assert [segment.reaches for segment in result.segments] == [span.reaches for span in subject.segments()]
    assert "use_case.segments()" in MODULE_SOURCE
    assert "intermediate_results" not in MODULE_SOURCE


# --- no wire form for a verification-domain record ---------------------------


def domain_imports() -> set[str]:
    names: set[str] = set()
    for statement in ast.walk(ast.parse(MODULE_SOURCE)):
        if isinstance(statement, ast.ImportFrom) and (statement.module or "").endswith("domain.contracts"):
            names.update(alias.name for alias in statement.names)
    return names


def test_the_module_reads_domain_enumerations_and_the_case_identity_only():
    names = domain_imports()

    assert names
    assert names <= DOMAIN_ENUM_NAMES | {"Identity"}
    assert "fields(" not in MODULE_SOURCE
    assert "asdict" not in MODULE_SOURCE
    assert "DOMAIN_RECORD_TYPES" not in MODULE_SOURCE
    assert "DOMAIN_FIELD_INVENTORY" not in MODULE_SOURCE


def test_the_rendered_bytes_carry_no_verification_domain_record():
    rendered = render_projection(project_readiness(every_gap_use_case(), {})).decode("ascii")
    judged = render_projection(project_readiness(full_use_case(), full_index())).decode("ascii")

    for text in (rendered, judged):
        assert "digest-case-normal-day" not in text
        assert "digest-orders-specification" not in text
        for field in ("identifier", "content_digest", "row_count", "approved_summary", "canonicalisation"):
            assert f'"{field}"' not in text


# --- integrity refusals -------------------------------------------------------


def test_a_record_that_is_not_a_use_case_is_refused():
    with pytest.raises(ReadinessError) as refusal:
        project_readiness("uc-order-volume", {})
    assert refusal.value.reason is RefusalReason.INVALID_INPUT


def test_a_case_index_that_is_not_a_mapping_is_refused():
    with pytest.raises(ReadinessError) as refusal:
        project_readiness(full_use_case(), [CaseFacts()])
    assert refusal.value.reason is RefusalReason.INVALID_INPUT


def test_a_case_index_key_that_is_not_a_case_identity_is_refused():
    with pytest.raises(ReadinessError) as refusal:
        project_readiness(full_use_case(), {CASE: CaseFacts()})
    assert refusal.value.reason is RefusalReason.INVALID_INPUT


def test_a_case_index_value_that_is_not_declared_case_facts_is_refused():
    with pytest.raises(ReadinessError) as refusal:
        project_readiness(full_use_case(), {identity(CASE): {"checkpoints": (STEP,)}})
    assert refusal.value.reason is RefusalReason.INVALID_INPUT


def test_a_case_identity_the_use_case_does_not_reference_is_refused():
    with pytest.raises(ReadinessError) as refusal:
        project_readiness(full_use_case(), {identity("case-late-arrivals"): CaseFacts()})
    assert refusal.value.reason is RefusalReason.UNKNOWN_CASE_IDENTITY


def test_a_case_status_the_record_contradicts_is_refused():
    subject = full_use_case(results=(scenario_result(CASE, VerificationStatus.FAIL),))

    with pytest.raises(ReadinessError) as refusal:
        project_readiness(subject, full_index(result_status=VerificationStatus.PASS))
    assert refusal.value.reason is RefusalReason.CONTRADICTORY_CASE_ENTRY


def test_a_case_naming_one_dataset_twice_is_refused():
    with pytest.raises(ReadinessError) as refusal:
        CaseFacts(
            datasets=(
                CaseDataset(dataset_id=INPUT_ID, role=DatasetRole.INPUT, provenance=DatasetProvenance.REAL),
                CaseDataset(
                    dataset_id=INPUT_ID, role=DatasetRole.INPUT, provenance=DatasetProvenance.SYNTHETIC
                ),
            )
        )
    assert refusal.value.reason is RefusalReason.CONTRADICTORY_CASE_ENTRY


def test_a_case_naming_one_expected_output_or_checkpoint_twice_is_refused():
    with pytest.raises(ReadinessError) as outputs:
        CaseFacts(
            expected_outputs=(
                CaseExpectedOutput(output_id=OUTPUT, provenance=DatasetProvenance.REAL),
                CaseExpectedOutput(output_id=OUTPUT, provenance=DatasetProvenance.DERIVED),
            )
        )
    assert outputs.value.reason is RefusalReason.CONTRADICTORY_CASE_ENTRY

    with pytest.raises(ReadinessError) as checkpoints:
        CaseFacts(checkpoints=(STEP, STEP))
    assert checkpoints.value.reason is RefusalReason.CONTRADICTORY_CASE_ENTRY


def test_an_expected_output_whose_origin_and_provenance_disagree_is_refused():
    with pytest.raises(ReadinessError) as derived:
        CaseExpectedOutput(
            output_id=OUTPUT,
            provenance=DatasetProvenance.REAL,
            origin=ExpectedOutputOrigin.SYNTHETIC_DERIVATION,
        )
    assert derived.value.reason is RefusalReason.CONTRADICTORY_CASE_ENTRY

    with pytest.raises(ReadinessError) as captured:
        CaseExpectedOutput(
            output_id=OUTPUT,
            provenance=DatasetProvenance.SYNTHETIC,
            origin=ExpectedOutputOrigin.MODERNISATION_CAPTURE,
        )
    assert captured.value.reason is RefusalReason.CONTRADICTORY_CASE_ENTRY


def test_an_undeclared_case_value_is_refused_rather_than_guessed():
    with pytest.raises(ReadinessError) as role:
        CaseDataset(dataset_id=INPUT_ID, role="input", provenance=DatasetProvenance.REAL)
    assert role.value.reason is RefusalReason.UNDECLARED_REPRESENTATION

    with pytest.raises(ReadinessError) as provenance:
        CaseDataset(dataset_id=INPUT_ID, role=DatasetRole.INPUT, provenance="real")
    assert provenance.value.reason is RefusalReason.UNDECLARED_REPRESENTATION

    with pytest.raises(ReadinessError) as status:
        CaseFacts(result_status="pass")
    assert status.value.reason is RefusalReason.UNDECLARED_REPRESENTATION


def test_an_unknown_availability_state_is_refused_rather_than_guessed():
    placeholder = dataset()
    object.__setattr__(placeholder.availability, "state", AvailabilityState.OBTAINED.value)
    subject = full_use_case(datasets=(placeholder, reference_dataset()))

    with pytest.raises(ReadinessError) as refusal:
        project_readiness(subject, full_index())
    assert refusal.value.reason is RefusalReason.UNDECLARED_REPRESENTATION


def test_an_unknown_dataset_role_is_refused_rather_than_guessed():
    placeholder = dataset()
    object.__setattr__(placeholder, "role", DatasetRole.INPUT.value)
    subject = full_use_case(datasets=(placeholder, reference_dataset()))

    with pytest.raises(ReadinessError) as refusal:
        project_readiness(subject, full_index())
    assert refusal.value.reason is RefusalReason.UNDECLARED_REPRESENTATION


def test_a_case_entry_that_records_no_identity_or_no_tuple_is_refused():
    with pytest.raises(ReadinessError) as unnamed:
        CaseDataset(dataset_id="   ", role=DatasetRole.INPUT, provenance=DatasetProvenance.REAL)
    assert unnamed.value.reason is RefusalReason.INVALID_INPUT

    with pytest.raises(ReadinessError) as unnamed_output:
        CaseExpectedOutput(output_id="", provenance=DatasetProvenance.REAL)
    assert unnamed_output.value.reason is RefusalReason.INVALID_INPUT

    with pytest.raises(ReadinessError) as sequence:
        CaseFacts(checkpoints=[STEP])
    assert sequence.value.reason is RefusalReason.INVALID_INPUT

    with pytest.raises(ReadinessError) as undeclared:
        CaseFacts(datasets=(INPUT_ID,))
    assert undeclared.value.reason is RefusalReason.INVALID_INPUT

    with pytest.raises(ReadinessError) as checkpoint:
        CaseFacts(checkpoints=(" ",))
    assert checkpoint.value.reason is RefusalReason.INVALID_INPUT


def test_a_title_for_an_undeclared_kind_or_an_unnamed_subject_is_refused():
    with pytest.raises(ReadinessError) as kind:
        suggested_item_title("input_dataset", INPUT_ID)
    assert kind.value.reason is RefusalReason.UNDECLARED_REPRESENTATION

    with pytest.raises(ReadinessError) as subject:
        suggested_item_title(FactKind.INPUT_DATASET, "")
    assert subject.value.reason is RefusalReason.INVALID_INPUT


def test_rendering_anything_but_a_projection_is_refused():
    with pytest.raises(ReadinessError) as refusal:
        render_projection({"use_case_id": "uc-order-volume"})
    assert refusal.value.reason is RefusalReason.INVALID_INPUT


def test_an_empty_use_case_reports_the_undefined_target_without_raising():
    result = project_readiness(opened(), {})

    assert isinstance(result, ReadinessProjection)
    assert result.segments == ()
    assert result.buildable is False
    assert result.acceptable_now is False
    assert [gap.kind for gap in result.gaps] == [FactKind.OUTPUT_DEFINITION]
    assert result.gaps[0].suggested_owner is None
