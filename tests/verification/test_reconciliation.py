"""Deterministic reconciliation: every comparison class, every finding, every refusal."""
# evorthon-verifies: EVD-README-042
# evorthon-verifies: EVD-README-026
# evorthon-verifies: EVD-README-017
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

import pytest

from evorthon_data.verification.core.canonical import (
    DIGEST_PREFIX,
    CanonicalisationRefusal,
    RefusalReason,
    canonical_digest,
    dataset_digest,
    record_digest,
)
from evorthon_data.verification.core.reconciliation import (
    EFFECTIVE_TIME_ROLE,
    FINDING_DIMENSION,
    IMPLEMENTED_DIMENSIONS,
    RULE_DERIVED_ORIGIN,
    RULE_DERIVED_PROVENANCE,
    UNCANONICAL_REASON_FORM,
    UNCANONICAL_SUMMARY,
    CandidateObservation,
    ExpectedMaterial,
    FindingKind,
    FindingSeverity,
    ReconciliationRefusalReason,
    ReconciliationRefused,
    RuleDerivation,
    UncanonicalReason,
    derive_expected_output,
    parity_clauses,
    reconcile_case,
    reconcile_clause,
)
from evorthon_data.verification.domain.contracts import (
    ActualOutput,
    AggregateControl,
    AssuranceDeclaration,
    AssuranceLevel,
    CanonicalisationDeclaration,
    Checkpoint,
    ClauseFamily,
    ComparisonDeclaration,
    ComparisonDimension,
    ComparisonPolicy,
    ContextIdentity,
    DatasetProvenance,
    DatasetRole,
    DiagnosticStrength,
    EvidenceReference,
    ExclusionDeclaration,
    ExpectedOutput,
    ExpectedOutputOrigin,
    FrozenDataset,
    GrainDeclaration,
    Identity,
    LineageDefinition,
    NullPlacement,
    OrderingDeclaration,
    OrderingField,
    OutputLineageBinding,
    ParityClause,
    ReplayInput,
    ReplaySpecification,
    RuleConstraint,
    RuleDeclaration,
    RuleOperator,
    SchemaDeclaration,
    SchemaField,
    SchemaValueType,
    SortDirection,
    SyntheticProvenance,
    ToleranceDeclaration,
    VerificationCase,
    VerificationMode,
    VerificationStatus,
    WarningBandDeclaration,
)
from evorthon_data.verification.enforcement.validation import inspect_verification_case

OUTPUT_ID = "daily-output"
CLAUSE_ID = "parity"
CONTEXT = ContextIdentity("context", "v1", "sha256:context", "2026-09-02T09:00:00Z", "09:00", "UTC")
OTHER_CONTEXT = replace(CONTEXT, context_id="other-context", digest="sha256:other-context")
CANONICALISATION = CanonicalisationDeclaration(
    "canonical-json-v1", "v1", "NFC", "json-null", 2, "milliseconds", "UTC", "positive-zero", "reject"
)
ALL_DIMENSIONS = tuple(ComparisonDimension)
DEFAULT_DIMENSIONS = tuple(
    dimension for dimension in ALL_DIMENSIONS if dimension is not ComparisonDimension.REPLAY_METADATA
)


def identity(name: str) -> Identity:
    return Identity(identifier=name, version="v1", digest=f"sha256:{name}")


def evidence(name: str) -> EvidenceReference:
    return EvidenceReference(name, "v1", f"sha256:{name}", f"approved {name}")


def schema(*, format_name: str = "csv-rfc4180", drop: tuple[str, ...] = (), effective_role: str = EFFECTIVE_TIME_ROLE):
    fields = (
        SchemaField("business-date", SchemaValueType.DATE, False, "partition-date", None, None),
        SchemaField("customer-id", SchemaValueType.STRING, False, "business-key", None, None),
        SchemaField("effective-from", SchemaValueType.DATE, False, effective_role, None, None),
        SchemaField("daily-value", SchemaValueType.DECIMAL, False, "measure", 18, 2),
        SchemaField("record-state", SchemaValueType.STRING, False, "publication-state", None, None),
    )
    return SchemaDeclaration(
        schema_id="daily-output-schema",
        version="v1",
        fields=tuple(field for field in fields if field.field_id not in drop),
        format_name=format_name,
    )


def grain(*, key_fields: tuple[str, ...] = ("business-date", "customer-id"), duplicates: bool = False):
    return GrainDeclaration(
        grain_id="customer-day",
        version="v1",
        key_fields=key_fields,
        population_description="one approved customer-day population",
        duplicate_keys_permitted=duplicates,
    )


def ordering(*, complete: bool = True) -> OrderingDeclaration:
    fields = (OrderingField("business-date", SortDirection.ASCENDING, NullPlacement.LAST),)
    if complete:
        fields = fields + (OrderingField("customer-id", SortDirection.ASCENDING, NullPlacement.LAST),)
    return OrderingDeclaration("daily-output-order", "v1", fields, ())


def aggregate_control(*, operation: str = "sum", null_handling: str = "exclude-null", rounding: str = "half-even"):
    return AggregateControl(
        "daily-total", "v1", operation, "daily-value", "daily-value-total", ("business-date",), null_handling, rounding
    )


def row(business_date: date, customer: str, effective: date, value: str, state: str = "published"):
    return {
        "business-date": business_date,
        "customer-id": customer,
        "effective-from": effective,
        "daily-value": Decimal(value),
        "record-state": state,
    }


BASE_ROWS = (
    row(date(2026, 9, 1), "customer-a", date(2026, 8, 31), "10.00"),
    row(date(2026, 9, 1), "customer-b", date(2026, 8, 31), "20.00"),
    row(date(2026, 9, 2), "customer-a", date(2026, 9, 1), "30.00"),
)
SUPPRESSED_ROW = row(date(2026, 9, 2), "customer-b", date(2026, 9, 1), "40.00", "suppressed")
INPUT_ROWS = BASE_ROWS + (SUPPRESSED_ROW,)
FORMAT_DIGEST = record_digest(schema())
# A schema of whole numbers, with a canonicalisation that declares no decimal
# scale because no field needs one.
COUNTED_CANONICALISATION = replace(CANONICALISATION, canonicalisation_id="canonical-json-counts", decimal_scale=None)


