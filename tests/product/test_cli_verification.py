"""The verification command routes: intake, verify and diagnose over one records root.

Every route is driven through the command surface itself, so the proof covers
what a caller actually runs: the words are parsed, the composition root resolves
the adapters an environment named, the verification workflows decide, and the
surface writes the result down. Nothing here reaches a network, a clock or a
real environment: the material is invented, it is laid out by the shipped
reference adapters' own writer, and every document sits under a scratch records
root.
"""
from __future__ import annotations

import ast
import json
import shutil
import sys
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from evorthon_data import cli, composition
from evorthon_data.presentation.use_case import ENVELOPE_FORM, EXIT_OK, EXIT_REFUSED
from evorthon_data.verification import presentation as report
from evorthon_data.verification.adapters import (
    CONFORMANCE_CANDIDATE,
    CONFORMANCE_DECLARED_OUTPUTS,
    CONFORMANCE_EVIDENCE,
    ReplayDeclaration,
    write_fixture_material,
)
from evorthon_data.verification.core.canonical import (
    RefusalReason as CanonicalisationRefusalReason,
    case_digest,
)
from evorthon_data.verification.core.reconciliation import ReconciliationRefusalReason
from evorthon_data.verification.enforcement.privacy import PrivacyRefusalReason
from evorthon_data.verification.enforcement.validation import (
    PolicyChangedAfterObservationError,
)
from evorthon_data.verification.enforcement.serialization import serialize_json, serialize_record
from evorthon_data.verification.ports.contracts import ProducedOutput
from evorthon_data.verification.workflows import (
    CanonicalisationRefusal,
    ContractRefusalReason,
    ContractRefused,
    IntakeRefusalReason,
    IntakeRefused,
    PortRefusal,
    ReconciliationRefused,
)

ROOT = Path(__file__).parents[2]
# The comparison fixtures are the one place a whole approved case is built, so
# this proof reads them rather than declaring a second one of its own.
CONTRACT_SOURCES = str(ROOT / "tests/verification")
if CONTRACT_SOURCES not in sys.path:
    sys.path.insert(0, CONTRACT_SOURCES)

import test_contract_engine as contract_fixture  # noqa: E402
import test_intake_workflow as intake_fixture  # noqa: E402
import test_reconciliation as parity_fixture  # noqa: E402

ROUTE_SOURCES = (ROOT / "src/evorthon_data/composition.py", ROOT / "src/evorthon_data/cli.py")
ENGAGEMENT = "eng-verification"
EVIDENCE_ADAPTER = "held-evidence"
CANDIDATE_ADAPTER = "declared-candidate"
HELD_DIRECTORY = "environment-owned-material"
CASE_DOCUMENT = f"{ENGAGEMENT}/case.json"
CONSTRAINT_DOCUMENT = ROOT / "tests/fixtures/synthetic/constraints/region-reference.json"
MATERIAL_DOCUMENT = f"{ENGAGEMENT}/material.json"
OUTPUT_ID = parity_fixture.OUTPUT_ID
# The clause a contract-family run fails, the family the case declares it
# under, and the clause such a run leaves unanswered. Neither clause is a
# difference between published rows, so a run that fails one of them names no
# failing output.
CONTRACT_CLAUSE = "operational"
CONTRACT_FAMILY = contract_fixture.FAMILY_BY_CLAUSE[CONTRACT_CLAUSE].value
OPEN_CLAUSE = "integrity"
# The closed decisions a diagnosis reports. Every route reads each one off the
# presentation surface that owns it, so a route source that spells one out has
# stated a decision of its own.
CLOSED_DECISIONS = (report.NO_FAILING_OUTPUT,)
# The characters a route is written from, by code point, so this file spells
# out no machine route of its own and the candidate scan finds nothing in it.
_STOP = chr(46)
_SEPARATOR = chr(47)
# The declared enumerations a route may never state a member of for itself, and
# the values a route may never build.
DOMAIN_ENUMERATIONS = (
    "VerificationStatus",
    "FaultClass",
    "ClauseFamily",
    "AssuranceLevel",
    "DisclosureDecision",
    "ComparisonDimension",
    "LocalisationStatus",
)
DOMAIN_VALUES = (
    "ClauseOutcome",
    "ClauseExecution",
    "ClauseReconciliation",
    "VerificationResult",
    "FaultRecord",
    "DeliveryContractOutcome",
)
# A case wide enough that no reader could mistake a bounded report for a dump.
WIDE_ROWS = tuple(
    parity_fixture.row(
        date(2026, 9, 1), f"customer-{index:03d}", date(2026, 8, 31), f"{10 + index}.00"
    )
    for index in range(40)
)
DIVERGENT_ROWS = 6


