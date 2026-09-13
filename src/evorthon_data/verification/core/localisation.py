"""Backward localisation of a failed output through a declared lineage graph.

This module answers one question: given a declared checkpoint graph, the
reconciled outcome of an expected output, and whatever checkpoint comparisons
are in hand, where did the divergence enter? It walks backwards from the failed
output through the declared graph and reports either an exact confirmation or
an honest interval. It decides nothing about acceptance, it gates nothing, and
it never narrows an interval by guesswork.

The module compares nothing itself. A checkpoint declares an expected state
identity, so the one comparison it supports is ``compare_checkpoint``, which
reads an observed state digest against the declared one. Every comparison over
frozen material belongs to the reconciliation engine and reaches this module as
the outcome that engine already produced. Two kinds of evidence therefore enter
here: the reconciled outcome of the output, and one comparison per checkpoint
whose state was observed.

The walk has four parts.

1. The path. The terminal checkpoint the definition binds to the failed output,
   and every checkpoint above it, following declared parents. Checkpoints that
   lead to another output are outside the path and never appear in its result.
2. The later boundary. The earliest checkpoints confirmed to diverge: a
   checkpoint whose comparison failed and that has no failing checkpoint above
   it. A path with no confirmed divergence is bounded instead by the terminal
   checkpoint the output binds, which is the last declared node above it.
3. The earlier boundary. The latest checkpoints confirmed to match, taken as
   the checkpoints that match and carry an unresolved or diverging child inside
   the interval. A path with no confirmed match is bounded instead by the
   earliest declared nodes of the interval.
4. The uncovered paths. Every run of checkpoints inside the interval whose
   state was never compared. They stay in the result as they are. A reader can
   see exactly which checkpoints the conclusion could not separate.

The status follows from those parts and adds nothing. A localisation is
confirmed when the later boundary is a confirmed divergence and no uncovered
checkpoint lies above it, so the divergence is exactly there. It is unknown
when the definition binds no terminal checkpoint for the output, because then
no declared node can bound anything. It is inferred in every other case, which
is the honest interval: the divergence lies after the earlier boundary and at
or before the later one.

An uncovered path carries the reason it cannot support a more precise
conclusion. When no checkpoint on the path was compared at all, the conclusion
rests on the output alone and the reason is output-only. When some were
compared and these were not, the reason is missing checkpoint evidence. When
one checkpoint inside the interval draws on more than one uncovered branch, the
branch that carried the divergence is undetermined, and those branches are
reported once more as an ambiguous branch. Nothing is refused, weakened or
labelled differently for being synthetic, inferred or weak.

Refusals are integrity refusals: an outcome for an output the definition does
not bind, a binding or a comparison naming a checkpoint the definition does not
declare, a checkpoint or an output declared twice, a declared graph that
returns to a checkpoint it already reached, two comparisons of one checkpoint
that disagree, a boundary the caller supplied no evidence for, and one evidence
identifier that carries more than one record. The module never invents a
missing declaration and never localises an output that did not fail.

The module reads no file, no clock, no environment and no locale, and it draws
no random value. Two walks over the same definition and the same evidence
produce identical records.
"""
# evorthon-implements: EVD-README-027
# evorthon-implements: EVD-README-020
# evorthon-implements: EVD-README-009
from __future__ import annotations

# evorthon-component: verification_core

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from evorthon_data.verification.domain.contracts import (
    Checkpoint,
    ClauseOutcome,
    DiagnosticLocalisation,
    EvidenceReference,
    LineageDefinition,
    LineageFrontier,
    LocalisationStatus,
    OutputLineageBinding,
    UncoveredPath,
    UncoveredPathReason,
    VerificationStatus,
)

LOCALISATION_FORM = "evorthon.verification.localisation.v1"

# The trailing segment that names the record holding the competing branches
# into one checkpoint, so it can never collide with a run of checkpoints.
BRANCH_PATH_SEGMENT = "branches"


class LocalisationRefusalReason(str, Enum):
    """The closed set of integrity reasons for refusing to localise."""

    UNBOUND_OUTPUT = "unbound-output"
    NOT_A_FAILED_OUTPUT = "not-a-failed-output"
    UNRESOLVED_CHECKPOINT = "unresolved-checkpoint"
    DUPLICATE_DECLARATION = "duplicate-declaration"
    CYCLIC_LINEAGE = "cyclic-lineage"
    CONTRADICTORY_COMPARISON = "contradictory-comparison"
    MISSING_EVIDENCE = "missing-evidence"
    AMBIGUOUS_EVIDENCE = "ambiguous-evidence"


