"""Bounded reports of what a remediation workflow decided, and what an acceptance rests on.

Three surfaces are written here, and they follow the rule the report module
beside this one keeps: a report names what was decided and never carries the
material behind it. No hypothesis, no proposed fix, no rationale summary, no
row and no approved text of a case reaches a line written here. What does reach
a line is an identity, a digest, a closed word, a count and a capped list.

The disposition surface writes one recorded decision. The reported values and
the recorded facts are the same values, so the one a caller reads out of an
envelope is the one the record holds: only the record form and the written
record name differ between them.

The rerun surface writes what one rerun of a corrected candidate found. It says
green when every prior failure passes and every prior pass still does, red when
it does not, and it names the clauses behind either word. It accepts nothing.

The acceptance surface writes what a named human acceptance would rest on, and
upgrades nothing. A declared authority is written as declared. A case with a
failing clause is written with the clauses that failed and the family each one
answers for, so a run that failed nothing a comparison reported is read as more
than a status. A case with insufficient evidence is written with the clauses
that lack it. A localisation that is inferred or unknown is written with the
word the localisation carries.
No field here says a delivery was accepted: acceptance is a named person's act,
recorded elsewhere, and this surface only lays out the evidence in front of it.

This module reads workflow outcome types, the declared verification vocabulary
and the records this presentation component wrote. It never asks a workflow
anything, never decides a status or a class, and never promotes one.
"""
# evorthon-implements: EVD-README-038
# evorthon-implements: EVD-README-010
from __future__ import annotations

# evorthon-component: verification_presentation

from collections.abc import Mapping, Sequence

from evorthon_data.verification.domain.contracts import (
    DatasetProvenance,
    VerificationStatus,
)
from evorthon_data.verification.workflows.remediation import (
    APPROVING_DISPOSITIONS,
    HUMAN_DISPOSITIONS,
)

from evorthon_data.verification.presentation.report import (
    CLAUSE_FIELDS,
    FAILING_CLAUSE_FIELD,
    OUTCOME_CLAUSE_FIELD,
    OUTCOME_DIGEST_FIELD,
    OUTCOME_RESULT_DIGEST_FIELD,
    OUTCOME_STATUS_FIELD,
    capped,
    clause_fields,
    failing_clauses,
    line,
)

# The stable names of the record forms the remediation routes write.
DECISION_RECORD_FORM = "evorthon.verification.remediation.decision.record.v1"
RERUN_RECORD_FORM = "evorthon.verification.remediation.rerun.record.v1"

# What a report writes for a value nobody recorded.
NOTHING = "none"
# The two words a declared flag is written as.
FLAG_WORDS = {True: "yes", False: "no"}
# The two words one rerun is reported under. Green is the word for a rerun that
# corrected every prior failure and broke nothing; red is the word for any
# other completed rerun. Neither word accepts anything.
RERUN_WORDS = {True: "green", False: "red"}
# The words a caller offers for a disposition, and the two of them that approve
# work. Both are read off the workflow that owns them, so no surface restates
# either set.
HUMAN_DISPOSITION_WORDS = tuple(disposition.value for disposition in HUMAN_DISPOSITIONS)
APPROVING_DISPOSITION_WORDS = tuple(
    disposition.value for disposition in APPROVING_DISPOSITIONS
)

# The field of a clause line that carries the status the clause decided.
CLAUSE_STATUS = CLAUSE_FIELDS.index("status")
# The names the records this module writes and reads hold their facts under.
# The status a recorded run carries is named by the surface that writes a
# recorded outcome, and so are the fields of one read back here, so a reader
# and a writer of the same record cannot drift into two sets of names.
CASE_FIELD = "case"
CASE_VERSION_FIELD = "case version"
CASE_DIGEST_FIELD = "case digest"
DECISION_FIELD = "decision"
DISPOSITION_FIELD = "disposition"
ASSURANCE_FIELD = "assurance"
WORK_FIELD = "work"
RERUN_FIELD = "rerun"
UNANSWERED_FIELD = "unanswered"
# The fault a decision answers, and the fault a gated packet was written for.
# The two records name it differently, so both names are declared here.
DECISION_FAULT_FIELD = "fault"
FAULT_FIELD = "fault id"
LOCALISATION_FIELD = "localisation status"
# What a record name is written as: what was decided, and the rationale the
# decision rests on. A second decision on one fault carries its own rationale
# and so keeps its own record beside the first.
RECORD_KEY = "{disposition}-{rationale}"


