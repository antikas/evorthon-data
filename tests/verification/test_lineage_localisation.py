"""Backward localisation over declared lineage graphs: every shape, every reason, every refusal."""
# evorthon-verifies: EVD-README-027
# evorthon-verifies: EVD-README-020
# evorthon-verifies: EVD-README-009
from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

import test_reconciliation as fixture
from evorthon_data.verification.core.localisation import (
    CheckpointComparison,
    LOCALISATION_FORM,
    LocalisationRefusalReason,
    LocalisationRefused,
    OutputOutcome,
    compare_checkpoint,
    failed_outputs,
    localise,
    localise_output,
)
from evorthon_data.verification.domain.contracts import (
    Checkpoint,
    ClauseFamily,
    ClauseOutcome,
    ComparisonDimension,
    EvidenceReference,
    LineageDefinition,
    LineageFrontier,
    LocalisationStatus,
    OutputLineageBinding,
    UncoveredPathReason,
    VerificationStatus,
)
from evorthon_data.verification.enforcement.validation import inspect_verification_record

DAILY_OUTPUT = "daily-output"
MONTHLY_OUTPUT = "monthly-output"
LANDING = "landing"
CONFORMED = "conformed"
PUBLISHED = "published"
CONFORMED_ORDERS = "conformed-orders"
CONFORMED_CUSTOMERS = "conformed-customers"
PUBLISHED_DAILY = "published-daily"
PUBLISHED_MONTHLY = "published-monthly"
LANDING_ORDERS = "landing-orders"
LANDING_CUSTOMERS = "landing-customers"

PASS = VerificationStatus.PASS
FAIL = VerificationStatus.FAIL


def checkpoint(checkpoint_id: str, parents: tuple[str, ...] = (), *, replay=None) -> Checkpoint:
    """Return one declared checkpoint with the shape the frozen output declares."""
    return Checkpoint(
        checkpoint_id=checkpoint_id,
        version="v1",
        parent_ids=parents,
        expected_state=fixture.identity(f"{checkpoint_id}-state"),
        schema=fixture.schema(),
        grain=fixture.grain(),
        canonicalisation=fixture.CANONICALISATION,
        transformation=fixture.identity(f"{checkpoint_id}-transformation"),
        provenance=fixture.identity(f"{checkpoint_id}-provenance"),
        diagnostic_evidence=(fixture.evidence(f"{checkpoint_id}-evidence"),),
        replay=replay,
    )


def lineage(lineage_id: str, checkpoints, bindings) -> LineageDefinition:
    return LineageDefinition(
        lineage_id=lineage_id,
        version="v1",
        checkpoints=tuple(checkpoints),
        output_bindings=tuple(OutputLineageBinding(output_id, terminal) for output_id, terminal in bindings),
    )


def chain_graph() -> LineageDefinition:
    """One product built from one predecessor, then published."""
    return lineage(
        "chain-lineage",
        (
            checkpoint(LANDING),
            checkpoint(CONFORMED, (LANDING,)),
            checkpoint(PUBLISHED, (CONFORMED,)),
        ),
        ((DAILY_OUTPUT, PUBLISHED),),
    )


def fork_graph() -> LineageDefinition:
    """One predecessor feeding two published outputs."""
    return lineage(
        "fork-lineage",
        (
            checkpoint(LANDING),
            checkpoint(PUBLISHED_DAILY, (LANDING,)),
            checkpoint(PUBLISHED_MONTHLY, (LANDING,)),
        ),
        ((DAILY_OUTPUT, PUBLISHED_DAILY), (MONTHLY_OUTPUT, PUBLISHED_MONTHLY)),
    )


def join_graph() -> LineageDefinition:
    """Two independent sources reconverging into one published output."""
    return lineage(
        "join-lineage",
        (
            checkpoint(LANDING_ORDERS),
            checkpoint(LANDING_CUSTOMERS),
            checkpoint(PUBLISHED, (LANDING_ORDERS, LANDING_CUSTOMERS)),
        ),
        ((DAILY_OUTPUT, PUBLISHED),),
    )


def diamond_graph() -> LineageDefinition:
    """One source splitting into two branches that reconverge into one output."""
    return lineage(
        "diamond-lineage",
        (
            checkpoint(LANDING),
            checkpoint(CONFORMED_ORDERS, (LANDING,)),
            checkpoint(CONFORMED_CUSTOMERS, (LANDING,)),
            checkpoint(PUBLISHED, (CONFORMED_ORDERS, CONFORMED_CUSTOMERS)),
        ),
        ((DAILY_OUTPUT, PUBLISHED),),
    )