def counted_schema() -> SchemaDeclaration:
    return SchemaDeclaration(
        schema_id="daily-count-schema",
        version="v1",
        fields=(
            SchemaField("business-date", SchemaValueType.DATE, False, "partition-date", None, None),
            SchemaField("customer-id", SchemaValueType.STRING, False, "business-key", None, None),
            SchemaField("effective-from", SchemaValueType.DATE, False, EFFECTIVE_TIME_ROLE, None, None),
            SchemaField("daily-count", SchemaValueType.INTEGER, False, "measure", None, None),
            SchemaField("record-state", SchemaValueType.STRING, False, "publication-state", None, None),
        ),
        format_name="csv-rfc4180",
    )


COUNTED_ROWS = tuple(
    {
        "business-date": item["business-date"],
        "customer-id": item["customer-id"],
        "effective-from": item["effective-from"],
        "daily-count": int(item["daily-value"]),
        "record-state": item["record-state"],
    }
    for item in BASE_ROWS
)
VALUE_TOLERANCE = ToleranceDeclaration(
    "daily-value-tolerance",
    "v1",
    (CLAUSE_ID,),
    (ComparisonDimension.VALUE, ComparisonDimension.CALCULATION),
    ("daily-value",),
    "absolute-difference",
    "0.00",
    "0.05",
    "currency-units",
    "half-even",
)
AGGREGATE_TOLERANCE = ToleranceDeclaration(
    "daily-total-tolerance",
    "v1",
    (CLAUSE_ID,),
    (ComparisonDimension.AGGREGATE,),
    ("daily-value-total",),
    "absolute-difference",
    "0.00",
    "0.05",
    "currency-units",
    "half-even",
)
WARNING_BAND = WarningBandDeclaration(
    "daily-value-warning",
    "v1",
    (CLAUSE_ID,),
    (ComparisonDimension.VALUE,),
    ("daily-value",),
    "absolute-difference",
    "0.01",
    "0.05",
    "currency-units",
)
SUPPRESSED_EXCLUSION = ExclusionDeclaration(
    "suppressed-record-exclusion",
    "v1",
    (CLAUSE_ID,),
    (ComparisonDimension.POPULATION,),
    (RuleConstraint("record-state", RuleOperator.EQUALS, "suppressed"),),
    "approved suppressed records do not form part of the published population",
)
EXACT_VALUE_TOLERANCE = replace(VALUE_TOLERANCE, upper_bound="0.00")


def frozen_input(provenance: DatasetProvenance = DatasetProvenance.REAL, rows=INPUT_ROWS) -> FrozenDataset:
    return FrozenDataset(
        dataset_id="input-dataset",
        version="v1",
        role=DatasetRole.INPUT,
        provenance=provenance,
        synthetic_provenance=(
            SyntheticProvenance("declared-schema-generator", "v1", "seed:input", "sha256:constraints", ())
            if provenance is DatasetProvenance.SYNTHETIC
            else None
        ),
        content_digest=dataset_digest(
            rows, schema=schema(), grain=grain(), canonicalisation=CANONICALISATION, ordering=None
        ),
        schema=schema(),
        grain=grain(),
        canonicalisation=CANONICALISATION,
        row_count=len(rows),
        approved_summary="approved frozen input",
    )


def expected_output(
    rows,
    *,
    schema_declaration=None,
    grain_declaration=None,
    ordering_declaration=None,
    canonicalisation=CANONICALISATION,
    provenance: DatasetProvenance = DatasetProvenance.REAL,
    origin=ExpectedOutputOrigin.MODERNISATION_CAPTURE,
) -> ExpectedOutput:
    schema_declaration = schema_declaration or schema()
    grain_declaration = grain_declaration or grain()
    return ExpectedOutput(
        output_id=OUTPUT_ID,
        version="v1",
        origin=origin,
        provenance=provenance,
        content_digest=dataset_digest(
            rows,
            schema=schema_declaration,
            grain=grain_declaration,
            canonicalisation=canonicalisation,
            ordering=ordering_declaration,
        ),
        schema=schema_declaration,
        grain=grain_declaration,
        canonicalisation=canonicalisation,
        row_count=len(rows),
        format_digest=FORMAT_DIGEST,
        approved_summary="approved expected daily output",
    )


def actual_output(
    rows,
    *,
    schema_declaration=None,
    grain_declaration=None,
    canonicalisation=CANONICALISATION,
    ordering_declaration=None,
    format_digest: str | None = None,
    content_digest: str | None = None,
    row_count: int | None = None,
) -> ActualOutput:
    schema_declaration = schema_declaration or schema()
    grain_declaration = grain_declaration or grain()
    if content_digest is None:
        try:
            content_digest = dataset_digest(
                rows,
                schema=schema_declaration,
                grain=grain_declaration,
                canonicalisation=canonicalisation,
                ordering=ordering_declaration,
            )
        except CanonicalisationRefusal as refusal:
            # A candidate that repeats a key its own grain forbids produces no
            # canonical bytes. The declared digest is then the one its rows
            # would produce if repetition were permitted.
            assert refusal.reason is RefusalReason.DUPLICATE_KEY_NOT_PERMITTED
            content_digest = dataset_digest(
                rows,
                schema=schema_declaration,
                grain=replace(grain_declaration, duplicate_keys_permitted=True),
                canonicalisation=canonicalisation,
                ordering=ordering_declaration,
            )
    return ActualOutput(
        output_id=OUTPUT_ID,
        version="v1",
        content_digest=content_digest,
        schema=schema_declaration,
        grain=grain_declaration,
        canonicalisation=canonicalisation,
        row_count=len(rows) if row_count is None else row_count,
        format_digest=FORMAT_DIGEST if format_digest is None else format_digest,
        approved_summary="observed daily output",
    )


@dataclass(frozen=True)
class Scenario:
    """One complete comparison: an approved case, its oracle and one observation."""

    case: VerificationCase
    expected: ExpectedMaterial
    observation: CandidateObservation

    def reconcile(self):
        return reconcile_clause(self.case, parity_clauses(self.case)[0], self.expected, self.observation)

    def failing(self) -> set[FindingKind]:
        return {
            finding.kind
            for finding in self.reconcile().findings
            if finding.severity is FindingSeverity.FAILING
        }

    def warnings(self) -> set[FindingKind]:
        return {
            finding.kind
            for finding in self.reconcile().findings
            if finding.severity is FindingSeverity.WARNING
        }


