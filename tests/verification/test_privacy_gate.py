"""The privacy gate before an adviser boundary: every rejected shape and every bound."""
# evorthon-verifies: EVD-README-021
from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

import test_fault_packet as packets
import test_reconciliation as fixture
from evorthon_data.verification.core.fault import (
    MAX_CHECKPOINTS_PER_PATH,
    MAX_DISCLOSED_EXAMPLES,
    MAX_EVIDENCE_REFERENCES,
    MAX_FRONTIER_CHECKPOINTS,
    MAX_UNCOVERED_PATHS,
    build_fault_packet,
)
from evorthon_data.verification.domain.contracts import (
    ComparisonDimension,
    DisclosureDecision,
    FaultClass,
    Identity,
)
from evorthon_data.verification.enforcement.privacy import (
    PACKET_BOUNDS,
    PRIVACY_GATE_FORM,
    REFUSAL_KIND,
    GatedFaultPacket,
    PrivacyRefusalKind,
    PrivacyRefusalReason,
    PrivacyRefused,
    gate_fault_packet,
    inspect_fault_packet,
)

MARK = chr(58)
SLASH = chr(92)
QUOTE = chr(34)
BREAK = chr(10)
OUTPUT_ID = packets.OUTPUT_ID


def disclosing_evidence():
    """Return evidence whose cohort is large enough for the policy to disclose."""
    withheld = tuple(
        fixture.row(date(2026, 9, 4), f"customer-{index}", date(2026, 9, 3), "60.00")
        for index in range(5)
    )
    return packets.evidence_for(
        fixture.scenario(
            dimensions=fixture.without(ComparisonDimension.AGGREGATE),
            expected_rows=fixture.BASE_ROWS + withheld,
            actual_rows=fixture.BASE_ROWS,
        )
    )


def disclosing_packet():
    return build_fault_packet(disclosing_evidence())


def scoped(packet, injected: str):
    """Return the packet with one declared shape written into its scope."""
    return replace(packet, diagnostic_scope=f"output {OUTPUT_ID}; {injected}")


def refusal(record) -> PrivacyRefusalReason:
    with pytest.raises(PrivacyRefused) as raised:
        gate_fault_packet(record)
    return raised.value.reason


# --- The gate lets a bounded, disclosing packet through ---


def test_a_bounded_disclosing_packet_crosses_the_boundary():
    packet = disclosing_packet()
    gated = gate_fault_packet(packet)

    assert packet.disclosure_decision is DisclosureDecision.DISCLOSE
    assert isinstance(gated, GatedFaultPacket)
    assert gated.record is packet
    assert gated.bounds == PACKET_BOUNDS
    assert gated.gate == PRIVACY_GATE_FORM


DISCLOSING_CLASSES = (
    ("a shape difference", packets.schema_coercion),
    ("a key declaration difference", packets.key_declaration_coercion),
    ("a written format difference", packets.output_formatting),
    ("an ordering that is not deterministic", packets.nondeterministic_ordering),
    ("a declared context the run did not use", packets.replay_context_drift),
)


@pytest.mark.parametrize(
    "build",
    [build for _, build in DISCLOSING_CLASSES],
    ids=[name for name, _ in DISCLOSING_CLASSES],
)
def test_every_packet_the_policy_discloses_passes_the_gate_as_built(build):
    packet = build_fault_packet(build())

    assert packet.disclosure_decision is DisclosureDecision.DISCLOSE
    assert gate_fault_packet(packet).record is packet


# --- The rejected shapes ---