def _identity_fields(name: str, identity) -> tuple[tuple[str, str], ...]:
    """Write one opaque identity as its identifier, its version and its digest."""
    if identity is None:
        return ((name, NOTHING), (f"{name} version", NOTHING), (f"{name} digest", NOTHING))
    return (
        (name, identity.identifier),
        (f"{name} version", identity.version),
        (f"{name} digest", identity.digest),
    )


def _decision_fields(outcome) -> tuple[tuple[str, str], ...]:
    """Write one recorded disposition as the facts both surfaces carry.

    Every field is an identity, a digest, a closed word or a count. The
    assurance class is the class the workflow recorded, written as it stands.
    """
    decision = outcome.decision
    presented = outcome.presented_owner_evidence
    certificate = outcome.presented_certificate
    return (
        *_identity_fields(CASE_FIELD, outcome.case),
        (DECISION_FIELD, decision.remediation_id),
        ("decision version", decision.version),
        (DISPOSITION_FIELD, decision.disposition.value),
        ("decided by", decision.decided_by.identifier),
        ("decided by version", decision.decided_by.version),
        ("decided by digest", decision.decided_by.digest),
        (ASSURANCE_FIELD, outcome.assurance.value),
        *_identity_fields("advice", decision.advice),
        *_identity_fields(DECISION_FAULT_FIELD, outcome.fault),
        *_identity_fields("approved work", decision.approved_work),
        ("fault open", FLAG_WORDS[outcome.fault_open]),
        ("discriminating tests", str(len(outcome.discriminating_tests))),
        ("requested evidence", str(len(outcome.requested_evidence))),
        ("owner presented", NOTHING if presented is None else presented.evidence_id),
        ("environment certificate", NOTHING if certificate is None else certificate.claim_id),
    )


def decision_key(outcome) -> str:
    """Return the plain name the record of one decision is held under.

    A fault identity is a composed logical name and cannot be a name a
    directory carries, so the key is what was decided and the rationale it
    rests on. Recording the same decision again writes the same record;
    deciding again on a fault that is still open writes another one beside it.
    """
    return RECORD_KEY.format(
        disposition=outcome.decision.disposition.value,
        rationale=outcome.decision.rationale.evidence_id,
    )


def remediation_values(outcome, record: str) -> tuple[tuple[str, object], ...]:
    """Report one recorded disposition: what was decided and where it was written."""
    return (*_decision_fields(outcome), ("record", record))


def remediation_record_facts(outcome) -> Mapping[str, str]:
    """Write down one recorded disposition as the facts its record holds."""
    return {"form": DECISION_RECORD_FORM, **dict(_decision_fields(outcome))}


def tracker_values(parent_item: object, remedy_item: object) -> tuple[tuple[str, object], ...]:
    """Report the tracker items one approving decision was projected onto."""
    return (
        ("parent item", NOTHING if parent_item is None else parent_item),
        ("remedy item", NOTHING if remedy_item is None else remedy_item),
    )


def _rerun_fields(rerun, decision: str) -> tuple[tuple[str, object], ...]:
    """Write one rerun as the facts both surfaces carry, with every list capped."""
    return (
        *_identity_fields(CASE_FIELD, rerun.case),
        (DECISION_FIELD, decision),
        (WORK_FIELD, rerun.work.identifier),
        (RERUN_FIELD, RERUN_WORDS[rerun.green]),
        (OUTCOME_STATUS_FIELD, rerun.contract.status.value),
        (OUTCOME_DIGEST_FIELD, rerun.contract.summary_digest),
        ("regression set", capped(rerun.regression_set)),
        ("corrected", capped(rerun.corrected)),
        ("restored defects", capped(rerun.restored_defects)),
        ("regressions", capped(rerun.regressions)),
        (UNANSWERED_FIELD, capped(rerun.unanswered)),
    )


def rerun_values(rerun, decision: str, record: str) -> tuple[tuple[str, object], ...]:
    """Report one rerun: the word it earned, the clauses behind it and its record."""
    return (
        *(
            (name, list(value) if isinstance(value, tuple) else value)
            for name, value in _rerun_fields(rerun, decision)
        ),
        ("record", record),
    )


def rerun_record_facts(rerun, decision: str) -> Mapping[str, str | tuple[str, ...]]:
    """Write down one rerun as the facts its record holds."""
    return {"form": RERUN_RECORD_FORM, **dict(_rerun_fields(rerun, decision))}


def _only(read: Mapping[str, tuple[str, ...]], name: str) -> str:
    """Read one fact a record states once, or say that the record states none."""
    held = read.get(name, ())
    return held[0] if len(held) == 1 else NOTHING


