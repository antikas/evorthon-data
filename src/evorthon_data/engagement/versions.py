"""Cutting a version over chosen spans, and the record of the human who takes it.

A version is the boundary a named person takes a chosen set of lineage spans
through. This module composes one. It reads the spans the use-case record
derives, takes the spans a person selected, works out the target outputs those
spans reach and the spans left outside them, snapshots the standing conditions
as they stand at the cut, and builds the immutable version through the type the
use-case record owns. Every version invariant stays with that type.

The projection digest and the suggested disposition arrive as caller-supplied
values and are stored exactly as they are given. Recomputing the projection
belongs to the route that composes the cut, so no readiness module is read
here.

The acceptance record is the durable artefact of the decision. It carries the
named human decision, the scenario cases the version was judged on, how the
frozen evidence of those cases reads as a whole, and the suggested disposition
as advice. Evidence generated to fill a gap is recorded with its own label and
is never a reason to refuse: what a person takes, and on what evidence, is that
person's call, and the record shows both.

A refusal here means the record would contradict itself: a version the use case
does not hold, a case the version does not name, an evidence identity the
record does not hold, a summary that is not what the cases read, or a value
outside the vocabulary this module reads. Nothing is refused for the quality of
the evidence behind it.
"""
# evorthon-implements: EVD-README-048
# evorthon-implements: EVD-README-047
# evorthon-implements: EVD-README-010
from __future__ import annotations

# evorthon-component: engagement
from dataclasses import dataclass
from enum import Enum

from ..verification.domain.contracts import EvidenceProvenance, Identity
from .aggregate import (
    Actor,
    DecisionKind,
    DecisionOutcome,
    EngagementError,
    ImmutableReference,
    NamedHumanDecision,
    ReferenceKind,
)
from .use_case import CoverageStatement, SegmentBoundary, UseCase, Version


# The identity kinds that can stand as the evidence one cut rests on.
EVIDENCE_REFERENCE_KINDS = frozenset(
    {ReferenceKind.VERIFICATION_RESULT, ReferenceKind.BUILD_EVIDENCE}
)


class RefusalReason(str, Enum):
    """The closed set of integrity reasons for refusing a cut or a record."""

    INVALID_INPUT = "invalid-input"
    UNDECLARED_REPRESENTATION = "undeclared-representation"
    UNKNOWN_VERSION = "unknown-version"
    UNKNOWN_CASE_IDENTITY = "unknown-case-identity"
    CONTRADICTORY_EVIDENCE = "contradictory-evidence"
    CONTRADICTORY_SUMMARY = "contradictory-summary"


class VersionError(EngagementError):
    """Raised when a cut or a record would contradict what the use case holds."""

    def __init__(self, reason: RefusalReason, detail: str) -> None:
        super().__init__(f"{reason.value}: {detail}")
        self.reason = reason


def _refuse(reason: RefusalReason, detail: str) -> VersionError:
    return VersionError(reason, detail)


def _require_instance(value: object, declared: type, label: str) -> None:
    if not isinstance(value, declared):
        raise _refuse(RefusalReason.INVALID_INPUT, f"{label} is required")


def _require_tuple(value: object, label: str) -> None:
    if not isinstance(value, tuple):
        raise _refuse(RefusalReason.INVALID_INPUT, f"{label} must be recorded in a tuple")


def evidence_provenance_summary(cases: tuple["CaseEvidence", ...]) -> EvidenceProvenance:
    """Report how the evidence behind a whole version reads.

    The reading follows the one the verification domain owns for a single case.
    The whole reads as real only when every case reads as real, and it reads as
    generated only when every case reads that way. Any other combination, and a
    record that cites no case at all, reads as mixed. The value labels the
    record and decides nothing.
    """
    _require_tuple(cases, "the cases of a record")
    declared = set()
    for case in cases:
        _require_instance(case, CaseEvidence, "each case reading")
        declared.add(case.evidence_provenance)
    if declared == {EvidenceProvenance.REAL}:
        return EvidenceProvenance.REAL
    if declared == {EvidenceProvenance.SYNTHETIC}:
        return EvidenceProvenance.SYNTHETIC
    return EvidenceProvenance.MIXED


