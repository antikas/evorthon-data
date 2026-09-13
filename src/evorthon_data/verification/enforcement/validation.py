"""Central, deterministic fail-closed enforcement for verification cases."""
from __future__ import annotations

# evorthon-component: verification_enforcement

import types
from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Union, get_args, get_origin, get_type_hints

from evorthon_data.verification.domain.contracts import (
    ActualOutput,
    AdviserConfidence,
    AggregateControl,
    AssuranceDeclaration,
    AssuranceLevel,
    CandidateIdentity,
    CanonicalisationDeclaration,
    Checkpoint,
    CLAUSE_TYPE_BY_FAMILY,
    ClauseFamily,
    ClauseOutcome,
    ComparisonDeclaration,
    ComparisonDimension,
    ComparisonPolicy,
    ConformanceClause,
    ContextIdentity,
    DatasetProvenance,
    DatasetRole,
    DeliveryIntegrityClause,
    DiagnosticLocalisation,
    DiagnosticStrength,
    DisclosureDecision,
    DOMAIN_RECORD_TYPES,
    EnvironmentCertificateClaim,
    EvidenceProvenance,
    EvidenceReference,
    ExpectedOutput,
    ExpectedOutputOrigin,
    ExclusionDeclaration,
    FaultClass,
    FaultRecord,
    FrozenDataset,
    GrainDeclaration,
    Identity,
    IndependentlyDerivedReceipt,
    InvariantClause,
    LineageDefinition,
    LineageFrontier,
    LocalisationStatus,
    NullPlacement,
    OperationalEvidenceClause,
    OrderingDeclaration,
    OrderingField,
    OutputLineageBinding,
    OwnerPresentedEvidence,
    ParityClause,
    ReceiptSubject,
    RemediationAdvice,
    RemediationDecision,
    RemediationDisposition,
    RepeatRunIdentity,
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
    UncoveredPath,
    UncoveredPathReason,
    VerificationCase,
    VerificationMode,
    VerificationResult,
    VerificationStatus,
    WarningBandDeclaration,
)


@dataclass(frozen=True)
class ValidationIssue:
    """One deterministic reason a case cannot enter a verification workflow."""

    code: str
    path: str
    message: str


@dataclass(frozen=True)
class ValidationReport:
    """A complete validation result; consumers call ``require_valid`` to proceed.

    ``evidence_provenance`` labels how a case's declared evidence reads as a
    whole.  It is absent for a record that is not a case, and it never decides
    whether a case may proceed.
    """

    issues: tuple[ValidationIssue, ...]
    evidence_provenance: EvidenceProvenance | None = None

    @property
    def valid(self) -> bool:
        return not self.issues

    def require_valid(self) -> None:
        if self.issues:
            raise VerificationContractError(self.issues)


class VerificationContractError(ValueError):
    """Raised when a case violates the portable fail-closed contract."""

    def __init__(self, issues: tuple[ValidationIssue, ...]):
        self.issues = issues
        detail = "; ".join(f"{issue.code} at {issue.path}: {issue.message}" for issue in issues)
        super().__init__(detail)


@dataclass(frozen=True)
class PolicyObservation:
    """The immutable identity and complete policy snapshot observed before execution."""

    case_id: str
    case_version: str
    policy_id: str
    policy_version: str
    policy_digest: str
    policy_snapshot: ComparisonPolicy


class PolicyChangedAfterObservationError(ValueError):
    """Raised if a case's declared policy changes after its facts are observed."""


def _issue(issues: list[ValidationIssue], code: str, path: str, message: str) -> None:
    issues.append(ValidationIssue(code=code, path=path, message=message))


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_identity(identity: object, issues: list[ValidationIssue], path: str, code: str, description: str) -> None:
    if not isinstance(identity, Identity) or not all(
        _nonempty(value) for value in (identity.identifier, identity.version, identity.digest)
    ):
        _issue(issues, code, path, f"{description} identity, version, and digest must be non-empty")


def _validate_context_identity(context: object, issues: list[ValidationIssue], path: str, code: str, description: str) -> None:
    if not isinstance(context, ContextIdentity) or not all(
        _nonempty(value)
        for value in (
            context.context_id,
            context.version,
            context.digest,
            context.logical_run_time,
            context.cutoff_time,
            context.timezone,
        )
    ):
        _issue(issues, code, path, f"{description} identity facts must be complete")


def _validate_candidate_identity(candidate: object, issues: list[ValidationIssue], path: str) -> None:
    if not isinstance(candidate, CandidateIdentity) or not all(
        _nonempty(value) for value in (candidate.candidate_id, candidate.version, candidate.artifact_digest)
    ):
        _issue(issues, "invalid-candidate-identity", path, "candidate identity, version, and artefact digest are required")


def _validate_repeat_run_identity(repeat: object, issues: list[ValidationIssue], path: str) -> None:
    if not isinstance(repeat, RepeatRunIdentity) or not all(
        _nonempty(value) for value in (repeat.repeat_run_id, repeat.version, repeat.digest)
    ):
        _issue(issues, "invalid-repeat-run-identity", path, "repeat-run identity, version, and digest are required")


def _unique(values: tuple[object, ...] | list[object]) -> bool:
    try:
        return len(values) == len(set(values))
    except TypeError:
        return False


def _validate_evidence(
    evidence: tuple[EvidenceReference, ...], issues: list[ValidationIssue], path: str, *, required: bool = True
) -> None:
    if required and not evidence:
        _issue(issues, "missing-evidence", path, "at least one evidence reference is required")
        return
    identifiers: list[str] = []
    for index, item in enumerate(evidence):
        item_path = f"{path}[{index}]"
        if not isinstance(item, EvidenceReference):
            _issue(issues, "invalid-evidence", item_path, "must be an EvidenceReference")
            continue
        if not all(_nonempty(value) for value in (item.evidence_id, item.version, item.digest, item.summary)):
            _issue(issues, "invalid-evidence", item_path, "identity, digest, version, and summary must be non-empty")
        identifiers.append(item.evidence_id)
    if not _unique(identifiers):
        _issue(issues, "ambiguous-evidence", path, "evidence identifiers must be unique within their declared scope")


def _validate_schema_field(field: object, issues: list[ValidationIssue], path: str) -> None:
    if not isinstance(field, SchemaField):
        _issue(issues, "invalid-schema-field", path, "must be a SchemaField")
        return
    if not _nonempty(field.field_id) or not _nonempty(field.semantic_role):
        _issue(issues, "invalid-schema-field", path, "field id and semantic role must be non-empty")
    if not isinstance(field.value_type, SchemaValueType):
        _issue(issues, "invalid-schema-field", path, "field value type is not supported")
    elif field.value_type is SchemaValueType.DECIMAL:
        if (
            type(field.precision) is not int
            or type(field.scale) is not int
            or field.precision <= 0
            or field.scale < 0
            or field.scale > field.precision
        ):
            _issue(issues, "invalid-decimal-field", path, "decimal precision and scale must be bounded and compatible")
    elif field.precision is not None or field.scale is not None:
        _issue(issues, "invalid-schema-field", path, "precision and scale are only permitted for decimal fields")


def _validate_schema(schema: SchemaDeclaration, issues: list[ValidationIssue], path: str) -> set[str]:
    if not isinstance(schema, SchemaDeclaration):
        _issue(issues, "invalid-schema", path, "must be a SchemaDeclaration")
        return set()
    if not all(_nonempty(value) for value in (schema.schema_id, schema.version, schema.format_name)):
        _issue(issues, "invalid-schema", path, "schema identity, version, and format must be non-empty")
    if not schema.fields:
        _issue(issues, "missing-schema-fields", path, "must declare at least one field")
        return set()
    field_ids: list[str] = []
    for index, field in enumerate(schema.fields):
        field_path = f"{path}.fields[{index}]"
        _validate_schema_field(field, issues, field_path)
        if isinstance(field, SchemaField):
            field_ids.append(field.field_id)
    if not _unique(field_ids):
        _issue(issues, "ambiguous-schema", path, "field identifiers must be unique")
    return set(field_ids)


def _validate_grain(grain: GrainDeclaration, field_ids: set[str], issues: list[ValidationIssue], path: str) -> None:
    if not isinstance(grain, GrainDeclaration):
        _issue(issues, "invalid-grain", path, "must be a GrainDeclaration")
        return
    if not all(_nonempty(value) for value in (grain.grain_id, grain.version, grain.population_description)):
        _issue(issues, "invalid-grain", path, "grain identity, version, and population description must be non-empty")
    if not grain.key_fields:
        _issue(issues, "ambiguous-grain", path, "at least one key field is required")
    if not _unique(grain.key_fields):
        _issue(issues, "ambiguous-grain", path, "key fields must not repeat")
    missing = sorted(set(grain.key_fields) - field_ids)
    if missing:
        _issue(issues, "ambiguous-grain", path, f"key fields are absent from the schema: {', '.join(missing)}")


def _validate_canonicalisation(
    declaration: CanonicalisationDeclaration, issues: list[ValidationIssue], path: str
) -> None:
    if not isinstance(declaration, CanonicalisationDeclaration):
        _issue(issues, "invalid-canonicalisation", path, "must be a CanonicalisationDeclaration")
        return
    values = (
        declaration.canonicalisation_id,
        declaration.version,
        declaration.unicode_normalisation,
        declaration.null_representation,
        declaration.signed_zero_representation,
        declaration.non_finite_number_policy,
    )
    if not all(_nonempty(value) for value in values):
        _issue(issues, "invalid-canonicalisation", path, "identity and representation policies must be non-empty")
    if declaration.decimal_scale is not None and (
        type(declaration.decimal_scale) is not int or declaration.decimal_scale < 0
    ):
        _issue(issues, "invalid-canonicalisation", path, "decimal scale must be a non-negative integer")


