"""The composition root: plain text in, declared values out, and the routes that use them.

This module is the only place where text becomes a declared value. A route
takes the words a person typed or the words a stored record holds, builds the
values the engagement, readiness, synthetic and delivery components own, calls
those components, and returns what they decided. No policy is made here: every
question about what a record may say is answered by the component that owns it,
and this module only carries the answer back.

Text forms. A value that carries more than one field is written as its fields
separated by a colon, in the order the field table below states; the last field
takes whatever remains, so a colon inside it is kept. A part that holds a list
separates its entries with a semicolon. One recorded declaration is written as
its parts separated by a vertical bar, so no declared value may contain one,
and no entry of a list may contain a semicolon. An empty part means the value
was not declared.

Records. One use case is held in one record under a records root inside the
repository-relative work directory. The record is the canonical readable
projection of three fields: the record form, the header the use case was opened
with, and one line for each recorded declaration, version cut and acceptance,
in the order they happened. Reading a record replays those lines through the
same factories that built them, so the stored words and the live words have one
reader. The record is validated against its own canonical projection before it
is replayed, so a record this module did not write is refused rather than read.

Refusals. Every refusal is an integrity refusal and carries one closed reason:
no record is held for the named engagement and use case, the records root is
outside the work directory, the stored record is not the canonical projection,
a declared value is one the record or its owning component cannot take, the
readiness digest a version is cut on is not the digest the projection has, or
the disposition stored on a version is not the text readiness owns. Nothing is
refused for a readiness state, a synthetic label or the strength of a
provenance: those are reported and left to the reader.

The verification routes refuse through the same closed set, extended by three
reasons of their own. A case document, an adapter configuration, a written
record, a place a configuration document names in an absolute form and an
adapter that contradicts the contract it claims are malformed records. An
adapter identity no configuration names, an evidence validity that does not
cover the run, a candidate an environment declares incompletely and a run an
engine refused are values a component cannot take. Evidence a repository does
not hold, an engagement holding no adapter configuration and a case holding no
record are records nobody holds. Stored evidence that does not produce the
digest it is approved under is an evidence digest mismatch. A packet the
privacy policy withholds is refused nowhere: the diagnosis and the adviser round
both report the withholding decision as the completed answer it is, and the
adviser round asks nobody anything. A recorded outcome that answers for another
run is a digest mismatch, and a document or a held directory outside the records
root is refused like a records root outside the work directory. Nothing is
refused here for a declared provenance, an assurance claim or a verification
status: a status is a result a route reports.

The remediation routes refuse through that same set. A disposition a human
may not take, an actor of the wrong kind, an identity the advice does not
require, material a disposition does not own and a record presented for
somebody else are values a component cannot take. A rerun over another case, a
decision presented again that is not the decision recorded, and a prior run
that is not the run the recorded outcome answers for are digest mismatches.
Nothing is refused for a declared provenance, a claimed assurance class or the
colour of a rerun: a rerun that stayed red is a completed route.

The adviser, generation and campaign routes refuse through that same set. A
reply the gated packet does not support, a packet that never passed the gate,
a declaration draft a segment does not imply and a campaign selection naming a
blocked or unapproved item are values a component cannot take. Nothing is
refused here for what a piece of advice says, for the shape of a generated
estate or for the disposition a campaign reports: each is a result a route
reports and a person reads.

Every refusal a route reports is one a workflow, an engine or this module
raised by name. An error no engine declares is not a refusal and leaves as
itself, so a fault in this product can never be read as a case that was
refused. No refusal detail carries a declared value: a row that cannot be read
is reported by the field it sits in and the type that field declares.
"""
from __future__ import annotations

# evorthon-component: composition
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import MappingProxyType

from .delivery.autobuild import (
    AutoBuildDeliveryRoute,
    AutoBuildRouteError,
    QueueSelection,
    SubprocessAutoBuildRunner,
)
from .delivery.declaration_draft import DeclarationDraftError, draft_declaration
from .delivery.ergasterion import (
    ErgasterionGenerationRoute,
    ErgasterionRouteError,
    ExactGenerationContract,
    GenerationDisposition,
    ProductDeclaration,
    SubprocessErgasterionRunner,
)
from .delivery.pinax import (
    ApprovedRemedy,
    PinaxContractProjector,
    PinaxProjectionError,
    SegmentIteration,
    SubprocessPinaxRunner,
    UseCaseScope,
)
from .dependencies import installed_capabilities
from .engagement import (
    Actor,
    ActorKind,
    EngagementError,
    EngagementMode,
    Fact,
    FactLocator,
    FactProvenance,
    FactStatus,
    ImmutableReference,
    ReferenceKind,
    UseCase,
    render_record_projection,
    validate_record_projection,
)
from .engagement.use_case import (
    ACCEPTED_STATES,
    Authority,
    AuthorityRole,
    AvailabilityState,
    BuildRoute,
    BuildRouteDeclaration,
    CONDITION_DEFAULTS,
    ConditionDeclaration,
    ConditionKey,
    ConditionOverride,
    ConditionState,
    ConsumerDependency,
    ContinuityLabel,
    DatasetAvailability,
    DatasetPlaceholder,
    IntakeArtefact,
    IntermediateResult,
    ReplacedOutput,
    ScenarioReference,
    ScenarioResult,
    StoredColumnName,
    TargetOutput,
    UseCaseHeader,
    Version,
)
from .engagement.versions import (
    AcceptanceRecord,
    CaseEvidence,
    cut_version,
    record_acceptance,
)
from .readiness import (
    CaseDataset,
    CaseExpectedOutput,
    CaseFacts,
    ReadinessProjection,
    project_readiness,
    projection_digest,
)
from .synthetic import GenerationRefusal, generate, read_request
from .synthetic.request import typed_value
from .verification import presentation as verification_presentation
from .verification.adapters import (
    FixtureCandidateRunner,
    FixtureEvidenceRepository,
    check_conformance,
)
from .verification.domain.contracts import (
    ActualOutput,
    DatasetProvenance,
    DatasetRole,
    EnvironmentCertificateClaim,
    EvidenceProvenance,
    EvidenceReference,
    ExpectedOutputOrigin,
    GrainDeclaration,
    Identity,
    OwnerPresentedEvidence,
    RemediationAdvice,
    RemediationDisposition,
    SchemaDeclaration,
    SchemaField,
    SchemaValueType,
    VerificationCase,
    VerificationStatus,
)
from .verification.enforcement.serialization import (
    SerializationError,
    deserialize_json,
    deserialize_record,
    serialize_json,
)
from .verification.enforcement.privacy import (
    PrivacyRefusalReason,
    PrivacyRefused,
    gate_fault_packet,
)
from .verification.enforcement.validation import (
    PolicyChangedAfterObservationError,
    VerificationContractError,
    inspect_verification_case,
    observe_policy,
)
from .verification.workflows import (
    AdviserRefusalReason,
    AdviserRefused,
    CandidateObservation,
    CanonicalisationRefusal,
    ContractRefused,
    DecidingActor,
    EvidenceBasis,
    ExecutedObservation,
    ExpectedMaterial,
    FaultRefused,
    HumanDisposition,
    IntakeRefusalReason,
    IntakeRefused,
    LocalisationRefused,
    PortRefusal,
    PresentedObservation,
    ReconciliationRefused,
    RemediationActorKind,
    RemediationRefusalReason,
    RemediationRefused,
    ReplayRefused,
    advise_on_fault,
    diagnose_failed_output,
    execute_delivery_contract,
    intake_case,
    reconcile_run,
    record_remediation_decision,
    rerun_corrected_case,
)


# The stable name of the record form this module writes and reads.
RECORD_FORM = "evorthon.use-case.record.v1"
# The repository-relative directory every record root sits in or under.
WORK_ROOT = "work"
RECORD_SUFFIX = ".md"
# The three separators of the text forms, from the widest to the narrowest.
PART_SEPARATOR = "|"
LIST_SEPARATOR = ";"
FIELD_SEPARATOR = ":"
# The record's own field names, in the order the projection writes them.
RECORD_FIELDS = ("form", "header", "entry")
# The line the canonical record projection writes for one fact.
RECORD_LINE = re.compile(r"- \*\*(?P<field>[a-z ]+):\*\* (?P<value>.+)")
# What the projection writes for a field that holds no entry at all.
EMPTY_LIST = "[]"
# A path segment that names an engagement or a use case in the records root.
PATH_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
# The words that stand for the two states of a declared flag.
CHECKPOINT_WORDS = MappingProxyType({"checkpoint": True, "no-checkpoint": False})
NULLABLE_WORDS = MappingProxyType({"nullable": True, "not-null": False})
DUPLICATE_KEY_WORDS = MappingProxyType({"duplicate-keys": True, "unique-keys": False})


class RefusalReason(str, Enum):
    """The closed set of integrity reasons a route refuses for."""

    UNKNOWN_ENGAGEMENT = "unknown-engagement"
    RECORD_OUTSIDE_WORK = "record-outside-work"
    MALFORMED_RECORD = "malformed-record"
    MALFORMED_VALUE = "malformed-value"
    DIGEST_MISMATCH = "digest-mismatch"
    DISPOSITION_MISMATCH = "disposition-mismatch"
    RECORD_NOT_HELD = "record-not-held"
    EVIDENCE_DIGEST_MISMATCH = "evidence-digest-mismatch"


class CompositionError(ValueError):
    """Raised when a route cannot compose what the words in front of it declare."""

    def __init__(self, reason: RefusalReason, detail: str) -> None:
        super().__init__(f"{reason.value}: {detail}")
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class RouteResult:
    """What one route did, in values a renderer can present.

    The values are ordered plain values. A route that reads readiness also
    carries the projection itself, because the projection is rendered by its
    own reader rather than flattened here.
    """

    command: str
    values: tuple[tuple[str, object], ...]
    projection: ReadinessProjection | None = None


def _refuse(reason: RefusalReason, detail: str) -> CompositionError:
    return CompositionError(reason, detail)


def _invalid(detail: str) -> CompositionError:
    return _refuse(RefusalReason.MALFORMED_VALUE, detail)


# --- reading plain text into fields -----------------------------------------


def part_text(value: object, label: str) -> str:
    """Read one part of a declaration, refusing anything a record cannot hold."""
    if not isinstance(value, str) or not value.strip():
        raise _invalid(f"{label} must be given as text")
    if PART_SEPARATOR in value or not value.isprintable():
        raise _invalid(f"{label} must be printable text without a part separator")
    return value


def entry_text(value: object, label: str) -> str:
    """Read one entry of a list part, which carries neither separator."""
    text = part_text(value, label)
    if LIST_SEPARATOR in text:
        raise _invalid(f"{label} must not contain a list separator")
    return text


def optional_part(value: object, label: str) -> str | None:
    """Read a part that may be left empty, meaning the value was not declared."""
    if value is None or value == "":
        return None
    return part_text(value, label)


def fields(value: object, count: int, label: str) -> tuple[str, ...]:
    """Split one compound value into exactly the fields its form declares."""
    text = part_text(value, label)
    read = tuple(text.split(FIELD_SEPARATOR, count - 1))
    if len(read) != count:
        raise _invalid(f"{label} is written as {count} fields separated by a colon")
    return read


def entries(value: object, label: str) -> tuple[str, ...]:
    """Split one list part into its entries, an empty part meaning none."""
    if value is None or value == "":
        return ()
    return tuple(entry_text(entry, label) for entry in part_text(value, label).split(LIST_SEPARATOR))


def list_part(values: object, label: str) -> str:
    """Write a sequence of given values as the one list part that holds them."""
    if values is None:
        return ""
    return LIST_SEPARATOR.join(entry_text(value, label) for value in values)


def compound(values: object, label: str) -> str:
    """Write given fields as the one compound value that carries them."""
    read = [part_text(value, label) for value in values]
    for value in read[:-1]:
        if FIELD_SEPARATOR in value:
            raise _invalid(f"{label} carries a field separator before its last field")
    return FIELD_SEPARATOR.join(read)


def named_fields(values: object, label: str) -> Mapping[str, str]:
    """Read written name and value pairs, refusing a repeated or unnamed one."""
    read: dict[str, str] = {}
    for written in values or ():
        name, separator, value = part_text(written, label).partition("=")
        if not separator or not name.strip():
            raise _invalid(f"{label} is written as a field name, an equals sign, and its value")
        if name in read:
            raise _invalid(f"{label} names {name} twice")
        read[name] = value
    return read


def declaration_parts(kind: str, declared: Mapping[str, str]) -> tuple[str, ...]:
    """Order the named fields of one declaration kind, leaving the rest empty."""
    if kind not in DECLARATION_PARTS:
        raise _invalid("a declaration kind must be one of: " + ", ".join(DECLARATION_KINDS))
    labels = DECLARATION_PARTS[kind]
    unknown = sorted(set(declared) - set(labels))
    if unknown:
        raise _invalid(
            f"a {kind} declaration has no field named "
            + ", ".join(unknown)
            + "; its fields are: "
            + ", ".join(labels)
        )
    return tuple(declared.get(label, "") for label in labels)


def read_document(path: object) -> str:
    """Read one supplied document as the text a component reads it from."""
    try:
        return Path(part_text(str(path), "a document path")).read_text(encoding="ascii")
    except OSError as error:
        raise _invalid(f"a supplied document could not be read: {error}") from error
    except UnicodeDecodeError as error:
        raise _invalid("a supplied document is written in printable ASCII") from error


def member(declared: type, value: object, label: str) -> object:
    """Read one written word as the member its own enumeration declares."""
    text = part_text(value, label)
    try:
        return declared(text)
    except ValueError as error:
        permitted = ", ".join(sorted(item.value for item in declared))
        raise _invalid(f"{label} must be one of: {permitted}") from error


def whole_number(value: object, label: str) -> int:
    """Read a written whole number, refusing anything else."""
    text = part_text(value, label)
    if not text.isascii() or not text.isdigit():
        raise _invalid(f"{label} must be a whole number")
    return int(text)


