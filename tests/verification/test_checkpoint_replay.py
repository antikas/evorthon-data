"""Isolated checkpoint replay over the environment contracts, and the explanations it separates."""
from __future__ import annotations

from dataclasses import replace

import pytest

import test_intake_workflow as intake_fixture
import test_lineage_localisation as walk_fixture
import test_reconciliation as fixture
from evorthon_data.verification.core.localisation import CheckpointComparison
from evorthon_data.verification.domain.contracts import (
    Checkpoint,
    DatasetRole,
    DiagnosticStrength,
    LineageDefinition,
    LocalisationStatus,
    OutputLineageBinding,
    ReplayInput,
    ReplaySpecification,
    UncoveredPathReason,
    VerificationStatus,
)
from evorthon_data.verification.enforcement.validation import (
    inspect_verification_case,
    inspect_verification_record,
)
from evorthon_data.verification.ports.contracts import PortRefusal, ProducedOutput
from evorthon_data.verification.workflows import (
    ReplayRefusalReason,
    ReplayRefused,
    intake_case,
    replay_checkpoint,
    replay_localisation,
)

OUTPUT_ID = fixture.OUTPUT_ID
LANDING = walk_fixture.LANDING
ORDERS = walk_fixture.CONFORMED_ORDERS
CUSTOMERS = walk_fixture.CONFORMED_CUSTOMERS
PUBLISHED = walk_fixture.PUBLISHED
INPUT_DATASET = "input-dataset"
REFERENCE_DATASET = "reference-dataset"
PASS = VerificationStatus.PASS
FAIL = VerificationStatus.FAIL

# The interval the supplied evidence leaves open: the output failed and the
# source matched, so both branches remain competing explanations.
OPEN_INTERVAL = {LANDING: PASS, PUBLISHED: FAIL}


def replay_for(node: Checkpoint, *, inputs=None) -> ReplaySpecification:
    """Return the replay one checkpoint declares for itself."""
    return ReplaySpecification(
        replay_id=f"{node.checkpoint_id}-replay",
        version="v1",
        checkpoint_id=node.checkpoint_id,
        inputs=(ReplayInput(INPUT_DATASET, DatasetRole.INPUT, True),) if inputs is None else inputs,
        context=fixture.CONTEXT,
        transformation=node.transformation,
        output_schema=node.schema,
        output_grain=node.grain,
        canonicalisation=node.canonicalisation,
    )


def diamond_graph(*, replayable=(ORDERS, CUSTOMERS), inputs=None) -> LineageDefinition:
    """One source splitting into two declared branches that reconverge into the output."""
    nodes = (
        walk_fixture.checkpoint(LANDING),
        walk_fixture.checkpoint(ORDERS, (LANDING,)),
        walk_fixture.checkpoint(CUSTOMERS, (LANDING,)),
        walk_fixture.checkpoint(PUBLISHED, (ORDERS, CUSTOMERS)),
    )
    declared = tuple(
        replace(node, replay=replay_for(node, inputs=inputs)) if node.checkpoint_id in replayable else node
        for node in nodes
    )
    return LineageDefinition(
        "diamond-lineage", "v1", declared, (OutputLineageBinding(OUTPUT_ID, PUBLISHED),)
    )


def replayable_case(graph: LineageDefinition):
    """Return an approved case whose lineage is one declared replayable graph."""
    base = fixture.scenario().case
    reference = replace(
        fixture.frozen_input(),
        dataset_id=REFERENCE_DATASET,
        role=DatasetRole.REFERENCE,
        approved_summary="approved frozen reference",
    )
    case = replace(
        base,
        frozen_datasets=(*base.frozen_datasets, reference),
        lineage=graph,
        diagnostic_strength=DiagnosticStrength.REPLAYABLE,
    )
    return intake_fixture.with_stored_evidence_digests(case)


def states(graph: LineageDefinition, diverging=()) -> dict[str, str]:
    """Return the state digest a replay of each checkpoint produces."""
    return {
        node.checkpoint_id: (
            f"sha256:{node.checkpoint_id}-replayed-elsewhere"
            if node.checkpoint_id in diverging
            else node.expected_state.digest
        )
        for node in graph.checkpoints
    }


class ReplayingRunner(intake_fixture.FakeCandidateRunner):
    """A runner that answers a replay with the states it produces from the given facts."""

    def __init__(self, produced_states=None):
        super().__init__()
        self._states = {} if produced_states is None else dict(produced_states)

    def produce_outputs(self, facts):
        self.received.append(facts)
        return tuple(
            ProducedOutput(checkpoint_id, "v1", digest, "sha256:replay-format", 3)
            for checkpoint_id, digest in sorted(self._states.items())
        )


