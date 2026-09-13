"""Portable semantic source for versioned verification-case contracts.

This module owns domain types and field inventories only. Validation,
serialization, deterministic comparison, environment access, and remediation
execution belong to later components. No contract carries a mutable source
location, credentials, raw rows, or a callable oracle.
"""
# evorthon-implements: EVD-README-023
# evorthon-implements: EVD-README-019
from __future__ import annotations

# evorthon-component: verification_domain
from dataclasses import dataclass, fields
from enum import Enum
from types import MappingProxyType


VERIFICATION_DOMAIN_VERSION = "evorthon.verification.domain.v2"


class VerificationMode(str, Enum):
    """The engagement mode that supplies the approved expected-output origin."""

    MODERNISATION = "modernisation"
    GREENFIELD = "greenfield"


class DatasetRole(str, Enum):
    """A frozen dataset's role in a verification case."""

    INPUT = "input"
    REFERENCE = "reference"
    ENRICHMENT = "enrichment"
    PRIOR_STATE = "prior-state"


class DatasetProvenance(str, Enum):
    """Where one frozen dataset or expected output came from."""

    REAL = "real"
    SYNTHETIC = "synthetic"
    DERIVED = "derived"


class EvidenceProvenance(str, Enum):
    """How the whole evidence of a case reads once its declared parts are combined."""

    REAL = "real"
    MIXED = "mixed"
    SYNTHETIC = "synthetic"


class ExpectedOutputOrigin(str, Enum):
    """The approved source class for an expected output, not a live route."""

    MODERNISATION_CAPTURE = "modernisation-capture"
    GREENFIELD_SPECIFICATION = "greenfield-specification"
    REFERENCE_IMPLEMENTATION = "reference-implementation"
    SYNTHETIC_DERIVATION = "synthetic-derivation"


class ClauseFamily(str, Enum):
    """The distinct deterministic check families supported by a case."""

    PARITY = "parity"
    CONFORMANCE = "conformance"
    INVARIANT = "invariant"
    OPERATIONAL_EVIDENCE = "operational-evidence"
    DELIVERY_INTEGRITY = "delivery-integrity"


class VerificationStatus(str, Enum):
    """A deterministic outcome recorded by a later comparison engine."""

    PASS = "pass"
    FAIL = "fail"
    INSUFFICIENT_EVIDENCE = "insufficient-evidence"


class DiagnosticStrength(str, Enum):
    """How precisely a case's available evidence may support localisation."""

    OUTPUT_ONLY = "output-only"
    CHECKPOINTED = "checkpointed"
    REPLAYABLE = "replayable"


class AssuranceLevel(str, Enum):
    """The level claimed by portable evidence; certification remains external."""

    DECLARED = "declared"
    OWNER_PRESENTED = "owner-presented"
    ENVIRONMENT_CERTIFIED = "environment-certified"


class RemediationDisposition(str, Enum):
    """A human's disposition of advice; it is not a command to make a change."""

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    MODIFIED = "modified"
    REQUEST_MORE_EVIDENCE = "request-more-evidence"


class ReceiptSubject(str, Enum):
    """The independently observed case fact represented by a receipt."""

    INPUT = "input"
    REFERENCE = "reference"
    ENRICHMENT = "enrichment"
    PRIOR_STATE = "prior-state"
    CONTEXT = "context"


class FaultClass(str, Enum):
    """The deterministic classification a later fault packet can record."""

    INPUT_IDENTITY = "input-identity"
    REFERENCE_IDENTITY = "reference-identity"
    SCHEMA_COERCION = "schema-coercion"
    MISSING_POPULATION = "missing-population"
    ADDITIONAL_POPULATION = "additional-population"
    DUPLICATE_JOIN_CARDINALITY = "duplicate-join-cardinality"
    FILTER_WINDOW_BOUNDARY = "filter-window-boundary"
    TEMPORAL_EFFECTIVE_DATE = "temporal-effective-date"
    DEFAULT_NULL = "default-null"
    CALCULATION_PRECISION_ROUNDING = "calculation-precision-rounding"
    NONDETERMINISTIC_ORDERING = "nondeterministic-ordering"
    STATE_REPLAY = "state-replay"
    OUTPUT_FORMATTING = "output-formatting"
    RUNTIME_CONFIGURATION_DRIFT = "runtime-configuration-drift"
    UNKNOWN = "unknown"