def scenario(
    *,
    dimensions=DEFAULT_DIMENSIONS,
    expected_rows=BASE_ROWS,
    actual_rows=None,
    expected_schema=None,
    expected_grain=None,
    actual_schema=None,
    actual_grain=None,
    canonicalisation=CANONICALISATION,
    actual_canonicalisation=None,
    actual_format_digest=None,
    actual_content_digest=None,
    actual_row_count=None,
    ordering_declaration=None,
    aggregates=None,
    tolerances=None,
    warning_bands=(WARNING_BAND,),
    exclusions=(),
    replay: bool = False,
    observed_context=None,
    observed_inputs=None,
    provenance: DatasetProvenance = DatasetProvenance.REAL,
    expected_origin=ExpectedOutputOrigin.MODERNISATION_CAPTURE,
) -> Scenario:
    """Build one reconciliation scenario from the declarations it needs.

    Policy declarations the comparison does not declare are dropped, so every
    scenario is a case the central validator accepts.
    """
    expected_schema = expected_schema or schema()
    expected_grain = expected_grain or grain()
    actual_canonicalisation = canonicalisation if actual_canonicalisation is None else actual_canonicalisation
    ordering_declaration = ordering() if ordering_declaration is None else ordering_declaration
    aggregates = (aggregate_control(),) if aggregates is None else aggregates
    tolerances = (VALUE_TOLERANCE, AGGREGATE_TOLERANCE) if tolerances is None else tolerances
    actual_rows = expected_rows if actual_rows is None else actual_rows
    declared = set(dimensions)
    tolerances = tuple(
        tolerance
        for tolerance in tolerances
        if set(tolerance.dimensions) <= declared
        and (ComparisonDimension.AGGREGATE not in tolerance.dimensions or aggregates)
    )
    warning_bands = tuple(band for band in warning_bands if set(band.dimensions) <= declared)
    exclusions = tuple(exclusion for exclusion in exclusions if set(exclusion.dimensions) <= declared)
    output = expected_output(
        expected_rows,
        schema_declaration=expected_schema,
        grain_declaration=expected_grain,
        ordering_declaration=ordering_declaration,
        canonicalisation=canonicalisation,
        provenance=provenance,
        origin=expected_origin,
    )
    replay_specification = (
        ReplaySpecification(
            "replay",
            "v1",
            OUTPUT_ID,
            (ReplayInput("input-dataset", DatasetRole.INPUT, True),),
            CONTEXT,
            identity("publish-daily-output"),
            expected_schema,
            expected_grain,
            canonicalisation,
        )
        if replay
        else None
    )
    checkpoints = (
        (
            Checkpoint(
                checkpoint_id=OUTPUT_ID,
                version="v1",
                parent_ids=(),
                expected_state=identity("daily-output-expected"),
                schema=expected_schema,
                grain=expected_grain,
                canonicalisation=canonicalisation,
                transformation=identity("publish-daily-output"),
                provenance=identity("candidate-source"),
                diagnostic_evidence=(evidence("checkpoint-evidence"),),
                replay=replay_specification,
            ),
        )
        if replay
        else ()
    )
    clause = ParityClause(
        CLAUSE_ID,
        "v1",
        OUTPUT_ID,
        ComparisonDeclaration(
            comparison_id="daily-output-comparison",
            version="v1",
            dimensions=tuple(dimensions),
            schema=expected_schema,
            grain=expected_grain,
            canonicalisation=canonicalisation,
            aggregates=tuple(aggregates),
            ordering=ordering_declaration,
            replay=replay_specification,
        ),
        (evidence("parity-evidence"),),
    )
    case = VerificationCase(
        case_id="reconciliation-case",
        version="v1",
        mode=VerificationMode.MODERNISATION,
        frozen_datasets=(frozen_input(provenance),),
        expected_outputs=(output,),
        context=CONTEXT,
        comparison_policy=ComparisonPolicy(
            "comparison-policy", "v1", "sha256:policy", (clause,), tolerances, exclusions, warning_bands
        ),
        lineage=LineageDefinition(
            "lineage",
            "v1",
            checkpoints,
            (OutputLineageBinding(OUTPUT_ID, OUTPUT_ID if replay else None),),
        ),
        assurance=AssuranceDeclaration("assurance", "v1", AssuranceLevel.DECLARED, (), ()),
        diagnostic_strength=DiagnosticStrength.REPLAYABLE if replay else DiagnosticStrength.OUTPUT_ONLY,
    )
    observation = CandidateObservation(
        output=actual_output(
            actual_rows,
            schema_declaration=actual_schema or expected_schema,
            grain_declaration=actual_grain or expected_grain,
            canonicalisation=actual_canonicalisation,
            ordering_declaration=ordering_declaration,
            format_digest=actual_format_digest,
            content_digest=actual_content_digest,
            row_count=actual_row_count,
        ),
        rows=tuple(actual_rows),
        context=CONTEXT if observed_context is None else observed_context,
        observed_inputs=(
            (Identity("input-dataset", "v1", frozen_input(provenance).content_digest),)
            if observed_inputs is None
            else observed_inputs
        ),
    )
    return Scenario(case, ExpectedMaterial(output, tuple(expected_rows)), observation)


def without(*dimensions) -> tuple[ComparisonDimension, ...]:
    dropped = set(dimensions)
    return tuple(dimension for dimension in DEFAULT_DIMENSIONS if dimension not in dropped)


def changed(rows, index: int, **fields):
    """Return the rows with one row's declared fields changed."""
    material = [dict(item) for item in rows]
    material[index].update(fields)
    return tuple(material)


# --- One named pass fixture and one named failure fixture per comparison class ---


def schema_pass() -> Scenario:
    return scenario()


def schema_failure() -> Scenario:
    trimmed = schema(drop=("record-state",))
    rows = tuple({key: value for key, value in item.items() if key != "record-state"} for item in BASE_ROWS)
    return scenario(actual_schema=trimmed, actual_rows=rows)


def schema_additional_failure() -> Scenario:
    widened = replace(
        schema(),
        fields=schema().fields + (SchemaField("settlement-state", SchemaValueType.STRING, False, "extra", None, None),),
    )
    rows = tuple({**item, "settlement-state": "settled"} for item in BASE_ROWS)
    return scenario(actual_schema=widened, actual_rows=rows)


def schema_type_failure() -> Scenario:
    relaxed = replace(
        schema(),
        fields=tuple(
            replace(field, nullable=True) if field.field_id == "daily-value" else field for field in schema().fields
        ),
    )
    return scenario(actual_schema=relaxed)


def population_pass() -> Scenario:
    return scenario()