class RefusingReplayRunner(ReplayingRunner):
    """A runner that refuses to replay through the port refusal type."""

    def produce_outputs(self, facts):
        raise PortRefusal("the environment cannot replay this checkpoint from its frozen inputs")


class Prepared:
    """One accepted intake over a replayable case and the evidence in hand for it."""

    def __init__(self, graph=None, *, diverging=(), runner=None, comparisons=None):
        self.graph = diamond_graph() if graph is None else graph
        self.case = replayable_case(self.graph)
        self.runner = ReplayingRunner(states(self.graph, diverging)) if runner is None else runner
        self.intake = intake_case(
            self.case,
            evidence_repository=intake_fixture.FakeEvidenceRepository(intake_fixture.answers_for(self.case)),
            candidate_runner=self.runner,
        )
        self.outcomes = (walk_fixture.outcome(OUTPUT_ID),)
        self.comparisons = (
            walk_fixture.compared(self.graph, OPEN_INTERVAL) if comparisons is None else comparisons
        )

    def replay(self, graph=None):
        return replay_localisation(
            self.graph if graph is None else graph,
            self.intake,
            OUTPUT_ID,
            outcomes=self.outcomes,
            comparisons=self.comparisons,
            candidate_runner=self.runner,
        )


def refusal(call) -> ReplayRefusalReason:
    with pytest.raises(ReplayRefused) as raised:
        call()
    return raised.value.reason


def names(frontiers) -> tuple[str, ...]:
    return tuple(frontier.checkpoint_id for frontier in frontiers)


def test_a_replayable_case_declares_a_lineage_the_central_validator_accepts():
    assert inspect_verification_case(replayable_case(diamond_graph())).issues == ()


def test_a_replay_supports_one_competing_explanation_and_rules_out_the_other():
    prepared = Prepared(diverging=(CUSTOMERS,))

    report = prepared.replay()

    assert report.output_id == OUTPUT_ID
    assert report.supported == (CUSTOMERS,)
    assert report.ruled_out == (ORDERS,)
    assert report.left_open == ()
    assert report.localisation.status is LocalisationStatus.CONFIRMED
    assert names(report.localisation.upper_frontier) == (CUSTOMERS,)
    assert names(report.localisation.lower_frontier) == (LANDING,)
    assert report.localisation.uncovered_paths == ()


def test_a_replay_that_rules_out_every_branch_confirms_the_checkpoint_they_reconverge_into():
    prepared = Prepared()

    report = prepared.replay()

    assert report.supported == ()
    assert report.ruled_out == (CUSTOMERS, ORDERS)
    assert report.localisation.status is LocalisationStatus.CONFIRMED
    assert names(report.localisation.upper_frontier) == (PUBLISHED,)
    assert names(report.localisation.lower_frontier) == (CUSTOMERS, ORDERS)


def test_an_explanation_with_no_declared_replay_is_left_open_and_keeps_its_interval():
    prepared = Prepared(diamond_graph(replayable=(ORDERS,)))

    report = prepared.replay()

    assert report.ruled_out == (ORDERS,)
    assert report.left_open == (CUSTOMERS,)
    assert [item.reason for item in report.explanations if item.checkpoint_id == CUSTOMERS] == [
        UncoveredPathReason.REPLAY_NOT_DECLARED
    ]
    assert report.localisation.status is LocalisationStatus.INFERRED
    assert [path.checkpoint_ids for path in report.localisation.uncovered_paths] == [(CUSTOMERS,)]


def test_a_confirmed_localisation_leaves_nothing_to_replay():
    prepared = Prepared(
        comparisons=walk_fixture.compared(
            diamond_graph(), {LANDING: PASS, ORDERS: FAIL, CUSTOMERS: PASS, PUBLISHED: FAIL}
        )
    )

    report = prepared.replay()

    assert report.explanations == ()
    assert report.comparisons == prepared.comparisons
    assert report.localisation.status is LocalisationStatus.CONFIRMED
    assert prepared.runner.received == []


