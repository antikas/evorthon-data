"""The one gate a fault packet passes before it may reach an adviser boundary.

This module is the single owner of the rule that decides whether a fault packet
may leave the product. It reads one packet and nothing else: no case, no rows,
no environment and no provider. It changes nothing, it asks nothing, and it
either returns the packet as gated or refuses it with a closed reason.

A packet is refused for one of two kinds of reason. An integrity refusal says
the record is not a packet this gate can read: a record of the wrong form, an
empty required declaration, or a packet whose class and disclosure decision
contradict each other. A privacy refusal says the packet carries something that
must never cross a boundary.

The privacy rules are these, checked in this order over every declared text and
every declared digest of the packet. The shapes a machine route, a credential
and a raw row are read by belong to one owner that every boundary of this
product reads, so no two boundaries can disagree about what one of them is.
The reasons and the messages below stay here, because what a carried shape
means at this boundary is this gate's to say.

* A local path. Every machine-route shape the product declares: a drive path
  with or without a separator after it, a network share path and its host on
  its own, a user-home path, an absolute path in either reading, a local file
  address, a web address, an address under any other scheme, a traversal at the
  start of a value or anywhere inside it, or a relative path written with a
  machine path's separator. A packet's declared text is one value this product
  wrote, not a page of prose, so the declared-value readings apply here. A fault
  locator is logical, so a packet that carries a location on somebody's machine,
  or an address that would reach one, is carrying the environment.
* A credential. Every credential shape the product declares: a named secret, a
  named key, a presented authorization token, the opening line of a stored key
  block of any kind, a
  secret with a value written against it, a user and secret written inside an
  address, or a token written against the header that carries it.
* A raw row. A written record rather than a sentence: a control character, a
  written object with quoted field names, or a run of delimited fields.
* A singleton value. A written observation of one subject: a date, a
  timestamp, a decimal, a quoted literal, or a value written against a name.
  These are the shapes a value takes when it is written into a sentence, and
  they are what this rule refuses. A whole number stays allowed, because a
  packet describes its scope by counting it, and so does a declared name,
  because clause, output and checkpoint identities are how a packet says what
  it is about. That is the honest limit of the rule: a bare word or a bare
  whole number cannot be told apart from a name or a count by reading it, so
  this gate does not claim to. What closes the remaining gap is the packet
  builder, whose only free text is a scope written from a closed template of
  declared names and counts and evidence summaries drawn from a closed set, so
  no observation reaches this text in the first place.
* A reversible digest. A digest slot that is not an opaque fingerprint of fixed
  width under a named algorithm. A digest over one value, or over a set small
  enough to enumerate, is readable by anyone who can try the inputs, so this
  gate accepts a fingerprint and refuses everything else in a digest slot.

Two further rules complete the boundary. A packet must fit the declared maximum
shape, which bounds how many clause outcomes, evidence references, lineage
boundaries and uncovered paths it carries and how long each declared text may
be; a packet larger than that is refused rather than trimmed. And a packet
whose disclosure decision is anything other than disclose does not cross: the
decision is made by the policy that counted the packet's scope, and this gate
carries it out. A packet withheld here still exists for the people who own the
case; only the boundary is closed.

Nothing is refused here for being synthetic, derived, inferred or weak. Those
declarations change what a reader should conclude, never whether the packet may
be read.
"""
# evorthon-implements: EVD-README-021
from __future__ import annotations

# evorthon-component: verification_enforcement

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from evorthon_data.boundary_patterns import (
    CREDENTIAL_PATTERNS as DECLARED_CREDENTIAL_PATTERNS,
)
from evorthon_data.boundary_patterns import (
    CREDENTIAL_SHAPES,
    MACHINE_ROUTE_PATTERNS,
    MACHINE_ROUTE_SHAPES,
    RAW_ROW_SHAPES,
    shape_carried,
    shapes,
)
from evorthon_data.boundary_patterns import (
    RAW_ROW_PATTERNS as DECLARED_RAW_ROW_PATTERNS,
)
from evorthon_data.verification.domain.contracts import (
    DisclosureDecision,
    EvidenceReference,
    FaultClass,
    FaultRecord,
)

