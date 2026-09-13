"""The use-case aggregate: header, lifecycle, outputs, datasets, lineage spans and versions.

One engagement holds many use cases. A use case owns one consumer outcome, its
named target outputs, the datasets it needs, the named intermediate steps
between them, how each segment is built, how the sources a segment reads
combine, the scenarios it is judged by, its authorities, its standing
conditions, the artefacts intake read, the products it consumes from other use
cases, and the lifecycle that ends in a named human acceptance.

Every recorded fact carries the artefact, position, extractor and status it came
from, so a reviewer can open the same artefact and check it. External records
stay identity references; no case content is copied.

The lineage spans are derived from those recorded facts and are never declared a
second time, so the record and the spans cannot disagree. A version is the
immutable boundary a named human accepts a chosen set of spans through; it says
what it covers and what it leaves outside, and it is fixed once cut.

Nothing here gates progress on the quality of that provenance. A refusal in this
module means the record would contradict itself, lose its provenance, name an
actor of the wrong kind, cross an undeclared lifecycle edge, or record a machine
route where only a logical locator belongs. A locator is logical, so it names an
artefact identity and a position inside it and never an address, whatever the
scheme, and never a path on a machine. A condition that was never answered
is not a refusal: it records the default it falls back to, so nothing is applied
that the record does not show.
"""
# evorthon-implements: EVD-README-049
# evorthon-implements: EVD-README-044
# evorthon-implements: EVD-README-043
from __future__ import annotations

# evorthon-component: engagement
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date
from enum import Enum
from types import MappingProxyType

from ..boundary_patterns import MACHINE_ROUTE_PATTERNS, MACHINE_ROUTE_SHAPES, shape_carried, shapes
from ..verification.domain.contracts import (
    DatasetRole,
    ExpectedOutputOrigin,
    GrainDeclaration,
    Identity,
    SchemaDeclaration,
    VerificationStatus,
)
from .aggregate import (
    Actor,
    ActorKind,
    DecisionKind,
    DecisionOutcome,
    EngagementError,
    EngagementMode,
    ImmutableReference,
    NamedHumanDecision,
    ReferenceKind,
    _required_text,
    is_placeholder_identity,
)


USE_CASE_SCHEMA_VERSION = "evorthon.use-case.v1"


class UseCaseError(EngagementError):
    """Raised when a use-case record would contradict itself or its lifecycle."""


class UseCaseState(str, Enum):
    """The complete use-case lifecycle vocabulary.

    Intake and build both run inside opened, so no state stands for work that
    cannot start. What can be built is a per-segment question answered outside
    this aggregate.
    """

    OPENED = "opened"
    VERIFIED = "verified"
    ACCEPTED = "accepted"
    IN_SERVICE = "in_service"
    SUPERSEDED = "superseded"


class FactStatus(str, Enum):
    """How a recorded fact reached the record."""

    EXTRACTED = "extracted"
    INFERRED = "inferred"
    CONFIRMED = "confirmed"


class AvailabilityState(str, Enum):
    """Whether a declared dataset is in hand, expected, absent, or filled."""

    OBTAINED = "obtained"
    OBTAINABLE_BY = "obtainable_by"
    UNOBTAINABLE = "unobtainable"
    SYNTHETIC_FILLED = "synthetic_filled"


LIFECYCLE_TRANSITIONS: frozenset[tuple[UseCaseState, UseCaseState]] = frozenset(
    {
        (UseCaseState.OPENED, UseCaseState.VERIFIED),
        (UseCaseState.VERIFIED, UseCaseState.ACCEPTED),
        (UseCaseState.ACCEPTED, UseCaseState.IN_SERVICE),
        (UseCaseState.ACCEPTED, UseCaseState.SUPERSEDED),
        (UseCaseState.IN_SERVICE, UseCaseState.SUPERSEDED),
    }
)
SIGNED_STATES = frozenset({UseCaseState.ACCEPTED, UseCaseState.IN_SERVICE, UseCaseState.SUPERSEDED})
# The states a record stands in once a named human has accepted a version and
# before it is superseded. A later version cut on such a record is accepted
# beside the acceptance it already holds, and no lifecycle edge is crossed.
ACCEPTED_STATES = frozenset({UseCaseState.ACCEPTED, UseCaseState.IN_SERVICE})
AVAILABILITY_STATES_WITH_DATASET = frozenset(
    {AvailabilityState.OBTAINED, AvailabilityState.SYNTHETIC_FILLED}
)

# A recorded locator is one declared value this product wrote, so every shape
# the product declares for a machine route is read here: the prose readings,
# the declared-value readings that a single segment, a lettered volume with no
# separator, a share host with nothing after it and a traversal anywhere in the
# value are enough for, and an address under any scheme at all. The shapes are
# owned in one place; the refusal below is this aggregate's own.
LOCATOR_ROUTES = shapes(MACHINE_ROUTE_PATTERNS, MACHINE_ROUTE_SHAPES)


def _reject_unsafe_locator(value: str, label: str) -> None:
    """Refuse a machine route where only a logical locator belongs."""
    carried = shape_carried(LOCATOR_ROUTES, value)
    if carried is not None:
        raise UseCaseError(f"{label} must be logical, not a {carried}")


def _require_provenance(value: object, label: str) -> None:
    """Refuse a recorded fact that carries no provenance."""
    if not isinstance(value, FactProvenance):
        raise UseCaseError(f"{label} requires recorded provenance")


def _require_human_actor(value: object, label: str) -> None:
    """Refuse any actor but a named human where only a human may act."""
    if not isinstance(value, Actor) or value.kind is not ActorKind.HUMAN:
        raise UseCaseError(f"only a named human may {label}")


def _require_tuple(value: object, label: str) -> None:
    """Refuse a changeable sequence where an immutable record holds a tuple."""
    if not isinstance(value, tuple):
        raise UseCaseError(f"{label} must be recorded in a tuple")


def _require_distinct_names(value: object, label: str) -> None:
    """Refuse anything but a tuple of named identities, each named once."""
    _require_tuple(value, label)
    for name in value:
        if not isinstance(name, str):
            raise UseCaseError(f"{label} names each entry in text")
        _required_text(name, f"{label} entry")
    if len(set(value)) != len(value):
        raise UseCaseError(f"{label} names each entry once")


@dataclass(frozen=True)
class FactLocator:
    """Where a fact was read: an artefact identity and a position inside it."""

    artefact: ImmutableReference
    position: str

    def __post_init__(self) -> None:
        if not isinstance(self.artefact, ImmutableReference):
            raise UseCaseError("a fact locator must name an intake_artefact identity")
        if self.artefact.kind is not ReferenceKind.INTAKE_ARTEFACT:
            raise UseCaseError("a fact locator must name an intake_artefact identity")
        _required_text(self.position, "locator position")
        _reject_unsafe_locator(self.artefact.identifier, "artefact identity")
        _reject_unsafe_locator(self.position, "locator position")


@dataclass(frozen=True)
class FactProvenance:
    """The artefact, position, extractor and status behind one recorded fact."""

    locator: FactLocator
    extracted_by: Actor
    status: FactStatus

    def __post_init__(self) -> None:
        if not isinstance(self.locator, FactLocator):
            raise UseCaseError("provenance requires a fact locator")
        if not isinstance(self.extracted_by, Actor):
            raise UseCaseError("provenance requires a named extractor")
        if not isinstance(self.status, FactStatus):
            raise UseCaseError("provenance requires a declared fact status")

    @property
    def artefact(self) -> ImmutableReference:
        """The artefact identity, owned by the locator so the two cannot disagree."""
        return self.locator.artefact


@dataclass(frozen=True)
class Fact:
    """One recorded value and the provenance that makes it inspectable."""

    value: str
    provenance: FactProvenance

    def __post_init__(self) -> None:
        _required_text(self.value, "fact value")
        _require_provenance(self.provenance, "a recorded fact")


@dataclass(frozen=True)
class UseCaseHeader:
    """Who consumes the use case, what it must achieve, and by when."""

    engagement_id: str
    engagement_mode: EngagementMode
    consumer: Fact
    outcome: Fact
    done_definition: Fact
    cadence: Fact
    deadline: Fact

    def __post_init__(self) -> None:
        _required_text(self.engagement_id, "engagement identity")
        if is_placeholder_identity(self.engagement_id):
            raise UseCaseError("engagement identity must not be a placeholder")
        if not isinstance(self.engagement_mode, EngagementMode):
            raise UseCaseError("a use case must declare the engagement mode")
        for label, item in (
            ("consumer", self.consumer),
            ("outcome", self.outcome),
            ("done definition", self.done_definition),
            ("cadence", self.cadence),
            ("deadline", self.deadline),
        ):
            if not isinstance(item, Fact):
                raise UseCaseError(f"the {label} must be a recorded fact")


