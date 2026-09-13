"""Reconciliation over the environment contracts, and the post-observation policy rules."""
# evorthon-verifies: EVD-README-023
# evorthon-verifies: EVD-README-019
from __future__ import annotations

from dataclasses import replace

import pytest

import test_intake_workflow as intake_fixture
import test_reconciliation as fixture
from evorthon_data.verification.core.canonical import result_digest
from evorthon_data.verification.core.reconciliation import (
    ExpectedMaterial,
    FindingKind,
    ReconciliationRefusalReason,
    ReconciliationRefused,
)
from evorthon_data.verification.domain.contracts import (
    DatasetProvenance,
    EvidenceProvenance,
    ExpectedOutputOrigin,
    VerificationStatus,
)
from evorthon_data.verification.enforcement.validation import (
    PolicyChangedAfterObservationError,
    inspect_verification_record,
    observe_policy,
)
from evorthon_data.verification.ports.contracts import PortRefusal, ProducedOutput
from evorthon_data.verification.workflows import intake_case, reconcile_run

OUTPUT_ID = fixture.OUTPUT_ID


def produced_from(output, **changes) -> ProducedOutput:
    """Return the output a runner declares for one observed output."""
    declaration = ProducedOutput(
        output_id=output.output_id,
        version=output.version,
        content_digest=output.content_digest,
        format_digest=output.format_digest,
        row_count=output.row_count,
    )
    return replace(declaration, **changes) if changes else declaration


class RefusingRunner(intake_fixture.FakeCandidateRunner):
    """A runner that refuses to produce outputs through the port refusal type."""

    def produce_outputs(self, facts):
        raise PortRefusal("the environment cannot run this candidate over the frozen facts")


class Prepared:
    """One accepted intake and the material a reconciliation needs for it."""

    def __init__(self, scenario=None, *, produced=None, runner=None):
        scenario = fixture.scenario() if scenario is None else scenario
        self.case = intake_fixture.with_stored_evidence_digests(scenario.case)
        self.observation = scenario.observation
        self.expected = ExpectedMaterial(self.case.expected_outputs[0], scenario.expected.rows)
        declared = (produced_from(self.observation.output),) if produced is None else produced
        self.runner = intake_fixture.FakeCandidateRunner(outputs=declared) if runner is None else runner
        self.intake = intake_case(
            self.case,
            evidence_repository=intake_fixture.FakeEvidenceRepository(intake_fixture.answers_for(self.case)),
            candidate_runner=self.runner,
        )
        self.observation_of_policy = observe_policy(self.case)

    def reconcile(self, case=None, *, policy_observation=None, intake=None):
        return reconcile_run(
            self.case if case is None else case,
            self.intake if intake is None else intake,
            policy_observation=self.observation_of_policy if policy_observation is None else policy_observation,
            expected_material={OUTPUT_ID: self.expected},
            observations={OUTPUT_ID: self.observation},
            candidate_runner=self.runner,
        )


def refusal(prepared, **arguments) -> ReconciliationRefusalReason:
    with pytest.raises(ReconciliationRefused) as raised:
        prepared.reconcile(**arguments)
    return raised.value.reason


def test_an_exact_candidate_run_reconciles_into_a_passing_verification_result():
    prepared = Prepared()

    outcome = prepared.reconcile()

    assert outcome.result.status is VerificationStatus.PASS
    assert inspect_verification_record(outcome.result).valid
    assert outcome.result_digest == result_digest(outcome.result)
    assert outcome.result.clause_outcomes == tuple(clause.outcome for clause in outcome.clauses)
    assert outcome.result.actual_outputs == (prepared.observation.output,)
    assert outcome.result.independent_receipts == prepared.intake.receipts
    assert outcome.findings == ()


def test_a_deliberate_difference_reconciles_into_a_failing_verification_result():
    prepared = Prepared(fixture.value_failure())

    outcome = prepared.reconcile()

    assert outcome.result.status is VerificationStatus.FAIL
    assert inspect_verification_record(outcome.result).valid
    assert {finding.kind for finding in outcome.findings} == {FindingKind.VALUE_DIVERGENCE}


def test_a_tolerance_changed_after_observation_fails_closed():
    prepared = Prepared()
    policy = prepared.case.comparison_policy
    widened = replace(
        prepared.case,
        comparison_policy=replace(
            policy, tolerances=(replace(policy.tolerances[0], upper_bound="9.99"), *policy.tolerances[1:])
        ),
    )

    with pytest.raises(PolicyChangedAfterObservationError):
        prepared.reconcile(widened)