PRIVACY_GATE_FORM = "evorthon.verification.privacy-gate.v1"

_MARK = chr(58)
_TRIM = ";,.()"


@dataclass(frozen=True)
class PacketBounds:
    """The declared maximum shape a packet may carry across the boundary."""

    affected_clause_outcomes: int
    evidence_references: int
    frontier_checkpoints: int
    uncovered_paths: int
    checkpoints_per_path: int
    identifier_characters: int
    text_characters: int


PACKET_BOUNDS = PacketBounds(
    affected_clause_outcomes=16,
    evidence_references=16,
    frontier_checkpoints=16,
    uncovered_paths=16,
    checkpoints_per_path=32,
    identifier_characters=128,
    text_characters=320,
)

# A packet's declared text is one value this product wrote, so this gate reads
# every machine-route, credential and raw-row shape the product declares. The
# shapes are owned in one place; the refusal reasons below are this gate's own.
LOCAL_PATH_PATTERNS = shapes(MACHINE_ROUTE_PATTERNS, MACHINE_ROUTE_SHAPES)
CREDENTIAL_PATTERNS = shapes(DECLARED_CREDENTIAL_PATTERNS, CREDENTIAL_SHAPES)
RAW_ROW_PATTERNS = shapes(DECLARED_RAW_ROW_PATTERNS, RAW_ROW_SHAPES)
# A written observation of one subject is not a shape another boundary reads:
# the public scan reads shipped text full of dates and decimals, the tracker
# adapter reads counted notes, and intake reads an adopter's own artefact. So
# these shapes stay here, with the rule that refuses them.
VALUE_LITERAL_PATTERNS = (
    re.compile(r"^\d{4}-\d{2}-\d{2}"),
    re.compile(r"^\d+[.,]\d+$"),
    re.compile(r"[\"']"),
    re.compile(r"="),
)
FINGERPRINT = re.compile(r"^[a-z][a-z0-9-]*" + _MARK + "[0-9a-f]{64}$")


class PrivacyRefusalKind(str, Enum):
    """Whether a refusal defends the record's meaning or the data behind it."""

    INTEGRITY = "integrity"
    PRIVACY = "privacy"


class PrivacyRefusalReason(str, Enum):
    """The closed set of reasons this gate refuses a packet."""

    UNRESOLVED_PACKET = "unresolved-packet"
    CONTRADICTORY_PACKET = "contradictory-packet"
    DECLARED_BOUND_EXCEEDED = "declared-bound-exceeded"
    LOCAL_PATH = "local-path"
    CREDENTIAL = "credential"
    RAW_ROW = "raw-row"
    SINGLETON_VALUE = "singleton-value"
    REVERSIBLE_DIGEST = "reversible-digest"
    DISCLOSURE_WITHHELD = "disclosure-withheld"


REFUSAL_KIND = MappingProxyType(
    {
        PrivacyRefusalReason.UNRESOLVED_PACKET: PrivacyRefusalKind.INTEGRITY,
        PrivacyRefusalReason.CONTRADICTORY_PACKET: PrivacyRefusalKind.INTEGRITY,
        PrivacyRefusalReason.DECLARED_BOUND_EXCEEDED: PrivacyRefusalKind.PRIVACY,
        PrivacyRefusalReason.LOCAL_PATH: PrivacyRefusalKind.PRIVACY,
        PrivacyRefusalReason.CREDENTIAL: PrivacyRefusalKind.PRIVACY,
        PrivacyRefusalReason.RAW_ROW: PrivacyRefusalKind.PRIVACY,
        PrivacyRefusalReason.SINGLETON_VALUE: PrivacyRefusalKind.PRIVACY,
        PrivacyRefusalReason.REVERSIBLE_DIGEST: PrivacyRefusalKind.PRIVACY,
        PrivacyRefusalReason.DISCLOSURE_WITHHELD: PrivacyRefusalKind.PRIVACY,
    }
)
if frozenset(REFUSAL_KIND) != frozenset(PrivacyRefusalReason):  # pragma: no cover
    raise RuntimeError("every privacy refusal reason declares a refusal kind")


