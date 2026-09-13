"""Read-only intake of an approved verification case.

Intake is the step between an approved case and any comparison. It reads
declared facts and stored evidence, changes nothing, and leaves receipts a
later engine can rely on.

The step does four things.

1. It validates the case through the one fail-closed validator the enforcement
   component owns. Intake adds no second validator and relaxes nothing.
2. It reads every evidence record the case references, through the evidence
   repository contract, and confirms each record against the case.
3. It derives receipts for the frozen case facts and for the run context. Every
   digest a receipt carries is computed here from canonical bytes through the
   deterministic core. None is copied from a value an environment supplied.
4. It prepares the frozen facts a candidate runner receives. It never asks a
   runner to produce anything, so the step stays read-only.

Intake observes declared facts and stored evidence only. It does not read
dataset rows, so a receipt for a frozen dataset binds the whole declaration
rather than the rows; an engine that later reads rows derives its own receipt
over those bytes. A receipt's subject identity carries the digest that receipt
observes, so a reader comparing the two is asking whether the declaration the
run read is the declaration the case froze, and nothing else.

Refusals are integrity refusals. Intake refuses evidence a repository does not
hold, evidence whose bytes do not match the digest the case approved, evidence
outside the validity the case's declared run instant requires, evidence that
contradicts itself or the case, and a candidate the environment declares
incompletely. It refuses nothing for being synthetic and nothing for the level
of assurance a case declares, so a synthetic case with complete evidence takes
exactly the same path as any other.

The module reads no file, no clock, no environment variable and no locale, and
it draws no random value. Two runs over the same case and the same stored
evidence produce byte-identical receipts.
"""
# evorthon-implements: EVD-README-020
from __future__ import annotations

# evorthon-component: verification_workflows

from collections.abc import Callable
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from enum import Enum
from types import MappingProxyType

from evorthon_data.verification.core.canonical import canonical_digest, case_digest, record_digest
from evorthon_data.verification.domain.contracts import (
    CandidateIdentity,
    ContextIdentity,
    DatasetRole,
    EvidenceReference,
    FrozenDataset,
    Identity,
    IndependentlyDerivedReceipt,
    ReceiptSubject,
    VerificationCase,
)
from evorthon_data.verification.enforcement.validation import (
    inspect_verification_case,
    inspect_verification_record,
)
from evorthon_data.verification.ports.contracts import (
    CANONICALISATION_BINDING,
    CandidateDeclaration,
    CandidateRunnerPort,
    EvidenceNotHeld,
    EvidenceRepositoryPort,
    FactBinding,
    FrozenCaseFacts,
    FrozenFact,
    GRAIN_BINDING,
    PortRefusal,
    SCHEMA_BINDING,
    StoredEvidence,
)


INTAKE_WORKFLOW_FORM = "evorthon.verification.intake.v1"
INTAKE_RECEIPT_VERSION = "evorthon.verification.intake.receipt.v1"
INTAKE_AUTHORITY_ID = "evorthon.verification.intake"

# A frozen dataset's declared role selects the receipt subject that stands for
# it. The map is explicit so a new role cannot silently lose its receipt.
RECEIPT_SUBJECT_BY_ROLE = MappingProxyType(
    {
        DatasetRole.INPUT: ReceiptSubject.INPUT,
        DatasetRole.REFERENCE: ReceiptSubject.REFERENCE,
        DatasetRole.ENRICHMENT: ReceiptSubject.ENRICHMENT,
        DatasetRole.PRIOR_STATE: ReceiptSubject.PRIOR_STATE,
    }
)


class IntakeRefusalReason(str, Enum):
    """The closed set of integrity reasons for refusing to intake a case."""

    CASE_INVALID = "case-invalid"
    EVIDENCE_MISSING = "evidence-missing"
    EVIDENCE_ALTERED = "evidence-altered"
    EVIDENCE_EXPIRED = "evidence-expired"
    EVIDENCE_INCONSISTENT = "evidence-inconsistent"
    CANDIDATE_INCONSISTENT = "candidate-inconsistent"


