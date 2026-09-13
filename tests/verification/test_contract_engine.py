"""Whole-delivery-contract execution: every clause family, its assurance and its refusals."""
# evorthon-verifies: EVD-README-027
# evorthon-verifies: EVD-README-026
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import test_intake_workflow as intake_fixture
import test_reconciliation as parity_fixture
from evorthon_data.verification.core.reconciliation import (
    RECONCILIATION_FORM,
    ClauseReconciliation,
    ExpectedMaterial,
)
from evorthon_data.verification.domain.contracts import (
    AssuranceDeclaration,
    AssuranceLevel,
    ClauseFamily,
    ComparisonDimension,
    ConformanceClause,
    DeliveryIntegrityClause,
    EnvironmentCertificateClaim,
    EvidenceReference,
    Identity,
    InvariantClause,
    OperationalEvidenceClause,
    OwnerPresentedEvidence,
    RuleConstraint,
    RuleDeclaration,
    RuleOperator,
    VerificationStatus,
)
from evorthon_data.verification.enforcement.validation import (
    inspect_verification_case,
    inspect_verification_record,
    observe_policy,
)
from evorthon_data.verification.ports.contracts import ProducedOutput
from evorthon_data.verification.workflows import (
    BLOCKING_FAMILIES,
    DELIVERY_CONTRACT_FORM,
    DIMENSION_BY_FAMILY,
    EVALUATOR_BY_FAMILY,
    ContractFindingKind,
    ContractRefusalReason,
    ContractRefused,
    EvidenceBasis,
    ExecutedObservation,
    PresentedObservation,
    execute_delivery_contract,
    intake_case,
    reconcile_run,
)
from evorthon_data.verification.workflows import delivery_contract as engine

OUTPUT_ID = parity_fixture.OUTPUT_ID
PARITY_CLAUSE_ID = parity_fixture.CLAUSE_ID
OWNER_EVIDENCE_ID = "owner-evidence"
CERTIFICATE_CLAIM_ID = "certificate-claim"

FAMILY_BY_CLAUSE = {
    "conformance": ClauseFamily.CONFORMANCE,
    "invariant": ClauseFamily.INVARIANT,
    "operational": ClauseFamily.OPERATIONAL_EVIDENCE,
    "integrity": ClauseFamily.DELIVERY_INTEGRITY,
}
CONTRACT_CLAUSE_IDS = tuple(FAMILY_BY_CLAUSE)

REQUIREMENTS = {
    "conformance": RuleDeclaration(
        "interface-rule",
        "v1",
        (
            RuleConstraint("interface-version", RuleOperator.EQUALS, "v1"),
            RuleConstraint("published-field-count", RuleOperator.AT_LEAST, "5"),
        ),
    ),
    "invariant": RuleDeclaration(
        "balance-rule",
        "v1",
        (
            RuleConstraint("balance-difference", RuleOperator.AT_MOST, "0"),
            RuleConstraint("orphan-key", RuleOperator.ABSENT, None),
        ),
    ),
    "operational": RuleDeclaration(
        "run-rule",
        "v1",
        (RuleConstraint("run-state", RuleOperator.EQUALS, "complete"),),
    ),
    "integrity": RuleDeclaration(
        "integrity-rule",
        "v1",
        (RuleConstraint("artefact-digest", RuleOperator.PRESENT, None),),
    ),
}
PASSING_FACTS = {
    "conformance": {"interface-version": "v1", "published-field-count": "5"},
    "invariant": {"balance-difference": "0"},
    "operational": {"run-state": "complete"},
    "integrity": {"artefact-digest": "sha256:delivered-artefact"},
}
FAILING_FACTS = {
    "conformance": {"interface-version": "v2", "published-field-count": "5"},
    "invariant": {"balance-difference": "1"},
    "operational": {"run-state": "incomplete"},
    "integrity": {},
}


def identity(name: str) -> Identity:
    return Identity(identifier=name, version="v1", digest=f"sha256:{name}")


def evidence(name: str) -> EvidenceReference:
    return EvidenceReference(name, "v1", f"sha256:{name}", f"approved {name}")


