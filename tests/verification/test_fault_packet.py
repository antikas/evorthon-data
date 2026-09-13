"""Deterministic fault classification and the packet: every class, threshold and bound."""
# evorthon-verifies: EVD-README-022
from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

import test_intake_workflow as intake_fixture
import test_reconciliation as fixture
from evorthon_data.verification.core.canonical import canonical_digest
from evorthon_data.verification.core.fault import (
    CONTRADICTING_SUMMARY,
    DIMENSION_PRECEDENCE,
    DISCLOSURE_CEILING,
    FAULT_PACKET_FORM,
    LOCALISATION_SUMMARY,
    LOWER_FRONTIER_SUMMARY,
    MAX_CHECKPOINTS_PER_PATH,
    MAX_DISCLOSED_EXAMPLES,
    MAX_EVIDENCE_REFERENCES,
    MAX_FRONTIER_CHECKPOINTS,
    MAX_UNCOVERED_PATHS,
    SMALL_CELL_FLOOR,
    SUPPORTING_SUMMARY,
    UNCOVERED_PATH_SUMMARY,
    UNDECIDED_DIMENSIONS,
    UPPER_FRONTIER_SUMMARY,
    FaultEvidence,
    FaultRefusalReason,
    FaultRefused,
    build_fault_packet,
    build_fault_packets,
    classify_fault,
    decide_disclosure,
    declare_confidence,
    packet_fields,
)
from evorthon_data.verification.core.localisation import (
    CheckpointComparison,
    OutputOutcome,
    localise,
    localise_output,
)
from evorthon_data.verification.core.reconciliation import RECONCILIATION_FORM, FindingSeverity
from evorthon_data.verification.domain.contracts import (
    AdviserConfidence,
    CandidateIdentity,
    ComparisonDimension,
    DatasetProvenance,
    DatasetRole,
    DisclosureDecision,
    EvidenceReference,
    FaultClass,
    Identity,
    IndependentlyDerivedReceipt,
    LocalisationStatus,
    ReceiptSubject,
    RepeatRunIdentity,
    UncoveredPath,
    UncoveredPathReason,
    VerificationResult,
    VerificationStatus,
)
from evorthon_data.verification.enforcement.privacy import (
    PrivacyRefusalReason,
    PrivacyRefused,
    inspect_fault_packet,
)
from evorthon_data.verification.enforcement.validation import inspect_verification_record

OUTPUT_ID = fixture.OUTPUT_ID
DECLARED_SUMMARIES = frozenset(
    {
        SUPPORTING_SUMMARY,
        CONTRADICTING_SUMMARY,
        UPPER_FRONTIER_SUMMARY,
        LOWER_FRONTIER_SUMMARY,
        UNCOVERED_PATH_SUMMARY,
        LOCALISATION_SUMMARY,
    }
)


def fingerprint(name: str) -> str:
    """Return an opaque fingerprint for one declared name."""
    return canonical_digest(name.encode("utf-8"))


def identity(name: str) -> Identity:
    return Identity(name, "v1", fingerprint(name))


def evidence(name: str) -> EvidenceReference:
    return EvidenceReference(name, "v1", fingerprint(name), "declared evidence for one observed fact")


def receipt(subject: ReceiptSubject, *, matched: bool) -> IndependentlyDerivedReceipt:
    """Return one environment-derived receipt that either agrees or does not."""
    subject_identity = identity(f"{subject.value}-subject")
    return IndependentlyDerivedReceipt(
        receipt_id=f"{subject.value}-receipt",
        version="v1",
        subject=subject,
        subject_identity=subject_identity,
        observed_digest=subject_identity.digest if matched else fingerprint("observed-elsewhere"),
        derived_by=identity("environment-observer"),
        evidence=(evidence(f"{subject.value}-receipt-evidence"),),
    )


def result_of(scenario, outcomes, *, receipts=()) -> VerificationResult:
    return VerificationResult(
        result_id="candidate-run",
        version="v1",
        case=identity(scenario.case.case_id),
        candidate=CandidateIdentity("candidate", "v1", fingerprint("candidate")),
        context=scenario.case.context,
        independent_receipts=tuple(receipts),
        actual_outputs=(scenario.observation.output,),
        clause_outcomes=tuple(outcomes),
        status=VerificationStatus.FAIL,
        evidence=(evidence("run-evidence"),),
        diagnostic_strength=scenario.case.diagnostic_strength,
        repeat_run_identity=RepeatRunIdentity("repeat-run", "v1", fingerprint("repeat-run")),
    )


def evidence_for(scenario, *, receipts=(), comparisons=(), outcomes=None) -> FaultEvidence:
    """Return the evidence one packet is built from, for one reconciled scenario."""
    reconciled = scenario.reconcile()
    held = (reconciled.outcome,) if outcomes is None else tuple(outcomes)
    return FaultEvidence(
        case=scenario.case,
        result=result_of(scenario, held, receipts=receipts),
        output_id=OUTPUT_ID,
        findings=reconciled.findings,
        localisation=localise_output(
            scenario.case.lineage,
            OUTPUT_ID,
            outcomes=tuple(OutputOutcome(OUTPUT_ID, outcome) for outcome in held),
            comparisons=tuple(comparisons),
        ),
        checkpoint_comparisons=tuple(comparisons),
    )


