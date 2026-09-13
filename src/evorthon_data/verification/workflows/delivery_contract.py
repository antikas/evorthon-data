"""Execution of a whole delivery contract over one approved case.

Reconciliation answers one question: did the candidate reproduce the approved
output. A delivery contract asks more. It declares interface and schema
conformance, business and data invariants, operational observations and
delivery-integrity evidence, and every one of those clauses has to be answered
before a person can accept a delivery.

This step answers them. It reads an approved case, the intake that confirmed
the case's evidence and the reconciliation outcomes the deterministic core
already produced for the parity clauses, and it returns one outcome for every
declared clause.

There is one evaluator per clause family, and each owns its own family.

* Parity is served by the outcomes passed in. The comparison engine owns every
  parity comparison, so this step adopts the outcome it produced exactly as it
  stands and compares nothing again. A parity clause with no outcome in hand is
  insufficient evidence, never a pass.
* Conformance executes the declared interface or schema requirement over the
  interface facts an observation carries.
* Invariant executes the declared business or data invariant over the facts an
  observation carries.
* Operational evidence executes the declared operational requirement. Its
  evidence usually comes from the environment that ran the candidate, so this
  is the family where an attestation most has to stay an attestation.
* Delivery integrity executes the declared requirement over a delivered
  artefact.

An outcome carries the assurance its evidence actually supports.

* A check executed here carries the declared level. The product executed it and
  declares the result; nobody certified it.
* An environment attestation carries the declared level as well, and it is
  recorded as not executed. It reaches a certificate level only when the case
  itself declares the environment certificate the attestation cites, and then
  it takes the level that declared claim states rather than one invented here.
* An owner statement and a human judgement reach the owner-presented level only
  when the case declares the owner evidence they cite.
* A presentation that cites a declaration the case does not carry is
  insufficient evidence for the level it claims. It is never promoted.

Insufficient evidence is a distinct outcome. A clause with no observation, with
evidence the intake did not confirm, with a fact nobody observed, with a
comparison this step does not execute or with an unsupported assurance claim
cannot be answered, and an answer it cannot give is never reported as a pass
and never as a failure.

Acceptance is decided elsewhere. Failures in the interface and operational
families are reported as blocking findings for the route that reads this
summary, and every other failure is reported as a failure. Nothing is refused
for weak evidence, for a declared provenance or for a claimed assurance level.

Refusals are integrity refusals: an intake that answers for another case, an
outcome or observation for a clause the case does not declare, a record that
answers for a family the case's clause does not have, a reconciliation for an
output the clause does not bind, and a self-contradicting input.

The module reads no file, no clock, no environment and no locale, and it draws
no random value. Two runs over the same case and the same material produce
identical records and an identical summary digest.
"""
# evorthon-implements: EVD-README-027
from __future__ import annotations

# evorthon-component: verification_workflows

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from types import MappingProxyType

from evorthon_data.verification.core.canonical import canonical_digest, case_digest, record_digest
from evorthon_data.verification.core.reconciliation import ClauseReconciliation
from evorthon_data.verification.domain.contracts import (
    AssuranceLevel,
    CLAUSE_TYPE_BY_FAMILY,
    ClauseFamily,
    ClauseOutcome,
    ComparisonDimension,
    ConformanceClause,
    DeliveryIntegrityClause,
    EvidenceReference,
    Identity,
    InvariantClause,
    OperationalEvidenceClause,
    ParityClause,
    RuleConstraint,
    RuleDeclaration,
    RuleOperator,
    VerificationCase,
    VerificationStatus,
)
from evorthon_data.verification.enforcement.validation import (
    validate_verification_case,
    validate_verification_record,
)
from evorthon_data.verification.workflows.intake import AcceptedIntake, confirm_intake_case

DELIVERY_CONTRACT_FORM = "evorthon.verification.delivery-contract.v1"

# The families whose failure a later acceptance route reads as blocking. A
# delivery that does not meet its declared interface, or whose declared
# operational observation did not hold, is not accepted on output parity alone.
BLOCKING_FAMILIES = (ClauseFamily.CONFORMANCE, ClauseFamily.OPERATIONAL_EVIDENCE)