@dataclass(frozen=True)
class CaseEvidence:
    """One scenario case and how the frozen evidence of that case reads.

    The reading is the value the verification domain derives for the case. It
    is taken as given here, and no case content is copied.
    """

    case: Identity
    evidence_provenance: EvidenceProvenance

    def __post_init__(self) -> None:
        if not isinstance(self.case, Identity):
            raise _refuse(RefusalReason.INVALID_INPUT, "a case reading must name its case by identity")
        if not isinstance(self.evidence_provenance, EvidenceProvenance):
            raise _refuse(
                RefusalReason.UNDECLARED_REPRESENTATION,
                "a case reading must carry a declared evidence reading",
            )


@dataclass(frozen=True)
class AcceptanceRecord:
    """One named person's decision on one version, and the evidence it rested on.

    The record names the version by identity, reads every scenario case that
    version names, carries the summary those readings make, and repeats the
    suggested disposition the version was cut with. The suggestion is advice.
    """

    decision: NamedHumanDecision
    version: ImmutableReference
    cases: tuple[CaseEvidence, ...]
    evidence_provenance: EvidenceProvenance
    suggested_disposition: str | None = None

    def __post_init__(self) -> None:
        _require_instance(self.decision, NamedHumanDecision, "a named human decision")
        _require_instance(self.version, ImmutableReference, "a version identity")
        if self.version.kind is not ReferenceKind.USE_CASE_VERSION:
            raise _refuse(RefusalReason.INVALID_INPUT, "a record must name a use_case_version identity")
        if self.decision.subject != self.version:
            raise _refuse(
                RefusalReason.INVALID_INPUT,
                "a record and its decision name one version",
            )
        summary = evidence_provenance_summary(self.cases)
        named = [case.case for case in self.cases]
        if len(set(named)) != len(named):
            raise _refuse(RefusalReason.CONTRADICTORY_EVIDENCE, "a record reads each case once")
        if not isinstance(self.evidence_provenance, EvidenceProvenance):
            raise _refuse(
                RefusalReason.UNDECLARED_REPRESENTATION,
                "a record must carry a declared evidence reading",
            )
        if self.evidence_provenance is not summary:
            raise _refuse(
                RefusalReason.CONTRADICTORY_SUMMARY,
                "the summary is not what the cases of the record read",
            )
        if self.suggested_disposition is not None and not self.suggested_disposition.strip():
            raise _refuse(RefusalReason.INVALID_INPUT, "a suggested disposition is required")

    @property
    def cases_read(self) -> tuple[Identity, ...]:
        """The scenario cases this record read, in the order it read them."""
        return tuple(case.case for case in self.cases)


def cut_version(
    use_case: UseCase,
    version_identity: ImmutableReference,
    covered_segments: tuple[str, ...],
    readiness_projection: ImmutableReference,
    *,
    scenario_case_versions: tuple[Identity, ...] = (),
    packages: tuple[ImmutableReference, ...] = (),
    evidence: tuple[ImmutableReference, ...] = (),
    suggested_disposition: str | None = None,
) -> tuple[UseCase, Version]:
    """Cut one version over the spans a person selected.

    The selected spans decide the coverage: the target outputs are the ones
    those spans reach, and every other span the record derives is named as
    outside the version. The standing conditions are snapshotted as they stand.
    The projection reference and the suggested disposition are stored exactly as
    given; nothing here recomputes either.

    Returns the use case with the version cut on it and the version itself.
    """
    _require_instance(use_case, UseCase, "a use case")
    _require_instance(version_identity, ImmutableReference, "a version identity")
    _require_instance(readiness_projection, ImmutableReference, "a projection reference")
    _require_tuple(covered_segments, "the spans a cut covers")
    _validate_evidence(use_case, evidence)
    spans = use_case.segments()
    selected = set(covered_segments)
    version = Version(
        identity=version_identity,
        coverage=CoverageStatement(
            covered_segments=tuple(covered_segments),
            covered_outputs=tuple(
                span.segment_id
                for span in spans
                if span.reaches is SegmentBoundary.TARGET_OUTPUT and span.segment_id in selected
            ),
            segments_outside=tuple(
                span.segment_id for span in spans if span.segment_id not in selected
            ),
        ),
        readiness_projection=readiness_projection,
        scenario_case_versions=scenario_case_versions,
        packages=packages,
        conditions=use_case.conditions,
        suggested_disposition=suggested_disposition,
    )
    return use_case.cut_version(version), version