# The class each declared defect shows when the receipts of the run were
# derived by the intake workflow itself. One entry per defect the shared
# comparison fixtures declare over the one supported route, so the receipt the
# intake writes and the comparison the classifier makes are held to one claim.
INTAKEN_CLASSES = {
    "duplicate-key": (fixture.duplicate_failure, FaultClass.DUPLICATE_JOIN_CARDINALITY),
    "missing-population": (fixture.population_failure, FaultClass.MISSING_POPULATION),
    "effective-time": (fixture.effective_time_failure, FaultClass.TEMPORAL_EFFECTIVE_DATE),
    "calculation": (fixture.calculation_failure, FaultClass.CALCULATION_PRECISION_ROUNDING),
    "aggregate": (fixture.aggregate_failure, FaultClass.UNKNOWN),
}


def intaken(case):
    """Return one case and the receipts the intake workflow really derived for it.

    The evidence digests are first set to the digests a repository can meet, so
    a fail-closed intake accepts the case; nothing else about the case moves.
    """
    prepared = intake_fixture.with_stored_evidence_digests(case)
    return prepared, intake_fixture.accepted(prepared).receipts


# --- One named fixture per declared fault class ---


def receipt_input_identity() -> FaultEvidence:
    return evidence_for(fixture.value_failure(), receipts=(receipt(ReceiptSubject.INPUT, matched=False),))


def receipt_reference_identity() -> FaultEvidence:
    return evidence_for(fixture.value_failure(), receipts=(receipt(ReceiptSubject.REFERENCE, matched=False),))


def receipt_context_drift() -> FaultEvidence:
    return evidence_for(fixture.value_failure(), receipts=(receipt(ReceiptSubject.CONTEXT, matched=False),))


def replay_context_drift() -> FaultEvidence:
    return evidence_for(fixture.replay_failure())


def replay_input_identity() -> FaultEvidence:
    return evidence_for(
        fixture.scenario(
            dimensions=fixture.ALL_DIMENSIONS,
            replay=True,
            observed_inputs=(Identity("input-dataset", "v1", fingerprint("a-different-input")),),
        )
    )


def replaying_case(**declarations):
    return fixture.scenario(
        dimensions=fixture.without(ComparisonDimension.AGGREGATE), replay=True, **declarations
    )


def state_replay() -> FaultEvidence:
    scenario = replaying_case(
        actual_rows=fixture.changed(fixture.BASE_ROWS, 0, **{"daily-value": Decimal("12.50")})
    )
    return evidence_for(
        scenario,
        comparisons=(
            CheckpointComparison(OUTPUT_ID, VerificationStatus.FAIL, (evidence("replayed-state"),)),
        ),
    )


def schema_coercion() -> FaultEvidence:
    return evidence_for(fixture.schema_failure())


def key_declaration_coercion() -> FaultEvidence:
    return evidence_for(fixture.key_failure())


def default_null() -> FaultEvidence:
    relaxed = replace(
        fixture.schema(),
        fields=tuple(
            replace(field, nullable=True) if field.field_id == "daily-value" else field
            for field in fixture.schema().fields
        ),
    )
    return evidence_for(
        fixture.scenario(
            dimensions=fixture.without(ComparisonDimension.AGGREGATE),
            actual_schema=relaxed,
            actual_rows=fixture.changed(fixture.BASE_ROWS, 0, **{"daily-value": Decimal("12.50")}),
        )
    )


def missing_population() -> FaultEvidence:
    return evidence_for(fixture.population_failure())


def additional_population() -> FaultEvidence:
    return evidence_for(fixture.population_additional_failure())


def filter_window_boundary() -> FaultEvidence:
    beyond = fixture.row(date(2026, 9, 3), "customer-a", date(2026, 9, 2), "50.00")
    return evidence_for(
        fixture.scenario(
            dimensions=fixture.without(ComparisonDimension.AGGREGATE),
            actual_rows=fixture.BASE_ROWS[:2] + (beyond,),
        )
    )


def duplicate_key_cardinality() -> FaultEvidence:
    return evidence_for(fixture.duplicate_failure())


def fanned_join_cardinality() -> FaultEvidence:
    return evidence_for(fixture.cardinality_failure())


def temporal_effective_date() -> FaultEvidence:
    return evidence_for(fixture.effective_time_failure())


def calculation_precision_rounding() -> FaultEvidence:
    return evidence_for(fixture.calculation_failure())


def nondeterministic_ordering() -> FaultEvidence:
    return evidence_for(fixture.ordering_failure())


def output_formatting() -> FaultEvidence:
    return evidence_for(fixture.format_failure())


def undecided_value() -> FaultEvidence:
    return evidence_for(fixture.value_failure())


def undecided_aggregate() -> FaultEvidence:
    return evidence_for(fixture.aggregate_failure())


def policy_ceiling() -> FaultEvidence:
    beyond = tuple(
        fixture.row(date(2026, 10, 1), f"customer-{index}", date(2026, 9, 30), "50.00")
        for index in range(51)
    )
    return evidence_for(
        fixture.scenario(
            dimensions=fixture.without(ComparisonDimension.AGGREGATE),
            actual_rows=fixture.BASE_ROWS + beyond,
        )
    )