# The comparison dimension each non-parity family reports. A parity clause
# declares its own dimensions, so it takes none from here.
DIMENSION_BY_FAMILY = MappingProxyType(
    {
        ClauseFamily.CONFORMANCE: ComparisonDimension.SCHEMA,
        ClauseFamily.INVARIANT: ComparisonDimension.VALUE,
        ClauseFamily.OPERATIONAL_EVIDENCE: ComparisonDimension.REPLAY_METADATA,
        ClauseFamily.DELIVERY_INTEGRITY: ComparisonDimension.OUTPUT_FORMAT,
    }
)

# The declared comparisons this step executes over observed facts. A declared
# comparison outside this set is reported as one nobody executed here.
EXECUTED_RULE_OPERATORS = frozenset(
    {
        RuleOperator.EQUALS,
        RuleOperator.NOT_EQUALS,
        RuleOperator.PRESENT,
        RuleOperator.ABSENT,
        RuleOperator.AT_LEAST,
        RuleOperator.AT_MOST,
    }
)


class EvidenceBasis(str, Enum):
    """What one clause outcome rests on."""

    EXECUTED_CHECK = "executed-check"
    ENVIRONMENT_ATTESTATION = "environment-attestation"
    OWNER_STATEMENT = "owner-statement"
    HUMAN_JUDGEMENT = "human-judgement"


# A result presented for a clause carries one of these. The basis of an
# executed check is not among them, so a presentation cannot claim it.
PRESENTED_BASES = (
    EvidenceBasis.ENVIRONMENT_ATTESTATION,
    EvidenceBasis.OWNER_STATEMENT,
    EvidenceBasis.HUMAN_JUDGEMENT,
)
# An owner statement and a human judgement both rest on evidence an owner
# presented. An attestation rests on a certificate the environment issued. The
# two declarations are read separately and never from each other.
OWNER_BASES = (EvidenceBasis.OWNER_STATEMENT, EvidenceBasis.HUMAN_JUDGEMENT)


class ContractFindingKind(str, Enum):
    """The closed vocabulary of reasons a clause did not simply pass."""

    REQUIREMENT_NOT_MET = "requirement-not-met"
    PRESENTED_FAILURE = "presented-failure"
    PRESENTED_INSUFFICIENT = "presented-insufficient"
    OBSERVATION_MISSING = "observation-missing"
    EVIDENCE_NOT_CONFIRMED = "evidence-not-confirmed"
    FACT_NOT_OBSERVED = "fact-not-observed"
    COMPARISON_NOT_EXECUTED = "comparison-not-executed"
    ASSURANCE_NOT_SUPPORTED = "assurance-not-supported"
    PARITY_OUTCOME_MISSING = "parity-outcome-missing"


class ContractRefusalReason(str, Enum):
    """The closed set of integrity reasons for refusing to execute a contract."""

    INTAKE_CASE_MISMATCH = "intake-case-mismatch"
    UNDECLARED_CLAUSE = "undeclared-clause"
    UNDECLARED_CLAUSE_FAMILY = "undeclared-clause-family"
    UNBOUND_OUTPUT = "unbound-output"
    CONTRADICTORY_INPUT = "contradictory-input"


class ContractRefused(ValueError):
    """Raised when a delivery contract cannot be executed with declared meaning."""

    def __init__(self, reason: ContractRefusalReason, subject: str, detail: str) -> None:
        super().__init__(f"{reason.value} at {subject}: {detail}")
        self.reason = reason
        self.subject = subject
        self.detail = detail


@dataclass(frozen=True)
class ExecutedObservation:
    """The declared facts one clause requirement is executed over.

    ``observed_values`` maps a declared field to the text observed for it. A
    field the observation does not carry, and a field it carries with no value,
    both read as absent.
    """

    clause_id: str
    observed_values: Mapping[str, str | None]


@dataclass(frozen=True)
class PresentedObservation:
    """A result presented for one clause rather than executed over facts.

    ``assurance_reference`` names the declaration the presentation rests on: an
    owner-presented evidence record for an owner statement or a human
    judgement, and an environment certificate claim for an attestation. An
    attestation that cites nothing keeps the declared level.
    """

    clause_id: str
    basis: EvidenceBasis
    presented_status: VerificationStatus
    assurance_reference: str | None = None


ClauseObservation = ExecutedObservation | PresentedObservation


@dataclass(frozen=True)
class ClauseFinding:
    """One reason a clause did not pass, and the subject it concerns."""

    kind: ContractFindingKind
    family: ClauseFamily
    clause_id: str
    locator: str
    detail: str


