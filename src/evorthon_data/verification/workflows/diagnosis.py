"""Diagnosis of one failed output, from a reconciled run to a gated packet.

Reconciliation says that an output did not reproduce. Diagnosis says what the
evidence of that failure supports: which class of fault it shows, where the
declared lineage places it, and what the smallest record is that may leave the
product. Every one of those answers is already owned elsewhere. This module
composes them in the one order they belong in and returns what they decided.

The step does four things.

1. It reads the reconciled clauses as outcomes named by the output each one
   answers for. A reconciled clause already carries both, so nothing here
   decides which output an outcome belongs to.
2. It localises the failed output through the replay workflow, which replays
   the competing explanations the localisation left open and returns the
   localisation those verdicts support together with every comparison it rests
   on.
3. It builds the investigation packet through the deterministic core, which
   owns the fault vocabulary, the classification order, the calibrated
   confidence and the disclosure decision.
4. It reads the packet in full through the one privacy gate, which refuses a
   packet that carries anything no packet may carry. The disclosure decision
   the core made is left on the record and reported as it stands, because a
   withheld packet is a completed diagnosis and not a failure to diagnose. The
   decision is applied where a packet would cross to an adviser, by the same
   gate, which is the one place it means a refusal.

No advice is asked for here. An adviser needs an environment-provided egress
port and the authorization that goes with it, and neither is a thing this
module may reach for, so ``advice`` is always absent and a caller reports it as
not requested rather than as unavailable.

Refusals are the refusals the owners raise: a localisation the declared lineage
cannot support, an output the run does not report as failed, and a packet that
carries something no packet may carry. Nothing is refused for a declared
provenance, a synthetic label, a claimed assurance or a disclosure decision:
each of those is reported and left to the reader.
"""
from __future__ import annotations

# evorthon-component: verification_workflows

from collections.abc import Mapping
from dataclasses import dataclass

from evorthon_data.verification.core.fault import (
    FaultEvidence,
    build_fault_packet,
    declare_confidence,
    packet_fields,
)
from evorthon_data.verification.core.localisation import OutputOutcome
from evorthon_data.verification.enforcement.privacy import (
    PRIVACY_GATE_FORM,
    inspect_fault_packet,
)
from evorthon_data.verification.ports.contracts import CandidateRunnerPort
from evorthon_data.verification.workflows.intake import AcceptedIntake
from evorthon_data.verification.workflows.reconciliation import ReconciliationOutcome
from evorthon_data.verification.workflows.replay import replay_localisation

DIAGNOSIS_WORKFLOW_FORM = "evorthon.verification.diagnosis.v1"


@dataclass(frozen=True)
class DiagnosisOutcome:
    """One diagnosed output: the packet the gate read and what the evidence supports.

    ``fields`` is the packet as declared text, which the core writes and which
    holds names, counts and opaque digests only. The packet carries the core's
    own disclosure decision, so a caller reads there whether the packet may be
    carried onward and reports the rest under that decision. ``advice`` is
    always absent, because this step asks no adviser anything.
    """

    output_id: str
    packet: object
    gate: str
    fault_class: object
    confidence: object
    localisation_status: object
    replayed: tuple[str, ...]
    ruled_out: tuple[str, ...]
    fields: Mapping[str, str]
    advice: object = None


def diagnose_failed_output(
    case,
    intake: AcceptedIntake,
    reconciliation: ReconciliationOutcome,
    *,
    output_id: str,
    candidate_runner: CandidateRunnerPort,
) -> DiagnosisOutcome:
    """Return the gated investigation packet for one output a run reports as failed."""
    outcomes = tuple(
        OutputOutcome(clause.output_id, clause.outcome) for clause in reconciliation.clauses
    )
    report = replay_localisation(
        case.lineage,
        intake,
        output_id,
        outcomes=outcomes,
        comparisons=(),
        candidate_runner=candidate_runner,
    )
    evidence = FaultEvidence(
        case=case,
        result=reconciliation.result,
        output_id=output_id,
        findings=reconciliation.findings,
        localisation=report.localisation,
        checkpoint_comparisons=report.comparisons,
    )
    packet = inspect_fault_packet(build_fault_packet(evidence))
    return DiagnosisOutcome(
        output_id=output_id,
        packet=packet,
        gate=PRIVACY_GATE_FORM,
        fault_class=packet.fault_class,
        confidence=declare_confidence(evidence),
        localisation_status=report.localisation.status,
        replayed=report.supported,
        ruled_out=report.ruled_out,
        fields=packet_fields(packet),
    )


__all__ = [
    "DIAGNOSIS_WORKFLOW_FORM",
    "DiagnosisOutcome",
    "diagnose_failed_output",
]