@dataclass(frozen=True)
class IntakeRefusal:
    """One deterministic integrity reason a case cannot enter verification."""

    reason: IntakeRefusalReason
    subject: str
    detail: str


class IntakeRefused(ValueError):
    """Raised when intake cannot accept a case with declared meaning."""

    def __init__(self, refusals: tuple[IntakeRefusal, ...]):
        self.refusals = refusals
        detail = "; ".join(f"{refusal.reason.value} at {refusal.subject}: {refusal.detail}" for refusal in refusals)
        super().__init__(detail)


@dataclass(frozen=True)
class ConfirmedEvidence:
    """One evidence record read from a repository and confirmed against the case.

    ``observed_digest`` is the digest intake computed over the stored bytes. It
    equals the digest the case approved, because a record whose bytes differ is
    refused before it reaches this record.
    """

    reference: EvidenceReference
    observed_digest: str
    recorded_at: str
    valid_until: str


@dataclass(frozen=True)
class AcceptedIntake:
    """The read-only outcome of accepting one case for verification."""

    case: Identity
    candidate: CandidateIdentity
    context: ContextIdentity
    receipts: tuple[IndependentlyDerivedReceipt, ...]
    receipt_digests: tuple[str, ...]
    confirmed_evidence: tuple[ConfirmedEvidence, ...]
    candidate_facts: FrozenCaseFacts
    intake_digest: str


@dataclass(frozen=True)
class IntakeReport:
    """Every integrity refusal found, and the accepted intake when there is none."""

    refusals: tuple[IntakeRefusal, ...]
    intake: AcceptedIntake | None = None

    @property
    def accepted(self) -> bool:
        return not self.refusals and self.intake is not None

    def require_accepted(self) -> AcceptedIntake:
        if self.refusals or self.intake is None:
            raise IntakeRefused(self.refusals)
        return self.intake


def confirm_intake_case(
    intake: AcceptedIntake,
    case: VerificationCase,
    refuse: Callable[[str, str], Exception],
) -> None:
    """Confirm one accepted intake answers for the case a later step is running.

    A step that reads receipts or confirmed evidence has to know they were taken
    for the case in hand, so this rule and the words it uses live here once.
    ``refuse`` receives the subject and the detail and returns the refusal the
    calling step raises, which keeps each step's own refusal vocabulary its own.
    """
    if not isinstance(intake, AcceptedIntake):
        raise refuse("intake", "an accepted intake is required before a case can be verified")
    declared = (intake.case.identifier, intake.case.version, intake.case.digest)
    if declared != (case.case_id, case.version, case_digest(case)):
        raise refuse(
            "intake.case",
            "the accepted intake answers for a different case identity, version or digest",
        )


def _refuse(
    refusals: list[IntakeRefusal],
    reason: IntakeRefusalReason,
    subject: str,
    detail: str,
) -> None:
    refusals.append(IntakeRefusal(reason=reason, subject=subject, detail=detail))