LOCAL_PATHS = (
    ("a drive path", "D" + MARK + "/estate/orders.csv"),
    ("a network share path", SLASH * 2 + "estate-server" + SLASH + "orders"),
    ("a user home path", "/" + "home" + "/analyst/orders.csv"),
    ("an absolute path", "/estate/extracts/orders.csv"),
    ("a local file address", "fi" + "le" + MARK + "//estate/orders.csv"),
    ("a remote address", "htt" + "p" + MARK + "//estate.example/orders"),
    ("a secure remote address", "htt" + "ps" + MARK + "//estate.example/orders"),
    ("a traversal", chr(46) * 2 + "/estate/orders.csv"),
    ("a backslash-relative path", "estate" + SLASH + "extracts" + SLASH + "orders.csv"),
)
CREDENTIALS = (
    ("a named secret", "the connection password is rotated by the environment"),
    ("a named key", "the api-key is rotated by the environment"),
    ("a presented token", "bearer " + "abcdefgh12345678"),
    ("a private key block", "-----BEGIN RSA PRIVATE KEY-----"),
    ("a key block of another kind", "-----BEGIN OPENSSH PUBLIC KEY-----"),
    ("a secret with a value written against it", "passwd=" + "Zq7Rt4Wm9Bx2Kd6Np3Vs"),
    (
        "a token written against the header that carries it",
        "authorization" + MARK + " bearer " + "Zq7Rt4Wm9Bx2Kd6Np3Vs",
    ),
)
RAW_ROWS = (
    ("a record separator", "one row" + BREAK + "another row"),
    ("a written object", "{" + QUOTE + "customer-id" + QUOTE + " 1}"),
    ("delimited fields", "customer-a|60|published"),
)
SINGLETON_VALUES = (
    ("a date", "the boundary is 2026-09-01"),
    ("a decimal", "the total is 60.00"),
    ("a quoted literal", "the key is " + QUOTE + "customer-a" + QUOTE),
    ("a value written against a name", "daily-value=60"),
)
REJECTED_SHAPES = (
    (PrivacyRefusalReason.LOCAL_PATH, LOCAL_PATHS),
    (PrivacyRefusalReason.CREDENTIAL, CREDENTIALS),
    (PrivacyRefusalReason.RAW_ROW, RAW_ROWS),
    (PrivacyRefusalReason.SINGLETON_VALUE, SINGLETON_VALUES),
)


@pytest.mark.parametrize(
    ("declared", "injected"),
    [(declared, injected) for declared, shapes in REJECTED_SHAPES for _, injected in shapes],
    ids=[f"{declared.value}-{name}" for declared, shapes in REJECTED_SHAPES for name, _ in shapes],
)
def test_every_rejected_shape_is_refused_before_the_boundary(declared, injected):
    assert refusal(scoped(disclosing_packet(), injected)) is declared


ALLOWED_TEXTS = (
    ("a rate written with a slash", "rows / second"),
    ("two named sides written with a slash", "input / output"),
)


@pytest.mark.parametrize(
    "allowed",
    [allowed for _, allowed in ALLOWED_TEXTS],
    ids=[name for name, _ in ALLOWED_TEXTS],
)
def test_a_declared_text_that_carries_no_rejected_shape_still_crosses(allowed):
    """A slash between two names counts things; it is not a path from a root."""
    carried = scoped(disclosing_packet(), allowed)

    assert gate_fault_packet(carried).record is carried


def test_a_rejected_shape_is_refused_wherever_the_packet_declares_it():
    packet = disclosing_packet()
    carried = replace(
        packet,
        supporting_evidence=(
            replace(packet.supporting_evidence[0], summary="rows read from D" + MARK + "/estate/orders.csv"),
        ),
    )

    assert refusal(carried) is PrivacyRefusalReason.LOCAL_PATH


REVERSIBLE_DIGESTS = (
    ("a name in a digest slot", "sha256" + MARK + "daily-output"),
    ("a fingerprint that is too short", "blake2b-256" + MARK + "0123abcd"),
    ("a value with no named algorithm", "customer-a"),
    ("a fingerprint that is not written in one case", "BLAKE2B-256" + MARK + "AB" * 32),
)