class LocalisationRefused(ValueError):
    """Raised when a localisation cannot be made with declared meaning."""

    def __init__(self, reason: LocalisationRefusalReason, subject: str, detail: str) -> None:
        super().__init__(f"{reason.value} at {subject}: {detail}")
        self.reason = reason
        self.subject = subject
        self.detail = detail


@dataclass(frozen=True)
class CheckpointComparison:
    """One comparison of a declared checkpoint against its declared expected state.

    ``status`` reads as the comparison engine reports any outcome: a pass is a
    checkpoint whose observed state matches the state it declares, a failure is
    a confirmed divergence, and insufficient evidence leaves the checkpoint
    uncovered. ``evidence`` names what supports the comparison, which is the
    checkpoint evidence intake confirmed or the evidence a replay produced.
    """

    checkpoint_id: str
    status: VerificationStatus
    evidence: tuple[EvidenceReference, ...]


@dataclass(frozen=True)
class OutputOutcome:
    """One reconciled clause outcome, named by the expected output it compared.

    A clause outcome carries no output identity of its own, so the caller that
    reconciled it states which output it answers for. One output can carry more
    than one outcome, and it is failed when any of them failed.
    """

    output_id: str
    outcome: ClauseOutcome


@dataclass(frozen=True)
class OutputLocalisation:
    """The localisation of one failed output, named by that output."""

    output_id: str
    localisation: DiagnosticLocalisation


def _refuse(reason: LocalisationRefusalReason, subject: str, detail: str) -> LocalisationRefused:
    return LocalisationRefused(reason, subject, detail)


def _unresolved(status: VerificationStatus | None) -> bool:
    """Return whether a checkpoint's state was left uncovered rather than compared."""
    return status is None or status is VerificationStatus.INSUFFICIENT_EVIDENCE


def _distinct(references: Iterable[EvidenceReference], subject: str) -> tuple[EvidenceReference, ...]:
    """Return the references in identifier order, one record per identifier."""
    held: dict[str, EvidenceReference] = {}
    for reference in references:
        seen = held.get(reference.evidence_id)
        if seen is not None and seen != reference:
            raise _refuse(
                LocalisationRefusalReason.AMBIGUOUS_EVIDENCE,
                subject,
                f"evidence {reference.evidence_id} carries more than one version or digest",
            )
        held[reference.evidence_id] = reference
    return tuple(held[identifier] for identifier in sorted(held))


def compare_checkpoint(
    checkpoint: Checkpoint,
    observed_digest: str,
    evidence: tuple[EvidenceReference, ...],
) -> CheckpointComparison:
    """Return the comparison of one checkpoint's observed state with its declared state.

    This is the one place a checkpoint state is compared. A checkpoint declares
    an expected state identity rather than frozen material, so the comparison is
    over the declared digest and nothing else. A caller that holds material
    rather than a digest reconciles it through the comparison engine and brings
    the outcome here.
    """
    if not isinstance(checkpoint, Checkpoint):
        raise _refuse(
            LocalisationRefusalReason.UNRESOLVED_CHECKPOINT,
            "checkpoint",
            "a declared checkpoint is required to compare a state against",
        )
    subject = f"lineage.checkpoints[{checkpoint.checkpoint_id}]"
    if not isinstance(observed_digest, str) or not observed_digest.strip():
        raise _refuse(
            LocalisationRefusalReason.MISSING_EVIDENCE,
            subject,
            "an observed state digest is required to compare a checkpoint",
        )
    if not evidence:
        raise _refuse(
            LocalisationRefusalReason.MISSING_EVIDENCE,
            subject,
            "a checkpoint comparison must name the evidence that supports it",
        )
    matched = observed_digest == checkpoint.expected_state.digest
    return CheckpointComparison(
        checkpoint_id=checkpoint.checkpoint_id,
        status=VerificationStatus.PASS if matched else VerificationStatus.FAIL,
        evidence=_distinct(evidence, subject),
    )


