"""The diagnostic adviser: one bounded packet out, one inert advice record back.

This workflow is the only place the product asks a model about a fault. It
reads a packet the privacy gate has already passed, sends the declared fields
of that packet through the model-egress port, and turns the declared reply into
the domain's inert advice record. It runs no command, changes no artefact,
touches no tracker and accepts nothing.

It lives with the verification workflows because that is the only verification
component the architecture record allows to reach both the fault packet and the
model-egress port. The core builds the packet and may not reach a provider; the
enforcement package gates the packet and reads nothing else; the readable Koine
projection may reach the port but not the packet.

What crosses the port. One function owns the field set: the packet's declared
text as the core writes it, plus the distinct evidence identities the packet
declares on each side of its argument. Every value is a declaration the gate
has already read, so nothing new is invented at this boundary. The identities
are sent because the adviser is asked to cite evidence by identity, and it can
only cite what it has been given. Nothing callable is placed in the call, so
the inference has no tool and no callback surface.

What comes back. The reply is a declared form, not free text: a confidence, a
list of assumptions, and zero or more hypotheses, each with a cause, a proposed
fix, a discriminating regression test, and the evidence identities it rests on
and argues against. There is no guessing step, because there is nothing to
guess: a reply of any other shape is refused before anything is recorded.

What is refused, and what is not. A packet that did not pass the gate sends
nothing. A packet declaring a bound looser than the product's own is refused
rather than obeyed, and the gate is asked about every packet under the
product's bounds, so a packet assembled by hand cannot widen what crosses by
declaring a wider shape for itself. A reply whose declared form is wrong, whose
confidence and hypotheses disagree, whose hypothesis is incomplete, or which
repeats a declaration, is refused. A reply citing evidence the packet does not
carry is refused, because an adviser may not introduce a fact the packet never
made available. Every one of those is an integrity reason: it says the packet
or the reply cannot be read as one.

Nothing is refused for what it says. The adviser's recommendation is recorded
word for word, and that includes a shell line, a written change to data, a
tolerance it would rather see, a tracker action or a plain statement that the
run should be accepted. Reading the words and refusing some of them would be a
weak defence of a strong property, because the words a filter misses are the
same words a filter would have to catch, and a refusal throws the whole answer
away.

The property this module actually holds is that nothing the advice says is
ever carried out here. The advice is text in an inert record. This module runs
no command, spawns no process, evaluates nothing, writes no file, and never
puts a word of the reply into another model call or into a tracked-work
command. Nothing downstream reads the advice record either: the tracker
adapter and the acceptance route never see it. A named person reads the advice
and decides what, if anything, to do about it. That is the whole safety
argument, and the tests for this module prove each of its parts rather than
asserting that some list of forbidden phrasings was caught.

Nothing is refused here for being synthetic, derived or weak. Weak evidence
lowers the confidence an adviser declares; it never withholds the advice.
"""
from __future__ import annotations

# evorthon-component: verification_workflows
# evorthon-implements: EVD-README-050

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from evorthon_data.security.model_egress import (
    ModelCall,
    ModelCallPurpose,
    ModelDestination,
    ModelEgressAuthorization,
    ModelEgressMode,
    ModelEgressPort,
)
from evorthon_data.verification.core.canonical import canonical_digest, record_digest
from evorthon_data.verification.core.fault import packet_fields
from evorthon_data.verification.domain.contracts import (
    AdviserConfidence,
    DisclosureDecision,
    EvidenceReference,
    FaultRecord,
    Identity,
    RemediationAdvice,
)
from evorthon_data.verification.enforcement.privacy import (
    PACKET_BOUNDS,
    PRIVACY_GATE_FORM,
    GatedFaultPacket,
    PacketBounds,
    gate_fault_packet,
)

ADVISER_WORKFLOW_FORM = "evorthon.verification.adviser.v1"
ADVISER_REPLY_FORM = "evorthon.verification.adviser.reply.v1"
ADVICE_VERSION = "evorthon.verification.adviser.advice.v1"

# The one route this workflow uses. The destination behind it is the adopting
# environment's choice; the route name is the product's.
ADVISER_ROUTE = "koine.advise.diagnosis"

