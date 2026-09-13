"""Bounded reports of what a verification workflow decided.

Everything a person or a machine reads about a verification run is written
here, and nothing else is. The rule this module keeps is short: a report names
what was compared and what the comparison decided, and it never carries the
material behind either. No row, no key, no field value, no approved text of a
case and no location reaches a line written here. What does reach a line is an
identity, a declared status, a count and an opaque digest.

Two surfaces are written, from the same values.

A reported surface is the ordered values one route reports. A caller renders
them through the one output convention the product's command surface owns, so
this module writes no envelope, no exit code and no refusal of its own.

A record surface is the facts one route writes down. A caller renders those
through the one record projection owner, so this module writes no file and no
projection either.

Every list is capped. A capped list carries the first entries and then one line
saying how many were not listed and what the cap is, so a reader can always
tell a short list from a long one that was cut.

A packet the disclosure policy withheld is reported as which fault it answers
for and the decision that withheld it, and as nothing else. The decision is a
completed answer rather than a failure, so it is written down and rendered like
any other; what the packet observed, and what the evidence behind it supports,
stay unwritten. The decision itself is read off the packet the core built, so
this module states no decision of its own.

One more closed decision is written here, because this is where the decisions a
diagnosis reports are owned. A run whose failing clauses were all answered over
the facts it declared names no failing output, and a packet answers for a
failing output, so such a run has no packet to build, withhold or disclose.
That is a completed diagnosis too: the decision, the families that failed and
the clauses they are, and nothing a packet would have carried. It is written
here rather than in the diagnosis workflow because the workflow answers for one
failing output and this run has none, so the workflow is never reached.

Where a report reads a written record back, the reader sits beside the writer
that wrote it, so the two cannot drift into two different sets of field names.

This module reads workflow outcome types and the declared verification
vocabulary, and reads nothing else. It never asks a workflow anything, never
decides a status and never promotes, demotes or relabels one: a status written
here is the status the outcome carries, and the one status it names for itself
names a failing outcome so a reader can be told which output failed.
"""
from __future__ import annotations

# evorthon-component: verification_presentation

from collections.abc import Mapping, Sequence

from evorthon_data.verification.domain.contracts import DisclosureDecision, VerificationStatus

# The stable names of the record forms the verification routes write.
INTAKE_RECORD_FORM = "evorthon.verification.intake.record.v1"
OUTCOME_RECORD_FORM = "evorthon.verification.outcome.record.v1"
PACKET_RECORD_FORM = "evorthon.verification.fault.record.v1"

