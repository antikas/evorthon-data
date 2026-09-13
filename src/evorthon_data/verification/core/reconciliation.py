"""Deterministic reconciliation of a frozen expected output with a candidate output.

This module is the comparison engine. It reads an approved case, the frozen
expected material and one candidate observation, and reports what differs. It
decides nothing about acceptance and it gates nothing: every difference is a
finding a person reads, and a finding never depends on whether the evidence was
declared real, synthetic or derived.

The engine compares one parity clause at a time, across the comparison
dimensions the clause declares.

* Schema. The declared fields of the oracle and of the observed output: which
  fields exist, their logical types, their nullability and their declared
  precision and scale.
* Population. The rows each side holds, keyed by the declared grain.
* Keys. The declared key fields themselves, and any key repeated where the
  declared grain forbids repetition.
* Values. Field by field, over rows the declared grain matches, against the
  declared tolerances and warning bands.
* Calculation. The narrow value difference whose size is at most one unit in
  the last declared decimal place, which is the signature of a rounding or
  precision difference rather than a different answer. A declared number with
  no declared decimal scale has no last place, so the class is refused rather
  than measured against a scale nobody declared.
* Joins and cardinality. How many rows a key carries on each side. A grain that
  permits a key to repeat declares a fan-out to compare; a grain that forbids
  it declares one row per key, and a key the observed output carries more than
  once is the fan-out that declaration does not allow. The class is therefore
  compared under both declared grains.
* Effective time. The declared effective-date fields of matched rows, which is
  the reference-time difference and never a plain value difference.
* Aggregates and control totals. Every declared aggregate, computed over both
  sides with the declared operation, null handling and rounding.
* Ordering. Whether the declared ordering determines the row order at all, or
  leaves rows tied and the written order undetermined.
* Output format. The declared written form of the output: its format name, its
  canonicalisation and its format digest.
* Replay metadata. The declared replay facts against the metadata the run
  actually observed.

Each of those classes owns its own finding kinds, so a duplicate, a
reference-time difference, a rounding difference and an aggregate difference
are four separate kinds that cannot be read as one another.

Refusals are integrity refusals: a case whose clause names material that is not
declared, supplied rows that do not produce the identity their own record
declares, a comparison class the case declares without the declaration that
class needs, and a declared operation or rule the engine does not implement.
The engine never guesses a missing declaration and never passes a declared
class it could not evaluate.

Every reference the engine writes cites its side by a digest. A side whose rows
cannot produce canonical bytes under their own declared grain is cited by the
digest of the closed reason record for that, and says the reason in the words
declared here, so a digest slot never holds anything a reader could turn back
into a value and a reportable difference is never kept out of a later record.

The module reads no file, no clock, no environment and no locale, and it draws
no random value. Two runs over the same case and the same material produce
identical records and identical digests. A caller's row order never reaches a
result, because every comparison reads the canonical bytes the deterministic
core writes.
"""
# evorthon-implements: EVD-README-042
# evorthon-implements: EVD-README-017
from __future__ import annotations

# evorthon-component: verification_core

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation
from enum import Enum
from types import MappingProxyType

from evorthon_data.verification.core.canonical import (
    FRAME_SEPARATOR,
    CanonicalisationRefusal,
    RefusalReason,
    canonical_digest,
    canonical_row_stream,
    record_digest,
)
from evorthon_data.verification.domain.contracts import (
    ActualOutput,
    AggregateControl,
    ClauseFamily,
    ClauseOutcome,
    ComparisonDimension,
    ContextIdentity,
    DatasetProvenance,
    DatasetRole,
    EvidenceReference,
    ExpectedOutput,
    ExpectedOutputOrigin,
    GrainDeclaration,
    Identity,
    OrderingDeclaration,
    ParityClause,
    RuleConstraint,
    RuleDeclaration,
    RuleOperator,
    SchemaDeclaration,
    SchemaField,
    SchemaValueType,
    VerificationCase,
    VerificationStatus,
)

RECONCILIATION_FORM = "evorthon.verification.reconciliation.v1"
KEY_IDENTITY_FORM = "evorthon.verification.reconciliation.key.v1"
UNCANONICAL_REASON_FORM = "evorthon.verification.reconciliation.uncanonical.v1"

# The declared semantic role that marks a field as carrying effective time. A
# comparison that declares the effective-time dimension and no field with this
# role is refused rather than compared as an ordinary value.
EFFECTIVE_TIME_ROLE = "effective-date"

# The origin an expected output carries once this engine derives it from a
# declared rule over frozen inputs.
RULE_DERIVED_ORIGIN = ExpectedOutputOrigin.SYNTHETIC_DERIVATION
RULE_DERIVED_PROVENANCE = DatasetProvenance.DERIVED

IMPLEMENTED_DIMENSIONS = frozenset(ComparisonDimension)
IMPLEMENTED_RULE_OPERATORS = frozenset(
    {
        RuleOperator.EQUALS,
        RuleOperator.NOT_EQUALS,
        RuleOperator.PRESENT,
        RuleOperator.ABSENT,
        RuleOperator.AT_LEAST,
        RuleOperator.AT_MOST,
    }
)
IMPLEMENTED_MEASUREMENTS = ("absolute-difference",)
IMPLEMENTED_AGGREGATE_OPERATIONS = ("sum", "count", "minimum", "maximum")
IMPLEMENTED_NULL_HANDLING = ("exclude-null", "reject-null")
IMPLEMENTED_ROUNDING_MODES = MappingProxyType(
    {"half-even": ROUND_HALF_EVEN, "half-up": ROUND_HALF_UP, "down": ROUND_DOWN}
)
NUMERIC_VALUE_TYPES = (SchemaValueType.INTEGER, SchemaValueType.DECIMAL)


class FindingKind(str, Enum):
    """The closed vocabulary of differences this engine can report."""

    SCHEMA_FIELD_MISSING = "schema-field-missing"
    SCHEMA_FIELD_ADDITIONAL = "schema-field-additional"
    SCHEMA_TYPE_DIVERGENCE = "schema-type-divergence"
    POPULATION_ROW_MISSING = "population-row-missing"
    POPULATION_ROW_ADDITIONAL = "population-row-additional"
    KEY_DECLARATION_DIVERGENCE = "key-declaration-divergence"
    KEY_DUPLICATE = "key-duplicate"
    CARDINALITY_DIVERGENCE = "cardinality-divergence"
    VALUE_DIVERGENCE = "value-divergence"
    VALUE_WARNING = "value-warning"
    ROUNDING_DIVERGENCE = "rounding-divergence"
    EFFECTIVE_TIME_DIVERGENCE = "effective-time-divergence"
    AGGREGATE_DIVERGENCE = "aggregate-divergence"
    ORDERING_NONDETERMINISTIC = "ordering-nondeterministic"
    FORMAT_DIVERGENCE = "format-divergence"
    REPLAY_METADATA_DIVERGENCE = "replay-metadata-divergence"