def written(value):
    """Write one typed row value in the form a declared document carries it."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def written_rows(rows):
    return [{name: written(value) for name, value in row.items()} for row in rows]


def produced_from(output) -> ProducedOutput:
    return ProducedOutput(
        output_id=output.output_id,
        version=output.version,
        content_digest=output.content_digest,
        format_digest=output.format_digest,
        row_count=output.row_count,
    )


def divergent(rows, count):
    """Return the rows with the first few carrying a different declared effective date.

    The divergence is in a dimension the fault vocabulary can name, so the
    packet a diagnosis builds over it carries a decided class and the
    disclosure policy lets it out. A measure that simply differs is a real
    divergence too, but it decides no class, and a packet with nothing decided
    to disclose is withheld.
    """
    changed = list(rows)
    for index in range(count):
        changed[index] = {
            **changed[index],
            "effective-from": changed[index]["effective-from"] - timedelta(days=1),
        }
    return tuple(changed)


def wide_scenario():
    return parity_fixture.scenario(
        expected_rows=WIDE_ROWS, actual_rows=divergent(WIDE_ROWS, DIVERGENT_ROWS)
    )


def contract_scenario(scenario=None):
    """Return one scenario whose case declares every non-parity clause family."""
    scenario = parity_fixture.scenario() if scenario is None else scenario
    return replace(scenario, case=contract_fixture.contract_case(scenario.case))


def contract_observations(failing: str = "", unobserved: str = ""):
    """Return the declared facts one run answers its non-parity clauses over.

    Every clause is answered over facts that meet it, except the one named as
    failing, which is answered over facts that do not, and the one named as
    unobserved, which is not answered at all and so stays open. None of them is
    a difference between published rows, so a run that fails one of them names
    no failing output.
    """
    return [
        {
            "clause": clause_id,
            "values": dict(
                contract_fixture.FAILING_FACTS[clause_id]
                if clause_id == failing
                else contract_fixture.PASSING_FACTS[clause_id]
            ),
        }
        for clause_id in contract_fixture.CONTRACT_CLAUSE_IDS
        if clause_id != unobserved
    ]


def passing_clause_observations():
    return contract_observations()


def declared(path: Path, document) -> None:
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="ascii", newline="\n"
    )


def seeded(base: Path, scenario, *, clauses=()):
    """Lay one whole engagement out under a scratch repository and return its case."""
    case = intake_fixture.with_stored_evidence_digests(scenario.case)
    engagement = base / "work" / ENGAGEMENT
    engagement.mkdir(parents=True, exist_ok=True)
    write_fixture_material(
        base / "work" / HELD_DIRECTORY,
        evidence=(
            *CONFORMANCE_EVIDENCE,
            *(
                intake_fixture.stored(reference)
                for reference in intake_fixture.declared_evidence(case)
            ),
        ),
        candidate=CONFORMANCE_CANDIDATE,
        declared_outputs=(
            CONFORMANCE_DECLARED_OUTPUTS,
            ReplayDeclaration(
                case_id=case.case_id,
                case_version=case.version,
                case_digest=case_digest(case),
                outputs=(produced_from(scenario.observation.output),),
            ),
        ),
    )
    (engagement / "case.json").write_text(serialize_json(case), encoding="ascii", newline="\n")
    declared(
        engagement / "adapters.json",
        {
            "form": composition.ADAPTER_CONFIGURATION_FORM,
            "adapters": {
                EVIDENCE_ADAPTER: {"family": "fixture", "directory": HELD_DIRECTORY},
                CANDIDATE_ADAPTER: {"family": "fixture", "directory": HELD_DIRECTORY},
            },
        },
    )
    declared(
        engagement / "material.json",
        {
            "form": composition.RUN_MATERIAL_FORM,
            "expected": [
                {
                    "output": case.expected_outputs[0].output_id,
                    "rows": written_rows(scenario.expected.rows),
                }
            ],
            "observed": [
                {
                    "output": serialize_record(scenario.observation.output),
                    "rows": written_rows(scenario.observation.rows),
                }
            ],
            "clauses": list(clauses),
        },
    )
    return case


def words(name: str, base: Path, *arguments):
    """The words that drive one verification route against one scratch repository."""
    return [
        "verification",
        name,
        "--repository",
        str(base),
        "--engagement",
        ENGAGEMENT,
        "--case",
        CASE_DOCUMENT,
        "--evidence-adapter",
        EVIDENCE_ADAPTER,
        "--candidate-adapter",
        CANDIDATE_ADAPTER,
        *arguments,
    ]


def verify_words(base: Path, *arguments):
    return words("verify", base, "--material", MATERIAL_DOCUMENT, *arguments)


def diagnose_words(base: Path, output_id: str = OUTPUT_ID, *arguments):
    return words(
        "diagnose-failure", base, "--material", MATERIAL_DOCUMENT, "--output", output_id, *arguments
    )


def run(capsys, argv):
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def machine(capsys, argv):
    code, out, err = run(capsys, [*argv, "--json"])
    return code, json.loads(out), out, err


def prepared(capsys, tmp_path, scenario=None, *, clauses=()):
    """One seeded repository whose case has been taken in and accepted."""
    scenario = parity_fixture.scenario() if scenario is None else scenario
    case = seeded(tmp_path, scenario, clauses=clauses)
    code, _, error = run(capsys, words("intake-case", tmp_path))
    assert (code, error) == (EXIT_OK, "")
    return case


def verified(capsys, tmp_path, scenario=None, *, clauses=()):
    case = prepared(capsys, tmp_path, scenario, clauses=clauses)
    code, payload, _, _ = machine(capsys, verify_words(tmp_path))
    assert code == EXIT_OK
    return case, payload["result"]


def case_record(base: Path, case, name: str) -> Path:
    return base / "work" / ENGAGEMENT / composition.CASE_DIRECTORY / case.case_id / name


def refused(capsys, argv):
    """Drive one route that must refuse and return the error it wrote."""
    code, payload, _, _ = machine(capsys, argv)
    assert code == EXIT_REFUSED
    assert payload["form"] == ENVELOPE_FORM
    assert payload["status"] == "refused"
    assert payload["exit code"] == EXIT_REFUSED
    assert set(payload) == {"form", "command", "status", "exit code", "error"}
    assert set(payload["error"]) == {"reason", "detail"}
    assert payload["error"]["reason"] in {reason.value for reason in composition.RefusalReason}
    return payload["error"]


def declared_document(base: Path, name: str):
    path = base / "work" / ENGAGEMENT / name
    return path, json.loads(path.read_text(encoding="ascii"))


def enumeration_members(path: Path) -> list[str]:
    """Name every declared enumeration member one source states for itself."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        f"{node.value.id}.{node.attr}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in DOMAIN_ENUMERATIONS
    ]