FAULT_CLASSES = (
    ("input-identity-receipt", FaultClass.INPUT_IDENTITY, receipt_input_identity),
    ("input-identity-replay", FaultClass.INPUT_IDENTITY, replay_input_identity),
    ("reference-identity", FaultClass.REFERENCE_IDENTITY, receipt_reference_identity),
    ("runtime-configuration-drift-receipt", FaultClass.RUNTIME_CONFIGURATION_DRIFT, receipt_context_drift),
    ("runtime-configuration-drift-replay", FaultClass.RUNTIME_CONFIGURATION_DRIFT, replay_context_drift),
    ("state-replay", FaultClass.STATE_REPLAY, state_replay),
    ("schema-coercion", FaultClass.SCHEMA_COERCION, schema_coercion),
    ("schema-coercion-key-declaration", FaultClass.SCHEMA_COERCION, key_declaration_coercion),
    ("default-null", FaultClass.DEFAULT_NULL, default_null),
    ("missing-population", FaultClass.MISSING_POPULATION, missing_population),
    ("additional-population", FaultClass.ADDITIONAL_POPULATION, additional_population),
    ("filter-window-boundary", FaultClass.FILTER_WINDOW_BOUNDARY, filter_window_boundary),
    ("duplicate-join-cardinality-key", FaultClass.DUPLICATE_JOIN_CARDINALITY, duplicate_key_cardinality),
    ("duplicate-join-cardinality-fan-out", FaultClass.DUPLICATE_JOIN_CARDINALITY, fanned_join_cardinality),
    ("temporal-effective-date", FaultClass.TEMPORAL_EFFECTIVE_DATE, temporal_effective_date),
    ("calculation-precision-rounding", FaultClass.CALCULATION_PRECISION_ROUNDING, calculation_precision_rounding),
    ("nondeterministic-ordering", FaultClass.NONDETERMINISTIC_ORDERING, nondeterministic_ordering),
    ("output-formatting", FaultClass.OUTPUT_FORMATTING, output_formatting),
    ("unknown-value", FaultClass.UNKNOWN, undecided_value),
    ("unknown-aggregate", FaultClass.UNKNOWN, undecided_aggregate),
)


@pytest.mark.parametrize(
    ("declared", "build"),
    [(declared, build) for _, declared, build in FAULT_CLASSES],
    ids=[name for name, _, _ in FAULT_CLASSES],
)
def test_every_declared_fault_class_has_a_fixture_that_produces_it(declared, build):
    assert classify_fault(build()) is declared


def test_the_declared_fault_vocabulary_is_covered_by_the_named_fixtures():
    covered = {declared for _, declared, _ in FAULT_CLASSES}

    assert covered == set(FaultClass)


@pytest.mark.parametrize(
    ("declared", "build"),
    [(declared, build) for _, declared, build in FAULT_CLASSES],
    ids=[name for name, _, _ in FAULT_CLASSES],
)
def test_classification_reads_the_same_evidence_the_same_way_every_time(declared, build):
    assert classify_fault(build()) is classify_fault(build())


@pytest.mark.parametrize("declared", sorted(INTAKEN_CLASSES), ids=sorted(INTAKEN_CLASSES))
def test_receipts_the_intake_workflow_derived_leave_the_class_to_the_findings(declared):
    """The receipt a real intake writes agrees with itself, so no fault is an identity fault.

    The receipts here are not written by hand: the intake workflow derives them
    from the case the run was taken over, exactly as the one supported route
    does. An unaltered declaration therefore leaves the first classification
    rule undecided and the failing differences name the class.
    """
    build, expected = INTAKEN_CLASSES[declared]
    scenario = build()
    case, receipts = intaken(scenario.case)
    held = replace(evidence_for(scenario, receipts=receipts), case=case)

    assert [receipt.observed_digest for receipt in receipts] == [
        receipt.subject_identity.digest for receipt in receipts
    ]
    assert classify_fault(held) is not FaultClass.INPUT_IDENTITY
    assert classify_fault(held) is expected


def test_a_receipt_the_intake_workflow_took_over_an_altered_declaration_reports_the_identity():
    """Alter one frozen declaration and the receipt over it no longer answers for the case.

    Both digests come from real intakes: the identity from the intake of the
    case the run declares, the observation from the intake of the altered one.
    The first classification rule then reports the identity of that subject and
    nothing later overrides it.
    """
    scenario = fixture.calculation_failure()
    case, receipts = intaken(scenario.case)
    altered = next(
        dataset for dataset in case.frozen_datasets if dataset.role is DatasetRole.INPUT
    )
    _, observed = intaken(
        replace(
            case,
            frozen_datasets=tuple(
                replace(dataset, row_count=dataset.row_count + 1)
                if dataset.dataset_id == altered.dataset_id
                else dataset
                for dataset in case.frozen_datasets
            ),
        )
    )
    taken = {receipt.receipt_id: receipt.observed_digest for receipt in observed}
    crossed = tuple(
        replace(receipt, observed_digest=taken[receipt.receipt_id]) for receipt in receipts
    )
    held = replace(evidence_for(scenario, receipts=crossed), case=case)

    assert classify_fault(held) is FaultClass.INPUT_IDENTITY