@dataclass(frozen=True)
class ClauseExecution:
    """One clause outcome, the assurance it carries and what it rests on.

    ``basis`` is absent when nothing was executed and nothing presented for the
    clause. ``executed`` is true only when this step ran the declared
    requirement over observed facts, or when the comparison engine ran the
    parity comparison this outcome came from.
    """

    clause_id: str
    family: ClauseFamily
    outcome: ClauseOutcome
    assurance: AssuranceLevel
    basis: EvidenceBasis | None
    executed: bool
    findings: tuple[ClauseFinding, ...]

    @property
    def blocking(self) -> bool:
        """Report whether this failure blocks acceptance for a later route."""
        return self.family in BLOCKING_FAMILIES and self.outcome.status is VerificationStatus.FAIL


@dataclass(frozen=True)
class DeliveryContractOutcome:
    """Every declared clause of one case, answered, with the summary they imply."""

    case: Identity
    executions: tuple[ClauseExecution, ...]
    summary_digest: str

    @property
    def outcomes(self) -> tuple[ClauseOutcome, ...]:
        return tuple(execution.outcome for execution in self.executions)

    @property
    def findings(self) -> tuple[ClauseFinding, ...]:
        return tuple(finding for execution in self.executions for finding in execution.findings)

    @property
    def status(self) -> VerificationStatus:
        """Report the status the clause outcomes imply, without deciding acceptance."""
        statuses = {execution.outcome.status for execution in self.executions}
        if VerificationStatus.FAIL in statuses:
            return VerificationStatus.FAIL
        if VerificationStatus.INSUFFICIENT_EVIDENCE in statuses:
            return VerificationStatus.INSUFFICIENT_EVIDENCE
        return VerificationStatus.PASS

    @property
    def failed(self) -> tuple[str, ...]:
        """Name every clause that failed, in declared order."""
        return tuple(
            execution.clause_id
            for execution in self.executions
            if execution.outcome.status is VerificationStatus.FAIL
        )

    @property
    def unresolved(self) -> tuple[str, ...]:
        """Name every clause the evidence in hand could not answer."""
        return tuple(
            execution.clause_id
            for execution in self.executions
            if execution.outcome.status is VerificationStatus.INSUFFICIENT_EVIDENCE
        )

    @property
    def blocking(self) -> tuple[ClauseFinding, ...]:
        """Report the findings a later acceptance route reads as blocking."""
        return tuple(
            finding for execution in self.executions if execution.blocking for finding in execution.findings
        )


@dataclass(frozen=True)
class _Inputs:
    """Everything one clause evaluator may read."""

    case: VerificationCase
    confirmed: frozenset[tuple[str, str, str]]
    reconciled: Mapping[str, ClauseReconciliation]
    observed: Mapping[str, ClauseObservation]


@dataclass(frozen=True)
class _ConstraintResult:
    """One declared constraint: it holds, it does not, or it could not be read."""

    held: bool | None
    kind: ContractFindingKind
    detail: str


def _refuse(reason: ContractRefusalReason, subject: str, detail: str) -> ContractRefused:
    return ContractRefused(reason, subject, detail)


def _family_of(clause: object) -> ClauseFamily | None:
    """Return the family one declared clause belongs to, if it belongs to one."""
    return next(
        (family for family, clause_type in CLAUSE_TYPE_BY_FAMILY.items() if isinstance(clause, clause_type)),
        None,
    )


def _confirm_intake(intake: AcceptedIntake, case: VerificationCase) -> None:
    """Refuse an intake that answers for another case, through the rule that owns it."""
    confirm_intake_case(
        intake,
        case,
        lambda subject, detail: _refuse(ContractRefusalReason.INTAKE_CASE_MISMATCH, subject, detail),
    )


def _confirmed_evidence(intake: AcceptedIntake) -> frozenset[tuple[str, str, str]]:
    """Return the identity of every evidence record the intake confirmed."""
    return frozenset(
        (item.reference.evidence_id, item.reference.version, item.observed_digest)
        for item in intake.confirmed_evidence
    )


def _clause_identity(clause: object) -> Identity:
    return Identity(clause.clause_id, clause.version, record_digest(clause))