# The field the core writes its disclosure decision under, the label a report
# writes that field as, and the one decision under which a packet may be
# carried onward. A caller that drives further work off one diagnosis reads
# these rather than stating a decision of its own. One pin holds them to the
# fields the core actually writes.
DISCLOSURE_FIELD = "disclosure_decision"
DISCLOSURE_LABEL = DISCLOSURE_FIELD.replace("_", " ")
DISCLOSED = DisclosureDecision.DISCLOSE.value
# The field the core writes the fault's own identity under.
PACKET_FAULT_FIELD = "fault_id"
# The status a verified run reports when every clause it answered passed, and
# the status it reports when a clause it answered failed. A caller that drives
# further work off one run reads these rather than stating a status of its own.
PASSED = VerificationStatus.PASS.value
FAILED = VerificationStatus.FAIL.value
# The names one recorded outcome holds its facts under, and the whole set of
# them a reader may read. The writer below and every reader of a recorded run
# name the same fields here, so the two cannot drift into two different sets of
# names.
OUTCOME_STATUS_FIELD = "status"
OUTCOME_CLAUSE_FIELD = "clause"
OUTCOME_FAILED_OUTPUT_FIELD = "failed output"
OUTCOME_RESULT_DIGEST_FIELD = "result digest"
OUTCOME_DIGEST_FIELD = "outcome digest"
OUTCOME_FIELDS = (
    OUTCOME_STATUS_FIELD,
    OUTCOME_CLAUSE_FIELD,
    OUTCOME_FAILED_OUTPUT_FIELD,
    OUTCOME_RESULT_DIGEST_FIELD,
    OUTCOME_DIGEST_FIELD,
)
# The label a diagnosis reports its own closed decision under, and the one
# decision it carries: the run failed with no output for a packet to answer
# for. The fields such a diagnosis reports beside it name which families failed
# and which clauses they are.
DECISION_LABEL = "decision"
NO_FAILING_OUTPUT = "no output failed"
FAILING_FAMILY_FIELD = "failing families"
FAILING_CLAUSE_FIELD = "failing clauses"
# The form the record of such a diagnosis takes. It is not a packet record,
# because no packet was built: it holds the decision and the clauses that
# failed, and nothing a packet would have carried.
DIAGNOSIS_RECORD_FORM = "evorthon.verification.diagnosis.record.v1"
# What a report carries for a packet the disclosure policy withheld: which
# fault this is, by the identity and the closed class the core decided, the
# form its record takes, and the decision itself. Everything the packet
# observed stays out: the scope with its counts, how far the lineage narrowed
# the fault, and how much evidence stands on each side of the argument.
WITHHELD_FIELDS = (PACKET_FAULT_FIELD, "packet_form", "fault_class", DISCLOSURE_FIELD)
# The label the gate that read a packet is named under, and the labels a report
# carries only where a packet was built at all. A caller that asks whether a
# diagnosis carries any packet reads the set here rather than listing it again.
GATE_LABEL = "gate"
PACKET_LABELS = frozenset(
    {name.replace("_", " ") for name in WITHHELD_FIELDS} | {GATE_LABEL}
)

# How many entries of any one list reach a report, and how the rest are said.
LIST_CAP = 8
NOT_LISTED = "{count} more not listed, cap {cap}"
# What a report says when a route asked no adviser anything.
NO_ADVICE = "not requested"
# The separator between the fields of one written summary line.
FIELD_SEPARATOR = ": "
# The fields one written clause line carries, in the order it writes them. The
# names are the reader's, so a caller that reads a line back names the same
# fields the writer wrote.
CLAUSE_FIELDS = ("clause", "family", "status", "assurance", "execution")


def capped(entries: Sequence[str]) -> tuple[str, ...]:
    """Return the entries a report carries, with the rest counted rather than listed."""
    listed = tuple(entries)
    if len(listed) <= LIST_CAP:
        return listed
    remaining = len(listed) - LIST_CAP
    return (*listed[:LIST_CAP], NOT_LISTED.format(count=remaining, cap=LIST_CAP))


def line(*fields: str) -> str:
    """Write one summary line as its fields, in the order the caller states them."""
    return FIELD_SEPARATOR.join(fields)


def clause_fields(written: str) -> tuple[str, ...] | None:
    """Read one clause line back into its fields, or nothing when it is not one.

    A line that does not carry the declared number of fields is not a clause
    line this module wrote. Nothing is guessed for it: the reader says so by
    returning nothing, and the caller that owns refusals decides what that is.
    """
    read = tuple(written.split(FIELD_SEPARATOR))
    return read if len(read) == len(CLAUSE_FIELDS) else None


def clause_entry(execution) -> Mapping[str, str]:
    """Read one answered clause into the fields a clause line carries, by name."""
    return {
        "clause": execution.clause_id,
        "family": execution.family.value,
        "status": execution.outcome.status.value,
        "assurance": execution.assurance.value,
        "execution": "executed" if execution.executed else "not executed",
    }


def _clause_lines(contract) -> tuple[str, ...]:
    """Write one line per answered clause: what it is and what it decided.

    The fields are written in the order the field names declare, so the writer
    and the reader beside it cannot drift into two different orders.
    """
    return tuple(
        line(*(clause_entry(execution)[name] for name in CLAUSE_FIELDS))
        for execution in contract.executions
    )