def test_a_duplicate_key_run_builds_a_packet_the_gate_reads_in_full():
    """A side with no canonical bytes still reaches a packet the gate reads through.

    The reference for that side carries the digest of its closed reason record,
    so every digest slot of the packet holds an opaque fingerprint. The
    injected proof below writes the reason into that slot as a word instead,
    and the gate refuses it.
    """
    packet = build_fault_packet(evidence_for(fixture.duplicate_failure()))

    assert packet.fault_class is FaultClass.DUPLICATE_JOIN_CARDINALITY
    assert inspect_fault_packet(packet) is packet
    written = replace(
        packet,
        supporting_evidence=tuple(
            replace(reference, digest=f"{RECONCILIATION_FORM}:no-canonical-bytes")
            for reference in packet.supporting_evidence
        ),
    )
    with pytest.raises(PrivacyRefused) as raised:
        inspect_fault_packet(written)
    assert raised.value.reason is PrivacyRefusalReason.REVERSIBLE_DIGEST


def test_an_identity_receipt_that_agrees_leaves_the_class_to_the_findings():
    agreeing = evidence_for(
        fixture.population_failure(), receipts=(receipt(ReceiptSubject.INPUT, matched=True),)
    )

    assert classify_fault(agreeing) is FaultClass.MISSING_POPULATION


def test_what_the_run_read_is_decided_before_what_the_output_shows():
    findings_only = classify_fault(missing_population())
    with_receipt = evidence_for(
        fixture.population_failure(), receipts=(receipt(ReceiptSubject.INPUT, matched=False),)
    )

    assert findings_only is FaultClass.MISSING_POPULATION
    assert classify_fault(with_receipt) is FaultClass.INPUT_IDENTITY


def test_a_declared_replay_that_reproduces_the_state_leaves_the_class_undecided():
    reproduced = replaying_case(
        actual_rows=fixture.changed(fixture.BASE_ROWS, 0, **{"daily-value": Decimal("12.50")})
    )
    matched = evidence_for(
        reproduced,
        comparisons=(
            CheckpointComparison(OUTPUT_ID, VerificationStatus.PASS, (evidence("replayed-state"),)),
        ),
    )

    assert classify_fault(matched) is FaultClass.UNKNOWN


# --- Competing signals: the declared order is what decides ---


def failing_dimensions(material: FaultEvidence) -> set[ComparisonDimension]:
    """Return the dimensions this output's failing differences name."""
    return {
        finding.dimension
        for finding in material.findings
        if finding.output_id == OUTPUT_ID and finding.severity is FindingSeverity.FAILING
    }


def trimmed_schema_rows():
    trimmed = fixture.schema(drop=("record-state",))
    rows = tuple(
        {key: value for key, value in item.items() if key != "record-state"} for item in fixture.BASE_ROWS
    )
    return trimmed, rows


def schema_over_key() -> FaultEvidence:
    trimmed, rows = trimmed_schema_rows()
    return evidence_for(
        fixture.scenario(
            dimensions=fixture.without(
                ComparisonDimension.AGGREGATE, ComparisonDimension.JOIN_CARDINALITY
            ),
            actual_schema=trimmed,
            actual_rows=rows + (rows[0],),
        )
    )


def schema_over_population() -> FaultEvidence:
    trimmed, rows = trimmed_schema_rows()
    return evidence_for(
        fixture.scenario(
            dimensions=fixture.without(ComparisonDimension.AGGREGATE),
            actual_schema=trimmed,
            actual_rows=rows[:2],
        )
    )


def key_declaration_over_cardinality() -> FaultEvidence:
    """A grain that permits a repeated key against an observed grain that does not.

    The comparison grain permits repetition, so no repeated-key finding is
    reported; the observed output declares a different key policy, which is a
    key-declaration difference, and its repeated key is a fan-out the
    comparison grain does compare.
    """
    return evidence_for(
        fixture.scenario(
            dimensions=(ComparisonDimension.KEY, ComparisonDimension.JOIN_CARDINALITY),
            expected_grain=fixture.grain(duplicates=True),
            actual_grain=fixture.grain(duplicates=False),
            actual_rows=fixture.BASE_ROWS + (fixture.BASE_ROWS[0],),
        )
    )


def cardinality_over_population() -> FaultEvidence:
    return evidence_for(
        fixture.scenario(
            dimensions=fixture.without(ComparisonDimension.AGGREGATE, ComparisonDimension.ORDERING),
            expected_grain=fixture.grain(duplicates=True),
            actual_rows=fixture.BASE_ROWS[:2] + (fixture.BASE_ROWS[0],),
        )
    )


def population_over_effective_time() -> FaultEvidence:
    return evidence_for(
        fixture.scenario(
            dimensions=fixture.without(ComparisonDimension.AGGREGATE),
            actual_rows=fixture.changed(
                fixture.BASE_ROWS[:2], 0, **{"effective-from": date(2026, 8, 30)}
            ),
        )
    )


def effective_time_over_calculation() -> FaultEvidence:
    return evidence_for(
        fixture.scenario(
            tolerances=(fixture.EXACT_VALUE_TOLERANCE, fixture.AGGREGATE_TOLERANCE),
            actual_rows=fixture.changed(
                fixture.BASE_ROWS,
                0,
                **{"daily-value": Decimal("10.01"), "effective-from": date(2026, 8, 30)},
            ),
        )
    )