def _validate_shape(schema: SchemaDeclaration, grain: GrainDeclaration, canonicalisation: CanonicalisationDeclaration, issues: list[ValidationIssue], path: str) -> set[str]:
    field_ids = _validate_schema(schema, issues, f"{path}.schema")
    _validate_grain(grain, field_ids, issues, f"{path}.grain")
    _validate_canonicalisation(canonicalisation, issues, f"{path}.canonicalisation")
    return field_ids


def _validate_synthetic_provenance(provenance: object, issues: list[ValidationIssue], path: str) -> None:
    if not isinstance(provenance, SyntheticProvenance):
        _issue(
            issues,
            "incomplete-synthetic-provenance",
            path,
            "a synthetic dataset must declare its generator, seed, and constraints",
        )
        return
    if not all(
        _nonempty(value)
        for value in (
            provenance.generator_id,
            provenance.generator_version,
            provenance.seed,
            provenance.constraints_digest,
        )
    ):
        _issue(
            issues,
            "incomplete-synthetic-provenance",
            path,
            "generator identity, generator version, seed, and constraints digest must be non-empty",
        )
    for index, constraining in enumerate(provenance.constrained_by):
        _validate_identity(
            constraining,
            issues,
            f"{path}.constrained_by[{index}]",
            "incomplete-synthetic-provenance",
            "constraining dataset",
        )


def _validate_dataset_provenance(dataset: FrozenDataset, issues: list[ValidationIssue], path: str) -> None:
    """Keep a declared provenance and its generator record from contradicting each other.

    Provenance itself never decides whether a dataset may be used; only a
    record that contradicts itself is refused.
    """
    if not isinstance(dataset.provenance, DatasetProvenance):
        _issue(issues, "invalid-dataset-provenance", path, "dataset provenance is not a supported provenance")
    elif dataset.provenance is DatasetProvenance.SYNTHETIC:
        _validate_synthetic_provenance(dataset.synthetic_provenance, issues, f"{path}.synthetic_provenance")
    elif dataset.synthetic_provenance is not None:
        _issue(
            issues,
            "contradictory-dataset-provenance",
            f"{path}.synthetic_provenance",
            f"a dataset declared {dataset.provenance.value} cannot carry a synthetic generator record",
        )


def _validate_frozen_dataset(dataset: object, issues: list[ValidationIssue], path: str) -> None:
    if not isinstance(dataset, FrozenDataset):
        _issue(issues, "invalid-dataset", path, "must be a FrozenDataset")
        return
    if not all(
        _nonempty(value)
        for value in (dataset.dataset_id, dataset.version, dataset.content_digest, dataset.approved_summary)
    ):
        _issue(issues, "invalid-dataset", path, "identity, digest, version, and summary must be non-empty")
    if type(dataset.row_count) is not int or dataset.row_count < 0:
        _issue(issues, "invalid-dataset", path, "row count must be a non-negative integer")
    if not isinstance(dataset.role, DatasetRole):
        _issue(issues, "invalid-dataset-role", path, "dataset role is not a supported role")
    _validate_dataset_provenance(dataset, issues, path)
    _validate_shape(dataset.schema, dataset.grain, dataset.canonicalisation, issues, path)


def _validate_expected_output(output: object, issues: list[ValidationIssue], path: str) -> None:
    if not isinstance(output, ExpectedOutput):
        _issue(issues, "invalid-expected-outcome", path, "must be an ExpectedOutput")
        return
    if not all(
        _nonempty(value)
        for value in (
            output.output_id,
            output.version,
            output.content_digest,
            output.format_digest,
            output.approved_summary,
        )
    ):
        _issue(issues, "invalid-expected-outcome", path, "identity, digest, version, and summary must be non-empty")
    if type(output.row_count) is not int or output.row_count < 0:
        _issue(issues, "invalid-expected-outcome", path, "row count must be a non-negative integer")
    if not isinstance(output.origin, ExpectedOutputOrigin):
        _issue(issues, "invalid-expected-origin", path, "output origin is not supported")
    if not isinstance(output.provenance, DatasetProvenance):
        _issue(issues, "invalid-expected-provenance", path, "output provenance is not a supported provenance")
    _validate_shape(output.schema, output.grain, output.canonicalisation, issues, path)


def _validate_dataset_roles(
    datasets: tuple[FrozenDataset, ...], issues: list[ValidationIssue]
) -> dict[tuple[DatasetRole, str], FrozenDataset]:
    by_identity: dict[tuple[DatasetRole, str], FrozenDataset] = {}
    dataset_ids: set[str] = set()
    if not datasets:
        _issue(issues, "missing-dataset-roles", "frozen_datasets", "at least one input dataset is required")
        return by_identity
    for index, dataset in enumerate(datasets):
        path = f"frozen_datasets[{index}]"
        if not isinstance(dataset, FrozenDataset):
            _issue(issues, "invalid-dataset", path, "must be a FrozenDataset")
            continue
        _validate_frozen_dataset(dataset, issues, path)
        if not isinstance(dataset.role, DatasetRole):
            continue
        else:
            identity = (dataset.role, dataset.dataset_id)
            if dataset.dataset_id in dataset_ids:
                _issue(issues, "duplicate-dataset-identity", path, "dataset identifiers must be unique within a case")
            elif identity in by_identity:
                _issue(issues, "duplicate-dataset-identity", path, "dataset role and identifier must be unique")
            else:
                dataset_ids.add(dataset.dataset_id)
                by_identity[identity] = dataset
    if not any(role is DatasetRole.INPUT for role, _ in by_identity):
        _issue(issues, "missing-dataset-roles", "frozen_datasets", "missing required role: input")
    return by_identity


def _allowed_origins(mode: VerificationMode) -> set[ExpectedOutputOrigin]:
    """Both modes accept a reference implementation and a synthetic derivation."""
    shared = {ExpectedOutputOrigin.REFERENCE_IMPLEMENTATION, ExpectedOutputOrigin.SYNTHETIC_DERIVATION}
    if mode is VerificationMode.MODERNISATION:
        return {ExpectedOutputOrigin.MODERNISATION_CAPTURE, *shared}
    return {ExpectedOutputOrigin.GREENFIELD_SPECIFICATION, *shared}


def _validate_expected_outputs(case: VerificationCase, issues: list[ValidationIssue]) -> dict[str, ExpectedOutput]:
    outputs: dict[str, ExpectedOutput] = {}
    if not case.expected_outputs:
        _issue(issues, "missing-expected-outcomes", "expected_outputs", "at least one frozen expected output is required")
        return outputs
    allowed = _allowed_origins(case.mode) if isinstance(case.mode, VerificationMode) else set()
    for index, output in enumerate(case.expected_outputs):
        path = f"expected_outputs[{index}]"
        if not isinstance(output, ExpectedOutput):
            _issue(issues, "invalid-expected-outcome", path, "must be an ExpectedOutput")
            continue
        _validate_expected_output(output, issues, path)
        if output.output_id in outputs:
            _issue(issues, "duplicate-expected-outcome", path, "output identifiers must be unique")
        else:
            outputs[output.output_id] = output
        if output.origin not in allowed:
            _issue(issues, "invalid-expected-origin", path, "output origin is not permitted for this engagement mode")
    return outputs


def _validate_rule_constraint(constraint: object, issues: list[ValidationIssue], path: str) -> None:
    if not isinstance(constraint, RuleConstraint) or not _nonempty(constraint.field_id):
        _issue(issues, "invalid-rule-constraint", path, "constraint field id is required")
        return
    if not isinstance(constraint.operator, RuleOperator):
        _issue(issues, "invalid-rule-constraint", path, "constraint operator is not supported")
    elif constraint.operator in {RuleOperator.PRESENT, RuleOperator.ABSENT}:
        if constraint.expected_value is not None:
            _issue(issues, "invalid-rule-constraint", path, "presence operators cannot declare an expected value")
    elif not _nonempty(constraint.expected_value):
        _issue(issues, "invalid-rule-constraint", path, "comparison operators require an expected value")


def _validate_rule(rule: RuleDeclaration, issues: list[ValidationIssue], path: str) -> None:
    if not isinstance(rule, RuleDeclaration):
        _issue(issues, "invalid-rule", path, "must be a RuleDeclaration")
        return
    if not _nonempty(rule.rule_id) or not _nonempty(rule.version) or not rule.constraints:
        _issue(issues, "invalid-rule", path, "rule identity and at least one constraint are required")
    for index, constraint in enumerate(rule.constraints):
        _validate_rule_constraint(constraint, issues, f"{path}.constraints[{index}]")