# The two field names the call adds to the packet's own declared text. They are
# stable, so one authorization can be scoped to this route once.
SUPPORTING_IDENTITIES_FIELD = "supporting_evidence_identities"
CONTRADICTING_IDENTITIES_FIELD = "contradicting_evidence_identities"


class AdviserRefusalReason(str, Enum):
    """The closed set of reasons this workflow refuses to record advice.

    Every one of them is an integrity reason: the packet or the reply cannot be
    read as one. None of them reads what the advice says, because what the
    advice says is the adviser's to write and a person's to judge.
    """

    UNGATED_PACKET = "ungated-packet"
    RELAXED_BOUNDS = "relaxed-bounds"
    UNRESOLVED_REPLY = "unresolved-reply"
    CONTRADICTORY_REPLY = "contradictory-reply"
    INCOMPLETE_HYPOTHESIS = "incomplete-hypothesis"
    REPEATED_DECLARATION = "repeated-declaration"
    UNCITED_EVIDENCE = "uncited-evidence"


class AdviserRefused(ValueError):
    """Raised before an adviser reply becomes advice it may not become."""

    def __init__(self, reason: AdviserRefusalReason, subject: str, detail: str) -> None:
        super().__init__(f"{reason.value} at {subject}: {detail}")
        self.reason = reason
        self.subject = subject
        self.detail = detail