class DisclosureDecision(str, Enum):
    """The closed outcome of deterministic diagnostic disclosure policy."""

    DISCLOSE = "disclose"
    WITHHOLD_SMALL_CELL = "withhold-small-cell"
    WITHHOLD_POLICY = "withhold-policy"
    WITHHOLD_UNKNOWN = "withhold-unknown"


class AdviserConfidence(str, Enum):
    """A bounded, calibrated confidence declaration for inert adviser output."""

    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SchemaValueType(str, Enum):
    """Portable logical value types used by declared schemas."""

    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    TIMESTAMP = "timestamp"
    BINARY = "binary"


class ComparisonDimension(str, Enum):
    """The output dimensions that deterministic reconciliation can compare."""

    SCHEMA = "schema"
    POPULATION = "population"
    KEY = "key"
    VALUE = "value"
    JOIN_CARDINALITY = "join-cardinality"
    EFFECTIVE_TIME = "effective-time"
    CALCULATION = "calculation"
    AGGREGATE = "aggregate"
    ORDERING = "ordering"
    OUTPUT_FORMAT = "output-format"
    REPLAY_METADATA = "replay-metadata"


class RuleOperator(str, Enum):
    """The closed comparison operators used in a declarative requirement."""

    EQUALS = "equals"
    NOT_EQUALS = "not-equals"
    PRESENT = "present"
    ABSENT = "absent"
    AT_LEAST = "at-least"
    AT_MOST = "at-most"
    MATCHES = "matches"


class SortDirection(str, Enum):
    """A field's required ordering direction."""

    ASCENDING = "ascending"
    DESCENDING = "descending"


class NullPlacement(str, Enum):
    """Where a canonical ordering places null values."""

    FIRST = "first"
    LAST = "last"


class LocalisationStatus(str, Enum):
    """Whether localisation is confirmed, inferred, or remains unknown."""

    CONFIRMED = "confirmed"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class UncoveredPathReason(str, Enum):
    """Why a lineage path cannot support a more precise conclusion."""

    OUTPUT_ONLY = "output-only"
    MISSING_CHECKPOINT_EVIDENCE = "missing-checkpoint-evidence"
    AMBIGUOUS_BRANCH = "ambiguous-branch"
    REPLAY_NOT_DECLARED = "replay-not-declared"


@dataclass(frozen=True)
class Identity:
    """An opaque, versioned identity and cryptographic fingerprint."""

    identifier: str
    version: str
    digest: str


@dataclass(frozen=True)
class EvidenceReference:
    """A portable evidence reference without storage or access routing."""

    evidence_id: str
    version: str
    digest: str
    summary: str


@dataclass(frozen=True)
class SchemaField:
    """One logical field in an expected or observed portable schema."""

    field_id: str
    value_type: SchemaValueType
    nullable: bool
    semantic_role: str
    precision: int | None
    scale: int | None


@dataclass(frozen=True)
class SchemaDeclaration:
    """A versioned schema declaration that can be compared independently."""

    schema_id: str
    version: str
    fields: tuple[SchemaField, ...]
    format_name: str


@dataclass(frozen=True)
class GrainDeclaration:
    """The key and population semantics for a declared result grain."""

    grain_id: str
    version: str
    key_fields: tuple[str, ...]
    population_description: str
    duplicate_keys_permitted: bool


@dataclass(frozen=True)
class CanonicalisationDeclaration:
    """The declared canonical representations required for stable comparison."""

    canonicalisation_id: str
    version: str
    unicode_normalisation: str
    null_representation: str
    decimal_scale: int | None
    timestamp_precision: str | None
    timezone: str | None
    signed_zero_representation: str
    non_finite_number_policy: str


@dataclass(frozen=True)
class SyntheticProvenance:
    """The generator facts that make a synthetic dataset reproducible and labelled.

    ``constrained_by`` names the datasets whose real content shaped the
    generated rows.  It is empty when no real data was available to constrain.
    """

    generator_id: str
    generator_version: str
    seed: str
    constraints_digest: str
    constrained_by: tuple[Identity, ...]