def _indexed_reconciliation(
    reconciliation: Sequence[ClauseReconciliation], clauses: Mapping[str, object]
) -> dict[str, ClauseReconciliation]:
    """Index the reconciled parity outcomes, refusing any that the case contradicts."""
    indexed: dict[str, ClauseReconciliation] = {}
    for item in reconciliation:
        if not isinstance(item, ClauseReconciliation):
            raise _refuse(
                ContractRefusalReason.CONTRADICTORY_INPUT,
                "reconciliation",
                "a reconciled parity clause is required",
            )
        subject = f"reconciliation[{item.clause_id}]"
        clause = clauses.get(item.clause_id)
        if clause is None:
            raise _refuse(
                ContractRefusalReason.UNDECLARED_CLAUSE,
                subject,
                "the case declares no clause for the reconciled outcome",
            )
        if not isinstance(clause, ParityClause) or item.outcome.family is not ClauseFamily.PARITY:
            raise _refuse(
                ContractRefusalReason.UNDECLARED_CLAUSE_FAMILY,
                subject,
                "the reconciled outcome answers for a family the case does not declare for this clause",
            )
        if _clause_identity(clause) != item.outcome.clause:
            raise _refuse(
                ContractRefusalReason.UNDECLARED_CLAUSE,
                subject,
                "the reconciled outcome answers for a clause identity the case does not declare",
            )
        if item.output_id != clause.expected_output_id:
            raise _refuse(
                ContractRefusalReason.UNBOUND_OUTPUT,
                subject,
                "the reconciled outcome answers for an output the clause does not bind",
            )
        if item.clause_id in indexed:
            raise _refuse(
                ContractRefusalReason.CONTRADICTORY_INPUT,
                subject,
                "more than one reconciled outcome answers for the clause",
            )
        indexed[item.clause_id] = item
    return indexed


def _indexed_observations(
    observations: Sequence[ClauseObservation], clauses: Mapping[str, object]
) -> dict[str, ClauseObservation]:
    """Index the observations, refusing any that the case or its own basis contradicts."""
    indexed: dict[str, ClauseObservation] = {}
    for item in observations:
        if not isinstance(item, (ExecutedObservation, PresentedObservation)):
            raise _refuse(
                ContractRefusalReason.CONTRADICTORY_INPUT,
                "observations",
                "an executed or a presented observation is required",
            )
        subject = f"observations[{item.clause_id}]"
        clause = clauses.get(item.clause_id)
        if clause is None:
            raise _refuse(
                ContractRefusalReason.UNDECLARED_CLAUSE,
                subject,
                "the case declares no clause for the observation",
            )
        if isinstance(clause, ParityClause):
            raise _refuse(
                ContractRefusalReason.UNDECLARED_CLAUSE_FAMILY,
                subject,
                "the case declares this clause in the parity family, which is reconciled and never observed here",
            )
        if item.clause_id in indexed:
            raise _refuse(
                ContractRefusalReason.CONTRADICTORY_INPUT,
                subject,
                "more than one observation answers for the clause",
            )
        _confirm_observation(item, subject)
        indexed[item.clause_id] = item
    return indexed


def _confirm_observation(observation: ClauseObservation, subject: str) -> None:
    """Refuse an observation that contradicts what it declares itself to be."""
    if isinstance(observation, PresentedObservation):
        if observation.basis not in PRESENTED_BASES:
            raise _refuse(
                ContractRefusalReason.CONTRADICTORY_INPUT,
                subject,
                "a presented result cannot declare the basis of an executed check",
            )
        if not isinstance(observation.presented_status, VerificationStatus):
            raise _refuse(
                ContractRefusalReason.CONTRADICTORY_INPUT,
                subject,
                "a presented result must declare a supported status",
            )
        return
    values = observation.observed_values
    if not isinstance(values, Mapping) or any(
        not isinstance(field_id, str) or not (value is None or isinstance(value, str))
        for field_id, value in values.items()
    ):
        raise _refuse(
            ContractRefusalReason.CONTRADICTORY_INPUT,
            subject,
            "observed facts must be declared text held against declared fields",
        )


def _unconfirmed(clause: object, confirmed: frozenset[tuple[str, str, str]]) -> tuple[EvidenceReference, ...]:
    """Return the evidence a clause requires that the intake did not confirm."""
    return tuple(
        reference
        for reference in clause.required_evidence
        if (reference.evidence_id, reference.version, reference.digest) not in confirmed
    )