def unbound_graph() -> LineageDefinition:
    """A definition that declares no lineage node for its output."""
    return lineage("output-only-lineage", (), ((DAILY_OUTPUT, None),))


def outcome(output_id: str = DAILY_OUTPUT, status: VerificationStatus = FAIL) -> OutputOutcome:
    """Return one reconciled clause outcome for an output."""
    return OutputOutcome(
        output_id,
        ClauseOutcome(
            outcome_id=f"{output_id}/parity",
            version="v1",
            clause=fixture.identity(f"{output_id}-clause"),
            family=ClauseFamily.PARITY,
            status=status,
            compared_dimensions=(ComparisonDimension.VALUE,),
            expected_evidence=(fixture.evidence(f"{output_id}-expected"),),
            observed_evidence=(fixture.evidence(f"{output_id}-observed"),),
        ),
    )


def compared(graph: LineageDefinition, statuses) -> tuple[CheckpointComparison, ...]:
    """Return one comparison per named checkpoint, carrying that checkpoint's declared evidence."""
    declared = {node.checkpoint_id: node for node in graph.checkpoints}
    return tuple(
        CheckpointComparison(checkpoint_id, status, declared[checkpoint_id].diagnostic_evidence)
        for checkpoint_id, status in statuses.items()
    )


@dataclass(frozen=True)
class Walk:
    """One declared graph, one failed output and the evidence in hand for it."""

    lineage: LineageDefinition
    output_id: str
    outcomes: tuple[OutputOutcome, ...]
    comparisons: tuple[CheckpointComparison, ...]

    def localise(self):
        return localise_output(
            self.lineage, self.output_id, outcomes=self.outcomes, comparisons=self.comparisons
        )


def walk(graph: LineageDefinition, statuses, *, output_id: str = DAILY_OUTPUT, outcomes=None) -> Walk:
    return Walk(
        lineage=graph,
        output_id=output_id,
        outcomes=(outcome(output_id),) if outcomes is None else outcomes,
        comparisons=compared(graph, statuses),
    )


def names(frontiers: tuple[LineageFrontier, ...]) -> tuple[str, ...]:
    return tuple(frontier.checkpoint_id for frontier in frontiers)


def paths(localisation):
    return tuple((path.path_id, path.checkpoint_ids, path.reason) for path in localisation.uncovered_paths)


# --- One named walk per declared graph shape and per honest conclusion ---


def chain_confirmed_divergence() -> Walk:
    return walk(chain_graph(), {LANDING: PASS, CONFORMED: FAIL, PUBLISHED: FAIL})


def chain_interval_over_missing_evidence() -> Walk:
    return walk(chain_graph(), {LANDING: PASS, PUBLISHED: FAIL})


def chain_output_only() -> Walk:
    return walk(chain_graph(), {})


def chain_terminal_matches() -> Walk:
    return walk(chain_graph(), {PUBLISHED: PASS})


def fork_confirmed_branch() -> Walk:
    return walk(fork_graph(), {LANDING: PASS, PUBLISHED_DAILY: FAIL})


def join_confirmed_source() -> Walk:
    return walk(join_graph(), {LANDING_ORDERS: PASS, LANDING_CUSTOMERS: FAIL, PUBLISHED: FAIL})


def diamond_simultaneous_branches() -> Walk:
    return walk(
        diamond_graph(),
        {LANDING: PASS, CONFORMED_ORDERS: FAIL, CONFORMED_CUSTOMERS: FAIL, PUBLISHED: FAIL},
    )


def diamond_reconvergence() -> Walk:
    return walk(
        diamond_graph(),
        {LANDING: PASS, CONFORMED_ORDERS: FAIL, CONFORMED_CUSTOMERS: PASS, PUBLISHED: FAIL},
    )


def diamond_ambiguous_branches() -> Walk:
    return walk(diamond_graph(), {LANDING: PASS, PUBLISHED: FAIL})


def diamond_inconclusive_branch() -> Walk:
    return walk(
        diamond_graph(),
        {
            LANDING: PASS,
            CONFORMED_CUSTOMERS: VerificationStatus.INSUFFICIENT_EVIDENCE,
            CONFORMED_ORDERS: PASS,
            PUBLISHED: FAIL,
        },
    )