def calculation_over_ordering() -> FaultEvidence:
    return evidence_for(
        fixture.scenario(
            ordering_declaration=fixture.ordering(complete=False),
            tolerances=(fixture.EXACT_VALUE_TOLERANCE, fixture.AGGREGATE_TOLERANCE),
            actual_rows=fixture.changed(fixture.BASE_ROWS, 0, **{"daily-value": Decimal("10.01")}),
        )
    )


def ordering_over_output_format() -> FaultEvidence:
    return evidence_for(
        fixture.scenario(
            ordering_declaration=fixture.ordering(complete=False),
            actual_format_digest="blake2b-256:another-written-form",
        )
    )


def output_format_over_value() -> FaultEvidence:
    return evidence_for(
        fixture.scenario(
            dimensions=fixture.without(ComparisonDimension.AGGREGATE),
            actual_format_digest="blake2b-256:another-written-form",
            actual_rows=fixture.changed(fixture.BASE_ROWS, 0, **{"daily-value": Decimal("12.50")}),
        )
    )


def value_with_aggregate() -> FaultEvidence:
    return evidence_for(
        fixture.scenario(
            actual_rows=fixture.changed(fixture.BASE_ROWS, 0, **{"daily-value": Decimal("12.50")})
        )
    )


PRECEDENCE_PAIRS = (
    (
        "schema before key",
        schema_over_key,
        ComparisonDimension.SCHEMA,
        ComparisonDimension.KEY,
        FaultClass.SCHEMA_COERCION,
    ),
    (
        "schema before population",
        schema_over_population,
        ComparisonDimension.SCHEMA,
        ComparisonDimension.POPULATION,
        FaultClass.SCHEMA_COERCION,
    ),
    (
        "key before join cardinality",
        key_declaration_over_cardinality,
        ComparisonDimension.KEY,
        ComparisonDimension.JOIN_CARDINALITY,
        FaultClass.SCHEMA_COERCION,
    ),
    (
        "join cardinality before population",
        cardinality_over_population,
        ComparisonDimension.JOIN_CARDINALITY,
        ComparisonDimension.POPULATION,
        FaultClass.DUPLICATE_JOIN_CARDINALITY,
    ),
    (
        "population before effective time",
        population_over_effective_time,
        ComparisonDimension.POPULATION,
        ComparisonDimension.EFFECTIVE_TIME,
        FaultClass.MISSING_POPULATION,
    ),
    (
        "effective time before calculation",
        effective_time_over_calculation,
        ComparisonDimension.EFFECTIVE_TIME,
        ComparisonDimension.CALCULATION,
        FaultClass.TEMPORAL_EFFECTIVE_DATE,
    ),
    (
        "calculation before ordering",
        calculation_over_ordering,
        ComparisonDimension.CALCULATION,
        ComparisonDimension.ORDERING,
        FaultClass.CALCULATION_PRECISION_ROUNDING,
    ),
    (
        "ordering before output format",
        ordering_over_output_format,
        ComparisonDimension.ORDERING,
        ComparisonDimension.OUTPUT_FORMAT,
        FaultClass.NONDETERMINISTIC_ORDERING,
    ),
    (
        "output format before value",
        output_format_over_value,
        ComparisonDimension.OUTPUT_FORMAT,
        ComparisonDimension.VALUE,
        FaultClass.OUTPUT_FORMATTING,
    ),
)


@pytest.mark.parametrize(
    ("build", "earlier", "later", "declared"),
    [(build, earlier, later, declared) for _, build, earlier, later, declared in PRECEDENCE_PAIRS],
    ids=[name for name, _, _, _, _ in PRECEDENCE_PAIRS],
)
def test_the_earlier_dimension_decides_when_two_dimensions_compete(build, earlier, later, declared):
    material = build()

    assert {earlier, later} <= failing_dimensions(material)
    assert classify_fault(material) is declared


def test_the_declared_dimension_order_is_the_one_this_product_ships():
    assert DIMENSION_PRECEDENCE == (
        ComparisonDimension.SCHEMA,
        ComparisonDimension.KEY,
        ComparisonDimension.JOIN_CARDINALITY,
        ComparisonDimension.POPULATION,
        ComparisonDimension.EFFECTIVE_TIME,
        ComparisonDimension.CALCULATION,
        ComparisonDimension.ORDERING,
        ComparisonDimension.OUTPUT_FORMAT,
        ComparisonDimension.VALUE,
        ComparisonDimension.AGGREGATE,
    )


def test_a_repeated_key_and_a_fan_out_answer_with_one_class():
    """A repeated key and a fan-out name one class, so for that kind the order
    of the two neighbours changes no answer. The key dimension's other kind, a
    divergent key declaration, names a different class, and that edge is
    proved by the competing fixture above.
    """
    assert classify_fault(duplicate_key_cardinality()) is FaultClass.DUPLICATE_JOIN_CARDINALITY
    assert classify_fault(fanned_join_cardinality()) is FaultClass.DUPLICATE_JOIN_CARDINALITY


def test_the_two_undecided_dimensions_answer_undecided_whatever_their_order():
    """Neither of the last two neighbours names a class for any kind it can
    report, so both readings answer that the evidence does not decide.
    """
    material = value_with_aggregate()

    assert UNDECIDED_DIMENSIONS == (ComparisonDimension.VALUE, ComparisonDimension.AGGREGATE)
    assert {ComparisonDimension.VALUE, ComparisonDimension.AGGREGATE} <= failing_dimensions(material)
    assert classify_fault(material) is FaultClass.UNKNOWN


