"""Isolated checkpoint replay that separates the explanations a localisation left open.

A localisation that reports an interval names the checkpoints it could not
separate. Each of those checkpoints is a competing explanation for the failure:
the divergence may have entered at any of them. This step tests those
explanations, one checkpoint at a time, and reports which the replay supports,
which it rules out, and which it could not separate at all.

A replay runs only where the case declares one. A checkpoint that declares a
replay specification names the frozen inputs it needs, the context it runs in
and the transformation it applies. The step gives the candidate runner exactly
those frozen inputs and nothing else, so the checkpoint is produced in
isolation from the rest of the run. A checkpoint that declares no replay is
left open, with the reason that no replay is declared for it.

The step does four things.

1. It localises the failed output through the deterministic core, which owns
   the walk, the boundaries and the uncovered paths.
2. It replays every checkpoint the localisation left uncovered, driving the
   candidate runner with the frozen inputs the replay declares and reading the
   output the replayed checkpoint names.
3. It compares each replayed state through the one checkpoint comparison the
   core owns, so a replay verdict is the same kind of fact as any other
   checkpoint comparison.
4. It localises again with those verdicts added, so the narrowed conclusion is
   the core's and this module reports rather than decides.

Refusals are integrity refusals: a replay declared for a checkpoint other than
its own, a required replay input the intake did not freeze, a runner that
refuses to produce outputs, a runner that answers with no output for the
replayed checkpoint, and any refusal the deterministic core raises. Nothing is
refused for the provenance a case declares or for the assurance it claims.

The module reads no file, no clock, no environment and no locale, and it draws
no random value.
"""
from __future__ import annotations

# evorthon-component: verification_workflows

from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import Enum

from evorthon_data.verification.core.localisation import (
    CheckpointComparison,
    OutputOutcome,
    compare_checkpoint,
    declared_checkpoints,
    localise_output,
)
from evorthon_data.verification.domain.contracts import (
    Checkpoint,
    DiagnosticLocalisation,
    EvidenceReference,
    LineageDefinition,
    ReplaySpecification,
    UncoveredPathReason,
    VerificationStatus,
)
from evorthon_data.verification.ports.contracts import (
    CandidateRunnerPort,
    FrozenCaseFacts,
    FrozenFact,
    PortRefusal,
    ProducedOutput,
)
from evorthon_data.verification.workflows.intake import AcceptedIntake

REPLAY_WORKFLOW_FORM = "evorthon.verification.replay.v1"


class ReplayRefusalReason(str, Enum):
    """The closed set of integrity reasons for refusing to replay a checkpoint."""

    REPLAY_CONTRADICTION = "replay-contradiction"
    REPLAY_INPUT_NOT_FROZEN = "replay-input-not-frozen"
    RUNNER_REFUSED = "runner-refused"
    REPLAY_OUTPUT_MISSING = "replay-output-missing"
    INTAKE_MISSING = "intake-missing"


class ReplayRefused(ValueError):
    """Raised when a replay cannot be run or read with declared meaning."""

    def __init__(self, reason: ReplayRefusalReason, subject: str, detail: str) -> None:
        super().__init__(f"{reason.value} at {subject}: {detail}")
        self.reason = reason
        self.subject = subject
        self.detail = detail


@dataclass(frozen=True)
class ReplayExplanation:
    """One competing explanation and what the replay did to it.

    ``status`` reads as the checkpoint comparison reads. A failure is a
    divergence the replay reproduced, so the explanation is supported. A pass is
    a state the replay reproduced correctly, so the explanation is ruled out.
    Insufficient evidence is an explanation the replay could not separate, and
    ``reason`` then states why.
    """

    checkpoint_id: str
    status: VerificationStatus
    reason: UncoveredPathReason | None
    evidence: tuple[EvidenceReference, ...]


@dataclass(frozen=True)
class ReplayReport:
    """Every explanation the replay tested, and the localisation that follows.

    ``localisation`` is the conclusion after the replay verdicts are added, and
    ``comparisons`` is every checkpoint comparison it rests on, the supplied
    ones and the replayed ones together.
    """

    output_id: str
    localisation: DiagnosticLocalisation
    explanations: tuple[ReplayExplanation, ...]
    comparisons: tuple[CheckpointComparison, ...]

    def _named(self, status: VerificationStatus) -> tuple[str, ...]:
        return tuple(
            explanation.checkpoint_id for explanation in self.explanations if explanation.status is status
        )

    @property
    def supported(self) -> tuple[str, ...]:
        """The checkpoints the replay confirmed as diverging."""
        return self._named(VerificationStatus.FAIL)

    @property
    def ruled_out(self) -> tuple[str, ...]:
        """The checkpoints the replay reproduced correctly."""
        return self._named(VerificationStatus.PASS)

    @property
    def left_open(self) -> tuple[str, ...]:
        """The checkpoints the replay could not separate."""
        return self._named(VerificationStatus.INSUFFICIENT_EVIDENCE)


def _refuse(reason: ReplayRefusalReason, subject: str, detail: str) -> ReplayRefused:
    return ReplayRefused(reason, subject, detail)


def _frozen_input_facts(
    replay: ReplaySpecification, facts: FrozenCaseFacts, subject: str
) -> tuple[FrozenFact, ...]:
    """Return the frozen facts the declared replay inputs name, in declared order."""
    held = {(fact.fact_id, fact.subject): fact for fact in facts.facts}
    selected: list[FrozenFact] = []
    for replay_input in replay.inputs:
        fact = held.get((replay_input.dataset_id, replay_input.role.value))
        if fact is None:
            if replay_input.required:
                raise _refuse(
                    ReplayRefusalReason.REPLAY_INPUT_NOT_FROZEN,
                    subject,
                    f"the replay requires input {replay_input.dataset_id}, which intake did not freeze",
                )
            continue
        selected.append(fact)
    return tuple(selected)