def declared_checkpoints(lineage: LineageDefinition) -> dict[str, Checkpoint]:
    """Return every declared checkpoint by identity, refusing a definition it cannot walk."""
    if not isinstance(lineage, LineageDefinition):
        raise _refuse(
            LocalisationRefusalReason.UNRESOLVED_CHECKPOINT,
            "lineage",
            "a lineage definition is required to localise against",
        )
    declared: dict[str, Checkpoint] = {}
    for checkpoint in lineage.checkpoints:
        subject = f"lineage.checkpoints[{checkpoint.checkpoint_id}]"
        if checkpoint.checkpoint_id in declared:
            raise _refuse(
                LocalisationRefusalReason.DUPLICATE_DECLARATION,
                subject,
                "the definition declares one checkpoint identity more than once",
            )
        declared[checkpoint.checkpoint_id] = checkpoint
    for checkpoint in lineage.checkpoints:
        for parent_id in checkpoint.parent_ids:
            if parent_id not in declared:
                raise _refuse(
                    LocalisationRefusalReason.UNRESOLVED_CHECKPOINT,
                    f"lineage.checkpoints[{checkpoint.checkpoint_id}].parent_ids",
                    f"parent {parent_id} is not declared",
                )
    return declared


def declared_bindings(lineage: LineageDefinition) -> dict[str, str | None]:
    """Return the declared terminal checkpoint of every bound output, by output."""
    bindings: dict[str, str | None] = {}
    for binding in lineage.output_bindings:
        if not isinstance(binding, OutputLineageBinding):
            raise _refuse(
                LocalisationRefusalReason.UNBOUND_OUTPUT,
                "lineage.output_bindings",
                "the definition carries a binding that is not an output lineage binding",
            )
        if binding.expected_output_id in bindings:
            raise _refuse(
                LocalisationRefusalReason.DUPLICATE_DECLARATION,
                f"lineage.output_bindings[{binding.expected_output_id}]",
                "the definition binds one expected output more than once",
            )
        bindings[binding.expected_output_id] = binding.terminal_checkpoint_id
    return bindings


def _held_comparisons(
    comparisons: Sequence[CheckpointComparison], declared: Mapping[str, Checkpoint]
) -> dict[str, CheckpointComparison]:
    """Return one comparison per checkpoint, refusing an unresolved or contradicted one."""
    held: dict[str, CheckpointComparison] = {}
    for comparison in comparisons:
        subject = f"comparisons[{comparison.checkpoint_id}]"
        if comparison.checkpoint_id not in declared:
            raise _refuse(
                LocalisationRefusalReason.UNRESOLVED_CHECKPOINT,
                subject,
                "the comparison answers for a checkpoint the definition does not declare",
            )
        if not comparison.evidence:
            raise _refuse(
                LocalisationRefusalReason.MISSING_EVIDENCE,
                subject,
                "a checkpoint comparison must name the evidence that supports it",
            )
        seen = held.get(comparison.checkpoint_id)
        if seen is not None:
            if seen.status is not comparison.status:
                raise _refuse(
                    LocalisationRefusalReason.CONTRADICTORY_COMPARISON,
                    subject,
                    "two comparisons of one checkpoint report different outcomes",
                )
            merged = _distinct((*seen.evidence, *comparison.evidence), subject)
            held[comparison.checkpoint_id] = CheckpointComparison(comparison.checkpoint_id, seen.status, merged)
            continue
        held[comparison.checkpoint_id] = CheckpointComparison(
            comparison.checkpoint_id, comparison.status, _distinct(comparison.evidence, subject)
        )
    return held


def _ancestry(declared: Mapping[str, Checkpoint], terminal_id: str, subject: str) -> dict[str, tuple[str, ...]]:
    """Return every checkpoint at or above one terminal, with its declared parents."""
    ancestry: dict[str, tuple[str, ...]] = {}
    on_path: set[str] = set()

    def walk(node: str) -> None:
        if node in on_path:
            raise _refuse(
                LocalisationRefusalReason.CYCLIC_LINEAGE,
                subject,
                f"the declared graph returns to checkpoint {node} it already reached",
            )
        if node in ancestry:
            return
        on_path.add(node)
        parents = tuple(declared[node].parent_ids)
        for parent_id in parents:
            walk(parent_id)
        on_path.discard(node)
        ancestry[node] = parents

    walk(terminal_id)
    return ancestry


def _strict_ancestors(node: str, ancestry: Mapping[str, tuple[str, ...]]) -> set[str]:
    """Return every checkpoint strictly above one node on the walked path."""
    found: set[str] = set()
    stack = list(ancestry[node])
    while stack:
        current = stack.pop()
        if current in found:
            continue
        found.add(current)
        stack.extend(ancestry[current])
    return found