def _validate_aggregate(
    aggregate: object,
    issues: list[ValidationIssue],
    path: str,
    field_ids: set[str] | None = None,
) -> None:
    if not isinstance(aggregate, AggregateControl):
        _issue(issues, "invalid-aggregate", path, "must be an AggregateControl")
        return
    if not all(
        _nonempty(value)
        for value in (
            aggregate.aggregate_id,
            aggregate.version,
            aggregate.operation,
            aggregate.input_field_id,
            aggregate.output_field_id,
            aggregate.null_handling,
            aggregate.rounding_mode,
        )
    ):
        _issue(issues, "invalid-aggregate", path, "aggregate fields must be explicit")
    if not _unique(aggregate.group_by_fields):
        _issue(issues, "invalid-aggregate", path, "aggregate group-by fields must not repeat")
    if field_ids is not None:
        missing = sorted(({aggregate.input_field_id, *aggregate.group_by_fields} - field_ids))
        if missing:
            _issue(issues, "invalid-aggregate", path, f"aggregate fields are absent from comparison schema: {', '.join(missing)}")


def _validate_ordering_field(field: object, issues: list[ValidationIssue], path: str) -> None:
    if not isinstance(field, OrderingField) or not _nonempty(field.field_id):
        _issue(issues, "invalid-ordering", path, "ordering field id is required")
        return
    if not isinstance(field.direction, SortDirection) or not isinstance(field.null_placement, NullPlacement):
        _issue(issues, "invalid-ordering", path, "ordering direction and null placement must be supported values")


def _validate_ordering(
    ordering: OrderingDeclaration | None,
    field_ids: set[str] | None,
    issues: list[ValidationIssue],
    path: str,
) -> None:
    if ordering is None:
        return
    if not all(_nonempty(value) for value in (ordering.ordering_id, ordering.version)) or not ordering.fields:
        _issue(issues, "invalid-ordering", path, "ordering identity and at least one ordering field are required")
        return
    ordering_fields: tuple[str, ...] = tuple(
        field.field_id for field in ordering.fields if isinstance(field, OrderingField)
    )
    for index, field in enumerate(ordering.fields):
        _validate_ordering_field(field, issues, f"{path}.fields[{index}]")
    if not _unique(ordering_fields) or not _unique(ordering.tie_breaker_fields):
        _issue(issues, "ambiguous-ordering", path, "ordering and tie-breaker fields must not repeat")
    if field_ids is not None:
        missing = sorted((set(ordering_fields) | set(ordering.tie_breaker_fields)) - field_ids)
        if missing:
            _issue(issues, "invalid-ordering", path, f"ordering fields are absent from comparison schema: {', '.join(missing)}")
    if ordering.tie_breaker_fields and tuple(ordering_fields[-len(ordering.tie_breaker_fields):]) != ordering.tie_breaker_fields:
        _issue(issues, "ambiguous-ordering", path, "tie-breaker fields must be the final ordering fields")


def _validate_replay_input(replay_input: object, issues: list[ValidationIssue], path: str) -> None:
    if not isinstance(replay_input, ReplayInput) or not _nonempty(replay_input.dataset_id):
        _issue(issues, "invalid-replay-input", path, "replay input dataset identity is required")
        return
    if not isinstance(replay_input.role, DatasetRole):
        _issue(issues, "invalid-replay-input", path, "replay input role is not supported")


def _validate_replay(
    replay: ReplaySpecification | None,
    datasets: dict[tuple[DatasetRole, str], FrozenDataset] | None,
    issues: list[ValidationIssue],
    path: str,
    expected_checkpoint: Checkpoint | None = None,
    expected_context: ContextIdentity | None = None,
) -> None:
    if replay is None:
        return
    if not isinstance(replay, ReplaySpecification):
        _issue(issues, "invalid-replay", path, "must be a ReplaySpecification")
        return
    if not all(_nonempty(value) for value in (replay.replay_id, replay.version, replay.checkpoint_id)):
        _issue(issues, "invalid-replay", path, "replay identity facts must be complete")
    if expected_checkpoint is not None and replay.checkpoint_id != expected_checkpoint.checkpoint_id:
        _issue(issues, "invalid-replay", path, "replay checkpoint id must match its enclosing checkpoint")
    _validate_context_identity(replay.context, issues, f"{path}.context", "invalid-replay", "replay context")
    _validate_identity(replay.transformation, issues, f"{path}.transformation", "invalid-replay", "replay transformation")
    if expected_context is not None and replay.context != expected_context:
        _issue(issues, "invalid-replay", f"{path}.context", "replay context must match the frozen verification context")
    if expected_checkpoint is not None:
        if replay.transformation != expected_checkpoint.transformation:
            _issue(issues, "invalid-replay", f"{path}.transformation", "replay transformation must match its checkpoint")
        if (
            replay.output_schema != expected_checkpoint.schema
            or replay.output_grain != expected_checkpoint.grain
            or replay.canonicalisation != expected_checkpoint.canonicalisation
        ):
            _issue(issues, "invalid-replay", path, "replay output shape must match its checkpoint")
    if not replay.inputs:
        _issue(issues, "invalid-replay", path, "replay must declare at least one frozen input")
    seen_inputs: set[tuple[str, DatasetRole]] = set()
    for index, replay_input in enumerate(replay.inputs):
        input_path = f"{path}.inputs[{index}]"
        _validate_replay_input(replay_input, issues, input_path)
        if not isinstance(replay_input, ReplayInput):
            continue
        marker = (replay_input.dataset_id, replay_input.role)
        if marker in seen_inputs:
            _issue(issues, "ambiguous-replay-input", input_path, "replay input is declared more than once")
        seen_inputs.add(marker)
        dataset = None if datasets is None else datasets.get((replay_input.role, replay_input.dataset_id))
        if datasets is not None and dataset is None and replay_input.required:
            _issue(issues, "unresolved-replay-input", input_path, "replay input must resolve to the matching frozen dataset role and identity")
    _validate_shape(replay.output_schema, replay.output_grain, replay.canonicalisation, issues, path)


def _validate_comparison(
    comparison: ComparisonDeclaration,
    datasets: dict[tuple[DatasetRole, str], FrozenDataset] | None,
    issues: list[ValidationIssue],
    path: str,
    checkpoints: dict[str, Checkpoint] | None = None,
    context: ContextIdentity | None = None,
) -> set[str]:
    if not isinstance(comparison, ComparisonDeclaration):
        _issue(issues, "invalid-comparison", path, "must be a ComparisonDeclaration")
        return set()
    if not all(_nonempty(value) for value in (comparison.comparison_id, comparison.version)):
        _issue(issues, "invalid-comparison", path, "comparison identity and version must be non-empty")
    if not comparison.dimensions or not _unique(comparison.dimensions):
        _issue(issues, "invalid-comparison", path, "comparison dimensions must be non-empty and unique")
    field_ids = _validate_shape(comparison.schema, comparison.grain, comparison.canonicalisation, issues, path)
    aggregate_ids: set[str] = set()
    for index, aggregate in enumerate(comparison.aggregates):
        aggregate_path = f"{path}.aggregates[{index}]"
        _validate_aggregate(aggregate, issues, aggregate_path, field_ids)
        if not isinstance(aggregate, AggregateControl):
            continue
        if aggregate.aggregate_id in aggregate_ids:
            _issue(issues, "duplicate-aggregate", aggregate_path, "aggregate identifiers must be unique")
        aggregate_ids.add(aggregate.aggregate_id)
    _validate_ordering(comparison.ordering, field_ids, issues, f"{path}.ordering")
    replay_checkpoint = None
    if comparison.replay is not None and checkpoints is not None:
        replay_checkpoint = checkpoints.get(comparison.replay.checkpoint_id)
        if replay_checkpoint is None:
            _issue(
                issues,
                "unresolved-replay-checkpoint",
                f"{path}.replay.checkpoint_id",
                "comparison replay must resolve to a declared lineage checkpoint",
            )
    _validate_replay(
        comparison.replay,
        datasets,
        issues,
        f"{path}.replay",
        replay_checkpoint,
        context,
    )
    return field_ids | {
        aggregate.output_field_id for aggregate in comparison.aggregates if isinstance(aggregate, AggregateControl)
    }