def replayed_missing_population():
    return replaying_case(actual_rows=fixture.BASE_ROWS[:2])


def confirmed_divergence():
    return (CheckpointComparison(OUTPUT_ID, VerificationStatus.FAIL, (evidence("replayed-state"),)),)


def identity_over_state() -> FaultEvidence:
    return evidence_for(
        replayed_missing_population(),
        receipts=(receipt(ReceiptSubject.INPUT, matched=False),),
        comparisons=confirmed_divergence(),
    )


def state_over_findings() -> FaultEvidence:
    return evidence_for(replayed_missing_population(), comparisons=confirmed_divergence())


def identity_over_findings() -> FaultEvidence:
    return evidence_for(
        fixture.population_failure(), receipts=(receipt(ReceiptSubject.INPUT, matched=False),)
    )


RULE_PAIRS = (
    ("what the run read before where the state diverged", identity_over_state, FaultClass.INPUT_IDENTITY),
    ("what the run read before what the output shows", identity_over_findings, FaultClass.INPUT_IDENTITY),
    ("where the state diverged before what the output shows", state_over_findings, FaultClass.STATE_REPLAY),
)


@pytest.mark.parametrize(
    ("build", "declared"),
    [(build, declared) for _, build, declared in RULE_PAIRS],
    ids=[name for name, _, _ in RULE_PAIRS],
)
def test_the_earlier_rule_decides_when_two_rules_compete(build, declared):
    assert classify_fault(build()) is declared


def test_every_competing_rule_would_have_decided_on_its_own():
    findings_only = evidence_for(replayed_missing_population())
    state_only = state_over_findings()

    assert classify_fault(findings_only) is FaultClass.MISSING_POPULATION
    assert classify_fault(state_only) is FaultClass.STATE_REPLAY
    assert failing_dimensions(identity_over_state()) == {ComparisonDimension.POPULATION}


# --- The declared disclosure thresholds ---


# The thresholds are written as the numbers the product ships, not as
# arithmetic on the constants, so moving a constant turns these red.
DISCLOSURE_THRESHOLDS = (
    ("no rows behind the differences", FaultClass.MISSING_POPULATION, 0, 1, DisclosureDecision.DISCLOSE),
    ("one row", FaultClass.MISSING_POPULATION, 1, 1, DisclosureDecision.WITHHOLD_SMALL_CELL),
    ("four rows", FaultClass.MISSING_POPULATION, 4, 1, DisclosureDecision.WITHHOLD_SMALL_CELL),
    ("five rows", FaultClass.MISSING_POPULATION, 5, 1, DisclosureDecision.DISCLOSE),
    ("six rows", FaultClass.MISSING_POPULATION, 6, 1, DisclosureDecision.DISCLOSE),
    ("fifty differences", FaultClass.MISSING_POPULATION, 5, 50, DisclosureDecision.DISCLOSE),
    ("fifty one differences", FaultClass.MISSING_POPULATION, 5, 51, DisclosureDecision.WITHHOLD_POLICY),
    ("an undecided class", FaultClass.UNKNOWN, 5, 1, DisclosureDecision.WITHHOLD_UNKNOWN),
)


def test_the_declared_policy_values_are_the_ones_this_product_ships():
    """Pin the policy itself, so a moved constant is a decision and not a drift."""
    assert SMALL_CELL_FLOOR == 5
    assert DISCLOSURE_CEILING == 50
    assert MAX_DISCLOSED_EXAMPLES == 8
    assert (MAX_EVIDENCE_REFERENCES, MAX_FRONTIER_CHECKPOINTS) == (16, 16)
    assert (MAX_UNCOVERED_PATHS, MAX_CHECKPOINTS_PER_PATH) == (16, 32)


@pytest.mark.parametrize(
    ("fault_class", "rows", "differences", "declared"),
    [(fault_class, rows, differences, declared) for _, fault_class, rows, differences, declared in DISCLOSURE_THRESHOLDS],
    ids=[name for name, _, _, _, _ in DISCLOSURE_THRESHOLDS],
)
def test_the_disclosure_policy_answers_at_every_declared_threshold(fault_class, rows, differences, declared):
    assert decide_disclosure(fault_class, distinct_rows=rows, distinct_differences=differences) is declared


def test_the_declared_disclosure_vocabulary_is_covered_by_the_declared_thresholds():
    covered = {declared for _, _, _, _, declared in DISCLOSURE_THRESHOLDS}

    assert covered == set(DisclosureDecision)


PACKET_DISCLOSURES = (
    ("a shape difference behind no row", schema_coercion, DisclosureDecision.DISCLOSE),
    ("a cohort below the declared floor", missing_population, DisclosureDecision.WITHHOLD_SMALL_CELL),
    ("more differences than the declared ceiling", policy_ceiling, DisclosureDecision.WITHHOLD_POLICY),
    ("a class the evidence does not decide", undecided_value, DisclosureDecision.WITHHOLD_UNKNOWN),
)


@pytest.mark.parametrize(
    ("build", "declared"),
    [(build, declared) for _, build, declared in PACKET_DISCLOSURES],
    ids=[name for name, _, _ in PACKET_DISCLOSURES],
)
def test_every_disclosure_decision_is_reached_by_a_built_packet(build, declared):
    assert build_fault_packet(build()).disclosure_decision is declared