def population_additional_failure() -> Scenario:
    extra = row(date(2026, 9, 3), "customer-a", date(2026, 9, 2), "50.00")
    return scenario(dimensions=without(ComparisonDimension.AGGREGATE), actual_rows=BASE_ROWS + (extra,))


def population_failure() -> Scenario:
    return scenario(dimensions=without(ComparisonDimension.AGGREGATE), actual_rows=BASE_ROWS[:2])


def key_pass() -> Scenario:
    return scenario()


def key_failure() -> Scenario:
    return scenario(actual_grain=grain(key_fields=("business-date", "customer-id", "record-state")))


def duplicate_failure() -> Scenario:
    return scenario(
        dimensions=without(ComparisonDimension.AGGREGATE, ComparisonDimension.JOIN_CARDINALITY),
        actual_rows=BASE_ROWS + (BASE_ROWS[0],),
    )


def value_pass() -> Scenario:
    return scenario(actual_rows=BASE_ROWS)


def value_failure() -> Scenario:
    return scenario(
        dimensions=without(ComparisonDimension.AGGREGATE),
        actual_rows=changed(BASE_ROWS, 0, **{"daily-value": Decimal("12.50")}),
    )


def calculation_pass() -> Scenario:
    return scenario(tolerances=(EXACT_VALUE_TOLERANCE, AGGREGATE_TOLERANCE))


def calculation_failure() -> Scenario:
    return scenario(
        tolerances=(EXACT_VALUE_TOLERANCE, AGGREGATE_TOLERANCE),
        actual_rows=changed(BASE_ROWS, 0, **{"daily-value": Decimal("10.01")}),
    )


def cardinality_pass() -> Scenario:
    return scenario(expected_grain=grain(duplicates=True))


def cardinality_failure() -> Scenario:
    return scenario(
        dimensions=without(ComparisonDimension.AGGREGATE, ComparisonDimension.ORDERING),
        expected_grain=grain(duplicates=True),
        actual_rows=BASE_ROWS + (changed(BASE_ROWS, 0, **{"daily-value": Decimal("11.00")})[0],),
    )


def one_to_one_cardinality_pass() -> Scenario:
    return scenario(expected_grain=grain(duplicates=False))


def one_to_one_cardinality_failure() -> Scenario:
    return scenario(
        dimensions=without(ComparisonDimension.AGGREGATE, ComparisonDimension.KEY),
        expected_grain=grain(duplicates=False),
        actual_rows=BASE_ROWS + (BASE_ROWS[0],),
    )


def calculation_without_declared_scale_refusal() -> Scenario:
    return scenario(
        dimensions=without(ComparisonDimension.AGGREGATE),
        canonicalisation=COUNTED_CANONICALISATION,
        expected_schema=counted_schema(),
        expected_rows=COUNTED_ROWS,
        aggregates=(),
        tolerances=(),
        warning_bands=(),
    )


def effective_time_pass() -> Scenario:
    return scenario()


def effective_time_failure() -> Scenario:
    return scenario(actual_rows=changed(BASE_ROWS, 0, **{"effective-from": date(2026, 8, 30)}))


def aggregate_pass() -> Scenario:
    return scenario()


def aggregate_failure() -> Scenario:
    rows = changed(BASE_ROWS, 0, **{"daily-value": Decimal("10.03")})
    rows = changed(rows, 1, **{"daily-value": Decimal("20.03")})
    return scenario(actual_rows=rows)


def ordering_pass() -> Scenario:
    return scenario(ordering_declaration=ordering(complete=True))


def ordering_failure() -> Scenario:
    return scenario(ordering_declaration=ordering(complete=False))


def format_pass() -> Scenario:
    return scenario()


def format_failure() -> Scenario:
    return scenario(actual_format_digest="blake2b-256:another-written-form")


def replay_pass() -> Scenario:
    return scenario(dimensions=ALL_DIMENSIONS, replay=True)


def replay_failure() -> Scenario:
    return scenario(dimensions=ALL_DIMENSIONS, replay=True, observed_context=OTHER_CONTEXT)


def warning_band_pass() -> Scenario:
    return scenario(
        dimensions=without(ComparisonDimension.AGGREGATE),
        actual_rows=changed(BASE_ROWS, 0, **{"daily-value": Decimal("10.03")}),
    )


def warning_band_absent() -> Scenario:
    return scenario(dimensions=without(ComparisonDimension.AGGREGATE))


def exclusion_pass() -> Scenario:
    return scenario(
        dimensions=without(ComparisonDimension.AGGREGATE),
        expected_rows=BASE_ROWS + (SUPPRESSED_ROW,),
        actual_rows=BASE_ROWS,
        exclusions=(SUPPRESSED_EXCLUSION,),
    )


def exclusion_absent() -> Scenario:
    return scenario(
        dimensions=without(ComparisonDimension.AGGREGATE),
        expected_rows=BASE_ROWS + (SUPPRESSED_ROW,),
        actual_rows=BASE_ROWS,
    )