@pytest.mark.parametrize(
    "digest",
    [digest for _, digest in REVERSIBLE_DIGESTS],
    ids=[name for name, _ in REVERSIBLE_DIGESTS],
)
def test_a_digest_slot_that_is_not_an_opaque_fingerprint_is_refused(digest):
    packet = disclosing_packet()
    carried = replace(packet, result=Identity(packet.result.identifier, packet.result.version, digest))

    assert refusal(carried) is PrivacyRefusalReason.REVERSIBLE_DIGEST


def test_a_reversible_digest_is_refused_inside_the_evidence_it_stands_for():
    packet = disclosing_packet()
    carried = replace(
        packet,
        supporting_evidence=(
            replace(packet.supporting_evidence[0], digest="sha256" + MARK + "customer-a"),
        ),
    )

    assert refusal(carried) is PrivacyRefusalReason.REVERSIBLE_DIGEST


# --- The declared maximum shape ---


def test_the_declared_bounds_are_the_ones_this_product_ships():
    assert PACKET_BOUNDS.affected_clause_outcomes == 16
    assert PACKET_BOUNDS.evidence_references == 16
    assert PACKET_BOUNDS.frontier_checkpoints == 16
    assert PACKET_BOUNDS.uncovered_paths == 16
    assert PACKET_BOUNDS.checkpoints_per_path == 32
    assert (PACKET_BOUNDS.identifier_characters, PACKET_BOUNDS.text_characters) == (128, 320)


def test_the_packet_builder_stays_inside_every_bound_the_gate_enforces():
    """The two owners hold the same numbers, so a builder never emits an ungateable packet."""
    assert MAX_DISCLOSED_EXAMPLES <= PACKET_BOUNDS.evidence_references
    assert MAX_EVIDENCE_REFERENCES == PACKET_BOUNDS.evidence_references
    assert MAX_FRONTIER_CHECKPOINTS == PACKET_BOUNDS.frontier_checkpoints
    assert MAX_UNCOVERED_PATHS == PACKET_BOUNDS.uncovered_paths
    assert MAX_CHECKPOINTS_PER_PATH == PACKET_BOUNDS.checkpoints_per_path


BOUND_BREACHES = (
    (
        "more comparisons than the bound",
        lambda packet: replace(
            packet,
            affected_clause_outcome_ids=tuple(
                f"failing-clause-{index:02d}" for index in range(PACKET_BOUNDS.affected_clause_outcomes + 1)
            ),
        ),
    ),
    (
        "more evidence than the bound",
        lambda packet: replace(
            packet,
            supporting_evidence=tuple(
                replace(packet.supporting_evidence[0], evidence_id=f"observed-{index:02d}")
                for index in range(PACKET_BOUNDS.evidence_references + 1)
            ),
        ),
    ),
    (
        "text longer than the bound",
        lambda packet: replace(packet, diagnostic_scope="a" * (PACKET_BOUNDS.text_characters + 1)),
    ),
    (
        "an identifier longer than the bound",
        lambda packet: replace(packet, fault_id="a" * (PACKET_BOUNDS.identifier_characters + 1)),
    ),
)


@pytest.mark.parametrize(
    "breach",
    [breach for _, breach in BOUND_BREACHES],
    ids=[name for name, _ in BOUND_BREACHES],
)
def test_a_packet_larger_than_the_declared_shape_is_refused_rather_than_trimmed(breach):
    assert refusal(breach(disclosing_packet())) is PrivacyRefusalReason.DECLARED_BOUND_EXCEEDED


def test_a_packet_exactly_at_the_declared_shape_still_crosses():
    packet = disclosing_packet()
    filled = replace(
        packet,
        affected_clause_outcome_ids=tuple(
            f"failing-clause-{index:02d}" for index in range(PACKET_BOUNDS.affected_clause_outcomes)
        ),
        diagnostic_scope="a" * PACKET_BOUNDS.text_characters,
    )

    assert gate_fault_packet(filled).record is filled


# --- The disclosure decision is carried out at the boundary ---