# Every finding kind belongs to exactly one declared comparison dimension, so a
# reader can never attribute a difference to the wrong comparison class.
FINDING_DIMENSION = MappingProxyType(
    {
        FindingKind.SCHEMA_FIELD_MISSING: ComparisonDimension.SCHEMA,
        FindingKind.SCHEMA_FIELD_ADDITIONAL: ComparisonDimension.SCHEMA,
        FindingKind.SCHEMA_TYPE_DIVERGENCE: ComparisonDimension.SCHEMA,
        FindingKind.POPULATION_ROW_MISSING: ComparisonDimension.POPULATION,
        FindingKind.POPULATION_ROW_ADDITIONAL: ComparisonDimension.POPULATION,
        FindingKind.KEY_DECLARATION_DIVERGENCE: ComparisonDimension.KEY,
        FindingKind.KEY_DUPLICATE: ComparisonDimension.KEY,
        FindingKind.CARDINALITY_DIVERGENCE: ComparisonDimension.JOIN_CARDINALITY,
        FindingKind.VALUE_DIVERGENCE: ComparisonDimension.VALUE,
        FindingKind.VALUE_WARNING: ComparisonDimension.VALUE,
        FindingKind.ROUNDING_DIVERGENCE: ComparisonDimension.CALCULATION,
        FindingKind.EFFECTIVE_TIME_DIVERGENCE: ComparisonDimension.EFFECTIVE_TIME,
        FindingKind.AGGREGATE_DIVERGENCE: ComparisonDimension.AGGREGATE,
        FindingKind.ORDERING_NONDETERMINISTIC: ComparisonDimension.ORDERING,
        FindingKind.FORMAT_DIVERGENCE: ComparisonDimension.OUTPUT_FORMAT,
        FindingKind.REPLAY_METADATA_DIVERGENCE: ComparisonDimension.REPLAY_METADATA,
    }
)


class FindingSeverity(str, Enum):
    """Whether a finding makes its clause fail or only labels a passing difference."""

    FAILING = "failing"
    WARNING = "warning"


class UncanonicalReason(str, Enum):
    """The closed set of reasons one side of a comparison produces no canonical bytes."""

    DUPLICATE_KEYS = "no-canonical-bytes-duplicate-keys"


# What a reference says about a side that produced no canonical bytes. The
# words are declared here and closed, because a reference that cannot cite
# bytes still has to say what it is citing instead.
UNCANONICAL_SUMMARY = MappingProxyType(
    {
        UncanonicalReason.DUPLICATE_KEYS: (
            "no canonical bytes because a key repeats where the declared grain forbids repetition"
        ),
    }
)
if frozenset(UNCANONICAL_SUMMARY) != frozenset(UncanonicalReason):  # pragma: no cover
    raise RuntimeError("every reason for no canonical bytes declares its own summary")


class ReconciliationRefusalReason(str, Enum):
    """The closed set of integrity reasons for refusing to reconcile."""

    UNRESOLVED_EXPECTED_OUTPUT = "unresolved-expected-output"
    UNRESOLVED_ACTUAL_OUTPUT = "unresolved-actual-output"
    ORACLE_CONTRADICTION = "oracle-contradiction"
    CONTENT_DIGEST_MISMATCH = "content-digest-mismatch"
    ROW_COUNT_MISMATCH = "row-count-mismatch"
    DECLARATION_MISSING = "declaration-missing"
    DIMENSION_NOT_IMPLEMENTED = "dimension-not-implemented"
    OPERATION_NOT_IMPLEMENTED = "operation-not-implemented"
    RULE_NOT_IMPLEMENTED = "rule-not-implemented"
    RULE_SOURCE_UNRESOLVED = "rule-source-unresolved"
    ORIGIN_CONTRADICTION = "origin-contradiction"
    INTAKE_CASE_MISMATCH = "intake-case-mismatch"
    CANDIDATE_OUTPUT_MISMATCH = "candidate-output-mismatch"


class ReconciliationRefused(ValueError):
    """Raised when a comparison cannot be made with declared meaning."""

    def __init__(self, reason: ReconciliationRefusalReason, subject: str, detail: str) -> None:
        super().__init__(f"{reason.value} at {subject}: {detail}")
        self.reason = reason
        self.subject = subject
        self.detail = detail


@dataclass(frozen=True)
class Finding:
    """One reported difference, with no declared value in it.

    ``locator`` names the clause, the output and, where one applies, the field
    or aggregate. ``row_digest`` is the canonical digest of the row the finding
    concerns, so a later component can find the row without this record
    carrying its content. ``measured`` is a magnitude in the declared unit and
    is present only where a declared tolerance or band measured one.
    """

    kind: FindingKind
    dimension: ComparisonDimension
    severity: FindingSeverity
    clause_id: str
    output_id: str
    locator: str
    detail: str
    row_digest: str | None = None
    measured: str | None = None


@dataclass(frozen=True)
class ExpectedMaterial:
    """The frozen oracle for one output: its approved record and its rows."""

    output: ExpectedOutput
    rows: tuple[Mapping[str, object], ...]


@dataclass(frozen=True)
class CandidateObservation:
    """One candidate output and the run metadata observed with it."""

    output: ActualOutput
    rows: tuple[Mapping[str, object], ...]
    context: ContextIdentity
    observed_inputs: tuple[Identity, ...] = ()


@dataclass(frozen=True)
class RuleDerivation:
    """A declared derivation of one expected output from one frozen input."""

    output_id: str
    source_dataset_id: str
    source_role: DatasetRole
    rule: RuleDeclaration


@dataclass(frozen=True)
class DerivedExpectedOutput:
    """An expected output this engine produced by executing a declared rule."""

    output: ExpectedOutput
    rows: tuple[Mapping[str, object], ...]
    rule: Identity


@dataclass(frozen=True)
class ClauseReconciliation:
    """The deterministic outcome and findings for one parity clause."""

    clause_id: str
    output_id: str
    outcome: ClauseOutcome
    findings: tuple[Finding, ...]


@dataclass(frozen=True)
class ReconciliationReport:
    """Every reconciled clause of one case, with the status they imply."""

    clauses: tuple[ClauseReconciliation, ...]

    @property
    def findings(self) -> tuple[Finding, ...]:
        return tuple(finding for clause in self.clauses for finding in clause.findings)

    @property
    def outcomes(self) -> tuple[ClauseOutcome, ...]:
        return tuple(clause.outcome for clause in self.clauses)

    @property
    def status(self) -> VerificationStatus:
        failed = any(clause.outcome.status is VerificationStatus.FAIL for clause in self.clauses)
        return VerificationStatus.FAIL if failed else VerificationStatus.PASS


@dataclass(frozen=True)
class _Row:
    """One canonical row: its canonical bytes, its digest and its typed values."""

    payload: str
    digest: str
    values: Mapping[str, object]


@dataclass(frozen=True)
class _Material:
    """One side of a comparison, read back from the canonical bytes it produces.

    ``digest`` is absent when the rows cannot produce canonical bytes under
    their own declared grain, which happens only when a key repeats where the
    grain forbids repetition. ``uncanonical`` names that reason from the closed
    set and is present exactly when the digest is not, so a reader never has to
    guess why a side produced none.
    """

    digest: str | None
    rows: tuple[_Row, ...]
    index: Mapping[str, SchemaField]
    uncanonical: UncanonicalReason | None = None


def _refuse(reason: ReconciliationRefusalReason, subject: str, detail: str) -> ReconciliationRefused:
    return ReconciliationRefused(reason, subject, detail)


def _frames(stream: bytes) -> list[str]:
    """Read back the frames of a canonical row stream written by the core."""
    frames: list[str] = []
    position = 0
    while position < len(stream):
        separator = stream.index(FRAME_SEPARATOR, position)
        length = int(stream[position:separator].decode("ascii"))
        start = separator + 1
        end = start + length
        frames.append(stream[start:end].decode("ascii"))
        position = end + 1
    return frames