def unbound_output() -> Walk:
    return walk(unbound_graph(), {})


NAMED_WALKS = (
    chain_confirmed_divergence,
    chain_interval_over_missing_evidence,
    chain_output_only,
    chain_terminal_matches,
    fork_confirmed_branch,
    join_confirmed_source,
    diamond_simultaneous_branches,
    diamond_reconvergence,
    diamond_ambiguous_branches,
    diamond_inconclusive_branch,
    unbound_output,
)


@pytest.mark.parametrize("named", NAMED_WALKS, ids=lambda named: named.__name__)
def test_every_named_walk_declares_a_lineage_the_central_validator_accepts(named):
    assert inspect_verification_record(named().lineage).issues == ()


@pytest.mark.parametrize("named", NAMED_WALKS, ids=lambda named: named.__name__)
def test_every_named_walk_produces_a_localisation_the_central_validator_accepts(named):
    assert inspect_verification_record(named().localise()).issues == ()


@pytest.mark.parametrize("named", NAMED_WALKS, ids=lambda named: named.__name__)
def test_two_walks_over_the_same_declaration_and_evidence_produce_the_identical_record(named):
    assert named().localise() == named().localise()


# --- Chain, fork, join and diamond ---


def test_a_chain_identifies_the_first_confirmed_divergence_and_not_the_failing_output():
    localisation = chain_confirmed_divergence().localise()

    assert localisation.status is LocalisationStatus.CONFIRMED
    assert names(localisation.upper_frontier) == (CONFORMED,)
    assert names(localisation.lower_frontier) == (LANDING,)
    assert localisation.uncovered_paths == ()


def test_a_fork_localises_each_output_inside_its_own_branch():
    graph = fork_graph()
    outcomes = (outcome(DAILY_OUTPUT), outcome(MONTHLY_OUTPUT))

    localisations = localise(
        graph,
        outcomes=outcomes,
        comparisons=compared(graph, {LANDING: PASS, PUBLISHED_DAILY: FAIL, PUBLISHED_MONTHLY: FAIL}),
    )

    assert tuple(item.output_id for item in localisations) == (DAILY_OUTPUT, MONTHLY_OUTPUT)
    assert names(localisations[0].localisation.upper_frontier) == (PUBLISHED_DAILY,)
    assert names(localisations[1].localisation.upper_frontier) == (PUBLISHED_MONTHLY,)
    assert names(localisations[0].localisation.lower_frontier) == (LANDING,)


def test_a_join_names_the_diverging_source_and_not_the_reconverged_output():
    localisation = join_confirmed_source().localise()

    assert localisation.status is LocalisationStatus.CONFIRMED
    assert names(localisation.upper_frontier) == (LANDING_CUSTOMERS,)
    assert PUBLISHED not in names(localisation.upper_frontier)


def test_a_diamond_reports_simultaneous_branches_as_two_confirmed_divergences():
    localisation = diamond_simultaneous_branches().localise()

    assert localisation.status is LocalisationStatus.CONFIRMED
    assert names(localisation.upper_frontier) == (CONFORMED_CUSTOMERS, CONFORMED_ORDERS)
    assert names(localisation.lower_frontier) == (LANDING,)


def test_a_diamond_with_one_matching_branch_confirms_the_other_branch_alone():
    localisation = diamond_reconvergence().localise()

    assert localisation.status is LocalisationStatus.CONFIRMED
    assert names(localisation.upper_frontier) == (CONFORMED_ORDERS,)
    assert names(localisation.lower_frontier) == (LANDING,)
    assert localisation.uncovered_paths == ()


def test_a_diamond_with_two_uncompared_branches_reports_them_as_an_ambiguous_branch():
    localisation = diamond_ambiguous_branches().localise()

    assert localisation.status is LocalisationStatus.INFERRED
    assert names(localisation.upper_frontier) == (PUBLISHED,)
    assert names(localisation.lower_frontier) == (LANDING,)
    assert paths(localisation) == (
        (
            f"{DAILY_OUTPUT}/{CONFORMED_CUSTOMERS}",
            (CONFORMED_CUSTOMERS,),
            UncoveredPathReason.MISSING_CHECKPOINT_EVIDENCE,
        ),
        (
            f"{DAILY_OUTPUT}/{CONFORMED_ORDERS}",
            (CONFORMED_ORDERS,),
            UncoveredPathReason.MISSING_CHECKPOINT_EVIDENCE,
        ),
        (
            f"{DAILY_OUTPUT}/{PUBLISHED}/branches",
            (CONFORMED_CUSTOMERS, CONFORMED_ORDERS),
            UncoveredPathReason.AMBIGUOUS_BRANCH,
        ),
    )


