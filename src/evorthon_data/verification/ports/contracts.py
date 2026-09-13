"""Environment-owned access contracts for a verification run.

This module is the boundary between the portable verification code and the
environment that holds candidate artefacts and stored evidence. It imports
nothing else of the product, so an adopter can implement these contracts
without taking on the domain, the deterministic core or any workflow. Every
fact a contract carries is therefore a plain value: an identity, a version, a
digest, a declared instant or the stored bytes themselves. A workflow prepares
those values from an approved case and reads them back here.

Two contracts are declared.

A candidate runner receives frozen case facts and produces outputs from them.
The facts it receives are frozen: identities, declared bindings and digests
taken from an approved case. The contract offers no address, no credential, no
route to a running source system and no observation of a live run, because a
routine verification compares an approved frozen expectation against a
candidate and never reaches for the system being replaced. An expected output
is never handed over: it is the oracle a result is measured against, so giving
it to a candidate would let the candidate answer with the answer.

An evidence repository reads evidence records the environment already holds. It
answers with the stored bytes and with the record's own declared facts, and a
reference it does not hold is refused rather than answered with an empty value,
so a caller can never mistake absence for a valid empty record. The caller
recomputes every digest for itself, so a declared digest here is a claim to be
checked and never a fact to be trusted.

Neither contract exposes any way to change stored material. Both are read
surfaces, and an implementation that needs locations, credentials, retention or
certificates keeps them on its own side of this boundary.
"""
# evorthon-implements: EVD-README-021
from __future__ import annotations

# evorthon-component: verification_ports

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


PORT_CONTRACT_VERSION = "evorthon.verification.ports.v1"

# The declared bindings a frozen fact carries. A binding names a declaration
# and its digest; it never restates the declaration's content.
SCHEMA_BINDING = "schema"
GRAIN_BINDING = "grain"
CANONICALISATION_BINDING = "canonicalisation"
BINDING_KINDS = (SCHEMA_BINDING, GRAIN_BINDING, CANONICALISATION_BINDING)


@dataclass(frozen=True)
class FactBinding:
    """One declaration bound to a frozen fact: what it is and which bytes it has."""

    binding_kind: str
    binding_id: str
    version: str
    digest: str


@dataclass(frozen=True)
class FrozenFact:
    """One frozen case fact a candidate may read, with its declared bindings."""

    subject: str
    fact_id: str
    version: str
    content_digest: str
    row_count: int
    bindings: tuple[FactBinding, ...]


@dataclass(frozen=True)
class FrozenCaseFacts:
    """The complete frozen surface one candidate run receives.

    The surface carries the case identity, the declared run context and one
    entry per frozen case fact. It carries no expected output, no location and
    no material outside the approved case.
    """

    case_id: str
    case_version: str
    case_digest: str
    context_id: str
    context_version: str
    context_digest: str
    logical_run_time: str
    cutoff_time: str
    timezone: str
    facts: tuple[FrozenFact, ...]


@dataclass(frozen=True)
class CandidateDeclaration:
    """The exact candidate artefact an environment offers for a run."""

    candidate_id: str
    version: str
    artifact_digest: str


@dataclass(frozen=True)
class ProducedOutput:
    """One output a candidate produced from the frozen facts it was given."""

    output_id: str
    version: str
    content_digest: str
    format_digest: str
    row_count: int


@dataclass(frozen=True)
class StoredEvidence:
    """One evidence record as an environment holds it.

    ``declared_digest`` is the environment's own claim about ``content``, and
    ``recorded_at`` and ``valid_until`` are the environment's own declaration
    of when the record holds. A caller checks all three rather than adopting
    them.
    """

    evidence_id: str
    version: str
    content: bytes
    declared_digest: str
    recorded_at: str
    valid_until: str
    summary: str


class PortRefusal(ValueError):
    """Raised when an environment contract cannot answer with declared meaning."""


class EvidenceNotHeld(PortRefusal):
    """Raised when an evidence repository does not hold a requested reference."""


@runtime_checkable
class CandidateRunnerPort(Protocol):
    """The environment contract that produces candidate outputs from frozen facts."""

    def declare_candidate(self) -> CandidateDeclaration:
        """Return the exact candidate artefact this runner produces outputs from."""

    def produce_outputs(self, facts: FrozenCaseFacts) -> tuple[ProducedOutput, ...]:
        """Return the outputs the candidate produces from the given frozen facts.

        The frozen facts are the whole input. An implementation that cannot
        produce outputs from them alone raises ``PortRefusal`` rather than
        reaching for material the approved case does not declare.
        """


@runtime_checkable
class EvidenceRepositoryPort(Protocol):
    """The environment contract that reads evidence records already held."""

    def read_evidence(self, evidence_id: str, version: str) -> StoredEvidence:
        """Return the stored evidence record for one declared reference.

        An implementation that does not hold the reference raises
        ``EvidenceNotHeld``. It never answers with an empty value, so absence
        can never be read as a valid empty record.
        """


__all__ = [
    "BINDING_KINDS",
    "CANONICALISATION_BINDING",
    "CandidateDeclaration",
    "CandidateRunnerPort",
    "EvidenceNotHeld",
    "EvidenceRepositoryPort",
    "FactBinding",
    "FrozenCaseFacts",
    "FrozenFact",
    "GRAIN_BINDING",
    "PORT_CONTRACT_VERSION",
    "PortRefusal",
    "ProducedOutput",
    "SCHEMA_BINDING",
    "StoredEvidence",
]