@dataclass(frozen=True)
class StoredColumnName:
    """An optional physical name declared for one logical schema field."""

    field_id: str
    stored_name: str

    def __post_init__(self) -> None:
        _required_text(self.field_id, "stored column field")
        _required_text(self.stored_name, "stored column name")


@dataclass(frozen=True)
class ReplacedOutput:
    """The existing output a modernisation target replaces, by identity and logical location."""

    identity: Identity
    system: str
    location: str

    def __post_init__(self) -> None:
        if not isinstance(self.identity, Identity):
            raise UseCaseError("a replaced output must be named by identity")
        _required_text(self.system, "replaced output system")
        _required_text(self.location, "replaced output location")
        _reject_unsafe_locator(self.location, "replaced output location")


@dataclass(frozen=True)
class TargetOutput:
    """One target output: its declared shape, timing, and optional stored names.

    The keys are the declared grain's key fields, so a second copy cannot drift
    from the grain. A modernisation target may name the output it replaces; a
    greenfield target names the specification or golden example that defines it.
    """

    output_id: str
    kind: str
    schema: SchemaDeclaration
    grain: GrainDeclaration
    cadence: str
    cutoff_semantics: str
    effective_time_semantics: str
    provenance: FactProvenance
    stored_name: str | None = None
    stored_column_names: tuple[StoredColumnName, ...] = ()
    replaces: ReplacedOutput | None = None
    defined_by: Identity | None = None

    def __post_init__(self) -> None:
        _required_text(self.output_id, "output identity")
        _required_text(self.kind, "output kind")
        if not isinstance(self.schema, SchemaDeclaration):
            raise UseCaseError("a target output must declare a schema")
        if not isinstance(self.grain, GrainDeclaration):
            raise UseCaseError("a target output must declare a grain")
        if not self.grain.key_fields:
            raise UseCaseError("a target output grain must declare its keys")
        declared = {field.field_id for field in self.schema.fields}
        undeclared_keys = [key for key in self.grain.key_fields if key not in declared]
        if undeclared_keys:
            raise UseCaseError("output keys are not declared schema fields: " + ", ".join(undeclared_keys))
        _required_text(self.cadence, "output cadence")
        _required_text(self.cutoff_semantics, "output cutoff semantics")
        _required_text(self.effective_time_semantics, "output effective-time semantics")
        _require_provenance(self.provenance, "a target output")
        if self.stored_name is not None:
            _required_text(self.stored_name, "output stored name")
        named_fields: set[str] = set()
        for column in self.stored_column_names:
            if not isinstance(column, StoredColumnName):
                raise UseCaseError("stored column names must be declared stored column names")
            if column.field_id not in declared:
                raise UseCaseError(f"a stored column name names an undeclared field: {column.field_id}")
            if column.field_id in named_fields:
                raise UseCaseError(f"a schema field has two stored column names: {column.field_id}")
            named_fields.add(column.field_id)
        if self.replaces is not None and not isinstance(self.replaces, ReplacedOutput):
            raise UseCaseError("a replaced output must be a declared replaced output")
        if self.defined_by is not None and not isinstance(self.defined_by, Identity):
            raise UseCaseError("a defining specification must be named by identity")

    @property
    def keys(self) -> tuple[str, ...]:
        """The output keys, owned by the declared grain."""
        return self.grain.key_fields


@dataclass(frozen=True)
class DatasetAvailability:
    """Whether a declared dataset is in hand, expected by a date, absent, or filled.

    An absent dataset is a recorded fact and not a stop. What that costs a
    segment is decided where readiness is computed.
    """

    state: AvailabilityState
    dataset: Identity | None = None
    obtainable_by: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, AvailabilityState):
            raise UseCaseError("a dataset must declare a known availability state")
        needs_dataset = self.state in AVAILABILITY_STATES_WITH_DATASET
        if needs_dataset and not isinstance(self.dataset, Identity):
            raise UseCaseError("an obtained or filled dataset requires a dataset identity")
        if not needs_dataset and self.dataset is not None:
            raise UseCaseError("an expected or absent dataset carries no dataset identity")
        if self.state is AvailabilityState.OBTAINABLE_BY:
            if not isinstance(self.obtainable_by, str):
                raise UseCaseError("an expected dataset requires the date it is expected by")
            try:
                date.fromisoformat(self.obtainable_by)
            except ValueError as error:
                raise UseCaseError("an expected dataset requires a calendar date") from error
        elif self.obtainable_by is not None:
            raise UseCaseError("only an expected dataset carries an expected date")


@dataclass(frozen=True)
class DatasetPlaceholder:
    """One declared input, reference, enrichment, or prior-state dataset."""

    placeholder_id: str
    role: DatasetRole
    source_system: str
    delivery_mode: str
    cadence: str
    access_owner: Actor
    classification: str
    availability: DatasetAvailability
    provenance: FactProvenance

    def __post_init__(self) -> None:
        _required_text(self.placeholder_id, "dataset identity")
        if not isinstance(self.role, DatasetRole):
            raise UseCaseError("a dataset must declare its role")
        _required_text(self.source_system, "dataset source system")
        _required_text(self.delivery_mode, "dataset delivery mode")
        _required_text(self.cadence, "dataset cadence")
        if not isinstance(self.access_owner, Actor):
            raise UseCaseError("a dataset must name an access owner")
        _required_text(self.classification, "dataset classification")
        if not isinstance(self.availability, DatasetAvailability):
            raise UseCaseError("a dataset must declare its availability")
        _require_provenance(self.provenance, "a dataset")


@dataclass(frozen=True)
class ScenarioResult:
    """One scenario's recorded verification outcome, by case and result identity.

    The case is held by identity alone. No frozen dataset, expected output,
    comparison policy, lineage, or assurance content is copied here.
    """

    case: Identity
    result: ImmutableReference
    status: VerificationStatus

    def __post_init__(self) -> None:
        if not isinstance(self.case, Identity):
            raise UseCaseError("a scenario result must name its case by identity")
        if not isinstance(self.result, ImmutableReference):
            raise UseCaseError("a scenario result must reference a verification_result identity")
        if self.result.kind is not ReferenceKind.VERIFICATION_RESULT:
            raise UseCaseError("a scenario result must reference a verification_result identity")
        if not isinstance(self.status, VerificationStatus):
            raise UseCaseError("a scenario result must carry a deterministic status")

    @property
    def passed(self) -> bool:
        """Whether the recorded outcome is a pass."""
        return self.status is VerificationStatus.PASS


@dataclass(frozen=True)
class StateTransition:
    """One lifecycle move and the named human who made it."""

    source: UseCaseState
    target: UseCaseState
    moved_by: Actor

    def __post_init__(self) -> None:
        if not isinstance(self.source, UseCaseState) or not isinstance(self.target, UseCaseState):
            raise UseCaseError("a lifecycle move must name declared states")
        if (self.source, self.target) not in LIFECYCLE_TRANSITIONS:
            raise UseCaseError(f"{self.source.value} does not transition to {self.target.value}")
        _require_human_actor(self.moved_by, "move the use-case lifecycle")


class ContinuityLabel(str, Enum):
    """Whether a step carries behaviour worth keeping or an accident of the old run."""

    CONTINUITY = "continuity"
    ACCIDENT = "accident"


class BuildRoute(str, Enum):
    """How one segment reaches its declared shape."""

    GENERATED = "generated"
    ENGINEERED = "engineered"
    EXISTING = "existing"


class CombinationMethod(str, Enum):
    """How a segment's consumed sources come together.

    This is the one owner of the method set. A union stacks the rows of every
    consumed source under one shape; a merge puts their columns side by side on
    declared keys. The set matches the combining vocabulary a product
    declaration is drafted against, so a declared method is one a delivery
    route can carry without translating it.
    """

    UNION = "union"
    MERGE = "merge"


class CombinationJoin(str, Enum):
    """Which rows a merge keeps.

    An inner merge keeps the rows every source carries the key of. An outer
    merge keeps every row of every source, so a column inherited from a side
    that can be unmatched is as optional as that side. There is no default: a
    merge that kept the wrong rows would either lose rows or publish an empty
    value where the consumer was told to expect one.
    """

    INNER = "inner"
    OUTER = "outer"