ASSURANCE = AssuranceDeclaration(
    assurance_id="assurance",
    version="v1",
    declared_level=AssuranceLevel.ENVIRONMENT_CERTIFIED,
    owner_presented_evidence=(
        OwnerPresentedEvidence(
            OWNER_EVIDENCE_ID, "v1", "sha256:owner-evidence", identity("data-owner"), evidence("owner-approval")
        ),
    ),
    environment_certificate_claims=(
        EnvironmentCertificateClaim(
            CERTIFICATE_CLAIM_ID,
            "v1",
            "sha256:certificate",
            identity("environment-assurer"),
            AssuranceLevel.ENVIRONMENT_CERTIFIED,
        ),
    ),
)


def contract_clauses(requirements=None):
    """Return one clause per non-parity family, with the requirements in hand."""
    declared = REQUIREMENTS if requirements is None else requirements
    return (
        ConformanceClause(
            "conformance", "v1", identity("interface-contract"), declared["conformance"], (evidence("conformance-evidence"),)
        ),
        InvariantClause(
            "invariant", "v1", identity("balance-invariant"), declared["invariant"], (evidence("invariant-evidence"),)
        ),
        OperationalEvidenceClause(
            "operational", "v1", identity("run-complete"), declared["operational"], (evidence("operational-evidence"),)
        ),
        DeliveryIntegrityClause(
            "integrity", "v1", identity("delivery-artifact"), declared["integrity"], (evidence("integrity-evidence"),)
        ),
    )


def with_requirement(clause_id: str, requirement: RuleDeclaration):
    """Return the contract clauses with one clause's requirement replaced."""
    declared = dict(REQUIREMENTS)
    declared[clause_id] = requirement
    return contract_clauses(declared)


def produced_from(output) -> ProducedOutput:
    return ProducedOutput(
        output_id=output.output_id,
        version=output.version,
        content_digest=output.content_digest,
        format_digest=output.format_digest,
        row_count=output.row_count,
    )


def contract_case(case, clauses=None):
    """Return the reconciliation case extended into a whole delivery contract."""
    policy = case.comparison_policy
    extended = replace(
        case,
        comparison_policy=replace(
            policy, clauses=policy.clauses + (contract_clauses() if clauses is None else clauses)
        ),
        assurance=ASSURANCE,
    )
    return intake_fixture.with_stored_evidence_digests(extended)


class Prepared:
    """One accepted intake, one reconciled parity clause and the contract around them."""

    def __init__(self, scenario=None, *, clauses=None):
        scenario = parity_fixture.scenario() if scenario is None else scenario
        self.case = contract_case(scenario.case, clauses)
        self.expected = ExpectedMaterial(self.case.expected_outputs[0], scenario.expected.rows)
        self.observation = scenario.observation
        self.runner = intake_fixture.FakeCandidateRunner(outputs=(produced_from(self.observation.output),))
        self.intake = intake_case(
            self.case,
            evidence_repository=intake_fixture.FakeEvidenceRepository(intake_fixture.answers_for(self.case)),
            candidate_runner=self.runner,
        )
        self.reconciliation = reconcile_run(
            self.case,
            self.intake,
            policy_observation=observe_policy(self.case),
            expected_material={OUTPUT_ID: self.expected},
            observations={OUTPUT_ID: self.observation},
            candidate_runner=self.runner,
        ).clauses

    def execute(self, *, observations=None, reconciliation=None, intake=None):
        return execute_delivery_contract(
            self.case,
            self.intake if intake is None else intake,
            reconciliation=self.reconciliation if reconciliation is None else reconciliation,
            observations=passing_observations() if observations is None else observations,
        )


def passing_observations():
    """Return one executed observation per non-parity clause, all of them met."""
    return tuple(ExecutedObservation(clause_id, dict(PASSING_FACTS[clause_id])) for clause_id in CONTRACT_CLAUSE_IDS)


def observations_with(observation):
    """Return the passing observations with one clause answered differently."""
    return tuple(
        observation if item.clause_id == observation.clause_id else item for item in passing_observations()
    )


def observations_without(clause_id: str):
    return tuple(item for item in passing_observations() if item.clause_id != clause_id)


def facts_for(clause_id: str, facts):
    return ExecutedObservation(clause_id, dict(facts[clause_id]))


def execution_for(outcome, clause_id: str):
    found = [execution for execution in outcome.executions if execution.clause_id == clause_id]
    assert len(found) == 1
    return found[0]


def kinds(execution):
    return {finding.kind for finding in execution.findings}


def refusal(prepared, **arguments) -> ContractRefusalReason:
    with pytest.raises(ContractRefused) as raised:
        prepared.execute(**arguments)
    return raised.value.reason