def _uncovered_region(
    upper_ids: Sequence[str],
    ancestry: Mapping[str, tuple[str, ...]],
    verdict: Mapping[str, VerificationStatus | None],
) -> set[str]:
    """Return the uncompared checkpoints that could hide an earlier divergence.

    The walk starts at the later boundary and follows declared parents upward.
    It stops at a checkpoint whose state matched, because a matching state
    bounds the interval, and it never crosses one.
    """
    region: set[str] = set()
    stack: list[str] = []
    for node in upper_ids:
        if _unresolved(verdict[node]):
            stack.append(node)
        elif verdict[node] is VerificationStatus.FAIL:
            stack.extend(ancestry[node])
    while stack:
        node = stack.pop()
        if node in region or not _unresolved(verdict[node]):
            continue
        region.add(node)
        stack.extend(ancestry[node])
    return region


def _components(region: set[str], ancestry: Mapping[str, tuple[str, ...]]) -> list[tuple[str, ...]]:
    """Return the uncovered checkpoints grouped into the runs they form."""
    neighbours: dict[str, set[str]] = {node: set() for node in region}
    for node in region:
        for parent_id in ancestry[node]:
            if parent_id in region:
                neighbours[node].add(parent_id)
                neighbours[parent_id].add(node)
    grouped: list[tuple[str, ...]] = []
    remaining = set(region)
    while remaining:
        seed = min(remaining)
        component: set[str] = set()
        stack = [seed]
        while stack:
            node = stack.pop()
            if node in component:
                continue
            component.add(node)
            stack.extend(neighbours[node])
        remaining -= component
        depth = {node: len(_strict_ancestors(node, ancestry) & component) for node in component}
        grouped.append(tuple(sorted(component, key=lambda node: (depth[node], node))))
    return grouped


def _frontier(
    node_ids: Sequence[str],
    held: Mapping[str, CheckpointComparison],
    confirmed: bool,
    observed: tuple[EvidenceReference, ...],
) -> tuple[LineageFrontier, ...]:
    """Return one boundary record per checkpoint, with the evidence that supports it."""
    return tuple(
        LineageFrontier(node, held[node].evidence if confirmed else observed) for node in sorted(node_ids)
    )


def _observed_evidence(outcomes: Sequence[OutputOutcome], output_id: str, subject: str) -> tuple[EvidenceReference, ...]:
    """Return the evidence the failed outcomes of one output observed."""
    failing = tuple(
        item.outcome
        for item in outcomes
        if item.output_id == output_id and item.outcome.status is VerificationStatus.FAIL
    )
    if not failing:
        raise _refuse(
            LocalisationRefusalReason.NOT_A_FAILED_OUTPUT,
            subject,
            "localisation reads a failed output and no supplied outcome for it failed",
        )
    observed = _distinct((reference for outcome in failing for reference in outcome.observed_evidence), subject)
    if not observed:
        raise _refuse(
            LocalisationRefusalReason.MISSING_EVIDENCE,
            subject,
            "a failed outcome must name the observed evidence its localisation rests on",
        )
    return observed


