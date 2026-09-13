"""Human-controlled remediation: one named person's disposition of one piece of advice.

Advice is inert text. Nothing in this product turns advice into work, and
nothing here reads what the advice says. This workflow records what a named
human decided about it, and that decision is the only thing a tracker, a rerun
or an acceptance route may act on. There is no route here from advice to work
or to a decision on its own: recording takes a disposition by a named human as
well, and a call without one is a missing argument rather than a default.

Four dispositions are recorded, and each leaves something different behind.

* Accept approves the remedy as advised. The decision names exactly one work
  identity, derived from the advice identity and the case, so recording the
  same decision again names the same work and a tracker sees one item.
* Edit records the human's own remedy as a new version of the advice. The
  discriminating tests and the evidence are carried over, the edit is stated in
  the assumptions, and the decision points at that version. The advice the
  adviser recorded is never changed; a new record is built beside it.
* Reject approves no work at all and leaves the fault as it was.
* An evidence request approves no work either. It states what is asked for, the
  rationale the decision carries names each thing asked for, and the fault
  stays as it was.

No disposition closes a fault. A rejection and an evidence request leave the
fault with no approved correction at all, and an approved correction is
answered by a rerun rather than by this record.

Who may decide. The decision is recorded only when the person deciding is the
authority the advice requires, named in full, and is a human. An actor of
another kind and an identity the advice does not require are both refused
before anything is built, because a decision recorded for the wrong person is a
record that contradicts itself. That is the one kind of refusal here: nothing
is refused for weak evidence, for a declared provenance or for a claimed
assurance class.

The assurance class of a decision. The class is a label read off what the
person presented beside the decision, and nothing about it is inferred.

* Environment certification is stated by an environment certificate claim
  issued for the deciding identity that declares that level. Nothing else
  states it.
* Owner presentation is stated by an owner-presented evidence record presented
  by the deciding identity. Nothing else states it.
* A named authority on its own states the declared class.

The class recorded is the highest class the presented material states. A
certificate that declares a level below environment certification therefore
states none of the two higher classes, and it is neither promoted nor thrown
away: every record presented is carried on the outcome exactly as it was
presented, so a reader sees the material and the class beside each other. A
record naming an identity other than the deciding one is refused as
inconsistent. The domain's decision record is unchanged by any of this; the
class lives on the workflow outcome.

The rerun. A corrected candidate is rerun over the same case, through the same
delivery-contract execution as any other run, against the clause outcomes of
the run that found the fault. The case in hand, the case the decision cites and
the case the prior outcome answered are one case or the rerun is refused. Every
clause that failed before must now pass and every clause that passed before
must still pass; a clause that fails again, a clause that has newly failed and
a clause the rerun could not answer are each reported with their clause
identities. The rerun decides nothing about acceptance. It reports, and a named
person reads the report.

The module reads no file, no clock and no environment, and it draws no random
value. Two recordings of the same decision produce identical records.
"""
# evorthon-implements: EVD-README-024
# evorthon-implements: EVD-README-022
from __future__ import annotations

# evorthon-component: verification_workflows

from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import Enum

from evorthon_data.verification.core.canonical import (
    DIGEST_PREFIX,
    canonical_digest,
    case_digest,
    record_digest,
)
from evorthon_data.verification.core.reconciliation import ClauseReconciliation
from evorthon_data.verification.domain.contracts import (
    AssuranceLevel,
    EnvironmentCertificateClaim,
    EvidenceReference,
    Identity,
    OwnerPresentedEvidence,
    RemediationAdvice,
    RemediationDecision,
    RemediationDisposition,
    VerificationCase,
    VerificationStatus,
)
from evorthon_data.verification.workflows.delivery_contract import (
    ClauseObservation,
    DeliveryContractOutcome,
    execute_delivery_contract,
)
from evorthon_data.verification.workflows.intake import AcceptedIntake

REMEDIATION_WORKFLOW_FORM = "evorthon.verification.remediation.v1"
REMEDIATION_RERUN_FORM = "evorthon.verification.remediation.rerun.v1"
REMEDIATION_DECISION_VERSION = "evorthon.verification.remediation.decision.v1"
REMEDIATION_WORK_VERSION = "evorthon.verification.remediation.work.v1"