@dataclass(frozen=True)
class AdviserRoute:
    """The destination and handling policy one adviser call is sent under.

    The engagement session declares the same five facts for its own generator
    and reviewer routes. The architecture record allows no edge from these
    workflows to the engagement component, so the declaration is repeated here
    rather than imported. A shared owner for it belongs with the egress port,
    which both components already reach.
    """

    destination: ModelDestination
    mode: ModelEgressMode
    data_class: str
    retention_policy: str
    evidence_policy: str

    def __post_init__(self) -> None:
        if not isinstance(self.destination, ModelDestination):
            raise ValueError("destination must be a ModelDestination")
        if not isinstance(self.mode, ModelEgressMode):
            raise ValueError("mode must be a ModelEgressMode")
        for name in ("data_class", "retention_policy", "evidence_policy"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(f"{name} must be a non-empty, trimmed string")


@dataclass(frozen=True)
class AdviserHypothesis:
    """One declared cause, what would correct it, and what would tell it apart."""

    cause: str
    proposed_fix: str
    discriminating_test: str
    supporting_evidence_ids: tuple[str, ...]
    contradicting_evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class AdviserReply:
    """The declared form an adviser answers in, and the only one read here."""

    form: str
    confidence: AdviserConfidence
    hypotheses: tuple[AdviserHypothesis, ...] = ()
    assumptions: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiagnosticAdviceOutcome:
    """What one adviser round produced, and the exact call it rests on.

    ``advice`` is absent for an unknown answer, which is a real answer and not
    a failure: the adviser read the packet and could not name a cause it would
    stand behind.
    """

    packet: GatedFaultPacket
    call: ModelCall
    confidence: AdviserConfidence
    advice: RemediationAdvice | None
    form: str = ADVISER_WORKFLOW_FORM

    @property
    def is_unknown(self) -> bool:
        """Whether the adviser answered that it cannot name a cause."""
        return self.advice is None


def _refuse(reason: AdviserRefusalReason, subject: str, detail: str) -> AdviserRefused:
    return AdviserRefused(reason, subject, detail)


def _distinct_identities(references: Sequence[EvidenceReference]) -> tuple[str, ...]:
    """Return the declared evidence identities of one side, in declared order."""
    seen: list[str] = []
    for reference in references:
        if reference.evidence_id not in seen:
            seen.append(reference.evidence_id)
    return tuple(seen)


def adviser_call_fields(packet: GatedFaultPacket) -> Mapping[str, object]:
    """Return every field one adviser call carries, and nothing else.

    This is the one owner of what crosses the port. It is the packet's declared
    text as the fault core writes it, plus the distinct evidence identities the
    packet declares, so the adviser can cite by identity what it was given. No
    row, no key, no field value and no approved text of a case is here, because
    none of those is in the packet the gate passed.
    """
    record = _gated_record(packet)
    fields = dict(packet_fields(record))
    fields[SUPPORTING_IDENTITIES_FIELD] = _distinct_identities(record.supporting_evidence)
    fields[CONTRADICTING_IDENTITIES_FIELD] = _distinct_identities(record.contradicting_evidence)
    return MappingProxyType(fields)


def _confirm_declared_bounds(bounds: object) -> None:
    """Refuse a packet that declares a bound looser than the product's own.

    The bounds a packet carries are a declaration, and a packet assembled by
    hand can declare anything. The product's bounds are the ones this boundary
    answers for, so a declaration looser than them on any measure is refused
    here rather than obeyed, and the gate is then asked about the record under
    the product's bounds and no other.
    """
    if not isinstance(bounds, PacketBounds):
        raise _refuse(
            AdviserRefusalReason.RELAXED_BOUNDS,
            "packet.bounds",
            "a packet declares the shape it was gated under",
        )
    for name in PACKET_BOUNDS.__dataclass_fields__:
        declared = getattr(bounds, name)
        product = getattr(PACKET_BOUNDS, name)
        if not isinstance(declared, int) or declared > product:
            raise _refuse(
                AdviserRefusalReason.RELAXED_BOUNDS,
                f"packet.bounds.{name}",
                f"the packet declares {declared} where the product's bound is {product}",
            )


def _gated_record(packet: object) -> FaultRecord:
    """Return the record of a packet that really did pass the gate.

    A record reaches this workflow only inside a gated packet, and the gate is
    asked again about that record so a packet assembled by hand cannot carry a
    withheld decision past this point. The gate keeps its own refusal.
    """
    if not isinstance(packet, GatedFaultPacket):
        raise _refuse(
            AdviserRefusalReason.UNGATED_PACKET,
            "packet",
            "a gated fault packet is required before an adviser sees anything",
        )
    if packet.gate != PRIVACY_GATE_FORM:
        raise _refuse(
            AdviserRefusalReason.UNGATED_PACKET,
            "packet.gate",
            "the packet does not declare the gate this adviser reads behind",
        )
    _confirm_declared_bounds(packet.bounds)
    confirmed = gate_fault_packet(packet.record, bounds=PACKET_BOUNDS).record
    if confirmed.disclosure_decision is not DisclosureDecision.DISCLOSE:
        raise _refuse(
            AdviserRefusalReason.UNGATED_PACKET,
            "packet.record.disclosure_decision",
            "a packet the disclosure policy withheld does not reach an adviser",
        )
    return confirmed


def build_adviser_call(
    packet: GatedFaultPacket,
    *,
    engagement_id: str,
    case_id: str,
    route: AdviserRoute,
) -> ModelCall:
    """Build the one bounded call so an environment can authorize it exactly."""
    if not isinstance(route, AdviserRoute):
        raise ValueError("an adviser call is sent under an AdviserRoute")
    return ModelCall(
        engagement_id=engagement_id,
        case_id=case_id,
        purpose=ModelCallPurpose.ADVISER,
        route=ADVISER_ROUTE,
        destination=route.destination,
        fields=adviser_call_fields(packet),
        data_class=route.data_class,
        retention_policy=route.retention_policy,
        evidence_policy=route.evidence_policy,
        mode=route.mode,
    )


def _declared_text(value: object, subject: str, reason: AdviserRefusalReason) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _refuse(reason, subject, "an adviser declares no empty text")
    return value


def _identity_list(value: object, subject: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise _refuse(
            AdviserRefusalReason.UNRESOLVED_REPLY,
            subject,
            "cited evidence is named by a tuple of declared identities",
        )
    return value


def _confirm_shape(reply: object) -> AdviserReply:
    """Confirm the reply is the declared form, in the shape that form states."""
    if not isinstance(reply, AdviserReply) or reply.form != ADVISER_REPLY_FORM:
        raise _refuse(
            AdviserRefusalReason.UNRESOLVED_REPLY,
            "reply",
            "an adviser answers in the declared reply form and no other",
        )
    if not isinstance(reply.confidence, AdviserConfidence):
        raise _refuse(
            AdviserRefusalReason.UNRESOLVED_REPLY,
            "reply.confidence",
            "confidence is declared from the calibrated vocabulary",
        )
    if not isinstance(reply.hypotheses, tuple) or any(
        not isinstance(item, AdviserHypothesis) for item in reply.hypotheses
    ):
        raise _refuse(
            AdviserRefusalReason.UNRESOLVED_REPLY,
            "reply.hypotheses",
            "hypotheses are declared as adviser hypotheses",
        )
    if not isinstance(reply.assumptions, tuple) or any(
        not isinstance(item, str) for item in reply.assumptions
    ):
        raise _refuse(
            AdviserRefusalReason.UNRESOLVED_REPLY,
            "reply.assumptions",
            "assumptions are declared as text",
        )
    unknown = reply.confidence is AdviserConfidence.UNKNOWN
    if unknown != (not reply.hypotheses):
        raise _refuse(
            AdviserRefusalReason.CONTRADICTORY_REPLY,
            "reply.confidence",
            "an unknown answer and an answer with no hypothesis are declared together or not at all",
        )
    return reply


def _confirm_declared(reply: AdviserReply) -> None:
    """Confirm every declared text of a reply is text and is not empty.

    This reads whether a declaration is there, never what it says. The words
    are recorded exactly as the adviser wrote them.
    """
    incomplete = AdviserRefusalReason.INCOMPLETE_HYPOTHESIS
    for index, hypothesis in enumerate(reply.hypotheses):
        subject = f"reply.hypotheses[{index}]"
        for name in ("cause", "proposed_fix", "discriminating_test"):
            field_subject = f"{subject}.{name}"
            _declared_text(getattr(hypothesis, name), field_subject, incomplete)
    for index, assumption in enumerate(reply.assumptions):
        subject = f"reply.assumptions[{index}]"
        _declared_text(assumption, subject, AdviserRefusalReason.UNRESOLVED_REPLY)


def _confirm_distinct(reply: AdviserReply) -> None:
    """Refuse a reply that declares the same thing twice."""
    declared = (
        ("cause", tuple(item.cause for item in reply.hypotheses)),
        ("proposed_fix", tuple(item.proposed_fix for item in reply.hypotheses)),
        ("discriminating_test", tuple(item.discriminating_test for item in reply.hypotheses)),
        ("assumption", reply.assumptions),
    )
    for name, values in declared:
        if len(set(values)) != len(values):
            raise _refuse(
                AdviserRefusalReason.REPEATED_DECLARATION,
                f"reply.{name}",
                "each declaration of an adviser reply is made once",
            )


def _cited(
    identities: tuple[str, ...],
    references: Sequence[EvidenceReference],
    subject: str,
) -> tuple[EvidenceReference, ...]:
    """Return the packet's own references for the identities a reply cites.

    A citation names an evidence identity. Where the packet declares more than
    one reference under one identity, the first declared reference is the one
    the advice carries, so the advice names each identity once.
    """
    held: dict[str, EvidenceReference] = {}
    for reference in references:
        held.setdefault(reference.evidence_id, reference)
    resolved: list[EvidenceReference] = []
    for identity in identities:
        reference = held.get(identity)
        if reference is None:
            raise _refuse(
                AdviserRefusalReason.UNCITED_EVIDENCE,
                subject,
                "the citation names evidence this packet does not carry",
            )
        if reference not in resolved:
            resolved.append(reference)
    return tuple(resolved)


def _advice_evidence(
    reply: AdviserReply, record: FaultRecord
) -> tuple[tuple[EvidenceReference, ...], tuple[EvidenceReference, ...]]:
    """Return the supporting and contradicting evidence the reply cites."""
    supporting: list[EvidenceReference] = []
    contradicting: list[EvidenceReference] = []
    for index, hypothesis in enumerate(reply.hypotheses):
        subject = f"reply.hypotheses[{index}]"
        supporting_ids = _identity_list(
            hypothesis.supporting_evidence_ids, f"{subject}.supporting_evidence_ids"
        )
        if not supporting_ids:
            raise _refuse(
                AdviserRefusalReason.INCOMPLETE_HYPOTHESIS,
                f"{subject}.supporting_evidence_ids",
                "a hypothesis rests on at least one piece of evidence the packet carries",
            )
        contradicting_ids = _identity_list(
            hypothesis.contradicting_evidence_ids, f"{subject}.contradicting_evidence_ids"
        )
        for cited, references, side in (
            (supporting_ids, record.supporting_evidence, supporting),
            (contradicting_ids, record.contradicting_evidence, contradicting),
        ):
            for reference in _cited(cited, references, subject):
                if reference not in side:
                    side.append(reference)
    return tuple(supporting), tuple(contradicting)


def _discriminating_test(text: str) -> Identity:
    """Return the identity of one declared regression test."""
    return Identity(identifier=text, version=ADVICE_VERSION, digest=canonical_digest(text.encode("utf-8")))


def _authority(required_authority: object) -> Identity:
    if not isinstance(required_authority, Identity) or not all(
        isinstance(value, str) and value.strip()
        for value in (required_authority.identifier, required_authority.version, required_authority.digest)
    ):
        raise ValueError("a named remediation authority is required")
    return required_authority


def read_adviser_reply(
    reply: object,
    packet: GatedFaultPacket,
    *,
    required_authority: Identity,
) -> RemediationAdvice | None:
    """Return the inert advice one declared reply supports, or nothing.

    Nothing is returned for an unknown answer. Every other outcome is either a
    complete advice record or a refusal with a closed reason; a reply is never
    partly recorded.
    """
    record = _gated_record(packet)
    authority = _authority(required_authority)
    confirmed = _confirm_shape(reply)
    _confirm_declared(confirmed)
    _confirm_distinct(confirmed)
    if not confirmed.hypotheses:
        return None
    supporting, contradicting = _advice_evidence(confirmed, record)
    return RemediationAdvice(
        advice_id=f"{record.fault_id}/advice",
        version=ADVICE_VERSION,
        fault=Identity(identifier=record.fault_id, version=record.version, digest=record_digest(record)),
        hypotheses=tuple(item.cause for item in confirmed.hypotheses),
        proposed_fixes=tuple(item.proposed_fix for item in confirmed.hypotheses),
        discriminating_tests=tuple(
            _discriminating_test(item.discriminating_test) for item in confirmed.hypotheses
        ),
        supporting_evidence=supporting,
        contradicting_evidence=contradicting,
        assumptions=confirmed.assumptions,
        required_authority=authority,
        confidence=confirmed.confidence,
    )


def advise_on_fault(
    packet: GatedFaultPacket,
    *,
    engagement_id: str,
    case_id: str,
    route: AdviserRoute,
    egress: ModelEgressPort,
    required_authority: Identity,
    authorization: ModelEgressAuthorization | None = None,
) -> DiagnosticAdviceOutcome:
    """Ask the adviser about one gated packet and record what it may record.

    The packet is confirmed before anything is built, so a packet that did not
    pass the gate sends nothing. The authorization is handed to the port
    unchanged: this workflow holds no provider client, no credential and no
    authorization policy, and a call the port refuses reaches no transport.
    """
    if not isinstance(egress, ModelEgressPort):
        raise ValueError("an adviser round runs through a ModelEgressPort")
    authority = _authority(required_authority)
    call = build_adviser_call(packet, engagement_id=engagement_id, case_id=case_id, route=route)
    reply = egress.invoke(call, authorization)
    advice = read_adviser_reply(reply, packet, required_authority=authority)
    confidence = AdviserConfidence.UNKNOWN if advice is None else advice.confidence
    return DiagnosticAdviceOutcome(packet=packet, call=call, confidence=confidence, advice=advice)


__all__ = [
    "ADVICE_VERSION",
    "ADVISER_REPLY_FORM",
    "ADVISER_ROUTE",
    "ADVISER_WORKFLOW_FORM",
    "AdviserHypothesis",
    "AdviserRefusalReason",
    "AdviserRefused",
    "AdviserReply",
    "AdviserRoute",
    "CONTRADICTING_IDENTITIES_FIELD",
    "DiagnosticAdviceOutcome",
    "SUPPORTING_IDENTITIES_FIELD",
    "advise_on_fault",
    "adviser_call_fields",
    "build_adviser_call",
    "read_adviser_reply",
]