def _field_index(schema: SchemaDeclaration) -> dict[str, SchemaField]:
    return {field.field_id: field for field in schema.fields}


def _row_from(payload: str, index: Mapping[str, SchemaField]) -> _Row:
    node = json.loads(payload, parse_float=Decimal)
    values: dict[str, object] = {}
    for field_id, value in node.items():
        field = index.get(field_id)
        if field is not None and field.value_type is SchemaValueType.DECIMAL and type(value) is int:
            value = Decimal(value)
        values[field_id] = value
    return _Row(payload=payload, digest=canonical_digest(payload.encode("ascii")), values=values)


def _material(
    rows: Sequence[Mapping[str, object]],
    *,
    schema: SchemaDeclaration,
    grain: GrainDeclaration,
    canonicalisation,
    ordering: OrderingDeclaration | None,
    repeats_reportable: bool,
) -> _Material:
    """Return the canonical bytes, digest and typed rows for one side.

    A grain that forbids repetition and rows that repeat a key produce no
    canonical bytes. That contradiction is reportable when the case declares
    the key dimension or the join-cardinality dimension, so the rows are read
    back under a grain that permits repetition and the digest is reported as
    absent. When the case declares neither there is no class that can report
    it, so the core's own integrity refusal stands.
    """
    index = _field_index(schema)
    try:
        stream = canonical_row_stream(
            rows, schema=schema, grain=grain, canonicalisation=canonicalisation, ordering=ordering
        )
    except CanonicalisationRefusal as refusal:
        if refusal.reason is not RefusalReason.DUPLICATE_KEY_NOT_PERMITTED or not repeats_reportable:
            raise
        stream = canonical_row_stream(
            rows,
            schema=schema,
            grain=replace(grain, duplicate_keys_permitted=True),
            canonicalisation=canonicalisation,
            ordering=ordering,
        )
        return _Material(
            None,
            tuple(_row_from(payload, index) for payload in _frames(stream)[1:]),
            index,
            UncanonicalReason.DUPLICATE_KEYS,
        )
    return _Material(
        canonical_digest(stream),
        tuple(_row_from(payload, index) for payload in _frames(stream)[1:]),
        index,
    )


def _text_form(value: object) -> str | None:
    """Return the declared text form of one canonical value, or nothing for a null."""
    if value is None:
        return None
    if type(value) is bool:
        return "true" if value else "false"
    if isinstance(value, (int, Decimal)):
        return str(value)
    return str(value)


def _numeric(value: object) -> Decimal | None:
    if type(value) is bool or value is None:
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if isinstance(value, int):
        return Decimal(value)
    return None


def _bound(value: str | None, subject: str) -> Decimal:
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise _refuse(
            ReconciliationRefusalReason.OPERATION_NOT_IMPLEMENTED,
            subject,
            "a declared bound must be a decimal the engine can read",
        ) from None


def _constraint_holds(constraint: RuleConstraint, row: _Row, subject: str) -> bool:
    """Return whether one declared constraint holds for one canonical row."""
    if constraint.operator not in IMPLEMENTED_RULE_OPERATORS:
        raise _refuse(
            ReconciliationRefusalReason.RULE_NOT_IMPLEMENTED,
            subject,
            f"the engine executes no rule operator {constraint.operator.value}",
        )
    if constraint.field_id not in row.values:
        raise _refuse(
            ReconciliationRefusalReason.RULE_NOT_IMPLEMENTED,
            subject,
            f"the rule names field {constraint.field_id}, which the compared rows do not declare",
        )
    value = row.values[constraint.field_id]
    if constraint.operator is RuleOperator.PRESENT:
        return value is not None
    if constraint.operator is RuleOperator.ABSENT:
        return value is None
    if value is None:
        # A null satisfies no value comparison. Presence is stated explicitly.
        return False
    if constraint.operator is RuleOperator.EQUALS:
        return _text_form(value) == constraint.expected_value
    if constraint.operator is RuleOperator.NOT_EQUALS:
        return _text_form(value) != constraint.expected_value
    measured = _numeric(value)
    if measured is None:
        raise _refuse(
            ReconciliationRefusalReason.RULE_NOT_IMPLEMENTED,
            subject,
            f"field {constraint.field_id} carries no number the declared bound can be compared with",
        )
    limit = _bound(constraint.expected_value, subject)
    if constraint.operator is RuleOperator.AT_LEAST:
        return measured >= limit
    return measured <= limit


def _rule_holds(constraints: Sequence[RuleConstraint], row: _Row, subject: str) -> bool:
    return all(_constraint_holds(constraint, row, subject) for constraint in constraints)


def _scoped(declarations, clause_id: str, dimension: ComparisonDimension):
    return tuple(
        declaration
        for declaration in declarations
        if clause_id in declaration.clause_ids and dimension in declaration.dimensions
    )


def _retained(rows: tuple[_Row, ...], exclusions, clause_id: str, dimension: ComparisonDimension, subject: str):
    """Return the rows no declared exclusion removes from this comparison class."""
    scoped = _scoped(exclusions, clause_id, dimension)
    if not scoped:
        return rows
    return tuple(
        row
        for row in rows
        if not any(_rule_holds(exclusion.selector, row, subject) for exclusion in scoped)
    )


def _key_of(row: _Row, grain: GrainDeclaration) -> tuple[str | None, ...] | None:
    key: list[str | None] = []
    for field_id in grain.key_fields:
        if field_id not in row.values:
            return None
        key.append(_text_form(row.values[field_id]))
    return tuple(key)


def _by_key(rows: tuple[_Row, ...], grain: GrainDeclaration):
    keyed: dict[tuple[str | None, ...], list[_Row]] = {}
    unkeyed: list[_Row] = []
    for row in rows:
        key = _key_of(row, grain)
        if key is None:
            unkeyed.append(row)
            continue
        keyed.setdefault(key, []).append(row)
    return keyed, tuple(unkeyed)


def _key_text(key: tuple[str | None, ...]) -> str:
    """Return a stable identity for one key without carrying its declared values.

    Each part is written with its own length before it, so two different keys
    can never be written the same way.
    """
    parts = [KEY_IDENTITY_FORM]
    parts.extend("null" if part is None else f"{len(part)}:{part}" for part in key)
    return canonical_digest("\n".join(parts).encode("utf-8"))


def _finding(
    kind: FindingKind,
    *,
    clause_id: str,
    output_id: str,
    locator: str,
    detail: str,
    severity: FindingSeverity = FindingSeverity.FAILING,
    row_digest: str | None = None,
    measured: str | None = None,
) -> Finding:
    return Finding(
        kind=kind,
        dimension=FINDING_DIMENSION[kind],
        severity=severity,
        clause_id=clause_id,
        output_id=output_id,
        locator=locator,
        detail=detail,
        row_digest=row_digest,
        measured=measured,
    )


