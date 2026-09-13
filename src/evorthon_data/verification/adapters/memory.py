"""Reference adapters that answer from material held in memory.

These two adapters are built from plain values and hold them for the life of
the object. They are the smallest honest implementation of each port contract:
an adopter reads them to see what a conforming adapter looks like, runs them
under the conformance suite, and drives a real intake with them before any
environment of their own is wired.

They hold what they are given and nothing else. Neither reads a file, a clock,
an environment variable or a network, so neither has a location, a credential,
a retention rule or a certificate to keep, and neither declares a capability
that would imply one. Both declare the plainest assurance, because material
handed to a constructor is declared material and no more than that.
"""
from __future__ import annotations

# evorthon-component: verification_adapters

from collections.abc import Sequence

from evorthon_data.verification.adapters.declaration import (
    AdapterDeclaration,
    DECLARED_ASSURANCE,
    HOLDS_MATERIAL_IN_MEMORY,
    READS_HELD_EVIDENCE,
    REPLAYS_DECLARED_OUTPUTS,
)
from evorthon_data.verification.adapters.material import (
    ReplayDeclaration,
    held_record,
    replayed_outputs,
)
from evorthon_data.verification.ports.contracts import (
    CandidateDeclaration,
    FrozenCaseFacts,
    PortRefusal,
    PORT_CONTRACT_VERSION,
    ProducedOutput,
    StoredEvidence,
)


IN_MEMORY_EVIDENCE_ADAPTER_ID = "reference-in-memory-evidence-repository"
IN_MEMORY_CANDIDATE_ADAPTER_ID = "reference-in-memory-candidate-runner"
REFERENCE_ADAPTER_VERSION = "v1"

NO_CANDIDATE_DECLARED = "the runner was built with no candidate declaration to answer for"


class InMemoryEvidenceRepository:
    """An evidence repository over records held in memory."""

    def __init__(
        self,
        records: Sequence[StoredEvidence] = (),
        *,
        adapter_id: str = IN_MEMORY_EVIDENCE_ADAPTER_ID,
        version: str = REFERENCE_ADAPTER_VERSION,
    ):
        self._records = tuple(records)
        self._adapter_id = adapter_id
        self._version = version

    def declare_adapter(self) -> AdapterDeclaration:
        """Return what this adapter says about itself."""
        return AdapterDeclaration(
            adapter_id=self._adapter_id,
            version=self._version,
            port_contract_version=PORT_CONTRACT_VERSION,
            capabilities=(READS_HELD_EVIDENCE, HOLDS_MATERIAL_IN_MEMORY),
            assurance=DECLARED_ASSURANCE,
        )

    def read_evidence(self, evidence_id: str, version: str) -> StoredEvidence:
        """Return the held record for one reference, or refuse as not held."""
        return held_record(self._records, evidence_id, version)


class InMemoryCandidateRunner:
    """A candidate runner that replays declared outputs held in memory."""

    def __init__(
        self,
        candidate: CandidateDeclaration | None = None,
        replays: Sequence[ReplayDeclaration] = (),
        *,
        adapter_id: str = IN_MEMORY_CANDIDATE_ADAPTER_ID,
        version: str = REFERENCE_ADAPTER_VERSION,
    ):
        self._candidate = candidate
        self._replays = tuple(replays)
        self._adapter_id = adapter_id
        self._version = version

    def declare_adapter(self) -> AdapterDeclaration:
        """Return what this adapter says about itself."""
        return AdapterDeclaration(
            adapter_id=self._adapter_id,
            version=self._version,
            port_contract_version=PORT_CONTRACT_VERSION,
            capabilities=(REPLAYS_DECLARED_OUTPUTS, HOLDS_MATERIAL_IN_MEMORY),
            assurance=DECLARED_ASSURANCE,
        )

    def declare_candidate(self) -> CandidateDeclaration:
        """Return the candidate artefact this runner produces outputs from."""
        if not isinstance(self._candidate, CandidateDeclaration):
            raise PortRefusal(NO_CANDIDATE_DECLARED)
        return self._candidate

    def produce_outputs(self, facts: FrozenCaseFacts) -> tuple[ProducedOutput, ...]:
        """Return the declared outputs for the frozen facts, or refuse."""
        return replayed_outputs(self._replays, facts)


__all__ = [
    "IN_MEMORY_CANDIDATE_ADAPTER_ID",
    "IN_MEMORY_EVIDENCE_ADAPTER_ID",
    "InMemoryCandidateRunner",
    "InMemoryEvidenceRepository",
    "NO_CANDIDATE_DECLARED",
    "REFERENCE_ADAPTER_VERSION",
]