def test_the_prepared_contract_case_is_one_the_central_validator_accepts():
    prepared = Prepared()

    assert inspect_verification_case(prepared.case).valid
    assert {clause.clause_id for clause in prepared.case.comparison_policy.clauses} == {
        PARITY_CLAUSE_ID,
        *CONTRACT_CLAUSE_IDS,
    }


def test_a_complete_delivery_contract_answers_every_declared_clause_and_passes():
    outcome = Prepared().execute()

    assert outcome.status is VerificationStatus.PASS
    assert {execution.family for execution in outcome.executions} == set(ClauseFamily)
    assert outcome.failed == ()
    assert outcome.unresolved == ()
    assert outcome.blocking == ()
    assert all(inspect_verification_record(execution.outcome).valid for execution in outcome.executions)


@pytest.mark.parametrize("clause_id", CONTRACT_CLAUSE_IDS)
def test_every_non_parity_family_has_a_pass_a_failure_and_an_insufficient_evidence_case(clause_id):
    prepared = Prepared()

    passing = execution_for(prepared.execute(), clause_id)
    failing = execution_for(
        prepared.execute(observations=observations_with(facts_for(clause_id, FAILING_FACTS))), clause_id
    )
    unanswered = execution_for(prepared.execute(observations=observations_without(clause_id)), clause_id)

    assert passing.outcome.status is VerificationStatus.PASS
    assert failing.outcome.status is VerificationStatus.FAIL
    assert unanswered.outcome.status is VerificationStatus.INSUFFICIENT_EVIDENCE
    assert passing.family is FAMILY_BY_CLAUSE[clause_id]
    assert kinds(passing) == set()
    assert kinds(failing) == {ContractFindingKind.REQUIREMENT_NOT_MET}
    assert kinds(unanswered) == {ContractFindingKind.OBSERVATION_MISSING}


def test_the_parity_family_has_a_pass_a_failure_and_an_insufficient_evidence_case():
    passing = execution_for(Prepared().execute(), PARITY_CLAUSE_ID)
    failing = execution_for(Prepared(parity_fixture.value_failure()).execute(), PARITY_CLAUSE_ID)
    unanswered = execution_for(Prepared().execute(reconciliation=()), PARITY_CLAUSE_ID)

    assert passing.outcome.status is VerificationStatus.PASS
    assert failing.outcome.status is VerificationStatus.FAIL
    assert unanswered.outcome.status is VerificationStatus.INSUFFICIENT_EVIDENCE
    assert kinds(unanswered) == {ContractFindingKind.PARITY_OUTCOME_MISSING}
    assert unanswered.basis is None


def test_interface_and_operational_failures_are_the_blocking_findings():
    prepared = Prepared()
    observations = (
        facts_for("conformance", FAILING_FACTS),
        facts_for("invariant", PASSING_FACTS),
        facts_for("operational", FAILING_FACTS),
        facts_for("integrity", PASSING_FACTS),
    )

    outcome = prepared.execute(observations=observations)

    assert outcome.status is VerificationStatus.FAIL
    assert outcome.failed == ("conformance", "operational")
    assert {finding.clause_id for finding in outcome.blocking} == {"conformance", "operational"}
    assert all(execution_for(outcome, clause_id).blocking for clause_id in ("conformance", "operational"))
    assert BLOCKING_FAMILIES == (ClauseFamily.CONFORMANCE, ClauseFamily.OPERATIONAL_EVIDENCE)


@pytest.mark.parametrize("clause_id", ["invariant", "integrity"])
def test_a_failure_outside_the_blocking_families_is_reported_without_blocking_acceptance(clause_id):
    outcome = Prepared().execute(observations=observations_with(facts_for(clause_id, FAILING_FACTS)))

    assert outcome.status is VerificationStatus.FAIL
    assert outcome.failed == (clause_id,)
    assert outcome.blocking == ()
    assert execution_for(outcome, clause_id).blocking is False


def test_a_presented_result_cannot_declare_the_basis_of_an_executed_check():
    prepared = Prepared()
    masquerade = PresentedObservation("operational", EvidenceBasis.EXECUTED_CHECK, VerificationStatus.PASS)

    assert refusal(prepared, observations=observations_with(masquerade)) is ContractRefusalReason.CONTRADICTORY_INPUT