class SegmentBoundary(str, Enum):
    """What a lineage span reaches: a named checkpoint step, or a target output."""

    INTERMEDIATE_RESULT = "intermediate_result"
    TARGET_OUTPUT = "target_output"


class AuthorityRole(str, Enum):
    """The named authorities a use case carries."""

    ACCEPTING = "accepting"
    EVIDENCE_OWNER = "evidence_owner"
    AMBIGUITY_RESOLVER = "ambiguity_resolver"


class ConditionState(str, Enum):
    """Whether a standing condition carries an answer or falls back to its default."""

    DECLARED = "declared"
    UNKNOWN = "unknown"


class ConditionTopic(str, Enum):
    """The subject areas the standing conditions cover."""

    CLASSIFICATION_AND_HANDLING = "classification_and_handling"
    HISTORY_AND_TIME = "history_and_time"
    FRESHNESS_AND_OPERATIONS = "freshness_and_operations"
    VOLUME_AND_PERFORMANCE = "volume_and_performance"
    ACCESS_AND_CONSUMPTION = "access_and_consumption"
    QUALITY_TOLERANCES = "quality_tolerances"
    CHANGE_AND_AUDIT = "change_and_audit"


class ConditionKey(str, Enum):
    """Every standing condition. Each is asked once and may be answered at any time."""

    HANDLING_CLASSIFICATION = "handling_classification"
    DATA_OWNER = "data_owner"
    DATA_STEWARD = "data_steward"
    PERMITTED_PURPOSE = "permitted_purpose"
    RESIDENCY = "residency"
    NON_PRODUCTION_MASKING = "non_production_masking"
    EVIDENCE_VISIBILITY = "evidence_visibility"
    RETENTION_WINDOW = "retention_window"
    BACKFILL_DEPTH = "backfill_depth"
    AS_OF_REPRODUCIBILITY = "as_of_reproducibility"
    HISTORISATION_KIND = "historisation_kind"
    SLOWLY_CHANGING_ATTRIBUTES = "slowly_changing_attributes"
    RESTATEMENT_HANDLING = "restatement_handling"
    ARCHIVE_OR_ONLINE = "archive_or_online"
    ERASURE_OBLIGATION = "erasure_obligation"
    FRESHNESS_DEADLINE = "freshness_deadline"
    MISSED_DEADLINE_RESPONSE = "missed_deadline_response"
    RECONCILIATION_CONTROLS = "reconciliation_controls"
    OPERATIONAL_OWNER = "operational_owner"
    MONITORING = "monitoring"
    CHECKPOINT_GRANULARITY = "checkpoint_granularity"
    MAX_RETRIES = "max_retries"
    BACKOFF = "backoff"
    LOAD_VOLUME = "load_volume"
    GROWTH_AND_PEAKS = "growth_and_peaks"
    QUERY_PATTERN = "query_pattern"
    COST_CEILING = "cost_ceiling"
    CONSUMPTION_ROUTE = "consumption_route"
    AUTHENTICATION_AND_AUTHORISATION = "authentication_and_authorisation"
    ROW_OR_COLUMN_RESTRICTIONS = "row_or_column_restrictions"
    DOWNSTREAM_CONSUMERS = "downstream_consumers"
    ACCEPTED_SOURCE_DEFECTS = "accepted_source_defects"
    WARNING_AND_FAILURE_CLASSES = "warning_and_failure_classes"
    COMPLETENESS_EXPECTATION = "completeness_expectation"
    CHANGE_FREQUENCY = "change_frequency"
    CHANGE_APPROVER = "change_approver"
    COMPATIBILITY_OBLIGATION = "compatibility_obligation"
    AUDIT_EVIDENCE = "audit_evidence"
    AUDIT_EVIDENCE_RETENTION = "audit_evidence_retention"
    PARALLEL_RUN_PERIOD = "parallel_run_period"
    CUTOVER_CRITERIA = "cutover_criteria"
    DECOMMISSION_OWNER = "decommission_owner"
    ROLLBACK = "rollback"


# Each topic owns its keys. This inventory is the only place the grouping is
# stated, so one key cannot belong to two subject areas.
CONDITION_TOPIC_KEYS: Mapping[ConditionTopic, tuple[ConditionKey, ...]] = MappingProxyType(
    {
        ConditionTopic.CLASSIFICATION_AND_HANDLING: (
            ConditionKey.HANDLING_CLASSIFICATION,
            ConditionKey.DATA_OWNER,
            ConditionKey.DATA_STEWARD,
            ConditionKey.PERMITTED_PURPOSE,
            ConditionKey.RESIDENCY,
            ConditionKey.NON_PRODUCTION_MASKING,
            ConditionKey.EVIDENCE_VISIBILITY,
        ),
        ConditionTopic.HISTORY_AND_TIME: (
            ConditionKey.RETENTION_WINDOW,
            ConditionKey.BACKFILL_DEPTH,
            ConditionKey.AS_OF_REPRODUCIBILITY,
            ConditionKey.HISTORISATION_KIND,
            ConditionKey.SLOWLY_CHANGING_ATTRIBUTES,
            ConditionKey.RESTATEMENT_HANDLING,
            ConditionKey.ARCHIVE_OR_ONLINE,
            ConditionKey.ERASURE_OBLIGATION,
        ),
        ConditionTopic.FRESHNESS_AND_OPERATIONS: (
            ConditionKey.FRESHNESS_DEADLINE,
            ConditionKey.MISSED_DEADLINE_RESPONSE,
            ConditionKey.RECONCILIATION_CONTROLS,
            ConditionKey.OPERATIONAL_OWNER,
            ConditionKey.MONITORING,
            ConditionKey.CHECKPOINT_GRANULARITY,
            ConditionKey.MAX_RETRIES,
            ConditionKey.BACKOFF,
        ),
        ConditionTopic.VOLUME_AND_PERFORMANCE: (
            ConditionKey.LOAD_VOLUME,
            ConditionKey.GROWTH_AND_PEAKS,
            ConditionKey.QUERY_PATTERN,
            ConditionKey.COST_CEILING,
        ),
        ConditionTopic.ACCESS_AND_CONSUMPTION: (
            ConditionKey.CONSUMPTION_ROUTE,
            ConditionKey.AUTHENTICATION_AND_AUTHORISATION,
            ConditionKey.ROW_OR_COLUMN_RESTRICTIONS,
            ConditionKey.DOWNSTREAM_CONSUMERS,
        ),
        ConditionTopic.QUALITY_TOLERANCES: (
            ConditionKey.ACCEPTED_SOURCE_DEFECTS,
            ConditionKey.WARNING_AND_FAILURE_CLASSES,
            ConditionKey.COMPLETENESS_EXPECTATION,
        ),
        ConditionTopic.CHANGE_AND_AUDIT: (
            ConditionKey.CHANGE_FREQUENCY,
            ConditionKey.CHANGE_APPROVER,
            ConditionKey.COMPATIBILITY_OBLIGATION,
            ConditionKey.AUDIT_EVIDENCE,
            ConditionKey.AUDIT_EVIDENCE_RETENTION,
            ConditionKey.PARALLEL_RUN_PERIOD,
            ConditionKey.CUTOVER_CRITERIA,
            ConditionKey.DECOMMISSION_OWNER,
            ConditionKey.ROLLBACK,
        ),
    }
)
CONDITION_KEYS: tuple[ConditionKey, ...] = tuple(
    key for keys in CONDITION_TOPIC_KEYS.values() for key in keys
)
# The suggestion an unanswered condition falls back to. It is recorded on the
# declaration itself, so nothing is applied that the record does not show.
CONDITION_DEFAULTS: Mapping[ConditionKey, str] = MappingProxyType(
    {
        ConditionKey.HANDLING_CLASSIFICATION: "confidential",
        ConditionKey.DATA_OWNER: "the accepting authority",
        ConditionKey.DATA_STEWARD: "the accepting authority",
        ConditionKey.PERMITTED_PURPOSE: "this use case alone",
        ConditionKey.RESIDENCY: "the residency of the source system",
        ConditionKey.NON_PRODUCTION_MASKING: "masked outside production",
        ConditionKey.EVIDENCE_VISIBILITY: "the named authorities",
        ConditionKey.RETENTION_WINDOW: "keep everything",
        ConditionKey.BACKFILL_DEPTH: "none",
        ConditionKey.AS_OF_REPRODUCIBILITY: "not required",
        ConditionKey.HISTORISATION_KIND: "current only",
        ConditionKey.SLOWLY_CHANGING_ATTRIBUTES: "not tracked",
        ConditionKey.RESTATEMENT_HANDLING: "a restatement replaces the load it corrects",
        ConditionKey.ARCHIVE_OR_ONLINE: "online for the whole retention window",
        ConditionKey.ERASURE_OBLIGATION: "none declared",
        ConditionKey.FRESHNESS_DEADLINE: "no deadline",
        ConditionKey.MISSED_DEADLINE_RESPONSE: "tell the operational owner",
        ConditionKey.RECONCILIATION_CONTROLS: "none",
        ConditionKey.OPERATIONAL_OWNER: "the accepting authority",
        ConditionKey.MONITORING: "none",
        ConditionKey.CHECKPOINT_GRANULARITY: "step",
        ConditionKey.MAX_RETRIES: "3",
        ConditionKey.BACKOFF: "exponential",
        ConditionKey.LOAD_VOLUME: "unmeasured",
        ConditionKey.GROWTH_AND_PEAKS: "unmeasured",
        ConditionKey.QUERY_PATTERN: "a full read of the output",
        ConditionKey.COST_CEILING: "none",
        ConditionKey.CONSUMPTION_ROUTE: "the tooling the consumer already has",
        ConditionKey.AUTHENTICATION_AND_AUTHORISATION: "owned by the environment",
        ConditionKey.ROW_OR_COLUMN_RESTRICTIONS: "none",
        ConditionKey.DOWNSTREAM_CONSUMERS: "none declared",
        ConditionKey.ACCEPTED_SOURCE_DEFECTS: "none",
        ConditionKey.WARNING_AND_FAILURE_CLASSES: "every difference is a failure",
        ConditionKey.COMPLETENESS_EXPECTATION: "every declared row",
        ConditionKey.CHANGE_FREQUENCY: "on request",
        ConditionKey.CHANGE_APPROVER: "the accepting authority",
        ConditionKey.COMPATIBILITY_OBLIGATION: "no breaking change inside a major version",
        ConditionKey.AUDIT_EVIDENCE: "the evidence of each accepted version",
        ConditionKey.AUDIT_EVIDENCE_RETENTION: "the retention window",
        ConditionKey.PARALLEL_RUN_PERIOD: "none",
        ConditionKey.CUTOVER_CRITERIA: "the accepting authority decides",
        ConditionKey.DECOMMISSION_OWNER: "the accepting authority",
        ConditionKey.ROLLBACK: "restore the output that was replaced",
    }
)
DECIDING_AUTHORITIES = frozenset({AuthorityRole.ACCEPTING, AuthorityRole.AMBIGUITY_RESOLVER})
CUTOVER_CONDITIONS = frozenset(
    {
        ConditionKey.PARALLEL_RUN_PERIOD,
        ConditionKey.CUTOVER_CRITERIA,
        ConditionKey.DECOMMISSION_OWNER,
        ConditionKey.ROLLBACK,
    }
)