def test_a_replay_receives_only_the_frozen_inputs_it_declares_and_its_declared_context():
    prepared = Prepared(diverging=(CUSTOMERS,))

    prepared.replay()

    assert {fact.fact_id for fact in prepared.intake.candidate_facts.facts} == {
        INPUT_DATASET,
        REFERENCE_DATASET,
    }
    for facts in prepared.runner.received:
        assert tuple(fact.fact_id for fact in facts.facts) == (INPUT_DATASET,)
        assert facts.context_id == fixture.CONTEXT.context_id
        assert facts.case_digest == prepared.intake.candidate_facts.case_digest


def test_a_replay_input_the_declaration_does_not_require_is_left_out_rather_than_refused():
    optional = (
        ReplayInput(INPUT_DATASET, DatasetRole.INPUT, True),
        ReplayInput("archive-dataset", DatasetRole.PRIOR_STATE, False),
    )
    prepared = Prepared(diamond_graph(inputs=optional), diverging=(CUSTOMERS,))

    report = prepared.replay()

    assert report.supported == (CUSTOMERS,)
    assert tuple(fact.fact_id for fact in prepared.runner.received[0].facts) == (INPUT_DATASET,)


def test_a_narrowed_localisation_is_a_record_the_central_validator_accepts():
    for diverging in ((), (CUSTOMERS,), (ORDERS, CUSTOMERS)):
        report = Prepared(diverging=diverging).replay()

        assert inspect_verification_record(report.localisation).issues == ()


def test_two_replays_over_the_same_declaration_and_evidence_report_the_identical_conclusion():
    first = Prepared(diverging=(CUSTOMERS,)).replay()
    second = Prepared(diverging=(CUSTOMERS,)).replay()

    assert first.localisation == second.localisation
    assert first.explanations == second.explanations


def test_a_required_replay_input_the_intake_did_not_freeze_is_refused():
    prepared = Prepared()
    unfrozen = diamond_graph(inputs=(ReplayInput("absent-dataset", DatasetRole.INPUT, True),))

    assert refusal(lambda: prepared.replay(unfrozen)) is ReplayRefusalReason.REPLAY_INPUT_NOT_FROZEN


def test_a_runner_that_refuses_to_replay_is_refused():
    prepared = Prepared(runner=RefusingReplayRunner())

    assert refusal(prepared.replay) is ReplayRefusalReason.RUNNER_REFUSED


def test_a_runner_that_declares_no_output_for_the_replayed_checkpoint_is_refused():
    prepared = Prepared(runner=ReplayingRunner({}))

    assert refusal(prepared.replay) is ReplayRefusalReason.REPLAY_OUTPUT_MISSING


def test_a_checkpoint_that_declares_no_replay_of_its_own_is_never_replayed():
    prepared = Prepared()
    declared = {node.checkpoint_id: node for node in prepared.graph.checkpoints}
    borrowed = replace(declared[PUBLISHED], replay=replay_for(declared[ORDERS]))

    for node in (declared[PUBLISHED], borrowed):
        assert (
            refusal(
                lambda node=node: replay_checkpoint(node, prepared.intake, candidate_runner=prepared.runner)
            )
            is ReplayRefusalReason.REPLAY_CONTRADICTION
        )


def test_a_replay_without_an_accepted_intake_is_refused():
    prepared = Prepared()
    declared = {node.checkpoint_id: node for node in prepared.graph.checkpoints}

    assert (
        refusal(
            lambda: replay_checkpoint(declared[ORDERS], prepared.case, candidate_runner=prepared.runner)
        )
        is ReplayRefusalReason.INTAKE_MISSING
    )


def test_every_refusal_reason_is_proved_here():
    proved = {
        ReplayRefusalReason.REPLAY_CONTRADICTION,
        ReplayRefusalReason.REPLAY_INPUT_NOT_FROZEN,
        ReplayRefusalReason.RUNNER_REFUSED,
        ReplayRefusalReason.REPLAY_OUTPUT_MISSING,
        ReplayRefusalReason.INTAKE_MISSING,
    }

    assert proved == set(ReplayRefusalReason)


def test_a_replay_verdict_is_the_same_kind_of_fact_as_any_other_checkpoint_comparison():
    prepared = Prepared(diverging=(CUSTOMERS,))

    report = prepared.replay()

    assert all(isinstance(comparison, CheckpointComparison) for comparison in report.comparisons)
    replayed = [item for item in report.comparisons if item.checkpoint_id == CUSTOMERS]
    assert [item.status for item in replayed] == [FAIL]
    assert [reference.evidence_id for reference in replayed[0].evidence] == [f"{CUSTOMERS}/replay"]