def test_an_environment_attestation_is_never_recorded_as_a_check_executed_here():
    attested = PresentedObservation("operational", EvidenceBasis.ENVIRONMENT_ATTESTATION, VerificationStatus.PASS)

    execution = execution_for(Prepared().execute(observations=observations_with(attested)), "operational")

    assert execution.outcome.status is VerificationStatus.PASS
    assert execution.basis is EvidenceBasis.ENVIRONMENT_ATTESTATION
    assert execution.executed is False
    assert execution.assurance is AssuranceLevel.DECLARED


def test_an_attestation_that_cites_an_undeclared_certificate_is_insufficient_evidence():
    attested = PresentedObservation(
        "operational", EvidenceBasis.ENVIRONMENT_ATTESTATION, VerificationStatus.PASS, "absent-claim"
    )

    execution = execution_for(Prepared().execute(observations=observations_with(attested)), "operational")

    assert execution.outcome.status is VerificationStatus.INSUFFICIENT_EVIDENCE
    assert execution.assurance is AssuranceLevel.DECLARED
    assert kinds(execution) == {ContractFindingKind.ASSURANCE_NOT_SUPPORTED}


def test_an_attestation_cannot_reach_a_certificate_level_through_the_owner_declaration():
    attested = PresentedObservation(
        "operational", EvidenceBasis.ENVIRONMENT_ATTESTATION, VerificationStatus.PASS, OWNER_EVIDENCE_ID
    )

    execution = execution_for(Prepared().execute(observations=observations_with(attested)), "operational")

    assert execution.assurance is AssuranceLevel.DECLARED
    assert execution.outcome.status is VerificationStatus.INSUFFICIENT_EVIDENCE


def test_an_attestation_that_cites_the_declared_certificate_takes_the_level_the_case_declares():
    attested = PresentedObservation(
        "operational", EvidenceBasis.ENVIRONMENT_ATTESTATION, VerificationStatus.PASS, CERTIFICATE_CLAIM_ID
    )

    execution = execution_for(Prepared().execute(observations=observations_with(attested)), "operational")

    assert execution.outcome.status is VerificationStatus.PASS
    assert execution.assurance is AssuranceLevel.ENVIRONMENT_CERTIFIED
    assert execution.executed is False


@pytest.mark.parametrize("basis", [EvidenceBasis.OWNER_STATEMENT, EvidenceBasis.HUMAN_JUDGEMENT])
def test_an_owner_statement_and_a_human_judgement_rest_on_declared_owner_evidence(basis):
    supported = PresentedObservation("integrity", basis, VerificationStatus.PASS, OWNER_EVIDENCE_ID)
    uncited = PresentedObservation("integrity", basis, VerificationStatus.PASS)

    presented = execution_for(Prepared().execute(observations=observations_with(supported)), "integrity")
    unsupported = execution_for(Prepared().execute(observations=observations_with(uncited)), "integrity")

    assert presented.outcome.status is VerificationStatus.PASS
    assert presented.assurance is AssuranceLevel.OWNER_PRESENTED
    assert presented.executed is False
    assert unsupported.outcome.status is VerificationStatus.INSUFFICIENT_EVIDENCE
    assert unsupported.assurance is AssuranceLevel.DECLARED


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (VerificationStatus.FAIL, ContractFindingKind.PRESENTED_FAILURE),
        (VerificationStatus.INSUFFICIENT_EVIDENCE, ContractFindingKind.PRESENTED_INSUFFICIENT),
    ],
)
def test_a_presented_result_carries_the_status_it_presents(status, kind):
    attested = PresentedObservation("operational", EvidenceBasis.ENVIRONMENT_ATTESTATION, status)

    execution = execution_for(Prepared().execute(observations=observations_with(attested)), "operational")

    assert execution.outcome.status is status
    assert kinds(execution) == {kind}


def test_the_engine_adopts_a_reconciled_parity_outcome_without_comparing_anything_again():
    prepared = Prepared()

    execution = execution_for(prepared.execute(), PARITY_CLAUSE_ID)

    assert execution.outcome is prepared.reconciliation[0].outcome
    assert execution.outcome.version == RECONCILIATION_FORM
    assert execution.outcome.compared_dimensions == prepared.case.comparison_policy.clauses[0].comparison.dimensions
    assert execution.executed is True