def failed_outputs(reconciliation) -> tuple[str, ...]:
    """Name every output a reconciled run reports as failing, in a stable order."""
    named: list[str] = []
    for clause in reconciliation.clauses:
        if clause.outcome.status is VerificationStatus.FAIL and clause.output_id not in named:
            named.append(clause.output_id)
    return tuple(named)


def intake_values(intake, record: str) -> tuple[tuple[str, object], ...]:
    """Report one accepted intake: what it answers for and the receipts it derived."""
    return (
        ("case", intake.case.identifier),
        ("case version", intake.case.version),
        ("candidate", intake.candidate.candidate_id),
        ("context", intake.context.context_id),
        ("intake digest", intake.intake_digest),
        ("confirmed evidence", len(intake.confirmed_evidence)),
        ("receipt digests", list(capped(intake.receipt_digests))),
        ("record", record),
    )


def verification_values(reconciliation, contract, record: str) -> tuple[tuple[str, object], ...]:
    """Report one verified run: the status its outcomes imply and what they were."""
    return (
        ("case", contract.case.identifier),
        (OUTCOME_STATUS_FIELD, contract.status.value),
        ("reconciled status", reconciliation.result.status.value),
        (OUTCOME_RESULT_DIGEST_FIELD, reconciliation.result_digest),
        (OUTCOME_DIGEST_FIELD, contract.summary_digest),
        ("evidence provenance", reconciliation.evidence_provenance.value),
        ("clauses", list(capped(_clause_lines(contract)))),
        ("failed clauses", list(capped(contract.failed))),
        ("unresolved clauses", list(capped(contract.unresolved))),
        ("failed outputs", list(capped(failed_outputs(reconciliation)))),
        ("record", record),
    )


def withheld_decision(decision: str) -> bool:
    """Say whether one reported disclosure decision withholds its packet.

    This is the one rule, and both the surface that bounds a report and a
    caller driving further work off a reported decision read it here: a packet
    is withheld unless the decision is the one that discloses it.
    """
    return decision != DISCLOSED


def withheld(diagnosis) -> bool:
    """Say whether the core withheld this packet, by reading the decision it made."""
    return withheld_decision(diagnosis.packet.disclosure_decision.value)


def _packet_fields(diagnosis) -> tuple[tuple[str, str], ...]:
    """Return the packet fields a report carries, bounded by the core's decision."""
    written = tuple(diagnosis.fields.items())
    if not withheld(diagnosis):
        return written
    return tuple((name, value) for name, value in written if name in WITHHELD_FIELDS)


def diagnosis_values(diagnosis, record: str) -> tuple[tuple[str, object], ...]:
    """Report one diagnosed packet: its declared fields, and that no advice was asked for.

    A withheld packet is reported as the fault it answers for and the decision
    that withheld it. What the evidence behind it supports is left out with the
    packet's own scope, because a reader who may not have the packet may not
    have how far it was narrowed either.
    """
    declared = tuple(
        (name.replace("_", " "), value) for name, value in _packet_fields(diagnosis)
    )
    supported = (
        ()
        if withheld(diagnosis)
        else (
            ("confidence", diagnosis.confidence.value),
            ("replayed", list(capped(diagnosis.replayed))),
            ("ruled out", list(capped(diagnosis.ruled_out))),
        )
    )
    return (
        *declared,
        *supported,
        (GATE_LABEL, diagnosis.gate),
        ("advice", NO_ADVICE),
        ("record", record),
    )


def intake_record_facts(intake) -> Mapping[str, str | tuple[str, ...]]:
    """Write down one accepted intake as the facts its record holds."""
    return {
        "form": INTAKE_RECORD_FORM,
        "case": intake.case.identifier,
        "case version": intake.case.version,
        "case digest": intake.case.digest,
        "candidate": intake.candidate.candidate_id,
        "context": intake.context.context_id,
        "intake digest": intake.intake_digest,
        "receipt": tuple(intake.receipt_digests),
    }