def _validate_clauses(
    policy: ComparisonPolicy,
    outputs: dict[str, ExpectedOutput] | None,
    datasets: dict[tuple[DatasetRole, str], FrozenDataset] | None,
    issues: list[ValidationIssue],
    checkpoints: dict[str, Checkpoint] | None = None,
    context: ContextIdentity | None = None,
) -> dict[str, ParityClause]:
    parity: dict[str, ParityClause] = {}
    seen: set[str] = set()
    if not policy.clauses:
        _issue(issues, "missing-comparison-clauses", "comparison_policy.clauses", "at least one comparison clause is required")
        return parity
    for index, clause in enumerate(policy.clauses):
        path = f"comparison_policy.clauses[{index}]"
        clause_id = getattr(clause, "clause_id", None)
        if not _nonempty(clause_id):
            _issue(issues, "invalid-comparison-clause", path, "clause id is required")
            continue
        if clause_id in seen:
            _issue(issues, "duplicate-comparison-clause", path, "clause identifiers must be unique")
        seen.add(clause_id)
        family = next((candidate for candidate, clause_type in CLAUSE_TYPE_BY_FAMILY.items() if isinstance(clause, clause_type)), None)
        if family is None:
            _issue(issues, "invalid-comparison-clause", path, "clause is not one of the supported family contracts")
            continue
        if not _nonempty(clause.version):
            _issue(issues, "invalid-comparison-clause", path, "clause version is required")
        _validate_evidence(clause.required_evidence, issues, f"{path}.required_evidence")
        if isinstance(clause, ParityClause):
            expected_output = None if outputs is None else outputs.get(clause.expected_output_id)
            if outputs is not None and expected_output is None:
                _issue(issues, "unresolved-expected-outcome", path, "parity clause must resolve a declared expected output")
            _validate_comparison(
                clause.comparison,
                datasets,
                issues,
                f"{path}.comparison",
                checkpoints,
                context,
            )
            if expected_output is not None and (
                clause.comparison.schema != expected_output.schema
                or clause.comparison.grain != expected_output.grain
                or clause.comparison.canonicalisation != expected_output.canonicalisation
            ):
                _issue(
                    issues,
                    "oracle-shape-divergence",
                    f"{path}.comparison",
                    "parity comparison schema, grain, and canonicalisation must match the frozen expected output",
                )
            parity[clause_id] = clause
        else:
            if isinstance(clause, ConformanceClause):
                _validate_identity(clause.contract, issues, f"{path}.contract", "invalid-clause-target", "contract")
            elif isinstance(clause, InvariantClause):
                _validate_identity(clause.invariant, issues, f"{path}.invariant", "invalid-clause-target", "invariant")
            elif isinstance(clause, OperationalEvidenceClause):
                _validate_identity(
                    clause.operational_signal,
                    issues,
                    f"{path}.operational_signal",
                    "invalid-clause-target",
                    "operational signal",
                )
            elif isinstance(clause, DeliveryIntegrityClause):
                _validate_identity(
                    clause.delivery_artifact,
                    issues,
                    f"{path}.delivery_artifact",
                    "invalid-clause-target",
                    "delivery artifact",
                )
            _validate_rule(clause.requirement, issues, f"{path}.requirement")
    if outputs is not None:
        uncovered = sorted(set(outputs) - {clause.expected_output_id for clause in parity.values()})
        if uncovered:
            _issue(issues, "uncompared-expected-outcome", "comparison_policy.clauses", f"expected outputs lack a parity clause: {', '.join(uncovered)}")
    return parity


def _parse_bound(value: str | None, path: str, issues: list[ValidationIssue]) -> Decimal | None:
    if not _nonempty(value):
        _issue(issues, "invalid-policy-bound", path, "both explicit bounds are required")
        return None
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError):
        _issue(issues, "invalid-policy-bound", path, "bound must be a decimal string")
        return None
    if not parsed.is_finite():
        _issue(issues, "invalid-policy-bound", path, "bound must be a finite decimal")
        return None
    return parsed


def _validate_policy_scope(
    declaration: ToleranceDeclaration | ExclusionDeclaration | WarningBandDeclaration,
    parity: dict[str, ParityClause] | None,
    issues: list[ValidationIssue],
    path: str,
) -> set[str] | None:
    clause_ids = declaration.clause_ids
    if not clause_ids or not _unique(clause_ids):
        _issue(issues, "invalid-policy-scope", path, "policy scope must contain unique clause identifiers")
    if not all(_nonempty(clause_id) for clause_id in clause_ids):
        _issue(issues, "invalid-policy-scope", path, "policy clause identifiers must be non-empty")
    if not declaration.dimensions or not _unique(declaration.dimensions) or not all(
        isinstance(dimension, ComparisonDimension) for dimension in declaration.dimensions
    ):
        _issue(issues, "invalid-policy-scope", path, "policy dimensions must be non-empty, unique supported values")
    if parity is None:
        return None
    missing = sorted(set(clause_ids) - set(parity))
    if missing:
        _issue(issues, "invalid-policy-scope", path, f"policy declarations may target only declared parity clauses: {', '.join(missing)}")
    available: set[str] | None = None
    for clause_id in clause_ids:
        clause = parity.get(clause_id)
        if clause is not None:
            clause_fields = {field.field_id for field in clause.comparison.schema.fields}
            clause_fields.update(aggregate.output_field_id for aggregate in clause.comparison.aggregates)
            available = clause_fields if available is None else available & clause_fields
    for clause_id in clause_ids:
        clause = parity.get(clause_id)
        if clause is not None and not set(declaration.dimensions).issubset(set(clause.comparison.dimensions)):
            _issue(issues, "invalid-policy-scope", path, "policy dimensions must be covered by each target comparison")
    return available or set()


def _validate_tolerances(
    tolerances: tuple[ToleranceDeclaration, ...],
    parity: dict[str, ParityClause] | None,
    issues: list[ValidationIssue],
    base_path: str = "comparison_policy.tolerances",
) -> None:
    seen: set[str] = set()
    for index, tolerance in enumerate(tolerances):
        path = f"{base_path}[{index}]"
        if tolerance.tolerance_id in seen:
            _issue(issues, "duplicate-tolerance", path, "tolerance identifiers must be unique")
        seen.add(tolerance.tolerance_id)
        available = _validate_policy_scope(tolerance, parity, issues, path)
        if not all(_nonempty(value) for value in (tolerance.tolerance_id, tolerance.version, tolerance.measurement, tolerance.unit, tolerance.rounding_mode)):
            _issue(issues, "invalid-tolerance", path, "tolerance identity, measurement, unit, and rounding mode are required")
        if (
            not tolerance.field_ids
            or not _unique(tolerance.field_ids)
            or not all(_nonempty(field_id) for field_id in tolerance.field_ids)
            or (available is not None and not set(tolerance.field_ids).issubset(available))
        ):
            _issue(issues, "invalid-tolerance", path, "tolerance fields must be unique declared comparison or aggregate fields")
        lower = _parse_bound(tolerance.lower_bound, f"{path}.lower_bound", issues)
        upper = _parse_bound(tolerance.upper_bound, f"{path}.upper_bound", issues)
        if lower is not None and upper is not None and lower > upper:
            _issue(issues, "invalid-tolerance", path, "lower bound cannot exceed upper bound")


def _validate_exclusions(
    exclusions: tuple[ExclusionDeclaration, ...],
    parity: dict[str, ParityClause] | None,
    issues: list[ValidationIssue],
    base_path: str = "comparison_policy.exclusions",
) -> None:
    seen: set[str] = set()
    for index, exclusion in enumerate(exclusions):
        path = f"{base_path}[{index}]"
        if exclusion.exclusion_id in seen:
            _issue(issues, "duplicate-exclusion", path, "exclusion identifiers must be unique")
        seen.add(exclusion.exclusion_id)
        available = _validate_policy_scope(exclusion, parity, issues, path)
        if not all(_nonempty(value) for value in (exclusion.exclusion_id, exclusion.version, exclusion.rationale)) or not exclusion.selector:
            _issue(issues, "invalid-exclusion", path, "exclusion identity, rationale, and selector are required")
        for selector_index, constraint in enumerate(exclusion.selector):
            selector_path = f"{path}.selector[{selector_index}]"
            _validate_rule(RuleDeclaration("selector", "v1", (constraint,)), issues, selector_path)
            if available is not None and isinstance(constraint, RuleConstraint) and constraint.field_id not in available:
                _issue(
                    issues,
                    "unresolved-exclusion-field",
                    f"{selector_path}.field_id",
                    "exclusion selector fields must resolve to a declared target comparison field",
                )


def _validate_warning_bands(
    warnings: tuple[WarningBandDeclaration, ...],
    parity: dict[str, ParityClause] | None,
    issues: list[ValidationIssue],
    base_path: str = "comparison_policy.warning_bands",
) -> None:
    seen: set[str] = set()
    for index, warning in enumerate(warnings):
        path = f"{base_path}[{index}]"
        if warning.warning_id in seen:
            _issue(issues, "duplicate-warning-band", path, "warning identifiers must be unique")
        seen.add(warning.warning_id)
        available = _validate_policy_scope(warning, parity, issues, path)
        if not all(_nonempty(value) for value in (warning.warning_id, warning.version, warning.measurement, warning.unit)):
            _issue(issues, "invalid-warning-band", path, "warning identity, measurement, and unit are required")
        if (
            not warning.field_ids
            or not _unique(warning.field_ids)
            or not all(_nonempty(field_id) for field_id in warning.field_ids)
            or (available is not None and not set(warning.field_ids).issubset(available))
        ):
            _issue(issues, "invalid-warning-band", path, "warning fields must be unique declared comparison or aggregate fields")
        lower = _parse_bound(warning.lower_bound, f"{path}.lower_bound", issues)
        upper = _parse_bound(warning.upper_bound, f"{path}.upper_bound", issues)
        if lower is not None and upper is not None and lower > upper:
            _issue(issues, "invalid-warning-band", path, "lower bound cannot exceed upper bound")


def _validate_policy(
    policy: ComparisonPolicy,
    outputs: dict[str, ExpectedOutput] | None,
    datasets: dict[tuple[DatasetRole, str], FrozenDataset] | None,
    issues: list[ValidationIssue],
    checkpoints: dict[str, Checkpoint] | None = None,
    context: ContextIdentity | None = None,
) -> dict[str, ParityClause]:
    if not isinstance(policy, ComparisonPolicy):
        _issue(issues, "invalid-comparison-policy", "comparison_policy", "must be a ComparisonPolicy")
        return {}
    if not all(_nonempty(value) for value in (policy.policy_id, policy.version, policy.digest)):
        _issue(issues, "invalid-comparison-policy", "comparison_policy", "policy identity, version, and digest are required")
    parity = _validate_clauses(policy, outputs, datasets, issues, checkpoints, context)
    _validate_tolerances(policy.tolerances, parity, issues)
    _validate_exclusions(policy.exclusions, parity, issues)
    _validate_warning_bands(policy.warning_bands, parity, issues)
    return parity