def test_a_branch_a_comparison_left_inconclusive_stays_an_uncovered_interval():
    localisation = diamond_inconclusive_branch().localise()

    assert localisation.status is LocalisationStatus.INFERRED
    assert paths(localisation) == (
        (
            f"{DAILY_OUTPUT}/{CONFORMED_CUSTOMERS}",
            (CONFORMED_CUSTOMERS,),
            UncoveredPathReason.MISSING_CHECKPOINT_EVIDENCE,
        ),
    )
    assert names(localisation.lower_frontier) == (CONFORMED_ORDERS, LANDING)


# --- Honest intervals ---


def test_an_output_only_localisation_is_labelled_inferred_over_the_whole_declared_path():
    localisation = chain_output_only().localise()

    assert localisation.status is LocalisationStatus.INFERRED
    assert names(localisation.lower_frontier) == (LANDING,)
    assert names(localisation.upper_frontier) == (PUBLISHED,)
    assert paths(localisation) == (
        (
            f"{DAILY_OUTPUT}/{LANDING}",
            (LANDING, CONFORMED, PUBLISHED),
            UncoveredPathReason.OUTPUT_ONLY,
        ),
    )


def test_an_uncompared_checkpoint_between_two_compared_ones_remains_an_interval():
    localisation = chain_interval_over_missing_evidence().localise()

    assert localisation.status is LocalisationStatus.INFERRED
    assert names(localisation.lower_frontier) == (LANDING,)
    assert names(localisation.upper_frontier) == (PUBLISHED,)
    assert paths(localisation) == (
        (
            f"{DAILY_OUTPUT}/{CONFORMED}",
            (CONFORMED,),
            UncoveredPathReason.MISSING_CHECKPOINT_EVIDENCE,
        ),
    )


def test_a_matching_terminal_under_a_failed_output_bounds_the_interval_at_that_terminal():
    localisation = chain_terminal_matches().localise()

    assert localisation.status is LocalisationStatus.INFERRED
    assert names(localisation.lower_frontier) == (PUBLISHED,)
    assert names(localisation.upper_frontier) == (PUBLISHED,)
    assert localisation.uncovered_paths == ()


def test_an_output_the_definition_places_on_no_node_localises_as_unknown():
    localisation = unbound_output().localise()

    assert localisation.status is LocalisationStatus.UNKNOWN
    assert localisation.lower_frontier == ()
    assert localisation.upper_frontier == ()
    assert localisation.uncovered_paths == ()
    assert localisation.supporting_evidence == (fixture.evidence(f"{DAILY_OUTPUT}-observed"),)


def test_a_localisation_carries_the_evidence_that_confirmed_each_boundary():
    localisation = chain_confirmed_divergence().localise()
    declared = {node.checkpoint_id: node for node in chain_graph().checkpoints}

    assert localisation.upper_frontier[0].evidence == declared[CONFORMED].diagnostic_evidence
    assert localisation.lower_frontier[0].evidence == declared[LANDING].diagnostic_evidence
    assert localisation.version == LOCALISATION_FORM


def test_only_the_domains_own_status_and_reason_vocabulary_reaches_a_localisation():
    for named in NAMED_WALKS:
        localisation = named().localise()
        assert isinstance(localisation.status, LocalisationStatus)
        for path in localisation.uncovered_paths:
            assert isinstance(path.reason, UncoveredPathReason)


def test_localisation_reports_one_record_per_failed_output_and_none_for_a_passing_one():
    graph = fork_graph()

    assert failed_outputs(graph, (outcome(DAILY_OUTPUT), outcome(MONTHLY_OUTPUT, PASS))) == (DAILY_OUTPUT,)
    assert localise(graph, outcomes=(outcome(MONTHLY_OUTPUT, PASS),), comparisons=()) == ()


# --- The one checkpoint comparison ---


def test_a_replayed_state_that_matches_the_declared_state_passes_and_a_different_one_fails():
    node = checkpoint(PUBLISHED)

    matched = compare_checkpoint(node, node.expected_state.digest, node.diagnostic_evidence)
    diverged = compare_checkpoint(node, "sha256:another-state", node.diagnostic_evidence)

    assert matched.status is PASS
    assert diverged.status is FAIL
    assert diverged.evidence == node.diagnostic_evidence


