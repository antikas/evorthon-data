"""Diagnosis over a reconciled run: one packet read in full, and no adviser asked anything."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

import test_reconciliation as fixture
import test_reconciliation_workflow as run_fixture
from evorthon_data.verification import presentation as report
from evorthon_data.verification.core.fault import SMALL_CELL_FLOOR, packet_fields
from evorthon_data.verification.core.localisation import (
    LocalisationRefusalReason,
    LocalisationRefused,
)
from evorthon_data.verification.domain.contracts import DisclosureDecision, FaultClass
from evorthon_data.verification.enforcement.privacy import (
    PRIVACY_GATE_FORM,
    PrivacyRefusalReason,
    PrivacyRefused,
    gate_fault_packet,
)
from evorthon_data.verification.workflows import DiagnosisOutcome, diagnose_failed_output

OUTPUT_ID = fixture.OUTPUT_ID
# A case wide enough that the declared small-cell floor is cleared.
WIDE_ROWS = tuple(
    fixture.row(date(2026, 9, 1), f"customer-{index:03d}", date(2026, 8, 31), f"{10 + index}.00")
    for index in range(40)
)
DIVERGENT_ROWS = 6


def divergent(rows, count):
    """Return the rows with the first few carrying a different declared effective date.

    The divergence names a dimension the fault vocabulary decides a class from,
    so the packet built over it has something decided to disclose.
    """
    changed = list(rows)
    for index in range(count):
        changed[index] = {
            **changed[index],
            "effective-from": changed[index]["effective-from"] - timedelta(days=1),
        }
    return tuple(changed)


def wide_failure():
    return fixture.scenario(
        expected_rows=WIDE_ROWS, actual_rows=divergent(WIDE_ROWS, DIVERGENT_ROWS)
    )


def small_failure():
    """One failure whose cohort is smaller than the declared small-cell floor."""
    return fixture.scenario(
        expected_rows=WIDE_ROWS, actual_rows=divergent(WIDE_ROWS, SMALL_CELL_FLOOR - 1)
    )


def diagnosed(scenario=None, *, output_id: str = OUTPUT_ID) -> DiagnosisOutcome:
    prepared = run_fixture.Prepared(wide_failure() if scenario is None else scenario)
    return diagnose_failed_output(
        prepared.case,
        prepared.intake,
        prepared.reconcile(),
        output_id=output_id,
        candidate_runner=prepared.runner,
    )


def test_a_failed_output_is_diagnosed_into_one_gated_packet():
    outcome = diagnosed()

    assert outcome.output_id == OUTPUT_ID
    assert outcome.gate == PRIVACY_GATE_FORM
    assert outcome.packet.disclosure_decision is DisclosureDecision.DISCLOSE
    assert outcome.fault_class is outcome.packet.fault_class
    assert outcome.fault_class is not FaultClass.UNKNOWN


def test_the_reported_fields_are_the_packet_fields_the_core_writes():
    outcome = diagnosed()

    assert dict(outcome.fields) == dict(packet_fields(outcome.packet))


def test_the_words_a_reporting_surface_bounds_a_withheld_packet_by_are_the_core_s_own():
    """The surface names fields and a decision the core really writes.

    A reporting surface decides what a withheld packet is reported as, and it
    names those fields by the words the core wrote them under. This holds the
    two to each other, so a field the core renames cannot leave the surface
    silently reporting nothing.
    """
    outcome = diagnosed()
    written = packet_fields(outcome.packet)

    assert set(report.WITHHELD_FIELDS) <= set(written)
    assert report.DISCLOSURE_FIELD in written
    assert report.DISCLOSURE_LABEL == report.DISCLOSURE_FIELD.replace("_", " ")
    assert written[report.DISCLOSURE_FIELD] == report.DISCLOSED
    assert outcome.packet.disclosure_decision is DisclosureDecision.DISCLOSE


def test_a_diagnosis_asks_no_adviser_anything():
    outcome = diagnosed()

    assert outcome.advice is None


def test_the_packet_carries_no_row_key_or_declared_value_of_the_compared_material():
    scenario = wide_failure()
    outcome = diagnosed(scenario)
    carried = {row["customer-id"] for row in scenario.observation.rows}
    carried |= {str(row["daily-value"]) for row in scenario.observation.rows}
    carried |= {row["business-date"].isoformat() for row in scenario.observation.rows}

    written = "\n".join(outcome.fields.values())

    assert not [value for value in carried if value in written]


def test_an_output_the_run_does_not_report_as_failing_is_refused():
    with pytest.raises(LocalisationRefused) as raised:
        diagnosed(fixture.scenario())

    assert raised.value.reason is LocalisationRefusalReason.NOT_A_FAILED_OUTPUT


@pytest.mark.parametrize(
    "declared, build, expected",
    (
        ("small cell", small_failure, DisclosureDecision.WITHHOLD_SMALL_CELL),
        ("unknown class", fixture.value_failure, DisclosureDecision.WITHHOLD_UNKNOWN),
    ),
    ids=("small-cell", "unknown-class"),
)
def test_a_packet_the_disclosure_policy_withholds_is_a_completed_diagnosis(
    declared, build, expected
):
    """A withholding is a decision the diagnosis reports, not a refusal it raises.

    The packet still passes every rule that says what a packet may carry, so a
    caller receives a diagnosed output carrying the decision. Whether that
    packet may then cross to an adviser is the gate's own question, asked where
    the crossing happens.
    """
    outcome = diagnosed(build())

    assert outcome.packet.disclosure_decision is expected
    assert outcome.fields["disclosure_decision"] == expected.value
    assert outcome.gate == PRIVACY_GATE_FORM
    with pytest.raises(PrivacyRefused) as raised:
        gate_fault_packet(outcome.packet)
    assert raised.value.reason is PrivacyRefusalReason.DISCLOSURE_WITHHELD