def outcome_record_facts(reconciliation, contract) -> Mapping[str, str | tuple[str, ...]]:
    """Write down one verified run as the facts its record holds."""
    return {
        "form": OUTCOME_RECORD_FORM,
        "case": contract.case.identifier,
        "case version": contract.case.version,
        "case digest": contract.case.digest,
        "result": reconciliation.result.result_id,
        OUTCOME_RESULT_DIGEST_FIELD: reconciliation.result_digest,
        OUTCOME_DIGEST_FIELD: contract.summary_digest,
        OUTCOME_STATUS_FIELD: contract.status.value,
        OUTCOME_CLAUSE_FIELD: _clause_lines(contract),
        OUTCOME_FAILED_OUTPUT_FIELD: failed_outputs(reconciliation),
    }


def failed_without_output(recorded: Mapping[str, tuple[str, ...]]) -> bool:
    """Say whether one recorded run failed with no output named as failing.

    This is the one rule for it, and every caller that asks reads it here. An
    output is named as failing only by the parity comparison that reports one,
    so a run whose failing clauses were all answered over the facts it declared
    carries the failing status and names no output beside it.
    """
    return recorded.get(OUTCOME_STATUS_FIELD, ()) == (FAILED,) and not recorded.get(
        OUTCOME_FAILED_OUTPUT_FIELD, ()
    )


def failing_clauses(
    recorded: Mapping[str, tuple[str, ...]]
) -> tuple[tuple[str, str], ...] | None:
    """Read one recorded run's failing clauses back as each clause and its family.

    A line that is not one this module wrote makes the whole reading nothing,
    so the caller that owns refusals says the record is malformed rather than
    reporting a reading with a line quietly dropped.
    """
    read: list[tuple[str, str]] = []
    for written in recorded.get(OUTCOME_CLAUSE_FIELD, ()):
        fields = clause_fields(written)
        if fields is None:
            return None
        entry = dict(zip(CLAUSE_FIELDS, fields))
        if entry["status"] == FAILED:
            read.append((entry["clause"], entry["family"]))
    return tuple(read)


def _failing_fields(failing: Sequence[tuple[str, str]]) -> tuple[tuple[str, ...], ...]:
    """Return the families one run's failing clauses answer for, and those clauses.

    A family is named once however many of its clauses failed, in the order the
    record holds them, so a reader is told which kinds of clause failed without
    reading the same word twice.
    """
    return (
        tuple(dict.fromkeys(family for _, family in failing)),
        tuple(clause for clause, _ in failing),
    )


def no_failing_output_values(
    case, failing: Sequence[tuple[str, str]], record: str
) -> tuple[tuple[str, object], ...]:
    """Report one diagnosis of a run that failed with no output to answer for.

    The clauses that failed were answered over the facts the run declared
    rather than over a difference between published rows, so there is no
    output, no packet and no fault of any kind. What the report carries is the
    closed decision, the families that failed and the clauses they are, so a
    reader is told what happened rather than told nothing.
    """
    families, clauses = _failing_fields(failing)
    return (
        ("case", case.case_id),
        ("case version", case.version),
        (DECISION_LABEL, NO_FAILING_OUTPUT),
        (FAILING_FAMILY_FIELD, list(capped(families))),
        (FAILING_CLAUSE_FIELD, list(capped(clauses))),
        ("advice", NO_ADVICE),
        ("record", record),
    )


def no_failing_output_record_facts(
    case, failing: Sequence[tuple[str, str]]
) -> Mapping[str, str | tuple[str, ...]]:
    """Write down one such diagnosis as the facts its record holds."""
    families, clauses = _failing_fields(failing)
    return {
        "form": DIAGNOSIS_RECORD_FORM,
        "case": case.case_id,
        "case version": case.version,
        DECISION_LABEL: NO_FAILING_OUTPUT,
        FAILING_FAMILY_FIELD: families,
        FAILING_CLAUSE_FIELD: clauses,
        "advice": NO_ADVICE,
    }