# --- The packet itself ---


def test_the_packet_is_a_valid_domain_record_the_central_validator_accepts():
    packet = build_fault_packet(missing_population())

    assert inspect_verification_record(packet).issues == ()
    assert packet.version == FAULT_PACKET_FORM
    assert packet.fault_id == f"candidate-run/{OUTPUT_ID}"


def test_the_packet_carries_only_its_own_declared_summaries():
    packet = build_fault_packet(state_replay())
    carried = {
        reference.summary
        for reference in (
            *packet.supporting_evidence,
            *packet.contradicting_evidence,
            *packet.localisation.supporting_evidence,
            *(
                reference
                for frontier in (*packet.localisation.lower_frontier, *packet.localisation.upper_frontier)
                for reference in frontier.evidence
            ),
            *(reference for path in packet.localisation.uncovered_paths for reference in path.evidence),
        )
    }

    assert carried
    assert carried <= DECLARED_SUMMARIES


def test_the_packet_keeps_the_identity_and_digest_of_every_record_it_stands_for():
    material = state_replay()
    packet = build_fault_packet(material)
    declared = {
        (reference.evidence_id, reference.digest)
        for outcome in material.result.clause_outcomes
        for reference in outcome.observed_evidence
    }

    assert declared
    assert declared <= {(reference.evidence_id, reference.digest) for reference in packet.supporting_evidence}


def test_the_scope_states_names_and_counts_and_never_a_declared_value():
    packet = build_fault_packet(missing_population())

    assert packet.diagnostic_scope.startswith(f"output {OUTPUT_ID}; ")
    assert "differences 1" in packet.diagnostic_scope
    assert "rows 1" in packet.diagnostic_scope
    assert "customer-a" not in packet.diagnostic_scope


def test_evidence_for_and_against_come_from_failing_and_matching_comparisons():
    scenario = fixture.population_failure()
    reconciled = scenario.reconcile()
    matched = replace(
        reconciled.outcome,
        outcome_id="matched-clause",
        status=VerificationStatus.PASS,
        observed_evidence=(evidence("matched-observation"),),
    )
    packet = build_fault_packet(evidence_for(scenario, outcomes=(reconciled.outcome, matched)))

    assert packet.affected_clause_outcome_ids == (reconciled.outcome.outcome_id,)
    assert "matched-observation" in {reference.evidence_id for reference in packet.contradicting_evidence}
    assert "matched-observation" not in {reference.evidence_id for reference in packet.supporting_evidence}


def test_a_confirmed_later_boundary_names_the_surface_a_correction_would_touch():
    confirmed = state_replay()
    packet = build_fault_packet(confirmed)

    assert confirmed.localisation.status is LocalisationStatus.CONFIRMED
    assert packet.correction_surface is not None
    assert packet.correction_surface.identifier == "publish-daily-output"


def test_an_unbounded_localisation_names_no_correction_surface():
    packet = build_fault_packet(undecided_value())

    assert packet.localisation.status is LocalisationStatus.UNKNOWN
    assert packet.correction_surface is None


def many_outcome_evidence(count: int) -> FaultEvidence:
    """Return evidence whose run reports one output failing many times over."""
    scenario = fixture.population_failure()
    reconciled = scenario.reconcile()
    outcomes = tuple(
        replace(
            reconciled.outcome,
            outcome_id=f"failing-clause-{index:02d}",
            observed_evidence=(evidence(f"observed-{index:02d}"),),
        )
        for index in range(count)
    )
    return evidence_for(scenario, outcomes=outcomes)


def test_the_packet_carries_eight_examples_and_refuses_the_ninth():
    """Eight is the declared number of examples, written here as itself."""
    at_the_bound = build_fault_packet(many_outcome_evidence(8))
    beyond = build_fault_packet(many_outcome_evidence(9))
    carried = {reference.evidence_id for reference in beyond.supporting_evidence}

    assert len(at_the_bound.supporting_evidence) == 8
    assert len(beyond.supporting_evidence) == 8
    assert "observed-07" in carried
    assert "observed-08" not in carried
    assert len(beyond.affected_clause_outcome_ids) == 9
    assert "clauses 9 of 9" in beyond.diagnostic_scope


def test_a_localisation_larger_than_the_declared_shape_is_refused_at_build_time():
    material = missing_population()
    stretched = replace(
        material,
        localisation=replace(
            material.localisation,
            uncovered_paths=tuple(
                UncoveredPath(
                    path_id=f"open-path-{index:02d}",
                    checkpoint_ids=(f"checkpoint-{index:02d}",),
                    reason=UncoveredPathReason.OUTPUT_ONLY,
                    evidence=(evidence(f"open-path-{index:02d}-evidence"),),
                )
                for index in range(MAX_UNCOVERED_PATHS + 1)
            ),
        ),
    )

    with pytest.raises(FaultRefused) as refusal:
        build_fault_packet(stretched)

    assert refusal.value.reason is FaultRefusalReason.DECLARED_BOUND_EXCEEDED


def test_the_packet_reads_the_same_evidence_the_same_way_every_time():
    assert build_fault_packet(missing_population()) == build_fault_packet(missing_population())