# --- Integrity refusals ---


def refusal(call) -> LocalisationRefusalReason:
    with pytest.raises(LocalisationRefused) as raised:
        call()
    return raised.value.reason


def test_an_outcome_for_an_output_the_definition_does_not_bind_is_refused():
    graph = chain_graph()

    assert (
        refusal(lambda: localise_output(graph, MONTHLY_OUTPUT, outcomes=(outcome(MONTHLY_OUTPUT),), comparisons=()))
        is LocalisationRefusalReason.UNBOUND_OUTPUT
    )
    assert (
        refusal(lambda: localise(graph, outcomes=(outcome(MONTHLY_OUTPUT),), comparisons=()))
        is LocalisationRefusalReason.UNBOUND_OUTPUT
    )


def test_localising_an_output_that_did_not_fail_is_refused():
    graph = chain_graph()

    assert (
        refusal(lambda: localise_output(graph, DAILY_OUTPUT, outcomes=(outcome(DAILY_OUTPUT, PASS),), comparisons=()))
        is LocalisationRefusalReason.NOT_A_FAILED_OUTPUT
    )


def test_a_binding_a_parent_or_a_comparison_naming_an_undeclared_checkpoint_is_refused():
    unresolved_terminal = lineage("broken-lineage", (checkpoint(LANDING),), ((DAILY_OUTPUT, PUBLISHED),))
    unresolved_parent = lineage(
        "broken-lineage", (checkpoint(PUBLISHED, (CONFORMED,)),), ((DAILY_OUTPUT, PUBLISHED),)
    )
    graph = chain_graph()
    stray = CheckpointComparison(PUBLISHED_MONTHLY, PASS, (fixture.evidence("stray-evidence"),))

    for broken in (unresolved_terminal, unresolved_parent):
        assert (
            refusal(lambda broken=broken: localise_output(broken, DAILY_OUTPUT, outcomes=(outcome(),), comparisons=()))
            is LocalisationRefusalReason.UNRESOLVED_CHECKPOINT
        )
    assert (
        refusal(lambda: localise_output(graph, DAILY_OUTPUT, outcomes=(outcome(),), comparisons=(stray,)))
        is LocalisationRefusalReason.UNRESOLVED_CHECKPOINT
    )


def test_a_checkpoint_or_an_output_declared_twice_is_refused():
    repeated_checkpoint = lineage(
        "repeated-lineage", (checkpoint(PUBLISHED), checkpoint(PUBLISHED)), ((DAILY_OUTPUT, PUBLISHED),)
    )
    repeated_binding = LineageDefinition(
        "repeated-lineage",
        "v1",
        (checkpoint(PUBLISHED),),
        (OutputLineageBinding(DAILY_OUTPUT, PUBLISHED), OutputLineageBinding(DAILY_OUTPUT, PUBLISHED)),
    )

    for broken in (repeated_checkpoint, repeated_binding):
        assert (
            refusal(lambda broken=broken: localise_output(broken, DAILY_OUTPUT, outcomes=(outcome(),), comparisons=()))
            is LocalisationRefusalReason.DUPLICATE_DECLARATION
        )


def test_a_declared_graph_that_returns_to_a_checkpoint_it_reached_is_refused():
    cyclic = lineage(
        "cyclic-lineage",
        (checkpoint(CONFORMED, (PUBLISHED,)), checkpoint(PUBLISHED, (CONFORMED,))),
        ((DAILY_OUTPUT, PUBLISHED),),
    )

    assert (
        refusal(lambda: localise_output(cyclic, DAILY_OUTPUT, outcomes=(outcome(),), comparisons=()))
        is LocalisationRefusalReason.CYCLIC_LINEAGE
    )


def test_two_comparisons_of_one_checkpoint_that_disagree_are_refused():
    graph = chain_graph()
    declared = {node.checkpoint_id: node for node in graph.checkpoints}
    disagreeing = (
        CheckpointComparison(PUBLISHED, PASS, declared[PUBLISHED].diagnostic_evidence),
        CheckpointComparison(PUBLISHED, FAIL, declared[PUBLISHED].diagnostic_evidence),
    )

    assert (
        refusal(lambda: localise_output(graph, DAILY_OUTPUT, outcomes=(outcome(),), comparisons=disagreeing))
        is LocalisationRefusalReason.CONTRADICTORY_COMPARISON
    )