def _compare_schema(oracle: SchemaDeclaration, observed: SchemaDeclaration, clause_id: str, output_id: str):
    findings: list[Finding] = []
    oracle_index = _field_index(oracle)
    observed_index = _field_index(observed)
    for field_id in sorted(set(oracle_index) - set(observed_index)):
        findings.append(
            _finding(
                FindingKind.SCHEMA_FIELD_MISSING,
                clause_id=clause_id,
                output_id=output_id,
                locator=field_id,
                detail="the approved schema declares a field the observed output does not",
            )
        )
    for field_id in sorted(set(observed_index) - set(oracle_index)):
        findings.append(
            _finding(
                FindingKind.SCHEMA_FIELD_ADDITIONAL,
                clause_id=clause_id,
                output_id=output_id,
                locator=field_id,
                detail="the observed output declares a field the approved schema does not",
            )
        )
    for field_id in sorted(set(oracle_index) & set(observed_index)):
        approved = oracle_index[field_id]
        seen = observed_index[field_id]
        if (approved.value_type, approved.nullable, approved.precision, approved.scale) != (
            seen.value_type,
            seen.nullable,
            seen.precision,
            seen.scale,
        ):
            findings.append(
                _finding(
                    FindingKind.SCHEMA_TYPE_DIVERGENCE,
                    clause_id=clause_id,
                    output_id=output_id,
                    locator=field_id,
                    detail="the observed field declares a different type, nullability, precision or scale",
                )
            )
    return findings


def _compare_keys(
    grain: GrainDeclaration,
    observed_grain: GrainDeclaration,
    actual: _Material,
    clause_id: str,
    output_id: str,
):
    findings: list[Finding] = []
    if grain.key_fields != observed_grain.key_fields:
        findings.append(
            _finding(
                FindingKind.KEY_DECLARATION_DIVERGENCE,
                clause_id=clause_id,
                output_id=output_id,
                locator="grain.key_fields",
                detail="the observed output declares different key fields from the approved grain",
            )
        )
    if grain.duplicate_keys_permitted != observed_grain.duplicate_keys_permitted:
        findings.append(
            _finding(
                FindingKind.KEY_DECLARATION_DIVERGENCE,
                clause_id=clause_id,
                output_id=output_id,
                locator="grain.duplicate_keys_permitted",
                detail="the observed output declares a different duplicate-key policy from the approved grain",
            )
        )
    if grain.duplicate_keys_permitted:
        return findings
    keyed, _ = _by_key(actual.rows, grain)
    for key, rows in keyed.items():
        if len(rows) > 1:
            findings.append(
                _finding(
                    FindingKind.KEY_DUPLICATE,
                    clause_id=clause_id,
                    output_id=output_id,
                    locator=_key_text(key),
                    detail=f"the approved grain forbids a repeated key and the observed output carries it {len(rows)} times",
                    row_digest=rows[0].digest,
                )
            )
    return sorted(findings, key=lambda finding: (finding.kind.value, finding.locator))


def _compare_population(expected_keyed, actual_keyed, unkeyed, clause_id: str, output_id: str):
    findings: list[Finding] = []
    for key in sorted(set(expected_keyed) - set(actual_keyed), key=_key_text):
        findings.append(
            _finding(
                FindingKind.POPULATION_ROW_MISSING,
                clause_id=clause_id,
                output_id=output_id,
                locator=_key_text(key),
                detail="the approved population holds a key the observed output does not",
                row_digest=expected_keyed[key][0].digest,
            )
        )
    for key in sorted(set(actual_keyed) - set(expected_keyed), key=_key_text):
        findings.append(
            _finding(
                FindingKind.POPULATION_ROW_ADDITIONAL,
                clause_id=clause_id,
                output_id=output_id,
                locator=_key_text(key),
                detail="the observed output holds a key the approved population does not",
                row_digest=actual_keyed[key][0].digest,
            )
        )
    for row in unkeyed:
        findings.append(
            _finding(
                FindingKind.POPULATION_ROW_ADDITIONAL,
                clause_id=clause_id,
                output_id=output_id,
                locator="unkeyed-row",
                detail="the observed output holds a row that declares no approved key field",
                row_digest=row.digest,
            )
        )
    return findings


def _compare_cardinality(expected_keyed, actual_keyed, clause_id: str, output_id: str):
    """Compare how many rows each key carries, under either declared grain.

    A key only one side holds is population, not cardinality, so this class
    reads the keys both sides hold. Under a grain that forbids repetition the
    approved count is one, and an observed count above it is the fan-out the
    grain does not allow; the key class states the same rows break the grain
    declaration itself.
    """
    findings: list[Finding] = []
    for key in sorted(set(expected_keyed) & set(actual_keyed), key=_key_text):
        approved = len(expected_keyed[key])
        seen = len(actual_keyed[key])
        if approved != seen:
            findings.append(
                _finding(
                    FindingKind.CARDINALITY_DIVERGENCE,
                    clause_id=clause_id,
                    output_id=output_id,
                    locator=_key_text(key),
                    detail=f"the approved population carries {approved} rows for this key and the observed output carries {seen}",
                    row_digest=actual_keyed[key][0].digest,
                    measured=str(seen - approved),
                )
            )
    return findings


def _within(measured: Decimal, declaration, subject: str) -> bool:
    if declaration.measurement not in IMPLEMENTED_MEASUREMENTS:
        raise _refuse(
            ReconciliationRefusalReason.OPERATION_NOT_IMPLEMENTED,
            subject,
            f"the engine measures no declared difference of kind {declaration.measurement}",
        )
    lower = _bound(declaration.lower_bound, subject)
    upper = _bound(declaration.upper_bound, subject)
    return lower <= measured <= upper


def _tolerated(measured: Decimal, tolerances, field_id: str, subject: str) -> bool:
    for tolerance in tolerances:
        if field_id not in tolerance.field_ids:
            continue
        if tolerance.rounding_mode not in IMPLEMENTED_ROUNDING_MODES:
            raise _refuse(
                ReconciliationRefusalReason.OPERATION_NOT_IMPLEMENTED,
                subject,
                f"the engine rounds by no declared mode {tolerance.rounding_mode}",
            )
        if _within(measured, tolerance, subject):
            return True
    return False


def _warned(measured: Decimal, bands, field_id: str, subject: str):
    for band in bands:
        if field_id in band.field_ids and _within(measured, band, subject):
            return band
    return None


def _calculation_units(
    schema: SchemaDeclaration, canonicalisation, key_fields: tuple[str, ...], excluded: tuple[str, ...], subject: str
) -> dict[str, Decimal]:
    """Return one unit in the last declared place for every compared number.

    The calculation class reads a difference against the last place the case
    declares for that field. A declared number with no declared decimal scale
    has no last place, so the class is refused rather than measured against a
    scale nobody declared.
    """
    units: dict[str, Decimal] = {}
    for field in schema.fields:
        if field.field_id in key_fields or field.field_id in excluded:
            continue
        if field.value_type not in NUMERIC_VALUE_TYPES:
            continue
        scale = field.scale if field.scale is not None else canonicalisation.decimal_scale
        if scale is None:
            raise _refuse(
                ReconciliationRefusalReason.DECLARATION_MISSING,
                subject,
                f"the comparison declares the calculation dimension and field {field.field_id} declares no decimal scale",
            )
        units[field.field_id] = Decimal(1).scaleb(-int(scale))
    return units