@dataclass(frozen=True)
class FrozenDataset:
    """Identity facts, declared shape, and declared provenance for frozen case data."""

    dataset_id: str
    version: str
    role: DatasetRole
    provenance: DatasetProvenance
    synthetic_provenance: SyntheticProvenance | None
    content_digest: str
    schema: SchemaDeclaration
    grain: GrainDeclaration
    canonicalisation: CanonicalisationDeclaration
    row_count: int
    approved_summary: str


@dataclass(frozen=True)
class ExpectedOutput:
    """A frozen expected output, its approved non-live origin, and its provenance."""

    output_id: str
    version: str
    origin: ExpectedOutputOrigin
    provenance: DatasetProvenance
    content_digest: str
    schema: SchemaDeclaration
    grain: GrainDeclaration
    canonicalisation: CanonicalisationDeclaration
    row_count: int
    format_digest: str
    approved_summary: str


@dataclass(frozen=True)
class CandidateIdentity:
    """The exact candidate artefact selected for a verification run."""

    candidate_id: str
    version: str
    artifact_digest: str


@dataclass(frozen=True)
class ContextIdentity:
    """The immutable logical execution context selected for a run."""

    context_id: str
    version: str
    digest: str
    logical_run_time: str
    cutoff_time: str
    timezone: str


@dataclass(frozen=True)
class IndependentlyDerivedReceipt:
    """An environment-derived receipt for a frozen case fact, never runner self-report."""

    receipt_id: str
    version: str
    subject: ReceiptSubject
    subject_identity: Identity
    observed_digest: str
    derived_by: Identity
    evidence: tuple[EvidenceReference, ...]


@dataclass(frozen=True)
class RepeatRunIdentity:
    """The identity that binds equivalent candidate runs for repeatability evidence."""

    repeat_run_id: str
    version: str
    digest: str


@dataclass(frozen=True)
class RuleConstraint:
    """A closed, inspectable constraint for a non-parity clause."""

    field_id: str
    operator: RuleOperator
    expected_value: str | None


@dataclass(frozen=True)
class RuleDeclaration:
    """A versioned, concrete requirement rather than an opaque rule digest."""

    rule_id: str
    version: str
    constraints: tuple[RuleConstraint, ...]


@dataclass(frozen=True)
class AggregateControl:
    """One declared aggregate or control total used in a parity clause."""

    aggregate_id: str
    version: str
    operation: str
    input_field_id: str
    output_field_id: str
    group_by_fields: tuple[str, ...]
    null_handling: str
    rounding_mode: str


@dataclass(frozen=True)
class OrderingField:
    """One declared ordering key and its canonical null handling."""

    field_id: str
    direction: SortDirection
    null_placement: NullPlacement


@dataclass(frozen=True)
class OrderingDeclaration:
    """The stable output ordering and deterministic tie-breakers."""

    ordering_id: str
    version: str
    fields: tuple[OrderingField, ...]
    tie_breaker_fields: tuple[str, ...]


@dataclass(frozen=True)
class ReplayInput:
    """A frozen case input that a declared checkpoint replay requires."""

    dataset_id: str
    role: DatasetRole
    required: bool


@dataclass(frozen=True)
class ReplaySpecification:
    """Declared replay facts for a checkpoint, never a runner or live route."""

    replay_id: str
    version: str
    checkpoint_id: str
    inputs: tuple[ReplayInput, ...]
    context: ContextIdentity
    transformation: Identity
    output_schema: SchemaDeclaration
    output_grain: GrainDeclaration
    canonicalisation: CanonicalisationDeclaration


@dataclass(frozen=True)
class ComparisonDeclaration:
    """The executable comparison surface that a parity clause freezes."""

    comparison_id: str
    version: str
    dimensions: tuple[ComparisonDimension, ...]
    schema: SchemaDeclaration
    grain: GrainDeclaration
    canonicalisation: CanonicalisationDeclaration
    aggregates: tuple[AggregateControl, ...]
    ordering: OrderingDeclaration | None
    replay: ReplaySpecification | None


@dataclass(frozen=True)
class ToleranceDeclaration:
    """A bounded tolerance with explicit scope and lower/upper limits."""

    tolerance_id: str
    version: str
    clause_ids: tuple[str, ...]
    dimensions: tuple[ComparisonDimension, ...]
    field_ids: tuple[str, ...]
    measurement: str
    lower_bound: str | None
    upper_bound: str | None
    unit: str
    rounding_mode: str