def _validate_checkpoint(
    checkpoint: object,
    datasets: dict[tuple[DatasetRole, str], FrozenDataset] | None,
    issues: list[ValidationIssue],
    path: str,
    context: ContextIdentity | None = None,
    *,
    evidence_required: bool = True,
) -> None:
    if not isinstance(checkpoint, Checkpoint):
        _issue(issues, "invalid-checkpoint", path, "must be a Checkpoint")
        return
    if not all(_nonempty(value) for value in (checkpoint.checkpoint_id, checkpoint.version)):
        _issue(issues, "invalid-checkpoint", path, "checkpoint identity and version are required")
    if not _unique(checkpoint.parent_ids) or not all(_nonempty(parent_id) for parent_id in checkpoint.parent_ids):
        _issue(issues, "invalid-checkpoint", f"{path}.parent_ids", "checkpoint parent identities must be non-empty and unique")
    if checkpoint.checkpoint_id in checkpoint.parent_ids:
        _issue(issues, "cyclic-lineage", path, "a checkpoint cannot parent itself")
    _validate_identity(checkpoint.expected_state, issues, f"{path}.expected_state", "invalid-checkpoint", "expected state")
    _validate_identity(checkpoint.transformation, issues, f"{path}.transformation", "invalid-checkpoint", "transformation")
    _validate_identity(checkpoint.provenance, issues, f"{path}.provenance", "invalid-checkpoint", "provenance")
    _validate_shape(checkpoint.schema, checkpoint.grain, checkpoint.canonicalisation, issues, path)
    _validate_evidence(
        checkpoint.diagnostic_evidence,
        issues,
        f"{path}.diagnostic_evidence",
        required=evidence_required,
    )
    _validate_replay(checkpoint.replay, datasets, issues, f"{path}.replay", checkpoint, context)


def _validate_output_lineage_binding(binding: object, issues: list[ValidationIssue], path: str) -> None:
    if not isinstance(binding, OutputLineageBinding) or not _nonempty(binding.expected_output_id):
        _issue(issues, "invalid-output-binding", path, "expected output identity is required")
        return
    if binding.terminal_checkpoint_id is not None and not _nonempty(binding.terminal_checkpoint_id):
        _issue(issues, "invalid-output-binding", path, "terminal checkpoint identity must be non-empty when declared")


def _validate_lineage(
    lineage: LineageDefinition,
    outputs: dict[str, ExpectedOutput] | None,
    strength: object | None,
    datasets: dict[tuple[DatasetRole, str], FrozenDataset] | None,
    issues: list[ValidationIssue],
    context: ContextIdentity | None = None,
) -> dict[str, Checkpoint]:
    if not isinstance(lineage, LineageDefinition):
        _issue(issues, "invalid-lineage", "lineage", "must be a LineageDefinition")
        return {}
    if not all(_nonempty(value) for value in (lineage.lineage_id, lineage.version)):
        _issue(issues, "invalid-lineage", "lineage", "lineage identity and version are required")
    checkpoints: dict[str, Checkpoint] = {}
    children: dict[str, set[str]] = {}
    for index, checkpoint in enumerate(lineage.checkpoints):
        path = f"lineage.checkpoints[{index}]"
        if not isinstance(checkpoint, Checkpoint):
            _issue(issues, "invalid-checkpoint", path, "must be a Checkpoint")
            continue
        _validate_checkpoint(
            checkpoint,
            datasets,
            issues,
            path,
            context,
            evidence_required=strength is not DiagnosticStrength.OUTPUT_ONLY,
        )
        if not _nonempty(checkpoint.checkpoint_id):
            continue
        if checkpoint.checkpoint_id in checkpoints:
            _issue(issues, "duplicate-checkpoint", path, "checkpoint identifiers must be unique")
        checkpoints[checkpoint.checkpoint_id] = checkpoint
        children.setdefault(checkpoint.checkpoint_id, set())
    for checkpoint_id, checkpoint in checkpoints.items():
        for parent_id in checkpoint.parent_ids:
            if parent_id not in checkpoints:
                _issue(issues, "unresolved-lineage-parent", f"lineage.checkpoints[{checkpoint_id}]", f"parent {parent_id!r} is not declared")
                continue
            if parent_id == checkpoint_id:
                _issue(issues, "cyclic-lineage", f"lineage.checkpoints[{checkpoint_id}]", "a checkpoint cannot parent itself")
            children.setdefault(parent_id, set()).add(checkpoint_id)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            _issue(issues, "cyclic-lineage", "lineage.checkpoints", "lineage graph contains a cycle")
            return
        if node in visited:
            return
        visiting.add(node)
        for parent in checkpoints[node].parent_ids:
            if parent in checkpoints:
                visit(parent)
        visiting.remove(node)
        visited.add(node)

    for checkpoint_id in checkpoints:
        visit(checkpoint_id)
    for index, binding in enumerate(lineage.output_bindings):
        _validate_output_lineage_binding(binding, issues, f"lineage.output_bindings[{index}]")
    bindings = {
        binding.expected_output_id: binding.terminal_checkpoint_id
        for binding in lineage.output_bindings
        if isinstance(binding, OutputLineageBinding)
    }
    if len(bindings) != len(lineage.output_bindings):
        _issue(issues, "duplicate-output-binding", "lineage.output_bindings", "each expected output has exactly one lineage binding")
    if outputs is not None and set(bindings) != set(outputs):
        missing = sorted(set(outputs) - set(bindings))
        unexpected = sorted(set(bindings) - set(outputs))
        if missing:
            _issue(issues, "missing-output-binding", "lineage.output_bindings", f"missing expected outputs: {', '.join(missing)}")
        if unexpected:
            _issue(issues, "unresolved-output-binding", "lineage.output_bindings", f"unknown expected outputs: {', '.join(unexpected)}")
    if strength is DiagnosticStrength.OUTPUT_ONLY:
        if checkpoints:
            _issue(issues, "invalid-diagnostic-strength", "lineage", "output-only cases cannot declare checkpoints")
        if any(terminal is not None for terminal in bindings.values()):
            _issue(issues, "invalid-diagnostic-strength", "lineage.output_bindings", "output-only cases cannot bind terminal checkpoints")
        return checkpoints
    if strength is not None:
        if not checkpoints:
            _issue(issues, "missing-lineage", "lineage", "checkpointed cases must declare lineage checkpoints")
        if strength is DiagnosticStrength.REPLAYABLE and not any(checkpoint.replay is not None for checkpoint in checkpoints.values()):
            _issue(issues, "missing-replay", "lineage", "replayable cases require at least one declared replay")
        if any(terminal is None for terminal in bindings.values()):
            _issue(issues, "missing-output-terminal", "lineage.output_bindings", "checkpointed cases require a terminal checkpoint for every expected output")
    terminals = {terminal for terminal in bindings.values() if terminal is not None}
    for output_id, terminal in bindings.items():
        if terminal is None:
            continue
        if terminal not in checkpoints:
            _issue(issues, "unresolved-output-binding", "lineage.output_bindings", f"terminal checkpoint {terminal!r} is not declared")
        elif children.get(terminal):
            _issue(issues, "invalid-output-terminal", "lineage.output_bindings", "terminal checkpoints cannot have child checkpoints")
        if outputs is not None and output_id in outputs and terminal in checkpoints:
            expected = outputs[output_id]
            checkpoint = checkpoints[terminal]
            if (
                checkpoint.schema != expected.schema
                or checkpoint.grain != expected.grain
                or checkpoint.canonicalisation != expected.canonicalisation
            ):
                _issue(
                    issues,
                    "terminal-shape-divergence",
                    f"lineage.output_bindings[{output_id}]",
                    "terminal checkpoint schema, grain, and canonicalisation must match the frozen expected output",
                )
    for checkpoint_id in (checkpoints if terminals else ()):
        reachable: set[str] = set()
        stack = [checkpoint_id]
        while stack:
            node = stack.pop()
            if node in reachable:
                continue
            reachable.add(node)
            stack.extend(children.get(node, ()))
        if not (reachable & terminals):
            _issue(issues, "unresolved-lineage", f"lineage.checkpoints[{checkpoint_id}]", "checkpoint does not lead to a declared output terminal")
    return checkpoints


def _validate_owner_presented_evidence(
    presented: object, issues: list[ValidationIssue], path: str
) -> None:
    if not isinstance(presented, OwnerPresentedEvidence):
        _issue(issues, "invalid-owner-evidence", path, "must be OwnerPresentedEvidence")
        return
    if not all(_nonempty(value) for value in (presented.evidence_id, presented.version, presented.digest)):
        _issue(issues, "invalid-owner-evidence", path, "owner evidence identity facts must be complete")
    _validate_identity(
        presented.presented_by,
        issues,
        f"{path}.presented_by",
        "invalid-owner-evidence",
        "owner presenter",
    )
    _validate_evidence((presented.approval_evidence,), issues, f"{path}.approval_evidence")


def _validate_environment_certificate_claim(
    claim: object, issues: list[ValidationIssue], path: str
) -> None:
    if not isinstance(claim, EnvironmentCertificateClaim) or claim.assurance_level is not AssuranceLevel.ENVIRONMENT_CERTIFIED:
        _issue(issues, "invalid-assurance", path, "certificate claims must state environment-certified assurance")
        return
    if not all(_nonempty(value) for value in (claim.claim_id, claim.version, claim.certificate_digest)):
        _issue(issues, "invalid-assurance", path, "certificate claim identity facts must be complete")
    _validate_identity(claim.issued_by, issues, f"{path}.issued_by", "invalid-assurance", "certificate issuer")