def isolated_facts(replay: ReplaySpecification, facts: FrozenCaseFacts, subject: str) -> FrozenCaseFacts:
    """Return the frozen surface one replay receives: its declared inputs and its context.

    The case identity is the one intake accepted, because a replay of a
    checkpoint is part of that case and not a case of its own. Everything the
    replay does not declare is left out, which is what makes the run isolated.
    """
    return replace(
        facts,
        context_id=replay.context.context_id,
        context_version=replay.context.version,
        context_digest=replay.context.digest,
        logical_run_time=replay.context.logical_run_time,
        cutoff_time=replay.context.cutoff_time,
        timezone=replay.context.timezone,
        facts=_frozen_input_facts(replay, facts, subject),
    )


def _replay_evidence(checkpoint_id: str, produced: ProducedOutput) -> EvidenceReference:
    """Return the evidence reference that stands for one replayed state."""
    return EvidenceReference(
        evidence_id=f"{checkpoint_id}/replay",
        version=REPLAY_WORKFLOW_FORM,
        digest=produced.content_digest,
        summary="the state an isolated replay of the declared checkpoint produced",
    )


def _produced_for(
    runner: CandidateRunnerPort, facts: FrozenCaseFacts, checkpoint_id: str, subject: str
) -> ProducedOutput:
    """Return the output the runner produced for one replayed checkpoint."""
    try:
        produced = runner.produce_outputs(facts)
    except PortRefusal as refusal:
        raise _refuse(
            ReplayRefusalReason.RUNNER_REFUSED,
            subject,
            f"the runner refused to replay the checkpoint from its frozen inputs: {refusal}",
        ) from None
    if not isinstance(produced, tuple) or any(not isinstance(item, ProducedOutput) for item in produced):
        raise _refuse(
            ReplayRefusalReason.REPLAY_OUTPUT_MISSING,
            subject,
            "the runner answered with something other than declared produced outputs",
        )
    for item in produced:
        if item.output_id == checkpoint_id:
            return item
    raise _refuse(
        ReplayRefusalReason.REPLAY_OUTPUT_MISSING,
        subject,
        "the runner declared no produced output for the replayed checkpoint",
    )


def replay_checkpoint(
    checkpoint: Checkpoint,
    intake: AcceptedIntake,
    *,
    candidate_runner: CandidateRunnerPort,
) -> CheckpointComparison:
    """Replay one declared checkpoint in isolation and return its comparison."""
    subject = f"lineage.checkpoints[{checkpoint.checkpoint_id}].replay"
    if not isinstance(intake, AcceptedIntake):
        raise _refuse(
            ReplayRefusalReason.INTAKE_MISSING,
            subject,
            "an accepted intake is required before a checkpoint can be replayed",
        )
    replay = checkpoint.replay
    if replay is None or replay.checkpoint_id != checkpoint.checkpoint_id:
        raise _refuse(
            ReplayRefusalReason.REPLAY_CONTRADICTION,
            subject,
            "a replay runs only where the checkpoint declares one for itself",
        )
    facts = isolated_facts(replay, intake.candidate_facts, subject)
    produced = _produced_for(candidate_runner, facts, checkpoint.checkpoint_id, subject)
    return compare_checkpoint(checkpoint, produced.content_digest, (_replay_evidence(checkpoint.checkpoint_id, produced),))


def _competing(localisation: DiagnosticLocalisation) -> tuple[str, ...]:
    """Return the checkpoints the localisation left open, in a stable order."""
    named: list[str] = []
    for path in localisation.uncovered_paths:
        named.extend(path.checkpoint_ids)
    return tuple(sorted(set(named)))


def replay_localisation(
    lineage: LineageDefinition,
    intake: AcceptedIntake,
    output_id: str,
    *,
    outcomes: Sequence[OutputOutcome],
    comparisons: Sequence[CheckpointComparison],
    candidate_runner: CandidateRunnerPort,
) -> ReplayReport:
    """Replay the competing explanations of one failed output and report what changed.

    A localisation with nothing left open needs no replay, and the report then
    carries the same localisation and no explanation.
    """
    declared = declared_checkpoints(lineage)
    held = tuple(comparisons)
    material = tuple(outcomes)
    localisation = localise_output(lineage, output_id, outcomes=material, comparisons=held)
    explanations: list[ReplayExplanation] = []
    replayed: list[CheckpointComparison] = []
    for checkpoint_id in _competing(localisation):
        checkpoint = declared[checkpoint_id]
        if checkpoint.replay is None:
            explanations.append(
                ReplayExplanation(
                    checkpoint_id=checkpoint_id,
                    status=VerificationStatus.INSUFFICIENT_EVIDENCE,
                    reason=UncoveredPathReason.REPLAY_NOT_DECLARED,
                    evidence=(),
                )
            )
            continue
        comparison = replay_checkpoint(checkpoint, intake, candidate_runner=candidate_runner)
        replayed.append(comparison)
        explanations.append(
            ReplayExplanation(
                checkpoint_id=checkpoint_id,
                status=comparison.status,
                reason=None,
                evidence=comparison.evidence,
            )
        )
    total = (*held, *replayed)
    return ReplayReport(
        output_id=output_id,
        localisation=localise_output(lineage, output_id, outcomes=material, comparisons=total),
        explanations=tuple(explanations),
        comparisons=total,
    )


__all__ = [
    "REPLAY_WORKFLOW_FORM",
    "ReplayExplanation",
    "ReplayRefusalReason",
    "ReplayRefused",
    "ReplayReport",
    "isolated_facts",
    "replay_checkpoint",
    "replay_localisation",
]