COMPARISON_CLASSES = (
    ("schema", ComparisonDimension.SCHEMA, schema_pass, schema_failure, FindingKind.SCHEMA_FIELD_MISSING),
    ("population", ComparisonDimension.POPULATION, population_pass, population_failure, FindingKind.POPULATION_ROW_MISSING),
    ("keys", ComparisonDimension.KEY, key_pass, key_failure, FindingKind.KEY_DECLARATION_DIVERGENCE),
    ("keys-duplicate", ComparisonDimension.KEY, key_pass, duplicate_failure, FindingKind.KEY_DUPLICATE),
    ("values", ComparisonDimension.VALUE, value_pass, value_failure, FindingKind.VALUE_DIVERGENCE),
    ("calculation", ComparisonDimension.CALCULATION, calculation_pass, calculation_failure, FindingKind.ROUNDING_DIVERGENCE),
    (
        "joins-and-cardinality",
        ComparisonDimension.JOIN_CARDINALITY,
        cardinality_pass,
        cardinality_failure,
        FindingKind.CARDINALITY_DIVERGENCE,
    ),
    (
        "joins-and-cardinality-one-to-one",
        ComparisonDimension.JOIN_CARDINALITY,
        one_to_one_cardinality_pass,
        one_to_one_cardinality_failure,
        FindingKind.CARDINALITY_DIVERGENCE,
    ),
    (
        "effective-time",
        ComparisonDimension.EFFECTIVE_TIME,
        effective_time_pass,
        effective_time_failure,
        FindingKind.EFFECTIVE_TIME_DIVERGENCE,
    ),
    ("aggregates", ComparisonDimension.AGGREGATE, aggregate_pass, aggregate_failure, FindingKind.AGGREGATE_DIVERGENCE),
    ("ordering", ComparisonDimension.ORDERING, ordering_pass, ordering_failure, FindingKind.ORDERING_NONDETERMINISTIC),
    ("formatting", ComparisonDimension.OUTPUT_FORMAT, format_pass, format_failure, FindingKind.FORMAT_DIVERGENCE),
    (
        "replay-metadata",
        ComparisonDimension.REPLAY_METADATA,
        replay_pass,
        replay_failure,
        FindingKind.REPLAY_METADATA_DIVERGENCE,
    ),
)
FINDING_PROOFS = (
    (FindingKind.SCHEMA_FIELD_MISSING, schema_failure),
    (FindingKind.SCHEMA_FIELD_ADDITIONAL, schema_additional_failure),
    (FindingKind.SCHEMA_TYPE_DIVERGENCE, schema_type_failure),
    (FindingKind.POPULATION_ROW_MISSING, population_failure),
    (FindingKind.POPULATION_ROW_ADDITIONAL, population_additional_failure),
    (FindingKind.KEY_DECLARATION_DIVERGENCE, key_failure),
    (FindingKind.KEY_DUPLICATE, duplicate_failure),
    (FindingKind.CARDINALITY_DIVERGENCE, cardinality_failure),
    (FindingKind.VALUE_DIVERGENCE, value_failure),
    (FindingKind.VALUE_WARNING, warning_band_pass),
    (FindingKind.ROUNDING_DIVERGENCE, calculation_failure),
    (FindingKind.EFFECTIVE_TIME_DIVERGENCE, effective_time_failure),
    (FindingKind.AGGREGATE_DIVERGENCE, aggregate_failure),
    (FindingKind.ORDERING_NONDETERMINISTIC, ordering_failure),
    (FindingKind.FORMAT_DIVERGENCE, format_failure),
    (FindingKind.REPLAY_METADATA_DIVERGENCE, replay_failure),
)
NAMED_FIXTURES = tuple(
    dict.fromkeys(
        (
            *(fixture for _, _, passing, failing, _ in COMPARISON_CLASSES for fixture in (passing, failing)),
            *(fixture for _, fixture in FINDING_PROOFS),
            calculation_without_declared_scale_refusal,
            warning_band_pass,
            warning_band_absent,
            exclusion_pass,
            exclusion_absent,
        )
    )
)


@pytest.mark.parametrize("fixture", NAMED_FIXTURES, ids=lambda fixture: fixture.__name__)
def test_every_named_fixture_declares_a_case_the_central_validator_accepts(fixture):
    report = inspect_verification_case(fixture().case)

    assert report.issues == ()


@pytest.mark.parametrize(
    "name, dimension, passing, failing, kind",
    COMPARISON_CLASSES,
    ids=[entry[0] for entry in COMPARISON_CLASSES],
)
def test_every_comparison_class_has_an_exact_pass_and_a_deliberate_failure(name, dimension, passing, failing, kind):
    clean = passing()
    broken = failing()

    assert dimension in clean.case.comparison_policy.clauses[0].comparison.dimensions
    assert clean.reconcile().outcome.status is VerificationStatus.PASS
    assert clean.failing() == set()
    assert broken.reconcile().outcome.status is VerificationStatus.FAIL
    assert kind in broken.failing()
    assert FINDING_DIMENSION[kind] is dimension


@pytest.mark.parametrize(
    "failing, kind",
    [
        (duplicate_failure, FindingKind.KEY_DUPLICATE),
        (effective_time_failure, FindingKind.EFFECTIVE_TIME_DIVERGENCE),
        (calculation_failure, FindingKind.ROUNDING_DIVERGENCE),
        (aggregate_failure, FindingKind.AGGREGATE_DIVERGENCE),
    ],
    ids=["duplicate", "reference-time", "rounding", "aggregate"],
)
def test_duplicate_reference_time_rounding_and_aggregate_faults_are_distinct_findings(failing, kind):
    reported = failing().failing()

    assert reported == {kind}


def test_a_rounding_sized_difference_and_a_larger_difference_are_never_the_same_finding():
    rounding = calculation_failure().failing()
    value = value_failure().failing()

    assert rounding == {FindingKind.ROUNDING_DIVERGENCE}
    assert value == {FindingKind.VALUE_DIVERGENCE}
    assert FINDING_DIMENSION[FindingKind.ROUNDING_DIVERGENCE] is ComparisonDimension.CALCULATION
    assert FINDING_DIMENSION[FindingKind.VALUE_DIVERGENCE] is ComparisonDimension.VALUE


def test_a_difference_the_declared_tolerance_covers_passes_and_carries_no_finding():
    passing = scenario(
        dimensions=without(ComparisonDimension.AGGREGATE),
        actual_rows=changed(BASE_ROWS, 0, **{"daily-value": Decimal("10.03")}),
        warning_bands=(),
    )

    assert passing.reconcile().outcome.status is VerificationStatus.PASS
    assert passing.reconcile().findings == ()


def test_a_declared_warning_band_labels_a_passing_difference_without_failing_it():
    warned = warning_band_pass()
    quiet = warning_band_absent()

    assert warned.reconcile().outcome.status is VerificationStatus.PASS
    assert warned.warnings() == {FindingKind.VALUE_WARNING}
    assert warned.failing() == set()
    assert quiet.warnings() == set()


def test_a_declared_exclusion_removes_rows_from_the_class_it_names():
    excluded = exclusion_pass()
    compared = exclusion_absent()

    assert excluded.reconcile().outcome.status is VerificationStatus.PASS
    assert compared.failing() == {FindingKind.POPULATION_ROW_MISSING}


@pytest.mark.parametrize("kind, fixture", FINDING_PROOFS, ids=[kind.value for kind, _ in FINDING_PROOFS])
def test_every_finding_kind_fires_on_its_offending_input_and_not_on_a_well_formed_one(kind, fixture):
    provoked = {finding.kind for finding in fixture().reconcile().findings}
    clean = {finding.kind for finding in schema_pass().reconcile().findings}

    assert kind in provoked
    assert kind not in clean


def test_every_finding_kind_carries_a_proof():
    assert {kind for kind, _ in FINDING_PROOFS} == set(FindingKind)