# --- factories: the one place text becomes a declared value ------------------


def actor(value: object, label: str = "an actor") -> Actor:
    """Build one named actor from its identity and its declared kind."""
    identity, kind = fields(value, 2, label)
    return _declared(Actor, identity=part_text(identity, f"{label} identity"), kind=member(ActorKind, kind, f"{label} kind"))


def identity_value(value: object, label: str = "an identity") -> Identity:
    """Build one opaque identity from its identifier, version and digest."""
    identifier, version, digest = fields(value, 3, label)
    return _declared(Identity, identifier=identifier, version=version, digest=digest)


def reference(kind: ReferenceKind, value: object, label: str) -> ImmutableReference:
    """Build one immutable reference of the kind the route already knows."""
    identifier, version, digest = fields(value, 3, label)
    return _declared(
        ImmutableReference, kind=kind, identifier=identifier, version=version, digest=digest
    )


def provenance(value: object, label: str = "a provenance") -> FactProvenance:
    """Build the artefact, position, extractor and status behind one fact."""
    identifier, version, digest, extractor, kind, status, position = fields(value, 7, label)
    return _declared(
        FactProvenance,
        locator=_declared(
            FactLocator,
            artefact=reference(
                ReferenceKind.INTAKE_ARTEFACT,
                FIELD_SEPARATOR.join((identifier, version, digest)),
                f"{label} artefact",
            ),
            position=part_text(position, f"{label} position"),
        ),
        extracted_by=actor(FIELD_SEPARATOR.join((extractor, kind)), f"{label} extractor"),
        status=member(FactStatus, status, f"{label} fact status"),
    )


def fact(value: object, recorded: FactProvenance, label: str) -> Fact:
    """Build one recorded fact from its value and the provenance behind it."""
    return _declared(Fact, value=part_text(value, label), provenance=recorded)


def schema_declaration(declared: object, written_fields: object) -> SchemaDeclaration:
    """Build one schema declaration from its identity and its written fields."""
    schema_id, version, format_name = fields(declared, 3, "a schema declaration")
    return _declared(
        SchemaDeclaration,
        schema_id=schema_id,
        version=version,
        fields=tuple(
            _schema_field(entry) for entry in entries(written_fields, "a schema field")
        ),
        format_name=format_name,
    )


def _schema_field(value: str) -> SchemaField:
    field_id, value_type, nullable, precision, scale, role = fields(value, 6, "a schema field")
    return _declared(
        SchemaField,
        field_id=field_id,
        value_type=member(SchemaValueType, value_type, "a schema field value type"),
        nullable=_word(NULLABLE_WORDS, nullable, "a schema field nullability"),
        semantic_role=part_text(role, "a schema field semantic role"),
        precision=None if precision == "" else whole_number(precision, "a schema field precision"),
        scale=None if scale == "" else whole_number(scale, "a schema field scale"),
    )


def grain_declaration(declared: object, keys: object) -> GrainDeclaration:
    """Build one grain declaration from its identity and its key fields."""
    grain_id, version, duplicates, population = fields(declared, 4, "a grain declaration")
    return _declared(
        GrainDeclaration,
        grain_id=grain_id,
        version=version,
        key_fields=entries(keys, "a grain key field"),
        population_description=part_text(population, "a grain population description"),
        duplicate_keys_permitted=_word(DUPLICATE_KEY_WORDS, duplicates, "a grain key rule"),
    )


def _word(words: Mapping[str, bool], value: object, label: str) -> bool:
    text = part_text(value, label)
    if text not in words:
        raise _invalid(f"{label} must be one of: " + ", ".join(sorted(words)))
    return words[text]


def _declared(built: type, **declared: object):
    """Build one declared value, carrying its owner's refusal as an integrity refusal."""
    try:
        return built(**declared)
    except (EngagementError, TypeError, ValueError) as error:
        raise _invalid(str(error)) from error


def _evolve(use_case: UseCase, method: str, *declared: object) -> UseCase:
    """Record one declared value on the aggregate, carrying its refusal back."""
    try:
        return getattr(use_case, method)(*declared)
    except EngagementError as error:
        raise _invalid(str(error)) from error


# --- the header and the declaration kinds ------------------------------------


HEADER_PARTS: tuple[str, ...] = (
    "use case reference",
    "engagement identity",
    "engagement mode",
    "consumer",
    "outcome",
    "done definition",
    "cadence",
    "deadline",
    "provenance",
)
DECLARATION_PARTS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "target-output": (
            "output identity",
            "output kind",
            "schema declaration",
            "schema fields",
            "grain declaration",
            "grain keys",
            "output cadence",
            "cutoff semantics",
            "effective-time semantics",
            "stored name",
            "stored column names",
            "replaced output",
            "defining specification",
            "provenance",
        ),
        "dataset": (
            "dataset identity",
            "dataset role",
            "source system",
            "delivery mode",
            "dataset cadence",
            "access owner",
            "classification",
            "availability state",
            "availability subject",
            "provenance",
        ),
        "intermediate-result": (
            "step identity",
            "step description",
            "evidence owner",
            "checkpoint candidate",
            "expected value origin",
            "continuity",
            "provenance",
        ),
        "build-route": (
            "segment identity",
            "build route",
            "target shape",
            "layer",
            "product domain",
            "provenance",
        ),
        "scenario": ("scenario case", "provenance"),
        "authority": ("authority role", "authority actor", "authority subject", "provenance"),
        "condition": (
            "condition key",
            "condition state",
            "condition value",
            "override value",
            "override author",
            "provenance",
        ),
        "intake-artefact": (
            "intake artefact",
            "artefact classification",
            "artefact locator",
            "provenance",
        ),
        "consumer-dependency": (
            "providing use case",
            "consumed product",
            "consumed major version",
            "provenance",
        ),
        "scenario-result": ("scenario case", "verification result", "verification status"),
    }
)
VERSION_PARTS: tuple[str, ...] = (
    "version reference",
    "covered segments",
    "projection reference",
    "scenario case versions",
    "packages",
    "evidence",
    "suggested disposition",
)
ACCEPTANCE_PARTS: tuple[str, ...] = (
    "version identity",
    "decision identity",
    "decided by",
    "decision rationale",
    "case readings",
)
VERSION_KIND = "version"
ACCEPTANCE_KIND = "acceptance"
DECLARATION_KINDS: tuple[str, ...] = tuple(DECLARATION_PARTS)
ENTRY_PARTS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {**DECLARATION_PARTS, VERSION_KIND: VERSION_PARTS, ACCEPTANCE_KIND: ACCEPTANCE_PARTS}
)


def use_case_from_header(parts: tuple[str, ...]) -> UseCase:
    """Open one use case from the parts its header was declared with."""
    read = _read_parts(HEADER_PARTS, parts, "a use-case header")
    recorded = provenance(read["provenance"])
    header = _declared(
        UseCaseHeader,
        engagement_id=part_text(read["engagement identity"], "an engagement identity"),
        engagement_mode=member(EngagementMode, read["engagement mode"], "an engagement mode"),
        consumer=fact(read["consumer"], recorded, "a consumer"),
        outcome=fact(read["outcome"], recorded, "an outcome"),
        done_definition=fact(read["done definition"], recorded, "a done definition"),
        cadence=fact(read["cadence"], recorded, "a cadence"),
        deadline=fact(read["deadline"], recorded, "a deadline"),
    )
    identity = reference(ReferenceKind.USE_CASE, read["use case reference"], "a use case reference")
    try:
        return UseCase.open(identity, header)
    except EngagementError as error:
        raise _invalid(str(error)) from error


def _read_parts(
    labels: tuple[str, ...], parts: tuple[str, ...], subject: str
) -> Mapping[str, str]:
    if len(parts) != len(labels):
        raise _invalid(
            f"{subject} is written as {len(labels)} parts separated by a vertical bar: "
            + ", ".join(labels)
        )
    return dict(zip(labels, parts))


def apply_declaration(use_case: UseCase, kind: str, parts: tuple[str, ...]) -> UseCase:
    """Record one declaration of the named kind on the use case."""
    if kind not in DECLARATION_PARTS:
        raise _invalid("a declaration kind must be one of: " + ", ".join(DECLARATION_KINDS))
    read = _read_parts(DECLARATION_PARTS[kind], parts, f"a {kind} declaration")
    return _DECLARATION_READERS[kind](use_case, read)


def _apply_target_output(use_case: UseCase, read: Mapping[str, str]) -> UseCase:
    replaced = optional_part(read["replaced output"], "a replaced output")
    defining = optional_part(read["defining specification"], "a defining specification")
    declared = _declared(
        TargetOutput,
        output_id=part_text(read["output identity"], "an output identity"),
        kind=part_text(read["output kind"], "an output kind"),
        schema=schema_declaration(read["schema declaration"], read["schema fields"]),
        grain=grain_declaration(read["grain declaration"], read["grain keys"]),
        cadence=part_text(read["output cadence"], "an output cadence"),
        cutoff_semantics=part_text(read["cutoff semantics"], "the cutoff semantics"),
        effective_time_semantics=part_text(
            read["effective-time semantics"], "the effective-time semantics"
        ),
        provenance=provenance(read["provenance"]),
        stored_name=optional_part(read["stored name"], "a stored name"),
        stored_column_names=tuple(
            _stored_column(entry) for entry in entries(read["stored column names"], "a stored column")
        ),
        replaces=None if replaced is None else _replaced_output(replaced),
        defined_by=None if defining is None else identity_value(defining, "a defining specification"),
    )
    return _evolve(use_case, "record_target_output", declared)


def _stored_column(value: str) -> StoredColumnName:
    field_id, stored = fields(value, 2, "a stored column")
    return _declared(StoredColumnName, field_id=field_id, stored_name=stored)


def _replaced_output(value: str) -> ReplacedOutput:
    identifier, version, digest, system, location = fields(value, 5, "a replaced output")
    return _declared(
        ReplacedOutput,
        identity=identity_value(
            FIELD_SEPARATOR.join((identifier, version, digest)), "a replaced output identity"
        ),
        system=part_text(system, "a replaced output system"),
        location=part_text(location, "a replaced output location"),
    )


def _apply_dataset(use_case: UseCase, read: Mapping[str, str]) -> UseCase:
    state = member(AvailabilityState, read["availability state"], "a dataset availability state")
    subject = optional_part(read["availability subject"], "a dataset availability subject")
    declared = _declared(
        DatasetPlaceholder,
        placeholder_id=part_text(read["dataset identity"], "a dataset identity"),
        role=member(DatasetRole, read["dataset role"], "a dataset role"),
        source_system=part_text(read["source system"], "a dataset source system"),
        delivery_mode=part_text(read["delivery mode"], "a dataset delivery mode"),
        cadence=part_text(read["dataset cadence"], "a dataset cadence"),
        access_owner=actor(read["access owner"], "a dataset access owner"),
        classification=part_text(read["classification"], "a dataset classification"),
        availability=_availability(state, subject),
        provenance=provenance(read["provenance"]),
    )
    return _evolve(use_case, "record_dataset", declared)


def _availability(state: AvailabilityState, subject: str | None) -> DatasetAvailability:
    if state is AvailabilityState.OBTAINABLE_BY:
        return _declared(DatasetAvailability, state=state, obtainable_by=subject)
    if subject is None:
        return _declared(DatasetAvailability, state=state)
    return _declared(
        DatasetAvailability,
        state=state,
        dataset=identity_value(subject, "a frozen dataset identity"),
    )


def _apply_intermediate_result(use_case: UseCase, read: Mapping[str, str]) -> UseCase:
    origin = optional_part(read["expected value origin"], "an expected value origin")
    continuity = optional_part(read["continuity"], "a continuity label")
    declared = _declared(
        IntermediateResult,
        result_id=part_text(read["step identity"], "a step identity"),
        description=part_text(read["step description"], "a step description"),
        evidence_owner=actor(read["evidence owner"], "a step evidence owner"),
        provenance=provenance(read["provenance"]),
        checkpoint_candidate=_word(
            CHECKPOINT_WORDS, read["checkpoint candidate"], "a checkpoint candidate"
        ),
        origin=None if origin is None else member(ExpectedOutputOrigin, origin, "an expected value origin"),
        continuity=None if continuity is None else member(ContinuityLabel, continuity, "a continuity label"),
    )
    return _evolve(use_case, "record_intermediate_result", declared)


def _apply_build_route(use_case: UseCase, read: Mapping[str, str]) -> UseCase:
    declared = _declared(
        BuildRouteDeclaration,
        segment_id=part_text(read["segment identity"], "a segment identity"),
        route=member(BuildRoute, read["build route"], "a build route"),
        provenance=provenance(read["provenance"]),
        target_shape=optional_part(read["target shape"], "a target shape"),
        layer=optional_part(read["layer"], "a layer"),
        product_domain=optional_part(read["product domain"], "a product domain"),
    )
    return _evolve(use_case, "record_build_route", declared)


def _apply_scenario(use_case: UseCase, read: Mapping[str, str]) -> UseCase:
    declared = _declared(
        ScenarioReference,
        case=identity_value(read["scenario case"], "a scenario case"),
        provenance=provenance(read["provenance"]),
    )
    return _evolve(use_case, "record_scenario", declared)


def _apply_authority(use_case: UseCase, read: Mapping[str, str]) -> UseCase:
    declared = _declared(
        Authority,
        role=member(AuthorityRole, read["authority role"], "an authority role"),
        actor=actor(read["authority actor"], "an authority actor"),
        provenance=provenance(read["provenance"]),
        subject=optional_part(read["authority subject"], "an authority subject"),
    )
    return _evolve(use_case, "record_authority", declared)