# The readable intake record is one section per intake subject. Each section
# names the use-case fields it records, and every section carries the provenance
# a recorded fact needs. Sections ten to sixteen take their standing conditions
# from the condition inventory above, so a condition is never named twice.
INTAKE_PROVENANCE_FIELDS: tuple[str, ...] = (
    "artefact",
    "position in artefact",
    "extracted by",
    "fact status",
)
_DATASET_FIELDS: tuple[str, ...] = (
    "dataset identity",
    "dataset role",
    "source system",
    "delivery mode",
    "dataset cadence",
    "access owner",
    "classification",
    "availability",
    "obtainable by",
)
_SCENARIO_CASE_FIELDS: tuple[str, ...] = ("scenario case identity", "scenario case version")


def _condition_fields(topic: ConditionTopic) -> tuple[str, ...]:
    """Name one subject area's standing conditions as readable labels."""
    return tuple(key.value.replace("_", " ") for key in CONDITION_TOPIC_KEYS[topic])


# The two intake field labels a greenfield use case is never asked, named once
# so the template below and every reader of it name the same label and cannot
# drift apart.
REPLACED_OUTPUT_INTAKE_FIELD = "replaced output"
CONTINUITY_OR_ACCIDENT_INTAKE_FIELD = "continuity or accident"
# The two intake field labels for what a segment reads from more than one
# source. The combination label names the method, and the keys and join a merge
# needs, for the segment it is recorded against; the nullability label names
# which of a pinned product's fields the segment reads can be empty, because a
# pin carries the producer's contract and no shape of its own.
SOURCE_COMBINATION_INTAKE_FIELD = "source combination"
CONSUMED_FIELD_NULLABILITY_INTAKE_FIELD = "consumed field nullability"
_INTAKE_SECTION_FIELDS: Mapping[str, tuple[str, ...]] = {
    "1. Outcome and consumer": (
        "engagement identity",
        "engagement mode",
        "consumer",
        "outcome",
        "done definition",
        "cadence",
        "deadline",
    ),
    "2. Target outputs": (
        "output identity",
        "output kind",
        "schema",
        "grain",
        "keys",
        "output cadence",
        "cutoff semantics",
        "effective-time semantics",
        "stored name",
        "stored column names",
        REPLACED_OUTPUT_INTAKE_FIELD,
        "defining specification",
    ),
    "3. Inputs": _DATASET_FIELDS,
    "4. Reference and enrichment data": _DATASET_FIELDS,
    "5. Intermediate steps": (
        "step identity",
        "step description",
        "evidence owner",
        "checkpoint candidate",
        "expected value origin",
        CONTINUITY_OR_ACCIDENT_INTAKE_FIELD,
    ),
    "6. Scenarios": _SCENARIO_CASE_FIELDS,
    "7. Comparison policy": _SCENARIO_CASE_FIELDS,
    "8. Authorities": ("authority role", "authority actor", "authority subject"),
    "9. Build route": (
        "segment identity",
        "build route",
        "target shape",
        "layer",
        "product domain",
    ),
    "10. Classification and handling": (
        *_condition_fields(ConditionTopic.CLASSIFICATION_AND_HANDLING),
        "intake artefact identity",
        "intake artefact classification",
        "intake artefact locator",
    ),
    "11. History and time": _condition_fields(ConditionTopic.HISTORY_AND_TIME),
    "12. Freshness and operations": _condition_fields(ConditionTopic.FRESHNESS_AND_OPERATIONS),
    "13. Volume and performance": _condition_fields(ConditionTopic.VOLUME_AND_PERFORMANCE),
    "14. Access and consumption": (
        *_condition_fields(ConditionTopic.ACCESS_AND_CONSUMPTION),
        "providing use case",
        "consumed product",
        "consumed major version",
        SOURCE_COMBINATION_INTAKE_FIELD,
        CONSUMED_FIELD_NULLABILITY_INTAKE_FIELD,
    ),
    "15. Quality tolerances": _condition_fields(ConditionTopic.QUALITY_TOLERANCES),
    "16. Change, audit and transition": _condition_fields(ConditionTopic.CHANGE_AND_AUDIT),
}
USE_CASE_INTAKE_SECTIONS: tuple[str, ...] = tuple(_INTAKE_SECTION_FIELDS)
USE_CASE_INTAKE_TEMPLATE_FIELDS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {name: (*fields, *INTAKE_PROVENANCE_FIELDS) for name, fields in _INTAKE_SECTION_FIELDS.items()}
)


def _require_major_version_pin(value: object, label: str) -> None:
    """Refuse a consumed product that is not pinned to a major version alone.

    The pin is plain decimal digits, optionally after a leading v. Anything a
    reader could not compare as a whole number, a digit of another script
    included, is refused.
    """
    if not isinstance(value, str):
        raise UseCaseError(f"{label} must pin a major version")
    digits = value[1:] if value[:1] == "v" else value
    if not digits.isascii() or not digits.isdigit():
        raise UseCaseError(f"{label} must pin a major version")


@dataclass(frozen=True)
class IntermediateResult:
    """One named step between the inputs and the outputs, in the words a human uses.

    Every named intermediate is a checkpoint candidate with an owner for the
    evidence at that point. A modernisation use case also says whether the step
    is behaviour to keep or an accident of the old run, and may take its
    expected value from a capture of that run.
    """

    result_id: str
    description: str
    evidence_owner: Actor
    provenance: FactProvenance
    checkpoint_candidate: bool = True
    origin: ExpectedOutputOrigin | None = None
    continuity: ContinuityLabel | None = None

    def __post_init__(self) -> None:
        _required_text(self.result_id, "intermediate result identity")
        _required_text(self.description, "intermediate result description")
        if not isinstance(self.evidence_owner, Actor):
            raise UseCaseError("an intermediate result must name an evidence owner")
        if not isinstance(self.checkpoint_candidate, bool):
            raise UseCaseError("an intermediate result must say whether it is a checkpoint candidate")
        if self.origin is not None and not isinstance(self.origin, ExpectedOutputOrigin):
            raise UseCaseError("an expected value must name a declared origin")
        if self.continuity is not None and not isinstance(self.continuity, ContinuityLabel):
            raise UseCaseError("a step must carry a declared continuity label")
        _require_provenance(self.provenance, "an intermediate result")