def test_a_reconciled_parity_failure_reaches_the_summary_exactly_as_it_stands():
    prepared = Prepared(parity_fixture.value_failure())

    outcome = prepared.execute()

    assert execution_for(outcome, PARITY_CLAUSE_ID).outcome is prepared.reconciliation[0].outcome
    assert outcome.status is VerificationStatus.FAIL
    assert outcome.failed == (PARITY_CLAUSE_ID,)
    assert outcome.blocking == ()


def test_the_engine_module_calls_no_comparison_entry_point():
    source = Path(engine.__file__).read_text(encoding="ascii")

    for entry_point in ("reconcile_case", "reconcile_clause", "reconcile_run", "dataset_digest"):
        assert entry_point not in source


def test_evidence_the_intake_did_not_confirm_is_insufficient_evidence():
    prepared = Prepared()
    trimmed = replace(
        prepared.intake,
        confirmed_evidence=tuple(
            item for item in prepared.intake.confirmed_evidence if item.reference.evidence_id != "operational-evidence"
        ),
    )

    execution = execution_for(prepared.execute(intake=trimmed), "operational")

    assert execution.outcome.status is VerificationStatus.INSUFFICIENT_EVIDENCE
    assert kinds(execution) == {ContractFindingKind.EVIDENCE_NOT_CONFIRMED}
    assert execution.executed is False


def test_a_fact_the_observation_does_not_carry_is_insufficient_evidence_and_not_a_failure():
    unobserved = ExecutedObservation("conformance", {"published-field-count": "5"})

    execution = execution_for(Prepared().execute(observations=observations_with(unobserved)), "conformance")

    assert execution.outcome.status is VerificationStatus.INSUFFICIENT_EVIDENCE
    assert kinds(execution) == {ContractFindingKind.FACT_NOT_OBSERVED}


def test_a_comparison_the_engine_does_not_execute_is_insufficient_evidence():
    pattern = RuleDeclaration(
        "interface-rule", "v1", (RuleConstraint("interface-version", RuleOperator.MATCHES, "v1"),)
    )
    prepared = Prepared(clauses=with_requirement("conformance", pattern))

    execution = execution_for(prepared.execute(), "conformance")

    assert execution.outcome.status is VerificationStatus.INSUFFICIENT_EVIDENCE
    assert kinds(execution) == {ContractFindingKind.COMPARISON_NOT_EXECUTED}


def test_a_number_the_observation_does_not_declare_as_one_is_insufficient_evidence():
    unreadable = ExecutedObservation("conformance", {"interface-version": "v1", "published-field-count": "many"})

    execution = execution_for(Prepared().execute(observations=observations_with(unreadable)), "conformance")

    assert execution.outcome.status is VerificationStatus.INSUFFICIENT_EVIDENCE
    assert kinds(execution) == {ContractFindingKind.COMPARISON_NOT_EXECUTED}


def test_a_proven_violation_fails_a_clause_even_where_another_constraint_cannot_be_read():
    mixed = ExecutedObservation("conformance", {"interface-version": "v2"})

    execution = execution_for(Prepared().execute(observations=observations_with(mixed)), "conformance")

    assert execution.outcome.status is VerificationStatus.FAIL
    assert kinds(execution) == {
        ContractFindingKind.REQUIREMENT_NOT_MET,
        ContractFindingKind.FACT_NOT_OBSERVED,
    }


def test_an_insufficient_clause_leaves_the_summary_unresolved_rather_than_passing_or_failing():
    outcome = Prepared().execute(observations=observations_without("invariant"))

    assert outcome.status is VerificationStatus.INSUFFICIENT_EVIDENCE
    assert outcome.unresolved == ("invariant",)
    assert outcome.failed == ()


@pytest.mark.parametrize(
    ("clause_id", "family"),
    sorted((clause_id, family.value) for clause_id, family in FAMILY_BY_CLAUSE.items()),
)
def test_each_answered_family_reports_its_declared_dimension_and_the_evidence_it_rests_on(clause_id, family):
    prepared = Prepared()
    execution = execution_for(prepared.execute(), clause_id)
    clause = {item.clause_id: item for item in prepared.case.comparison_policy.clauses}[clause_id]

    assert execution.outcome.compared_dimensions == (DIMENSION_BY_FAMILY[ClauseFamily(family)],)
    assert execution.outcome.version == DELIVERY_CONTRACT_FORM
    assert execution.outcome.expected_evidence == clause.required_evidence
    assert len(execution.outcome.observed_evidence) == 1