def _apply_condition(use_case: UseCase, read: Mapping[str, str]) -> UseCase:
    key = member(ConditionKey, read["condition key"], "a condition key")
    state = member(ConditionState, read["condition state"], "a condition state")
    override_value = optional_part(read["override value"], "an override value")
    override_author = optional_part(read["override author"], "an override author")
    override = None
    if override_value is not None or override_author is not None:
        override = _declared(
            ConditionOverride,
            value=part_text(override_value, "an override value"),
            author=actor(override_author, "an override author"),
        )
    answered = state is ConditionState.DECLARED
    declared = _declared(
        ConditionDeclaration,
        key=key,
        state=state,
        provenance=provenance(read["provenance"]),
        value=optional_part(read["condition value"], "a condition value"),
        default_value=None if answered else CONDITION_DEFAULTS[key],
        override=override,
    )
    return _evolve(use_case, "record_condition", declared)


def _apply_intake_artefact(use_case: UseCase, read: Mapping[str, str]) -> UseCase:
    declared = _declared(
        IntakeArtefact,
        artefact=reference(
            ReferenceKind.INTAKE_ARTEFACT, read["intake artefact"], "an intake artefact"
        ),
        classification=part_text(read["artefact classification"], "an artefact classification"),
        locator=part_text(read["artefact locator"], "an artefact locator"),
        provenance=provenance(read["provenance"]),
    )
    return _evolve(use_case, "record_intake_artefact", declared)


def _apply_consumer_dependency(use_case: UseCase, read: Mapping[str, str]) -> UseCase:
    declared = _declared(
        ConsumerDependency,
        provider=reference(ReferenceKind.USE_CASE, read["providing use case"], "a providing use case"),
        product_id=part_text(read["consumed product"], "a consumed product"),
        major_version=part_text(read["consumed major version"], "a consumed major version"),
        provenance=provenance(read["provenance"]),
    )
    return _evolve(use_case, "record_consumer_dependency", declared)


def _apply_scenario_result(use_case: UseCase, read: Mapping[str, str]) -> UseCase:
    declared = _declared(
        ScenarioResult,
        case=identity_value(read["scenario case"], "a scenario case"),
        result=reference(
            ReferenceKind.VERIFICATION_RESULT, read["verification result"], "a verification result"
        ),
        status=member(VerificationStatus, read["verification status"], "a verification status"),
    )
    return _evolve(use_case, "record_scenario_result", declared)


_DECLARATION_READERS = MappingProxyType(
    {
        "target-output": _apply_target_output,
        "dataset": _apply_dataset,
        "intermediate-result": _apply_intermediate_result,
        "build-route": _apply_build_route,
        "scenario": _apply_scenario,
        "authority": _apply_authority,
        "condition": _apply_condition,
        "intake-artefact": _apply_intake_artefact,
        "consumer-dependency": _apply_consumer_dependency,
        "scenario-result": _apply_scenario_result,
    }
)


def apply_version(use_case: UseCase, parts: tuple[str, ...]) -> tuple[UseCase, Version]:
    """Cut one version over the spans and values the parts declare."""
    read = _read_parts(VERSION_PARTS, parts, "a version cut")
    try:
        return cut_version(
            use_case,
            reference(ReferenceKind.USE_CASE_VERSION, read["version reference"], "a version reference"),
            entries(read["covered segments"], "a covered segment"),
            reference(
                ReferenceKind.READINESS_PROJECTION,
                read["projection reference"],
                "a projection reference",
            ),
            scenario_case_versions=tuple(
                identity_value(entry, "a scenario case version")
                for entry in entries(read["scenario case versions"], "a scenario case version")
            ),
            packages=tuple(
                reference(ReferenceKind.APPROVED_WORK, entry, "a package")
                for entry in entries(read["packages"], "a package")
            ),
            evidence=tuple(
                reference(ReferenceKind.VERIFICATION_RESULT, entry, "an evidence identity")
                for entry in entries(read["evidence"], "an evidence identity")
            ),
            suggested_disposition=part_text(
                read["suggested disposition"], "a suggested disposition"
            ),
        )
    except EngagementError as error:
        raise _invalid(str(error)) from error


def held_version(use_case: UseCase, identifier: str) -> Version:
    """The one version the record holds under a named identity."""
    version = next(
        (held for held in use_case.versions if held.identity.identifier == identifier), None
    )
    if version is None:
        raise _invalid(f"the use case holds no version named {identifier}")
    return version


def verified_version(
    use_case: UseCase, identifier: str, projection: ReadinessProjection
) -> Version:
    """The held version this reading reproduces, refusing one it does not.

    A version carries the digest of the bytes the projection it was cut on
    rendered. Only a reading that renders those same bytes can say what that
    version's readiness was, so only such a reading may stand an acceptance on
    it. Once the digests agree, the disposition comparison has already run over
    this version as the projection was read.
    """
    version = held_version(use_case, part_text(identifier, "a version identity"))
    if version.readiness_digest != projection_digest(projection):
        raise _refuse(
            RefusalReason.DIGEST_MISMATCH,
            "the supplied reading does not reproduce the readiness that version "
            + version.identity.identifier
            + " was cut on",
        )
    return version


def apply_acceptance(use_case: UseCase, parts: tuple[str, ...], version: Version | None = None):
    """Record one named human acceptance of one version the record holds.

    A caller that is standing new work on the record passes the version it has
    already verified against the reading the record makes now, so no unverified
    version reaches an acceptance. Replaying a stored record passes none: a
    replay reconstructs what was recorded, and every route that reads the
    record checks it against the current reading before anything new stands on
    it.

    The lifecycle moves through the first acceptance only. A version taken on a
    record that already stands accepted is accepted beside the one it holds.
    """
    read = _read_parts(ACCEPTANCE_PARTS, parts, "an acceptance")
    identifier = part_text(read["version identity"], "a version identity")
    if version is None:
        version = held_version(use_case, identifier)
    elif version.identity.identifier != identifier:
        raise _invalid("an acceptance records the version it was verified against")
    decided_by = actor(read["decided by"], "an accepting authority")
    try:
        record = record_acceptance(
            use_case,
            version,
            decision_id=part_text(read["decision identity"], "a decision identity"),
            decided_by=decided_by,
            rationale=reference(
                ReferenceKind.DECISION_RATIONALE, read["decision rationale"], "a decision rationale"
            ),
            cases=tuple(
                _case_reading(entry) for entry in entries(read["case readings"], "a case reading")
            ),
        )
        return _accepted(use_case, record), record
    except EngagementError as error:
        raise _invalid(str(error)) from error


def _accepted(use_case: UseCase, record: AcceptanceRecord) -> UseCase:
    """Put one named acceptance on the record, moving the lifecycle once.

    A use case reaches accepted once. The first acceptance takes it there
    through the moves the aggregate declares, so a record whose scenario does
    not pass, and a record that has been superseded, are refused exactly as
    they were. A record that already stands accepted, in service or not, takes
    a later version's acceptance beside the one it holds, through the
    aggregate's own verb for it. The state the record carries is the only thing
    read here, and the aggregate owns every rule either verb applies, including
    that one version is accepted once.
    """
    decision = record.decision
    if use_case.state not in ACCEPTED_STATES:
        return use_case.verify(decision.decided_by).accept(decision)
    return use_case.take_acceptance(decision)


def _case_reading(value: str) -> CaseEvidence:
    identifier, version, digest, reading = fields(value, 4, "a case reading")
    return _declared(
        CaseEvidence,
        case=identity_value(
            FIELD_SEPARATOR.join((identifier, version, digest)), "a case reading identity"
        ),
        evidence_provenance=member(EvidenceProvenance, reading, "a case evidence reading"),
    )


def apply_entry(use_case: UseCase, line: str) -> UseCase:
    """Apply one recorded line, whatever kind of change it recorded."""
    kind, parts = read_entry(line)
    if kind == VERSION_KIND:
        return apply_version(use_case, parts)[0]
    if kind == ACCEPTANCE_KIND:
        return apply_acceptance(use_case, parts)[0]
    return apply_declaration(use_case, kind, parts)


def write_entry(kind: str, parts: tuple[str, ...]) -> str:
    """Write one change as the line a record holds for it."""
    if kind not in ENTRY_PARTS:
        raise _invalid("an entry kind must be one of: " + ", ".join(ENTRY_PARTS))
    _read_parts(ENTRY_PARTS[kind], parts, f"a {kind} entry")
    return PART_SEPARATOR.join((kind, *parts))


def read_entry(line: str) -> tuple[str, tuple[str, ...]]:
    """Read one recorded line back into the kind and parts it was written from."""
    kind, _, remainder = line.partition(PART_SEPARATOR)
    if kind not in ENTRY_PARTS:
        raise _refuse(
            RefusalReason.MALFORMED_RECORD,
            "a recorded entry names a kind the record form does not declare: " + kind,
        )
    return kind, tuple(remainder.split(PART_SEPARATOR))


# --- the records root and the record itself ----------------------------------


def records_root(repository: object, root: object) -> Path:
    """Resolve the records root, refusing one outside the work directory."""
    base = Path(part_text(str(repository), "a repository")).resolve()
    named = Path(part_text(str(root), "a records root"))
    resolved = (named if named.is_absolute() else base / named).resolve()
    work = (base / WORK_ROOT).resolve()
    if resolved != work and work not in resolved.parents:
        raise _refuse(
            RefusalReason.RECORD_OUTSIDE_WORK,
            f"a records root sits in or under the {WORK_ROOT} directory of the repository",
        )
    return resolved


def record_path(root: Path, engagement_id: str, use_case_id: str) -> Path:
    """Name the one record file that holds one use case."""
    return root / _segment(engagement_id, "an engagement identity") / (
        _segment(use_case_id, "a use case identity") + RECORD_SUFFIX
    )


def _segment(value: object, label: str) -> str:
    text = part_text(value, label)
    if not PATH_SEGMENT.fullmatch(text):
        raise _invalid(f"{label} must be a plain name a directory can carry")
    return text


def render_record(header: str, recorded: tuple[str, ...]) -> str:
    """Render one record as the canonical readable projection of its facts."""
    return render_record_projection(_record_facts(header, recorded))


def _record_facts(header: str, recorded: tuple[str, ...]) -> Mapping[str, object]:
    return {"form": RECORD_FORM, "header": header, "entry": recorded}


def record_lines(text: str) -> tuple[tuple[str, str], ...]:
    """Read one written record into its recorded facts, in the order it wrote them.

    This is the one place a record's lines are read, so every record this
    module holds refuses a line that is not one recorded fact for the same
    reason and in the same words.
    """
    read: list[tuple[str, str]] = []
    for line in text.splitlines():
        match = RECORD_LINE.fullmatch(line)
        if match is None:
            raise _refuse(RefusalReason.MALFORMED_RECORD, "a record holds one recorded fact per line")
        read.append((match.group("field"), match.group("value")))
    return tuple(read)


def read_record(text: str) -> tuple[str, tuple[str, ...]]:
    """Read one stored record, refusing anything but its canonical projection."""
    read = record_lines(text)
    names = [name for name, _ in read]
    if names[:2] != list(RECORD_FIELDS[:2]) or any(name != RECORD_FIELDS[2] for name in names[2:]):
        raise _refuse(
            RefusalReason.MALFORMED_RECORD,
            "a record states its form, then its header, then one line for each entry",
        )
    recorded = tuple(value for _, value in read[2:])
    if recorded == (EMPTY_LIST,):
        recorded = ()
    header = read[1][1]
    if validate_record_projection(text, _record_facts(header, recorded)):
        raise _refuse(
            RefusalReason.MALFORMED_RECORD, "a record is the canonical projection of its own facts"
        )
    if read[0][1] != RECORD_FORM:
        raise _refuse(RefusalReason.MALFORMED_RECORD, "a record declares a form this reader knows")
    return header, recorded


def load_use_case(
    repository: object, root: object, engagement_id: str, use_case_id: str
) -> tuple[UseCase, str, tuple[str, ...], Path]:
    """Read one held record and replay it into the use case it records."""
    path = record_path(records_root(repository, root), engagement_id, use_case_id)
    if not path.is_file():
        raise _refuse(
            RefusalReason.UNKNOWN_ENGAGEMENT,
            f"no record is held for {use_case_id} under engagement {engagement_id}",
        )
    header, recorded = read_record(path.read_text(encoding="ascii"))
    use_case = use_case_from_header(tuple(header.split(PART_SEPARATOR)))
    if use_case.header.engagement_id != engagement_id or use_case.identity.identifier != use_case_id:
        raise _refuse(
            RefusalReason.MALFORMED_RECORD,
            "a record is held under the engagement and use case its header names",
        )
    for line in recorded:
        use_case = apply_entry(use_case, line)
    return use_case, header, recorded, path