def _localise(
    lineage: LineageDefinition,
    output_id: str,
    declared: Mapping[str, Checkpoint],
    bindings: Mapping[str, str | None],
    held: Mapping[str, CheckpointComparison],
    outcomes: Sequence[OutputOutcome],
) -> DiagnosticLocalisation:
    """Walk one failed output backwards and return its confirmation or its interval."""
    subject = f"lineage.output_bindings[{output_id}]"
    if output_id not in bindings:
        raise _refuse(
            LocalisationRefusalReason.UNBOUND_OUTPUT,
            subject,
            "the definition binds no lineage terminal for the output",
        )
    observed = _observed_evidence(outcomes, output_id, subject)
    localisation_id = f"{lineage.lineage_id}/{output_id}"
    terminal_id = bindings[output_id]
    if terminal_id is None:
        # The definition places the output on no declared node, so no boundary
        # can be named and no interval can be drawn.
        return DiagnosticLocalisation(
            localisation_id=localisation_id,
            version=LOCALISATION_FORM,
            status=LocalisationStatus.UNKNOWN,
            lower_frontier=(),
            upper_frontier=(),
            uncovered_paths=(),
            supporting_evidence=observed,
        )
    if terminal_id not in declared:
        raise _refuse(
            LocalisationRefusalReason.UNRESOLVED_CHECKPOINT,
            subject,
            f"the binding names terminal checkpoint {terminal_id}, which is not declared",
        )

    ancestry = _ancestry(declared, terminal_id, subject)
    children: dict[str, set[str]] = {node: set() for node in ancestry}
    for node, parents in ancestry.items():
        for parent_id in parents:
            children[parent_id].add(node)
    verdict = {node: held[node].status if node in held else None for node in ancestry}
    compared = any(not _unresolved(status) for status in verdict.values())

    diverged = {node for node, status in verdict.items() if status is VerificationStatus.FAIL}
    first_diverged = tuple(sorted(node for node in diverged if not (_strict_ancestors(node, ancestry) & diverged)))
    confirmed_upper = bool(first_diverged)
    upper_ids = first_diverged if confirmed_upper else (terminal_id,)

    region = _uncovered_region(upper_ids, ancestry, verdict)
    interval = set(upper_ids) | region
    matched = tuple(
        sorted(
            node
            for node, status in verdict.items()
            if status is VerificationStatus.PASS and ((children[node] & interval) or node == terminal_id)
        )
    )
    confirmed_lower = bool(matched)
    lower_ids = matched if confirmed_lower else tuple(
        sorted(node for node in interval if not (set(ancestry[node]) & interval))
    )

    reason = UncoveredPathReason.MISSING_CHECKPOINT_EVIDENCE if compared else UncoveredPathReason.OUTPUT_ONLY
    paths = [
        UncoveredPath(
            path_id=f"{output_id}/{component[0]}",
            checkpoint_ids=component,
            reason=reason,
            evidence=observed,
        )
        for component in _components(region, ancestry)
    ]
    for node in sorted(interval):
        branches = tuple(sorted(parent_id for parent_id in ancestry[node] if parent_id in region))
        if len(branches) > 1:
            paths.append(
                UncoveredPath(
                    path_id=f"{output_id}/{node}/{BRANCH_PATH_SEGMENT}",
                    checkpoint_ids=branches,
                    reason=UncoveredPathReason.AMBIGUOUS_BRANCH,
                    evidence=observed,
                )
            )

    supporting = _distinct(
        (
            *observed,
            *(
                reference
                for node in (*upper_ids, *lower_ids)
                if node in held
                for reference in held[node].evidence
            ),
        ),
        subject,
    )
    status = (
        LocalisationStatus.CONFIRMED if confirmed_upper and not region else LocalisationStatus.INFERRED
    )
    return DiagnosticLocalisation(
        localisation_id=localisation_id,
        version=LOCALISATION_FORM,
        status=status,
        lower_frontier=_frontier(lower_ids, held, confirmed_lower, observed),
        upper_frontier=_frontier(upper_ids, held, confirmed_upper, observed),
        uncovered_paths=tuple(sorted(paths, key=lambda path: path.path_id)),
        supporting_evidence=supporting,
    )


def failed_outputs(lineage: LineageDefinition, outcomes: Sequence[OutputOutcome]) -> tuple[str, ...]:
    """Return the bound outputs whose reconciled outcome failed, in a stable order."""
    bindings = declared_bindings(lineage)
    failed: set[str] = set()
    for item in outcomes:
        if item.output_id not in bindings:
            raise _refuse(
                LocalisationRefusalReason.UNBOUND_OUTPUT,
                f"outcomes[{item.output_id}]",
                "the outcome answers for an output the definition does not bind",
            )
        if item.outcome.status is VerificationStatus.FAIL:
            failed.add(item.output_id)
    return tuple(sorted(failed))


def localise_output(
    lineage: LineageDefinition,
    output_id: str,
    *,
    outcomes: Sequence[OutputOutcome],
    comparisons: Sequence[CheckpointComparison],
) -> DiagnosticLocalisation:
    """Return the localisation of one failed output."""
    declared = declared_checkpoints(lineage)
    bindings = declared_bindings(lineage)
    held = _held_comparisons(comparisons, declared)
    return _localise(lineage, output_id, declared, bindings, held, tuple(outcomes))


def localise(
    lineage: LineageDefinition,
    *,
    outcomes: Sequence[OutputOutcome],
    comparisons: Sequence[CheckpointComparison],
) -> tuple[OutputLocalisation, ...]:
    """Return one localisation per failed output, in output order."""
    declared = declared_checkpoints(lineage)
    bindings = declared_bindings(lineage)
    held = _held_comparisons(comparisons, declared)
    material = tuple(outcomes)
    return tuple(
        OutputLocalisation(output_id, _localise(lineage, output_id, declared, bindings, held, material))
        for output_id in failed_outputs(lineage, material)
    )


__all__ = [
    "BRANCH_PATH_SEGMENT",
    "CheckpointComparison",
    "LOCALISATION_FORM",
    "LocalisationRefusalReason",
    "LocalisationRefused",
    "OutputLocalisation",
    "OutputOutcome",
    "compare_checkpoint",
    "declared_bindings",
    "declared_checkpoints",
    "failed_outputs",
    "localise",
    "localise_output",
]