# The remainders the derived identities carry after the record they came from.
DECISION_REMAINDER = "decision"
WORK_REMAINDER = "remedy"
# The marker an edited advice version carries, so a reader can tell the version
# a human wrote from the version an adviser wrote.
EDITED_ADVICE_MARKER = "edited"

# The dispositions a human may take on advice. The adviser's own proposed state
# is not among them: advice is proposed by being written, and a person disposes
# of it.
HUMAN_DISPOSITIONS = (
    RemediationDisposition.ACCEPTED,
    RemediationDisposition.MODIFIED,
    RemediationDisposition.REJECTED,
    RemediationDisposition.REQUEST_MORE_EVIDENCE,
)
# The two dispositions that approve work, and so the two a rerun may run for.
APPROVING_DISPOSITIONS = (RemediationDisposition.ACCEPTED, RemediationDisposition.MODIFIED)


class RemediationActorKind(str, Enum):
    """The kinds of actor a disposition can name; only one of them may decide.

    The engagement aggregate declares the same three kinds for its own records.
    The architecture record allows no edge from these workflows to the
    engagement component, so the vocabulary is declared here rather than
    imported. A shared owner for it belongs with the verification domain, which
    both components already reach.
    """

    HUMAN = "human"
    MODEL = "model"
    SERVICE = "service"


class RemediationRefusalReason(str, Enum):
    """The closed set of integrity reasons this workflow refuses to record or rerun.

    Every one of them says a record cannot be read as one: the wrong kind of
    actor, an identity the advice does not require, a record naming somebody
    else, material one disposition does not own, or a rerun over another case.
    None of them reads what the advice says or how strong its evidence is.
    """

    UNDECLARED_ADVICE = "undeclared-advice"
    UNDECLARED_DISPOSITION = "undeclared-disposition"
    UNDECLARED_OUTCOME = "undeclared-outcome"
    NON_HUMAN_ACTOR = "non-human-actor"
    UNNAMED_AUTHORITY = "unnamed-authority"
    INCOMPLETE_DISPOSITION = "incomplete-disposition"
    INCONSISTENT_ASSURANCE = "inconsistent-assurance"
    UNAPPROVED_REMEDY = "unapproved-remedy"
    CASE_MISMATCH = "case-mismatch"
    NO_PRIOR_DEFECT = "no-prior-defect"


class RemediationRefused(ValueError):
    """Raised before a remediation record would be built with a meaning it cannot carry."""

    def __init__(self, reason: RemediationRefusalReason, subject: str, detail: str) -> None:
        super().__init__(f"{reason.value} at {subject}: {detail}")
        self.reason = reason
        self.subject = subject
        self.detail = detail


@dataclass(frozen=True)
class DecidingActor:
    """The actor a disposition is taken by, and the kind that actor is."""

    identity: Identity
    kind: RemediationActorKind


@dataclass(frozen=True)
class HumanDisposition:
    """One named human's disposition of one piece of advice.

    ``edited_fixes`` and ``edit_statement`` belong to an edit and to nothing
    else. ``requested_evidence`` belongs to an evidence request and to nothing
    else. ``owner_presented`` and ``environment_certificate`` are the material
    the person presented beside the decision, and the assurance class is read
    off them.
    """

    disposition: RemediationDisposition
    decided_by: DecidingActor
    rationale: EvidenceReference
    edited_fixes: tuple[str, ...] = ()
    edit_statement: str | None = None
    requested_evidence: tuple[str, ...] = ()
    owner_presented: OwnerPresentedEvidence | None = None
    environment_certificate: EnvironmentCertificateClaim | None = None


@dataclass(frozen=True)
class RemediationOutcome:
    """One recorded disposition: the decision, its assurance class and what it points at.

    ``advice`` is the version the decision points at: the recorded advice for
    every disposition but an edit, and the human's edited version for an edit.
    ``fault`` and ``discriminating_tests`` are named here as well as inside
    that record, so a reader outside these workflows can name what the decision
    is about without opening the advice at all.
    """

    case: Identity
    fault: Identity
    decision: RemediationDecision
    assurance: AssuranceLevel
    advice: RemediationAdvice
    discriminating_tests: tuple[Identity, ...]
    requested_evidence: tuple[str, ...] = ()
    presented_owner_evidence: OwnerPresentedEvidence | None = None
    presented_certificate: EnvironmentCertificateClaim | None = None
    form: str = REMEDIATION_WORKFLOW_FORM

    @property
    def approved_work(self) -> Identity | None:
        """The one work identity this decision approved, or nothing."""
        return self.decision.approved_work

    @property
    def fault_open(self) -> bool:
        """Whether the fault is left with no approved correction at all.

        A rejection and an evidence request leave it so. An approved correction
        is answered by a rerun, and no disposition closes a fault here.
        """
        return self.decision.approved_work is None