def test_the_packet_fields_offered_onward_are_declared_names_counts_and_fingerprints():
    packet = build_fault_packet(schema_coercion())
    fields = packet_fields(packet)

    assert fields["fault_class"] == FaultClass.SCHEMA_COERCION.value
    assert fields["disclosure_decision"] == DisclosureDecision.DISCLOSE.value
    assert fields["result_digest"] == packet.result.digest
    assert set(fields) == {
        "fault_id",
        "packet_form",
        "result_identity",
        "result_digest",
        "fault_class",
        "disclosure_decision",
        "diagnostic_scope",
        "localisation_status",
        "supporting_evidence_count",
        "contradicting_evidence_count",
    }


def test_one_packet_is_built_for_every_localised_output():
    scenario = fixture.population_failure()
    reconciled = scenario.reconcile()
    result = result_of(scenario, (reconciled.outcome,))
    packets = build_fault_packets(
        scenario.case,
        result,
        findings=reconciled.findings,
        localisations=localise(
            scenario.case.lineage,
            outcomes=(OutputOutcome(OUTPUT_ID, reconciled.outcome),),
            comparisons=(),
        ),
    )

    assert tuple(packet.fault_id for packet in packets) == (f"candidate-run/{OUTPUT_ID}",)


# --- Confidence is declared, never withheld ---


CONFIDENCE_CASES = (
    ("a confirmed boundary", state_replay, AdviserConfidence.HIGH),
    ("an undecided class", undecided_value, AdviserConfidence.UNKNOWN),
    ("a decided class with no declared lineage", missing_population, AdviserConfidence.UNKNOWN),
)


@pytest.mark.parametrize(
    ("build", "declared"),
    [(build, declared) for _, build, declared in CONFIDENCE_CASES],
    ids=[name for name, _, _ in CONFIDENCE_CASES],
)
def test_confidence_follows_how_far_the_lineage_narrowed_the_fault(build, declared):
    assert declare_confidence(build()) is declared


def test_an_interval_with_a_path_it_could_not_separate_lowers_confidence_without_withholding():
    open_path = evidence_for(
        replaying_case(actual_rows=fixture.BASE_ROWS[:2]),
        comparisons=(),
    )
    packet = build_fault_packet(open_path)

    assert open_path.localisation.status is LocalisationStatus.INFERRED
    assert open_path.localisation.uncovered_paths
    assert declare_confidence(open_path) is AdviserConfidence.LOW
    assert packet.fault_class is FaultClass.MISSING_POPULATION


def test_declared_provenance_changes_no_class_no_decision_and_no_confidence():
    def built(provenance):
        return evidence_for(
            fixture.scenario(
                dimensions=fixture.without(ComparisonDimension.AGGREGATE),
                actual_rows=fixture.BASE_ROWS[:2],
                provenance=provenance,
            )
        )

    real = built(DatasetProvenance.REAL)
    synthetic = built(DatasetProvenance.SYNTHETIC)

    assert classify_fault(real) is classify_fault(synthetic)
    assert declare_confidence(real) is declare_confidence(synthetic)
    assert build_fault_packet(real).disclosure_decision is build_fault_packet(synthetic).disclosure_decision


# --- Integrity refusals ---


def test_a_packet_is_refused_for_an_output_the_case_does_not_declare():
    material = replace(missing_population(), output_id="another-output")

    with pytest.raises(FaultRefused) as refusal:
        build_fault_packet(material)

    assert refusal.value.reason is FaultRefusalReason.UNRESOLVED_OUTPUT


def test_a_packet_is_refused_for_a_comparison_of_an_undeclared_checkpoint():
    material = replace(
        state_replay(),
        checkpoint_comparisons=(
            CheckpointComparison("undeclared-checkpoint", VerificationStatus.FAIL, (evidence("elsewhere"),)),
        ),
    )

    with pytest.raises(FaultRefused) as refusal:
        build_fault_packet(material)

    assert refusal.value.reason is FaultRefusalReason.UNRESOLVED_CHECKPOINT


def test_a_packet_is_refused_when_two_comparisons_of_one_checkpoint_disagree():
    material = replace(
        state_replay(),
        checkpoint_comparisons=(
            CheckpointComparison(OUTPUT_ID, VerificationStatus.FAIL, (evidence("replayed-state"),)),
            CheckpointComparison(OUTPUT_ID, VerificationStatus.PASS, (evidence("replayed-state"),)),
        ),
    )

    with pytest.raises(FaultRefused) as refusal:
        build_fault_packet(material)

    assert refusal.value.reason is FaultRefusalReason.CONTRADICTORY_COMPARISON


def test_a_packet_is_refused_for_an_output_the_run_reports_as_matching():
    scenario = fixture.population_failure()
    reconciled = scenario.reconcile()
    matched = replace(reconciled.outcome, status=VerificationStatus.PASS)
    material = FaultEvidence(
        case=scenario.case,
        result=result_of(scenario, (matched,)),
        output_id=OUTPUT_ID,
        findings=reconciled.findings,
        localisation=localise_output(
            scenario.case.lineage,
            OUTPUT_ID,
            outcomes=(OutputOutcome(OUTPUT_ID, reconciled.outcome),),
            comparisons=(),
        ),
    )

    with pytest.raises(FaultRefused) as refusal:
        build_fault_packet(material)

    assert refusal.value.reason is FaultRefusalReason.NOT_A_FAILED_OUTPUT