def _assurance(
    basis: EvidenceBasis, citation: str | None, case: VerificationCase
) -> tuple[AssuranceLevel, bool]:
    """Return the level the evidence supports, and whether the case declares it.

    A check executed here carries the declared level. A presentation rises
    above that level only through a declaration the case itself carries, and a
    citation the case does not carry supports no level at all.
    """
    if basis is EvidenceBasis.EXECUTED_CHECK:
        return AssuranceLevel.DECLARED, True
    assurance = case.assurance
    if basis in OWNER_BASES:
        presented = next(
            (item for item in assurance.owner_presented_evidence if item.evidence_id == citation),
            None,
        )
        if presented is None:
            return AssuranceLevel.DECLARED, False
        return AssuranceLevel.OWNER_PRESENTED, True
    if citation is None:
        return AssuranceLevel.DECLARED, True
    claim = next(
        (item for item in assurance.environment_certificate_claims if item.claim_id == citation),
        None,
    )
    if claim is None:
        return AssuranceLevel.DECLARED, False
    return claim.assurance_level, True


def _number(text: str) -> Decimal | None:
    """Return the finite number the declared text names, if it names one."""
    try:
        parsed = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _execute_constraint(constraint: RuleConstraint, values: Mapping[str, str | None]) -> _ConstraintResult:
    """Execute one declared constraint over the observed facts.

    The answer is that the constraint holds, that it does not hold, or that it
    could not be read at all. A constraint nobody could read is never reported
    as either of the other two.
    """
    operator = constraint.operator
    observed = values.get(constraint.field_id)
    present = observed is not None
    if operator not in EXECUTED_RULE_OPERATORS:
        return _ConstraintResult(None, ContractFindingKind.COMPARISON_NOT_EXECUTED, "the declared comparison is not one this step executes")
    if operator is RuleOperator.PRESENT:
        return _ConstraintResult(present, ContractFindingKind.REQUIREMENT_NOT_MET, "the declared fact is absent")
    if operator is RuleOperator.ABSENT:
        return _ConstraintResult(not present, ContractFindingKind.REQUIREMENT_NOT_MET, "the declared fact is present")
    if constraint.expected_value is None:
        return _ConstraintResult(None, ContractFindingKind.COMPARISON_NOT_EXECUTED, "the declared comparison carries no expected value")
    if not present:
        return _ConstraintResult(None, ContractFindingKind.FACT_NOT_OBSERVED, "the declared fact was not observed")
    if operator is RuleOperator.EQUALS:
        return _ConstraintResult(
            observed == constraint.expected_value,
            ContractFindingKind.REQUIREMENT_NOT_MET,
            "the observed fact differs from the declared expectation",
        )
    if operator is RuleOperator.NOT_EQUALS:
        return _ConstraintResult(
            observed != constraint.expected_value,
            ContractFindingKind.REQUIREMENT_NOT_MET,
            "the observed fact is the value the requirement excludes",
        )
    measured = _number(observed)
    limit = _number(constraint.expected_value)
    if measured is None or limit is None:
        return _ConstraintResult(None, ContractFindingKind.COMPARISON_NOT_EXECUTED, "the declared limit or the observed fact is not a finite number")
    if operator is RuleOperator.AT_LEAST:
        return _ConstraintResult(measured >= limit, ContractFindingKind.REQUIREMENT_NOT_MET, "the observed number is below the declared limit")
    return _ConstraintResult(measured <= limit, ContractFindingKind.REQUIREMENT_NOT_MET, "the observed number is above the declared limit")


def _observed_reference(clause_id: str, observation: ClauseObservation) -> EvidenceReference:
    """Return the reference that stands for what was observed for one clause."""
    if isinstance(observation, ExecutedObservation):
        payload = json.dumps(
            {"observed-facts": dict(observation.observed_values)},
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        )
        summary = "the declared facts one executed check read"
    else:
        payload = json.dumps(
            {
                "assurance-reference": observation.assurance_reference,
                "basis": observation.basis.value,
                "presented-status": observation.presented_status.value,
            },
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        )
        summary = "one presented clause result"
    return EvidenceReference(
        evidence_id=f"{clause_id}/observed",
        version=DELIVERY_CONTRACT_FORM,
        digest=canonical_digest(payload.encode("ascii")),
        summary=summary,
    )


def _finding(
    kind: ContractFindingKind, family: ClauseFamily, clause_id: str, locator: str, detail: str
) -> ClauseFinding:
    return ClauseFinding(kind=kind, family=family, clause_id=clause_id, locator=locator, detail=detail)


