"""Reconciliation of an accepted intake against a candidate run.

This step sits between intake and any later diagnosis. It runs the candidate
through the environment contract, reconciles every parity clause through the
deterministic core, and composes one verification result.

The step does five things.

1. It refuses a case whose comparison policy moved after its facts were
   observed. The rule belongs to the enforcement component and is used here as
   it stands; this module adds no second rule and relaxes nothing.
2. It confirms that the accepted intake answers for the case being reconciled,
   so a result can never be composed from receipts taken for another case.
3. It asks the candidate runner for the outputs it produced from the frozen
   facts, and requires every compared output to carry the identity, digests and
   row count the runner declared for it.
4. It reconciles every parity clause through the deterministic core, which owns
   every comparison rule and every finding.
5. It composes the verification result from the intake, the observed outputs
   and the clause outcomes, validates it through the one fail-closed validator,
   and takes its digest from the deterministic core.

Refusals are integrity refusals: a policy changed after observation, an intake
that answers for another case, a candidate output that contradicts the runner's
own declaration, material that does not match the identity its record declares,
and any refusal the deterministic core raises. Nothing is refused for the
provenance a case declares or for the assurance it claims, so a case whose
evidence is synthetic or derived takes exactly the same path as any other.

The module reads no file, no clock, no environment and no locale, and it draws
no random value.
"""
# evorthon-implements: EVD-README-009
# evorthon-implements: EVD-README-003
from __future__ import annotations

# evorthon-component: verification_workflows

from dataclasses import dataclass

from evorthon_data.verification.core.canonical import canonical_digest, result_digest
from evorthon_data.verification.core.reconciliation import (
    CandidateObservation,
    ClauseReconciliation,
    ExpectedMaterial,
    Finding,
    ReconciliationRefusalReason,
    ReconciliationRefused,
    parity_clauses,
    reconcile_case,
)
from evorthon_data.verification.domain.contracts import (
    EvidenceProvenance,
    RepeatRunIdentity,
    VerificationCase,
    VerificationResult,
)
from evorthon_data.verification.enforcement.validation import (
    PolicyObservation,
    ensure_policy_unchanged,
    validate_verification_record,
)
from evorthon_data.verification.ports.contracts import CandidateRunnerPort, PortRefusal, ProducedOutput
from evorthon_data.verification.workflows.intake import AcceptedIntake, confirm_intake_case

RECONCILIATION_RESULT_VERSION = "evorthon.verification.reconciliation.result.v1"
REPEAT_RUN_VERSION = "evorthon.verification.reconciliation.repeat-run.v1"


@dataclass(frozen=True)
class ReconciliationOutcome:
    """One reconciled candidate run: its result, its digest and its findings.

    ``evidence_provenance`` is the label the case derives from its own declared
    parts. It travels with the result so a reader can see what the comparison
    rested on. It never changes a comparison, an outcome or a status.
    """

    result: VerificationResult
    result_digest: str
    clauses: tuple[ClauseReconciliation, ...]
    findings: tuple[Finding, ...]
    produced: tuple[ProducedOutput, ...]
    evidence_provenance: EvidenceProvenance


def _refuse(reason: ReconciliationRefusalReason, subject: str, detail: str) -> ReconciliationRefused:
    return ReconciliationRefused(reason, subject, detail)


def _confirm_intake(intake: AcceptedIntake, case: VerificationCase) -> None:
    """Refuse an intake that answers for another case, through the rule that owns it."""
    confirm_intake_case(
        intake,
        case,
        lambda subject, detail: _refuse(ReconciliationRefusalReason.INTAKE_CASE_MISMATCH, subject, detail),
    )


def _produced_outputs(runner: CandidateRunnerPort, intake: AcceptedIntake) -> tuple[ProducedOutput, ...]:
    try:
        produced = runner.produce_outputs(intake.candidate_facts)
    except PortRefusal as refusal:
        raise _refuse(
            ReconciliationRefusalReason.CANDIDATE_OUTPUT_MISMATCH,
            "candidate",
            f"the runner refused to produce outputs from the frozen facts: {refusal}",
        ) from None
    if not isinstance(produced, tuple) or any(not isinstance(item, ProducedOutput) for item in produced):
        raise _refuse(
            ReconciliationRefusalReason.CANDIDATE_OUTPUT_MISMATCH,
            "candidate",
            "the runner answered with something other than declared produced outputs",
        )
    return produced