def test_a_row_that_declares_no_approved_key_is_reported_and_never_matched():
    blind = scenario(
        dimensions=without(ComparisonDimension.AGGREGATE, ComparisonDimension.ORDERING),
        ordering_declaration=ordering(complete=False),
        actual_schema=schema(drop=("customer-id",)),
        actual_grain=grain(key_fields=("business-date",), duplicates=True),
        actual_rows=tuple({key: value for key, value in item.items() if key != "customer-id"} for item in BASE_ROWS),
    )
    findings = blind.reconcile().findings

    assert FindingKind.POPULATION_ROW_ADDITIONAL in {finding.kind for finding in findings}
    assert "unkeyed-row" in {finding.locator for finding in findings}
    assert blind.reconcile().outcome.status is VerificationStatus.FAIL


def test_the_finding_vocabulary_is_closed_and_every_kind_names_one_comparison_dimension():
    assert set(FINDING_DIMENSION) == set(FindingKind)
    assert set(FINDING_DIMENSION.values()) <= set(ComparisonDimension)
    assert IMPLEMENTED_DIMENSIONS == frozenset(ComparisonDimension)


def test_a_finding_carries_no_declared_value_from_either_side():
    findings = value_failure().reconcile().findings

    assert findings
    for finding in findings:
        assert "12.50" not in finding.detail
        assert "customer-a" not in finding.locator
        assert finding.row_digest is None or finding.row_digest.startswith("blake2b-256:")


def test_a_clause_outcome_is_a_domain_record_with_digests_from_the_deterministic_core():
    reconciliation = schema_pass().reconcile()
    outcome = reconciliation.outcome
    clause = parity_clauses(schema_pass().case)[0]

    assert outcome.family is ClauseFamily.PARITY
    assert outcome.clause.digest == record_digest(clause)
    assert outcome.compared_dimensions == clause.comparison.dimensions
    assert outcome.expected_evidence[0].digest.startswith("blake2b-256:")
    assert record_digest(outcome).startswith("blake2b-256:")


def test_two_runs_over_the_same_material_produce_identical_outcomes_and_digests():
    first = schema_pass().reconcile()
    second = schema_pass().reconcile()

    assert first == second
    assert record_digest(first.outcome) == record_digest(second.outcome)


def test_a_shuffled_candidate_row_order_produces_the_identical_outcome():
    ordered = scenario()
    shuffled = scenario(actual_rows=(BASE_ROWS[2], BASE_ROWS[0], BASE_ROWS[1]))

    assert shuffled.reconcile() == ordered.reconcile()
    assert record_digest(shuffled.reconcile().outcome) == record_digest(ordered.reconcile().outcome)


@pytest.mark.parametrize("provenance", list(DatasetProvenance), ids=lambda value: value.value)
def test_declared_provenance_changes_no_comparison_and_no_outcome(provenance):
    labelled = scenario(
        provenance=provenance,
        expected_origin=(
            ExpectedOutputOrigin.SYNTHETIC_DERIVATION
            if provenance is not DatasetProvenance.REAL
            else ExpectedOutputOrigin.MODERNISATION_CAPTURE
        ),
    )
    real = scenario()

    assert inspect_verification_case(labelled.case).issues == ()
    assert labelled.reconcile().findings == real.reconcile().findings
    assert labelled.reconcile().outcome.status is real.reconcile().outcome.status


def test_a_case_reconciles_every_declared_parity_clause():
    report = reconcile_case(
        schema_pass().case,
        expected_material={OUTPUT_ID: schema_pass().expected},
        observations={OUTPUT_ID: schema_pass().observation},
    )

    assert [clause.clause_id for clause in report.clauses] == [CLAUSE_ID]
    assert report.status is VerificationStatus.PASS
    assert report.outcomes == (report.clauses[0].outcome,)


# --- Integrity refusals ---


def refusal(scenario_under_test) -> ReconciliationRefusalReason:
    with pytest.raises(ReconciliationRefused) as raised:
        scenario_under_test.reconcile()
    return raised.value.reason


def test_a_one_to_one_grain_still_compares_the_declared_join_cardinality_class():
    exact = one_to_one_cardinality_pass()
    fanned = one_to_one_cardinality_failure()

    assert exact.case.expected_outputs[0].grain.duplicate_keys_permitted is False
    assert exact.reconcile().outcome.status is VerificationStatus.PASS
    assert fanned.failing() == {FindingKind.CARDINALITY_DIVERGENCE}
    assert duplicate_failure().failing() == {FindingKind.KEY_DUPLICATE}


def test_a_side_with_no_canonical_bytes_is_cited_by_the_digest_of_its_closed_reason():
    """A digest slot never holds a word, so the reason itself is a record with a digest.

    A key that repeats where the grain forbids it leaves the observed side with
    no canonical bytes. The reference for that side still carries an opaque
    fingerprint, the digest of the closed reason record, and says the reason in
    the words this engine declares for it. The side that did produce bytes is
    cited by them, so the two cannot be confused.
    """
    outcome = duplicate_failure().reconcile().outcome
    observed = outcome.observed_evidence[0]
    expected = outcome.expected_evidence[0]

    reason = record_digest(
        Identity(
            UncanonicalReason.DUPLICATE_KEYS.value,
            UNCANONICAL_REASON_FORM,
            canonical_digest(UncanonicalReason.DUPLICATE_KEYS.value.encode("ascii")),
        )
    )
    assert observed.digest == reason
    assert observed.digest.startswith(DIGEST_PREFIX)
    assert observed.summary == UNCANONICAL_SUMMARY[UncanonicalReason.DUPLICATE_KEYS]
    assert expected.digest.startswith(DIGEST_PREFIX)
    assert expected.summary != observed.summary
    # A run that produced bytes on both sides cites both by those bytes.
    matched = value_failure().reconcile().outcome
    assert matched.observed_evidence[0].summary != observed.summary
    assert matched.observed_evidence[0].digest.startswith(DIGEST_PREFIX)


def test_a_calculation_class_over_a_number_with_no_declared_decimal_scale_is_refused():
    counted = calculation_without_declared_scale_refusal()

    assert ComparisonDimension.CALCULATION in counted.case.comparison_policy.clauses[0].comparison.dimensions
    assert refusal(counted) is ReconciliationRefusalReason.DECLARATION_MISSING
    assert calculation_pass().reconcile().outcome.status is VerificationStatus.PASS
    assert calculation_failure().failing() == {FindingKind.ROUNDING_DIVERGENCE}