def _execution(
    clause: object,
    family: ClauseFamily,
    inputs: _Inputs,
    *,
    status: VerificationStatus,
    assurance: AssuranceLevel,
    basis: EvidenceBasis | None,
    executed: bool,
    findings: tuple[ClauseFinding, ...],
    observed: EvidenceReference | None,
    dimensions: tuple[ComparisonDimension, ...] | None = None,
) -> ClauseExecution:
    """Compose one clause outcome and validate it through the one fail-closed validator."""
    outcome = ClauseOutcome(
        outcome_id=f"{inputs.case.case_id}/{clause.clause_id}",
        version=DELIVERY_CONTRACT_FORM,
        clause=_clause_identity(clause),
        family=family,
        status=status,
        compared_dimensions=(DIMENSION_BY_FAMILY[family],) if dimensions is None else dimensions,
        expected_evidence=clause.required_evidence,
        observed_evidence=() if observed is None else (observed,),
    )
    validate_verification_record(outcome)
    return ClauseExecution(
        clause_id=clause.clause_id,
        family=family,
        outcome=outcome,
        assurance=assurance,
        basis=basis,
        executed=executed,
        findings=findings,
    )


def _answer_clause(
    clause: object,
    family: ClauseFamily,
    subject: Identity,
    requirement: RuleDeclaration,
    inputs: _Inputs,
) -> ClauseExecution:
    """Answer one clause whose requirement is declared rather than compared.

    The order is fixed. A clause with no observation cannot be answered. A
    clause whose required evidence the intake did not confirm cannot be
    answered. A presentation whose claimed level the case does not declare
    cannot be answered at that level. Only then is the declared requirement
    executed, or the presented result recorded as what it is.
    """
    observation = inputs.observed.get(clause.clause_id)
    if observation is None:
        return _execution(
            clause,
            family,
            inputs,
            status=VerificationStatus.INSUFFICIENT_EVIDENCE,
            assurance=AssuranceLevel.DECLARED,
            basis=None,
            executed=False,
            findings=(
                _finding(
                    ContractFindingKind.OBSERVATION_MISSING,
                    family,
                    clause.clause_id,
                    subject.identifier,
                    "nothing was observed or presented for the clause",
                ),
            ),
            observed=None,
        )
    executed_check = isinstance(observation, ExecutedObservation)
    basis = EvidenceBasis.EXECUTED_CHECK if executed_check else observation.basis
    citation = None if executed_check else observation.assurance_reference
    assurance, supported = _assurance(basis, citation, inputs.case)
    observed = _observed_reference(clause.clause_id, observation)
    unconfirmed = _unconfirmed(clause, inputs.confirmed)
    if unconfirmed:
        return _execution(
            clause,
            family,
            inputs,
            status=VerificationStatus.INSUFFICIENT_EVIDENCE,
            assurance=assurance,
            basis=basis,
            executed=False,
            findings=tuple(
                _finding(
                    ContractFindingKind.EVIDENCE_NOT_CONFIRMED,
                    family,
                    clause.clause_id,
                    reference.evidence_id,
                    "the intake confirmed no record for the evidence the clause requires",
                )
                for reference in unconfirmed
            ),
            observed=observed,
        )
    if not supported:
        return _execution(
            clause,
            family,
            inputs,
            status=VerificationStatus.INSUFFICIENT_EVIDENCE,
            assurance=assurance,
            basis=basis,
            executed=False,
            findings=(
                _finding(
                    ContractFindingKind.ASSURANCE_NOT_SUPPORTED,
                    family,
                    clause.clause_id,
                    subject.identifier,
                    "the case declares no assurance record for the level this presentation cites",
                ),
            ),
            observed=observed,
        )
    if not executed_check:
        return _presented_clause(clause, family, subject, observation, assurance, inputs, observed)
    return _executed_clause(clause, family, requirement, observation, assurance, inputs, observed)


def _presented_clause(
    clause: object,
    family: ClauseFamily,
    subject: Identity,
    observation: PresentedObservation,
    assurance: AssuranceLevel,
    inputs: _Inputs,
    observed: EvidenceReference,
) -> ClauseExecution:
    """Record a presented result as the status it presents, at the level it supports."""
    status = observation.presented_status
    findings: tuple[ClauseFinding, ...] = ()
    if status is VerificationStatus.FAIL:
        findings = (
            _finding(
                ContractFindingKind.PRESENTED_FAILURE,
                family,
                clause.clause_id,
                subject.identifier,
                "the presented result reports the clause as failed",
            ),
        )
    elif status is VerificationStatus.INSUFFICIENT_EVIDENCE:
        findings = (
            _finding(
                ContractFindingKind.PRESENTED_INSUFFICIENT,
                family,
                clause.clause_id,
                subject.identifier,
                "the presented result reports evidence that does not answer the clause",
            ),
        )
    return _execution(
        clause,
        family,
        inputs,
        status=status,
        assurance=assurance,
        basis=observation.basis,
        executed=False,
        findings=findings,
        observed=observed,
    )