class PrivacyRefused(PermissionError):
    """Raised before a packet reaches a boundary it may not cross."""

    def __init__(self, reason: PrivacyRefusalReason, subject: str, detail: str) -> None:
        super().__init__(f"{reason.value} at {subject}: {detail}")
        self.reason = reason
        self.kind = REFUSAL_KIND[reason]
        self.subject = subject
        self.detail = detail


@dataclass(frozen=True)
class GatedFaultPacket:
    """One packet this gate has read in full, with the bounds it satisfied."""

    record: FaultRecord
    bounds: PacketBounds
    gate: str = PRIVACY_GATE_FORM


def _refuse(reason: PrivacyRefusalReason, subject: str, detail: str) -> PrivacyRefused:
    return PrivacyRefused(reason, subject, detail)


def _evidence_texts(references: Sequence[EvidenceReference], path: str):
    for index, reference in enumerate(references):
        yield f"{path}[{index}].evidence_id", reference.evidence_id, True
        yield f"{path}[{index}].version", reference.version, True
        yield f"{path}[{index}].summary", reference.summary, False


def _declared_texts(record: FaultRecord):
    """Yield every declared text of a packet as a subject, a value and its kind.

    The third item says whether the text is an identifier, which carries the
    shorter declared bound, or free text, which carries the longer one.
    """
    yield "fault_id", record.fault_id, True
    yield "version", record.version, True
    yield "result.identifier", record.result.identifier, True
    yield "result.version", record.result.version, True
    for index, outcome_id in enumerate(record.affected_clause_outcome_ids):
        yield f"affected_clause_outcome_ids[{index}]", outcome_id, True
    yield "diagnostic_scope", record.diagnostic_scope, False
    localisation = record.localisation
    yield "localisation.localisation_id", localisation.localisation_id, True
    yield "localisation.version", localisation.version, True
    for name, frontiers in (
        ("lower_frontier", localisation.lower_frontier),
        ("upper_frontier", localisation.upper_frontier),
    ):
        for index, frontier in enumerate(frontiers):
            subject = f"localisation.{name}[{index}]"
            yield f"{subject}.checkpoint_id", frontier.checkpoint_id, True
            yield from _evidence_texts(frontier.evidence, f"{subject}.evidence")
    for index, uncovered in enumerate(localisation.uncovered_paths):
        subject = f"localisation.uncovered_paths[{index}]"
        yield f"{subject}.path_id", uncovered.path_id, True
        for position, checkpoint_id in enumerate(uncovered.checkpoint_ids):
            yield f"{subject}.checkpoint_ids[{position}]", checkpoint_id, True
        yield from _evidence_texts(uncovered.evidence, f"{subject}.evidence")
    yield from _evidence_texts(localisation.supporting_evidence, "localisation.supporting_evidence")
    yield from _evidence_texts(record.supporting_evidence, "supporting_evidence")
    yield from _evidence_texts(record.contradicting_evidence, "contradicting_evidence")
    if record.correction_surface is not None:
        yield "correction_surface.identifier", record.correction_surface.identifier, True
        yield "correction_surface.version", record.correction_surface.version, True