def _compare_values(
    pairs,
    *,
    fields: tuple[str, ...],
    tolerances,
    bands,
    calculation_units: Mapping[str, Decimal] | None,
    clause_id: str,
    output_id: str,
    subject: str,
):
    """Compare declared fields of matched rows against the declared policy."""
    findings: list[Finding] = []
    for key, approved_row, seen_row in pairs:
        for field_id in fields:
            approved = approved_row.values.get(field_id)
            seen = seen_row.values.get(field_id)
            measured = None
            approved_number = _numeric(approved)
            seen_number = _numeric(seen)
            if approved_number is not None and seen_number is not None:
                measured = abs(approved_number - seen_number)
            if approved == seen and _text_form(approved) == _text_form(seen):
                continue
            if measured is not None and _tolerated(measured, tolerances, field_id, subject):
                band = _warned(measured, bands, field_id, subject)
                if band is not None:
                    findings.append(
                        _finding(
                            FindingKind.VALUE_WARNING,
                            clause_id=clause_id,
                            output_id=output_id,
                            locator=field_id,
                            detail="the difference is inside the declared tolerance and inside a declared warning band",
                            severity=FindingSeverity.WARNING,
                            row_digest=seen_row.digest,
                            measured=str(measured),
                        )
                    )
                continue
            rounding_shaped = (
                calculation_units is not None
                and measured is not None
                and field_id in calculation_units
                and measured <= calculation_units[field_id]
            )
            kind = FindingKind.ROUNDING_DIVERGENCE if rounding_shaped else FindingKind.VALUE_DIVERGENCE
            detail = (
                "the difference is at most one unit in the last declared decimal place"
                if rounding_shaped
                else "the observed value differs from the approved value beyond every declared tolerance"
            )
            findings.append(
                _finding(
                    kind,
                    clause_id=clause_id,
                    output_id=output_id,
                    locator=field_id,
                    detail=detail,
                    row_digest=seen_row.digest,
                    measured=None if measured is None else str(measured),
                )
            )
    return findings


def _compare_effective_time(pairs, *, fields: tuple[str, ...], clause_id: str, output_id: str):
    findings: list[Finding] = []
    for key, approved_row, seen_row in pairs:
        for field_id in fields:
            if _text_form(approved_row.values.get(field_id)) != _text_form(seen_row.values.get(field_id)):
                findings.append(
                    _finding(
                        FindingKind.EFFECTIVE_TIME_DIVERGENCE,
                        clause_id=clause_id,
                        output_id=output_id,
                        locator=field_id,
                        detail="the observed row carries a different declared effective time from the approved row",
                        row_digest=seen_row.digest,
                    )
                )
    return findings


def _aggregate_groups(aggregate: AggregateControl, rows: tuple[_Row, ...], canonicalisation, subject: str):
    """Return the declared aggregate for every group present in these rows."""
    grouped: dict[tuple[str | None, ...], list[object]] = {}
    for row in rows:
        if aggregate.input_field_id not in row.values:
            continue
        group = tuple(_text_form(row.values.get(field_id)) for field_id in aggregate.group_by_fields)
        value = row.values[aggregate.input_field_id]
        if value is None:
            if aggregate.null_handling == "reject-null":
                raise _refuse(
                    ReconciliationRefusalReason.OPERATION_NOT_IMPLEMENTED,
                    subject,
                    "the declared aggregate rejects a null and the compared rows carry one",
                )
            continue
        grouped.setdefault(group, []).append(value)
    totals: dict[tuple[str | None, ...], Decimal] = {}
    quantum = Decimal(1).scaleb(-int(canonicalisation.decimal_scale or 0))
    rounding = IMPLEMENTED_ROUNDING_MODES[aggregate.rounding_mode]
    for group, values in grouped.items():
        if aggregate.operation == "count":
            totals[group] = Decimal(len(values))
            continue
        numbers = [_numeric(value) for value in values]
        if any(number is None for number in numbers):
            raise _refuse(
                ReconciliationRefusalReason.OPERATION_NOT_IMPLEMENTED,
                subject,
                "the declared aggregate reads a value that is not a number the engine can total",
            )
        if aggregate.operation == "sum":
            total = sum(numbers, Decimal(0))
        elif aggregate.operation == "minimum":
            total = min(numbers)
        else:
            total = max(numbers)
        totals[group] = total.quantize(quantum, rounding=rounding)
    return totals


def _compare_aggregates(
    aggregates,
    expected_rows,
    actual_rows,
    *,
    canonicalisation,
    tolerances,
    clause_id: str,
    output_id: str,
    subject: str,
):
    findings: list[Finding] = []
    for aggregate in aggregates:
        approved = _aggregate_groups(aggregate, expected_rows, canonicalisation, subject)
        seen = _aggregate_groups(aggregate, actual_rows, canonicalisation, subject)
        for group in sorted(set(approved) | set(seen), key=_key_text):
            locator = f"{aggregate.output_field_id}/{_key_text(group)}"
            if group not in approved or group not in seen:
                findings.append(
                    _finding(
                        FindingKind.AGGREGATE_DIVERGENCE,
                        clause_id=clause_id,
                        output_id=output_id,
                        locator=locator,
                        detail="one side holds a declared aggregate group the other does not",
                    )
                )
                continue
            measured = abs(approved[group] - seen[group])
            if measured == 0 or _tolerated(measured, tolerances, aggregate.output_field_id, subject):
                continue
            findings.append(
                _finding(
                    FindingKind.AGGREGATE_DIVERGENCE,
                    clause_id=clause_id,
                    output_id=output_id,
                    locator=locator,
                    detail="the declared control total differs beyond every declared tolerance",
                    measured=str(measured),
                )
            )
    return findings


def _compare_ordering(ordering: OrderingDeclaration, sides, clause_id: str, output_id: str):
    """Report a declared ordering that leaves distinct rows tied."""
    findings: list[Finding] = []
    fields = tuple(field.field_id for field in ordering.fields) + tuple(ordering.tie_breaker_fields)
    for side, rows in sides:
        tied: dict[tuple[str | None, ...], set[str]] = {}
        for row in rows:
            key = tuple(_text_form(row.values.get(field_id)) for field_id in fields)
            tied.setdefault(key, set()).add(row.payload)
        for key in sorted((key for key, payloads in tied.items() if len(payloads) > 1), key=_key_text):
            findings.append(
                _finding(
                    FindingKind.ORDERING_NONDETERMINISTIC,
                    clause_id=clause_id,
                    output_id=output_id,
                    locator=f"{side}/{_key_text(key)}",
                    detail="the declared ordering and tie-breakers leave distinct rows in an undetermined order",
                    measured=str(len(tied[key])),
                )
            )
    return findings


def _compare_format(expected: ExpectedOutput, observed: ActualOutput, clause_id: str, output_id: str):
    findings: list[Finding] = []
    if expected.format_digest != observed.format_digest:
        findings.append(
            _finding(
                FindingKind.FORMAT_DIVERGENCE,
                clause_id=clause_id,
                output_id=output_id,
                locator="format_digest",
                detail="the observed output declares a different format digest from the approved output",
            )
        )
    if expected.schema.format_name != observed.schema.format_name:
        findings.append(
            _finding(
                FindingKind.FORMAT_DIVERGENCE,
                clause_id=clause_id,
                output_id=output_id,
                locator="schema.format_name",
                detail="the observed output declares a different written format from the approved output",
            )
        )
    if expected.canonicalisation != observed.canonicalisation:
        findings.append(
            _finding(
                FindingKind.FORMAT_DIVERGENCE,
                clause_id=clause_id,
                output_id=output_id,
                locator="canonicalisation",
                detail="the observed output declares a different canonical written form from the approved output",
            )
        )
    return findings