def _executed_clause(
    clause: object,
    family: ClauseFamily,
    requirement: RuleDeclaration,
    observation: ExecutedObservation,
    assurance: AssuranceLevel,
    inputs: _Inputs,
    observed: EvidenceReference,
) -> ClauseExecution:
    """Execute the declared requirement over the observed facts.

    A constraint proven not to hold fails the clause even where another
    constraint could not be read. A clause with no proven violation and a
    constraint nobody could read is insufficient evidence, never a pass.
    """
    findings: list[ClauseFinding] = []
    unresolved = False
    failed = False
    for constraint in requirement.constraints:
        result = _execute_constraint(constraint, observation.observed_values)
        if result.held is True:
            continue
        findings.append(
            _finding(result.kind, family, clause.clause_id, constraint.field_id, result.detail)
        )
        if result.held is None:
            unresolved = True
        else:
            failed = True
    if failed:
        status = VerificationStatus.FAIL
    elif unresolved:
        status = VerificationStatus.INSUFFICIENT_EVIDENCE
    else:
        status = VerificationStatus.PASS
    return _execution(
        clause,
        family,
        inputs,
        status=status,
        assurance=assurance,
        basis=EvidenceBasis.EXECUTED_CHECK,
        executed=True,
        findings=tuple(findings),
        observed=observed,
    )


def evaluate_parity(clause: ParityClause, inputs: _Inputs) -> ClauseExecution:
    """Adopt the reconciled outcome for one parity clause.

    The comparison engine owns every parity comparison. Its outcome is taken
    exactly as it stands, so no comparison is repeated and no second answer for
    a parity clause can exist. A clause with no reconciled outcome in hand is
    insufficient evidence.
    """
    reconciled = inputs.reconciled.get(clause.clause_id)
    if reconciled is None:
        return _execution(
            clause,
            ClauseFamily.PARITY,
            inputs,
            status=VerificationStatus.INSUFFICIENT_EVIDENCE,
            assurance=AssuranceLevel.DECLARED,
            basis=None,
            executed=False,
            findings=(
                _finding(
                    ContractFindingKind.PARITY_OUTCOME_MISSING,
                    ClauseFamily.PARITY,
                    clause.clause_id,
                    clause.expected_output_id,
                    "no reconciled outcome was supplied for the clause",
                ),
            ),
            observed=None,
            dimensions=clause.comparison.dimensions,
        )
    validate_verification_record(reconciled.outcome)
    return ClauseExecution(
        clause_id=clause.clause_id,
        family=ClauseFamily.PARITY,
        outcome=reconciled.outcome,
        assurance=AssuranceLevel.DECLARED,
        basis=EvidenceBasis.EXECUTED_CHECK,
        executed=True,
        findings=(),
    )


def evaluate_conformance(clause: ConformanceClause, inputs: _Inputs) -> ClauseExecution:
    """Answer one declared interface or schema conformance clause.

    The declared requirement is executed over the interface facts an
    observation carries. A failure here is a blocking finding, because a
    delivery that does not meet its declared interface is not accepted on
    output parity alone.
    """
    return _answer_clause(clause, ClauseFamily.CONFORMANCE, clause.contract, clause.requirement, inputs)


def evaluate_invariant(clause: InvariantClause, inputs: _Inputs) -> ClauseExecution:
    """Answer one declared business or data invariant clause.

    The declared requirement is executed over the facts an observation carries.
    An invariant that does not hold is a failure a person reads; this step
    reports it and gates nothing on it.
    """
    return _answer_clause(clause, ClauseFamily.INVARIANT, clause.invariant, clause.requirement, inputs)


def evaluate_operational_evidence(clause: OperationalEvidenceClause, inputs: _Inputs) -> ClauseExecution:
    """Answer one declared operational-evidence clause.

    The evidence for an operational signal usually comes from the environment
    that ran the candidate. An attestation is recorded as an attestation, never
    as a check executed here and never as a certificate the case does not
    declare. A failure here is a blocking finding.
    """
    return _answer_clause(
        clause, ClauseFamily.OPERATIONAL_EVIDENCE, clause.operational_signal, clause.requirement, inputs
    )