def _validate_assurance_declaration(
    assurance: object, issues: list[ValidationIssue], path: str
) -> None:
    if not isinstance(assurance, AssuranceDeclaration):
        _issue(issues, "invalid-assurance", path, "must be an AssuranceDeclaration")
        return
    if not all(_nonempty(value) for value in (assurance.assurance_id, assurance.version)):
        _issue(issues, "invalid-assurance", path, "assurance identity and version are required")
    if not isinstance(assurance.declared_level, AssuranceLevel):
        _issue(issues, "invalid-assurance", f"{path}.declared_level", "assurance level is unsupported")
        return
    owner_evidence = assurance.owner_presented_evidence
    certificate_claims = assurance.environment_certificate_claims
    if assurance.declared_level is AssuranceLevel.DECLARED and (owner_evidence or certificate_claims):
        _issue(issues, "invalid-assurance", path, "declared-only assurance cannot claim owner or environment evidence")
    if assurance.declared_level in {AssuranceLevel.OWNER_PRESENTED, AssuranceLevel.ENVIRONMENT_CERTIFIED} and not owner_evidence:
        _issue(issues, "invalid-assurance", path, "owner-presented assurance requires approved owner evidence")
    if assurance.declared_level is AssuranceLevel.ENVIRONMENT_CERTIFIED and not certificate_claims:
        _issue(issues, "invalid-assurance", path, "environment-certified assurance requires an environment certificate claim")
    for index, presented in enumerate(owner_evidence):
        _validate_owner_presented_evidence(presented, issues, f"{path}.owner_presented_evidence[{index}]")
    for index, claim in enumerate(certificate_claims):
        _validate_environment_certificate_claim(claim, issues, f"{path}.environment_certificate_claims[{index}]")


def _validate_assurance(case: VerificationCase, issues: list[ValidationIssue]) -> None:
    _validate_assurance_declaration(case.assurance, issues, "assurance")


def _validate_receipt(receipt: object, issues: list[ValidationIssue], path: str) -> None:
    if not isinstance(receipt, IndependentlyDerivedReceipt):
        _issue(issues, "invalid-receipt", path, "must be an IndependentlyDerivedReceipt")
        return
    if not all(_nonempty(value) for value in (receipt.receipt_id, receipt.version, receipt.observed_digest)):
        _issue(issues, "invalid-receipt", path, "receipt identity, version, and observed digest are required")
    if not isinstance(receipt.subject, ReceiptSubject):
        _issue(issues, "invalid-receipt", f"{path}.subject", "receipt subject is not supported")
    _validate_identity(receipt.subject_identity, issues, f"{path}.subject_identity", "invalid-receipt", "receipt subject")
    _validate_identity(receipt.derived_by, issues, f"{path}.derived_by", "invalid-receipt", "receipt derivation authority")
    _validate_evidence(receipt.evidence, issues, f"{path}.evidence")


def _validate_actual_output(output: object, issues: list[ValidationIssue], path: str) -> None:
    if not isinstance(output, ActualOutput):
        _issue(issues, "invalid-actual-output", path, "must be an ActualOutput")
        return
    if not all(
        _nonempty(value)
        for value in (
            output.output_id,
            output.version,
            output.content_digest,
            output.format_digest,
            output.approved_summary,
        )
    ):
        _issue(issues, "invalid-actual-output", path, "output identity, digests, version, and summary are required")
    if type(output.row_count) is not int or output.row_count < 0:
        _issue(issues, "invalid-actual-output", f"{path}.row_count", "row count must be a non-negative integer")
    _validate_shape(output.schema, output.grain, output.canonicalisation, issues, path)


def _validate_clause_outcome(outcome: object, issues: list[ValidationIssue], path: str) -> None:
    if not isinstance(outcome, ClauseOutcome):
        _issue(issues, "invalid-clause-outcome", path, "must be a ClauseOutcome")
        return
    if not all(_nonempty(value) for value in (outcome.outcome_id, outcome.version)):
        _issue(issues, "invalid-clause-outcome", path, "outcome identity and version are required")
    _validate_identity(outcome.clause, issues, f"{path}.clause", "invalid-clause-outcome", "clause")
    status_is_supported = isinstance(outcome.status, VerificationStatus)
    if not isinstance(outcome.family, ClauseFamily) or not status_is_supported:
        _issue(issues, "invalid-clause-outcome", path, "clause family and status must be supported values")
    if not outcome.compared_dimensions or not _unique(outcome.compared_dimensions) or not all(
        isinstance(dimension, ComparisonDimension) for dimension in outcome.compared_dimensions
    ):
        _issue(issues, "invalid-clause-outcome", f"{path}.compared_dimensions", "compared dimensions must be non-empty, unique supported values")
    evidence_required = status_is_supported and outcome.status is not VerificationStatus.INSUFFICIENT_EVIDENCE
    _validate_evidence(outcome.expected_evidence, issues, f"{path}.expected_evidence", required=evidence_required)
    _validate_evidence(outcome.observed_evidence, issues, f"{path}.observed_evidence", required=evidence_required)


def _validate_lineage_frontier(frontier: object, issues: list[ValidationIssue], path: str) -> None:
    if not isinstance(frontier, LineageFrontier) or not _nonempty(frontier.checkpoint_id):
        _issue(issues, "invalid-lineage-frontier", path, "checkpoint identity is required")
        return
    _validate_evidence(frontier.evidence, issues, f"{path}.evidence")


def _validate_uncovered_path(uncovered: object, issues: list[ValidationIssue], path: str) -> None:
    if not isinstance(uncovered, UncoveredPath):
        _issue(issues, "invalid-uncovered-path", path, "must be an UncoveredPath")
        return
    if not _nonempty(uncovered.path_id):
        _issue(issues, "invalid-uncovered-path", path, "path identity is required")
    if not uncovered.checkpoint_ids or not _unique(uncovered.checkpoint_ids) or not all(
        _nonempty(checkpoint_id) for checkpoint_id in uncovered.checkpoint_ids
    ):
        _issue(issues, "invalid-uncovered-path", f"{path}.checkpoint_ids", "checkpoint path must be non-empty and unambiguous")
    if not isinstance(uncovered.reason, UncoveredPathReason):
        _issue(issues, "invalid-uncovered-path", f"{path}.reason", "uncovered-path reason is not supported")
    _validate_evidence(uncovered.evidence, issues, f"{path}.evidence")


def _validate_localisation(localisation: object, issues: list[ValidationIssue], path: str) -> None:
    if not isinstance(localisation, DiagnosticLocalisation):
        _issue(issues, "invalid-localisation", path, "must be a DiagnosticLocalisation")
        return
    if not all(_nonempty(value) for value in (localisation.localisation_id, localisation.version)):
        _issue(issues, "invalid-localisation", path, "localisation identity and version are required")
    if not isinstance(localisation.status, LocalisationStatus):
        _issue(issues, "invalid-localisation", f"{path}.status", "localisation status is not supported")
    elif localisation.status is not LocalisationStatus.UNKNOWN and (
        not localisation.lower_frontier or not localisation.upper_frontier
    ):
        _issue(issues, "invalid-localisation", path, "confirmed or inferred localisation requires lower and upper frontiers")
    for name, frontiers in (
        ("lower_frontier", localisation.lower_frontier),
        ("upper_frontier", localisation.upper_frontier),
    ):
        checkpoint_ids: list[str] = []
        for index, frontier in enumerate(frontiers):
            _validate_lineage_frontier(frontier, issues, f"{path}.{name}[{index}]")
            if isinstance(frontier, LineageFrontier):
                checkpoint_ids.append(frontier.checkpoint_id)
        if not _unique(checkpoint_ids):
            _issue(issues, "invalid-localisation", f"{path}.{name}", "frontier checkpoint identities must be unique")
    path_ids: list[str] = []
    for index, uncovered in enumerate(localisation.uncovered_paths):
        _validate_uncovered_path(uncovered, issues, f"{path}.uncovered_paths[{index}]")
        if isinstance(uncovered, UncoveredPath):
            path_ids.append(uncovered.path_id)
    if not _unique(path_ids):
        _issue(issues, "invalid-localisation", f"{path}.uncovered_paths", "uncovered path identities must be unique")
    _validate_evidence(localisation.supporting_evidence, issues, f"{path}.supporting_evidence")