def test_a_declared_effective_time_class_without_an_effective_date_field_is_refused():
    blind = scenario(expected_schema=schema(effective_role="measure"))

    assert refusal(blind) is ReconciliationRefusalReason.DECLARATION_MISSING


def test_a_declared_aggregate_class_without_a_declared_aggregate_is_refused():
    empty = scenario(aggregates=(), tolerances=(VALUE_TOLERANCE,))

    assert refusal(empty) is ReconciliationRefusalReason.DECLARATION_MISSING


def test_a_declared_ordering_class_without_a_declared_ordering_is_refused():
    unordered = scenario(ordering_declaration=None)
    unordered = replace(
        unordered,
        case=_with_comparison(unordered.case, ordering=None),
    )

    assert refusal(unordered) is ReconciliationRefusalReason.DECLARATION_MISSING


def test_a_declared_replay_class_without_a_declared_replay_is_refused():
    unbound = scenario(dimensions=ALL_DIMENSIONS, replay=True)
    unbound = replace(unbound, case=_with_comparison(unbound.case, replay=None))

    assert refusal(unbound) is ReconciliationRefusalReason.DECLARATION_MISSING


def _with_comparison(case, **changes):
    """Return the case with its parity comparison changed, for a refusal proof."""
    clause = case.comparison_policy.clauses[0]
    replaced = replace(clause, comparison=replace(clause.comparison, **changes))
    return replace(case, comparison_policy=replace(case.comparison_policy, clauses=(replaced,)))


def test_an_aggregate_operation_the_engine_does_not_compute_is_refused():
    unknown = scenario(aggregates=(aggregate_control(operation="median"),))

    assert refusal(unknown) is ReconciliationRefusalReason.OPERATION_NOT_IMPLEMENTED


def test_a_null_handling_the_engine_does_not_apply_is_refused():
    unknown = scenario(aggregates=(aggregate_control(null_handling="ignore"),))

    assert refusal(unknown) is ReconciliationRefusalReason.OPERATION_NOT_IMPLEMENTED


def test_a_rounding_mode_the_engine_does_not_apply_is_refused():
    unknown = scenario(aggregates=(aggregate_control(rounding="banker"),))

    assert refusal(unknown) is ReconciliationRefusalReason.OPERATION_NOT_IMPLEMENTED


def test_a_tolerance_measurement_the_engine_does_not_measure_is_refused():
    unknown = scenario(tolerances=(replace(VALUE_TOLERANCE, measurement="relative-difference"), AGGREGATE_TOLERANCE))

    assert refusal(unknown) is ReconciliationRefusalReason.OPERATION_NOT_IMPLEMENTED


def test_an_exclusion_operator_the_engine_does_not_execute_is_refused():
    unknown = scenario(
        exclusions=(
            replace(
                SUPPRESSED_EXCLUSION,
                selector=(RuleConstraint("record-state", RuleOperator.MATCHES, "suppressed.*"),),
            ),
        )
    )

    assert refusal(unknown) is ReconciliationRefusalReason.RULE_NOT_IMPLEMENTED


def test_expected_rows_that_do_not_produce_the_declared_digest_are_refused():
    tampered = scenario()
    tampered = replace(
        tampered, expected=ExpectedMaterial(tampered.expected.output, changed(BASE_ROWS, 0, **{"daily-value": Decimal("99.00")}))
    )

    assert refusal(tampered) is ReconciliationRefusalReason.CONTENT_DIGEST_MISMATCH


def test_candidate_rows_that_do_not_produce_the_declared_digest_are_refused():
    tampered = scenario(actual_content_digest="blake2b-256:not-the-bytes")

    assert refusal(tampered) is ReconciliationRefusalReason.CONTENT_DIGEST_MISMATCH


def test_a_declared_row_count_the_supplied_rows_do_not_match_is_refused():
    miscounted = scenario(actual_row_count=99)

    assert refusal(miscounted) is ReconciliationRefusalReason.ROW_COUNT_MISMATCH


def test_material_for_another_output_is_refused():
    mismatched = scenario()
    mismatched = replace(
        mismatched,
        expected=ExpectedMaterial(replace(mismatched.expected.output, output_id="other-output"), mismatched.expected.rows),
    )

    assert refusal(mismatched) is ReconciliationRefusalReason.UNRESOLVED_EXPECTED_OUTPUT


def test_an_oracle_that_contradicts_the_expected_output_the_case_declares_is_refused():
    swapped = scenario()
    swapped = replace(
        swapped,
        expected=ExpectedMaterial(
            replace(swapped.expected.output, content_digest="blake2b-256:another-oracle"), swapped.expected.rows
        ),
    )

    assert refusal(swapped) is ReconciliationRefusalReason.ORACLE_CONTRADICTION


def test_an_observation_for_another_output_is_refused():
    mismatched = scenario()
    mismatched = replace(
        mismatched,
        observation=replace(
            mismatched.observation, output=replace(mismatched.observation.output, output_id="other-output")
        ),
    )

    assert refusal(mismatched) is ReconciliationRefusalReason.UNRESOLVED_ACTUAL_OUTPUT


def test_a_case_with_no_material_for_a_declared_clause_is_refused():
    incomplete = scenario()

    with pytest.raises(ReconciliationRefused) as raised:
        reconcile_case(incomplete.case, expected_material={}, observations={})

    assert raised.value.reason is ReconciliationRefusalReason.UNRESOLVED_EXPECTED_OUTPUT


def test_an_oracle_that_repeats_a_key_its_own_grain_forbids_produces_no_comparison():
    contradictory = scenario(expected_rows=BASE_ROWS)
    material = ExpectedMaterial(contradictory.expected.output, BASE_ROWS + (BASE_ROWS[0],))

    with pytest.raises(CanonicalisationRefusal) as raised:
        replace(contradictory, expected=material).reconcile()

    assert raised.value.reason is RefusalReason.DUPLICATE_KEY_NOT_PERMITTED


def test_a_declared_ordering_the_observed_rows_cannot_carry_is_an_integrity_refusal():
    blind = scenario(
        actual_schema=schema(drop=("customer-id",)),
        actual_grain=grain(key_fields=("business-date",), duplicates=True),
        actual_rows=tuple({key: value for key, value in item.items() if key != "customer-id"} for item in BASE_ROWS),
        actual_content_digest="blake2b-256:unavailable",
    )

    with pytest.raises(CanonicalisationRefusal) as raised:
        blind.reconcile()

    assert raised.value.reason is RefusalReason.ORDERING_NOT_APPLICABLE