def _compare_replay(replay, observation: CandidateObservation, datasets, clause_id: str, output_id: str):
    findings: list[Finding] = []
    if observation.context != replay.context:
        findings.append(
            _finding(
                FindingKind.REPLAY_METADATA_DIVERGENCE,
                clause_id=clause_id,
                output_id=output_id,
                locator="context",
                detail="the run observed a different execution context from the declared replay context",
            )
        )
    observed = {identity.identifier: identity for identity in observation.observed_inputs}
    for replay_input in replay.inputs:
        if not replay_input.required:
            continue
        seen = observed.get(replay_input.dataset_id)
        if seen is None:
            findings.append(
                _finding(
                    FindingKind.REPLAY_METADATA_DIVERGENCE,
                    clause_id=clause_id,
                    output_id=output_id,
                    locator=f"inputs/{replay_input.dataset_id}",
                    detail="the run observed no metadata for a frozen input the declared replay requires",
                )
            )
            continue
        declared = datasets.get((replay_input.role, replay_input.dataset_id))
        if declared is not None and (seen.version, seen.digest) != (declared.version, declared.content_digest):
            findings.append(
                _finding(
                    FindingKind.REPLAY_METADATA_DIVERGENCE,
                    clause_id=clause_id,
                    output_id=output_id,
                    locator=f"inputs/{replay_input.dataset_id}",
                    detail="the run observed a different version or digest for a frozen input than the case declares",
                )
            )
    if (replay.output_schema, replay.output_grain, replay.canonicalisation) != (
        observation.output.schema,
        observation.output.grain,
        observation.output.canonicalisation,
    ):
        findings.append(
            _finding(
                FindingKind.REPLAY_METADATA_DIVERGENCE,
                clause_id=clause_id,
                output_id=output_id,
                locator="output_shape",
                detail="the observed output shape differs from the shape the declared replay produces",
            )
        )
    return findings


def _confirm(record, material: _Material, rows, subject: str) -> None:
    if material.digest is not None and material.digest != record.content_digest:
        raise _refuse(
            ReconciliationRefusalReason.CONTENT_DIGEST_MISMATCH,
            subject,
            "the supplied rows do not produce the content digest the record declares",
        )
    if record.row_count != len(rows):
        raise _refuse(
            ReconciliationRefusalReason.ROW_COUNT_MISMATCH,
            subject,
            "the supplied rows do not match the row count the record declares",
        )


def _preflight(clause: ParityClause, policy, dimensions, subject: str) -> dict[str, Decimal] | None:
    """Refuse a declared comparison class the engine cannot evaluate.

    The return value is the declared last place of every compared number, which
    the calculation class reads, or nothing when the case declares no
    calculation class.
    """
    unknown = sorted(dimension for dimension in dimensions if dimension not in IMPLEMENTED_DIMENSIONS)
    if unknown:
        raise _refuse(
            ReconciliationRefusalReason.DIMENSION_NOT_IMPLEMENTED,
            subject,
            f"the engine evaluates no declared comparison dimension {unknown[0]}",
        )
    comparison = clause.comparison
    if ComparisonDimension.AGGREGATE in dimensions and not comparison.aggregates:
        raise _refuse(
            ReconciliationRefusalReason.DECLARATION_MISSING,
            subject,
            "the comparison declares the aggregate dimension and declares no aggregate",
        )
    if ComparisonDimension.ORDERING in dimensions and comparison.ordering is None:
        raise _refuse(
            ReconciliationRefusalReason.DECLARATION_MISSING,
            subject,
            "the comparison declares the ordering dimension and declares no ordering",
        )
    if ComparisonDimension.REPLAY_METADATA in dimensions and comparison.replay is None:
        raise _refuse(
            ReconciliationRefusalReason.DECLARATION_MISSING,
            subject,
            "the comparison declares the replay-metadata dimension and declares no replay",
        )
    if ComparisonDimension.EFFECTIVE_TIME in dimensions and not _effective_time_fields(comparison.schema):
        raise _refuse(
            ReconciliationRefusalReason.DECLARATION_MISSING,
            subject,
            "the comparison declares the effective-time dimension and no field declares the effective-date role",
        )
    for aggregate in comparison.aggregates:
        if aggregate.operation not in IMPLEMENTED_AGGREGATE_OPERATIONS:
            raise _refuse(
                ReconciliationRefusalReason.OPERATION_NOT_IMPLEMENTED,
                subject,
                f"the engine computes no declared aggregate operation {aggregate.operation}",
            )
        if aggregate.null_handling not in IMPLEMENTED_NULL_HANDLING:
            raise _refuse(
                ReconciliationRefusalReason.OPERATION_NOT_IMPLEMENTED,
                subject,
                f"the engine applies no declared null handling {aggregate.null_handling}",
            )
        if aggregate.rounding_mode not in IMPLEMENTED_ROUNDING_MODES:
            raise _refuse(
                ReconciliationRefusalReason.OPERATION_NOT_IMPLEMENTED,
                subject,
                f"the engine rounds by no declared mode {aggregate.rounding_mode}",
            )
        field = _field_index(comparison.schema).get(aggregate.input_field_id)
        if aggregate.operation != "count" and (field is None or field.value_type not in NUMERIC_VALUE_TYPES):
            raise _refuse(
                ReconciliationRefusalReason.OPERATION_NOT_IMPLEMENTED,
                subject,
                "the declared aggregate totals a field whose declared type carries no number",
            )
    for declaration in (*policy.tolerances, *policy.warning_bands):
        if clause.clause_id in declaration.clause_ids and declaration.measurement not in IMPLEMENTED_MEASUREMENTS:
            raise _refuse(
                ReconciliationRefusalReason.OPERATION_NOT_IMPLEMENTED,
                subject,
                f"the engine measures no declared difference of kind {declaration.measurement}",
            )
    if ComparisonDimension.CALCULATION not in dimensions:
        return None
    excluded = _effective_time_fields(comparison.schema) if ComparisonDimension.EFFECTIVE_TIME in dimensions else ()
    return _calculation_units(
        comparison.schema, comparison.canonicalisation, comparison.grain.key_fields, excluded, subject
    )


def _oracle_identity(output: ExpectedOutput) -> tuple[object, ...]:
    """Return what identifies one expected output, apart from how it is labelled."""
    return (
        output.output_id,
        output.version,
        output.content_digest,
        output.schema,
        output.grain,
        output.canonicalisation,
        output.row_count,
        output.format_digest,
    )


def _effective_time_fields(schema: SchemaDeclaration) -> tuple[str, ...]:
    return tuple(field.field_id for field in schema.fields if field.semantic_role == EFFECTIVE_TIME_ROLE)


def _uncanonical_digest(reason: UncanonicalReason) -> str:
    """Return the record digest of the closed reason record for one side.

    A side that produced no canonical bytes still has to be cited by a digest,
    and a digest slot may hold nothing a reader could turn back into a value.
    The reason itself is a record: its declared identity names the reason, the
    form it is declared under, and the canonical digest of the reason's own
    words, and the digest of that record is what the reference carries.
    """
    return record_digest(
        Identity(
            identifier=reason.value,
            version=UNCANONICAL_REASON_FORM,
            digest=canonical_digest(reason.value.encode("ascii")),
        )
    )


def _evidence(prefix: str, material: _Material, summary: str) -> EvidenceReference:
    """Return the reference one side of a comparison is cited by.

    A side that produced canonical bytes is cited by their digest, with the
    approved summary of what it holds. A side that produced none is cited by
    the digest of the closed reason record for that, and says the reason in the
    words this module declares for it.
    """
    if material.uncanonical is None:
        return EvidenceReference(
            evidence_id=prefix,
            version=RECONCILIATION_FORM,
            digest=material.digest,
            summary=summary,
        )
    return EvidenceReference(
        evidence_id=prefix,
        version=RECONCILIATION_FORM,
        digest=_uncanonical_digest(material.uncanonical),
        summary=UNCANONICAL_SUMMARY[material.uncanonical],
    )