@dataclass(frozen=True)
class RemediationRerun:
    """What one rerun of a corrected candidate found, compared clause by clause.

    ``regression_set`` names the clauses the prior outcome answered as a pass
    or a failure, in the order the case declares them. A clause the prior run
    could not answer is not in it, because there is nothing to hold the rerun
    to. Nothing here accepts anything.
    """

    case: Identity
    work: Identity
    contract: DeliveryContractOutcome
    regression_set: tuple[str, ...]
    corrected: tuple[str, ...]
    restored_defects: tuple[str, ...]
    regressions: tuple[str, ...]
    unanswered: tuple[str, ...]
    form: str = REMEDIATION_RERUN_FORM

    @property
    def green(self) -> bool:
        """Whether every prior failure now passes and every prior pass still does."""
        return not (self.restored_defects or self.regressions or self.unanswered)


def _refuse(reason: RemediationRefusalReason, subject: str, detail: str) -> RemediationRefused:
    return RemediationRefused(reason, subject, detail)


def _named_identity(value: object, subject: str, reason: RemediationRefusalReason) -> Identity:
    """Return one identity that names all three of its parts."""
    if not isinstance(value, Identity) or not all(
        isinstance(part, str) and part.strip()
        for part in (value.identifier, value.version, value.digest)
    ):
        raise _refuse(reason, subject, "an identity names an identifier, a version and a digest")
    return value