@dataclass(frozen=True)
class BuildRouteDeclaration:
    """How one segment is built, and the shape and layer it produces."""

    segment_id: str
    route: BuildRoute
    provenance: FactProvenance
    target_shape: str | None = None
    layer: str | None = None
    product_domain: str | None = None

    def __post_init__(self) -> None:
        _required_text(self.segment_id, "segment identity")
        if not isinstance(self.route, BuildRoute):
            raise UseCaseError("a segment must declare a known build route")
        if self.target_shape is not None:
            _required_text(self.target_shape, "target shape")
        if self.layer is not None:
            _required_text(self.layer, "layer label")
        if self.route is BuildRoute.GENERATED:
            if self.product_domain is None:
                raise UseCaseError("a generated segment must name the product domain it generates into")
            _required_text(self.product_domain, "product domain")
        elif self.product_domain is not None:
            raise UseCaseError("only a generated segment names a product domain")
        _require_provenance(self.provenance, "a build route")


@dataclass(frozen=True)
class SourceCombination:
    """How one segment's consumed sources combine into what it reads.

    A segment that reads more than one source says which of the declared
    methods brings them together. A union stacks their rows and takes neither
    keys nor a join. A merge puts their columns side by side, so it names the
    keys it merges on and says which rows it keeps. The declaration is recorded
    against the segment it belongs to and names the sources it combines; the
    segment refuses a source it does not consume.
    """

    segment_id: str
    method: CombinationMethod
    sources: tuple[str, ...]
    provenance: FactProvenance
    keys: tuple[str, ...] = ()
    join: CombinationJoin | None = None

    def __post_init__(self) -> None:
        _required_text(self.segment_id, "segment identity")
        if not isinstance(self.method, CombinationMethod):
            raise UseCaseError("a combination must declare a known combination method")
        _require_distinct_names(self.sources, "the sources of a combination")
        if len(self.sources) < 2:
            raise UseCaseError("a combination names the two or more sources it combines")
        if self.method is CombinationMethod.MERGE:
            _require_distinct_names(self.keys, "the keys of a merge")
            if not self.keys:
                raise UseCaseError("a merge must name the keys it merges its sources on")
            if not isinstance(self.join, CombinationJoin):
                raise UseCaseError("a merge must declare which rows it keeps")
        else:
            if self.keys:
                raise UseCaseError("only a merge names the keys it merges on")
            if self.join is not None:
                raise UseCaseError("only a merge declares which rows it keeps")
        _require_provenance(self.provenance, "a source combination")


@dataclass(frozen=True)
class ScenarioReference:
    """One scenario the use case owns, held by case identity and version.

    The case registry owns the frozen inputs, the expected output and the
    comparison rules. None of that content is copied here.
    """

    case: Identity
    provenance: FactProvenance

    def __post_init__(self) -> None:
        if not isinstance(self.case, Identity):
            raise UseCaseError("a scenario must name its case by identity")
        _required_text(self.case.version, "scenario case version")
        _require_provenance(self.provenance, "a scenario")


@dataclass(frozen=True)
class Authority:
    """One named authority: who accepts, who owns evidence for a named subject, who resolves ambiguity."""

    role: AuthorityRole
    actor: Actor
    provenance: FactProvenance
    subject: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.role, AuthorityRole):
            raise UseCaseError("an authority must declare a known role")
        if not isinstance(self.actor, Actor):
            raise UseCaseError("an authority must name an actor")
        if self.role in DECIDING_AUTHORITIES:
            _require_human_actor(self.actor, "hold a deciding authority")
        if self.role is AuthorityRole.EVIDENCE_OWNER:
            if self.subject is None:
                raise UseCaseError("an evidence owner must name the subject it owns the evidence for")
            _required_text(self.subject, "authority subject")
        elif self.subject is not None:
            raise UseCaseError("only an evidence owner names a subject")
        _require_provenance(self.provenance, "an authority")


@dataclass(frozen=True)
class ConditionOverride:
    """A named human's replacement for the default a condition falls back to."""

    value: str
    author: Actor

    def __post_init__(self) -> None:
        _required_text(self.value, "override value")
        if not isinstance(self.author, Actor):
            raise UseCaseError("an override must name its author")
        _require_human_actor(self.author, "override a default")


@dataclass(frozen=True)
class ConditionDeclaration:
    """One standing condition: the answer it was given, or the default it falls back to.

    An unanswered condition records that default on the declaration itself, so a
    reader sees what is in force without consulting anything else. A named human
    may override the default, and the override carries its author.
    """

    key: ConditionKey
    state: ConditionState
    provenance: FactProvenance
    value: str | None = None
    default_value: str | None = None
    override: ConditionOverride | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.key, ConditionKey):
            raise UseCaseError("a condition must name a declared condition key")
        if not isinstance(self.state, ConditionState):
            raise UseCaseError("a condition must say whether it was answered")
        _require_provenance(self.provenance, "a condition")
        if self.state is ConditionState.DECLARED:
            if self.value is None:
                raise UseCaseError("an answered condition requires the value it was given")
            _required_text(self.value, "condition value")
            if self.default_value is not None:
                raise UseCaseError("an answered condition records no default")
            if self.override is not None:
                raise UseCaseError("only an unanswered condition carries an override")
            return
        if self.value is not None:
            raise UseCaseError("an unanswered condition carries no given value")
        if self.default_value is None:
            raise UseCaseError("an unanswered condition must record the default it falls back to")
        if self.default_value != CONDITION_DEFAULTS[self.key]:
            raise UseCaseError("a recorded default must be the default the condition key declares")
        if self.override is not None and not isinstance(self.override, ConditionOverride):
            raise UseCaseError("an override must be a declared override")

    @property
    def effective_value(self) -> str:
        """What is in force: the answer, the override, or the recorded default."""
        if self.state is ConditionState.DECLARED:
            return str(self.value)
        if self.override is not None:
            return self.override.value
        return str(self.default_value)


@dataclass(frozen=True)
class IntakeArtefact:
    """One frozen intake artefact: its identity and digest, its classification, and where it sits."""

    artefact: ImmutableReference
    classification: str
    locator: str
    provenance: FactProvenance

    def __post_init__(self) -> None:
        if not isinstance(self.artefact, ImmutableReference):
            raise UseCaseError("an intake artefact must carry an intake_artefact identity")
        if self.artefact.kind is not ReferenceKind.INTAKE_ARTEFACT:
            raise UseCaseError("an intake artefact must carry an intake_artefact identity")
        _required_text(self.classification, "artefact classification")
        _required_text(self.locator, "artefact locator")
        _reject_unsafe_locator(self.artefact.identifier, "artefact identity")
        _reject_unsafe_locator(self.locator, "artefact locator")
        _require_provenance(self.provenance, "an intake artefact")


@dataclass(frozen=True)
class ConsumedFieldExpectation:
    """One field a consumed product is expected to publish, and whether it can be empty.

    A pin names the producer's contract and carries no shape of its own, so a
    segment reading only pinned products states nothing about their fields
    unless it is recorded here. What is recorded is the reader's expectation,
    not the producer's contract: the producer stays the owner of what it
    publishes, and a disagreement between the two is what a check is for.
    """

    field_id: str
    nullable: bool

    def __post_init__(self) -> None:
        _required_text(self.field_id, "consumed field identity")
        if not isinstance(self.nullable, bool):
            raise UseCaseError("a consumed field must say whether it can be empty")


@dataclass(frozen=True)
class ConsumerDependency:
    """Another use case's output product this one consumes, at a pinned major version."""

    provider: ImmutableReference
    product_id: str
    major_version: str
    provenance: FactProvenance
    expected_fields: tuple[ConsumedFieldExpectation, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.provider, ImmutableReference):
            raise UseCaseError("a consumer dependency must name the providing use_case identity")
        if self.provider.kind is not ReferenceKind.USE_CASE:
            raise UseCaseError("a consumer dependency must name the providing use_case identity")
        _required_text(self.product_id, "consumed product identity")
        _require_major_version_pin(self.major_version, "a consumed product")
        _require_tuple(self.expected_fields, "the expected fields of a consumed product")
        named: set[str] = set()
        for expectation in self.expected_fields:
            if not isinstance(expectation, ConsumedFieldExpectation):
                raise UseCaseError("a consumed product declares consumed field expectations")
            if expectation.field_id in named:
                raise UseCaseError(f"a consumed field is expected twice: {expectation.field_id}")
            named.add(expectation.field_id)
        _require_provenance(self.provenance, "a consumer dependency")