def reconcile_clause(
    case: VerificationCase,
    clause: ParityClause,
    expected: ExpectedMaterial,
    observation: CandidateObservation,
) -> ClauseReconciliation:
    """Reconcile one parity clause and return its outcome and findings."""
    subject = f"comparison_policy.clauses[{clause.clause_id}]"
    output_id = clause.expected_output_id
    if expected.output.output_id != output_id:
        raise _refuse(
            ReconciliationRefusalReason.UNRESOLVED_EXPECTED_OUTPUT,
            subject,
            "the supplied expected material answers for a different output",
        )
    if observation.output.output_id != output_id:
        raise _refuse(
            ReconciliationRefusalReason.UNRESOLVED_ACTUAL_OUTPUT,
            subject,
            "the supplied observation answers for a different output",
        )
    declared = {output.output_id: output for output in case.expected_outputs}.get(output_id)
    if declared is None:
        raise _refuse(
            ReconciliationRefusalReason.UNRESOLVED_EXPECTED_OUTPUT,
            subject,
            "the case declares no expected output for the clause to compare",
        )
    if _oracle_identity(declared) != _oracle_identity(expected.output):
        # The oracle is the case's, not a caller's. Origin, provenance and
        # approved text label it and are not part of what it identifies.
        raise _refuse(
            ReconciliationRefusalReason.ORACLE_CONTRADICTION,
            subject,
            "the supplied expected material contradicts the expected output the case declares",
        )
    policy = case.comparison_policy
    comparison = clause.comparison
    dimensions = comparison.dimensions
    calculation_units = _preflight(clause, policy, dimensions, subject)

    keys_compared = ComparisonDimension.KEY in dimensions
    cardinality_compared = ComparisonDimension.JOIN_CARDINALITY in dimensions
    ordering = comparison.ordering
    # The oracle must satisfy its own declared grain. Only the observed side
    # can carry a repeated key as a finding.
    expected_material = _material(
        expected.rows,
        schema=expected.output.schema,
        grain=expected.output.grain,
        canonicalisation=expected.output.canonicalisation,
        ordering=ordering,
        repeats_reportable=False,
    )
    actual_material = _material(
        observation.rows,
        schema=observation.output.schema,
        grain=observation.output.grain,
        canonicalisation=observation.output.canonicalisation,
        ordering=ordering,
        repeats_reportable=keys_compared or cardinality_compared,
    )
    _confirm(expected.output, expected_material, expected.rows, f"{subject}.expected_output")
    _confirm(observation.output, actual_material, observation.rows, f"{subject}.actual_output")

    grain = comparison.grain
    canonicalisation = comparison.canonicalisation
    tolerances = _scoped(policy.tolerances, clause.clause_id, ComparisonDimension.VALUE) + _scoped(
        policy.tolerances, clause.clause_id, ComparisonDimension.CALCULATION
    )
    aggregate_tolerances = _scoped(policy.tolerances, clause.clause_id, ComparisonDimension.AGGREGATE)
    bands = _scoped(policy.warning_bands, clause.clause_id, ComparisonDimension.VALUE)
    effective_fields = _effective_time_fields(comparison.schema)
    compared_fields = tuple(
        field_id
        for field_id in sorted(set(expected_material.index) & set(actual_material.index))
        if field_id not in grain.key_fields
        and not (ComparisonDimension.EFFECTIVE_TIME in dimensions and field_id in effective_fields)
    )

    findings: list[Finding] = []
    if ComparisonDimension.SCHEMA in dimensions:
        findings.extend(_compare_schema(comparison.schema, observation.output.schema, clause.clause_id, output_id))
    if keys_compared:
        findings.extend(_compare_keys(grain, observation.output.grain, actual_material, clause.clause_id, output_id))
    if ComparisonDimension.POPULATION in dimensions:
        expected_keyed, _ = _by_key(
            _retained(expected_material.rows, policy.exclusions, clause.clause_id, ComparisonDimension.POPULATION, subject),
            grain,
        )
        actual_keyed, unkeyed = _by_key(
            _retained(actual_material.rows, policy.exclusions, clause.clause_id, ComparisonDimension.POPULATION, subject),
            grain,
        )
        findings.extend(_compare_population(expected_keyed, actual_keyed, unkeyed, clause.clause_id, output_id))
    if cardinality_compared:
        expected_keyed, _ = _by_key(
            _retained(
                expected_material.rows, policy.exclusions, clause.clause_id, ComparisonDimension.JOIN_CARDINALITY, subject
            ),
            grain,
        )
        actual_keyed, _ = _by_key(
            _retained(
                actual_material.rows, policy.exclusions, clause.clause_id, ComparisonDimension.JOIN_CARDINALITY, subject
            ),
            grain,
        )
        findings.extend(_compare_cardinality(expected_keyed, actual_keyed, clause.clause_id, output_id))
    value_compared = ComparisonDimension.VALUE in dimensions or ComparisonDimension.CALCULATION in dimensions
    if value_compared or ComparisonDimension.EFFECTIVE_TIME in dimensions:
        expected_keyed, _ = _by_key(
            _retained(expected_material.rows, policy.exclusions, clause.clause_id, ComparisonDimension.VALUE, subject),
            grain,
        )
        actual_keyed, _ = _by_key(
            _retained(actual_material.rows, policy.exclusions, clause.clause_id, ComparisonDimension.VALUE, subject),
            grain,
        )
        pairs = [
            (key, expected_keyed[key][0], actual_keyed[key][0])
            for key in sorted(set(expected_keyed) & set(actual_keyed), key=_key_text)
            if len(expected_keyed[key]) == 1 and len(actual_keyed[key]) == 1
        ]
        if value_compared:
            findings.extend(
                _compare_values(
                    pairs,
                    fields=compared_fields,
                    tolerances=tolerances,
                    bands=bands,
                    calculation_units=calculation_units,
                    clause_id=clause.clause_id,
                    output_id=output_id,
                    subject=subject,
                )
            )
        if ComparisonDimension.EFFECTIVE_TIME in dimensions:
            findings.extend(
                _compare_effective_time(pairs, fields=effective_fields, clause_id=clause.clause_id, output_id=output_id)
            )
    if ComparisonDimension.AGGREGATE in dimensions:
        findings.extend(
            _compare_aggregates(
                comparison.aggregates,
                _retained(
                    expected_material.rows, policy.exclusions, clause.clause_id, ComparisonDimension.AGGREGATE, subject
                ),
                _retained(
                    actual_material.rows, policy.exclusions, clause.clause_id, ComparisonDimension.AGGREGATE, subject
                ),
                canonicalisation=canonicalisation,
                tolerances=aggregate_tolerances,
                clause_id=clause.clause_id,
                output_id=output_id,
                subject=subject,
            )
        )
    if ComparisonDimension.ORDERING in dimensions:
        findings.extend(
            _compare_ordering(
                ordering,
                (("expected", expected_material.rows), ("observed", actual_material.rows)),
                clause.clause_id,
                output_id,
            )
        )
    if ComparisonDimension.OUTPUT_FORMAT in dimensions:
        findings.extend(_compare_format(expected.output, observation.output, clause.clause_id, output_id))
    if ComparisonDimension.REPLAY_METADATA in dimensions:
        datasets = {(dataset.role, dataset.dataset_id): dataset for dataset in case.frozen_datasets}
        findings.extend(
            _compare_replay(comparison.replay, observation, datasets, clause.clause_id, output_id)
        )

    ordered = tuple(
        sorted(findings, key=lambda finding: (finding.dimension.value, finding.kind.value, finding.locator))
    )
    failed = any(finding.severity is FindingSeverity.FAILING for finding in ordered)
    outcome = ClauseOutcome(
        outcome_id=f"{case.case_id}/{clause.clause_id}",
        version=RECONCILIATION_FORM,
        clause=Identity(clause.clause_id, clause.version, record_digest(clause)),
        family=ClauseFamily.PARITY,
        status=VerificationStatus.FAIL if failed else VerificationStatus.PASS,
        compared_dimensions=dimensions,
        expected_evidence=(
            _evidence(f"{clause.clause_id}/expected", expected_material, expected.output.approved_summary),
        ),
        observed_evidence=(
            _evidence(f"{clause.clause_id}/observed", actual_material, observation.output.approved_summary),
        ),
    )
    return ClauseReconciliation(clause.clause_id, output_id, outcome, ordered)