def _declared_text(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _refuse(
            RemediationRefusalReason.INCOMPLETE_DISPOSITION,
            subject,
            "a disposition declares no empty text",
        )
    return value


def _declared_texts(value: object, subject: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise _refuse(
            RemediationRefusalReason.INCOMPLETE_DISPOSITION,
            subject,
            "a disposition records a list of declarations in a tuple",
        )
    return tuple(_declared_text(item, f"{subject}[{index}]") for index, item in enumerate(value))


def _confirm_advice(advice: object) -> RemediationAdvice:
    """Confirm the advice is a recorded advice record that names its authority."""
    if not isinstance(advice, RemediationAdvice):
        raise _refuse(
            RemediationRefusalReason.UNDECLARED_ADVICE,
            "advice",
            "a disposition is taken on one recorded advice record",
        )
    _named_identity(
        advice.required_authority, "advice.required_authority", RemediationRefusalReason.UNDECLARED_ADVICE
    )
    _named_identity(advice.fault, "advice.fault", RemediationRefusalReason.UNDECLARED_ADVICE)
    return advice


def _confirm_actor(disposition: HumanDisposition, advice: RemediationAdvice) -> Identity:
    """Confirm the person deciding is the authority the advice requires, and is human."""
    actor = disposition.decided_by
    if not isinstance(actor, DecidingActor):
        raise _refuse(
            RemediationRefusalReason.UNDECLARED_DISPOSITION,
            "disposition.decided_by",
            "a disposition names the actor that took it",
        )
    if actor.kind is not RemediationActorKind.HUMAN:
        raise _refuse(
            RemediationRefusalReason.NON_HUMAN_ACTOR,
            "disposition.decided_by.kind",
            "only a named human disposes of advice",
        )
    identity = _named_identity(
        actor.identity, "disposition.decided_by.identity", RemediationRefusalReason.UNNAMED_AUTHORITY
    )
    if identity != advice.required_authority:
        raise _refuse(
            RemediationRefusalReason.UNNAMED_AUTHORITY,
            "disposition.decided_by.identity",
            "the decision is recorded only for the authority the advice requires",
        )
    return identity


def _confirm_disposition(disposition: object) -> HumanDisposition:
    """Confirm the disposition is one a human may take, declared in the shape it takes."""
    if not isinstance(disposition, HumanDisposition):
        raise _refuse(
            RemediationRefusalReason.UNDECLARED_DISPOSITION,
            "disposition",
            "advice becomes a decision only through a declared human disposition",
        )
    if disposition.disposition not in HUMAN_DISPOSITIONS:
        raise _refuse(
            RemediationRefusalReason.UNDECLARED_DISPOSITION,
            "disposition.disposition",
            "a human accepts, edits, rejects or asks for more evidence",
        )
    rationale = disposition.rationale
    if not isinstance(rationale, EvidenceReference) or not all(
        isinstance(part, str) and part.strip()
        for part in (rationale.evidence_id, rationale.version, rationale.digest, rationale.summary)
    ):
        raise _refuse(
            RemediationRefusalReason.INCOMPLETE_DISPOSITION,
            "disposition.rationale",
            "a decision carries the rationale the person recorded",
        )
    return disposition


def _confirm_material(disposition: HumanDisposition) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
    """Confirm each disposition carries its own material and no other's.

    An edit carries the remedy the person wrote and a statement of what was
    changed. An evidence request carries what is asked for. Any other
    disposition carries neither, so material that belongs to a disposition
    nobody took is refused rather than ignored.
    """
    taken = disposition.disposition
    edited = _declared_texts(disposition.edited_fixes, "disposition.edited_fixes")
    requested = _declared_texts(disposition.requested_evidence, "disposition.requested_evidence")
    statement = disposition.edit_statement
    if taken is RemediationDisposition.MODIFIED:
        if not edited:
            raise _refuse(
                RemediationRefusalReason.INCOMPLETE_DISPOSITION,
                "disposition.edited_fixes",
                "an edit records the remedy the person wrote",
            )
        statement = _declared_text(statement, "disposition.edit_statement")
    else:
        if edited or statement is not None:
            raise _refuse(
                RemediationRefusalReason.INCOMPLETE_DISPOSITION,
                "disposition.edited_fixes",
                "only an edit records a remedy of its own",
            )
        statement = ""
    if taken is RemediationDisposition.REQUEST_MORE_EVIDENCE:
        if not requested:
            raise _refuse(
                RemediationRefusalReason.INCOMPLETE_DISPOSITION,
                "disposition.requested_evidence",
                "an evidence request states what is asked for",
            )
        for index, asked in enumerate(requested):
            if asked not in disposition.rationale.summary:
                raise _refuse(
                    RemediationRefusalReason.INCOMPLETE_DISPOSITION,
                    f"disposition.requested_evidence[{index}]",
                    "the rationale the decision carries names each thing asked for",
                )
    elif requested:
        raise _refuse(
            RemediationRefusalReason.INCOMPLETE_DISPOSITION,
            "disposition.requested_evidence",
            "only an evidence request states what is asked for",
        )
    return edited, statement, requested


def _confirm_assurance(disposition: HumanDisposition, identity: Identity) -> AssuranceLevel:
    """Return the class the presented material states for the deciding identity.

    Each class has one thing that states it and nothing else is read. A record
    presented for somebody else is refused, because a decision cannot rest on
    material about another person. A certificate that declares a level below
    environment certification states none of the higher classes; it is carried
    on the outcome as presented and is neither promoted nor discarded.
    """
    owner = disposition.owner_presented
    claim = disposition.environment_certificate
    if owner is not None:
        if not isinstance(owner, OwnerPresentedEvidence):
            raise _refuse(
                RemediationRefusalReason.INCONSISTENT_ASSURANCE,
                "disposition.owner_presented",
                "owner-presented material is declared as an owner-presented evidence record",
            )
        if owner.presented_by != identity:
            raise _refuse(
                RemediationRefusalReason.INCONSISTENT_ASSURANCE,
                "disposition.owner_presented.presented_by",
                "the evidence presented names a different identity from the one deciding",
            )
    if claim is not None:
        if not isinstance(claim, EnvironmentCertificateClaim):
            raise _refuse(
                RemediationRefusalReason.INCONSISTENT_ASSURANCE,
                "disposition.environment_certificate",
                "a certificate is declared as an environment certificate claim",
            )
        if claim.issued_by != identity:
            raise _refuse(
                RemediationRefusalReason.INCONSISTENT_ASSURANCE,
                "disposition.environment_certificate.issued_by",
                "the certificate names a different identity from the one deciding",
            )
        if claim.assurance_level is AssuranceLevel.ENVIRONMENT_CERTIFIED:
            return AssuranceLevel.ENVIRONMENT_CERTIFIED
    if owner is not None:
        return AssuranceLevel.OWNER_PRESENTED
    return AssuranceLevel.DECLARED


def _advice_identity(advice: RemediationAdvice) -> Identity:
    """Return the identity of one advice record as it stands."""
    return Identity(
        identifier=advice.advice_id, version=advice.version, digest=record_digest(advice)
    )


def _edited_advice(advice: RemediationAdvice, fixes: tuple[str, ...], statement: str) -> RemediationAdvice:
    """Return the human's remedy as a new version of the advice.

    Everything the adviser recorded but the remedy is carried over, the edit is
    stated in the assumptions, and the version says the record was edited and
    which edit it holds. The record passed in is frozen and is not touched.
    """
    identity = _advice_identity(advice)
    payload = "\n".join(
        (
            REMEDIATION_WORK_VERSION,
            identity.identifier,
            identity.version,
            identity.digest,
            statement,
            *fixes,
        )
    )
    edit = canonical_digest(payload.encode("utf-8"))
    return replace(
        advice,
        version=f"{advice.version}/{EDITED_ADVICE_MARKER}/{edit}",
        proposed_fixes=fixes,
        assumptions=(*advice.assumptions, statement),
    )


def _work_identity(advice: Identity, case: Identity) -> Identity:
    """Return the one work identity an approved remedy names.

    The identity is derived from the advice identity and the case identity and
    from nothing else, so recording the same decision again names the same
    work, and a tracker that projects it twice holds one item. The identifier
    carries the derivation's fingerprint in plain form, without the label and
    the separator the canonical digest beside it carries, so one tracker title
    and one logical reference segment can each carry the whole identifier.
    """
    payload = "\n".join(
        (
            REMEDIATION_WORK_VERSION,
            advice.identifier,
            advice.version,
            advice.digest,
            case.identifier,
            case.version,
            case.digest,
        )
    )
    digest = canonical_digest(payload.encode("utf-8"))
    return Identity(
        identifier=f"{WORK_REMAINDER}-{digest.removeprefix(f'{DIGEST_PREFIX}:')}",
        version=REMEDIATION_WORK_VERSION,
        digest=digest,
    )


def record_remediation_decision(
    advice: object,
    disposition: object,
    *,
    case: object,
) -> RemediationOutcome:
    """Record one named human's disposition of one piece of advice.

    Nothing is recorded for anybody but the authority the advice requires, and
    nothing is recorded for an actor that is not a human. An accepted or edited
    remedy names one work identity; a rejection and an evidence request name
    none and leave the fault as it was.
    """
    confirmed = _confirm_advice(advice)
    taken = _confirm_disposition(disposition)
    identity = _confirm_actor(taken, confirmed)
    case_identity = _named_identity(case, "case", RemediationRefusalReason.INCOMPLETE_DISPOSITION)
    fixes, statement, requested = _confirm_material(taken)
    assurance = _confirm_assurance(taken, identity)
    recorded = (
        _edited_advice(confirmed, fixes, statement)
        if taken.disposition is RemediationDisposition.MODIFIED
        else confirmed
    )
    advice_identity = _advice_identity(recorded)
    approved = (
        _work_identity(advice_identity, case_identity)
        if taken.disposition in APPROVING_DISPOSITIONS
        else None
    )
    decision = RemediationDecision(
        remediation_id=f"{advice_identity.identifier}/{DECISION_REMAINDER}",
        version=REMEDIATION_DECISION_VERSION,
        advice=advice_identity,
        disposition=taken.disposition,
        decided_by=identity,
        rationale=taken.rationale,
        approved_work=approved,
    )
    return RemediationOutcome(
        case=case_identity,
        fault=recorded.fault,
        decision=decision,
        assurance=assurance,
        advice=recorded,
        discriminating_tests=recorded.discriminating_tests,
        requested_evidence=requested,
        presented_owner_evidence=taken.owner_presented,
        presented_certificate=taken.environment_certificate,
    )


def _approved_work(outcome: object) -> tuple[RemediationOutcome, Identity]:
    """Return the outcome and the work it approved, refusing one that approved none."""
    if not isinstance(outcome, RemediationOutcome):
        raise _refuse(
            RemediationRefusalReason.UNDECLARED_OUTCOME,
            "outcome",
            "a rerun runs for one recorded remediation outcome",
        )
    work = outcome.decision.approved_work
    if outcome.decision.disposition not in APPROVING_DISPOSITIONS or work is None:
        raise _refuse(
            RemediationRefusalReason.UNAPPROVED_REMEDY,
            "outcome.decision",
            "a rerun runs for an approved or edited remedy and for no other disposition",
        )
    return outcome, work


def _confirm_case(outcome: RemediationOutcome, case: object, prior: object) -> Identity:
    """Confirm the case in hand is the case the decision cites and the prior run answered."""
    if not isinstance(case, VerificationCase):
        raise _refuse(
            RemediationRefusalReason.CASE_MISMATCH,
            "case",
            "a rerun runs over the verification case the decision cites",
        )
    if not isinstance(prior, DeliveryContractOutcome):
        raise _refuse(
            RemediationRefusalReason.CASE_MISMATCH,
            "prior",
            "a rerun compares against the clause outcomes of the run that found the fault",
        )
    identity = Identity(identifier=case.case_id, version=case.version, digest=case_digest(case))
    if identity != outcome.case:
        raise _refuse(
            RemediationRefusalReason.CASE_MISMATCH,
            "case",
            "the case identity, version and digest are not the ones the decision cites",
        )
    if prior.case != identity:
        raise _refuse(
            RemediationRefusalReason.CASE_MISMATCH,
            "prior.case",
            "the prior outcome answered a different case",
        )
    return identity


def _status_by_clause(outcome: DeliveryContractOutcome) -> dict[str, VerificationStatus]:
    """Return the status of each answered clause, in the order the case declares them."""
    return {execution.clause_id: execution.outcome.status for execution in outcome.executions}


def rerun_corrected_case(
    outcome: object,
    case: object,
    intake: AcceptedIntake,
    *,
    prior: object,
    reconciliation: Sequence[ClauseReconciliation] = (),
    observations: Sequence[ClauseObservation] = (),
) -> RemediationRerun:
    """Rerun one corrected candidate over the same case and report what changed.

    The regression set is the clause outcomes of the run that found the fault.
    Every clause that failed then must pass now, and every clause that passed
    then must pass now. A clause that fails again, a clause that has newly
    failed and a clause this run could not answer are each named in the report.
    Nothing here accepts a delivery or closes a fault.
    """
    confirmed, work = _approved_work(outcome)
    identity = _confirm_case(confirmed, case, prior)
    before = _status_by_clause(prior)
    if VerificationStatus.FAIL not in before.values():
        raise _refuse(
            RemediationRefusalReason.NO_PRIOR_DEFECT,
            "prior",
            "the prior outcome records no failing clause for a remedy to correct",
        )
    contract = execute_delivery_contract(
        case,
        intake,
        reconciliation=reconciliation,
        observations=observations,
    )
    after = _status_by_clause(contract)
    compared: list[str] = []
    corrected: list[str] = []
    restored: list[str] = []
    regressions: list[str] = []
    unanswered: list[str] = []
    for clause_id, was in before.items():
        if was not in (VerificationStatus.PASS, VerificationStatus.FAIL):
            continue
        compared.append(clause_id)
        now = after.get(clause_id)
        if now is VerificationStatus.PASS:
            if was is VerificationStatus.FAIL:
                corrected.append(clause_id)
        elif now is VerificationStatus.FAIL:
            if was is VerificationStatus.FAIL:
                restored.append(clause_id)
            else:
                regressions.append(clause_id)
        else:
            unanswered.append(clause_id)
    return RemediationRerun(
        case=identity,
        work=work,
        contract=contract,
        regression_set=tuple(compared),
        corrected=tuple(corrected),
        restored_defects=tuple(restored),
        regressions=tuple(regressions),
        unanswered=tuple(unanswered),
    )


__all__ = [
    "APPROVING_DISPOSITIONS",
    "DECISION_REMAINDER",
    "DecidingActor",
    "EDITED_ADVICE_MARKER",
    "HUMAN_DISPOSITIONS",
    "HumanDisposition",
    "REMEDIATION_DECISION_VERSION",
    "REMEDIATION_RERUN_FORM",
    "REMEDIATION_WORKFLOW_FORM",
    "REMEDIATION_WORK_VERSION",
    "RemediationActorKind",
    "RemediationOutcome",
    "RemediationRefusalReason",
    "RemediationRefused",
    "RemediationRerun",
    "WORK_REMAINDER",
    "record_remediation_decision",
    "rerun_corrected_case",
]