def store_use_case(path: Path, header: str, recorded: tuple[str, ...]) -> None:
    """Write one record as the canonical projection of the facts it holds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_record(header, recorded), encoding="ascii", newline="\n")


# --- the case index the readiness routes are given ---------------------------


def case_index(
    use_case: UseCase,
    *,
    case_datasets: tuple[str, ...] = (),
    case_expected_outputs: tuple[str, ...] = (),
    case_checkpoints: tuple[str, ...] = (),
    case_statuses: tuple[str, ...] = (),
) -> Mapping[Identity, CaseFacts]:
    """Build the case index readiness reads, from the words a caller supplied.

    Each written line names a scenario case the record already references, so
    the facts a case supplies cannot name a case the use case does not hold.
    """
    referenced = {scenario.case.identifier: scenario.case for scenario in use_case.scenarios}
    datasets: dict[str, list[CaseDataset]] = {}
    outputs: dict[str, list[CaseExpectedOutput]] = {}
    checkpoints: dict[str, list[str]] = {}
    statuses: dict[str, VerificationStatus] = {}
    for line in case_datasets:
        case, dataset_id, role, written = fields(line, 4, "a case dataset")
        datasets.setdefault(_case(referenced, case), []).append(
            _declared(
                CaseDataset,
                dataset_id=dataset_id,
                role=member(DatasetRole, role, "a case dataset role"),
                provenance=member(DatasetProvenance, written, "a case dataset provenance"),
            )
        )
    for line in case_expected_outputs:
        case, output_id, written, origin = fields(line, 4, "a case expected output")
        outputs.setdefault(_case(referenced, case), []).append(
            _declared(
                CaseExpectedOutput,
                output_id=output_id,
                provenance=member(DatasetProvenance, written, "a case expected output provenance"),
                origin=None
                if origin == ""
                else member(ExpectedOutputOrigin, origin, "a case expected output origin"),
            )
        )
    for line in case_checkpoints:
        case, checkpoint = fields(line, 2, "a case checkpoint")
        checkpoints.setdefault(_case(referenced, case), []).append(
            part_text(checkpoint, "a case checkpoint")
        )
    for line in case_statuses:
        case, written = fields(line, 2, "a case result status")
        statuses[_case(referenced, case)] = member(
            VerificationStatus, written, "a case result status"
        )
    return {
        case: _declared(
            CaseFacts,
            datasets=tuple(datasets.get(identifier, ())),
            expected_outputs=tuple(outputs.get(identifier, ())),
            checkpoints=tuple(checkpoints.get(identifier, ())),
            result_status=statuses.get(identifier),
        )
        for identifier, case in referenced.items()
    }


def _case(referenced: Mapping[str, Identity], identifier: str) -> str:
    if identifier not in referenced:
        raise _invalid(f"the use case references no scenario case named {identifier}")
    return identifier


def read_readiness(use_case: UseCase, index: Mapping[Identity, CaseFacts]) -> ReadinessProjection:
    """Project the readiness of one use case and check the versions it holds.

    A version carries the digest of the exact bytes the projection it was cut
    on rendered. When a stored version carries the digest of this projection,
    it was cut on this reading, so the disposition it stores must still be the
    text this reading owns; anything else means the stored record was changed
    after the cut, and it is refused. A version carrying another digest was cut
    on a reading this record no longer produces, so nothing is compared for it,
    and a route that needs a current version is already held to the digest rule
    at the cut.
    """
    try:
        projection = project_readiness(use_case, index)
    except ValueError as error:
        raise _invalid(str(error)) from error
    digest = projection_digest(projection)
    for version in use_case.versions:
        if version.readiness_digest != digest:
            continue
        if version.suggested_disposition != projection.suggested_disposition:
            raise _refuse(
                RefusalReason.DISPOSITION_MISMATCH,
                "the disposition stored on version "
                + version.identity.identifier
                + " is not the text readiness owns",
            )
    return projection


# --- the routes --------------------------------------------------------------


def open_use_case(
    *,
    repository: object,
    root: object,
    header_parts: tuple[str, ...],
) -> RouteResult:
    """Open one use case and hold it in a new record.

    The header names the engagement the record is held under, so the record
    sits where the use case says it belongs and nowhere else.
    """
    use_case = use_case_from_header(header_parts)
    engagement_id = use_case.header.engagement_id
    path = record_path(
        records_root(repository, root), engagement_id, use_case.identity.identifier
    )
    if path.exists():
        raise _invalid(
            f"a record is already held for {use_case.identity.identifier} under engagement {engagement_id}"
        )
    header = PART_SEPARATOR.join(header_parts)
    store_use_case(path, header, ())
    return RouteResult(
        command="use-case open",
        values=(
            ("engagement", engagement_id),
            ("use case", use_case.identity.identifier),
            ("state", use_case.state.value),
            ("record", _relative(repository, path)),
        ),
    )


def record_fact(
    *,
    repository: object,
    root: object,
    engagement_id: str,
    use_case_id: str,
    kind: str,
    declared_fields: object = (),
) -> RouteResult:
    """Record one declaration of any kind the use-case record holds."""
    parts = declaration_parts(kind, named_fields(declared_fields, "a declared field"))
    use_case, header, recorded, path = load_use_case(repository, root, engagement_id, use_case_id)
    line = write_entry(kind, parts)
    updated = apply_declaration(use_case, kind, parts)
    store_use_case(path, header, (*recorded, line))
    return RouteResult(
        command="use-case record-fact",
        values=(
            ("use case", use_case_id),
            ("kind", kind),
            ("subject", parts[0]),
            ("revision", updated.revision),
            ("record", _relative(repository, path)),
        ),
    )


def read_use_case_readiness(
    *,
    repository: object,
    root: object,
    engagement_id: str,
    use_case_id: str,
    case_datasets: tuple[str, ...] = (),
    case_expected_outputs: tuple[str, ...] = (),
    case_checkpoints: tuple[str, ...] = (),
    case_statuses: tuple[str, ...] = (),
) -> RouteResult:
    """Report the readiness of one held use case."""
    use_case, _, _, _ = load_use_case(repository, root, engagement_id, use_case_id)
    projection = read_readiness(
        use_case,
        case_index(
            use_case,
            case_datasets=case_datasets,
            case_expected_outputs=case_expected_outputs,
            case_checkpoints=case_checkpoints,
            case_statuses=case_statuses,
        ),
    )
    return RouteResult(
        command="use-case readiness",
        values=(
            ("use case", use_case_id),
            ("readiness digest", projection_digest(projection)),
            ("buildable", projection.buildable),
            ("acceptable now", projection.acceptable_now),
            ("suggested disposition", projection.suggested_disposition),
        ),
        projection=projection,
    )


def synthesise_dataset(*, document: str, seed: str, generator_version: str) -> RouteResult:
    """Generate one labelled dataset from a constraint request document."""
    try:
        request = read_request(document)
        generated = generate(
            request.schema,
            request.grain,
            request.keys,
            request.constraints,
            part_text(seed, "a seed"),
            part_text(generator_version, "a generator version"),
        )
    except CompositionError:
        raise
    except GenerationRefusal as refusal:
        raise _invalid(
            f"a request document the generator refused: {refusal.reason.value}"
        ) from None
    dataset = generated.dataset
    written = dataset.synthetic_provenance
    return RouteResult(
        command="use-case synthesise-dataset",
        values=(
            ("dataset", dataset.dataset_id),
            ("version", dataset.version),
            ("role", dataset.role.value),
            ("provenance", dataset.provenance.value),
            ("rows", dataset.row_count),
            ("content digest", dataset.content_digest),
            ("generator", written.generator_id),
            ("generator version", written.generator_version),
            ("seed", written.seed),
            ("constraints digest", written.constraints_digest),
            ("constrained by", [source.identifier for source in written.constrained_by]),
        ),
    )


def cut_use_case_version(
    *,
    repository: object,
    root: object,
    engagement_id: str,
    use_case_id: str,
    version_reference: str,
    covered_segments: str,
    projection_reference: str,
    readiness_digest: str,
    scenario_case_versions: str = "",
    packages: str = "",
    evidence: str = "",
    case_datasets: tuple[str, ...] = (),
    case_expected_outputs: tuple[str, ...] = (),
    case_checkpoints: tuple[str, ...] = (),
    case_statuses: tuple[str, ...] = (),
) -> RouteResult:
    """Cut one version on a recomputed readiness projection.

    The projection is computed again here and its digest compared with the one
    the caller states, so a version is never cut on a reading nobody can
    reproduce. The disposition stored on the new version is the text this
    reading owns, and every version the record already holds is checked against
    that text as the record is read.
    """
    use_case, header, recorded, path = load_use_case(repository, root, engagement_id, use_case_id)
    projection = read_readiness(
        use_case,
        case_index(
            use_case,
            case_datasets=case_datasets,
            case_expected_outputs=case_expected_outputs,
            case_checkpoints=case_checkpoints,
            case_statuses=case_statuses,
        ),
    )
    recomputed = projection_digest(projection)
    stated = part_text(readiness_digest, "a readiness digest")
    if recomputed != stated:
        raise _refuse(
            RefusalReason.DIGEST_MISMATCH,
            "the readiness projection of this record does not have the digest the cut states",
        )
    identifier, version_name = fields(projection_reference, 2, "a projection reference")
    parts = (
        part_text(version_reference, "a version reference"),
        covered_segments,
        FIELD_SEPARATOR.join((identifier, version_name, recomputed)),
        scenario_case_versions,
        packages,
        evidence,
        projection.suggested_disposition,
    )
    line = write_entry(VERSION_KIND, parts)
    updated, version = apply_version(use_case, parts)
    store_use_case(path, header, (*recorded, line))
    return RouteResult(
        command="use-case cut-version",
        values=(
            ("use case", use_case_id),
            ("version", version.identity.identifier),
            ("readiness digest", version.readiness_digest),
            ("suggested disposition", version.suggested_disposition),
            ("covered segments", list(version.covered_segments)),
            ("covered outputs", list(version.covered_outputs)),
            ("segments outside", list(version.segments_outside)),
            ("revision", updated.revision),
            ("record", _relative(repository, path)),
        ),
    )


def record_use_case_acceptance(
    *,
    repository: object,
    root: object,
    engagement_id: str,
    use_case_id: str,
    version_identity: str,
    decision_identity: str,
    decided_by: str,
    rationale: str,
    case_readings: str = "",
    case_datasets: tuple[str, ...] = (),
    case_expected_outputs: tuple[str, ...] = (),
    case_checkpoints: tuple[str, ...] = (),
    case_statuses: tuple[str, ...] = (),
) -> RouteResult:
    """Record one named human acceptance of one version the record holds.

    The readiness of the record is read first, with the case facts the caller
    supplies. The version being accepted must be the one that reading
    reproduces, so a caller cannot disarm the check by reading the record
    differently from the way the version was cut; and because the digests then
    agree, the reading has already compared the disposition the version stores
    byte for byte. The route reports the text of that verified reading.
    """
    use_case, header, recorded, path = load_use_case(repository, root, engagement_id, use_case_id)
    projection = read_readiness(
        use_case,
        case_index(
            use_case,
            case_datasets=case_datasets,
            case_expected_outputs=case_expected_outputs,
            case_checkpoints=case_checkpoints,
            case_statuses=case_statuses,
        ),
    )
    version = verified_version(use_case, version_identity, projection)
    parts = (
        part_text(version_identity, "a version identity"),
        part_text(decision_identity, "a decision identity"),
        part_text(decided_by, "an accepting authority"),
        part_text(rationale, "a decision rationale"),
        case_readings,
    )
    line = write_entry(ACCEPTANCE_KIND, parts)
    updated, record = apply_acceptance(use_case, parts, version)
    store_use_case(path, header, (*recorded, line))
    return RouteResult(
        command="use-case record-acceptance",
        values=(
            ("use case", use_case_id),
            ("version", record.version.identifier),
            ("decision", record.decision.decision_id),
            ("decided by", record.decision.decided_by.identity),
            ("evidence provenance", record.evidence_provenance.value),
            ("suggested disposition", projection.suggested_disposition),
            ("state", updated.state.value),
            ("record", _relative(repository, path)),
        ),
    )


def pinax_runner():
    """The runner the gap route drives when a caller supplies none."""
    return SubprocessPinaxRunner()


def project_use_case_gaps(
    *,
    repository: object,
    root: object,
    engagement_id: str,
    use_case_id: str,
    actor_handle: str,
    prefix: str = "evd",
    tracker_repository: object = None,
    runner: object = None,
    case_datasets: tuple[str, ...] = (),
    case_expected_outputs: tuple[str, ...] = (),
    case_checkpoints: tuple[str, ...] = (),
    case_statuses: tuple[str, ...] = (),
) -> RouteResult:
    """Project the readiness gaps of one held use case as tracked work."""
    use_case, _, _, _ = load_use_case(repository, root, engagement_id, use_case_id)
    projection = read_readiness(
        use_case,
        case_index(
            use_case,
            case_datasets=case_datasets,
            case_expected_outputs=case_expected_outputs,
            case_checkpoints=case_checkpoints,
            case_statuses=case_statuses,
        ),
    )
    projector = _projector(actor_handle, prefix, runner)
    target = Path(str(repository if tracker_repository is None else tracker_repository))
    try:
        result = projector.project(
            (UseCaseScope(use_case=use_case, readiness=projection),), repository=target
        )
    except PinaxProjectionError as error:
        raise _invalid(str(error)) from error
    projected = result.use_cases[0]
    return RouteResult(
        command="use-case project-gaps",
        values=(
            ("use case", projected.identity.use_case_id),
            ("engagement", projected.identity.engagement_id),
            ("parent item", projected.parent_item),
            ("gap items", [item for _, item in projected.gap_items]),
            ("stale gap items", [item.item_id for item in result.stale_gap_items]),
        ),
        projection=projection,
    )


def _projector(actor_handle: str, prefix: str, runner: object) -> PinaxContractProjector:
    try:
        return PinaxContractProjector(
            runner if runner is not None else pinax_runner(),
            actor=part_text(actor_handle, "an actor handle"),
            prefix=part_text(prefix, "a tracker item prefix"),
        )
    except PinaxProjectionError as error:
        raise _invalid(str(error)) from error


def _relative(repository: object, path: Path) -> str:
    """Report a written record by its repository-relative name and nothing more."""
    return path.resolve().relative_to(Path(str(repository)).resolve()).as_posix()


# --- the verification case routes ---------------------------------------------
#
# These routes read approved verification material, drive the verification
# workflows over it, and write down what those workflows decided. Nothing here
# decides anything about a case: no comparison, no status, no fault class and
# no disclosure rule is stated in this module. Every value a route reports is
# read off a workflow outcome, and every line a route writes is written by the
# verification presentation surface that owns bounded reporting.
#
# An environment names its own adapters. A route takes a logical identity and
# never a path, and the configuration document below is the one place an
# identity becomes a shipped adapter over a directory the environment holds.


# The one directory the case records of one engagement sit under.
CASE_DIRECTORY = "cases"
# The document an environment writes to name the adapters it offers.
ADAPTER_DOCUMENT = "adapters.json"
ADAPTER_CONFIGURATION_FORM = "evorthon.verification.adapters.v1"
# The document that carries the material one run is compared over.
RUN_MATERIAL_FORM = "evorthon.verification.material.v1"
# The one shipped adapter family an environment configures.
FIXTURE_FAMILY = "fixture"
EVIDENCE_FAMILIES = MappingProxyType({FIXTURE_FAMILY: FixtureEvidenceRepository})
CANDIDATE_FAMILIES = MappingProxyType({FIXTURE_FAMILY: FixtureCandidateRunner})
# The keyword each port contract is handed to the conformance suite under.
EVIDENCE_CONTRACT = "evidence_repository"
CANDIDATE_CONTRACT = "candidate_runner"
# The names the records these routes write are held under. A packet record is
# named after the output it answers for; a diagnosis that answers for no output
# at all carries the case's own one name.
INTAKE_RECORD = "intake.md"
OUTCOME_RECORD = "outcome.md"
PACKET_RECORD = "fault-{output}.md"
DIAGNOSIS_RECORD = "diagnosis.md"
# The label one diagnosis reports its disclosure decision under, the one rule
# for reading whether that decision withholds its packet, the one reading of
# the closed decisions a diagnosis reports, and the status a verified run
# reports when nothing it answered failed. All four are read off the
# presentation surface that reads them off the core, so no route here states a
# decision or a status of its own and a caller driving further work off one run
# reads the same words.
DISCLOSURE_LABEL = verification_presentation.DISCLOSURE_LABEL
PASSED = verification_presentation.PASSED
withheld_decision = verification_presentation.withheld_decision
diagnosis_decision = verification_presentation.diagnosis_decision
# The record fields the diagnosis route reads the recorded run from, named by
# the surface that wrote them, and the digest of the whole contract that run
# answered.
FAILED_OUTPUT_FIELD = verification_presentation.OUTCOME_FAILED_OUTPUT_FIELD
RESULT_DIGEST_FIELD = verification_presentation.OUTCOME_RESULT_DIGEST_FIELD
OUTCOME_DIGEST_FIELD = verification_presentation.OUTCOME_DIGEST_FIELD

# What this module reports each closed workflow refusal as. The tables are
# total and the checks below say so, so a reason a workflow adds cannot be
# reported under a word that was written for another one.
INTAKE_REASONS = MappingProxyType(
    {
        IntakeRefusalReason.CASE_INVALID: RefusalReason.MALFORMED_RECORD,
        IntakeRefusalReason.EVIDENCE_MISSING: RefusalReason.RECORD_NOT_HELD,
        IntakeRefusalReason.EVIDENCE_ALTERED: RefusalReason.EVIDENCE_DIGEST_MISMATCH,
        IntakeRefusalReason.EVIDENCE_INCONSISTENT: RefusalReason.EVIDENCE_DIGEST_MISMATCH,
        IntakeRefusalReason.EVIDENCE_EXPIRED: RefusalReason.MALFORMED_VALUE,
        IntakeRefusalReason.CANDIDATE_INCONSISTENT: RefusalReason.MALFORMED_VALUE,
    }
)
# The one privacy refusal no route ever carries. A withheld packet is reported
# as the completed decision it is, by every route that holds one, before any
# boundary is asked about it, so the gate's own withheld refusal never reaches
# a caller and has no word here.
REPORTED_PRIVACY_REASONS = frozenset({PrivacyRefusalReason.DISCLOSURE_WITHHELD})
PRIVACY_REASONS = MappingProxyType(
    {
        PrivacyRefusalReason.UNRESOLVED_PACKET: RefusalReason.MALFORMED_RECORD,
        PrivacyRefusalReason.CONTRADICTORY_PACKET: RefusalReason.MALFORMED_RECORD,
        PrivacyRefusalReason.DECLARED_BOUND_EXCEEDED: RefusalReason.MALFORMED_VALUE,
        PrivacyRefusalReason.LOCAL_PATH: RefusalReason.MALFORMED_VALUE,
        PrivacyRefusalReason.CREDENTIAL: RefusalReason.MALFORMED_VALUE,
        PrivacyRefusalReason.RAW_ROW: RefusalReason.MALFORMED_VALUE,
        PrivacyRefusalReason.SINGLETON_VALUE: RefusalReason.MALFORMED_VALUE,
        PrivacyRefusalReason.REVERSIBLE_DIGEST: RefusalReason.MALFORMED_VALUE,
    }
)
if frozenset(INTAKE_REASONS) != frozenset(IntakeRefusalReason):  # pragma: no cover
    raise RuntimeError("every intake refusal reason is reported under one declared reason")
if frozenset(PRIVACY_REASONS) | REPORTED_PRIVACY_REASONS != frozenset(PrivacyRefusalReason):  # pragma: no cover
    raise RuntimeError("every privacy refusal reason is reported or carried under one declared reason")
if frozenset(PRIVACY_REASONS) & REPORTED_PRIVACY_REASONS:  # pragma: no cover
    raise RuntimeError("a privacy refusal a route reports is not also carried as a refusal")

# The refusals a verification engine is allowed to raise. Anything else is a
# fault in this product and leaves as itself rather than as a refusal.
ENGINE_REFUSALS = (
    CanonicalisationRefusal,
    ContractRefused,
    PolicyChangedAfterObservationError,
    PortRefusal,
    ReconciliationRefused,
    VerificationContractError,
)
DIAGNOSIS_REFUSALS = (
    FaultRefused,
    LocalisationRefused,
    PortRefusal,
    ReplayRefused,
    VerificationContractError,
)


def _held_place(named: object, label: str) -> Path:
    """Read one place a document names, refusing anything but a relative one.

    A configuration document names a place inside the records root the caller
    already gave, so an absolute form, a lettered volume and a share host are
    all refused before anything is resolved. The written form is read in both
    path flavours, so the refusal is the same on every host and never depends
    on which forms the host's own path rules recognise. The refusal says which
    declaration was refused and never what it carried.
    """
    text = part_text(str(named), label)
    lettered = PureWindowsPath(text)
    rooted = PurePosixPath(text)
    if lettered.drive or lettered.root or rooted.root:
        raise _refuse(
            RefusalReason.MALFORMED_RECORD,
            f"{label} is written as a place relative to the records root",
        )
    return Path(text)


def _inside(base: Path, named: object, label: str) -> Path:
    """Resolve one named place under a base, refusing one that leaves it."""
    written = Path(part_text(str(named), label))
    resolved = (written if written.is_absolute() else base / written).resolve()
    if resolved != base and base not in resolved.parents:
        raise _refuse(
            RefusalReason.RECORD_OUTSIDE_WORK,
            f"{label} sits in or under the records root",
        )
    return resolved


def case_directory(root: Path, engagement_id: str, case_id: str) -> Path:
    """Name the one directory that holds the records of one case."""
    return (
        root
        / _segment(engagement_id, "an engagement identity")
        / CASE_DIRECTORY
        / _segment(case_id, "a case identity")
    )


def _listed(entries: object) -> str:
    """Write a bounded list of declared reasons as the sentence a refusal carries."""
    return "; ".join(verification_presentation.capped(tuple(entries)))


def _issue_detail(issues: object) -> str:
    return _listed(f"{issue.path} {issue.code}" for issue in issues)


def _declared_document(path: Path, form: str, label: str) -> Mapping[str, object]:
    """Read one declared document, refusing anything but the form it names."""
    text = read_document(path)
    try:
        declared = json.loads(text)
    except ValueError as error:
        raise _refuse(
            RefusalReason.MALFORMED_RECORD, f"{label} is written as one declared object: {error}"
        ) from None
    if not isinstance(declared, Mapping) or declared.get("form") != form:
        raise _refuse(RefusalReason.MALFORMED_RECORD, f"{label} declares the form {form}")
    return declared


def _declared_entries(declared: Mapping[str, object], name: str, label: str) -> tuple:
    entries = declared.get(name) or ()
    if not isinstance(entries, (list, tuple)) or not all(
        isinstance(entry, Mapping) for entry in entries
    ):
        raise _invalid(f"{label} is written as a list of declared objects")
    return tuple(entries)


def _declared_record(value: object, declared: type, label: str) -> object:
    """Rehydrate one domain record through the one deserializer that owns the form."""
    if not isinstance(value, Mapping):
        raise _invalid(f"{label} is written as one declared record envelope")
    try:
        record = deserialize_record(value)
    except SerializationError as error:
        raise _refuse(
            RefusalReason.MALFORMED_RECORD, f"{label} is a readable record: {error}"
        ) from None
    except VerificationContractError as error:
        raise _refuse(
            RefusalReason.MALFORMED_RECORD,
            f"{label} is a record the validator accepts: {_issue_detail(error.issues)}",
        ) from None
    if not isinstance(record, declared):
        raise _invalid(f"{label} declares a {declared.__name__}")
    return record


def _declared_json(root: Path, document: object, declared: type, label: str):
    """Read one declared domain document through the one deserializer that owns the form.

    Every document a route reads sits under the records root, is read as the
    record its own wire schema declares, and is refused with the validator's
    issues when it is not one. No refusal detail carries a declared value.
    """
    text = read_document(_inside(root, document, label))
    try:
        record = deserialize_json(text)
    except SerializationError as error:
        raise _refuse(
            RefusalReason.MALFORMED_RECORD, f"{label} is a readable record: {error}"
        ) from None
    except VerificationContractError as error:
        raise _refuse(
            RefusalReason.MALFORMED_RECORD,
            f"{label} is one the validator accepts: {_issue_detail(error.issues)}",
        ) from None
    if not isinstance(record, declared):
        raise _refuse(RefusalReason.MALFORMED_RECORD, f"{label} declares a {declared.__name__}")
    return record


def read_case(root: Path, document: object) -> VerificationCase:
    """Read one approved case document, refused as invalid with the validator's issues."""
    record = _declared_json(root, document, VerificationCase, "a case document")
    issues = inspect_verification_case(record).issues
    if issues:
        raise _refuse(
            RefusalReason.MALFORMED_RECORD,
            f"a case document is one the validator accepts: {_issue_detail(issues)}",
        )
    return record