def diagnosis_decision(reported: Sequence[tuple[str, object]]) -> str | None:
    """Read the closed decision one reported diagnosis carries, or nothing at all.

    Two decisions close a diagnosis where it stands, and neither is a failure
    to diagnose. A run that failed with no output for a packet to answer for is
    reported as that decision; a packet the disclosure policy withheld is
    reported as the decision that withheld it. Either one means there is no
    packet to carry onward, so a caller that drives further work off one
    diagnosis reads both here and states neither for itself.
    """
    read = dict(reported)
    decided = read.get(DECISION_LABEL)
    if decided is not None:
        return str(decided)
    disclosure = read.get(DISCLOSURE_LABEL)
    if disclosure is not None and withheld_decision(str(disclosure)):
        return str(disclosure)
    return None


def unasked_adviser_values(case, diagnosis, authority: str) -> tuple[tuple[str, object], ...]:
    """Report one adviser round nobody was asked, because the packet was withheld.

    A packet the disclosure policy withheld does not cross to an adviser, and
    that decision is the round's completed answer rather than a failure. The
    report names which fault it answers for and the decision that withheld it,
    says no advice was asked for, and names the authority such a round would
    have required. Nothing the packet observed is written.
    """
    declared = dict(_packet_fields(diagnosis))
    return (
        ("case", case.case_id),
        ("case version", case.version),
        ("fault", declared[PACKET_FAULT_FIELD]),
        (DISCLOSURE_LABEL, declared[DISCLOSURE_FIELD]),
        ("advice", NO_ADVICE),
        ("required authority", authority),
    )


def packet_record_facts(diagnosis) -> Mapping[str, str | tuple[str, ...]]:
    """Write down one diagnosed packet as the facts its record holds.

    A withheld packet is written down too, because the decision is a completed
    answer a later reader needs. The record then holds the fault identity and
    the decision, and no content of the packet the decision withheld.
    """
    facts: dict[str, str | tuple[str, ...]] = {"form": PACKET_RECORD_FORM}
    for name, value in _packet_fields(diagnosis):
        facts[name.replace("_", " ")] = value
    facts[GATE_LABEL] = diagnosis.gate
    if not withheld(diagnosis):
        facts["confidence"] = diagnosis.confidence.value
    facts["advice"] = NO_ADVICE
    return facts


__all__ = [
    "CLAUSE_FIELDS",
    "DECISION_LABEL",
    "DIAGNOSIS_RECORD_FORM",
    "DISCLOSED",
    "DISCLOSURE_FIELD",
    "DISCLOSURE_LABEL",
    "FAILED",
    "FAILING_CLAUSE_FIELD",
    "FAILING_FAMILY_FIELD",
    "FIELD_SEPARATOR",
    "GATE_LABEL",
    "INTAKE_RECORD_FORM",
    "LIST_CAP",
    "NOT_LISTED",
    "NO_ADVICE",
    "NO_FAILING_OUTPUT",
    "OUTCOME_CLAUSE_FIELD",
    "OUTCOME_DIGEST_FIELD",
    "OUTCOME_FAILED_OUTPUT_FIELD",
    "OUTCOME_FIELDS",
    "OUTCOME_RECORD_FORM",
    "OUTCOME_RESULT_DIGEST_FIELD",
    "OUTCOME_STATUS_FIELD",
    "PACKET_FAULT_FIELD",
    "PACKET_LABELS",
    "PACKET_RECORD_FORM",
    "PASSED",
    "WITHHELD_FIELDS",
    "capped",
    "clause_entry",
    "clause_fields",
    "diagnosis_decision",
    "diagnosis_values",
    "failed_outputs",
    "failed_without_output",
    "failing_clauses",
    "intake_record_facts",
    "intake_values",
    "line",
    "no_failing_output_record_facts",
    "no_failing_output_values",
    "outcome_record_facts",
    "packet_record_facts",
    "unasked_adviser_values",
    "verification_values",
    "withheld",
    "withheld_decision",
]