def _declared_digests(record: FaultRecord):
    """Yield every declared digest of a packet as a subject and a value."""
    yield "result.digest", record.result.digest
    localisation = record.localisation
    for name, frontiers in (
        ("lower_frontier", localisation.lower_frontier),
        ("upper_frontier", localisation.upper_frontier),
    ):
        for index, frontier in enumerate(frontiers):
            for position, reference in enumerate(frontier.evidence):
                yield f"localisation.{name}[{index}].evidence[{position}].digest", reference.digest
    for index, uncovered in enumerate(localisation.uncovered_paths):
        for position, reference in enumerate(uncovered.evidence):
            yield f"localisation.uncovered_paths[{index}].evidence[{position}].digest", reference.digest
    for name, references in (
        ("localisation.supporting_evidence", localisation.supporting_evidence),
        ("supporting_evidence", record.supporting_evidence),
        ("contradicting_evidence", record.contradicting_evidence),
    ):
        for index, reference in enumerate(references):
            yield f"{name}[{index}].digest", reference.digest
    if record.correction_surface is not None:
        yield "correction_surface.digest", record.correction_surface.digest


def _confirm_form(record: object) -> FaultRecord:
    if not isinstance(record, FaultRecord):
        raise _refuse(
            PrivacyRefusalReason.UNRESOLVED_PACKET,
            "packet",
            "a fault record is required before a packet can be gated",
        )
    try:
        texts = tuple(_declared_texts(record))
    except (AttributeError, TypeError):
        raise _refuse(
            PrivacyRefusalReason.UNRESOLVED_PACKET,
            "packet",
            "the record does not carry the declarations a packet is read from",
        ) from None
    for subject, value, _ in texts:
        if not isinstance(value, str) or not value.strip():
            raise _refuse(
                PrivacyRefusalReason.UNRESOLVED_PACKET,
                subject,
                "a packet declares no empty text",
            )
    if not record.affected_clause_outcome_ids:
        raise _refuse(
            PrivacyRefusalReason.UNRESOLVED_PACKET,
            "affected_clause_outcome_ids",
            "a packet names at least one comparison it answers for",
        )
    if not record.supporting_evidence:
        raise _refuse(
            PrivacyRefusalReason.UNRESOLVED_PACKET,
            "supporting_evidence",
            "a packet names at least one piece of evidence for what it reports",
        )
    return record


def _confirm_agreement(record: FaultRecord) -> None:
    unknown = record.fault_class is FaultClass.UNKNOWN
    withheld_unknown = record.disclosure_decision is DisclosureDecision.WITHHOLD_UNKNOWN
    if unknown != withheld_unknown:
        raise _refuse(
            PrivacyRefusalReason.CONTRADICTORY_PACKET,
            "disclosure_decision",
            "an undecided class and an undecided disclosure decision are declared together or not at all",
        )


def _confirm_bounds(record: FaultRecord, bounds: PacketBounds) -> None:
    counted = (
        ("affected_clause_outcome_ids", len(record.affected_clause_outcome_ids), bounds.affected_clause_outcomes),
        ("supporting_evidence", len(record.supporting_evidence), bounds.evidence_references),
        ("contradicting_evidence", len(record.contradicting_evidence), bounds.evidence_references),
        (
            "localisation.supporting_evidence",
            len(record.localisation.supporting_evidence),
            bounds.evidence_references,
        ),
        ("localisation.lower_frontier", len(record.localisation.lower_frontier), bounds.frontier_checkpoints),
        ("localisation.upper_frontier", len(record.localisation.upper_frontier), bounds.frontier_checkpoints),
        ("localisation.uncovered_paths", len(record.localisation.uncovered_paths), bounds.uncovered_paths),
    )
    for subject, measured, maximum in counted:
        if measured > maximum:
            raise _refuse(
                PrivacyRefusalReason.DECLARED_BOUND_EXCEEDED,
                subject,
                f"the packet carries {measured} where the declared bound is {maximum}",
            )
    for index, uncovered in enumerate(record.localisation.uncovered_paths):
        if len(uncovered.checkpoint_ids) > bounds.checkpoints_per_path:
            raise _refuse(
                PrivacyRefusalReason.DECLARED_BOUND_EXCEEDED,
                f"localisation.uncovered_paths[{index}].checkpoint_ids",
                f"the path names {len(uncovered.checkpoint_ids)} checkpoints where the declared bound is {bounds.checkpoints_per_path}",
            )
    for subject, value, identifier in _declared_texts(record):
        maximum = bounds.identifier_characters if identifier else bounds.text_characters
        if len(value) > maximum:
            raise _refuse(
                PrivacyRefusalReason.DECLARED_BOUND_EXCEEDED,
                subject,
                f"the text is {len(value)} characters where the declared bound is {maximum}",
            )