def read_adapter_configuration(root: Path, engagement_id: str) -> Mapping[str, Mapping]:
    """Read the document an environment writes to name the adapters it offers."""
    path = root / _segment(engagement_id, "an engagement identity") / ADAPTER_DOCUMENT
    if not path.is_file():
        raise _refuse(
            RefusalReason.RECORD_NOT_HELD,
            f"no adapter configuration is held for engagement {engagement_id}",
        )
    declared = _declared_document(path, ADAPTER_CONFIGURATION_FORM, "an adapter configuration")
    adapters = declared.get("adapters")
    if not isinstance(adapters, Mapping) or not all(
        isinstance(entry, Mapping) for entry in adapters.values()
    ):
        raise _refuse(
            RefusalReason.MALFORMED_RECORD,
            "an adapter configuration names one shipped family and one held directory per identity",
        )
    return adapters


def resolve_adapter(
    root: Path,
    configuration: Mapping[str, Mapping],
    identity: object,
    *,
    label: str,
    families: Mapping[str, type],
    contract: str,
):
    """Resolve one logical identity into a shipped adapter the suite has read."""
    declared = configuration.get(part_text(identity, label))
    if declared is None:
        raise _invalid(f"{label} is one the adapter configuration names")
    built = families.get(declared.get("family"))
    if built is None:
        raise _invalid(f"{label} names a shipped adapter family: {', '.join(sorted(families))}")
    directory = _held_place(declared.get("directory"), f"{label} directory")
    adapter = built(_inside(root, directory, f"{label} directory"))
    report = check_conformance(**{contract: adapter})
    if not report.conformant:
        raise _refuse(
            RefusalReason.MALFORMED_RECORD,
            f"{label} answers the contract it claims: "
            + _listed(f"{finding.member} {finding.reason.value}" for finding in report.findings),
        )
    return adapter


def resolve_adapters(root: Path, engagement_id: str, evidence_identity, candidate_identity):
    """Resolve both environment adapters one run reads through."""
    configuration = read_adapter_configuration(root, engagement_id)
    return (
        resolve_adapter(
            root,
            configuration,
            evidence_identity,
            label="an evidence adapter",
            families=EVIDENCE_FAMILIES,
            contract=EVIDENCE_CONTRACT,
        ),
        resolve_adapter(
            root,
            configuration,
            candidate_identity,
            label="a candidate adapter",
            families=CANDIDATE_FAMILIES,
            contract=CANDIDATE_CONTRACT,
        ),
    )


def _declared_rows(declared: object, schema: SchemaDeclaration, label: str):
    """Read written rows into the value types the declared schema states."""
    if declared is None:
        declared = ()
    if not isinstance(declared, (list, tuple)):
        raise _invalid(f"{label} is written as a list of declared rows")
    index = {field.field_id: field for field in schema.fields}
    rows = []
    for entry in declared:
        if not isinstance(entry, Mapping):
            raise _invalid(f"{label} is written as a list of declared rows")
        unknown = sorted(set(entry) - set(index))
        if unknown:
            raise _invalid(
                f"{label} names fields the schema does not declare: {', '.join(unknown)}"
            )
        read: dict[str, object] = {}
        for name in entry:
            field = index[name]
            try:
                read[name] = typed_value(entry[name], field)
            except (ArithmeticError, AttributeError, TypeError, ValueError):
                raise _invalid(
                    f"{label} carries a value the field {field.field_id} cannot take as "
                    f"the {field.value_type.value} it declares"
                ) from None
        rows.append(read)
    return tuple(rows)


def _clause_observation(entry: Mapping[str, object]):
    """Read one declared clause observation: facts observed, or a result presented."""
    clause_id = part_text(entry.get("clause"), "a clause identity")
    if "basis" in entry:
        return PresentedObservation(
            clause_id=clause_id,
            basis=member(EvidenceBasis, entry.get("basis"), "an evidence basis"),
            presented_status=member(VerificationStatus, entry.get("status"), "a presented status"),
            assurance_reference=optional_part(entry.get("assurance"), "an assurance reference"),
        )
    values = entry.get("values")
    if not isinstance(values, Mapping):
        raise _invalid("an executed clause observation declares the values it was executed over")
    observed = {}
    for name, value in values.items():
        observed[part_text(name, "an observed field")] = (
            None if value is None else part_text(value, "an observed value")
        )
    return ExecutedObservation(clause_id=clause_id, observed_values=observed)