def test_every_refusal_reason_is_proved_here_or_guarded_against_a_later_dimension():
    proved_here = {
        ReconciliationRefusalReason.UNRESOLVED_EXPECTED_OUTPUT,
        ReconciliationRefusalReason.UNRESOLVED_ACTUAL_OUTPUT,
        ReconciliationRefusalReason.ORACLE_CONTRADICTION,
        ReconciliationRefusalReason.CONTENT_DIGEST_MISMATCH,
        ReconciliationRefusalReason.ROW_COUNT_MISMATCH,
        ReconciliationRefusalReason.DECLARATION_MISSING,
        ReconciliationRefusalReason.OPERATION_NOT_IMPLEMENTED,
        ReconciliationRefusalReason.RULE_NOT_IMPLEMENTED,
        ReconciliationRefusalReason.RULE_SOURCE_UNRESOLVED,
        ReconciliationRefusalReason.ORIGIN_CONTRADICTION,
    }
    proved_over_the_environment_contracts = {
        ReconciliationRefusalReason.INTAKE_CASE_MISMATCH,
        ReconciliationRefusalReason.CANDIDATE_OUTPUT_MISMATCH,
    }
    # The remaining reason cannot be provoked while the engine evaluates every
    # declared dimension. The guard turns red the moment one is added.
    guarded = {ReconciliationRefusalReason.DIMENSION_NOT_IMPLEMENTED}

    assert proved_here | proved_over_the_environment_contracts | guarded == set(ReconciliationRefusalReason)
    assert IMPLEMENTED_DIMENSIONS == frozenset(ComparisonDimension)


# --- Rule-derived expected outputs ---


PUBLISHED_RULE = RuleDeclaration(
    "published-records", "v1", (RuleConstraint("record-state", RuleOperator.EQUALS, "published"),)
)


def derivation(rule: RuleDeclaration = PUBLISHED_RULE, *, dataset_id: str = "input-dataset") -> RuleDerivation:
    return RuleDerivation(OUTPUT_ID, dataset_id, DatasetRole.INPUT, rule)


def derivation_case(origin=RULE_DERIVED_ORIGIN):
    """Return a case whose expected output is the one a declared rule produces."""
    return scenario(expected_rows=BASE_ROWS, expected_origin=origin).case


def test_a_declared_rule_derives_the_expected_output_and_labels_its_origin():
    derived = derive_expected_output(
        derivation_case(), derivation(), INPUT_ROWS, ordering=ordering()
    )

    assert derived.output.origin is RULE_DERIVED_ORIGIN
    assert derived.output.provenance is RULE_DERIVED_PROVENANCE
    assert derived.rows == BASE_ROWS
    assert derived.output.row_count == len(BASE_ROWS)
    assert derived.output.content_digest == dataset_digest(
        BASE_ROWS, schema=schema(), grain=grain(), canonicalisation=CANONICALISATION, ordering=ordering()
    )
    assert derived.rule.digest == record_digest(PUBLISHED_RULE)


def test_a_rule_derivation_is_deterministic_over_the_same_frozen_input():
    case = derivation_case()

    first = derive_expected_output(case, derivation(), INPUT_ROWS, ordering=ordering())
    second = derive_expected_output(case, derivation(), tuple(reversed(INPUT_ROWS)), ordering=ordering())

    assert first.output == second.output
    assert record_digest(first.output) == record_digest(second.output)


def test_a_derived_expected_output_reconciles_like_any_other_oracle():
    case = derivation_case()
    derived = derive_expected_output(case, derivation(), INPUT_ROWS, ordering=ordering())
    reconciled = scenario(expected_origin=RULE_DERIVED_ORIGIN)
    reconciliation = reconcile_clause(
        case,
        parity_clauses(case)[0],
        ExpectedMaterial(replace(derived.output, version="v1"), derived.rows),
        reconciled.observation,
    )

    assert reconciliation.outcome.status is VerificationStatus.PASS


def test_a_rule_operator_the_engine_does_not_execute_is_refused_and_never_guessed():
    unknown = RuleDeclaration(
        "matching-records", "v1", (RuleConstraint("record-state", RuleOperator.MATCHES, "publish.*"),)
    )

    with pytest.raises(ReconciliationRefused) as raised:
        derive_expected_output(derivation_case(), derivation(unknown), INPUT_ROWS, ordering=ordering())

    assert raised.value.reason is ReconciliationRefusalReason.RULE_NOT_IMPLEMENTED


def test_a_derivation_from_an_undeclared_frozen_input_is_refused():
    with pytest.raises(ReconciliationRefused) as raised:
        derive_expected_output(
            derivation_case(), derivation(dataset_id="other-dataset"), INPUT_ROWS, ordering=ordering()
        )

    assert raised.value.reason is ReconciliationRefusalReason.RULE_SOURCE_UNRESOLVED


def test_a_derivation_for_an_output_the_case_declares_from_another_origin_is_refused():
    with pytest.raises(ReconciliationRefused) as raised:
        derive_expected_output(
            derivation_case(ExpectedOutputOrigin.MODERNISATION_CAPTURE),
            derivation(),
            INPUT_ROWS,
            ordering=ordering(),
        )

    assert raised.value.reason is ReconciliationRefusalReason.ORIGIN_CONTRADICTION


def test_a_derivation_whose_rows_contradict_the_declared_input_digest_is_refused():
    with pytest.raises(ReconciliationRefused) as raised:
        derive_expected_output(derivation_case(), derivation(), BASE_ROWS, ordering=ordering())

    assert raised.value.reason is ReconciliationRefusalReason.CONTENT_DIGEST_MISMATCH


def test_a_declared_expected_output_that_the_rule_does_not_produce_is_refused():
    case = derivation_case()
    narrower = RuleDeclaration(
        "recent-records", "v1", (RuleConstraint("daily-value", RuleOperator.AT_LEAST, "20.00"),)
    )

    with pytest.raises(ReconciliationRefused) as raised:
        derive_expected_output(case, derivation(narrower), INPUT_ROWS, ordering=ordering())

    assert raised.value.reason is ReconciliationRefusalReason.CONTENT_DIGEST_MISMATCH


def test_the_engine_reads_a_key_identity_without_carrying_its_declared_values():
    missing = population_failure().reconcile().findings

    assert missing
    for finding in missing:
        assert finding.locator.startswith("blake2b-256:")
        assert "customer" not in finding.locator