def parity_clauses(case: VerificationCase) -> tuple[ParityClause, ...]:
    """Return the parity clauses of a case, in declared order."""
    return tuple(clause for clause in case.comparison_policy.clauses if isinstance(clause, ParityClause))


def reconcile_case(
    case: VerificationCase,
    *,
    expected_material: Mapping[str, ExpectedMaterial],
    observations: Mapping[str, CandidateObservation],
) -> ReconciliationReport:
    """Reconcile every parity clause of a case.

    Clauses of the other declared families are not reconciled here. They are
    executed by the delivery-contract engine, which composes these outcomes
    rather than repeating them.
    """
    reconciled: list[ClauseReconciliation] = []
    for clause in parity_clauses(case):
        subject = f"comparison_policy.clauses[{clause.clause_id}]"
        expected = expected_material.get(clause.expected_output_id)
        if expected is None:
            raise _refuse(
                ReconciliationRefusalReason.UNRESOLVED_EXPECTED_OUTPUT,
                subject,
                "no expected material was supplied for the output the clause names",
            )
        observation = observations.get(clause.expected_output_id)
        if observation is None:
            raise _refuse(
                ReconciliationRefusalReason.UNRESOLVED_ACTUAL_OUTPUT,
                subject,
                "no candidate observation was supplied for the output the clause names",
            )
        reconciled.append(reconcile_clause(case, clause, expected, observation))
    return ReconciliationReport(tuple(reconciled))


def derive_expected_output(
    case: VerificationCase,
    derivation: RuleDerivation,
    source_rows: Sequence[Mapping[str, object]],
    *,
    ordering: OrderingDeclaration | None = None,
) -> DerivedExpectedOutput:
    """Execute a declared rule over one frozen input and return the expected output.

    The rule selects the rows of the declared frozen input that satisfy every
    declared constraint. The derived output keeps the input's declared shape,
    carries the rule-derivation origin and derived provenance, and takes its
    digests from the deterministic core. An operator the engine does not
    execute is refused; nothing is guessed.
    """
    subject = f"frozen_datasets[{derivation.source_dataset_id}]"
    datasets = {(dataset.role, dataset.dataset_id): dataset for dataset in case.frozen_datasets}
    dataset = datasets.get((derivation.source_role, derivation.source_dataset_id))
    if dataset is None:
        raise _refuse(
            ReconciliationRefusalReason.RULE_SOURCE_UNRESOLVED,
            subject,
            "the derivation names a frozen input the case does not declare",
        )
    declared = {output.output_id: output for output in case.expected_outputs}.get(derivation.output_id)
    if declared is not None and declared.origin is not RULE_DERIVED_ORIGIN:
        raise _refuse(
            ReconciliationRefusalReason.ORIGIN_CONTRADICTION,
            f"expected_outputs[{derivation.output_id}]",
            "the case declares another origin for the output this derivation would produce",
        )
    material = _material(
        source_rows,
        schema=dataset.schema,
        grain=dataset.grain,
        canonicalisation=dataset.canonicalisation,
        ordering=None,
        repeats_reportable=False,
    )
    if material.digest != dataset.content_digest:
        raise _refuse(
            ReconciliationRefusalReason.CONTENT_DIGEST_MISMATCH,
            subject,
            "the supplied input rows do not produce the content digest the frozen input declares",
        )
    rule_subject = f"rule[{derivation.rule.rule_id}]"
    # Each supplied row is read through its own canonical bytes, so the rule
    # sees the declared value and never the caller's raw one. The kept rows are
    # returned in canonical order, so a caller's row order reaches nothing.
    paired = [
        (
            _material(
                [source_row],
                schema=dataset.schema,
                grain=dataset.grain,
                canonicalisation=dataset.canonicalisation,
                ordering=None,
                repeats_reportable=False,
            ).rows[0],
            source_row,
        )
        for source_row in source_rows
    ]
    selected = tuple(
        dict(source_row)
        for _, source_row in sorted(
            (pair for pair in paired if _rule_holds(derivation.rule.constraints, pair[0], rule_subject)),
            key=lambda pair: pair[0].payload,
        )
    )
    digest = canonical_digest(
        canonical_row_stream(
            selected,
            schema=dataset.schema,
            grain=dataset.grain,
            canonicalisation=dataset.canonicalisation,
            ordering=ordering,
        )
    )
    if declared is not None and declared.content_digest != digest:
        raise _refuse(
            ReconciliationRefusalReason.CONTENT_DIGEST_MISMATCH,
            f"expected_outputs[{derivation.output_id}]",
            "the declared expected output does not carry the digest the declared rule produces",
        )
    output = ExpectedOutput(
        output_id=derivation.output_id,
        version=derivation.rule.version,
        origin=RULE_DERIVED_ORIGIN,
        provenance=RULE_DERIVED_PROVENANCE,
        content_digest=digest,
        schema=dataset.schema,
        grain=dataset.grain,
        canonicalisation=dataset.canonicalisation,
        row_count=len(selected),
        format_digest=record_digest(dataset.schema),
        approved_summary=(
            f"expected output derived by rule {derivation.rule.rule_id} at {derivation.rule.version} "
            f"over frozen input {dataset.dataset_id}"
        ),
    )
    return DerivedExpectedOutput(
        output=output,
        rows=selected,
        rule=Identity(derivation.rule.rule_id, derivation.rule.version, record_digest(derivation.rule)),
    )


__all__ = [
    "CandidateObservation",
    "ClauseReconciliation",
    "DerivedExpectedOutput",
    "EFFECTIVE_TIME_ROLE",
    "ExpectedMaterial",
    "FINDING_DIMENSION",
    "Finding",
    "FindingKind",
    "FindingSeverity",
    "IMPLEMENTED_AGGREGATE_OPERATIONS",
    "IMPLEMENTED_DIMENSIONS",
    "IMPLEMENTED_MEASUREMENTS",
    "IMPLEMENTED_NULL_HANDLING",
    "IMPLEMENTED_ROUNDING_MODES",
    "IMPLEMENTED_RULE_OPERATORS",
    "RECONCILIATION_FORM",
    "RULE_DERIVED_ORIGIN",
    "RULE_DERIVED_PROVENANCE",
    "UNCANONICAL_REASON_FORM",
    "UNCANONICAL_SUMMARY",
    "ReconciliationRefusalReason",
    "ReconciliationRefused",
    "ReconciliationReport",
    "RuleDerivation",
    "UncanonicalReason",
    "derive_expected_output",
    "parity_clauses",
    "reconcile_case",
    "reconcile_clause",
]