@dataclass(frozen=True)
class Segment:
    """One lineage span: where it starts, what it passes, and the boundary it reaches.

    A span is named by the boundary it reaches, because exactly one span reaches
    each boundary. It carries the build route declared under that name, and the
    source combination declared under that name, and carries neither when none
    is declared for it. The combination is checked against the sources the span
    actually reads, so the two cannot disagree.
    """

    segment_id: str
    sources: tuple[str, ...]
    passes_through: tuple[str, ...]
    reaches: SegmentBoundary
    route: BuildRouteDeclaration | None = None
    combination: SourceCombination | None = None

    def __post_init__(self) -> None:
        _required_text(self.segment_id, "span identity")
        _require_distinct_names(self.sources, "the sources of a span")
        _require_distinct_names(self.passes_through, "the steps a span passes")
        if not isinstance(self.reaches, SegmentBoundary):
            raise UseCaseError("a span must say what kind of boundary it reaches")
        self._validate_route()
        self._validate_combination()

    def _validate_route(self) -> None:
        if self.route is None:
            return
        if not isinstance(self.route, BuildRouteDeclaration):
            raise UseCaseError("a span carries a declared build route")
        if self.route.segment_id != self.segment_id:
            raise UseCaseError("a span carries the build route declared for it")

    def _validate_combination(self) -> None:
        if self.combination is None:
            return
        if not isinstance(self.combination, SourceCombination):
            raise UseCaseError("a span carries a declared source combination")
        if self.combination.segment_id != self.segment_id:
            raise UseCaseError("a span carries the source combination declared for it")
        unread = sorted(set(self.combination.sources) - set(self.sources))
        if unread:
            raise UseCaseError("a combination names a source the span does not read: " + ", ".join(unread))


@dataclass(frozen=True)
class CoverageStatement:
    """What a version covers and what it leaves outside, in the version's own words.

    The statement is recorded on the version so a reader sees the boundary
    without deriving it again. It is refused when it names one span both inside
    and outside, and the use case refuses it when it disagrees with the spans
    the use case actually has.
    """

    covered_segments: tuple[str, ...]
    covered_outputs: tuple[str, ...] = ()
    segments_outside: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_distinct_names(self.covered_segments, "the spans a version covers")
        _require_distinct_names(self.covered_outputs, "the outputs a version covers")
        _require_distinct_names(self.segments_outside, "the spans a version leaves outside")
        if not self.covered_segments:
            raise UseCaseError("a version covers at least one span")
        both = sorted(set(self.covered_segments) & set(self.segments_outside))
        if both:
            raise UseCaseError("a coverage statement names one span inside and outside: " + ", ".join(both))


@dataclass(frozen=True)
class Version:
    """One acceptance boundary, fixed once cut.

    It names the spans and outputs it covers, the scenario cases at the exact
    versions that ran, the packages it delivers, the standing conditions as they
    stood at the cut, and the projection it was cut on. The projection digest is
    stored as it was given; recomputing it belongs to the route that cuts the
    version, not to this record.
    """

    identity: ImmutableReference
    coverage: CoverageStatement
    readiness_projection: ImmutableReference
    scenario_case_versions: tuple[Identity, ...] = ()
    packages: tuple[ImmutableReference, ...] = ()
    conditions: tuple[ConditionDeclaration, ...] = ()
    suggested_disposition: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ImmutableReference):
            raise UseCaseError("a version must carry a use_case_version identity")
        if self.identity.kind is not ReferenceKind.USE_CASE_VERSION:
            raise UseCaseError("a version must carry a use_case_version identity")
        if not isinstance(self.coverage, CoverageStatement):
            raise UseCaseError("a version must carry a coverage statement")
        if not isinstance(self.readiness_projection, ImmutableReference):
            raise UseCaseError("a version must reference the projection it was cut on")
        if self.readiness_projection.kind is not ReferenceKind.READINESS_PROJECTION:
            raise UseCaseError("a version must reference the projection it was cut on")
        self._validate_cases()
        self._validate_packages()
        self._validate_conditions()
        if self.suggested_disposition is not None:
            _required_text(self.suggested_disposition, "suggested disposition")

    @property
    def covered_segments(self) -> tuple[str, ...]:
        """The spans this version covers, owned by the coverage statement."""
        return self.coverage.covered_segments

    @property
    def covered_outputs(self) -> tuple[str, ...]:
        """The target outputs this version covers, owned by the coverage statement."""
        return self.coverage.covered_outputs

    @property
    def segments_outside(self) -> tuple[str, ...]:
        """The spans this version leaves outside it, owned by the coverage statement."""
        return self.coverage.segments_outside

    @property
    def readiness_digest(self) -> str:
        """The projection digest as given at the cut, owned by the projection reference."""
        return self.readiness_projection.digest

    def _validate_cases(self) -> None:
        _require_tuple(self.scenario_case_versions, "the scenario cases of a version")
        for case in self.scenario_case_versions:
            if not isinstance(case, Identity):
                raise UseCaseError("a version must name each scenario case by identity")
            _required_text(case.version, "scenario case version")
        if len(set(self.scenario_case_versions)) != len(self.scenario_case_versions):
            raise UseCaseError("a version names each scenario case once")

    def _validate_packages(self) -> None:
        _require_tuple(self.packages, "the packages of a version")
        for package in self.packages:
            if not isinstance(package, ImmutableReference):
                raise UseCaseError("a version must name each package by approved_work identity")
            if package.kind is not ReferenceKind.APPROVED_WORK:
                raise UseCaseError("a version must name each package by approved_work identity")
        if len(set(self.packages)) != len(self.packages):
            raise UseCaseError("a version names each package once")

    def _validate_conditions(self) -> None:
        _require_tuple(self.conditions, "the conditions of a version")
        keys: set[ConditionKey] = set()
        for condition in self.conditions:
            if not isinstance(condition, ConditionDeclaration):
                raise UseCaseError("a version snapshot holds declared conditions")
            if condition.key in keys:
                raise UseCaseError("a version snapshot holds each condition once")
            keys.add(condition.key)