@dataclass(frozen=True)
class ExclusionDeclaration:
    """A declared, inspectable exclusion selector and its scope."""

    exclusion_id: str
    version: str
    clause_ids: tuple[str, ...]
    dimensions: tuple[ComparisonDimension, ...]
    selector: tuple[RuleConstraint, ...]
    rationale: str


@dataclass(frozen=True)
class WarningBandDeclaration:
    """A non-passing warning band with explicit scope and limits."""

    warning_id: str
    version: str
    clause_ids: tuple[str, ...]
    dimensions: tuple[ComparisonDimension, ...]
    field_ids: tuple[str, ...]
    measurement: str
    lower_bound: str | None
    upper_bound: str | None
    unit: str


@dataclass(frozen=True)
class ParityClause:
    """A clause that reconciles a frozen expected output with an actual one."""

    clause_id: str
    version: str
    expected_output_id: str
    comparison: ComparisonDeclaration
    required_evidence: tuple[EvidenceReference, ...]


@dataclass(frozen=True)
class ConformanceClause:
    """A clause that checks a declared interface or contract requirement."""

    clause_id: str
    version: str
    contract: Identity
    requirement: RuleDeclaration
    required_evidence: tuple[EvidenceReference, ...]


@dataclass(frozen=True)
class InvariantClause:
    """A clause that checks an approved invariant over declared evidence."""

    clause_id: str
    version: str
    invariant: Identity
    requirement: RuleDeclaration
    required_evidence: tuple[EvidenceReference, ...]


@dataclass(frozen=True)
class OperationalEvidenceClause:
    """A clause that checks operational evidence without certifying it."""

    clause_id: str
    version: str
    operational_signal: Identity
    requirement: RuleDeclaration
    required_evidence: tuple[EvidenceReference, ...]


@dataclass(frozen=True)
class DeliveryIntegrityClause:
    """A clause that checks declared delivery artefact integrity."""

    clause_id: str
    version: str
    delivery_artifact: Identity
    requirement: RuleDeclaration
    required_evidence: tuple[EvidenceReference, ...]


ComparisonClause = (
    ParityClause
    | ConformanceClause
    | InvariantClause
    | OperationalEvidenceClause
    | DeliveryIntegrityClause
)
CLAUSE_TYPE_BY_FAMILY = MappingProxyType(
    {
        ClauseFamily.PARITY: ParityClause,
        ClauseFamily.CONFORMANCE: ConformanceClause,
        ClauseFamily.INVARIANT: InvariantClause,
        ClauseFamily.OPERATIONAL_EVIDENCE: OperationalEvidenceClause,
        ClauseFamily.DELIVERY_INTEGRITY: DeliveryIntegrityClause,
    }
)


@dataclass(frozen=True)
class ComparisonPolicy:
    """Frozen clauses and their explicit tolerance, exclusion, and warning policy."""

    policy_id: str
    version: str
    digest: str
    clauses: tuple[ComparisonClause, ...]
    tolerances: tuple[ToleranceDeclaration, ...]
    exclusions: tuple[ExclusionDeclaration, ...]
    warning_bands: tuple[WarningBandDeclaration, ...]


@dataclass(frozen=True)
class Checkpoint:
    """A declared lineage checkpoint and bounded diagnostic evidence."""

    checkpoint_id: str
    version: str
    parent_ids: tuple[str, ...]
    expected_state: Identity
    schema: SchemaDeclaration
    grain: GrainDeclaration
    canonicalisation: CanonicalisationDeclaration
    transformation: Identity
    provenance: Identity
    diagnostic_evidence: tuple[EvidenceReference, ...]
    replay: ReplaySpecification | None


@dataclass(frozen=True)
class OutputLineageBinding:
    """The declared terminal checkpoint for one expected output.

    Output-only cases retain the output binding with no terminal checkpoint;
    checkpointed cases bind it to a declared terminal node in the lineage DAG.
    """

    expected_output_id: str
    terminal_checkpoint_id: str | None


@dataclass(frozen=True)
class LineageDefinition:
    """The declared checkpoint graph for localisation, if the case has one."""

    lineage_id: str
    version: str
    checkpoints: tuple[Checkpoint, ...]
    output_bindings: tuple[OutputLineageBinding, ...]