def _validate_verification_result(result: object, issues: list[ValidationIssue], path: str) -> None:
    if not isinstance(result, VerificationResult):
        _issue(issues, "invalid-verification-result", path, "must be a VerificationResult")
        return
    if not all(_nonempty(value) for value in (result.result_id, result.version)):
        _issue(issues, "invalid-verification-result", path, "result identity and version are required")
    _validate_identity(result.case, issues, f"{path}.case", "invalid-verification-result", "verification case")
    _validate_candidate_identity(result.candidate, issues, f"{path}.candidate")
    _validate_context_identity(result.context, issues, f"{path}.context", "invalid-verification-result", "result context")
    complete_result_required = isinstance(result.status, VerificationStatus) and result.status is not VerificationStatus.INSUFFICIENT_EVIDENCE
    if complete_result_required and not result.independent_receipts:
        _issue(issues, "missing-result-evidence", f"{path}.independent_receipts", "independent receipts are required")
    receipt_ids: list[str] = []
    receipt_subjects: set[ReceiptSubject] = set()
    for index, receipt in enumerate(result.independent_receipts):
        _validate_receipt(receipt, issues, f"{path}.independent_receipts[{index}]")
        if isinstance(receipt, IndependentlyDerivedReceipt):
            receipt_ids.append(receipt.receipt_id)
            if isinstance(receipt.subject, ReceiptSubject):
                receipt_subjects.add(receipt.subject)
    if not _unique(receipt_ids):
        _issue(issues, "ambiguous-result-evidence", f"{path}.independent_receipts", "receipt identities must be unique")
    missing_subjects = {ReceiptSubject.INPUT, ReceiptSubject.CONTEXT} - receipt_subjects
    if complete_result_required and missing_subjects:
        _issue(
            issues,
            "missing-result-evidence",
            f"{path}.independent_receipts",
            "input and context receipts are required",
        )
    output_ids: list[str] = []
    for index, output in enumerate(result.actual_outputs):
        _validate_actual_output(output, issues, f"{path}.actual_outputs[{index}]")
        if isinstance(output, ActualOutput):
            output_ids.append(output.output_id)
    if complete_result_required and not output_ids:
        _issue(issues, "missing-actual-output", f"{path}.actual_outputs", "at least one actual output is required")
    elif not _unique(output_ids):
        _issue(issues, "ambiguous-actual-output", f"{path}.actual_outputs", "actual output identities must be unique")
    outcome_ids: list[str] = []
    statuses: list[VerificationStatus] = []
    for index, outcome in enumerate(result.clause_outcomes):
        _validate_clause_outcome(outcome, issues, f"{path}.clause_outcomes[{index}]")
        if isinstance(outcome, ClauseOutcome):
            outcome_ids.append(outcome.outcome_id)
            if isinstance(outcome.status, VerificationStatus):
                statuses.append(outcome.status)
    if not outcome_ids:
        _issue(issues, "missing-clause-outcome", f"{path}.clause_outcomes", "at least one clause outcome is required")
    elif not _unique(outcome_ids):
        _issue(issues, "ambiguous-clause-outcome", f"{path}.clause_outcomes", "clause outcome identities must be unique")
    if not isinstance(result.status, VerificationStatus):
        _issue(issues, "invalid-verification-result", f"{path}.status", "result status is not supported")
    elif result.status is VerificationStatus.PASS and any(status is not VerificationStatus.PASS for status in statuses):
        _issue(issues, "inconsistent-result-status", f"{path}.status", "passing result requires every clause outcome to pass")
    elif result.status is VerificationStatus.FAIL and VerificationStatus.FAIL not in statuses:
        _issue(issues, "inconsistent-result-status", f"{path}.status", "failed result requires at least one failed clause outcome")
    elif result.status is VerificationStatus.INSUFFICIENT_EVIDENCE and (
        VerificationStatus.FAIL in statuses or VerificationStatus.INSUFFICIENT_EVIDENCE not in statuses
    ):
        _issue(issues, "inconsistent-result-status", f"{path}.status", "insufficient-evidence result requires an insufficient clause and no failed clause")
    _validate_evidence(result.evidence, issues, f"{path}.evidence")
    if not isinstance(result.diagnostic_strength, DiagnosticStrength):
        _issue(issues, "invalid-verification-result", f"{path}.diagnostic_strength", "diagnostic strength is not supported")
    _validate_repeat_run_identity(result.repeat_run_identity, issues, f"{path}.repeat_run_identity")


def _validate_fault_record(fault: object, issues: list[ValidationIssue], path: str) -> None:
    if not isinstance(fault, FaultRecord):
        _issue(issues, "invalid-fault-record", path, "must be a FaultRecord")
        return
    if not all(_nonempty(value) for value in (fault.fault_id, fault.version, fault.diagnostic_scope)):
        _issue(issues, "invalid-fault-record", path, "fault identity, version, and diagnostic scope are required")
    _validate_identity(fault.result, issues, f"{path}.result", "invalid-fault-record", "verification result")
    if not fault.affected_clause_outcome_ids or not _unique(fault.affected_clause_outcome_ids) or not all(
        _nonempty(outcome_id) for outcome_id in fault.affected_clause_outcome_ids
    ):
        _issue(issues, "invalid-fault-record", f"{path}.affected_clause_outcome_ids", "affected clause outcomes must be non-empty and unique")
    if not isinstance(fault.fault_class, FaultClass) or not isinstance(fault.disclosure_decision, DisclosureDecision):
        _issue(issues, "invalid-fault-record", path, "fault class and disclosure decision must be supported values")
    _validate_localisation(fault.localisation, issues, f"{path}.localisation")
    _validate_evidence(fault.supporting_evidence, issues, f"{path}.supporting_evidence")
    _validate_evidence(fault.contradicting_evidence, issues, f"{path}.contradicting_evidence", required=False)
    if fault.correction_surface is not None:
        _validate_identity(fault.correction_surface, issues, f"{path}.correction_surface", "invalid-fault-record", "correction surface")


def _validate_remediation_advice(advice: object, issues: list[ValidationIssue], path: str) -> None:
    if not isinstance(advice, RemediationAdvice):
        _issue(issues, "invalid-remediation-advice", path, "must be RemediationAdvice")
        return
    if not all(_nonempty(value) for value in (advice.advice_id, advice.version)):
        _issue(issues, "invalid-remediation-advice", path, "advice identity and version are required")
    _validate_identity(advice.fault, issues, f"{path}.fault", "invalid-remediation-advice", "fault")
    if not advice.hypotheses or not _unique(advice.hypotheses) or not all(
        _nonempty(value) for value in advice.hypotheses
    ):
        _issue(issues, "invalid-remediation-advice", f"{path}.hypotheses", "hypotheses must be non-empty and unique")
    for name, values in (("proposed_fixes", advice.proposed_fixes), ("assumptions", advice.assumptions)):
        if not _unique(values) or not all(_nonempty(value) for value in values):
            _issue(issues, "invalid-remediation-advice", f"{path}.{name}", f"{name.replace('_', ' ')} must be non-empty and unique")
    for index, test in enumerate(advice.discriminating_tests):
        _validate_identity(test, issues, f"{path}.discriminating_tests[{index}]", "invalid-remediation-advice", "discriminating test")
    _validate_evidence(advice.supporting_evidence, issues, f"{path}.supporting_evidence")
    _validate_evidence(advice.contradicting_evidence, issues, f"{path}.contradicting_evidence", required=False)
    _validate_identity(advice.required_authority, issues, f"{path}.required_authority", "invalid-remediation-advice", "required authority")
    if not isinstance(advice.confidence, AdviserConfidence):
        _issue(issues, "invalid-remediation-advice", f"{path}.confidence", "adviser confidence is not supported")


def _validate_remediation_decision(decision: object, issues: list[ValidationIssue], path: str) -> None:
    if not isinstance(decision, RemediationDecision):
        _issue(issues, "invalid-remediation-decision", path, "must be a RemediationDecision")
        return
    if not all(_nonempty(value) for value in (decision.remediation_id, decision.version)):
        _issue(issues, "invalid-remediation-decision", path, "remediation identity and version are required")
    _validate_identity(decision.advice, issues, f"{path}.advice", "invalid-remediation-decision", "advice")
    _validate_identity(decision.decided_by, issues, f"{path}.decided_by", "invalid-remediation-decision", "decision authority")
    _validate_evidence((decision.rationale,), issues, f"{path}.rationale")
    if not isinstance(decision.disposition, RemediationDisposition):
        _issue(issues, "invalid-remediation-decision", f"{path}.disposition", "remediation disposition is not supported")
    elif decision.disposition in {RemediationDisposition.ACCEPTED, RemediationDisposition.MODIFIED}:
        if decision.approved_work is None:
            _issue(issues, "invalid-remediation-decision", f"{path}.approved_work", "accepted or modified advice requires approved work identity")
    elif decision.approved_work is not None:
        _issue(issues, "invalid-remediation-decision", f"{path}.approved_work", "non-approved advice cannot carry approved work identity")
    if decision.approved_work is not None:
        _validate_identity(decision.approved_work, issues, f"{path}.approved_work", "invalid-remediation-decision", "approved work")


def _matches_contract_type(value: object, annotation: object) -> bool:
    origin = get_origin(annotation)
    if annotation is Any:
        return True
    if origin in (Union, types.UnionType):
        return any(_matches_contract_type(value, candidate) for candidate in get_args(annotation))
    if origin is tuple:
        if type(value) is not tuple:
            return False
        arguments = get_args(annotation)
        if len(arguments) > 1 and arguments[1] is not Ellipsis:
            return len(value) == len(arguments) and all(
                _matches_contract_type(item, item_type) for item, item_type in zip(value, arguments)
            )
        item_type = arguments[0] if arguments else Any
        return all(_matches_contract_type(item, item_type) for item in value)
    if annotation is type(None):
        return value is None
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return type(value) is annotation
    if isinstance(annotation, type) and is_dataclass(annotation):
        return type(value) is annotation
    if annotation in (str, int, bool, float):
        return type(value) is annotation or (annotation is float and type(value) is int)
    return isinstance(value, annotation) if isinstance(annotation, type) else False


