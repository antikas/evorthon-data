"""Versioned, governed engagement lifecycle with identity-only external references."""
# evorthon-implements: EVD-README-038
# evorthon-implements: EVD-README-030
# evorthon-implements: EVD-README-023
# evorthon-implements: EVD-README-018
# evorthon-implements: EVD-README-013
# evorthon-implements: EVD-README-005
from __future__ import annotations

# evorthon-component: engagement
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path


ENGAGEMENT_SCHEMA_VERSION = "evorthon.engagement.v1"


class EngagementError(ValueError):
    """Raised when an engagement would cross a governed lifecycle boundary."""


class EngagementMode(str, Enum):
    MODERNISATION = "modernisation"
    GREENFIELD = "greenfield"


class LifecyclePhase(str, Enum):
    SETUP = "setup"
    FRAMING = "framing"
    DISCOVERY = "discovery"
    DESIGN = "design"
    DELIVERY_CONTRACT = "delivery_contract"
    DELIVERY = "delivery"
    VERIFIED = "verified"
    ACCEPTED = "accepted"


class DiscoveryKind(str, Enum):
    ESTATE = "estate"
    CAPABILITY = "capability"


class CheckFamily(str, Enum):
    """High-level verification families captured with the engagement intent."""

    PARITY = "parity"
    CONFORMANCE = "conformance"
    INVARIANT = "invariant"
    OPERATIONAL_EVIDENCE = "operational-evidence"
    DELIVERY_INTEGRITY = "delivery-integrity"


class ExpectedCheckResult(str, Enum):
    """The machine result required before a success criterion is satisfied."""

    PASS = "pass"


class ReferenceKind(str, Enum):
    STAGE_RECORD = "stage_record"
    APPROVED_WORK = "approved_work"
    BUILD_EVIDENCE = "build_evidence"
    VERIFICATION_RESULT = "verification_result"
    REVIEW_FINDINGS = "review_findings"
    DECISION_RATIONALE = "decision_rationale"
    VALIDATOR_SPECIFICATION = "validator_specification"
    USE_CASE = "use_case"
    USE_CASE_VERSION = "use_case_version"
    READINESS_PROJECTION = "readiness_projection"
    INTAKE_ARTEFACT = "intake_artefact"


class ActorKind(str, Enum):
    HUMAN = "human"
    MODEL = "model"
    SERVICE = "service"


class ReviewDisposition(str, Enum):
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"


class DecisionKind(str, Enum):
    RECORD_APPROVAL = "record_approval"
    ENGAGEMENT_ACCEPTANCE = "engagement_acceptance"
    VERSION_ACCEPTANCE = "version_acceptance"