def record_acceptance(
    use_case: UseCase,
    version: Version,
    *,
    decision_id: str,
    decided_by: Actor,
    rationale: ImmutableReference,
    cases: tuple[CaseEvidence, ...] = (),
) -> AcceptanceRecord:
    """Record one named person's decision on one version the use case holds.

    The record reads every scenario case the version names and no other. The
    summary of those readings is derived here and stored on the record, and the
    suggested disposition the version was cut with is repeated as advice. A
    reading that says the evidence was generated rather than real is recorded
    and never refused.
    """
    _require_instance(use_case, UseCase, "a use case")
    _require_instance(version, Version, "a version")
    if version not in use_case.versions:
        raise _refuse(
            RefusalReason.UNKNOWN_VERSION,
            "the use case does not hold this version: " + version.identity.identifier,
        )
    _validate_cases(version, cases)
    return AcceptanceRecord(
        decision=NamedHumanDecision(
            decision_id=decision_id,
            kind=DecisionKind.VERSION_ACCEPTANCE,
            outcome=DecisionOutcome.ACCEPTED,
            subject=version.identity,
            decided_by=decided_by,
            rationale=rationale,
        ),
        version=version.identity,
        cases=cases,
        evidence_provenance=evidence_provenance_summary(cases),
        suggested_disposition=version.suggested_disposition,
    )


def _validate_evidence(use_case: UseCase, evidence: object) -> None:
    """Refuse evidence the use-case record cannot show."""
    _require_tuple(evidence, "the evidence of a cut")
    recorded = {result.result for result in use_case.scenario_results}
    seen: set[ImmutableReference] = set()
    for reference in evidence:
        _require_instance(reference, ImmutableReference, "each evidence identity")
        if reference.kind not in EVIDENCE_REFERENCE_KINDS:
            raise _refuse(
                RefusalReason.INVALID_INPUT,
                "an evidence identity names a result or a build artefact: " + reference.identifier,
            )
        if reference in seen:
            raise _refuse(
                RefusalReason.CONTRADICTORY_EVIDENCE,
                "an evidence identity is named twice: " + reference.identifier,
            )
        if reference.kind is ReferenceKind.VERIFICATION_RESULT and reference not in recorded:
            raise _refuse(
                RefusalReason.CONTRADICTORY_EVIDENCE,
                "the record holds no such result: " + reference.identifier,
            )
        seen.add(reference)


def _validate_cases(version: Version, cases: object) -> None:
    """Refuse a set of readings that does not match the cases the version names."""
    _require_tuple(cases, "the cases of a record")
    named = set(version.scenario_case_versions)
    read: set[Identity] = set()
    for case in cases:
        _require_instance(case, CaseEvidence, "each case reading")
        if case.case not in named:
            raise _refuse(
                RefusalReason.UNKNOWN_CASE_IDENTITY,
                "the version does not name this case: " + case.case.identifier,
            )
        read.add(case.case)
    unread = sorted(case.identifier for case in named - read)
    if unread:
        raise _refuse(
            RefusalReason.CONTRADICTORY_SUMMARY,
            "the record does not read every case the version names: " + ", ".join(unread),
        )
