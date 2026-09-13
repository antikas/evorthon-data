"""The two rules every reference adapter answers by, written once.

A reference adapter holds material and answers from it. Where the material
sits differs between the in-memory family and the fixture family, but what
counts as an answer does not, so both rules live here and neither family
repeats them.

An evidence reference is answered only when the held material carries that
exact identity and version. Anything else is refused as not held. The refusal
names no value at all: not the reference that was asked for and not where the
material sits. A caller can ask with any text it likes, and a refusal that
repeated the question back would carry that text onward, which is how a route
to somebody's machine ends up inside a record that had no reason to hold one.

Declared outputs are replayed only for the case identity and version the frozen
facts carry, and only when the case digest in those facts is the digest the
outputs were frozen against. The rule reads the identity, the version and the
digest, and nothing else in the facts, so a runner built on it cannot reach for
material the approved case does not declare. A contradiction refuses; it never
answers with the outputs of a different case and never answers with nothing.
"""
from __future__ import annotations

# evorthon-component: verification_adapters

from collections.abc import Sequence
from dataclasses import dataclass

from evorthon_data.verification.ports.contracts import (
    EvidenceNotHeld,
    FrozenCaseFacts,
    PortRefusal,
    ProducedOutput,
    StoredEvidence,
)


# What a refusal says. Each names the rule that refused and no value, so a
# refusal carries nothing onward that a caller or an environment supplied.
NOT_HELD = "the repository does not hold the requested evidence reference"
FACTS_UNREADABLE = "the runner received no frozen case facts to produce outputs from"
NO_DECLARED_OUTPUTS = "the runner holds no declared outputs for the case identity and version it received"
FACTS_CONTRADICT_DECLARATION = (
    "the frozen facts carry a case digest the declared outputs were not frozen against"
)


@dataclass(frozen=True)
class ReplayDeclaration:
    """The outputs one candidate is declared to produce for one frozen case.

    The declaration names the case it answers for by identity, version and
    digest. It carries no location, no route to a running source system and
    nothing of the case beyond those three facts.
    """

    case_id: str
    case_version: str
    case_digest: str
    outputs: tuple[ProducedOutput, ...]


def held_record(
    records: Sequence[StoredEvidence], evidence_id: str, version: str
) -> StoredEvidence:
    """Return the held record for one reference, or refuse as not held."""
    for record in records:
        if record.evidence_id == evidence_id and record.version == version:
            return record
    raise EvidenceNotHeld(NOT_HELD)


def replayed_outputs(
    declarations: Sequence[ReplayDeclaration], facts: FrozenCaseFacts
) -> tuple[ProducedOutput, ...]:
    """Return the declared outputs for the frozen facts, or refuse."""
    if not isinstance(facts, FrozenCaseFacts):
        raise PortRefusal(FACTS_UNREADABLE)
    for declaration in declarations:
        if declaration.case_id == facts.case_id and declaration.case_version == facts.case_version:
            if declaration.case_digest != facts.case_digest:
                raise PortRefusal(FACTS_CONTRADICT_DECLARATION)
            return tuple(declaration.outputs)
    raise PortRefusal(NO_DECLARED_OUTPUTS)


__all__ = [
    "FACTS_CONTRADICT_DECLARATION",
    "FACTS_UNREADABLE",
    "NOT_HELD",
    "NO_DECLARED_OUTPUTS",
    "ReplayDeclaration",
    "held_record",
    "replayed_outputs",
]