@dataclass(frozen=True)
class OwnerPresentedEvidence:
    """Evidence presented and approved by an owner; this is not certification."""

    evidence_id: str
    version: str
    digest: str
    presented_by: Identity
    approval_evidence: EvidenceReference


@dataclass(frozen=True)
class EnvironmentCertificateClaim:
    """An environment-owned certificate claim referenced without owning a store."""

    claim_id: str
    version: str
    certificate_digest: str
    issued_by: Identity
    assurance_level: AssuranceLevel


@dataclass(frozen=True)
class AssuranceDeclaration:
    """The distinct owner-presented and environment-certificate assurance inputs."""

    assurance_id: str
    version: str
    declared_level: AssuranceLevel
    owner_presented_evidence: tuple[OwnerPresentedEvidence, ...]
    environment_certificate_claims: tuple[EnvironmentCertificateClaim, ...]


@dataclass(frozen=True)
class VerificationCase:
    """The versioned oracle that freezes facts before any candidate run begins."""

    case_id: str
    version: str
    mode: VerificationMode
    frozen_datasets: tuple[FrozenDataset, ...]
    expected_outputs: tuple[ExpectedOutput, ...]
    context: ContextIdentity
    comparison_policy: ComparisonPolicy
    lineage: LineageDefinition
    assurance: AssuranceDeclaration
    diagnostic_strength: DiagnosticStrength

    @property
    def evidence_provenance(self) -> EvidenceProvenance:
        """Report how the frozen evidence of this case reads as a whole.

        The value is derived from the declared provenance of every frozen
        dataset and expected output, so it cannot drift from them.  Evidence
        reads as real or synthetic only when every declared part agrees; any
        other combination, derived evidence included, reads as mixed.  The
        value labels the case and never decides whether it may proceed.
        """
        declared = {part.provenance for part in (*self.frozen_datasets, *self.expected_outputs)}
        if declared == {DatasetProvenance.REAL}:
            return EvidenceProvenance.REAL
        if declared == {DatasetProvenance.SYNTHETIC}:
            return EvidenceProvenance.SYNTHETIC
        return EvidenceProvenance.MIXED


@dataclass(frozen=True)
class ActualOutput:
    """Identity facts and declared shape for one candidate-produced output."""

    output_id: str
    version: str
    content_digest: str
    schema: SchemaDeclaration
    grain: GrainDeclaration
    canonicalisation: CanonicalisationDeclaration
    row_count: int
    format_digest: str
    approved_summary: str


@dataclass(frozen=True)
class ClauseOutcome:
    """A deterministic outcome for one frozen clause in a verification result."""

    outcome_id: str
    version: str
    clause: Identity
    family: ClauseFamily
    status: VerificationStatus
    compared_dimensions: tuple[ComparisonDimension, ...]
    expected_evidence: tuple[EvidenceReference, ...]
    observed_evidence: tuple[EvidenceReference, ...]


@dataclass(frozen=True)
class LineageFrontier:
    """One confirmed lineage boundary and the evidence supporting that boundary."""

    checkpoint_id: str
    evidence: tuple[EvidenceReference, ...]


@dataclass(frozen=True)
class UncoveredPath:
    """A declared lineage path that cannot support exact localisation."""

    path_id: str
    checkpoint_ids: tuple[str, ...]
    reason: UncoveredPathReason
    evidence: tuple[EvidenceReference, ...]


@dataclass(frozen=True)
class DiagnosticLocalisation:
    """An exact confirmation or honest interval bounded by lineage frontiers."""

    localisation_id: str
    version: str
    status: LocalisationStatus
    lower_frontier: tuple[LineageFrontier, ...]
    upper_frontier: tuple[LineageFrontier, ...]
    uncovered_paths: tuple[UncoveredPath, ...]
    supporting_evidence: tuple[EvidenceReference, ...]


@dataclass(frozen=True)
class VerificationResult:
    """A candidate-run result, its outputs, and per-clause deterministic outcomes."""

    result_id: str
    version: str
    case: Identity
    candidate: CandidateIdentity
    context: ContextIdentity
    independent_receipts: tuple[IndependentlyDerivedReceipt, ...]
    actual_outputs: tuple[ActualOutput, ...]
    clause_outcomes: tuple[ClauseOutcome, ...]
    status: VerificationStatus
    evidence: tuple[EvidenceReference, ...]
    diagnostic_strength: DiagnosticStrength
    repeat_run_identity: RepeatRunIdentity