def read_run_material(root: Path, document: object, case: VerificationCase):
    """Read the material one run is compared over, in the values the workflows take."""
    declared = _declared_document(
        _inside(root, document, "a material document"), RUN_MATERIAL_FORM, "a material document"
    )
    approved = {output.output_id: output for output in case.expected_outputs}
    expected = {}
    for entry in _declared_entries(declared, "expected", "the approved material"):
        named = part_text(entry.get("output"), "an expected output")
        output = approved.get(named)
        if output is None:
            raise _invalid("an approved material entry names an output the case declares")
        expected[named] = ExpectedMaterial(
            output, _declared_rows(entry.get("rows"), output.schema, "the approved rows")
        )
    observed = {}
    for entry in _declared_entries(declared, "observed", "the observed material"):
        output = _declared_record(entry.get("output"), ActualOutput, "an observed output")
        observed[output.output_id] = CandidateObservation(
            output=output,
            rows=_declared_rows(entry.get("rows"), output.schema, "the observed rows"),
            context=case.context,
            observed_inputs=tuple(
                _declared_record(item, Identity, "an observed input")
                for item in entry.get("inputs") or ()
            ),
        )
    clauses = tuple(
        _clause_observation(entry)
        for entry in _declared_entries(declared, "clauses", "the clause observations")
    )
    return expected, observed, clauses


def store_case_record(path: Path, facts: Mapping[str, object]) -> None:
    """Write one case record as the canonical projection of the facts it holds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(render_record_projection(facts), encoding="ascii", newline="\n")
    except UnicodeEncodeError as error:
        raise _invalid(f"a case record holds printable ASCII: {error}") from None


def read_case_record(path: Path, form: str) -> Mapping[str, tuple[str, ...]]:
    """Read one written case record, refusing anything but its canonical projection."""
    if not path.is_file():
        raise _refuse(RefusalReason.RECORD_NOT_HELD, f"no {form} record is held for the case")
    text = path.read_text(encoding="ascii")
    collected: dict[str, list[str]] = {}
    for name, value in record_lines(text):
        collected.setdefault(name, []).append(value)
    read = {
        name: () if values == [EMPTY_LIST] else tuple(values) for name, values in collected.items()
    }
    if validate_record_projection(text, read):
        raise _refuse(
            RefusalReason.MALFORMED_RECORD, "a case record is the canonical projection of its facts"
        )
    if read.get("form") != (form,):
        raise _refuse(
            RefusalReason.MALFORMED_RECORD, "a case record declares a form this reader knows"
        )
    return read


def _accepted_intake(case: VerificationCase, evidence_repository, candidate_runner):
    """Take one case in, reporting the closed reasons intake refused it for."""
    try:
        return intake_case(
            case, evidence_repository=evidence_repository, candidate_runner=candidate_runner
        )
    except IntakeRefused as refusal:
        if not refusal.refusals:
            raise _refuse(
                RefusalReason.MALFORMED_RECORD,
                "intake answered with neither an accepted case nor a reason for refusing one",
            ) from None
        raise _refuse(
            INTAKE_REASONS[refusal.refusals[0].reason],
            "intake refused the case: "
            + _listed(f"{item.reason.value} at {item.subject}" for item in refusal.refusals),
        ) from None


def _reconciled(case: VerificationCase, intake, candidate_runner, expected, observed):
    """Run one case through the parity engine, reporting the refusals it declares."""
    try:
        return reconcile_run(
            case,
            intake,
            policy_observation=observe_policy(case),
            expected_material=expected,
            observations=observed,
            candidate_runner=candidate_runner,
        )
    except ENGINE_REFUSALS as refusal:
        raise _invalid(f"a verification run refused: {refusal}") from None


def _verified(case: VerificationCase, intake, candidate_runner, expected, observed, clauses):
    """Run one case through the parity engine and the whole delivery contract."""
    reconciliation = _reconciled(case, intake, candidate_runner, expected, observed)
    try:
        contract = execute_delivery_contract(
            case, intake, reconciliation=reconciliation.clauses, observations=clauses
        )
    except ENGINE_REFUSALS as refusal:
        raise _invalid(f"a verification run refused: {refusal}") from None
    return reconciliation, contract


def _diagnosed(case: VerificationCase, intake, reconciliation, candidate_runner, output_id: str):
    """Build one investigation packet through the diagnosis workflow.

    The workflow reads the packet through the privacy gate, which refuses a
    packet carrying anything no packet may carry. The decision about carrying
    the packet onward comes back on the packet itself and is reported rather
    than refused for, so the refusals caught here are the gate's own.
    """
    try:
        return diagnose_failed_output(
            case,
            intake,
            reconciliation,
            output_id=output_id,
            candidate_runner=candidate_runner,
        )
    except PrivacyRefused as refusal:
        raise _refuse(
            PRIVACY_REASONS[refusal.reason], f"a packet did not leave the gate: {refusal}"
        ) from None
    except DIAGNOSIS_REFUSALS as refusal:
        raise _invalid(f"a diagnosis refused: {refusal}") from None


def intake_verification_case(
    *,
    repository: object,
    root: object,
    engagement_id: str,
    case_document: object,
    evidence_identity: object,
    candidate_identity: object,
) -> RouteResult:
    """Take one approved case in and hold the receipts it derived."""
    base = records_root(repository, root)
    case = read_case(base, case_document)
    evidence_repository, candidate_runner = resolve_adapters(
        base, engagement_id, evidence_identity, candidate_identity
    )
    intake = _accepted_intake(case, evidence_repository, candidate_runner)
    path = case_directory(base, engagement_id, case.case_id) / INTAKE_RECORD
    store_case_record(path, verification_presentation.intake_record_facts(intake))
    return RouteResult(
        command="verification intake-case",
        values=verification_presentation.intake_values(intake, _relative(repository, path)),
    )


def verify_case(
    *,
    repository: object,
    root: object,
    engagement_id: str,
    case_document: object,
    material_document: object,
    evidence_identity: object,
    candidate_identity: object,
) -> RouteResult:
    """Verify one accepted case and hold the outcome its clauses imply."""
    base = records_root(repository, root)
    case = read_case(base, case_document)
    evidence_repository, candidate_runner = resolve_adapters(
        base, engagement_id, evidence_identity, candidate_identity
    )
    intake = _accepted_intake(case, evidence_repository, candidate_runner)
    expected, observed, clauses = read_run_material(base, material_document, case)
    reconciliation, contract = _verified(
        case, intake, candidate_runner, expected, observed, clauses
    )
    path = case_directory(base, engagement_id, case.case_id) / OUTCOME_RECORD
    store_case_record(
        path, verification_presentation.outcome_record_facts(reconciliation, contract)
    )
    return RouteResult(
        command="verification verify",
        values=verification_presentation.verification_values(
            reconciliation, contract, _relative(repository, path)
        ),
    )


def _recorded_run(base: Path, engagement_id: str, case_document: object):
    """Read one case and the outcome its verified run recorded, with its place.

    Every route that answers for a run already taken reads it here, so the case
    the route was given and the record held beside it are read once and in one
    order.
    """
    case = read_case(base, case_document)
    directory = case_directory(base, engagement_id, case.case_id)
    recorded = read_case_record(
        directory / OUTCOME_RECORD, verification_presentation.OUTCOME_RECORD_FORM
    )
    return case, directory, recorded


def _gated_packet(
    base: Path,
    case,
    recorded: Mapping[str, tuple[str, ...]],
    *,
    engagement_id: str,
    material_document: object,
    evidence_identity: object,
    candidate_identity: object,
    output_id: object,
):
    """Derive the gated packet for one output a recorded outcome reports as failing.

    The whole derivation sits in one place because two routes need the same
    packet: the one that writes it down and the one that asks an adviser about
    it. Nothing is decided here. The recorded outcome names the failing output,
    the run is derived again from the adapters and the material it was taken
    over, and the recorded result digest says whether it is that run.
    """
    named = part_text(output_id, "an output identity")
    if named not in recorded.get(FAILED_OUTPUT_FIELD, ()):
        raise _invalid("a recorded outcome reports the output a diagnosis answers for as failing")
    evidence_repository, candidate_runner = resolve_adapters(
        base, engagement_id, evidence_identity, candidate_identity
    )
    intake = _accepted_intake(case, evidence_repository, candidate_runner)
    expected, observed, clauses = read_run_material(base, material_document, case)
    reconciliation, _ = _verified(case, intake, candidate_runner, expected, observed, clauses)
    if (reconciliation.result_digest,) != recorded.get(RESULT_DIGEST_FIELD, ()):
        raise _refuse(
            RefusalReason.DIGEST_MISMATCH,
            "a diagnosis reads the run the recorded outcome answers for",
        )
    return named, _diagnosed(case, intake, reconciliation, candidate_runner, named)


def diagnose_case_failure(
    *,
    repository: object,
    root: object,
    engagement_id: str,
    case_document: object,
    material_document: object,
    evidence_identity: object,
    candidate_identity: object,
    output_id: object,
) -> RouteResult:
    """Diagnose one output a recorded outcome reports as failing.

    A diagnosis whose packet the disclosure policy withheld is a completed
    diagnosis: the decision is reported and written down with the fault it
    answers for, and the bounded reporting surface leaves the packet's own
    content out of both.

    A run that failed with no output for a packet to answer for is a completed
    diagnosis too. A packet answers for a failing output, and a run whose
    failing clauses were all answered over the facts it declared reports none,
    so there is no packet to build and no fault to classify. The decision the
    reporting surface owns is what this route reports and writes down, with the
    families that failed and the clauses they are. A recorded outcome that
    reports no failure at all is refused as before, because there is nothing to
    diagnose.
    """
    base = records_root(repository, root)
    case, directory, recorded = _recorded_run(base, engagement_id, case_document)
    if verification_presentation.failed_without_output(recorded):
        failing = verification_presentation.failing_clauses(recorded)
        if failing is None:
            raise _refuse(
                RefusalReason.MALFORMED_RECORD,
                "a recorded outcome writes every clause it answered in the one declared form",
            )
        path = directory / DIAGNOSIS_RECORD
        store_case_record(
            path, verification_presentation.no_failing_output_record_facts(case, failing)
        )
        return RouteResult(
            command="verification diagnose-failure",
            values=verification_presentation.no_failing_output_values(
                case, failing, _relative(repository, path)
            ),
        )
    named, diagnosis = _gated_packet(
        base,
        case,
        recorded,
        engagement_id=engagement_id,
        material_document=material_document,
        evidence_identity=evidence_identity,
        candidate_identity=candidate_identity,
        output_id=output_id,
    )
    path = directory / PACKET_RECORD.format(output=_segment(named, "an output identity"))
    store_case_record(path, verification_presentation.packet_record_facts(diagnosis))
    return RouteResult(
        command="verification diagnose-failure",
        values=verification_presentation.diagnosis_values(diagnosis, _relative(repository, path)),
    )


# --- the remediation and acceptance routes ------------------------------------
#
# These routes present what the remediation workflow decided about one piece of
# advice. Nothing here disposes of advice, derives a work identity, reads an
# assurance class off presented material or decides what a rerun found: every
# one of those answers comes back from the workflow, and this module carries it
# to the record and to the report. The tracker is reached only through the same
# narrow projector the gap route uses, and only for a decision that already
# approved work.

# The names the records these routes write are held under, and the shapes the
# acceptance route reads a whole case directory back through.
DECISION_RECORD = "decision-{key}.md"
RERUN_RECORD = "rerun-{key}.md"
DECISION_RECORDS = "decision-*.md"
RERUN_RECORDS = "rerun-*.md"
PACKET_RECORDS = "fault-*.md"
# The document a person writes to carry the remedy they wrote themselves.
REMEDY_DOCUMENT_FORM = "evorthon.verification.remedy.v1"
# The words a caller may give for a disposition, read off the presentation
# surface that reads them off the workflow, so no route restates the set.
HUMAN_DISPOSITION_WORDS = verification_presentation.HUMAN_DISPOSITION_WORDS
# The fields a recorded case identity is read back from, named by the surface
# that wrote them.
RECORDED_CASE_FIELDS = (
    verification_presentation.CASE_FIELD,
    verification_presentation.CASE_VERSION_FIELD,
    verification_presentation.CASE_DIGEST_FIELD,
)

# What this module reports each closed remediation refusal as. The table is
# total and the check below says so.
REMEDIATION_REASONS = MappingProxyType(
    {
        RemediationRefusalReason.UNDECLARED_ADVICE: RefusalReason.MALFORMED_RECORD,
        RemediationRefusalReason.UNDECLARED_DISPOSITION: RefusalReason.MALFORMED_VALUE,
        RemediationRefusalReason.UNDECLARED_OUTCOME: RefusalReason.MALFORMED_VALUE,
        RemediationRefusalReason.NON_HUMAN_ACTOR: RefusalReason.MALFORMED_VALUE,
        RemediationRefusalReason.UNNAMED_AUTHORITY: RefusalReason.MALFORMED_VALUE,
        RemediationRefusalReason.INCOMPLETE_DISPOSITION: RefusalReason.MALFORMED_VALUE,
        RemediationRefusalReason.INCONSISTENT_ASSURANCE: RefusalReason.MALFORMED_VALUE,
        RemediationRefusalReason.UNAPPROVED_REMEDY: RefusalReason.MALFORMED_VALUE,
        RemediationRefusalReason.CASE_MISMATCH: RefusalReason.DIGEST_MISMATCH,
        RemediationRefusalReason.NO_PRIOR_DEFECT: RefusalReason.MALFORMED_VALUE,
    }
)
if frozenset(REMEDIATION_REASONS) != frozenset(RemediationRefusalReason):  # pragma: no cover
    raise RuntimeError("every remediation refusal reason is reported under one declared reason")


def _remediation(call, *given: object, **declared: object):
    """Drive one remediation workflow, reporting the closed reasons it refuses for."""
    try:
        return call(*given, **declared)
    except RemediationRefused as refusal:
        raise _refuse(
            REMEDIATION_REASONS[refusal.reason], f"a remediation refused: {refusal}"
        ) from None
    except ENGINE_REFUSALS as refusal:
        raise _invalid(f"a verification run refused: {refusal}") from None


def deciding_actor(value: object, label: str = "a deciding actor") -> DecidingActor:
    """Build one deciding actor from its identity and the kind of actor it is.

    The kind is written last and the identity takes everything before it,
    because an identity's digest carries a field separator of its own.
    """
    written = part_text(value, label)
    identity, separator, kind = written.rpartition(FIELD_SEPARATOR)
    if not separator:
        raise _invalid(f"{label} is written as an identity and then the kind of actor it is")
    return _declared(
        DecidingActor,
        identity=identity_value(identity, f"{label} identity"),
        kind=member(RemediationActorKind, kind, f"{label} kind"),
    )


def read_remedy(root: Path, document: object) -> tuple[tuple[str, ...], str]:
    """Read the remedy a person wrote themselves, and the statement of what changed."""
    declared = _declared_document(
        _inside(root, document, "a remedy document"), REMEDY_DOCUMENT_FORM, "a remedy document"
    )
    written = declared.get("fixes")
    if not isinstance(written, (list, tuple)):
        raise _invalid("a remedy document writes the remedy it carries as a list")
    return (
        tuple(part_text(fix, "a written remedy") for fix in written),
        part_text(declared.get("statement"), "a remedy statement"),
    )


def human_disposition(
    root: Path,
    *,
    disposition: object,
    decided_by: object,
    rationale_document: object,
    requested_evidence: tuple[str, ...] = (),
    remedy_document: object = None,
    owner_document: object = None,
    certificate_document: object = None,
) -> HumanDisposition:
    """Build one named human's disposition from the words and documents it declares.

    Nothing is checked here beyond the shape each value declares. Whether a
    disposition may carry a remedy, must state what it asks for, or may be
    taken by the person named is the workflow's to answer.
    """
    fixes, statement = ((), None) if remedy_document is None else read_remedy(root, remedy_document)
    return _declared(
        HumanDisposition,
        disposition=member(RemediationDisposition, disposition, "a disposition"),
        decided_by=deciding_actor(decided_by),
        rationale=_declared_json(
            root, rationale_document, EvidenceReference, "a rationale document"
        ),
        edited_fixes=fixes,
        edit_statement=statement,
        requested_evidence=tuple(
            part_text(asked, "a requested evidence") for asked in requested_evidence or ()
        ),
        owner_presented=(
            None
            if owner_document is None
            else _declared_json(
                root, owner_document, OwnerPresentedEvidence, "an owner-presented document"
            )
        ),
        environment_certificate=(
            None
            if certificate_document is None
            else _declared_json(
                root, certificate_document, EnvironmentCertificateClaim, "a certificate document"
            )
        ),
    )


def _recorded_fact(read: Mapping[str, tuple[str, ...]], name: str) -> str:
    """Read one fact a case record states exactly once."""
    held = read.get(name, ())
    if len(held) != 1:
        raise _refuse(RefusalReason.MALFORMED_RECORD, f"a case record states one {name}")
    return held[0]


def recorded_case_identity(case: VerificationCase, read: Mapping[str, tuple[str, ...]]) -> Identity:
    """Read the case identity the recorded outcome answers for.

    The digest is the one the recorded run was taken on, because this module
    computes no digest of its own. The case the route was given is confirmed to
    be that case by name and version here, and by digest inside the workflow
    the moment a rerun compares them.
    """
    identifier, version, digest = (_recorded_fact(read, name) for name in RECORDED_CASE_FIELDS)
    if (case.case_id, case.version) != (identifier, version):
        raise _refuse(
            RefusalReason.MALFORMED_RECORD,
            "a recorded outcome answers for the case document the route was given",
        )
    return _declared(Identity, identifier=identifier, version=version, digest=digest)


def _held_records(directory: Path, pattern: str, form: str, repository: object):
    """Read every record of one form a case directory holds, in a stable order."""
    return tuple(
        (_relative(repository, path), read_case_record(path, form))
        for path in sorted(directory.glob(pattern))
    )


def _decision_place(directory: Path, outcome, held: str) -> Path:
    """Name the one record of one decision, or of the rerun that answers it.

    The name is the key the presentation surface writes for the decision, which
    is what was decided and the rationale it rests on. A fault identity and an
    advice identity are composed logical names and are no name a directory
    carries, so neither is used here.
    """
    return directory / held.format(
        key=_segment(verification_presentation.decision_key(outcome), "a decision key")
    )


def _recorded_faults(directory: Path, repository: object) -> tuple[str, ...]:
    """Name every fault this case has a recorded gated packet for."""
    return tuple(
        fault
        for _, read in _held_records(
            directory, PACKET_RECORDS, verification_presentation.PACKET_RECORD_FORM, repository
        )
        for fault in read.get(verification_presentation.FAULT_FIELD, ())
    )


def _confirm_fault(outcome, directory: Path, repository: object) -> None:
    """Confirm the advice answers a fault this case recorded a packet for.

    Advice is written about one gated packet. A decision recorded under a case
    that never reported that fault is a record contradicting the case it sits
    under, so it is refused before anything is written. The packet record
    carries the fault by name, so the name is what is compared.
    """
    if outcome.fault.identifier not in _recorded_faults(directory, repository):
        raise _refuse(
            RefusalReason.RECORD_NOT_HELD,
            "no gated packet is held for the fault the advice answers",
        )
    return None


def _confirm_immutable(outcome, directory: Path, path: Path, repository: object) -> None:
    """Confirm nothing already recorded for this fault is changed by this decision.

    An approved or edited remedy is immutable: once a named human has approved
    a correction for a fault, deciding again on that fault is refused. A
    decision that left the fault open may be followed by another, which is
    written beside it rather than over it. Recording the same decision again
    changes nothing and is not a change.
    """
    facts = verification_presentation.remediation_record_facts(outcome)
    written = {name: (value,) for name, value in facts.items()}
    for name, held in _held_records(
        directory, DECISION_RECORDS, verification_presentation.DECISION_RECORD_FORM, repository
    ):
        if held == written:
            continue
        if held.get(verification_presentation.DECISION_FAULT_FIELD, ()) != (
            outcome.fault.identifier,
        ):
            continue
        approving = held.get(verification_presentation.DISPOSITION_FIELD, ())
        if approving and approving[0] in verification_presentation.APPROVING_DISPOSITION_WORDS:
            raise _refuse(
                RefusalReason.DIGEST_MISMATCH,
                "a named human already approved a correction for this fault, "
                "and that record is not changed",
            )
        if Path(name).name == path.name:
            raise _refuse(
                RefusalReason.DIGEST_MISMATCH,
                "a decision is already recorded under this name and states something else",
            )
    return None


def _recorded_decision(outcome, directory: Path, decision_identity: object) -> None:
    """Confirm the decision presented again is the decision the case already records."""
    if part_text(decision_identity, "a decision identity") != outcome.decision.remediation_id:
        raise _invalid("a rerun names the decision the words it was given record")
    held = read_case_record(
        _decision_place(directory, outcome, DECISION_RECORD),
        verification_presentation.DECISION_RECORD_FORM,
    )
    facts = verification_presentation.remediation_record_facts(outcome)
    if held != {name: (value,) for name, value in facts.items()}:
        raise _refuse(
            RefusalReason.DIGEST_MISMATCH,
            "a rerun runs for the decision the case records, presented again as it was recorded",
        )
    return None


def _projected_remedy(
    outcome,
    *,
    repository: object,
    root: object,
    engagement_id: str,
    use_case_id: object,
    actor_handle: object,
    prefix: str,
    tracker_repository: object,
    iteration: object,
    remedy_summary: object,
    runner: object,
    case_facts: Mapping[str, tuple[str, ...]],
) -> tuple[str | None, str | None]:
    """Project one approved remedy as tracked work, or project nothing at all.

    A decision that approved no work is projected nowhere. The workflow decided
    that, and this route reads its answer rather than restating the rule.
    """
    if actor_handle is None or outcome.approved_work is None:
        return None, None
    if use_case_id is None or iteration is None or remedy_summary is None:
        raise _invalid(
            "projecting an approved remedy names the use case, the iteration it corrects "
            "and the summary the tracked work carries"
        )
    use_case, _, _, _ = load_use_case(repository, root, engagement_id, use_case_id)
    projection = read_readiness(use_case, case_index(use_case, **case_facts))
    iteration_id, segment_id, iteration_summary = fields(iteration, 3, "an iteration")
    scope = UseCaseScope(
        use_case=use_case,
        readiness=projection,
        iterations=(
            _declared(
                SegmentIteration,
                iteration_id=iteration_id,
                segment_id=segment_id,
                summary=iteration_summary,
            ),
        ),
        remedies=(
            _declared(
                ApprovedRemedy,
                outcome=outcome,
                iteration_id=iteration_id,
                summary=part_text(remedy_summary, "a remedy summary"),
            ),
        ),
    )
    projector = _projector(actor_handle, prefix, runner)
    target = Path(str(repository if tracker_repository is None else tracker_repository))
    try:
        result = projector.project((scope,), repository=target)
    except PinaxProjectionError as error:
        raise _invalid(str(error)) from error
    projected = result.use_cases[0]
    return projected.parent_item, projected.remedy_items[0][1]


def record_remediation(
    *,
    repository: object,
    root: object,
    engagement_id: str,
    case_document: object,
    advice_document: object,
    disposition: object,
    decided_by: object,
    rationale_document: object,
    requested_evidence: tuple[str, ...] = (),
    remedy_document: object = None,
    owner_document: object = None,
    certificate_document: object = None,
    use_case_id: object = None,
    actor_handle: object = None,
    prefix: str = "evd",
    tracker_repository: object = None,
    iteration: object = None,
    remedy_summary: object = None,
    runner: object = None,
    case_datasets: tuple[str, ...] = (),
    case_expected_outputs: tuple[str, ...] = (),
    case_checkpoints: tuple[str, ...] = (),
    case_statuses: tuple[str, ...] = (),
) -> RouteResult:
    """Record one named human's disposition of one piece of advice."""
    base = records_root(repository, root)
    case = read_case(base, case_document)
    directory = case_directory(base, engagement_id, case.case_id)
    recorded = read_case_record(
        directory / OUTCOME_RECORD, verification_presentation.OUTCOME_RECORD_FORM
    )
    identity = recorded_case_identity(case, recorded)
    advice = _declared_json(base, advice_document, RemediationAdvice, "an advice document")
    taken = human_disposition(
        base,
        disposition=disposition,
        decided_by=decided_by,
        rationale_document=rationale_document,
        requested_evidence=requested_evidence,
        remedy_document=remedy_document,
        owner_document=owner_document,
        certificate_document=certificate_document,
    )
    outcome = _remediation(record_remediation_decision, advice, taken, case=identity)
    _confirm_fault(outcome, directory, repository)
    path = _decision_place(directory, outcome, DECISION_RECORD)
    _confirm_immutable(outcome, directory, path, repository)
    store_case_record(path, verification_presentation.remediation_record_facts(outcome))
    parent_item, remedy_item = _projected_remedy(
        outcome,
        repository=repository,
        root=root,
        engagement_id=engagement_id,
        use_case_id=use_case_id,
        actor_handle=actor_handle,
        prefix=prefix,
        tracker_repository=tracker_repository,
        iteration=iteration,
        remedy_summary=remedy_summary,
        runner=runner,
        case_facts={
            "case_datasets": case_datasets,
            "case_expected_outputs": case_expected_outputs,
            "case_checkpoints": case_checkpoints,
            "case_statuses": case_statuses,
        },
    )
    return RouteResult(
        command="verification record-remediation",
        values=(
            *verification_presentation.remediation_values(outcome, _relative(repository, path)),
            *verification_presentation.tracker_values(parent_item, remedy_item),
        ),
    )