def test_every_declared_family_has_one_evaluator_and_one_reported_dimension():
    assert set(EVALUATOR_BY_FAMILY) == set(ClauseFamily)
    assert set(DIMENSION_BY_FAMILY) == set(ClauseFamily) - {ClauseFamily.PARITY}
    assert set(DIMENSION_BY_FAMILY.values()) <= set(ComparisonDimension)


def test_two_runs_over_the_same_material_answer_identically():
    prepared = Prepared()

    first = prepared.execute()
    second = prepared.execute()

    assert first == second
    assert first.summary_digest == second.summary_digest
    assert first.case == Identity(prepared.case.case_id, prepared.case.version, prepared.intake.case.digest)


def test_a_changed_answer_changes_the_summary_digest():
    prepared = Prepared()

    passing = prepared.execute()
    failing = prepared.execute(observations=observations_with(facts_for("invariant", FAILING_FACTS)))

    assert passing.summary_digest != failing.summary_digest


def test_an_intake_that_answers_for_another_case_is_refused():
    prepared = Prepared()
    other = Prepared(parity_fixture.value_failure())

    assert refusal(prepared, intake=other.intake) is ContractRefusalReason.INTAKE_CASE_MISMATCH
    assert refusal(prepared, intake="not an accepted intake") is ContractRefusalReason.INTAKE_CASE_MISMATCH


def test_an_observation_for_a_clause_the_case_does_not_declare_is_refused():
    prepared = Prepared()
    stray = ExecutedObservation("absent-clause", {"run-state": "complete"})

    assert refusal(prepared, observations=(stray,)) is ContractRefusalReason.UNDECLARED_CLAUSE


def test_an_observation_for_a_parity_clause_is_refused_as_a_family_the_case_does_not_declare():
    prepared = Prepared()
    stray = ExecutedObservation(PARITY_CLAUSE_ID, {"run-state": "complete"})

    assert refusal(prepared, observations=(stray,)) is ContractRefusalReason.UNDECLARED_CLAUSE_FAMILY


def test_a_reconciled_outcome_for_a_non_parity_clause_is_refused():
    prepared = Prepared()
    misfiled = replace(prepared.reconciliation[0], clause_id="conformance")

    assert refusal(prepared, reconciliation=(misfiled,)) is ContractRefusalReason.UNDECLARED_CLAUSE_FAMILY


def test_a_reconciled_outcome_for_a_clause_identity_the_case_does_not_declare_is_refused():
    prepared = Prepared()
    reconciled = prepared.reconciliation[0]
    unknown = replace(reconciled, clause_id="absent-clause")
    moved = replace(
        reconciled, outcome=replace(reconciled.outcome, clause=identity("moved-clause"))
    )

    assert refusal(prepared, reconciliation=(unknown,)) is ContractRefusalReason.UNDECLARED_CLAUSE
    assert refusal(prepared, reconciliation=(moved,)) is ContractRefusalReason.UNDECLARED_CLAUSE


def test_a_reconciled_outcome_for_an_output_the_clause_does_not_bind_is_refused():
    prepared = Prepared()
    unbound = replace(prepared.reconciliation[0], output_id="absent-output")

    assert refusal(prepared, reconciliation=(unbound,)) is ContractRefusalReason.UNBOUND_OUTPUT


@pytest.mark.parametrize(
    "observations",
    [
        (ExecutedObservation("operational", {"run-state": "complete"}), ExecutedObservation("operational", {})),
        (ExecutedObservation("operational", {"run-state": 1}),),
        (ExecutedObservation("operational", {1: "complete"}),),
        ("not an observation",),
    ],
)
def test_a_self_contradicting_input_is_refused(observations):
    assert refusal(Prepared(), observations=observations) is ContractRefusalReason.CONTRADICTORY_INPUT


def test_more_than_one_reconciled_outcome_for_one_clause_is_refused():
    prepared = Prepared()
    twice = (prepared.reconciliation[0], prepared.reconciliation[0])

    assert refusal(prepared, reconciliation=twice) is ContractRefusalReason.CONTRADICTORY_INPUT


def test_a_reconciliation_that_is_not_a_reconciled_clause_is_refused():
    assert refusal(Prepared(), reconciliation=("not a reconciliation",)) is ContractRefusalReason.CONTRADICTORY_INPUT


def test_the_reconciled_clause_type_is_the_one_the_comparison_engine_produces():
    prepared = Prepared()

    assert all(isinstance(item, ClauseReconciliation) for item in prepared.reconciliation)