def constructed_values(path: Path) -> list[str]:
    """Name every declared verification value one source builds for itself."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in DOMAIN_VALUES
    ]


def test_the_command_surface_carries_every_declared_verification_route(capsys):
    with pytest.raises(SystemExit) as exited:
        cli.main(["verification", "--help"])

    printed = capsys.readouterr().out
    assert exited.value.code == EXIT_OK
    declared = {
        "intake-case",
        "verify",
        "diagnose-failure",
        "record-remediation",
        "rerun",
        "acceptance-evidence",
    }
    assert declared <= set(printed.split())
    assert set(cli.VERIFICATION_ROUTES) == declared
    assert set(cli.ROUTE_TABLES) == {"use-case", "verification"}


@pytest.mark.parametrize(
    ("route", "options"),
    [
        ("intake-case", ("--case", "--evidence-adapter", "--candidate-adapter")),
        ("verify", ("--case", "--material", "--evidence-adapter", "--candidate-adapter")),
        ("diagnose-failure", ("--case", "--material", "--output", "--candidate-adapter")),
    ],
)
def test_every_verification_route_declares_the_words_it_takes(capsys, route, options):
    with pytest.raises(SystemExit) as exited:
        cli.main(["verification", route, "--help"])

    printed = capsys.readouterr().out
    assert exited.value.code == EXIT_OK
    for option in options:
        assert option in printed


def test_an_approved_case_is_taken_in_and_its_receipts_are_recorded(capsys, tmp_path):
    case = seeded(tmp_path, parity_fixture.scenario())

    code, payload, _, error = machine(capsys, words("intake-case", tmp_path))

    assert (code, error) == (EXIT_OK, "")
    reported = payload["result"]
    assert payload["command"] == "verification intake-case"
    assert reported["case"] == case.case_id
    assert reported["receipt digests"]
    path = case_record(tmp_path, case, composition.INTAKE_RECORD)
    held = composition.read_case_record(path, report.INTAKE_RECORD_FORM)
    assert held["intake digest"] == (reported["intake digest"],)
    assert list(held["receipt"]) == reported["receipt digests"]


def test_a_reproduced_run_verifies_as_passing(capsys, tmp_path):
    case, reported = verified(capsys, tmp_path)

    assert reported["status"] == "pass"
    assert reported["failed clauses"] == []
    path = case_record(tmp_path, case, composition.OUTCOME_RECORD)
    held = composition.read_case_record(path, report.OUTCOME_RECORD_FORM)
    assert held["status"] == ("pass",)
    assert held["outcome digest"] == (reported["outcome digest"],)


def test_a_diverging_run_reports_a_mismatch_and_still_completes(capsys, tmp_path):
    case, reported = verified(capsys, tmp_path, parity_fixture.value_failure())

    assert reported["status"] == "fail"
    assert reported["failed clauses"] == [parity_fixture.CLAUSE_ID]
    assert reported["failed outputs"] == [OUTPUT_ID]
    held = composition.read_case_record(
        case_record(tmp_path, case, composition.OUTCOME_RECORD), report.OUTCOME_RECORD_FORM
    )
    assert held["failed output"] == (OUTPUT_ID,)


def test_a_clause_with_no_observation_reports_insufficient_evidence_and_completes(
    capsys, tmp_path
):
    _, reported = verified(capsys, tmp_path, contract_scenario())

    assert reported["status"] == "insufficient-evidence"
    assert reported["unresolved clauses"] == list(contract_fixture.CONTRACT_CLAUSE_IDS)
    assert reported["failed clauses"] == []


def test_a_whole_contract_answered_over_observed_facts_verifies_as_passing(capsys, tmp_path):
    _, reported = verified(
        capsys, tmp_path, contract_scenario(), clauses=passing_clause_observations()
    )

    assert reported["status"] == "pass"
    assert reported["unresolved clauses"] == []


def test_a_case_document_the_validator_refuses_is_refused_as_invalid(capsys, tmp_path):
    seeded(tmp_path, parity_fixture.scenario())
    path, document = declared_document(tmp_path, "case.json")
    document["record"]["case_id"] = ""
    path.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="ascii", newline="\n")

    error = refused(capsys, words("intake-case", tmp_path))

    assert error["reason"] == composition.RefusalReason.MALFORMED_RECORD.value
    assert "validator" in error["detail"]


def test_an_adapter_identity_no_configuration_names_is_refused(capsys, tmp_path):
    seeded(tmp_path, parity_fixture.scenario())
    argv = words("intake-case", tmp_path)
    argv[argv.index("--evidence-adapter") + 1] = "an-identity-nothing-names"

    error = refused(capsys, argv)

    assert error["reason"] == composition.RefusalReason.MALFORMED_VALUE.value


def test_an_adapter_directory_outside_the_records_root_is_refused(capsys, tmp_path):
    seeded(tmp_path, parity_fixture.scenario())
    path, document = declared_document(tmp_path, "adapters.json")
    document["adapters"][EVIDENCE_ADAPTER]["directory"] = (
        _STOP + _STOP + _SEPARATOR + HELD_DIRECTORY
    )
    declared(path, document)

    error = refused(capsys, words("intake-case", tmp_path))

    assert error["reason"] == composition.RefusalReason.RECORD_OUTSIDE_WORK.value


def test_an_adapter_that_holds_no_conformance_material_is_refused_with_the_findings(
    capsys, tmp_path
):
    seeded(tmp_path, parity_fixture.scenario())
    (tmp_path / "work" / "empty-material").mkdir()
    path, document = declared_document(tmp_path, "adapters.json")
    document["adapters"][EVIDENCE_ADAPTER]["directory"] = "empty-material"
    declared(path, document)

    error = refused(capsys, words("intake-case", tmp_path))

    assert error["reason"] == composition.RefusalReason.MALFORMED_RECORD.value
    assert "read_evidence" in error["detail"]


def test_an_adapter_family_the_product_does_not_ship_is_refused(capsys, tmp_path):
    seeded(tmp_path, parity_fixture.scenario())
    path, document = declared_document(tmp_path, "adapters.json")
    document["adapters"][CANDIDATE_ADAPTER]["family"] = "an-unshipped-family"
    declared(path, document)

    error = refused(capsys, words("intake-case", tmp_path))

    assert error["reason"] == composition.RefusalReason.MALFORMED_VALUE.value


def test_a_case_whose_stored_evidence_was_altered_is_refused_at_intake(capsys, tmp_path):
    case = seeded(tmp_path, parity_fixture.scenario())
    reference = intake_fixture.declared_evidence(case)[0]
    held = (
        tmp_path
        / "work"
        / HELD_DIRECTORY
        / "evidence"
        / reference.evidence_id
        / f"{reference.version}.content"
    )
    held.write_bytes(b"material an approved case never digested\n")

    error = refused(capsys, words("intake-case", tmp_path))

    assert error["reason"] == composition.RefusalReason.EVIDENCE_DIGEST_MISMATCH.value
    assert "intake refused the case" in error["detail"]


def test_a_records_root_outside_the_work_directory_is_refused(capsys, tmp_path):
    seeded(tmp_path, parity_fixture.scenario())
    argv = words("intake-case", tmp_path)
    argv[argv.index("--repository") + 2 : argv.index("--repository") + 2] = [
        "--records-root",
        "elsewhere",
    ]

    error = refused(capsys, argv)

    assert error["reason"] == composition.RefusalReason.RECORD_OUTSIDE_WORK.value


def test_a_failed_output_is_diagnosed_into_a_gated_packet(capsys, tmp_path):
    case, _ = verified(capsys, tmp_path, wide_scenario())

    code, payload, _, error = machine(capsys, diagnose_words(tmp_path))

    assert (code, error) == (EXIT_OK, "")
    reported = payload["result"]
    assert payload["command"] == "verification diagnose-failure"
    assert reported["disclosure decision"] == "disclose"
    assert reported["advice"] == report.NO_ADVICE
    assert reported["gate"]
    held = composition.read_case_record(
        case_record(tmp_path, case, composition.PACKET_RECORD.format(output=OUTPUT_ID)),
        report.PACKET_RECORD_FORM,
    )
    assert held["fault class"] == (reported["fault class"],)
    assert held["advice"] == (report.NO_ADVICE,)


def test_a_packet_the_disclosure_policy_withholds_is_reported_and_written_bounded(
    capsys, tmp_path
):
    """A withholding is a completed diagnosis: the decision is the answer.

    The route reports which fault this is and the decision the policy made, and
    nothing the packet observed reaches either the report or the record. The
    scope with its counts, how far the lineage narrowed the fault and how much
    evidence stands on each side are all left out, because a reader who may not
    have the packet may not have those either.
    """
    case, _ = verified(capsys, tmp_path, parity_fixture.value_failure())

    code, payload, _, error = machine(capsys, diagnose_words(tmp_path))

    assert (code, error) == (EXIT_OK, "")
    reported = payload["result"]
    assert reported["disclosure decision"] != report.DISCLOSED
    assert reported["fault class"] and reported["fault id"]
    withheld_labels = {name.replace("_", " ") for name in report.WITHHELD_FIELDS}
    assert {"diagnostic scope", "localisation status", "confidence"}.isdisjoint(reported)
    assert withheld_labels <= set(reported)
    held = composition.read_case_record(
        case_record(tmp_path, case, composition.PACKET_RECORD.format(output=OUTPUT_ID)),
        report.PACKET_RECORD_FORM,
    )
    assert held[report.DISCLOSURE_LABEL] == (reported["disclosure decision"],)
    assert withheld_labels <= set(held)
    assert {"diagnostic scope", "localisation status", "confidence"}.isdisjoint(held)


def test_a_contract_failure_with_no_failing_output_is_diagnosed_as_a_closed_decision(
    capsys, tmp_path
):
    """A run that failed with no output to answer for is a completed diagnosis.

    The clause that failed was answered over the facts the run declared, so the
    parity comparison named no output and there is no packet to build. The
    route reports the decision, the family that failed and the clause it is,
    writes that down, and carries no packet content and no fault of any kind
    into either.
    """
    case, reported = verified(
        capsys,
        tmp_path,
        contract_scenario(),
        clauses=contract_observations(failing=CONTRACT_CLAUSE),
    )
    assert (reported["status"], reported["failed outputs"]) == (report.FAILED, [])

    code, written, error = run(capsys, diagnose_words(tmp_path))
    assert (code, error) == (EXIT_OK, "")
    assert report.NO_FAILING_OUTPUT in written
    code, payload, _, error = machine(capsys, diagnose_words(tmp_path))

    assert (code, error) == (EXIT_OK, "")
    diagnosed = payload["result"]
    assert diagnosed[report.DECISION_LABEL] == report.NO_FAILING_OUTPUT
    assert diagnosed[report.FAILING_FAMILY_FIELD] == [CONTRACT_FAMILY]
    assert diagnosed[report.FAILING_CLAUSE_FIELD] == reported["failed clauses"]
    assert diagnosed["advice"] == report.NO_ADVICE
    assert report.PACKET_LABELS.isdisjoint(diagnosed)
    held = composition.read_case_record(
        case_record(tmp_path, case, composition.DIAGNOSIS_RECORD), report.DIAGNOSIS_RECORD_FORM
    )
    assert held[report.DECISION_LABEL] == (report.NO_FAILING_OUTPUT,)
    assert held[report.FAILING_FAMILY_FIELD] == (CONTRACT_FAMILY,)
    assert held[report.FAILING_CLAUSE_FIELD] == tuple(reported["failed clauses"])
    assert report.PACKET_LABELS.isdisjoint(held)


def test_a_recorded_outcome_whose_clause_lines_are_not_the_declared_form_is_refused(
    capsys, tmp_path
):
    """A line the writer did not write is not read as one and not guessed at either.

    The clauses that failed are read back off the record the run wrote. A line
    the declared clause form does not fit makes the whole reading nothing, so
    the route refuses the record rather than reporting a reading with a line
    quietly dropped.
    """
    case, _ = verified(
        capsys,
        tmp_path,
        contract_scenario(),
        clauses=contract_observations(failing=CONTRACT_CLAUSE),
    )
    path = case_record(tmp_path, case, composition.OUTCOME_RECORD)
    held = composition.read_case_record(path, report.OUTCOME_RECORD_FORM)
    composition.store_case_record(
        path, {**held, report.OUTCOME_CLAUSE_FIELD: ("a line no writer here wrote",)}
    )

    error = refused(capsys, diagnose_words(tmp_path))

    assert error["reason"] == composition.RefusalReason.MALFORMED_RECORD.value


def test_a_diagnosis_of_an_output_no_recorded_outcome_reports_as_failing_is_refused(
    capsys, tmp_path
):
    """A run that failed nothing at all has nothing for a diagnosis to answer for."""
    verified(capsys, tmp_path)

    error = refused(capsys, diagnose_words(tmp_path))

    assert error["reason"] == composition.RefusalReason.MALFORMED_VALUE.value
    assert "failing" in error["detail"]


def test_a_recorded_outcome_that_answers_for_another_run_is_refused(capsys, tmp_path):
    case, _ = verified(capsys, tmp_path, wide_scenario())
    path = case_record(tmp_path, case, composition.OUTCOME_RECORD)
    held = composition.read_case_record(path, report.OUTCOME_RECORD_FORM)
    changed = {
        name: ("blake2b-256:" + "0" * 64,) if name == composition.RESULT_DIGEST_FIELD else value
        for name, value in held.items()
    }
    composition.store_case_record(path, changed)

    error = refused(capsys, diagnose_words(tmp_path))

    assert error["reason"] == composition.RefusalReason.DIGEST_MISMATCH.value


def test_no_row_key_or_value_of_a_wide_case_reaches_either_output(capsys, tmp_path):
    scenario = wide_scenario()
    prepared(capsys, tmp_path, scenario)
    carried = {row["customer-id"] for row in scenario.observation.rows}
    carried |= {str(row["daily-value"]) for row in scenario.observation.rows}
    carried |= {row["business-date"].isoformat() for row in scenario.observation.rows}

    written_out = ""
    for argv in (verify_words(tmp_path), diagnose_words(tmp_path)):
        for machine_words in ([], ["--json"]):
            code, out, error = run(capsys, [*argv, *machine_words])
            assert (code, error) == (EXIT_OK, "")
            written_out += out

    assert len(scenario.observation.rows) == len(WIDE_ROWS)
    assert not [value for value in carried if value in written_out]


def test_every_list_a_route_reports_stays_inside_the_declared_cap(capsys, tmp_path):
    _, reported = verified(
        capsys, tmp_path, contract_scenario(), clauses=passing_clause_observations()
    )

    for value in reported.values():
        if isinstance(value, list):
            assert len(value) <= report.LIST_CAP + 1
    assert report.capped(tuple(str(index) for index in range(20))) == (
        *(str(index) for index in range(report.LIST_CAP)),
        report.NOT_LISTED.format(count=20 - report.LIST_CAP, cap=report.LIST_CAP),
    )


def stated_decisions(written: str) -> list[str]:
    """Name every closed decision one source spells out for itself."""
    return [decision for decision in CLOSED_DECISIONS if decision in written]


def test_the_root_and_the_command_surface_state_no_verification_outcome_of_their_own():
    for path in ROUTE_SOURCES:
        assert enumeration_members(path) == []
        assert constructed_values(path) == []


def test_the_root_and_the_command_surface_state_no_closed_decision_of_their_own():
    """The decision a diagnosis reports is read off its owner, not written here."""
    for path in ROUTE_SOURCES:
        assert stated_decisions(path.read_text(encoding="utf-8")) == []


def test_a_stated_closed_decision_reddens_the_no_decision_assertion(tmp_path):
    mirror = tmp_path / "composition.py"
    shutil.copyfile(ROOT / "src/evorthon_data/composition.py", mirror)
    with mirror.open("a", encoding="utf-8") as written_source:
        written_source.write(
            f'\n\ndef _injected():\n    return "{report.NO_FAILING_OUTPUT}"\n'
        )

    assert stated_decisions(mirror.read_text(encoding="utf-8")) == [report.NO_FAILING_OUTPUT]


def test_a_stated_verification_outcome_reddens_the_no_outcome_assertion(tmp_path):
    mirror = tmp_path / "composition.py"
    shutil.copyfile(ROOT / "src/evorthon_data/composition.py", mirror)
    with mirror.open("a", encoding="utf-8") as written_source:
        written_source.write(
            "\n\ndef _injected():\n"
            "    return VerificationStatus.PASS, ClauseOutcome('a', 'v1')\n"
        )

    assert enumeration_members(mirror) == ["VerificationStatus.PASS"]
    assert constructed_values(mirror) == ["ClauseOutcome"]


def test_every_record_a_route_writes_sits_under_the_records_root(capsys, tmp_path):
    case, _ = verified(capsys, tmp_path, wide_scenario())
    code, _, error = run(capsys, diagnose_words(tmp_path))
    assert (code, error) == (EXIT_OK, "")

    records = tmp_path / "work"
    written_records = sorted(
        path for path in records.rglob("*.md") if path.is_file()
    )
    assert written_records == sorted(
        (
            case_record(tmp_path, case, composition.INTAKE_RECORD),
            case_record(tmp_path, case, composition.OUTCOME_RECORD),
            case_record(tmp_path, case, composition.PACKET_RECORD.format(output=OUTPUT_ID)),
        )
    )
    for path in written_records:
        assert path.read_text(encoding="ascii").endswith("\n")


def test_a_record_that_is_not_its_own_canonical_projection_is_refused(capsys, tmp_path):
    case, _ = verified(capsys, tmp_path, wide_scenario())
    path = case_record(tmp_path, case, composition.OUTCOME_RECORD)
    path.write_text(path.read_text(encoding="ascii") + "a line no projection writes\n", encoding="ascii")

    error = refused(capsys, diagnose_words(tmp_path))

    assert error["reason"] == composition.RefusalReason.MALFORMED_RECORD.value


# --- what a refusal detail may carry, which refusals a route reports, and where a
# --- document may name a place -----------------------------------------------

# A written value that reads like held data, so a refusal that echoed it would
# be unmistakable. It is invented and names no system.
UNREADABLE_VALUE = "account-88213344-sensitive"
DATE_FIELD = "business-date"


def test_a_row_value_its_field_cannot_take_is_refused_without_carrying_the_value(
    capsys, tmp_path
):
    prepared(capsys, tmp_path, wide_scenario())
    path, document = declared_document(tmp_path, "material.json")
    document["observed"][0]["rows"][0][DATE_FIELD] = UNREADABLE_VALUE
    declared(path, document)

    error = refused(capsys, verify_words(tmp_path))

    assert error["reason"] == composition.RefusalReason.MALFORMED_VALUE.value
    assert DATE_FIELD in error["detail"]
    assert "date" in error["detail"]
    assert UNREADABLE_VALUE not in error["detail"]


def test_the_value_a_refusal_withholds_is_one_the_reading_error_would_have_carried():
    with pytest.raises(ValueError) as raised:
        date.fromisoformat(UNREADABLE_VALUE)

    assert UNREADABLE_VALUE in str(raised.value)


def test_a_request_document_the_generator_refuses_carries_no_written_value(capsys, tmp_path):
    request = tmp_path / "request.json"
    document = json.loads(CONSTRAINT_DOCUMENT.read_text(encoding="ascii"))
    document["constraints"]["fields"][0]["rule"] = UNREADABLE_VALUE
    declared(request, document)

    code, payload, _, _ = machine(
        capsys,
        [
            "use-case",
            "synthesise-dataset",
            "--request",
            str(request),
            "--seed",
            "a-declared-seed",
            "--generator-version",
            "1.0.0",
        ],
    )

    assert code == EXIT_REFUSED
    assert payload["error"]["reason"] == composition.RefusalReason.MALFORMED_VALUE.value
    assert UNREADABLE_VALUE not in payload["error"]["detail"]


def test_a_case_with_no_recorded_outcome_is_refused_as_a_record_nobody_holds(capsys, tmp_path):
    prepared(capsys, tmp_path, wide_scenario())

    error = refused(capsys, diagnose_words(tmp_path))

    assert error["reason"] == composition.RefusalReason.RECORD_NOT_HELD.value


def test_an_engagement_with_no_adapter_configuration_is_refused_the_same_way(capsys, tmp_path):
    seeded(tmp_path, parity_fixture.scenario())
    (tmp_path / "work" / ENGAGEMENT / "adapters.json").unlink()

    error = refused(capsys, words("intake-case", tmp_path))

    assert error["reason"] == composition.RefusalReason.RECORD_NOT_HELD.value


def test_every_declared_workflow_refusal_is_reported_under_one_declared_reason():
    """Each closed workflow reason is either carried as a refusal or reported as itself.

    The one privacy reason no route carries is the withheld disclosure: every
    route that holds a withheld packet reports the decision as the completed
    answer it is, so that reason is named as reported rather than mapped to a
    refusal word, and the two sets never overlap.
    """
    assert set(composition.INTAKE_REASONS) == set(IntakeRefusalReason)
    assert set(composition.PRIVACY_REASONS) | composition.REPORTED_PRIVACY_REASONS == set(
        PrivacyRefusalReason
    )
    assert not set(composition.PRIVACY_REASONS) & composition.REPORTED_PRIVACY_REASONS
    assert composition.REPORTED_PRIVACY_REASONS == {PrivacyRefusalReason.DISCLOSURE_WITHHELD}
    assert set(composition.INTAKE_REASONS.values()) <= set(composition.RefusalReason)
    assert set(composition.PRIVACY_REASONS.values()) <= set(composition.RefusalReason)


@pytest.mark.parametrize(
    "refusal",
    [
        ReconciliationRefused(
            ReconciliationRefusalReason.UNRESOLVED_ACTUAL_OUTPUT, "a-subject", "a declared reason"
        ),
        ContractRefused(
            ContractRefusalReason.UNDECLARED_CLAUSE_FAMILY, "a-subject", "a declared reason"
        ),
        PolicyChangedAfterObservationError("the declared policy moved after observation"),
        PortRefusal("the environment cannot answer for the frozen facts"),
        CanonicalisationRefusal(
            CanonicalisationRefusalReason.UNSUPPORTED_TYPE, "a declared reason"
        ),
    ],
    ids=lambda refusal: type(refusal).__name__,
)
def test_every_named_engine_refusal_reaches_the_envelope(capsys, tmp_path, monkeypatch, refusal):
    prepared(capsys, tmp_path, wide_scenario())

    def refusing(*arguments, **declared):
        raise refusal

    monkeypatch.setattr(composition, "reconcile_run", refusing)

    error = refused(capsys, verify_words(tmp_path))

    assert error["reason"] == composition.RefusalReason.MALFORMED_VALUE.value
    assert "a verification run refused" in error["detail"]


def test_an_error_no_engine_declares_is_not_reported_as_a_refusal(capsys, tmp_path):
    prepared(capsys, tmp_path, wide_scenario())

    def faulting(*arguments, **declared):
        raise ValueError("a fault in this product and not a refusal")

    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(composition, "reconcile_run", faulting)
        with pytest.raises(ValueError) as raised:
            cli.main(verify_words(tmp_path))

    assert not isinstance(raised.value, composition.CompositionError)
    assert "a fault in this product" in str(raised.value)


def test_a_hand_added_failed_output_is_still_refused_by_the_comparison_engine(capsys, tmp_path):
    case, _ = verified(capsys, tmp_path)
    path = case_record(tmp_path, case, composition.OUTCOME_RECORD)
    held = composition.read_case_record(path, report.OUTCOME_RECORD_FORM)
    composition.store_case_record(
        path, {**held, composition.FAILED_OUTPUT_FIELD: (OUTPUT_ID,)}
    )

    error = refused(capsys, diagnose_words(tmp_path))

    assert error["reason"] == composition.RefusalReason.MALFORMED_VALUE.value
    assert "not-a-failed-output" in error["detail"]


def test_one_reader_owns_the_record_line_loop_for_every_record_this_root_holds(tmp_path):
    written = "a line no record projection writes\n"
    path = tmp_path / "outcome.md"
    path.write_text(written, encoding="ascii")

    with pytest.raises(composition.CompositionError) as read_as_record:
        composition.read_record(written)
    with pytest.raises(composition.CompositionError) as read_as_case:
        composition.read_case_record(path, report.OUTCOME_RECORD_FORM)
    with pytest.raises(composition.CompositionError) as read_alone:
        composition.record_lines(written)

    details = {read_as_record.value.detail, read_as_case.value.detail, read_alone.value.detail}
    assert details == {"a record holds one recorded fact per line"}


@pytest.mark.parametrize(
    "place",
    [
        chr(47) + "held" + chr(47) + "material",
        "d" + chr(58) + chr(47) + "held",
        "d" + chr(58) + "held",
        chr(47) * 2 + "held" + chr(47) + "material",
    ],
    ids=("rooted", "lettered-volume", "volume-relative", "share-host"),
)
def test_an_adapter_place_written_in_an_absolute_form_is_refused_without_echoing_it(
    capsys, tmp_path, place
):
    seeded(tmp_path, parity_fixture.scenario())
    path, document = declared_document(tmp_path, "adapters.json")
    document["adapters"][EVIDENCE_ADAPTER]["directory"] = place
    declared(path, document)

    error = refused(capsys, words("intake-case", tmp_path))

    assert error["reason"] == composition.RefusalReason.MALFORMED_RECORD.value
    assert "relative to the records root" in error["detail"]
    assert place not in error["detail"]


def test_a_place_that_resolves_inside_the_records_root_is_still_refused_when_absolute(
    capsys, tmp_path
):
    seeded(tmp_path, parity_fixture.scenario())
    path, document = declared_document(tmp_path, "adapters.json")
    document["adapters"][EVIDENCE_ADAPTER]["directory"] = (
        (tmp_path / "work" / HELD_DIRECTORY).as_posix()
    )
    declared(path, document)

    error = refused(capsys, words("intake-case", tmp_path))

    assert error["reason"] == composition.RefusalReason.MALFORMED_RECORD.value


def test_an_intake_that_names_no_reason_and_accepts_nothing_is_still_refused(
    capsys, tmp_path, monkeypatch
):
    seeded(tmp_path, parity_fixture.scenario())

    def answering_with_neither(*arguments, **declared):
        raise IntakeRefused(())

    monkeypatch.setattr(composition, "intake_case", answering_with_neither)

    error = refused(capsys, words("intake-case", tmp_path))

    assert error["reason"] == composition.RefusalReason.MALFORMED_RECORD.value
    assert "neither an accepted case nor a reason" in error["detail"]