def evaluate_delivery_integrity(clause: DeliveryIntegrityClause, inputs: _Inputs) -> ClauseExecution:
    """Answer one declared delivery-integrity clause.

    The declared requirement is executed over the facts an observation carries
    about the delivered artefact. Integrity of the stored evidence itself is
    confirmed at intake, and a clause whose required evidence intake did not
    confirm is insufficient evidence here.
    """
    return _answer_clause(
        clause, ClauseFamily.DELIVERY_INTEGRITY, clause.delivery_artifact, clause.requirement, inputs
    )


EVALUATOR_BY_FAMILY = MappingProxyType(
    {
        ClauseFamily.PARITY: evaluate_parity,
        ClauseFamily.CONFORMANCE: evaluate_conformance,
        ClauseFamily.INVARIANT: evaluate_invariant,
        ClauseFamily.OPERATIONAL_EVIDENCE: evaluate_operational_evidence,
        ClauseFamily.DELIVERY_INTEGRITY: evaluate_delivery_integrity,
    }
)

if frozenset(EVALUATOR_BY_FAMILY) != frozenset(ClauseFamily):
    raise RuntimeError("every declared clause family requires one evaluator")
if frozenset(DIMENSION_BY_FAMILY) | {ClauseFamily.PARITY} != frozenset(ClauseFamily):
    raise RuntimeError("every clause family answered here requires one reported dimension")


def _summary_digest(executions: tuple[ClauseExecution, ...]) -> str:
    """Return the digest of what this summary says, in declared clause order."""
    parts = tuple(
        "|".join(
            (
                execution.clause_id,
                execution.family.value,
                execution.outcome.status.value,
                execution.assurance.value,
                "none" if execution.basis is None else execution.basis.value,
                "executed" if execution.executed else "not-executed",
            )
        )
        for execution in executions
    )
    return canonical_digest("\n".join(parts).encode("ascii"))


def execute_delivery_contract(
    case: VerificationCase,
    intake: AcceptedIntake,
    *,
    reconciliation: Sequence[ClauseReconciliation] = (),
    observations: Sequence[ClauseObservation] = (),
) -> DeliveryContractOutcome:
    """Answer every declared clause of one delivery contract.

    ``reconciliation`` carries the outcomes the comparison engine already
    produced for the parity clauses; they are adopted and never recomputed.
    ``observations`` carry the facts executed over, or the results presented
    for, the clauses of the other families.
    """
    validate_verification_case(case)
    _confirm_intake(intake, case)
    clauses = {clause.clause_id: clause for clause in case.comparison_policy.clauses}
    inputs = _Inputs(
        case=case,
        confirmed=_confirmed_evidence(intake),
        reconciled=_indexed_reconciliation(reconciliation, clauses),
        observed=_indexed_observations(observations, clauses),
    )
    executions: list[ClauseExecution] = []
    for clause in case.comparison_policy.clauses:
        family = _family_of(clause)
        if family is None:
            raise _refuse(
                ContractRefusalReason.UNDECLARED_CLAUSE_FAMILY,
                f"comparison_policy.clauses[{getattr(clause, 'clause_id', '')}]",
                "the clause belongs to no declared family",
            )
        executions.append(EVALUATOR_BY_FAMILY[family](clause, inputs))
    answered = tuple(executions)
    return DeliveryContractOutcome(
        case=Identity(case.case_id, case.version, case_digest(case)),
        executions=answered,
        summary_digest=_summary_digest(answered),
    )


__all__ = [
    "BLOCKING_FAMILIES",
    "ClauseExecution",
    "ClauseFinding",
    "ClauseObservation",
    "ContractFindingKind",
    "ContractRefusalReason",
    "ContractRefused",
    "DELIVERY_CONTRACT_FORM",
    "DIMENSION_BY_FAMILY",
    "DeliveryContractOutcome",
    "EVALUATOR_BY_FAMILY",
    "EXECUTED_RULE_OPERATORS",
    "EvidenceBasis",
    "ExecutedObservation",
    "OWNER_BASES",
    "PRESENTED_BASES",
    "PresentedObservation",
    "evaluate_conformance",
    "evaluate_delivery_integrity",
    "evaluate_invariant",
    "evaluate_operational_evidence",
    "evaluate_parity",
    "execute_delivery_contract",
]
