"""What an environment adapter says about itself when it crosses a port.

An adapter answers a port contract. This record is how it says which contract
it answers, what it can do, and how much its answers are worth. It is
labelling: it names what an adopter claims, and the conformance suite refuses
only a claim that contradicts what the port shows.

Three things are declared here and nowhere else in this package.

The port contract version an adapter implements is the one the ports declare.
An adapter that names any other version is answering a contract this product
does not offer, so the suite refuses it rather than reading it.

The capabilities are a closed set. Four of them name what the suite can watch
happen: replaying declared outputs, reading held evidence, and the two places
an adapter can hold the material it answers from. A fifth names the one
environment input an adapter may name across the port, a certificate it can
cite. Signing and retention have no name in this set at all, because they stay
on the environment's own side and nothing about them crosses a read surface; an
adapter that invents a name for one is refused as an unknown capability.

The assurance is one of exactly three strings. The verification domain owns
those three words, and this package may not import the domain, so the strings
are declared here and a test asserts that this set equals the domain's own. An
assurance above the plainest of the three is a claim about an input, so it
holds only when the adapter can name the input it rests on.

Nothing here reads a location, a credential or any stored material. The record
carries identities and words, and the conformance suite reads every one of them
against the one owner of the machine-route and credential shapes.
"""
from __future__ import annotations

# evorthon-component: verification_adapters

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from evorthon_data.verification.ports.contracts import PORT_CONTRACT_VERSION


# What an adapter can do, named once. A capability is observed across the port
# or it is not declared.
REPLAYS_DECLARED_OUTPUTS = "replays-declared-outputs"
READS_HELD_EVIDENCE = "reads-held-evidence"
HOLDS_MATERIAL_IN_MEMORY = "holds-material-in-memory"
HOLDS_MATERIAL_ON_A_FILE_SYSTEM = "holds-material-on-a-file-system"
PRESENTS_A_CERTIFICATE = "presents-a-certificate"

ADAPTER_CAPABILITIES: tuple[str, ...] = (
    REPLAYS_DECLARED_OUTPUTS,
    READS_HELD_EVIDENCE,
    HOLDS_MATERIAL_IN_MEMORY,
    HOLDS_MATERIAL_ON_A_FILE_SYSTEM,
    PRESENTS_A_CERTIFICATE,
)

# Where an adapter keeps what it answers from. A port shows that material is
# held, never which side of the machine holds it, so one adapter names one
# place and naming both is a contradiction the suite refuses.
HOLDING_CAPABILITIES: tuple[str, ...] = (
    HOLDS_MATERIAL_IN_MEMORY,
    HOLDS_MATERIAL_ON_A_FILE_SYSTEM,
)

# The three assurance words the verification domain owns. This package cannot
# import the domain, so the set is restated here and pinned to it by a test.
DECLARED_ASSURANCE = "declared"
OWNER_PRESENTED_ASSURANCE = "owner-presented"
ENVIRONMENT_CERTIFIED_ASSURANCE = "environment-certified"

ASSURANCE_LEVELS: tuple[str, ...] = (
    DECLARED_ASSURANCE,
    OWNER_PRESENTED_ASSURANCE,
    ENVIRONMENT_CERTIFIED_ASSURANCE,
)

# The assurance words that rest on an input, and the field that has to name it.
ASSURANCE_INPUT_FIELDS: tuple[tuple[str, str], ...] = (
    (OWNER_PRESENTED_ASSURANCE, "owner_presented_inputs"),
    (ENVIRONMENT_CERTIFIED_ASSURANCE, "environment_certificates"),
)


@dataclass(frozen=True)
class AdapterDeclaration:
    """What one adapter says it is, answers, can do and is worth.

    ``owner_presented_inputs`` and ``environment_certificates`` name inputs the
    environment holds. They carry identities only: the input itself, the
    certificate itself and wherever either is kept never cross the port.
    """

    adapter_id: str
    version: str
    port_contract_version: str = PORT_CONTRACT_VERSION
    capabilities: tuple[str, ...] = ()
    assurance: str = DECLARED_ASSURANCE
    owner_presented_inputs: tuple[str, ...] = field(default_factory=tuple)
    environment_certificates: tuple[str, ...] = field(default_factory=tuple)


@runtime_checkable
class AdapterDeclarationPort(Protocol):
    """The one method every adapter adds to the port contract it answers."""

    def declare_adapter(self) -> AdapterDeclaration:
        """Return what this adapter says about itself."""


__all__ = [
    "ADAPTER_CAPABILITIES",
    "ASSURANCE_INPUT_FIELDS",
    "ASSURANCE_LEVELS",
    "AdapterDeclaration",
    "AdapterDeclarationPort",
    "DECLARED_ASSURANCE",
    "ENVIRONMENT_CERTIFIED_ASSURANCE",
    "HOLDING_CAPABILITIES",
    "HOLDS_MATERIAL_IN_MEMORY",
    "HOLDS_MATERIAL_ON_A_FILE_SYSTEM",
    "OWNER_PRESENTED_ASSURANCE",
    "PRESENTS_A_CERTIFICATE",
    "READS_HELD_EVIDENCE",
    "REPLAYS_DECLARED_OUTPUTS",
]