@dataclass(frozen=True)
class UseCase:
    """The versioned use-case aggregate; external records stay identity references."""

    identity: ImmutableReference
    header: UseCaseHeader
    schema_version: str = USE_CASE_SCHEMA_VERSION
    revision: int = 1
    state: UseCaseState = UseCaseState.OPENED
    target_outputs: tuple[TargetOutput, ...] = ()
    datasets: tuple[DatasetPlaceholder, ...] = ()
    intermediate_results: tuple[IntermediateResult, ...] = ()
    build_routes: tuple[BuildRouteDeclaration, ...] = ()
    source_combinations: tuple[SourceCombination, ...] = ()
    scenarios: tuple[ScenarioReference, ...] = ()
    authorities: tuple[Authority, ...] = ()
    conditions: tuple[ConditionDeclaration, ...] = ()
    intake_artefacts: tuple[IntakeArtefact, ...] = ()
    consumer_dependencies: tuple[ConsumerDependency, ...] = ()
    scenario_results: tuple[ScenarioResult, ...] = ()
    versions: tuple[Version, ...] = ()
    decisions: tuple[NamedHumanDecision, ...] = ()
    transitions: tuple[StateTransition, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ImmutableReference):
            raise UseCaseError("a use case must carry a use_case identity")
        if self.identity.kind is not ReferenceKind.USE_CASE:
            raise UseCaseError("a use case must carry a use_case identity")
        if not isinstance(self.header, UseCaseHeader):
            raise UseCaseError("a use case must carry a header")
        if self.schema_version != USE_CASE_SCHEMA_VERSION:
            raise UseCaseError(f"unsupported use-case schema version: {self.schema_version}")
        if self.revision < 1:
            raise UseCaseError("use-case revision must be positive")
        if not isinstance(self.state, UseCaseState):
            raise UseCaseError("a use case must carry a declared lifecycle state")
        self._validate_outputs()
        self._validate_datasets()
        self._validate_intermediate_results()
        self._validate_build_routes()
        self._validate_source_combinations()
        self._validate_scenarios()
        self._validate_authorities()
        self._validate_conditions()
        self._validate_intake_artefacts()
        self._validate_consumer_dependencies()
        self._validate_versions()
        self._validate_scenario_results()
        self._validate_decisions()
        self._validate_lifecycle()

    @classmethod
    def open(cls, identity: ImmutableReference, header: UseCaseHeader) -> "UseCase":
        """Open a use case. Intake and build both run from here."""
        return cls(identity=identity, header=header)

    def record_target_output(self, output: TargetOutput) -> "UseCase":
        """Record one declared target output."""
        return self._evolve(target_outputs=(*self.target_outputs, output))

    def record_dataset(self, placeholder: DatasetPlaceholder) -> "UseCase":
        """Record one declared input, reference, enrichment, or prior-state dataset."""
        return self._evolve(datasets=(*self.datasets, placeholder))

    def record_intermediate_result(self, result: IntermediateResult) -> "UseCase":
        """Record one named step between the inputs and the outputs."""
        return self._evolve(intermediate_results=(*self.intermediate_results, result))

    def record_build_route(self, route: BuildRouteDeclaration) -> "UseCase":
        """Record how one segment is built."""
        return self._evolve(build_routes=(*self.build_routes, route))

    def record_source_combination(self, combination: SourceCombination) -> "UseCase":
        """Record how one segment's consumed sources combine."""
        return self._evolve(source_combinations=(*self.source_combinations, combination))

    def record_scenario(self, scenario: ScenarioReference) -> "UseCase":
        """Record one scenario the use case owns, by case identity and version."""
        return self._evolve(scenarios=(*self.scenarios, scenario))

    def record_authority(self, authority: Authority) -> "UseCase":
        """Record one named authority."""
        return self._evolve(authorities=(*self.authorities, authority))

    def record_condition(self, condition: ConditionDeclaration) -> "UseCase":
        """Record one standing condition, answered or falling back to its default."""
        return self._evolve(conditions=(*self.conditions, condition))

    def record_intake_artefact(self, artefact: IntakeArtefact) -> "UseCase":
        """Record one frozen artefact intake read."""
        return self._evolve(intake_artefacts=(*self.intake_artefacts, artefact))

    def record_consumer_dependency(self, dependency: ConsumerDependency) -> "UseCase":
        """Record one product this use case consumes from another use case."""
        return self._evolve(consumer_dependencies=(*self.consumer_dependencies, dependency))

    def record_scenario_result(self, result: ScenarioResult) -> "UseCase":
        """Record the verification result reference for one scenario."""
        return self._evolve(scenario_results=(*self.scenario_results, result))

    def cut_version(self, version: Version) -> "UseCase":
        """Cut one version over the spans and outputs it names.

        The version is fixed from here. Cutting a later one leaves every earlier
        version exactly as it was cut.
        """
        return self._evolve(versions=(*self.versions, version))

    def segments(self) -> tuple[Segment, ...]:
        """Derive the lineage spans from the recorded inputs, steps and outputs.

        A span runs from its sources to the next boundary it reaches. The
        sources of the first span are every declared dataset, whatever its
        availability; after that they are the boundary the previous span
        reached. A boundary is a named step kept as a checkpoint, or a target
        output; a step that is not a checkpoint is passed through inside the
        span that reaches the next one.

        The recorded order of the steps is the only order the record holds, so
        the spans follow it. The datasets and the target outputs are sets rather
        than sequences, so both are read in name order and the derivation does
        not depend on the order they were recorded in.
        """
        self._require_one_reading()
        sources = tuple(sorted(placeholder.placeholder_id for placeholder in self.datasets))
        passed: tuple[str, ...] = ()
        spans: list[Segment] = []
        for result in self.intermediate_results:
            if not result.checkpoint_candidate:
                passed = (*passed, result.result_id)
                continue
            spans.append(self._span(sources, passed, result.result_id, SegmentBoundary.INTERMEDIATE_RESULT))
            sources = (result.result_id,)
            passed = ()
        for output_id in sorted(output.output_id for output in self.target_outputs):
            spans.append(self._span(sources, passed, output_id, SegmentBoundary.TARGET_OUTPUT))
        return tuple(spans)

    def verify(self, moved_by: Actor) -> "UseCase":
        """Move to verified once every scenario of the current version has a passing result."""
        return self._move(UseCaseState.VERIFIED, moved_by)

    def accept(self, decision: NamedHumanDecision) -> "UseCase":
        """Record the named human decision that accepts the current version."""
        if not isinstance(decision, NamedHumanDecision):
            raise UseCaseError("acceptance requires a named human decision")
        return self._move(
            UseCaseState.ACCEPTED,
            decision.decided_by,
            decisions=(*self.decisions, decision),
        )

    def take_acceptance(self, decision: NamedHumanDecision) -> "UseCase":
        """Record a later version's named acceptance beside the one already taken.

        A use case reaches accepted once, so a version cut on a record that
        already stands accepted, in service or not, is taken where that record
        stands and no lifecycle edge is crossed. A record that does not stand
        accepted has no acceptance to take a later one beside: the move that
        takes a record there is the acceptance that makes it, and this refuses.
        A superseded record stands past its acceptances and refuses here too.
        """
        if not isinstance(decision, NamedHumanDecision):
            raise UseCaseError("acceptance requires a named human decision")
        if self.state not in ACCEPTED_STATES:
            raise UseCaseError("only an accepted use case takes a later acceptance beside its own")
        return self._evolve(decisions=(*self.decisions, decision))

    def enter_service(self, moved_by: Actor) -> "UseCase":
        """Put an accepted use case into service."""
        return self._move(UseCaseState.IN_SERVICE, moved_by)

    def supersede(self, moved_by: Actor) -> "UseCase":
        """Supersede the use case once a later version takes over."""
        return self._move(UseCaseState.SUPERSEDED, moved_by)

    @property
    def acceptance(self) -> NamedHumanDecision | None:
        """The named human acceptance taken most recently, or none where none was taken.

        A record holds one acceptance for each version accepted on it, so this
        is the decision that accepted the latest of them. Every acceptance the
        record holds, in the order it took them, is in its decisions.
        """
        return self.decisions[-1] if self.decisions else None

    @property
    def current_version(self) -> Version | None:
        """The version cut most recently, once one is cut."""
        return self.versions[-1] if self.versions else None

    def _span(
        self,
        sources: tuple[str, ...],
        passed: tuple[str, ...],
        boundary: str,
        reaches: SegmentBoundary,
    ) -> Segment:
        return Segment(
            segment_id=boundary,
            sources=sources,
            passes_through=passed,
            reaches=reaches,
            route=self._declared_route(boundary),
            combination=self._declared_combination(boundary),
        )

    def _declared_route(self, segment_id: str) -> BuildRouteDeclaration | None:
        for route in self.build_routes:
            if route.segment_id == segment_id:
                return route
        return None

    def _declared_combination(self, segment_id: str) -> SourceCombination | None:
        for combination in self.source_combinations:
            if combination.segment_id == segment_id:
                return combination
        return None

    def _require_one_reading(self) -> None:
        """Refuse a lineage the recorded facts let a reader read two ways."""
        # Every step is compared, checkpoint or not: a step that shares a target
        # output's name would otherwise be passed through a span of its own name.
        names = [result.result_id for result in self.intermediate_results]
        names += [output.output_id for output in self.target_outputs]
        repeated = sorted({name for name in names if names.count(name) > 1})
        if repeated:
            raise UseCaseError("a step and a target output share one span name: " + ", ".join(repeated))
        trailing: list[str] = []
        for result in self.intermediate_results:
            trailing = [] if result.checkpoint_candidate else [*trailing, result.result_id]
        if trailing and len(self.target_outputs) > 1:
            raise UseCaseError(
                "a step after the last checkpoint could belong to more than one target output: "
                + ", ".join(trailing)
            )

    def _move(self, target: UseCaseState, moved_by: Actor, **changes: object) -> "UseCase":
        move = StateTransition(source=self.state, target=target, moved_by=moved_by)
        return self._evolve(state=target, transitions=(*self.transitions, move), **changes)

    def _evolve(self, **changes: object) -> "UseCase":
        return replace(self, revision=self.revision + 1, **changes)

    def _validate_outputs(self) -> None:
        for output in self.target_outputs:
            if not isinstance(output, TargetOutput):
                raise UseCaseError("target outputs must be declared target outputs")
            if output.replaces is not None and self.header.engagement_mode is not EngagementMode.MODERNISATION:
                raise UseCaseError("only a modernisation use case replaces an existing output")
        identifiers = [output.output_id for output in self.target_outputs]
        if len(identifiers) != len(set(identifiers)):
            raise UseCaseError("target output identities must be unique")

    def _validate_datasets(self) -> None:
        for placeholder in self.datasets:
            if not isinstance(placeholder, DatasetPlaceholder):
                raise UseCaseError("datasets must be declared datasets")
        identifiers = [placeholder.placeholder_id for placeholder in self.datasets]
        if len(identifiers) != len(set(identifiers)):
            raise UseCaseError("dataset identities must be unique")

    def _validate_intermediate_results(self) -> None:
        greenfield = self.header.engagement_mode is not EngagementMode.MODERNISATION
        for result in self.intermediate_results:
            if not isinstance(result, IntermediateResult):
                raise UseCaseError("intermediate results must be declared intermediate results")
            if not greenfield:
                continue
            if result.continuity is not None:
                raise UseCaseError("only a modernisation use case labels continuity or accident")
            if result.origin is ExpectedOutputOrigin.MODERNISATION_CAPTURE:
                raise UseCaseError("only a modernisation use case takes an expected value from an old run")
        identifiers = [result.result_id for result in self.intermediate_results]
        if len(identifiers) != len(set(identifiers)):
            raise UseCaseError("intermediate result identities must be unique")

    def _validate_build_routes(self) -> None:
        for route in self.build_routes:
            if not isinstance(route, BuildRouteDeclaration):
                raise UseCaseError("build routes must be declared build routes")
        identifiers = [route.segment_id for route in self.build_routes]
        if len(identifiers) != len(set(identifiers)):
            raise UseCaseError("a segment declares one build route")

    def _validate_source_combinations(self) -> None:
        """Read each combination once, and once the spans exist, against its own span.

        Deriving the spans is what puts a combination beside the sources it
        claims to combine, so a record that already derives one is checked here.
        A combination recorded before the datasets and outputs it belongs to is
        an incomplete record and not a contradiction, so it waits.
        """
        for combination in self.source_combinations:
            if not isinstance(combination, SourceCombination):
                raise UseCaseError("source combinations must be declared source combinations")
        identifiers = [combination.segment_id for combination in self.source_combinations]
        if len(identifiers) != len(set(identifiers)):
            raise UseCaseError("a segment declares one source combination")
        if self.source_combinations:
            self.segments()

    def _validate_scenarios(self) -> None:
        for scenario in self.scenarios:
            if not isinstance(scenario, ScenarioReference):
                raise UseCaseError("scenarios must be declared scenario references")
        cases = [scenario.case for scenario in self.scenarios]
        if len(cases) != len(set(cases)):
            raise UseCaseError("a scenario is named once")

    def _validate_authorities(self) -> None:
        subjects: set[str] = set()
        held: set[AuthorityRole] = set()
        for authority in self.authorities:
            if not isinstance(authority, Authority):
                raise UseCaseError("authorities must be declared authorities")
            if authority.role is AuthorityRole.EVIDENCE_OWNER:
                if authority.subject in subjects:
                    raise UseCaseError("one evidence owner is named for each subject")
                subjects.add(str(authority.subject))
                continue
            if authority.role in held:
                raise UseCaseError("a use case names one accepting authority and one ambiguity resolver")
            held.add(authority.role)

    def _validate_conditions(self) -> None:
        modernisation = self.header.engagement_mode is EngagementMode.MODERNISATION
        keys: set[ConditionKey] = set()
        for condition in self.conditions:
            if not isinstance(condition, ConditionDeclaration):
                raise UseCaseError("conditions must be declared conditions")
            if condition.key in keys:
                raise UseCaseError("a condition is declared once")
            keys.add(condition.key)
            if condition.key in CUTOVER_CONDITIONS and not modernisation:
                raise UseCaseError("only a modernisation use case declares a cutover condition")

    def _validate_intake_artefacts(self) -> None:
        for artefact in self.intake_artefacts:
            if not isinstance(artefact, IntakeArtefact):
                raise UseCaseError("intake artefacts must be declared intake artefacts")
        identifiers = [artefact.artefact.identifier for artefact in self.intake_artefacts]
        if len(identifiers) != len(set(identifiers)):
            raise UseCaseError("intake artefact identities must be unique")

    def _validate_consumer_dependencies(self) -> None:
        for dependency in self.consumer_dependencies:
            if not isinstance(dependency, ConsumerDependency):
                raise UseCaseError("consumer dependencies must be declared consumer dependencies")
            if dependency.provider.identifier == self.identity.identifier:
                raise UseCaseError("a use case does not consume its own product")
        consumed = [
            (dependency.provider.identifier, dependency.product_id)
            for dependency in self.consumer_dependencies
        ]
        if len(consumed) != len(set(consumed)):
            raise UseCaseError("a consumed product is pinned once")

    def _validate_versions(self) -> None:
        identifiers: set[str] = set()
        spans: tuple[Segment, ...] | None = None
        for version in self.versions:
            if not isinstance(version, Version):
                raise UseCaseError("versions must be declared versions")
            if version.identity.identifier in identifiers:
                raise UseCaseError("version identities must be unique")
            identifiers.add(version.identity.identifier)
            if spans is None:
                spans = self.segments()
            self._validate_coverage(version, spans)
            self._validate_version_cases(version)

    def _validate_coverage(self, version: Version, spans: tuple[Segment, ...]) -> None:
        names = {span.segment_id for span in spans}
        covered = set(version.covered_segments)
        unknown = sorted(covered - names)
        if unknown:
            raise UseCaseError("a version covers a span the use case does not have: " + ", ".join(unknown))
        if sorted(version.segments_outside) != sorted(names - covered):
            raise UseCaseError("a coverage statement must name every span the version leaves outside it")
        reached = {
            span.segment_id
            for span in spans
            if span.reaches is SegmentBoundary.TARGET_OUTPUT and span.segment_id in covered
        }
        if sorted(version.covered_outputs) != sorted(reached):
            raise UseCaseError("a version must name every target output its spans reach and no other")

    def _validate_version_cases(self, version: Version) -> None:
        referenced = {scenario.case for scenario in self.scenarios}
        unknown = sorted(
            case.identifier for case in version.scenario_case_versions if case not in referenced
        )
        if unknown:
            raise UseCaseError(
                "a version names a scenario case the use case does not reference: " + ", ".join(unknown)
            )

    def _validate_scenario_results(self) -> None:
        for result in self.scenario_results:
            if not isinstance(result, ScenarioResult):
                raise UseCaseError("scenario results must be declared scenario results")
        recorded = {result.case: result for result in self.scenario_results}
        if len(recorded) != len(self.scenario_results):
            raise UseCaseError("a scenario may record only one result")
        if self.state is UseCaseState.OPENED:
            return
        version = self.current_version
        judged = version.scenario_case_versions if version is not None else tuple(recorded)
        if not judged or any(case not in recorded for case in judged):
            raise UseCaseError("a verified use case requires a recorded scenario result")
        if not all(recorded[case].passed for case in judged):
            raise UseCaseError("a verified use case requires a passing result for every scenario")

    def _validate_decisions(self) -> None:
        decision_ids: set[str] = set()
        accepted: set[ImmutableReference] = set()
        for decision in self.decisions:
            if not isinstance(decision, NamedHumanDecision):
                raise UseCaseError("decisions must be named human decisions")
            if decision.kind is not DecisionKind.VERSION_ACCEPTANCE:
                raise UseCaseError("a use case records version_acceptance decisions only")
            if decision.outcome is not DecisionOutcome.ACCEPTED:
                raise UseCaseError("a version acceptance must carry the accepted outcome")
            if decision.subject.kind is not ReferenceKind.USE_CASE_VERSION:
                raise UseCaseError("a version acceptance must reference a use_case_version identity")
            if decision.decision_id in decision_ids:
                raise UseCaseError("decision ids must be unique")
            if decision.subject in accepted:
                raise UseCaseError(
                    "a version is accepted once and its record is fixed from there: "
                    + decision.subject.identifier
                )
            decision_ids.add(decision.decision_id)
            accepted.add(decision.subject)
        if self.state in SIGNED_STATES and not self.decisions:
            raise UseCaseError("an accepted use case requires a named human acceptance decision")

    def _validate_lifecycle(self) -> None:
        state = UseCaseState.OPENED
        for move in self.transitions:
            if not isinstance(move, StateTransition):
                raise UseCaseError("lifecycle moves must be declared lifecycle moves")
            if move.source is not state:
                raise UseCaseError("lifecycle moves must form an unbroken chain")
            state = move.target
        if state is not self.state:
            raise UseCaseError("the recorded lifecycle chain does not end at the current state")