def test_a_packet_the_policy_withheld_does_not_cross():
    withheld = build_fault_packet(packets.missing_population())

    assert withheld.disclosure_decision is DisclosureDecision.WITHHOLD_SMALL_CELL
    assert refusal(withheld) is PrivacyRefusalReason.DISCLOSURE_WITHHELD


def test_a_withheld_packet_is_still_readable_as_a_shape():
    withheld = build_fault_packet(packets.missing_population())

    assert inspect_fault_packet(withheld) is withheld


@pytest.mark.parametrize(
    "declared",
    [decision for decision in DisclosureDecision if decision is not DisclosureDecision.DISCLOSE],
    ids=[
        decision.value for decision in DisclosureDecision if decision is not DisclosureDecision.DISCLOSE
    ],
)
def test_every_decision_other_than_disclose_closes_the_boundary(declared):
    packet = disclosing_packet()
    withheld = replace(
        packet,
        fault_class=FaultClass.UNKNOWN if declared is DisclosureDecision.WITHHOLD_UNKNOWN else packet.fault_class,
        disclosure_decision=declared,
    )

    assert refusal(withheld) is PrivacyRefusalReason.DISCLOSURE_WITHHELD


# --- Integrity refusals ---


def test_a_record_that_is_not_a_packet_is_refused():
    assert refusal("a fault packet") is PrivacyRefusalReason.UNRESOLVED_PACKET


def test_a_packet_with_an_empty_declaration_is_refused():
    assert refusal(replace(disclosing_packet(), diagnostic_scope="   ")) is PrivacyRefusalReason.UNRESOLVED_PACKET


def test_a_packet_that_names_no_comparison_is_refused():
    assert (
        refusal(replace(disclosing_packet(), affected_clause_outcome_ids=()))
        is PrivacyRefusalReason.UNRESOLVED_PACKET
    )


def test_a_packet_that_names_no_evidence_for_what_it_reports_is_refused():
    assert (
        refusal(replace(disclosing_packet(), supporting_evidence=()))
        is PrivacyRefusalReason.UNRESOLVED_PACKET
    )


def test_a_class_and_a_decision_that_contradict_each_other_are_refused():
    assert (
        refusal(replace(disclosing_packet(), fault_class=FaultClass.UNKNOWN))
        is PrivacyRefusalReason.CONTRADICTORY_PACKET
    )


def test_an_undecided_class_declared_as_decided_is_refused():
    undecided = build_fault_packet(packets.undecided_value())

    assert (
        refusal(replace(undecided, disclosure_decision=DisclosureDecision.WITHHOLD_POLICY))
        is PrivacyRefusalReason.CONTRADICTORY_PACKET
    )


# --- Every refusal declares its kind ---


def test_every_declared_refusal_reason_declares_whether_it_defends_meaning_or_data():
    assert set(REFUSAL_KIND) == set(PrivacyRefusalReason)
    assert set(REFUSAL_KIND.values()) == set(PrivacyRefusalKind)


@pytest.mark.parametrize(
    "reason",
    sorted(PrivacyRefusalReason, key=lambda reason: reason.value),
    ids=[reason.value for reason in sorted(PrivacyRefusalReason, key=lambda reason: reason.value)],
)
def test_a_refusal_carries_the_kind_its_reason_declares(reason):
    raised = PrivacyRefused(reason, "packet", "one declared detail")

    assert raised.kind is REFUSAL_KIND[reason]


def test_the_two_integrity_reasons_are_the_only_ones_that_defend_meaning():
    integrity = {reason for reason, kind in REFUSAL_KIND.items() if kind is PrivacyRefusalKind.INTEGRITY}

    assert integrity == {
        PrivacyRefusalReason.UNRESOLVED_PACKET,
        PrivacyRefusalReason.CONTRADICTORY_PACKET,
    }


def test_the_gate_reads_a_packet_and_changes_nothing():
    packet = disclosing_packet()

    assert gate_fault_packet(packet).record == packet
    assert build_fault_packet(disclosing_evidence()) == packet