def _validate_portable_content(value: object, issues: list[ValidationIssue], path: str) -> None:
    """Apply baseline semantic checks to every externally exposed domain record."""
    if is_dataclass(value) and not isinstance(value, type):
        hints = get_type_hints(type(value))
        for field in fields(value):
            field_value = getattr(value, field.name)
            field_path = f"{path}.{field.name}"
            if not _matches_contract_type(field_value, hints[field.name]):
                _issue(issues, "invalid-record-type", field_path, "value does not match its declared contract type")
                continue
            _validate_portable_content(field_value, issues, field_path)
        return
    if isinstance(value, tuple):
        for index, item in enumerate(value):
            _validate_portable_content(item, issues, f"{path}[{index}]")
        return
    if isinstance(value, str) and not _nonempty(value):
        _issue(issues, "invalid-record-content", path, "string values must be non-empty")
    elif isinstance(value, int) and not isinstance(value, bool) and value < 0:
        _issue(issues, "invalid-record-content", path, "integer values cannot be negative")


def _validate_standalone_clause(record: object, issues: list[ValidationIssue], path: str) -> None:
    policy = ComparisonPolicy("standalone-policy", "v1", "standalone-digest", (record,), (), (), ())
    _validate_clauses(policy, None, None, issues)


def _validate_standalone_tolerance(record: object, issues: list[ValidationIssue], path: str) -> None:
    _validate_tolerances((record,), None, issues, path)


def _validate_standalone_exclusion(record: object, issues: list[ValidationIssue], path: str) -> None:
    _validate_exclusions((record,), None, issues, path)


def _validate_standalone_warning(record: object, issues: list[ValidationIssue], path: str) -> None:
    _validate_warning_bands((record,), None, issues, path)


_STANDALONE_RECORD_VALIDATORS = {
    Identity: lambda record, issues, path: _validate_identity(record, issues, path, "invalid-identity", "record"),
    EvidenceReference: lambda record, issues, path: _validate_evidence((record,), issues, path),
    SchemaField: _validate_schema_field,
    SchemaDeclaration: _validate_schema,
    GrainDeclaration: lambda record, issues, path: _validate_grain(record, set(record.key_fields), issues, path),
    CanonicalisationDeclaration: _validate_canonicalisation,
    SyntheticProvenance: _validate_synthetic_provenance,
    FrozenDataset: _validate_frozen_dataset,
    ExpectedOutput: _validate_expected_output,
    CandidateIdentity: _validate_candidate_identity,
    ContextIdentity: lambda record, issues, path: _validate_context_identity(
        record, issues, path, "invalid-context-identity", "record"
    ),
    IndependentlyDerivedReceipt: _validate_receipt,
    RepeatRunIdentity: _validate_repeat_run_identity,
    RuleConstraint: _validate_rule_constraint,
    RuleDeclaration: _validate_rule,
    AggregateControl: _validate_aggregate,
    OrderingField: _validate_ordering_field,
    OrderingDeclaration: lambda record, issues, path: _validate_ordering(record, None, issues, path),
    ReplayInput: _validate_replay_input,
    ReplaySpecification: lambda record, issues, path: _validate_replay(record, None, issues, path),
    ComparisonDeclaration: lambda record, issues, path: _validate_comparison(record, None, issues, path),
    ToleranceDeclaration: _validate_standalone_tolerance,
    ExclusionDeclaration: _validate_standalone_exclusion,
    WarningBandDeclaration: _validate_standalone_warning,
    ParityClause: _validate_standalone_clause,
    ConformanceClause: _validate_standalone_clause,
    InvariantClause: _validate_standalone_clause,
    OperationalEvidenceClause: _validate_standalone_clause,
    DeliveryIntegrityClause: _validate_standalone_clause,
    ComparisonPolicy: lambda record, issues, path: _validate_policy(record, None, None, issues),
    Checkpoint: lambda record, issues, path: _validate_checkpoint(record, None, issues, path),
    OutputLineageBinding: _validate_output_lineage_binding,
    LineageDefinition: lambda record, issues, path: _validate_lineage(record, None, None, None, issues),
    OwnerPresentedEvidence: _validate_owner_presented_evidence,
    EnvironmentCertificateClaim: _validate_environment_certificate_claim,
    AssuranceDeclaration: _validate_assurance_declaration,
    ActualOutput: _validate_actual_output,
    ClauseOutcome: _validate_clause_outcome,
    LineageFrontier: _validate_lineage_frontier,
    UncoveredPath: _validate_uncovered_path,
    DiagnosticLocalisation: _validate_localisation,
    VerificationResult: _validate_verification_result,
    FaultRecord: _validate_fault_record,
    RemediationAdvice: _validate_remediation_advice,
    RemediationDecision: _validate_remediation_decision,
}

if frozenset(_STANDALONE_RECORD_VALIDATORS) | {VerificationCase} != frozenset(DOMAIN_RECORD_TYPES):
    raise RuntimeError("every exposed verification record requires one fail-closed semantic validator")


def inspect_verification_record(record: object) -> ValidationReport:
    """Validate any record exposed by the generated portable wire contract."""
    if type(record) not in DOMAIN_RECORD_TYPES:
        return ValidationReport((ValidationIssue("invalid-record", "record", "must be a known verification-domain record"),))
    if isinstance(record, VerificationCase):
        return inspect_verification_case(record)

    issues: list[ValidationIssue] = []
    _validate_portable_content(record, issues, "record")
    has_type_issues = any(issue.code == "invalid-record-type" for issue in issues)
    try:
        _STANDALONE_RECORD_VALIDATORS[type(record)](record, issues, "record")
    except Exception:
        if not has_type_issues:
            raise
        # Semantic validators assume the declared runtime shape. The portable
        # type issue is already the controlled refusal for malformed values.
    return ValidationReport(tuple(issues))


def validate_verification_record(record: object) -> object:
    """Fail closed for every top-level record in the generated wire contract."""
    inspect_verification_record(record).require_valid()
    return record


def inspect_verification_case(case: VerificationCase) -> ValidationReport:
    """Collect every portable-contract violation without making any decision for a user."""
    issues: list[ValidationIssue] = []
    evidence_provenance: EvidenceProvenance | None = None
    if not isinstance(case, VerificationCase):
        return ValidationReport((ValidationIssue("invalid-case", "case", "must be a VerificationCase"),))
    _validate_portable_content(case, issues, "case")
    has_type_issues = any(issue.code == "invalid-record-type" for issue in issues)
    try:
        if not all(_nonempty(value) for value in (case.case_id, case.version)):
            _issue(issues, "invalid-case-identity", "case", "case identity and version must be non-empty")
        _validate_context_identity(case.context, issues, "case.context", "invalid-case-identity", "case context")
        if not isinstance(case.mode, VerificationMode):
            _issue(issues, "invalid-mode", "mode", "verification mode is unsupported")
        if not isinstance(case.diagnostic_strength, DiagnosticStrength):
            _issue(issues, "invalid-diagnostic-strength", "diagnostic_strength", "diagnostic strength is unsupported")
        datasets = _validate_dataset_roles(case.frozen_datasets, issues)
        outputs = _validate_expected_outputs(case, issues)
        checkpoints = _validate_lineage(
            case.lineage,
            outputs,
            case.diagnostic_strength,
            datasets,
            issues,
            case.context,
        )
        _validate_policy(
            case.comparison_policy,
            outputs,
            datasets,
            issues,
            checkpoints,
            case.context,
        )
        _validate_assurance(case, issues)
        evidence_provenance = case.evidence_provenance
    except Exception:
        if not has_type_issues:
            raise
    return ValidationReport(tuple(issues), evidence_provenance)


def validate_verification_case(case: VerificationCase) -> VerificationCase:
    """Fail closed and return a valid case only when all central checks pass."""
    inspect_verification_case(case).require_valid()
    return case


def observe_policy(case: VerificationCase) -> PolicyObservation:
    """Freeze the policy identity and all policy content before execution begins."""
    validate_verification_case(case)
    policy = case.comparison_policy
    return PolicyObservation(case.case_id, case.version, policy.policy_id, policy.version, policy.digest, policy)


def ensure_policy_unchanged(case: VerificationCase, observation: PolicyObservation) -> None:
    """Refuse a case whose comparison policy moved after observation."""
    validate_verification_case(case)
    if not isinstance(observation, PolicyObservation) or not isinstance(observation.policy_snapshot, ComparisonPolicy):
        raise PolicyChangedAfterObservationError("comparison policy observation is invalid; a new verification case is required")
    policy = case.comparison_policy
    observed = (observation.case_id, observation.case_version, observation.policy_id, observation.policy_version, observation.policy_digest)
    current = (case.case_id, case.version, policy.policy_id, policy.version, policy.digest)
    if current != observed or policy != observation.policy_snapshot:
        raise PolicyChangedAfterObservationError("comparison policy changed after observation; a new verification case is required")


# Short forms keep the core enforcement API discoverable without introducing a
# second validator implementation.
inspect_case = inspect_verification_case
validate_case = validate_verification_case


__all__ = [
    "PolicyChangedAfterObservationError",
    "PolicyObservation",
    "ValidationIssue",
    "ValidationReport",
    "VerificationContractError",
    "ensure_policy_unchanged",
    "inspect_verification_case",
    "inspect_case",
    "inspect_verification_record",
    "observe_policy",
    "validate_verification_case",
    "validate_case",
    "validate_verification_record",
]