class DecisionOutcome(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    ACCEPTED = "accepted"


# These are the record schemas that the aggregate owns.  The legacy stage
# names below are projections for the bootstrap examples and their stable API.
ENGAGEMENT_RECORD_FIELDS: dict[str, tuple[str, ...]] = {
    "setup": ("status", "users", "platform boundary", "authorities", "constraints", "evidence identifiers", "open decisions"),
    "framing": (
        "consumer outcome",
        "success signals",
        "success criteria",
        "scope",
        "authorities",
        "evidence",
        "constraints",
        "open questions",
        "verification case intent",
        "check families",
        "lineage/checkpoint expectations",
        "acceptance rules",
    ),
    "estate_discovery": (
        "processing",
        "data",
        "interfaces",
        "controls",
        "continuity needs",
        "accidental legacy behaviour",
        "evidence",
        "uncertainty",
        "verification case intent",
        "check families",
        "lineage/checkpoint expectations",
        "acceptance rules",
    ),
    "capability_discovery": (
        "required capabilities",
        "constraints",
        "evidence",
        "uncertainty",
        "verification case intent",
        "check families",
        "lineage/checkpoint expectations",
        "acceptance rules",
    ),
    "design": (
        "architecture",
        "operating model",
        "contracts",
        "transition",
        "increments",
        "risks",
        "acceptance signals",
        "evidence",
        "verification case intent",
        "check families",
        "lineage/checkpoint expectations",
        "acceptance rules",
    ),
    "delivery_contract": (
        "package inventory",
        "dependency inventory",
        "gate inventory",
        "exclusions",
        "acceptance",
        "evidence",
        "verification case intent",
        "check families",
        "lineage/checkpoint expectations",
        "acceptance rules",
    ),
    "verification_result": ("deterministic checks", "results", "evidence identity", "uncertainty", "approved differences", "named acceptance"),
}
REVIEW_FIELDS = ("paired review", "reviewer", "finding", "disposition")
STAGE_FIELDS = {
    "outcome": ENGAGEMENT_RECORD_FIELDS["framing"],
    "current_estate": ENGAGEMENT_RECORD_FIELDS["estate_discovery"],
    "capability_discovery": ENGAGEMENT_RECORD_FIELDS["capability_discovery"],
    "design": ENGAGEMENT_RECORD_FIELDS["design"],
    "implementation_plan": ENGAGEMENT_RECORD_FIELDS["delivery_contract"],
    "verification": ENGAGEMENT_RECORD_FIELDS["verification_result"],
}
MODE_STAGES = {
    "modernisation": ("outcome", "current_estate", "design", "implementation_plan", "verification"),
    "greenfield": ("outcome", "capability_discovery", "design", "implementation_plan", "verification"),
}
FILE_STAGES = {
    "outcome-brief.md": "outcome",
    "current-estate-map.md": "current_estate",
    "capability-discovery.md": "capability_discovery",
    "platform-design.md": "design",
    "implementation-plan.md": "implementation_plan",
    "verification-record.md": "verification",
}
KOINE_TEMPLATE_FIELDS = {
    "instance-context.md": ENGAGEMENT_RECORD_FIELDS["setup"],
    **{filename: STAGE_FIELDS[stage] for filename, stage in FILE_STAGES.items()},
}

CONTENT_PHASES = (
    LifecyclePhase.SETUP,
    LifecyclePhase.FRAMING,
    LifecyclePhase.DISCOVERY,
    LifecyclePhase.DESIGN,
    LifecyclePhase.DELIVERY_CONTRACT,
)
NEXT_PHASE = {
    LifecyclePhase.SETUP: LifecyclePhase.FRAMING,
    LifecyclePhase.FRAMING: LifecyclePhase.DISCOVERY,
    LifecyclePhase.DISCOVERY: LifecyclePhase.DESIGN,
    LifecyclePhase.DESIGN: LifecyclePhase.DELIVERY_CONTRACT,
    LifecyclePhase.DELIVERY_CONTRACT: LifecyclePhase.DELIVERY,
    LifecyclePhase.DELIVERY: LifecyclePhase.VERIFIED,
    LifecyclePhase.VERIFIED: LifecyclePhase.ACCEPTED,
}


def _required_text(value: str, label: str) -> None:
    if not value.strip():
        raise EngagementError(f"{label} is required")


_PLACEHOLDER_IDENTITIES = frozenset(
    {"none", "tbd", "todo", "unknown", "unassigned", "to-be-determined", "pending", "forthcoming", "later"}
)
_SUCCESS_CRITERION_FIELDS = frozenset(
    {"signal", "check_family", "validator", "evidence", "required_result", "acceptance_rule"}
)
_REFERENCE_FIELDS = frozenset({"kind", "identifier", "version", "digest"})
_EVIDENCE_FIELDS = frozenset({"identifier", "version", "digest"})


def is_placeholder_identity(value: object) -> bool:
    """Return whether an identity component is an explicit unresolved placeholder."""
    return isinstance(value, str) and value.strip().casefold() in _PLACEHOLDER_IDENTITIES


def validate_success_criterion_contract(value: object) -> tuple[str, ...]:
    """Validate the canonical framing-time check identity and pass contract."""
    if not isinstance(value, Mapping):
        return ("criterion must be an object",)
    failures: list[str] = []
    keys = frozenset(value)
    if keys != _SUCCESS_CRITERION_FIELDS:
        failures.append(
            "criterion fields must be exactly " + ", ".join(sorted(_SUCCESS_CRITERION_FIELDS))
        )
        return tuple(failures)

    for field in ("signal", "acceptance_rule"):
        item = value[field]
        if not isinstance(item, str) or not item.strip():
            failures.append(f"{field} is required")
    if value["check_family"] not in {item.value for item in CheckFamily}:
        failures.append("check_family is not supported")
    if value["required_result"] != ExpectedCheckResult.PASS.value:
        failures.append("required_result must be pass")

    validator = value["validator"]
    if not isinstance(validator, Mapping) or frozenset(validator) != _REFERENCE_FIELDS:
        failures.append("validator must be an immutable validator-specification reference")
    else:
        if validator["kind"] != ReferenceKind.VALIDATOR_SPECIFICATION.value:
            failures.append("validator kind must be validator_specification")
        for field in ("identifier", "version", "digest"):
            item = validator[field]
            if not isinstance(item, str) or not item.strip():
                failures.append(f"validator {field} is required")
            elif is_placeholder_identity(item):
                failures.append(f"validator {field} must not be a placeholder")

    evidence = value["evidence"]
    if not isinstance(evidence, (list, tuple)) or not evidence:
        failures.append("evidence must contain at least one immutable reference")
    else:
        for index, item in enumerate(evidence, start=1):
            if not isinstance(item, Mapping) or frozenset(item) != _EVIDENCE_FIELDS:
                failures.append(f"evidence {index} must be an immutable reference")
                continue
            for field in ("identifier", "version", "digest"):
                part = item[field]
                if not isinstance(part, str) or not part.strip():
                    failures.append(f"evidence {index} {field} is required")
                elif is_placeholder_identity(part):
                    failures.append(f"evidence {index} {field} must not be a placeholder")
    return tuple(failures)


@dataclass(frozen=True)
class Actor:
    """A named participant; only a human can make an engagement decision."""

    identity: str
    kind: ActorKind

    def __post_init__(self) -> None:
        _required_text(self.identity, "actor identity")
        if is_placeholder_identity(self.identity):
            raise EngagementError("actor identity must not be a placeholder")


@dataclass(frozen=True)
class ImmutableReference:
    """An immutable identity reference, deliberately without copied external state."""

    kind: ReferenceKind
    identifier: str
    version: str
    digest: str

    def __post_init__(self) -> None:
        _required_text(self.identifier, "reference identifier")
        _required_text(self.version, "reference version")
        _required_text(self.digest, "reference digest")


@dataclass(frozen=True)
class StageRecord:
    """A submitted record for the active human-governed lifecycle phase."""

    phase: LifecyclePhase
    document: ImmutableReference
    authored_by: Actor
    discovery_kind: DiscoveryKind | None = None

    def __post_init__(self) -> None:
        if self.phase not in CONTENT_PHASES:
            raise EngagementError(f"{self.phase.value} does not accept a stage record")
        if self.document.kind is not ReferenceKind.STAGE_RECORD:
            raise EngagementError("stage records must reference a stage_record identity")
        if self.phase is LifecyclePhase.DISCOVERY and self.discovery_kind is None:
            raise EngagementError("a discovery record must declare its discovery kind")
        if self.phase is not LifecyclePhase.DISCOVERY and self.discovery_kind is not None:
            raise EngagementError("only a discovery record may declare a discovery kind")


@dataclass(frozen=True)
class RecordReview:
    """An independent review of a submitted record."""

    subject: ImmutableReference
    reviewer: Actor
    disposition: ReviewDisposition
    findings: ImmutableReference

    def __post_init__(self) -> None:
        if self.subject.kind is not ReferenceKind.STAGE_RECORD:
            raise EngagementError("a review must reference a stage_record identity")
        if self.findings.kind is not ReferenceKind.REVIEW_FINDINGS:
            raise EngagementError("review findings must use a review_findings identity")


@dataclass(frozen=True)
class RecordRevision:
    """An audited replacement of a draft that received changes-requested."""

    superseded: StageRecord
    review: RecordReview
    replacement: StageRecord

    def __post_init__(self) -> None:
        if self.review.subject != self.superseded.document:
            raise EngagementError("a revision review must reference the superseded record")
        if self.review.disposition is not ReviewDisposition.CHANGES_REQUESTED:
            raise EngagementError("only a changes-requested review can cause a record revision")
        if self.review.reviewer.identity == self.superseded.authored_by.identity:
            raise EngagementError("a superseded record author cannot review their own record")
        if self.replacement.phase is not self.superseded.phase:
            raise EngagementError("a replacement record must retain the superseded lifecycle phase")
        if self.replacement.document == self.superseded.document:
            raise EngagementError("a replacement record must have a new immutable identity")


@dataclass(frozen=True)
class NamedHumanDecision:
    """A durable decision made by a named human, never by a model."""

    decision_id: str
    kind: DecisionKind
    outcome: DecisionOutcome
    subject: ImmutableReference
    decided_by: Actor
    rationale: ImmutableReference

    def __post_init__(self) -> None:
        _required_text(self.decision_id, "decision id")
        if self.decided_by.kind is not ActorKind.HUMAN:
            raise EngagementError("only a named human may approve or accept an engagement")
        if self.rationale.kind is not ReferenceKind.DECISION_RATIONALE:
            raise EngagementError("a decision rationale must use a decision_rationale identity")


@dataclass(frozen=True)
class Engagement:
    """The versioned aggregate; external systems are kept as identity references only."""

    engagement_id: str
    mode: EngagementMode
    schema_version: str = ENGAGEMENT_SCHEMA_VERSION
    revision: int = 1
    phase: LifecyclePhase = LifecyclePhase.SETUP
    records: tuple[StageRecord, ...] = ()
    reviews: tuple[RecordReview, ...] = ()
    record_revisions: tuple[RecordRevision, ...] = ()
    decisions: tuple[NamedHumanDecision, ...] = ()
    approved_work: tuple[ImmutableReference, ...] = ()
    build_evidence: tuple[ImmutableReference, ...] = ()
    verification_results: tuple[ImmutableReference, ...] = ()

    def __post_init__(self) -> None:
        _required_text(self.engagement_id, "engagement id")
        if self.schema_version != ENGAGEMENT_SCHEMA_VERSION:
            raise EngagementError(f"unsupported engagement schema version: {self.schema_version}")
        if self.revision < 1:
            raise EngagementError("engagement revision must be positive")
        self._validate_record_sequence()
        self._validate_references()
        self._validate_reviews_and_decisions()

    @classmethod
    def create(cls, engagement_id: str, mode: EngagementMode) -> "Engagement":
        return cls(engagement_id=engagement_id, mode=mode)

    @property
    def current_record(self) -> StageRecord | None:
        return next((record for record in self.records if record.phase is self.phase), None)

    def submit(self, record: StageRecord) -> "Engagement":
        """Submit the one record permitted in the current content phase."""
        if self.phase not in CONTENT_PHASES:
            raise EngagementError(f"cannot submit a stage record during {self.phase.value}")
        if record.phase is not self.phase:
            raise EngagementError(f"expected a {self.phase.value} record, got {record.phase.value}")
        if self.current_record is not None:
            raise EngagementError(f"{self.phase.value} already has a submitted record")
        expected_discovery = (
            DiscoveryKind.ESTATE if self.mode is EngagementMode.MODERNISATION else DiscoveryKind.CAPABILITY
        )
        if self.phase is LifecyclePhase.DISCOVERY and record.discovery_kind is not expected_discovery:
            raise EngagementError(
                f"{self.mode.value} discovery must be {expected_discovery.value}; fictional estate records are refused"
            )
        return self._evolve(records=(*self.records, record))

    def review(self, review: RecordReview) -> "Engagement":
        """Record an independent review before a human can approve the active record."""
        record = self._require_current_record()
        if review.subject != record.document:
            raise EngagementError("review subject must be the current stage-record identity")
        if review.reviewer.identity == record.authored_by.identity:
            raise EngagementError("a record author cannot review their own record")
        if any(item.subject == review.subject for item in self.reviews):
            raise EngagementError("a stage record already has a review")
        return self._evolve(reviews=(*self.reviews, review))

    def revise(self, replacement: StageRecord) -> "Engagement":
        """Replace the active draft after changes-requested, retaining its audit chain."""
        record = self._require_current_record()
        review = self._review_for(record.document)
        if review is None or review.disposition is not ReviewDisposition.CHANGES_REQUESTED:
            raise EngagementError("record revision requires a changes-requested independent review")
        if replacement.phase is not self.phase:
            raise EngagementError("a replacement record must remain in the current lifecycle phase")
        if any(item.document == replacement.document for item in self.records) or any(
            revision.superseded.document == replacement.document for revision in self.record_revisions
        ):
            raise EngagementError("a replacement record must have a new immutable identity")
        record_index = self.records.index(record)
        records = (*self.records[:record_index], replacement, *self.records[record_index + 1 :])
        reviews = tuple(item for item in self.reviews if item.subject != record.document)
        revision = RecordRevision(superseded=record, review=review, replacement=replacement)
        return self._evolve(
            records=records,
            reviews=reviews,
            record_revisions=(*self.record_revisions, revision),
        )

    def approve(self, decision: NamedHumanDecision) -> "Engagement":
        """Approve a reviewed record; a model can neither approve nor self-accept it."""
        record = self._require_current_record()
        review = self._review_for(record.document)
        if review is None or review.disposition is not ReviewDisposition.APPROVED:
            raise EngagementError("a stage record requires an approved independent review before approval")
        if decision.kind is not DecisionKind.RECORD_APPROVAL or decision.outcome is not DecisionOutcome.APPROVED:
            raise EngagementError("a stage record requires a human record_approval decision with outcome approved")
        if decision.subject != record.document:
            raise EngagementError("record approval must reference the current stage-record identity")
        if decision.decided_by.identity == record.authored_by.identity:
            raise EngagementError("a record author cannot approve their own record")
        if self._decision_for(decision.subject, DecisionKind.RECORD_APPROVAL) is not None:
            raise EngagementError("a stage record already has a human approval")
        return self._evolve(decisions=(*self.decisions, decision))

    def advance(self) -> "Engagement":
        """Move only across the exact, governed transition from the current phase."""
        next_phase = NEXT_PHASE.get(self.phase)
        if next_phase is None:
            raise EngagementError("the accepted engagement has no further transition")
        if self.phase in CONTENT_PHASES:
            record = self._require_current_record()
            if self._review_for(record.document) is None:
                raise EngagementError("cannot advance without an independent review")
            if self._decision_for(record.document, DecisionKind.RECORD_APPROVAL) is None:
                raise EngagementError("cannot advance without named human approval")
        elif self.phase is LifecyclePhase.DELIVERY:
            if not self.approved_work or not self.build_evidence or not self.verification_results:
                raise EngagementError("delivery needs approved work, build evidence, and verification-result identities")
        elif self.phase is LifecyclePhase.VERIFIED:
            if not any(
                decision.kind is DecisionKind.ENGAGEMENT_ACCEPTANCE
                and decision.outcome is DecisionOutcome.ACCEPTED
                for decision in self.decisions
            ):
                raise EngagementError("verified delivery needs named human acceptance")
        return self._evolve(phase=next_phase)

    def add_approved_work(self, reference: ImmutableReference) -> "Engagement":
        self._require_delivery_phase()
        return self._add_reference("approved_work", reference, ReferenceKind.APPROVED_WORK)

    def add_build_evidence(self, reference: ImmutableReference) -> "Engagement":
        self._require_delivery_phase()
        if not self.approved_work:
            raise EngagementError("build evidence requires an approved-work identity")
        return self._add_reference("build_evidence", reference, ReferenceKind.BUILD_EVIDENCE)

    def add_verification_result(self, reference: ImmutableReference) -> "Engagement":
        self._require_delivery_phase()
        if not self.build_evidence:
            raise EngagementError("a verification result requires build-evidence identity")
        return self._add_reference("verification_results", reference, ReferenceKind.VERIFICATION_RESULT)

    def accept(self, decision: NamedHumanDecision) -> "Engagement":
        """Record the final acceptance without copying any verification result content."""
        if self.phase is not LifecyclePhase.VERIFIED:
            raise EngagementError("acceptance is permitted only after verification")
        if decision.kind is not DecisionKind.ENGAGEMENT_ACCEPTANCE or decision.outcome is not DecisionOutcome.ACCEPTED:
            raise EngagementError("final acceptance requires an engagement_acceptance decision with outcome accepted")
        if decision.subject not in self.verification_results:
            raise EngagementError("acceptance must reference a recorded verification-result identity")
        if self._decision_for(decision.subject, DecisionKind.ENGAGEMENT_ACCEPTANCE) is not None:
            raise EngagementError("this verification result already has an acceptance decision")
        return self._evolve(decisions=(*self.decisions, decision))

    def _evolve(self, **changes: object) -> "Engagement":
        return replace(self, revision=self.revision + 1, **changes)

    def _require_current_record(self) -> StageRecord:
        record = self.current_record
        if record is None:
            raise EngagementError(f"{self.phase.value} has no submitted stage record")
        return record

    def _require_delivery_phase(self) -> None:
        if self.phase is not LifecyclePhase.DELIVERY:
            raise EngagementError("external delivery references are permitted only during delivery")

    def _review_for(self, subject: ImmutableReference) -> RecordReview | None:
        return next((review for review in self.reviews if review.subject == subject), None)

    def _decision_for(self, subject: ImmutableReference, kind: DecisionKind) -> NamedHumanDecision | None:
        return next((decision for decision in self.decisions if decision.subject == subject and decision.kind is kind), None)

    def _add_reference(
        self, attribute: str, reference: ImmutableReference, expected_kind: ReferenceKind
    ) -> "Engagement":
        if reference.kind is not expected_kind:
            raise EngagementError(f"expected a {expected_kind.value} identity reference")
        existing = getattr(self, attribute)
        if reference in existing:
            raise EngagementError(f"duplicate {expected_kind.value} identity reference")
        return self._evolve(**{attribute: (*existing, reference)})

    def _validate_record_sequence(self) -> None:
        phase_index = CONTENT_PHASES.index(self.phase) if self.phase in CONTENT_PHASES else len(CONTENT_PHASES)
        if len(self.records) not in ({phase_index, phase_index + 1} if self.phase in CONTENT_PHASES else {len(CONTENT_PHASES)}):
            raise EngagementError("stage records do not form the lifecycle prefix for the current phase")
        for index, record in enumerate(self.records):
            if record.phase is not CONTENT_PHASES[index]:
                raise EngagementError("stage records must follow the declared lifecycle order")
            if record.phase is LifecyclePhase.DISCOVERY:
                expected = DiscoveryKind.ESTATE if self.mode is EngagementMode.MODERNISATION else DiscoveryKind.CAPABILITY
                if record.discovery_kind is not expected:
                    raise EngagementError(f"{self.mode.value} cannot use {record.discovery_kind!s} discovery")
        identifiers = [record.document.identifier for record in self.records]
        if len(identifiers) != len(set(identifiers)):
            raise EngagementError("stage-record identities must be unique")

    def _validate_references(self) -> None:
        groups = (
            (self.approved_work, ReferenceKind.APPROVED_WORK),
            (self.build_evidence, ReferenceKind.BUILD_EVIDENCE),
            (self.verification_results, ReferenceKind.VERIFICATION_RESULT),
        )
        for references, expected_kind in groups:
            if any(reference.kind is not expected_kind for reference in references):
                raise EngagementError(f"{expected_kind.value} references must contain only their declared identity kind")
            identifiers = [reference.identifier for reference in references]
            if len(identifiers) != len(set(identifiers)):
                raise EngagementError(f"{expected_kind.value} identities must be unique")
        if self.phase in {LifecyclePhase.VERIFIED, LifecyclePhase.ACCEPTED} and not (
            self.approved_work and self.build_evidence and self.verification_results
        ):
            raise EngagementError("verified and accepted engagements require all delivery identity references")
        if self.phase not in {LifecyclePhase.DELIVERY, LifecyclePhase.VERIFIED, LifecyclePhase.ACCEPTED} and any(
            (self.approved_work, self.build_evidence, self.verification_results)
        ):
            raise EngagementError("external delivery identities are permitted only after an approved delivery contract")

    def _validate_reviews_and_decisions(self) -> None:
        records = {record.document: record for record in self.records}
        superseded_records: dict[ImmutableReference, StageRecord] = {}
        expected_replacement: dict[LifecyclePhase, StageRecord] = {}
        for revision in self.record_revisions:
            if not isinstance(revision, RecordRevision):
                raise EngagementError("record revisions must contain RecordRevision values")
            if revision.superseded.document in records or revision.superseded.document in superseded_records:
                raise EngagementError("a superseded record identity may appear only once")
            predecessor = expected_replacement.get(revision.superseded.phase)
            if predecessor is not None and revision.superseded != predecessor:
                raise EngagementError("record revisions must form an unbroken replacement chain")
            superseded_records[revision.superseded.document] = revision.superseded
            expected_replacement[revision.superseded.phase] = revision.replacement
        for phase, replacement in expected_replacement.items():
            active = next((record for record in self.records if record.phase is phase), None)
            if active != replacement:
                raise EngagementError("the active record must be the end of its revision chain")
        seen_reviews: set[ImmutableReference] = set()
        for review in self.reviews:
            record = records.get(review.subject)
            if record is None:
                raise EngagementError("a review may reference only a submitted stage record")
            if review.reviewer.identity == record.authored_by.identity:
                raise EngagementError("a record author cannot review their own record")
            if review.subject in seen_reviews:
                raise EngagementError("a stage record may have only one review")
            seen_reviews.add(review.subject)
        decision_ids: set[str] = set()
        seen_approvals: set[tuple[ImmutableReference, DecisionKind]] = set()
        for decision in self.decisions:
            if decision.decision_id in decision_ids:
                raise EngagementError("decision ids must be unique")
            decision_ids.add(decision.decision_id)
            key = (decision.subject, decision.kind)
            if key in seen_approvals:
                raise EngagementError("a subject may have only one decision of each kind")
            seen_approvals.add(key)
            if decision.kind is DecisionKind.RECORD_APPROVAL:
                record = records.get(decision.subject)
                if record is None or decision.outcome is not DecisionOutcome.APPROVED:
                    raise EngagementError("record approval must approve a submitted stage record")
                if decision.decided_by.identity == record.authored_by.identity:
                    raise EngagementError("a record author cannot approve their own record")
            elif decision.kind is DecisionKind.ENGAGEMENT_ACCEPTANCE:
                if decision.outcome is not DecisionOutcome.ACCEPTED or decision.subject not in self.verification_results:
                    raise EngagementError("engagement acceptance must accept a verification-result identity")
                if self.phase not in {LifecyclePhase.VERIFIED, LifecyclePhase.ACCEPTED}:
                    raise EngagementError("engagement acceptance is permitted only after verification")

        completed_count = (
            CONTENT_PHASES.index(self.phase) if self.phase in CONTENT_PHASES else len(CONTENT_PHASES)
        )
        for record in self.records[:completed_count]:
            review = next((item for item in self.reviews if item.subject == record.document), None)
            if review is None or review.disposition is not ReviewDisposition.APPROVED:
                raise EngagementError("a completed lifecycle phase requires an approved independent review")
            approval = self._decision_for(record.document, DecisionKind.RECORD_APPROVAL)
            if approval is None:
                raise EngagementError("a completed lifecycle phase requires named human approval")
        if self.phase is LifecyclePhase.ACCEPTED and not any(
            decision.kind is DecisionKind.ENGAGEMENT_ACCEPTANCE
            and decision.outcome is DecisionOutcome.ACCEPTED
            for decision in self.decisions
        ):
            raise EngagementError("an accepted engagement requires named human acceptance")


def _label_values(markdown: str) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for line in markdown.splitlines():
        match = re.match(r"\s*(?:[-*]|\|)?\s*\**([A-Za-z][A-Za-z /-]*?)\**\s*:\s*(.*?)\s*$", line)
        if match:
            label = " ".join(match.group(1).lower().split())
            value = match.group(2)
            if value.startswith("**"):
                value = value[2:].lstrip()
            values.setdefault(label, []).append(value)
    return values


def _labels(markdown: str) -> set[str]:
    return set(_label_values(markdown))


def render_record_projection(facts: Mapping[str, str | tuple[str, ...]]) -> str:
    """Render aggregate-owned facts as the canonical human-readable record body."""
    lines: list[str] = []
    for field, value in facts.items():
        projected = value if isinstance(value, tuple) else (value,)
        if not projected:
            projected = ("[]",)
        lines.extend(f"- **{field}:** {item}" for item in projected)
    return "\n".join(lines) + "\n"


def validate_record_projection(
    markdown: str,
    facts: Mapping[str, str | tuple[str, ...]],
) -> list[str]:
    """Exact-compare a readable record with its aggregate-owned structured facts."""
    if markdown == render_record_projection(facts):
        return []
    return ["readable record is not the canonical structured-fact projection"]


def _contains_placeholder_identity(value: str, *, allow_none: bool = False) -> bool:
    tokens = re.findall(r"[a-z0-9-]+", value.casefold())
    return any(
        is_placeholder_identity(token) and not (allow_none and token == "none")
        for token in tokens
    )


def _checkpoint_expectations_have_owners(values: list[str]) -> bool:
    for value in values:
        for expectation in (part.strip() for part in value.split(";") if part.strip()):
            if "@" in expectation:
                checkpoint, owner = expectation.rsplit("@", 1)
            elif "—" in expectation:
                checkpoint, owner = expectation.split("—", 1)
            else:
                return False
            if (
                not checkpoint.strip()
                or not owner.strip()
                or _contains_placeholder_identity(owner)
            ):
                return False
    return bool(values)


_DELIVERY_TABLE_HEADER = (
    "package id",
    "summary",
    "owner",
    "validator",
    "depends on",
    "gate id",
    "gate requirement",
)


def _delivery_inventory_rows(markdown: str) -> list[dict[str, str]]:
    table_rows = [
        tuple(cell.strip() for cell in line.strip().strip("|").split("|"))
        for line in markdown.splitlines()
        if line.strip().startswith("|") and line.strip().endswith("|")
    ]
    for index, row in enumerate(table_rows):
        if tuple(cell.casefold() for cell in row) != _DELIVERY_TABLE_HEADER:
            continue
        result: list[dict[str, str]] = []
        for candidate in table_rows[index + 1 :]:
            if len(candidate) != len(_DELIVERY_TABLE_HEADER):
                continue
            if all(re.fullmatch(r":?-{3,}:?", cell) for cell in candidate):
                continue
            result.append(dict(zip(_DELIVERY_TABLE_HEADER, candidate, strict=True)))
        return result
    return []


def _validate_delivery_inventory(markdown: str) -> list[str]:
    rows = _delivery_inventory_rows(markdown)
    if not rows:
        return [
            "package inventory must contain at least one complete package row",
            "dependency inventory must be represented by package rows",
            "gate inventory must contain at least one complete gate row",
        ]
    failures: list[str] = []
    for index, row in enumerate(rows, start=1):
        for field in ("package id", "summary", "owner", "validator", "gate id", "gate requirement"):
            if not row[field] or _contains_placeholder_identity(row[field]):
                failures.append(f"delivery row {index} must contain a non-placeholder {field}")
        dependency = row["depends on"]
        if not dependency or _contains_placeholder_identity(dependency, allow_none=True):
            failures.append(f"delivery row {index} must declare dependencies or an explicit none marker")
    return failures


def validate_stage(path: Path, stage: str) -> list[str]:
    """Validate one legacy record projection against the aggregate-owned schema."""
    if stage not in STAGE_FIELDS:
        raise ValueError(f"unknown stage: {stage}")
    markdown = path.read_text(encoding="utf-8")
    values = _label_values(markdown)
    labels = set(values)
    required = (*STAGE_FIELDS[stage], *REVIEW_FIELDS)
    failures = [field for field in required if field not in labels]
    failures.extend(
        f"{field} must not be empty"
        for field in required
        if field in values and not any(value.strip() for value in values[field])
    )
    for field in ("authorities", "lineage/checkpoint expectations"):
        if field in values and any(_contains_placeholder_identity(value) for value in values[field]):
            failures.append(f"{field} must name accountable identities, not placeholders")
    if "lineage/checkpoint expectations" in values and not _checkpoint_expectations_have_owners(
        values["lineage/checkpoint expectations"]
    ):
        failures.append("lineage/checkpoint expectations must name an owner for every checkpoint")
    if stage == "implementation_plan":
        for field in ("package inventory", "dependency inventory", "gate inventory"):
            if field in values and any(
                _contains_placeholder_identity(value, allow_none=field == "dependency inventory")
                for value in values[field]
            ):
                failures.append(f"{field} must not contain placeholders")
        failures.extend(_validate_delivery_inventory(markdown))
    if stage == "outcome" and "success criteria" in values:
        valid_criteria: list[Mapping[str, object]] = []
        for raw in values["success criteria"]:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                failures.append("success criteria must be canonical JSON")
                continue
            criteria = parsed if isinstance(parsed, list) else [parsed]
            if not criteria:
                failures.append("success criteria must contain at least one criterion")
                continue
            for index, criterion in enumerate(criteria, start=1):
                criterion_failures = validate_success_criterion_contract(criterion)
                failures.extend(f"success criteria {index}: {failure}" for failure in criterion_failures)
                if not criterion_failures:
                    valid_criteria.append(criterion)
        declared_signals = tuple(
            part.strip().removesuffix(".").casefold()
            for raw in values.get("success signals", ())
            for part in raw.split(";")
            if part.strip()
        )
        criterion_signals = tuple(str(item["signal"]).casefold() for item in valid_criteria)
        if valid_criteria and criterion_signals != declared_signals:
            failures.append("success criteria must map one-to-one to the declared signals")
        acceptance = " ".join(values.get("acceptance rules", ())).casefold()
        evidence = " ".join(values.get("evidence", ())).casefold()
        for index, criterion in enumerate(valid_criteria, start=1):
            if str(criterion["acceptance_rule"]).casefold() not in acceptance:
                failures.append(f"success criteria {index}: acceptance rule is not declared")
            references = [criterion["validator"], *criterion["evidence"]]
            for reference in references:
                token = f"{reference['identifier']}@{reference['version']}#{reference['digest']}".casefold()
                if token not in evidence:
                    failures.append(f"success criteria {index}: reference is not approved evidence: {token}")
    return failures


def validate_template_projection(path: Path) -> list[str]:
    """Reject Koine templates that omit or invent aggregate-owned fields."""
    expected = KOINE_TEMPLATE_FIELDS.get(path.name)
    if expected is None:
        raise ValueError(f"unknown Koine template: {path.name}")
    labels = _labels(path.read_text(encoding="utf-8"))
    required = set((*expected, *REVIEW_FIELDS)) if path.name != "instance-context.md" else set(expected)
    missing = [field for field in (*expected, *(() if path.name == "instance-context.md" else REVIEW_FIELDS)) if field not in labels]
    unexpected = sorted(labels - required)
    return [*missing, *(f"unexpected field: {field}" for field in unexpected)]


def validate_examples(root: Path) -> dict[str, list[str]]:
    """Validate the two readable example modes through the aggregate projections."""
    failures: dict[str, list[str]] = {}
    for mode, stages in MODE_STAGES.items():
        directory = root / mode / ("customer-service-reporting" if mode == "modernisation" else "renewable-asset-observability")
        for filename, stage in FILE_STAGES.items():
            path = directory / filename
            if stage not in stages:
                if path.exists():
                    failures[str(path)] = ["stage is not permitted for this mode"]
                continue
            missing = validate_stage(path, stage) if path.exists() else ["record is missing"]
            if missing:
                failures[str(path)] = missing
    return failures