def _matched(patterns: Iterable[re.Pattern[str]], value: str) -> bool:
    return any(pattern.search(value) for pattern in patterns)


def _carries_value_literal(value: str) -> str | None:
    for token in value.split():
        trimmed = token.strip(_TRIM)
        if trimmed and _matched(VALUE_LITERAL_PATTERNS, trimmed):
            return "a written observation of one subject"
    return None


def _confirm_content(record: FaultRecord) -> None:
    texts = tuple((subject, value) for subject, value, _ in _declared_texts(record))
    rules = (
        (PrivacyRefusalReason.LOCAL_PATH, lambda value: shape_carried(LOCAL_PATH_PATTERNS, value)),
        (PrivacyRefusalReason.CREDENTIAL, lambda value: shape_carried(CREDENTIAL_PATTERNS, value)),
        (PrivacyRefusalReason.RAW_ROW, lambda value: shape_carried(RAW_ROW_PATTERNS, value)),
        (PrivacyRefusalReason.SINGLETON_VALUE, _carries_value_literal),
    )
    for reason, carried in rules:
        for subject, value in texts:
            shape = carried(value)
            if shape is not None:
                raise _refuse(reason, subject, f"the declared text carries {shape}")


def _confirm_digests(record: FaultRecord) -> None:
    for subject, digest in _declared_digests(record):
        if not isinstance(digest, str) or not FINGERPRINT.match(digest):
            raise _refuse(
                PrivacyRefusalReason.REVERSIBLE_DIGEST,
                subject,
                "a digest slot carries an opaque fingerprint of fixed width under a named algorithm",
            )


def _confirm_disclosure(record: FaultRecord) -> None:
    if record.disclosure_decision is not DisclosureDecision.DISCLOSE:
        raise _refuse(
            PrivacyRefusalReason.DISCLOSURE_WITHHELD,
            "disclosure_decision",
            f"the disclosure policy withheld this packet as {record.disclosure_decision.value}",
        )


def inspect_fault_packet(record: object, *, bounds: PacketBounds = PACKET_BOUNDS) -> FaultRecord:
    """Read one packet in full and refuse it on the first rule it breaks.

    The packet's disclosure decision is not applied here, so a caller can read
    a withheld packet's shape without crossing a boundary with it.
    """
    confirmed = _confirm_form(record)
    _confirm_agreement(confirmed)
    _confirm_bounds(confirmed, bounds)
    _confirm_content(confirmed)
    _confirm_digests(confirmed)
    return confirmed


def gate_fault_packet(record: object, *, bounds: PacketBounds = PACKET_BOUNDS) -> GatedFaultPacket:
    """Return the packet as gated, or refuse it before any adviser boundary."""
    confirmed = inspect_fault_packet(record, bounds=bounds)
    _confirm_disclosure(confirmed)
    return GatedFaultPacket(record=confirmed, bounds=bounds)


__all__ = [
    "CREDENTIAL_PATTERNS",
    "FINGERPRINT",
    "GatedFaultPacket",
    "LOCAL_PATH_PATTERNS",
    "PACKET_BOUNDS",
    "PRIVACY_GATE_FORM",
    "PacketBounds",
    "PrivacyRefusalKind",
    "PrivacyRefusalReason",
    "PrivacyRefused",
    "RAW_ROW_PATTERNS",
    "REFUSAL_KIND",
    "VALUE_LITERAL_PATTERNS",
    "gate_fault_packet",
    "inspect_fault_packet",
]