def test_a_boundary_with_no_supporting_evidence_is_refused():
    graph = chain_graph()
    unsupported = (CheckpointComparison(PUBLISHED, FAIL, ()),)
    blind = OutputOutcome(DAILY_OUTPUT, replace(outcome().outcome, observed_evidence=()))
    node = checkpoint(PUBLISHED)

    assert (
        refusal(lambda: localise_output(graph, DAILY_OUTPUT, outcomes=(outcome(),), comparisons=unsupported))
        is LocalisationRefusalReason.MISSING_EVIDENCE
    )
    assert (
        refusal(lambda: localise_output(graph, DAILY_OUTPUT, outcomes=(blind,), comparisons=()))
        is LocalisationRefusalReason.MISSING_EVIDENCE
    )
    assert (
        refusal(lambda: compare_checkpoint(node, "  ", node.diagnostic_evidence))
        is LocalisationRefusalReason.MISSING_EVIDENCE
    )
    assert (
        refusal(lambda: compare_checkpoint(node, node.expected_state.digest, ()))
        is LocalisationRefusalReason.MISSING_EVIDENCE
    )


def test_one_evidence_identifier_that_carries_two_records_is_refused():
    graph = chain_graph()
    declared = {node.checkpoint_id: node for node in graph.checkpoints}
    altered = replace(declared[PUBLISHED].diagnostic_evidence[0], digest="sha256:another-record")
    conflicting = (
        CheckpointComparison(PUBLISHED, FAIL, declared[PUBLISHED].diagnostic_evidence),
        CheckpointComparison(PUBLISHED, FAIL, (altered,)),
    )

    assert (
        refusal(lambda: localise_output(graph, DAILY_OUTPUT, outcomes=(outcome(),), comparisons=conflicting))
        is LocalisationRefusalReason.AMBIGUOUS_EVIDENCE
    )


def test_a_definition_that_is_not_a_lineage_or_a_binding_is_refused():
    not_a_lineage = fixture.identity("not-a-lineage")
    not_a_binding = LineageDefinition("odd-lineage", "v1", (checkpoint(PUBLISHED),), (fixture.identity("odd"),))

    assert (
        refusal(lambda: localise_output(not_a_lineage, DAILY_OUTPUT, outcomes=(outcome(),), comparisons=()))
        is LocalisationRefusalReason.UNRESOLVED_CHECKPOINT
    )
    assert (
        refusal(lambda: localise_output(not_a_binding, DAILY_OUTPUT, outcomes=(outcome(),), comparisons=()))
        is LocalisationRefusalReason.UNBOUND_OUTPUT
    )
    assert (
        refusal(lambda: compare_checkpoint(not_a_lineage, "sha256:state", (fixture.evidence("any"),)))
        is LocalisationRefusalReason.UNRESOLVED_CHECKPOINT
    )


def test_every_refusal_reason_is_proved_here():
    proved = {
        LocalisationRefusalReason.UNBOUND_OUTPUT,
        LocalisationRefusalReason.NOT_A_FAILED_OUTPUT,
        LocalisationRefusalReason.UNRESOLVED_CHECKPOINT,
        LocalisationRefusalReason.DUPLICATE_DECLARATION,
        LocalisationRefusalReason.CYCLIC_LINEAGE,
        LocalisationRefusalReason.CONTRADICTORY_COMPARISON,
        LocalisationRefusalReason.MISSING_EVIDENCE,
        LocalisationRefusalReason.AMBIGUOUS_EVIDENCE,
    }

    assert proved == set(LocalisationRefusalReason)


def test_nothing_is_refused_or_narrowed_for_the_provenance_a_declaration_carries():
    graph = chain_graph()
    synthetic = tuple(
        CheckpointComparison(
            item.checkpoint_id,
            item.status,
            (EvidenceReference(f"{item.checkpoint_id}-synthetic", "v1", "sha256:synthetic", "generated evidence"),),
        )
        for item in compared(graph, {LANDING: PASS, CONFORMED: FAIL, PUBLISHED: FAIL})
    )

    localisation = localise_output(graph, DAILY_OUTPUT, outcomes=(outcome(),), comparisons=synthetic)

    assert localisation.status is LocalisationStatus.CONFIRMED
    assert names(localisation.upper_frontier) == (CONFORMED,)