def _uncertain_clauses(read: Mapping[str, tuple[str, ...]]) -> tuple[tuple[str, ...], int]:
    """Name the clauses a recorded outcome answers with insufficient evidence.

    A line the clause form does not fit is not read as one. It is counted
    rather than guessed at, so a reader is told that a line went unread.
    """
    named: list[str] = []
    unread = 0
    for written in read.get(OUTCOME_CLAUSE_FIELD, ()):
        fields = clause_fields(written)
        if fields is None:
            unread += 1
        elif fields[CLAUSE_STATUS] == VerificationStatus.INSUFFICIENT_EVIDENCE.value:
            named.append(fields[0])
    return tuple(named), unread


def acceptance_values(
    case,
    outcome: Mapping[str, tuple[str, ...]],
    packets: Sequence[Mapping[str, tuple[str, ...]]],
    decisions: Sequence[Mapping[str, tuple[str, ...]]],
    reruns: Sequence[Mapping[str, tuple[str, ...]]],
    records: Sequence[str],
) -> tuple[tuple[str, object], ...]:
    """Report what a named human acceptance of one case would rest on.

    The status is the status the recorded outcome carries. The residual
    uncertainty is the clauses the outcome could not answer, the localisation
    word each gated packet carries, and the clauses a rerun left unanswered.
    Each decision is written with the disposition and the assurance class it
    was recorded under. The labels the evidence carries are the labels the case
    declares. Nothing is promoted, and no field says a delivery was accepted.
    """
    uncertain, unread = _uncertain_clauses(outcome)
    # The clauses the recorded run answered as failing, read through the one
    # reader of a recorded outcome. That reading is nothing where a clause line
    # is not one the writer wrote, and the unread count beside it is what says
    # so, because the same line is the one this surface could not read either.
    failing = failing_clauses(outcome)
    synthetic = sum(
        1
        for dataset in case.frozen_datasets
        if dataset.provenance is DatasetProvenance.SYNTHETIC
    )
    unanswered: list[str] = []
    for rerun in reruns:
        unanswered.extend(rerun.get(UNANSWERED_FIELD, ()))
    return (
        (CASE_FIELD, case.case_id),
        (CASE_VERSION_FIELD, case.version),
        (OUTCOME_STATUS_FIELD, _only(outcome, OUTCOME_STATUS_FIELD)),
        (OUTCOME_RESULT_DIGEST_FIELD, _only(outcome, OUTCOME_RESULT_DIGEST_FIELD)),
        ("evidence provenance", case.evidence_provenance.value),
        ("declared assurance", case.assurance.declared_level.value),
        ("owner presented records", str(len(case.assurance.owner_presented_evidence))),
        ("environment certificates", str(len(case.assurance.environment_certificate_claims))),
        ("synthetic datasets", str(synthetic)),
        (
            FAILING_CLAUSE_FIELD,
            list(
                capped(
                    ()
                    if failing is None
                    else tuple(line(clause, family) for clause, family in failing)
                )
            ),
        ),
        ("clauses without sufficient evidence", list(capped(uncertain))),
        ("unread clause lines", str(unread)),
        (
            "localisation",
            list(
                capped(
                    tuple(
                        line(_only(packet, FAULT_FIELD), _only(packet, LOCALISATION_FIELD))
                        for packet in packets
                    )
                )
            ),
        ),
        (
            "decisions",
            list(
                capped(
                    tuple(
                        line(
                            _only(decision, DECISION_FIELD),
                            _only(decision, DISPOSITION_FIELD),
                            _only(decision, ASSURANCE_FIELD),
                        )
                        for decision in decisions
                    )
                )
            ),
        ),
        (
            "reruns",
            list(
                capped(
                    tuple(
                        line(_only(rerun, WORK_FIELD), _only(rerun, RERUN_FIELD))
                        for rerun in reruns
                    )
                )
            ),
        ),
        ("unanswered clauses", list(capped(tuple(unanswered)))),
        ("records", list(capped(tuple(records)))),
    )


__all__ = [
    "APPROVING_DISPOSITION_WORDS",
    "ASSURANCE_FIELD",
    "CASE_DIGEST_FIELD",
    "CASE_FIELD",
    "CASE_VERSION_FIELD",
    "DECISION_FAULT_FIELD",
    "DECISION_FIELD",
    "DECISION_RECORD_FORM",
    "DISPOSITION_FIELD",
    "FLAG_WORDS",
    "HUMAN_DISPOSITION_WORDS",
    "NOTHING",
    "RERUN_RECORD_FORM",
    "RERUN_WORDS",
    "FAULT_FIELD",
    "acceptance_values",
    "decision_key",
    "remediation_record_facts",
    "remediation_values",
    "rerun_record_facts",
    "rerun_values",
    "tracker_values",
]