def test_an_exclusion_changed_after_observation_fails_closed():
    prepared = Prepared(fixture.exclusion_pass())
    policy = prepared.case.comparison_policy
    narrowed = replace(
        prepared.case,
        comparison_policy=replace(
            policy, exclusions=(replace(policy.exclusions[0], rationale="a different approved reason"),)
        ),
    )

    with pytest.raises(PolicyChangedAfterObservationError):
        prepared.reconcile(narrowed)


def test_a_warning_band_changed_after_observation_fails_closed():
    prepared = Prepared()
    policy = prepared.case.comparison_policy
    widened = replace(
        prepared.case,
        comparison_policy=replace(policy, warning_bands=(replace(policy.warning_bands[0], upper_bound="9.99"),)),
    )

    with pytest.raises(PolicyChangedAfterObservationError):
        prepared.reconcile(widened)


def test_the_policy_rules_are_the_enforcement_rules_and_an_unchanged_policy_passes_them():
    prepared = Prepared()

    outcome = prepared.reconcile(policy_observation=observe_policy(prepared.case))

    assert outcome.result.status is VerificationStatus.PASS


def test_an_intake_taken_for_another_case_is_refused():
    prepared = Prepared()
    other = Prepared(fixture.value_failure())

    assert (
        refusal(prepared, case=other.case, policy_observation=other.observation_of_policy)
        is ReconciliationRefusalReason.INTAKE_CASE_MISMATCH
    )


def test_a_candidate_output_that_contradicts_the_runners_declaration_is_refused():
    prepared = Prepared()
    prepared.runner = intake_fixture.FakeCandidateRunner(
        outputs=(produced_from(prepared.observation.output, content_digest="blake2b-256:another-run"),)
    )

    assert refusal(prepared) is ReconciliationRefusalReason.CANDIDATE_OUTPUT_MISMATCH


def test_a_runner_that_declares_no_output_for_a_compared_clause_is_refused():
    prepared = Prepared(produced=())

    assert refusal(prepared) is ReconciliationRefusalReason.CANDIDATE_OUTPUT_MISMATCH


def test_a_runner_that_refuses_to_produce_outputs_is_refused():
    prepared = Prepared()
    prepared.runner = RefusingRunner()

    assert refusal(prepared) is ReconciliationRefusalReason.CANDIDATE_OUTPUT_MISMATCH


def test_a_clause_with_no_supplied_observation_is_refused():
    prepared = Prepared()

    with pytest.raises(ReconciliationRefused) as raised:
        reconcile_run(
            prepared.case,
            prepared.intake,
            policy_observation=prepared.observation_of_policy,
            expected_material={OUTPUT_ID: prepared.expected},
            observations={},
            candidate_runner=prepared.runner,
        )

    assert raised.value.reason is ReconciliationRefusalReason.UNRESOLVED_ACTUAL_OUTPUT


def test_two_runs_over_the_same_material_produce_the_identical_result_and_digest():
    prepared = Prepared()

    first = prepared.reconcile()
    second = prepared.reconcile()

    assert first.result == second.result
    assert first.result_digest == second.result_digest


def test_a_shuffled_candidate_row_order_produces_the_identical_result_and_digest():
    ordered = Prepared()
    shuffled = Prepared(fixture.scenario(actual_rows=(fixture.BASE_ROWS[2], fixture.BASE_ROWS[0], fixture.BASE_ROWS[1])))

    assert shuffled.reconcile().result == ordered.reconcile().result
    assert shuffled.reconcile().result_digest == ordered.reconcile().result_digest


@pytest.mark.parametrize(
    "provenance, label",
    [
        (DatasetProvenance.REAL, EvidenceProvenance.REAL),
        (DatasetProvenance.SYNTHETIC, EvidenceProvenance.SYNTHETIC),
        (DatasetProvenance.DERIVED, EvidenceProvenance.MIXED),
    ],
    ids=lambda value: value.value,
)
def test_a_result_carries_the_label_its_case_derives_and_takes_the_same_path(provenance, label):
    prepared = Prepared(
        fixture.scenario(
            provenance=provenance,
            expected_origin=(
                ExpectedOutputOrigin.MODERNISATION_CAPTURE
                if provenance is DatasetProvenance.REAL
                else ExpectedOutputOrigin.SYNTHETIC_DERIVATION
            ),
        )
    )

    outcome = prepared.reconcile()

    assert outcome.evidence_provenance is label
    assert outcome.result.status is VerificationStatus.PASS
    assert outcome.findings == ()


def test_the_runner_receives_the_frozen_facts_intake_prepared_and_nothing_else():
    prepared = Prepared()

    prepared.reconcile()

    assert prepared.runner.received[-1] == prepared.intake.candidate_facts
    assert all("expected" not in fact.subject for fact in prepared.intake.candidate_facts.facts)