def rerun_remediation(
    *,
    repository: object,
    root: object,
    engagement_id: str,
    case_document: object,
    advice_document: object,
    disposition: object,
    decided_by: object,
    rationale_document: object,
    decision_identity: object,
    evidence_identity: object,
    candidate_identity: object,
    material_document: object,
    prior_candidate_identity: object,
    prior_material_document: object,
    requested_evidence: tuple[str, ...] = (),
    remedy_document: object = None,
    owner_document: object = None,
    certificate_document: object = None,
) -> RouteResult:
    """Rerun one corrected candidate over the case a recorded decision cites.

    The decision is presented again in the words it was recorded from and the
    workflow records it again, so a rerun runs for a decision this product
    already holds and for no other. The run that found the fault is derived
    again from the candidate and the material it was taken over, and the
    recorded outcome's own result digest says whether it is that run.
    """
    base = records_root(repository, root)
    case = read_case(base, case_document)
    directory = case_directory(base, engagement_id, case.case_id)
    recorded = read_case_record(
        directory / OUTCOME_RECORD, verification_presentation.OUTCOME_RECORD_FORM
    )
    identity = recorded_case_identity(case, recorded)
    advice = _declared_json(base, advice_document, RemediationAdvice, "an advice document")
    taken = human_disposition(
        base,
        disposition=disposition,
        decided_by=decided_by,
        rationale_document=rationale_document,
        requested_evidence=requested_evidence,
        remedy_document=remedy_document,
        owner_document=owner_document,
        certificate_document=certificate_document,
    )
    outcome = _remediation(record_remediation_decision, advice, taken, case=identity)
    _confirm_fault(outcome, directory, repository)
    _recorded_decision(outcome, directory, decision_identity)
    evidence_repository, prior_runner = resolve_adapters(
        base, engagement_id, evidence_identity, prior_candidate_identity
    )
    prior_intake = _accepted_intake(case, evidence_repository, prior_runner)
    expected, observed, clauses = read_run_material(base, prior_material_document, case)
    prior_reconciliation, prior_contract = _verified(
        case, prior_intake, prior_runner, expected, observed, clauses
    )
    if (prior_contract.summary_digest,) != recorded.get(OUTCOME_DIGEST_FIELD, ()):
        raise _refuse(
            RefusalReason.DIGEST_MISMATCH,
            "a rerun compares against the whole contract the recorded outcome answers for",
        )
    if (prior_reconciliation.result_digest,) != recorded.get(RESULT_DIGEST_FIELD, ()):
        raise _refuse(
            RefusalReason.DIGEST_MISMATCH,
            "a rerun compares against the run the recorded outcome answers for",
        )
    _, corrected_runner = resolve_adapters(
        base, engagement_id, evidence_identity, candidate_identity
    )
    corrected_intake = _accepted_intake(case, evidence_repository, corrected_runner)
    expected, observed, clauses = read_run_material(base, material_document, case)
    corrected = _reconciled(case, corrected_intake, corrected_runner, expected, observed)
    rerun = _remediation(
        rerun_corrected_case,
        outcome,
        case,
        corrected_intake,
        prior=prior_contract,
        reconciliation=corrected.clauses,
        observations=clauses,
    )
    path = _decision_place(directory, outcome, RERUN_RECORD)
    decision = outcome.decision.remediation_id
    store_case_record(path, verification_presentation.rerun_record_facts(rerun, decision))
    return RouteResult(
        command="verification rerun",
        values=verification_presentation.rerun_values(
            rerun, decision, _relative(repository, path)
        ),
    )