@dataclass(frozen=True)
class FaultRecord:
    """A safe fault record with per-clause references and honest localisation."""

    fault_id: str
    version: str
    result: Identity
    affected_clause_outcome_ids: tuple[str, ...]
    fault_class: FaultClass
    localisation: DiagnosticLocalisation
    diagnostic_scope: str
    disclosure_decision: DisclosureDecision
    supporting_evidence: tuple[EvidenceReference, ...]
    contradicting_evidence: tuple[EvidenceReference, ...]
    correction_surface: Identity | None


@dataclass(frozen=True)
class RemediationAdvice:
    """Inert, evidence-backed advice that a later workflow may present to people."""

    advice_id: str
    version: str
    fault: Identity
    hypotheses: tuple[str, ...]
    proposed_fixes: tuple[str, ...]
    discriminating_tests: tuple[Identity, ...]
    supporting_evidence: tuple[EvidenceReference, ...]
    contradicting_evidence: tuple[EvidenceReference, ...]
    assumptions: tuple[str, ...]
    required_authority: Identity
    confidence: AdviserConfidence


@dataclass(frozen=True)
class RemediationDecision:
    """A human disposition of advice without a mutation or acceptance capability."""

    remediation_id: str
    version: str
    advice: Identity
    disposition: RemediationDisposition
    decided_by: Identity
    rationale: EvidenceReference
    approved_work: Identity | None


DOMAIN_RECORD_TYPES = (
    Identity,
    EvidenceReference,
    SchemaField,
    SchemaDeclaration,
    GrainDeclaration,
    CanonicalisationDeclaration,
    SyntheticProvenance,
    FrozenDataset,
    ExpectedOutput,
    CandidateIdentity,
    ContextIdentity,
    IndependentlyDerivedReceipt,
    RepeatRunIdentity,
    RuleConstraint,
    RuleDeclaration,
    AggregateControl,
    OrderingField,
    OrderingDeclaration,
    ReplayInput,
    ReplaySpecification,
    ComparisonDeclaration,
    ToleranceDeclaration,
    ExclusionDeclaration,
    WarningBandDeclaration,
    ParityClause,
    ConformanceClause,
    InvariantClause,
    OperationalEvidenceClause,
    DeliveryIntegrityClause,
    ComparisonPolicy,
    Checkpoint,
    OutputLineageBinding,
    LineageDefinition,
    OwnerPresentedEvidence,
    EnvironmentCertificateClaim,
    AssuranceDeclaration,
    VerificationCase,
    ActualOutput,
    ClauseOutcome,
    LineageFrontier,
    UncoveredPath,
    DiagnosticLocalisation,
    VerificationResult,
    FaultRecord,
    RemediationAdvice,
    RemediationDecision,
)
DOMAIN_ENUM_TYPES = (
    VerificationMode,
    DatasetRole,
    DatasetProvenance,
    EvidenceProvenance,
    ExpectedOutputOrigin,
    ClauseFamily,
    VerificationStatus,
    DiagnosticStrength,
    AssuranceLevel,
    RemediationDisposition,
    ReceiptSubject,
    FaultClass,
    DisclosureDecision,
    AdviserConfidence,
    SchemaValueType,
    ComparisonDimension,
    RuleOperator,
    SortDirection,
    NullPlacement,
    LocalisationStatus,
    UncoveredPathReason,
)

# These inventories are mechanically derived from the semantic record classes.
# The enforcement package owns serialization and fail-closed validation of
# their external forms.
DOMAIN_TYPE_VERSIONS = MappingProxyType(
    {
        contract_type.__name__: VERIFICATION_DOMAIN_VERSION
        for contract_type in (*DOMAIN_RECORD_TYPES, *DOMAIN_ENUM_TYPES)
    }
)
DOMAIN_FIELD_INVENTORY = MappingProxyType(
    {
        contract_type.__name__: tuple(field.name for field in fields(contract_type))
        for contract_type in DOMAIN_RECORD_TYPES
    }
)