def _instant(value: object) -> datetime | None:
    """Return the declared instant, or nothing when the text does not name one."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _collect_evidence(node: object, found: list[EvidenceReference]) -> None:
    if isinstance(node, EvidenceReference):
        found.append(node)
        return
    if isinstance(node, tuple):
        for item in node:
            _collect_evidence(item, found)
        return
    if is_dataclass(node) and not isinstance(node, type):
        for field in fields(node):
            _collect_evidence(getattr(node, field.name), found)


def declared_evidence(case: VerificationCase) -> tuple[EvidenceReference, ...]:
    """Return every distinct evidence reference the case declares, in a stable order."""
    found: list[EvidenceReference] = []
    _collect_evidence(case, found)
    distinct = sorted({reference for reference in found}, key=lambda reference: (reference.evidence_id, reference.version))
    return tuple(distinct)


def _requested_references(
    case: VerificationCase, refusals: list[IntakeRefusal]
) -> tuple[EvidenceReference, ...]:
    """Return the references to read, refusing an identifier the case declares twice over."""
    requested: list[EvidenceReference] = []
    by_identifier: dict[str, list[EvidenceReference]] = {}
    for reference in declared_evidence(case):
        by_identifier.setdefault(reference.evidence_id, []).append(reference)
    for evidence_id, references in by_identifier.items():
        if len(references) > 1:
            _refuse(
                refusals,
                IntakeRefusalReason.EVIDENCE_INCONSISTENT,
                f"case.evidence[{evidence_id}]",
                "the case declares one evidence reference with more than one version or digest",
            )
            continue
        requested.append(references[0])
    return tuple(requested)


def _read_evidence(
    reference: EvidenceReference,
    repository: EvidenceRepositoryPort,
    refusals: list[IntakeRefusal],
) -> StoredEvidence | None:
    subject = f"evidence[{reference.evidence_id}]"
    try:
        record = repository.read_evidence(reference.evidence_id, reference.version)
    except EvidenceNotHeld as refusal:
        _refuse(refusals, IntakeRefusalReason.EVIDENCE_MISSING, subject, f"the repository does not hold the reference: {refusal}")
        return None
    except PortRefusal as refusal:
        _refuse(refusals, IntakeRefusalReason.EVIDENCE_MISSING, subject, f"the repository refused to answer for the reference: {refusal}")
        return None
    if not isinstance(record, StoredEvidence):
        _refuse(refusals, IntakeRefusalReason.EVIDENCE_MISSING, subject, "the repository answered with no evidence record")
        return None
    return record


def _confirm_evidence(
    reference: EvidenceReference,
    record: StoredEvidence,
    run_instant: datetime,
    refusals: list[IntakeRefusal],
) -> ConfirmedEvidence | None:
    subject = f"evidence[{reference.evidence_id}]"
    if record.evidence_id != reference.evidence_id or record.version != reference.version:
        _refuse(
            refusals,
            IntakeRefusalReason.EVIDENCE_INCONSISTENT,
            subject,
            "the record answers for a different evidence identity or version",
        )
        return None
    if not isinstance(record.content, bytes):
        _refuse(refusals, IntakeRefusalReason.EVIDENCE_INCONSISTENT, subject, "the record carries no stored bytes")
        return None
    observed = canonical_digest(record.content)
    if record.declared_digest != observed:
        _refuse(
            refusals,
            IntakeRefusalReason.EVIDENCE_INCONSISTENT,
            subject,
            "the record declares a digest its own stored bytes do not produce",
        )
        return None
    if reference.digest != observed:
        _refuse(
            refusals,
            IntakeRefusalReason.EVIDENCE_ALTERED,
            subject,
            "the stored bytes do not produce the digest the case approved",
        )
        return None
    recorded_at = _instant(record.recorded_at)
    valid_until = _instant(record.valid_until)
    if recorded_at is None or valid_until is None:
        _refuse(
            refusals,
            IntakeRefusalReason.EVIDENCE_INCONSISTENT,
            subject,
            "the record declares a validity that cannot be read as dated instants with an offset",
        )
        return None
    if valid_until < recorded_at:
        _refuse(
            refusals,
            IntakeRefusalReason.EVIDENCE_INCONSISTENT,
            subject,
            "the record declares a validity that ends before it starts",
        )
        return None
    if not recorded_at <= run_instant <= valid_until:
        _refuse(
            refusals,
            IntakeRefusalReason.EVIDENCE_EXPIRED,
            subject,
            "the declared validity does not cover the run instant the case context declares",
        )
        return None
    return ConfirmedEvidence(
        reference=reference,
        observed_digest=observed,
        recorded_at=record.recorded_at,
        valid_until=record.valid_until,
    )


def _declared_candidate(
    runner: CandidateRunnerPort, refusals: list[IntakeRefusal]
) -> CandidateIdentity | None:
    try:
        declaration = runner.declare_candidate()
    except PortRefusal as refusal:
        _refuse(
            refusals,
            IntakeRefusalReason.CANDIDATE_INCONSISTENT,
            "candidate",
            f"the runner refused to declare a candidate artefact: {refusal}",
        )
        return None
    if not isinstance(declaration, CandidateDeclaration):
        _refuse(
            refusals,
            IntakeRefusalReason.CANDIDATE_INCONSISTENT,
            "candidate",
            "the runner declared no candidate artefact",
        )
        return None
    candidate = CandidateIdentity(
        candidate_id=declaration.candidate_id,
        version=declaration.version,
        artifact_digest=declaration.artifact_digest,
    )
    issues = inspect_verification_record(candidate).issues
    for issue in issues:
        _refuse(
            refusals,
            IntakeRefusalReason.CANDIDATE_INCONSISTENT,
            f"candidate.{issue.path}",
            f"{issue.code}: {issue.message}",
        )
    return None if issues else candidate


def _bindings(dataset: FrozenDataset) -> tuple[FactBinding, ...]:
    return (
        FactBinding(SCHEMA_BINDING, dataset.schema.schema_id, dataset.schema.version, record_digest(dataset.schema)),
        FactBinding(GRAIN_BINDING, dataset.grain.grain_id, dataset.grain.version, record_digest(dataset.grain)),
        FactBinding(
            CANONICALISATION_BINDING,
            dataset.canonicalisation.canonicalisation_id,
            dataset.canonicalisation.version,
            record_digest(dataset.canonicalisation),
        ),
    )


def frozen_case_facts(case: VerificationCase) -> FrozenCaseFacts:
    """Return the frozen facts a candidate runner receives for this case.

    The surface carries the case identity, the declared run context and one
    entry per frozen dataset with its declared bindings and digests. No
    expected output appears in it, because an expected output is the oracle the
    candidate's own outputs are measured against.
    """
    facts = tuple(
        FrozenFact(
            subject=dataset.role.value,
            fact_id=dataset.dataset_id,
            version=dataset.version,
            content_digest=dataset.content_digest,
            row_count=dataset.row_count,
            bindings=_bindings(dataset),
        )
        for dataset in case.frozen_datasets
    )
    return FrozenCaseFacts(
        case_id=case.case_id,
        case_version=case.version,
        case_digest=case_digest(case),
        context_id=case.context.context_id,
        context_version=case.context.version,
        context_digest=case.context.digest,
        logical_run_time=case.context.logical_run_time,
        cutoff_time=case.context.cutoff_time,
        timezone=case.context.timezone,
        facts=facts,
    )


def _authority() -> Identity:
    """Return the identity of the derivation this module performs."""
    return Identity(
        identifier=INTAKE_AUTHORITY_ID,
        version=INTAKE_WORKFLOW_FORM,
        digest=canonical_digest(INTAKE_WORKFLOW_FORM.encode("ascii")),
    )


def _receipts(
    case: VerificationCase, confirmed: tuple[ConfirmedEvidence, ...]
) -> tuple[IndependentlyDerivedReceipt, ...]:
    """Derive one receipt per frozen case fact and one for the run context.

    A receipt carries the subject as the case declares it and the digest intake
    computed over the whole declaration through the deterministic core. The
    observed digest therefore binds the declaration and not the rows, because
    intake reads no rows. An engine that later reads rows derives its own
    receipt over those bytes.

    The subject identity carries the same digest the receipt observes, because
    a receipt answers for what it read. A reader that finds the two apart is
    reading a receipt taken over an altered declaration, which is the one thing
    that comparison is asked. The declaration's own content digest is the
    runner's claim about bytes and stays where the case states it, on the
    frozen dataset and on the frozen facts a candidate runner receives; no
    receipt restates it.
    """
    authority = _authority()
    evidence = tuple(item.reference for item in confirmed)
    receipts = [
        IndependentlyDerivedReceipt(
            receipt_id=f"{case.case_id}/{dataset.role.value}/{dataset.dataset_id}",
            version=INTAKE_RECEIPT_VERSION,
            subject=RECEIPT_SUBJECT_BY_ROLE[dataset.role],
            subject_identity=Identity(dataset.dataset_id, dataset.version, record_digest(dataset)),
            observed_digest=record_digest(dataset),
            derived_by=authority,
            evidence=evidence,
        )
        for dataset in case.frozen_datasets
    ]
    receipts.append(
        IndependentlyDerivedReceipt(
            receipt_id=f"{case.case_id}/context/{case.context.context_id}",
            version=INTAKE_RECEIPT_VERSION,
            subject=ReceiptSubject.CONTEXT,
            subject_identity=Identity(
                case.context.context_id, case.context.version, record_digest(case.context)
            ),
            observed_digest=record_digest(case.context),
            derived_by=authority,
            evidence=evidence,
        )
    )
    return tuple(receipts)


def inspect_intake(
    case: VerificationCase,
    *,
    evidence_repository: EvidenceRepositoryPort,
    candidate_runner: CandidateRunnerPort,
) -> IntakeReport:
    """Collect every integrity refusal for one case without deciding anything else."""
    refusals: list[IntakeRefusal] = []
    for issue in inspect_verification_case(case).issues:
        _refuse(refusals, IntakeRefusalReason.CASE_INVALID, issue.path, f"{issue.code}: {issue.message}")
    if refusals:
        return IntakeReport(tuple(refusals))
    run_instant = _instant(case.context.logical_run_time)
    if run_instant is None:
        _refuse(
            refusals,
            IntakeRefusalReason.CASE_INVALID,
            "case.context.logical_run_time",
            "the declared run instant cannot be read as a dated instant with an offset",
        )
        return IntakeReport(tuple(refusals))

    confirmed: list[ConfirmedEvidence] = []
    for reference in _requested_references(case, refusals):
        record = _read_evidence(reference, evidence_repository, refusals)
        if record is None:
            continue
        item = _confirm_evidence(reference, record, run_instant, refusals)
        if item is not None:
            confirmed.append(item)
    candidate = _declared_candidate(candidate_runner, refusals)
    if refusals or candidate is None:
        return IntakeReport(tuple(refusals))

    receipts = _receipts(case, tuple(confirmed))
    receipt_digests = tuple(record_digest(receipt) for receipt in receipts)
    intake = AcceptedIntake(
        case=Identity(case.case_id, case.version, case_digest(case)),
        candidate=candidate,
        context=case.context,
        receipts=receipts,
        receipt_digests=receipt_digests,
        confirmed_evidence=tuple(confirmed),
        candidate_facts=frozen_case_facts(case),
        intake_digest=canonical_digest("\n".join((case_digest(case), *receipt_digests)).encode("ascii")),
    )
    return IntakeReport((), intake)


def intake_case(
    case: VerificationCase,
    *,
    evidence_repository: EvidenceRepositoryPort,
    candidate_runner: CandidateRunnerPort,
) -> AcceptedIntake:
    """Fail closed and return an accepted intake only when every check passes."""
    return inspect_intake(
        case,
        evidence_repository=evidence_repository,
        candidate_runner=candidate_runner,
    ).require_accepted()


__all__ = [
    "AcceptedIntake",
    "ConfirmedEvidence",
    "INTAKE_AUTHORITY_ID",
    "INTAKE_RECEIPT_VERSION",
    "INTAKE_WORKFLOW_FORM",
    "IntakeRefusal",
    "IntakeRefusalReason",
    "IntakeRefused",
    "IntakeReport",
    "RECEIPT_SUBJECT_BY_ROLE",
    "confirm_intake_case",
    "declared_evidence",
    "frozen_case_facts",
    "inspect_intake",
    "intake_case",
]