def read_acceptance_evidence(
    *, repository: object, root: object, engagement_id: str, case_document: object
) -> RouteResult:
    """Report what a named human acceptance of one case would rest on, and nothing more."""
    base = records_root(repository, root)
    case = read_case(base, case_document)
    directory = case_directory(base, engagement_id, case.case_id)
    outcome_path = directory / OUTCOME_RECORD
    recorded = read_case_record(outcome_path, verification_presentation.OUTCOME_RECORD_FORM)
    packets = _held_records(
        directory, PACKET_RECORDS, verification_presentation.PACKET_RECORD_FORM, repository
    )
    decisions = _held_records(
        directory, DECISION_RECORDS, verification_presentation.DECISION_RECORD_FORM, repository
    )
    reruns = _held_records(
        directory, RERUN_RECORDS, verification_presentation.RERUN_RECORD_FORM, repository
    )
    held = (*packets, *decisions, *reruns)
    return RouteResult(
        command="verification acceptance-evidence",
        values=verification_presentation.acceptance_values(
            case,
            recorded,
            tuple(read for _, read in packets),
            tuple(read for _, read in decisions),
            tuple(read for _, read in reruns),
            (_relative(repository, outcome_path), *(name for name, _ in held)),
        ),
    )


# --- the adviser, generation and campaign routes ------------------------------
#
# These three routes drive the stages that have an owning function but no route
# of their own. Nothing is decided here either. The adviser workflow reads the
# reply and refuses what it may not record; the declaration adapter drafts,
# adjudicates and yields proposal evidence only for an accepted adjudication;
# the released delivery routes compose and issue their own commands and read
# their own results back. Every external mechanism is taken as an injected port
# or runner, with the default this module reaches for when a caller supplies
# none named beside it, exactly as the gap route names its own.

# The one directory a generated estate of one engagement is laid out under.
ESTATE_DIRECTORY = "estates"
# What a route reports where a stage produced nothing at all.
NOTHING = verification_presentation.NOTHING
# The words that stand for the two states of a selected item's readiness and of
# its approval. Both are facts a caller reads off its own owning source.
READY_WORDS = MappingProxyType({"ready": True, "not-ready": False})
APPROVED_WORDS = MappingProxyType({"approved": True, "unapproved": False})

# What this module reports each closed adviser refusal as. The table is total
# and the check below says so.
ADVISER_REASONS = MappingProxyType(
    {
        AdviserRefusalReason.UNGATED_PACKET: RefusalReason.MALFORMED_RECORD,
        AdviserRefusalReason.RELAXED_BOUNDS: RefusalReason.MALFORMED_VALUE,
        AdviserRefusalReason.UNRESOLVED_REPLY: RefusalReason.MALFORMED_RECORD,
        AdviserRefusalReason.CONTRADICTORY_REPLY: RefusalReason.MALFORMED_RECORD,
        AdviserRefusalReason.INCOMPLETE_HYPOTHESIS: RefusalReason.MALFORMED_VALUE,
        AdviserRefusalReason.REPEATED_DECLARATION: RefusalReason.MALFORMED_VALUE,
        AdviserRefusalReason.UNCITED_EVIDENCE: RefusalReason.MALFORMED_VALUE,
    }
)
if frozenset(ADVISER_REASONS) != frozenset(AdviserRefusalReason):  # pragma: no cover
    raise RuntimeError("every adviser refusal reason is reported under one declared reason")


def ergasterion_runner():
    """The runner the generation route drives when a caller supplies none."""
    return SubprocessErgasterionRunner()


def autobuild_runner():
    """The runner the campaign route drives when a caller supplies none."""
    return SubprocessAutoBuildRunner()


def _installed(capabilities: object):
    """The capability report a delivery route is given, or the installed one."""
    return installed_capabilities() if capabilities is None else capabilities


def _generation_route(
    actor_handle: object, capabilities: object, runner: object
) -> ErgasterionGenerationRoute:
    try:
        return ErgasterionGenerationRoute(
            runner if runner is not None else ergasterion_runner(),
            actor=part_text(actor_handle, "a generation actor"),
            capabilities=_installed(capabilities),
        )
    except ErgasterionRouteError as error:
        raise _invalid(str(error)) from error


def _campaign_route(capabilities: object, runner: object) -> AutoBuildDeliveryRoute:
    try:
        return AutoBuildDeliveryRoute(
            runner if runner is not None else autobuild_runner(),
            capabilities=_installed(capabilities),
        )
    except AutoBuildRouteError as error:
        raise _invalid(str(error)) from error


def ask_case_adviser(
    *,
    repository: object,
    root: object,
    engagement_id: str,
    case_document: object,
    material_document: object,
    evidence_identity: object,
    candidate_identity: object,
    output_id: object,
    advice_document: object,
    adviser_route: object,
    egress: object,
    required_authority: object,
    authorization: object = None,
) -> RouteResult:
    """Ask the adviser about one disclosed packet and hold the advice it recorded.

    The packet is derived exactly as the diagnosis route derives it. A packet
    the disclosure policy withheld is a completed round that asks nobody
    anything, so no call is made and the decision is what the route reports.
    The reply crosses the injected port and nothing else: this module holds no provider
    client, no credential and no authorization policy, and it parses no
    provider text. An unknown answer is a real answer and writes no document.
    The advice is written where the caller named it, so the route that records
    a named human's disposition of it reads the same document.
    """
    base = records_root(repository, root)
    case, _, recorded = _recorded_run(base, engagement_id, case_document)
    _, diagnosis = _gated_packet(
        base,
        case,
        recorded,
        engagement_id=engagement_id,
        material_document=material_document,
        evidence_identity=evidence_identity,
        candidate_identity=candidate_identity,
        output_id=output_id,
    )
    authority = identity_value(required_authority, "a required authority")
    if verification_presentation.withheld(diagnosis):
        # The policy withheld this packet, so there is nobody to ask. That is
        # the round's completed answer: the decision is reported, no call
        # crosses the egress port and no advice document is written.
        return RouteResult(
            command="verification ask-adviser",
            values=verification_presentation.unasked_adviser_values(
                case, diagnosis, authority.identifier
            ),
        )
    try:
        # The diagnosis reports the record the gate read. The gate is asked
        # about it again here, because the adviser only ever sees a packet the
        # privacy policy has just disclosed, and the gate owns that decision.
        gated = gate_fault_packet(diagnosis.packet)
    except PrivacyRefused as refusal:
        raise _refuse(
            PRIVACY_REASONS[refusal.reason], f"a packet did not leave the gate: {refusal}"
        ) from None
    try:
        outcome = advise_on_fault(
            gated,
            engagement_id=part_text(engagement_id, "an engagement identity"),
            case_id=case.case_id,
            route=adviser_route,
            egress=egress,
            required_authority=authority,
            authorization=authorization,
        )
    except AdviserRefused as refusal:
        raise _refuse(
            ADVISER_REASONS[refusal.reason], f"an adviser round refused: {refusal}"
        ) from None
    except PrivacyRefused as refusal:
        raise _refuse(
            PRIVACY_REASONS[refusal.reason], f"a packet did not leave the gate: {refusal}"
        ) from None
    advice = outcome.advice
    if advice is not None:
        place = _inside(base, advice_document, "an advice document")
        place.parent.mkdir(parents=True, exist_ok=True)
        try:
            place.write_text(serialize_json(advice), encoding="ascii", newline="\n")
        except UnicodeEncodeError as error:
            raise _invalid(f"an advice document holds printable ASCII: {error}") from None
    return RouteResult(
        command="verification ask-adviser",
        values=(
            ("case", case.case_id),
            ("case version", case.version),
            ("fault", gated.record.fault_id),
            ("confidence", outcome.confidence.value),
            ("advice", NOTHING if advice is None else advice.advice_id),
            ("advice version", NOTHING if advice is None else advice.version),
            ("hypotheses", 0 if advice is None else len(advice.hypotheses)),
            ("required authority", authority.identifier),
        ),
    )


def generate_segment_products(
    *,
    repository: object,
    root: object,
    engagement_id: str,
    declaration_request: object,
    proposal_reference: str,
    drafted_by: str,
    reviewer: str,
    disposition: str,
    generation_reference: str,
    generation_actor: str,
    estate_name: str,
    seeds: object = (),
    canonicalisation: object = None,
    capabilities: object = None,
    runner: object = None,
) -> RouteResult:
    """Draft one segment's product declaration, adjudicate it, and emit it.

    The draft is the declaration adapter's and the emission is the released
    tool's. This route states no step, no layer and no operational value: it
    carries the adjudicated draft into an exact generation contract and asks
    the generation route, on its injected runner, to produce the estate. A
    declaration a reviewer has not accepted yields no proposal evidence, which
    is the adapter's refusal and not this module's.
    """
    base = records_root(repository, root)
    try:
        draft = draft_declaration(declaration_request)
        proposal_id, proposal_version = fields(
            proposal_reference, 2, "a declaration proposal reference"
        )
        proposal = draft.proposed(
            proposal_id=proposal_id,
            version=proposal_version,
            drafted_by=part_text(drafted_by, "a drafting actor"),
        )
        adjudicated = proposal.adjudicated(
            reviewer=identity_value(reviewer, "a declaration reviewer"),
            disposition=member(GenerationDisposition, disposition, "a declaration disposition"),
        )
        evidence = adjudicated.proposal_evidence()
    except DeclarationDraftError as error:
        raise _invalid(str(error)) from None
    contract = _declared(
        ExactGenerationContract,
        identity=identity_value(generation_reference, "a generation reference"),
        declarations=(
            _declared(ProductDeclaration, file_name=draft.file_name, document=draft.yaml_text),
        ),
        seeds=tuple(seeds or ()),
        canonicalisation=canonicalisation,
    )
    estate = (
        base
        / _segment(engagement_id, "an engagement identity")
        / ESTATE_DIRECTORY
        / _segment(estate_name, "a generation estate")
    )
    estate.parent.mkdir(parents=True, exist_ok=True)
    try:
        generated = _generation_route(generation_actor, capabilities, runner).generate(
            contract, estate=estate
        )
    except ErgasterionRouteError as error:
        raise _invalid(str(error)) from None
    return RouteResult(
        command="delivery generate-products",
        values=(
            ("declaration digest", draft.content_digest),
            ("proposal", proposal.reference.identifier),
            ("proposal version", proposal.reference.version),
            ("reviewer", adjudicated.reviewer.identifier),
            ("disposition", adjudicated.disposition.value),
            ("proposal evidence", evidence.evidence_id),
            ("generation", generated.contract_identity.identifier),
            ("generated by", generated.generated_by),
            ("lineage", generated.lineage.lineage_id),
            (
                "checkpoints",
                [checkpoint.checkpoint_id for checkpoint in generated.lineage.checkpoints],
            ),
            ("artefact digests", [digest for _, digest in generated.artefact_digests]),
        ),
    )


def dispatch_approved_items(
    *,
    repository: object,
    profile: str,
    harness: str,
    selections: object = (),
    capabilities: object = None,
    runner: object = None,
    delivery_authority: object = None,
) -> RouteResult:
    """Issue one campaign over the already-approved, already-ready items named.

    Each selection is written as the item, its readiness and its approval,
    because both are facts a caller reads off its own owning source: the
    tracker and the human approval record. This route computes neither, and
    refusing a blocked or unapproved item is the delivery route's own.
    """
    items = tuple(
        _declared(
            QueueSelection,
            item_id=item,
            ready=_word(READY_WORDS, ready, "a queue readiness"),
            approved=_word(APPROVED_WORDS, approved, "a queue approval"),
        )
        for item, ready, approved in (
            fields(line, 3, "a queue selection") for line in selections or ()
        )
    )
    try:
        record = _campaign_route(capabilities, runner).dispatch(
            repository=Path(part_text(str(repository), "a target repository")),
            profile=part_text(profile, "a campaign profile"),
            harness=part_text(harness, "a campaign harness"),
            items=items,
            delivery_authority=delivery_authority,
        )
    except AutoBuildRouteError as error:
        raise _invalid(str(error)) from None
    return RouteResult(
        command="delivery dispatch-items",
        values=(
            ("campaign", record.campaign_id),
            ("stop reason", record.stop_reason),
            ("run digest", record.digest),
            ("items", [f"{item.item_id} {item.disposition}" for item in record.items]),
        ),
    )