def _confirm_observation(produced: ProducedOutput | None, observation: CandidateObservation, subject: str) -> None:
    if produced is None:
        raise _refuse(
            ReconciliationRefusalReason.CANDIDATE_OUTPUT_MISMATCH,
            subject,
            "the runner declared no produced output for the output this clause compares",
        )
    output = observation.output
    declared = (produced.version, produced.content_digest, produced.format_digest, produced.row_count)
    observed = (output.version, output.content_digest, output.format_digest, output.row_count)
    if declared != observed:
        raise _refuse(
            ReconciliationRefusalReason.CANDIDATE_OUTPUT_MISMATCH,
            subject,
            "the compared output contradicts the version, digests or row count the runner declared",
        )


def _repeat_run_identity(intake: AcceptedIntake) -> RepeatRunIdentity:
    """Bind equivalent runs: the same case, candidate and context repeat here."""
    parts = (
        intake.case.digest,
        intake.candidate.candidate_id,
        intake.candidate.version,
        intake.candidate.artifact_digest,
        intake.context.digest,
    )
    return RepeatRunIdentity(
        repeat_run_id=f"{intake.case.identifier}/{intake.candidate.candidate_id}",
        version=REPEAT_RUN_VERSION,
        digest=canonical_digest("\n".join(parts).encode("ascii")),
    )


def reconcile_run(
    case: VerificationCase,
    intake: AcceptedIntake,
    *,
    policy_observation: PolicyObservation,
    expected_material: dict[str, ExpectedMaterial],
    observations: dict[str, CandidateObservation],
    candidate_runner: CandidateRunnerPort,
) -> ReconciliationOutcome:
    """Reconcile one candidate run and return its verification result.

    ``policy_observation`` is the snapshot taken when the case's facts were
    observed. A comparison policy that moved since then is refused here through
    the enforcement rule that owns it.
    """
    ensure_policy_unchanged(case, policy_observation)
    _confirm_intake(intake, case)
    produced = _produced_outputs(candidate_runner, intake)
    declared_by_id = {item.output_id: item for item in produced}
    for clause in parity_clauses(case):
        observation = observations.get(clause.expected_output_id)
        if observation is None:
            raise _refuse(
                ReconciliationRefusalReason.UNRESOLVED_ACTUAL_OUTPUT,
                f"comparison_policy.clauses[{clause.clause_id}]",
                "no candidate observation was supplied for the output the clause names",
            )
        validate_verification_record(observation.output)
        _confirm_observation(
            declared_by_id.get(clause.expected_output_id),
            observation,
            f"actual_outputs[{clause.expected_output_id}]",
        )
    report = reconcile_case(case, expected_material=expected_material, observations=observations)
    # One output can carry more than one clause, and a result declares each
    # observed output once.
    compared = tuple(
        {clause.output_id: observations[clause.output_id].output for clause in report.clauses}.values()
    )
    result = VerificationResult(
        result_id=f"{case.case_id}/{intake.candidate.candidate_id}",
        version=RECONCILIATION_RESULT_VERSION,
        case=intake.case,
        candidate=intake.candidate,
        context=intake.context,
        independent_receipts=intake.receipts,
        actual_outputs=compared,
        clause_outcomes=report.outcomes,
        status=report.status,
        evidence=tuple(item.reference for item in intake.confirmed_evidence),
        diagnostic_strength=case.diagnostic_strength,
        repeat_run_identity=_repeat_run_identity(intake),
    )
    validate_verification_record(result)
    return ReconciliationOutcome(
        result=result,
        result_digest=result_digest(result),
        clauses=report.clauses,
        findings=report.findings,
        produced=produced,
        evidence_provenance=case.evidence_provenance,
    )


__all__ = [
    "RECONCILIATION_RESULT_VERSION",
    "REPEAT_RUN_VERSION",
    "ReconciliationOutcome",
    "reconcile_run",
]
