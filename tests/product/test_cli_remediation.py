"""The remediation routes: record one disposition, rerun a correction, lay out the evidence.

Every route is driven through the command surface itself, over a scratch
records root, so the proof covers what a caller actually runs: the words are
parsed, the composition root reads the documents an environment holds, the
remediation workflow decides, and the surface writes the result down. The
tracker is reached through the fake released command the projection's own proof
owns, so nothing here touches a real tracker, a network or a clock.

The advice, the fault packet behind it and the authority it requires are the
projection proof's fixtures, and the case, the adapters and the material are
the verification proof's. Neither is declared a second time here.
"""
from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from evorthon_data import cli, composition
from evorthon_data.presentation.use_case import ENVELOPE_FORM, EXIT_OK, EXIT_REFUSED
from evorthon_data.verification import presentation as report
from evorthon_data.verification.adapters import (
    CONFORMANCE_CANDIDATE,
    CONFORMANCE_DECLARED_OUTPUTS,
    ReplayDeclaration,
    write_fixture_material,
)
from evorthon_data.verification.core.canonical import case_digest
from evorthon_data.verification.domain.contracts import (
    AssuranceLevel,
    EnvironmentCertificateClaim,
    EvidenceReference,
    Identity,
    OwnerPresentedEvidence,
)
from evorthon_data.verification.enforcement.serialization import serialize_json

import test_cli_use_case as use_case_fixture  # noqa: E402
import test_cli_verification as verification_fixture  # noqa: E402
import test_pinax_projection as remedy_fixture  # noqa: E402
from test_pinax_projection import ACTOR, FakePinax  # noqa: E402

ROOT = Path(__file__).parents[2]
ROUTE_SOURCES = (ROOT / "src/evorthon_data/composition.py", ROOT / "src/evorthon_data/cli.py")
COMMAND_SOURCE = ROOT / "src/evorthon_data/cli.py"

ENGAGEMENT = verification_fixture.ENGAGEMENT
CASE_DOCUMENT = verification_fixture.CASE_DOCUMENT
MATERIAL_DOCUMENT = verification_fixture.MATERIAL_DOCUMENT
EVIDENCE_ADAPTER = verification_fixture.EVIDENCE_ADAPTER
CANDIDATE_ADAPTER = verification_fixture.CANDIDATE_ADAPTER
CORRECTED_ADAPTER = "corrected-candidate"
CORRECTED_DIRECTORY = "environment-owned-correction"
CORRECTED_MATERIAL = f"{ENGAGEMENT}/corrected.json"

ADVICE_DOCUMENT = f"{ENGAGEMENT}/advice.json"
RATIONALE_DOCUMENT = f"{ENGAGEMENT}/rationale.json"
ASKED_RATIONALE_DOCUMENT = f"{ENGAGEMENT}/asked-rationale.json"
OWNER_DOCUMENT = f"{ENGAGEMENT}/owner-presented.json"
CERTIFICATE_DOCUMENT = f"{ENGAGEMENT}/certificate.json"
OTHER_CERTIFICATE_DOCUMENT = f"{ENGAGEMENT}/other-certificate.json"
REMEDY_DOCUMENT = f"{ENGAGEMENT}/remedy.json"

# A digest carries its own field separator, written here by code point so the
# file spells out no address-like token of its own.
SEPARATOR = chr(58)


def fingerprint(name: str) -> str:
    return f"sha256{SEPARATOR}{name}"


AUTHORITY = remedy_fixture.REMEDY_AUTHORITY
ANOTHER_AUTHORITY = Identity("another-authority", "v1", fingerprint("another-authority"))
DECIDED_BY = f"{AUTHORITY.identifier}:{AUTHORITY.version}:{AUTHORITY.digest}:human"
ASKED = remedy_fixture.REMEDY_ASKED
# The advice the adviser recorded keeps its own identity whatever fault it is
# bound to, so the decision it becomes is named the same way throughout.
ADVICE_ID = f"{remedy_fixture.REMEDY_FAULT_ID}/advice"
DECISION_IDENTITY = f"{ADVICE_ID}/decision"
CLAUSE_ID = verification_fixture.parity_fixture.CLAUSE_ID
OUTPUT_ID = verification_fixture.OUTPUT_ID
# The rationale each decision rests on, which is half of a record name.
RATIONALE_ID = "remedy-rationale"
ASKED_RATIONALE_ID = "asked-rationale"
SECOND_RATIONALE_ID = "second-rationale"
SECOND_RATIONALE_DOCUMENT = f"{ENGAGEMENT}/second-rationale.json"

# The prose a person and an adviser wrote, which no report and no record may
# carry. Each is declared in one document and checked for in both outputs.
RATIONALE_SUMMARY = "the authority read the parity finding and approved the remedy"
EDIT_STATEMENT = "the authority narrowed the remedy to the reported window"
EDITED_FIX = "restore the declared population filter for the reported window only"
# The declared enumerations the composition root may never state a member of,
# and the records it may never build for itself.
DOMAIN_ENUMERATIONS = ("RemediationDisposition", "AssuranceLevel", "RemediationActorKind")
DOMAIN_VALUES = ("RemediationDecision", "RemediationOutcome", "RemediationRerun")
# The delivery capabilities the composition root may build for itself. The
# declared values a scope carries are built here; a tracker command is not.
DELIVERY_CAPABILITIES = {
    "ApprovedRemedy",
    "PinaxContractProjector",
    "SegmentIteration",
    "SubprocessPinaxRunner",
    "UseCaseScope",
}


def run(capsys, argv):
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def machine(capsys, argv):
    code, out, err = run(capsys, [*argv, "--json"])
    return code, json.loads(out), out, err


def refused(capsys, argv):
    """Drive one route that must refuse and return the error it wrote."""
    code, payload, _, _ = machine(capsys, argv)
    assert code == EXIT_REFUSED
    assert payload["form"] == ENVELOPE_FORM
    assert set(payload) == {"form", "command", "status", "exit code", "error"}
    assert set(payload["error"]) == {"reason", "detail"}
    assert payload["error"]["reason"] in {reason.value for reason in composition.RefusalReason}
    return payload["error"]


def declared(path: Path, document) -> None:
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="ascii", newline="\n"
    )


def serialized(path: Path, record) -> None:
    path.write_text(serialize_json(record), encoding="ascii", newline="\n")


def reference(name: str, summary: str) -> EvidenceReference:
    return EvidenceReference(name, "v1", fingerprint(name), summary)


def divergent_scenario():
    """One run of the shared case whose measures diverge past the declared tolerance.

    The case is wide enough for the privacy gate to let a packet out, because a
    decision is only recorded for a fault the case has a gated packet for.
    """
    return verification_fixture.wide_scenario()


def corrected_scenario():
    """One run of the same case that reproduces the approved output exactly."""
    return verification_fixture.parity_fixture.scenario(
        expected_rows=verification_fixture.WIDE_ROWS
    )


def unanswered_scenario():
    """One failing run of a case that declares clauses nothing answers, under a declared authority.

    The whole-contract fixture states an environment-certified assurance of its
    own. The label this proof needs is the weakest one, so the declaration is
    taken from the parity case the contract case was built from.
    """
    parity = divergent_scenario()
    scenario = verification_fixture.contract_scenario(parity)
    return replace(scenario, case=replace(scenario.case, assurance=parity.case.assurance))


def advice_for(fault=None):
    """The recorded advice, bound to the fault the case reported when there is one."""
    recorded_advice = remedy_fixture.remedy_advice()
    return recorded_advice if fault is None else replace(recorded_advice, fault=fault)


def documents(base: Path, fault=None) -> None:
    """Write the advice and the material a person presents beside a decision."""
    engagement = base / "work" / ENGAGEMENT
    serialized(engagement / "advice.json", advice_for(fault))
    serialized(engagement / "rationale.json", reference(RATIONALE_ID, RATIONALE_SUMMARY))
    serialized(
        engagement / "second-rationale.json",
        reference(SECOND_RATIONALE_ID, "the authority decided again on the open fault"),
    )
    serialized(
        engagement / "asked-rationale.json",
        reference(ASKED_RATIONALE_ID, f"the decision waits on {ASKED}"),
    )
    serialized(
        engagement / "owner-presented.json",
        OwnerPresentedEvidence(
            evidence_id="owner-approved-parity",
            version="v1",
            digest=fingerprint("owner-approved-parity"),
            presented_by=AUTHORITY,
            approval_evidence=reference("owner-approval", "the owner approved the presented work"),
        ),
    )
    serialized(
        engagement / "certificate.json",
        EnvironmentCertificateClaim(
            claim_id="environment-certificate",
            version="v1",
            certificate_digest=fingerprint("environment-certificate"),
            issued_by=AUTHORITY,
            assurance_level=AssuranceLevel.ENVIRONMENT_CERTIFIED,
        ),
    )
    serialized(
        engagement / "other-certificate.json",
        EnvironmentCertificateClaim(
            claim_id="environment-certificate",
            version="v1",
            certificate_digest=fingerprint("environment-certificate"),
            issued_by=ANOTHER_AUTHORITY,
            assurance_level=AssuranceLevel.ENVIRONMENT_CERTIFIED,
        ),
    )
    declared(
        engagement / "remedy.json",
        {
            "form": composition.REMEDY_DOCUMENT_FORM,
            "fixes": [EDITED_FIX],
            "statement": EDIT_STATEMENT,
        },
    )


def corrected_material(base: Path, case, scenario) -> None:
    """Lay the corrected candidate out beside the one the recorded run was taken over."""
    write_fixture_material(
        base / "work" / CORRECTED_DIRECTORY,
        candidate=CONFORMANCE_CANDIDATE,
        declared_outputs=(
            CONFORMANCE_DECLARED_OUTPUTS,
            ReplayDeclaration(
                case_id=case.case_id,
                case_version=case.version,
                case_digest=case_digest(case),
                outputs=(verification_fixture.produced_from(scenario.observation.output),),
            ),
        ),
    )
    engagement = base / "work" / ENGAGEMENT
    path, document = verification_fixture.declared_document(base, "adapters.json")
    document["adapters"][CORRECTED_ADAPTER] = {
        "family": "fixture",
        "directory": CORRECTED_DIRECTORY,
    }
    declared(path, document)
    _, material = verification_fixture.declared_document(base, "material.json")
    material["observed"] = [
        {
            "output": verification_fixture.serialize_record(scenario.observation.output),
            "rows": verification_fixture.written_rows(scenario.observation.rows),
        }
    ]
    declared(engagement / "corrected.json", material)


def recorded_fault(base: Path, case):
    """The fault the case has a recorded gated packet for, as the packet names it."""
    held = composition.read_case_record(
        recorded(base, case, composition.PACKET_RECORD.format(output=OUTPUT_ID)),
        report.PACKET_RECORD_FORM,
    )
    return Identity(held[report.FAULT_FIELD][0], "v1", fingerprint("gated-packet"))


def verified(capsys, tmp_path, scenario=None, *, clauses=()):
    """One seeded engagement taken in, verified, and diagnosed for the failing output.

    The advice is written twice: once before the run, as an environment holds
    it, and once bound to the fault the diagnosis actually recorded, which is
    the fault a decision may be recorded for.
    """
    scenario = divergent_scenario() if scenario is None else scenario
    case = verification_fixture.seeded(tmp_path, scenario, clauses=clauses)
    documents(tmp_path)
    code, _, error = run(capsys, verification_fixture.words("intake-case", tmp_path))
    assert (code, error) == (EXIT_OK, "")
    code, _, error = run(capsys, verification_fixture.verify_words(tmp_path))
    assert (code, error) == (EXIT_OK, "")
    code, _, error = run(capsys, verification_fixture.diagnose_words(tmp_path))
    assert (code, error) == (EXIT_OK, "")
    documents(tmp_path, recorded_fault(tmp_path, case))
    return case


def decision_words(
    base: Path,
    *arguments,
    disposition: str = "accepted",
    rationale: str = RATIONALE_DOCUMENT,
    decided_by: str = DECIDED_BY,
):
    """The words one named human disposes of the recorded advice in."""
    return [
        "--advice",
        ADVICE_DOCUMENT,
        "--disposition",
        disposition,
        "--decided-by",
        decided_by,
        "--rationale",
        rationale,
        *arguments,
    ]


def remediation_words(base: Path, *arguments, **declared_words):
    return [
        "verification",
        "record-remediation",
        "--repository",
        str(base),
        "--engagement",
        ENGAGEMENT,
        "--case",
        CASE_DOCUMENT,
        *decision_words(base, *arguments, **declared_words),
    ]


def rerun_words(base: Path, *arguments, candidate: str = CORRECTED_ADAPTER, material: str = CORRECTED_MATERIAL, **declared_words):
    return [
        "verification",
        "rerun",
        "--repository",
        str(base),
        "--engagement",
        ENGAGEMENT,
        "--case",
        CASE_DOCUMENT,
        "--evidence-adapter",
        EVIDENCE_ADAPTER,
        "--candidate-adapter",
        candidate,
        "--material",
        material,
        "--prior-candidate-adapter",
        CANDIDATE_ADAPTER,
        "--prior-material",
        MATERIAL_DOCUMENT,
        "--decision",
        DECISION_IDENTITY,
        *decision_words(base, *arguments, **declared_words),
    ]


def acceptance_words(base: Path):
    return [
        "verification",
        "acceptance-evidence",
        "--repository",
        str(base),
        "--engagement",
        ENGAGEMENT,
        "--case",
        CASE_DOCUMENT,
    ]


def rationale_of(disposition: str) -> str:
    """The rationale identity each disposition in this proof rests on."""
    return ASKED_RATIONALE_ID if disposition == "request-more-evidence" else RATIONALE_ID


def disposition_words(disposition: str):
    """The extra words each disposition carries, and no other disposition may."""
    if disposition == "modified":
        return {"arguments": ("--edited-remedy", REMEDY_DOCUMENT), "rationale": RATIONALE_DOCUMENT}
    if disposition == "request-more-evidence":
        return {
            "arguments": ("--requested-evidence", ASKED),
            "rationale": ASKED_RATIONALE_DOCUMENT,
        }

    return {"arguments": (), "rationale": RATIONALE_DOCUMENT}


def case_records(base: Path, case) -> Path:
    """The one directory that holds every record of one case."""
    return base / "work" / ENGAGEMENT / composition.CASE_DIRECTORY / case.case_id


def recorded(base: Path, case, name: str) -> Path:
    return case_records(base, case) / name


def decision_key(disposition: str = "accepted", rationale: str = RATIONALE_ID) -> str:
    """The plain name the record of one decision is held under."""
    return f"{disposition}-{rationale}"


def decision_record(base: Path, case, key: str | None = None) -> Path:
    return recorded(
        base, case, composition.DECISION_RECORD.format(key=decision_key() if key is None else key)
    )


def use_case_words(repository, name, *arguments):
    """The words that drive one use-case route under the verification engagement."""
    return [
        "use-case",
        name,
        "--repository",
        str(repository),
        "--engagement",
        ENGAGEMENT,
        "--use-case",
        use_case_fixture.USE_CASE,
        *arguments,
    ]


def opened_use_case(capsys, repository):
    """One held use case under the same engagement, for the tracker to project onto."""
    overrides = {"--engagement": ENGAGEMENT}
    code, _, error = run(capsys, use_case_fixture.open_words(repository, **overrides))
    assert (code, error) == (EXIT_OK, "")
    for kind, fields in use_case_fixture.DECLARATIONS.items():
        if kind == "consumer-dependency":
            continue
        words = use_case_words(repository, "record-fact", "--kind", kind)
        for name, value in fields.items():
            words.extend(("--field", f"{name}={value}"))
        code, _, error = run(capsys, words)
        assert (code, error) == (EXIT_OK, ""), f"{kind}: {error}"
    return repository


def tracker_words(base: Path):
    """The words that also project one approved remedy as tracked work."""
    return (
        "--use-case",
        use_case_fixture.USE_CASE,
        "--actor",
        ACTOR,
        "--iteration",
        f"first-report-loop:{use_case_fixture.OUTPUT}:build and verify the report span",
        "--remedy-summary",
        "correct the declared population of the report",
        *use_case_fixture.case_words(),
    )


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
    """Name every declared remediation value one source builds for itself."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in DOMAIN_VALUES
    ]


# --- the command surface ------------------------------------------------------


@pytest.mark.parametrize(
    ("route", "options"),
    [
        ("record-remediation", ("--case", "--advice", "--disposition", "--decided-by", "--rationale", "--edited-remedy")),
        ("rerun", ("--case", "--decision", "--candidate-adapter", "--material", "--prior-material")),
        ("acceptance-evidence", ("--case", "--engagement")),
    ],
)
def test_every_remediation_route_declares_the_words_it_takes(capsys, route, options):
    with pytest.raises(SystemExit) as exited:
        cli.main(["verification", route, "--help"])

    printed = capsys.readouterr().out
    assert exited.value.code == EXIT_OK
    for option in options:
        assert option in printed


@pytest.mark.parametrize(
    "route", ["record-remediation", "acceptance-evidence"], ids=("recorded", "evidence")
)
def test_a_completed_route_writes_concise_human_lines_when_no_envelope_is_asked_for(
    capsys, tmp_path, route
):
    verified(capsys, tmp_path)
    words = {
        "record-remediation": remediation_words(tmp_path),
        "acceptance-evidence": acceptance_words(tmp_path),
    }[route]

    code, out, error = run(capsys, words)

    assert (code, error) == (EXIT_OK, "")
    lines = out.splitlines()
    assert out.isascii()
    assert lines
    for line in lines:
        assert line.count(chr(58)) >= 1


def test_the_disposition_words_are_the_ones_the_workflow_declares():
    assert composition.HUMAN_DISPOSITION_WORDS == report.HUMAN_DISPOSITION_WORDS
    assert set(composition.HUMAN_DISPOSITION_WORDS) == {
        "accepted",
        "modified",
        "rejected",
        "request-more-evidence",
    }


# --- every disposition round-trips -------------------------------------------


@pytest.mark.parametrize(
    "disposition", ["accepted", "modified", "rejected", "request-more-evidence"]
)
def test_every_disposition_is_recorded_and_read_back_with_equal_values(
    capsys, tmp_path, disposition
):
    case = verified(capsys, tmp_path)
    extra = disposition_words(disposition)

    code, payload, _, error = machine(
        capsys,
        remediation_words(
            tmp_path,
            *extra["arguments"],
            disposition=disposition,
            rationale=extra["rationale"],
        ),
    )

    assert (code, error) == (EXIT_OK, "")
    reported = payload["result"]
    assert payload["command"] == "verification record-remediation"
    assert reported["disposition"] == disposition
    assert reported["decision"] == DECISION_IDENTITY
    held = composition.read_case_record(
        decision_record(tmp_path, case, decision_key(disposition, rationale_of(disposition))),
        report.DECISION_RECORD_FORM,
    )
    written = {name: (value,) for name, value in reported.items()}
    for name in ("record", "parent item", "remedy item"):
        written.pop(name)
    assert held == {"form": (report.DECISION_RECORD_FORM,), **written}


@pytest.mark.parametrize(
    ("disposition", "work", "open_fault"),
    [
        ("accepted", True, "no"),
        ("modified", True, "no"),
        ("rejected", False, "yes"),
        ("request-more-evidence", False, "yes"),
    ],
)
def test_each_disposition_reports_the_work_it_approved_and_whether_the_fault_stays_open(
    capsys, tmp_path, disposition, work, open_fault
):
    verified(capsys, tmp_path)
    extra = disposition_words(disposition)

    code, payload, _, _ = machine(
        capsys,
        remediation_words(
            tmp_path,
            *extra["arguments"],
            disposition=disposition,
            rationale=extra["rationale"],
        ),
    )

    reported = payload["result"]
    assert code == EXIT_OK
    assert reported["fault open"] == open_fault
    assert (reported["approved work"] != report.NOTHING) is work


def test_recording_the_same_accepted_decision_again_writes_the_same_record(capsys, tmp_path):
    case = verified(capsys, tmp_path)
    words = remediation_words(tmp_path)
    code, first, _, _ = machine(capsys, words)
    written = decision_record(tmp_path, case).read_text(encoding="ascii")

    code_again, second, _, _ = machine(capsys, words)

    assert (code, code_again) == (EXIT_OK, EXIT_OK)
    assert first == second
    assert decision_record(tmp_path, case).read_text(encoding="ascii") == written


# --- who may decide, and on what ---------------------------------------------


def test_a_modified_disposition_with_no_edited_remedy_is_refused(capsys, tmp_path):
    verified(capsys, tmp_path)

    error = refused(capsys, remediation_words(tmp_path, disposition="modified"))

    assert error["reason"] == composition.RefusalReason.MALFORMED_VALUE.value
    assert "incomplete-disposition" in error["detail"]
    assert "an edit records the remedy the person wrote" in error["detail"]


def test_an_edited_remedy_on_a_disposition_that_owns_none_is_refused(capsys, tmp_path):
    verified(capsys, tmp_path)

    error = refused(
        capsys,
        remediation_words(tmp_path, "--edited-remedy", REMEDY_DOCUMENT, disposition="rejected"),
    )

    assert error["reason"] == composition.RefusalReason.MALFORMED_VALUE.value
    assert "only an edit records a remedy of its own" in error["detail"]


def test_a_decider_the_advice_does_not_require_is_refused_with_the_workflow_reason(
    capsys, tmp_path
):
    verified(capsys, tmp_path)
    other = (
        f"{ANOTHER_AUTHORITY.identifier}:{ANOTHER_AUTHORITY.version}:"
        f"{ANOTHER_AUTHORITY.digest}:human"
    )

    error = refused(capsys, remediation_words(tmp_path, decided_by=other))

    assert error["reason"] == composition.RefusalReason.MALFORMED_VALUE.value
    assert "unnamed-authority" in error["detail"]
    assert "the authority the advice requires" in error["detail"]


def test_an_actor_that_is_not_a_human_is_refused(capsys, tmp_path):
    verified(capsys, tmp_path)
    machine_actor = f"{AUTHORITY.identifier}:{AUTHORITY.version}:{AUTHORITY.digest}:model"

    error = refused(capsys, remediation_words(tmp_path, decided_by=machine_actor))

    assert error["reason"] == composition.RefusalReason.MALFORMED_VALUE.value
    assert "non-human-actor" in error["detail"]


def test_a_deciding_actor_with_no_declared_kind_is_refused_as_an_invalid_value(capsys, tmp_path):
    verified(capsys, tmp_path)

    error = refused(capsys, remediation_words(tmp_path, decided_by=AUTHORITY.identifier))

    assert error["reason"] == composition.RefusalReason.MALFORMED_VALUE.value
    assert "the kind of actor it is" in error["detail"]


# --- the assurance class, read off what was presented -------------------------


@pytest.mark.parametrize(
    ("presented", "assurance", "named"),
    [
        ((), "declared", report.NOTHING),
        (("--owner-presented", OWNER_DOCUMENT), "owner-presented", "owner-approved-parity"),
        (("--certificate", CERTIFICATE_DOCUMENT), "environment-certified", report.NOTHING),
    ],
    ids=("declared", "owner-presented", "environment-certified"),
)
def test_the_assurance_class_is_the_class_the_presented_material_states(
    capsys, tmp_path, presented, assurance, named
):
    case = verified(capsys, tmp_path)

    code, payload, _, _ = machine(capsys, remediation_words(tmp_path, *presented))

    reported = payload["result"]
    assert code == EXIT_OK
    assert reported["assurance"] == assurance
    assert reported["owner presented"] == named
    held = composition.read_case_record(
        decision_record(tmp_path, case), report.DECISION_RECORD_FORM
    )
    assert held["assurance"] == (assurance,)


def test_a_certificate_issued_for_another_identity_is_refused(capsys, tmp_path):
    verified(capsys, tmp_path)

    error = refused(
        capsys, remediation_words(tmp_path, "--certificate", OTHER_CERTIFICATE_DOCUMENT)
    )

    assert error["reason"] == composition.RefusalReason.MALFORMED_VALUE.value
    assert "inconsistent-assurance" in error["detail"]


def test_an_unauthenticated_declaration_is_still_recorded_and_still_labelled_declared(
    capsys, tmp_path
):
    case = verified(capsys, tmp_path)

    code, payload, _, _ = machine(capsys, remediation_words(tmp_path))

    assert code == EXIT_OK
    assert payload["result"]["assurance"] == AssuranceLevel.DECLARED.value
    code, evidence, _, _ = machine(capsys, acceptance_words(tmp_path))
    assert code == EXIT_OK
    assert evidence["result"]["declared assurance"] == AssuranceLevel.DECLARED.value
    assert AssuranceLevel.DECLARED.value in evidence["result"]["decisions"][0]
    assert case.assurance.declared_level is AssuranceLevel.DECLARED


# --- the tracker ---------------------------------------------------------------


def test_an_approving_decision_projects_exactly_one_item_and_a_second_run_adds_nothing(
    capsys, tmp_path, monkeypatch
):
    verified(capsys, tmp_path)
    opened_use_case(capsys, tmp_path)
    runner = FakePinax()
    monkeypatch.setattr(composition, "pinax_runner", lambda: runner)
    words = remediation_words(tmp_path, *tracker_words(tmp_path))

    code, payload, _, error = machine(capsys, words)

    assert (code, error) == (EXIT_OK, "")
    reported = payload["result"]
    assert reported["parent item"].startswith("evd-")
    assert reported["remedy item"].startswith("evd-")
    titles = {item["title"] for item in runner.items.values()}
    added = len(runner.items)
    remedy_item = reported["remedy item"]
    assert any(reported["approved work"] in title for title in titles)

    code, again, _, _ = machine(capsys, words)

    assert code == EXIT_OK
    assert again["result"]["remedy item"] == remedy_item
    assert len(runner.items) == added


@pytest.mark.parametrize("disposition", ["rejected", "request-more-evidence"])
def test_a_decision_that_approves_no_work_is_projected_nowhere(
    capsys, tmp_path, monkeypatch, disposition
):
    verified(capsys, tmp_path)
    opened_use_case(capsys, tmp_path)
    runner = FakePinax()
    monkeypatch.setattr(composition, "pinax_runner", lambda: runner)
    extra = disposition_words(disposition)

    code, payload, _, _ = machine(
        capsys,
        remediation_words(
            tmp_path,
            *extra["arguments"],
            *tracker_words(tmp_path),
            disposition=disposition,
            rationale=extra["rationale"],
        ),
    )

    assert code == EXIT_OK
    assert payload["result"]["parent item"] == report.NOTHING
    assert payload["result"]["remedy item"] == report.NOTHING
    assert runner.commands == []


def test_a_decision_recorded_without_a_tracker_actor_reaches_no_tracker(
    capsys, tmp_path, monkeypatch
):
    verified(capsys, tmp_path)
    runner = FakePinax()
    monkeypatch.setattr(composition, "pinax_runner", lambda: runner)

    code, payload, _, _ = machine(capsys, remediation_words(tmp_path))

    assert code == EXIT_OK
    assert payload["result"]["remedy item"] == report.NOTHING
    assert runner.commands == []


def test_projecting_without_the_words_the_projection_needs_is_refused(capsys, tmp_path):
    verified(capsys, tmp_path)

    error = refused(capsys, remediation_words(tmp_path, "--actor", ACTOR))

    assert error["reason"] == composition.RefusalReason.MALFORMED_VALUE.value
    assert "names the use case" in error["detail"]


# --- the rerun ------------------------------------------------------------------


def prepared_rerun(capsys, tmp_path):
    """One recorded failing run, one recorded accepted decision and a corrected candidate."""
    case = verified(capsys, tmp_path)
    corrected_material(tmp_path, case, corrected_scenario())
    code, _, error = run(capsys, remediation_words(tmp_path))
    assert (code, error) == (EXIT_OK, "")
    return case


def test_a_corrected_rerun_is_green_and_completes(capsys, tmp_path):
    case = prepared_rerun(capsys, tmp_path)

    code, payload, _, error = machine(capsys, rerun_words(tmp_path))

    assert (code, error) == (EXIT_OK, "")
    reported = payload["result"]
    assert payload["command"] == "verification rerun"
    assert reported["rerun"] == "green"
    assert reported["corrected"] == [CLAUSE_ID]
    assert reported["restored defects"] == []
    assert reported["regression set"] == [CLAUSE_ID]
    held = composition.read_case_record(
        recorded(tmp_path, case, composition.RERUN_RECORD.format(key=decision_key())),
        report.RERUN_RECORD_FORM,
    )
    assert held["rerun"] == ("green",)
    assert held["decision"] == (DECISION_IDENTITY,)


def test_a_rerun_that_does_not_correct_the_fault_is_red_and_still_completes(capsys, tmp_path):
    prepared_rerun(capsys, tmp_path)

    code, payload, _, error = machine(
        capsys, rerun_words(tmp_path, candidate=CANDIDATE_ADAPTER, material=MATERIAL_DOCUMENT)
    )

    reported = payload["result"]
    assert (code, error) == (EXIT_OK, "")
    assert reported["rerun"] == "red"
    assert reported["restored defects"] == [CLAUSE_ID]
    assert reported["corrected"] == []


def test_a_rerun_for_a_disposition_that_approved_no_work_is_refused(capsys, tmp_path):
    case = verified(capsys, tmp_path)
    corrected_material(tmp_path, case, corrected_scenario())
    code, _, _ = run(capsys, remediation_words(tmp_path, disposition="rejected"))
    assert code == EXIT_OK

    error = refused(capsys, rerun_words(tmp_path, disposition="rejected"))

    assert error["reason"] == composition.RefusalReason.MALFORMED_VALUE.value
    assert "unapproved-remedy" in error["detail"]


def test_a_rerun_naming_a_decision_the_case_does_not_record_is_refused(capsys, tmp_path):
    prepared_rerun(capsys, tmp_path)

    error = refused(capsys, rerun_words(tmp_path, "--decision", "no-such-decision"))

    assert error["reason"] == composition.RefusalReason.MALFORMED_VALUE.value
    assert "names the decision" in error["detail"]


def test_a_rerun_whose_prior_run_is_not_the_recorded_one_is_refused(capsys, tmp_path):
    case = prepared_rerun(capsys, tmp_path)

    error = refused(
        capsys,
        rerun_words(
            tmp_path,
            "--prior-candidate-adapter",
            CORRECTED_ADAPTER,
            "--prior-material",
            CORRECTED_MATERIAL,
        ),
    )

    assert error["reason"] == composition.RefusalReason.DIGEST_MISMATCH.value
    assert "the recorded outcome answers for" in error["detail"]
    assert case.case_id


def test_a_rerun_presenting_a_decision_the_record_does_not_hold_is_refused(capsys, tmp_path):
    case = prepared_rerun(capsys, tmp_path)
    path = decision_record(tmp_path, case)
    held = composition.read_case_record(path, report.DECISION_RECORD_FORM)
    composition.store_case_record(path, {**held, "assurance": ("environment-certified",)})

    error = refused(capsys, rerun_words(tmp_path))

    assert error["reason"] == composition.RefusalReason.DIGEST_MISMATCH.value
    assert "presented again as it was recorded" in error["detail"]


# --- a prior run that is not the whole run the outcome answered for --------------

THIN_PRIOR = f"{ENGAGEMENT}/prior-thinned.json"


def answered_rerun(capsys, tmp_path):
    """One recorded whole-contract run, its decision, and a corrected candidate."""
    case = verified(
        capsys,
        tmp_path,
        unanswered_scenario(),
        clauses=verification_fixture.passing_clause_observations(),
    )
    corrected_material(tmp_path, case, corrected_scenario())
    code, _, error = run(capsys, remediation_words(tmp_path))
    assert (code, error) == (EXIT_OK, "")
    return case


def thinned(base: Path) -> None:
    """The recorded run's material with its clause observations taken out."""
    _, material = verification_fixture.declared_document(base, "material.json")
    declared(base / "work" / ENGAGEMENT / "prior-thinned.json", {**material, "clauses": []})


def test_a_prior_material_that_answers_fewer_clauses_than_the_recorded_run_is_refused(
    capsys, tmp_path
):
    """A thinned prior would shrink the regression set and hide a clause that broke."""
    case = answered_rerun(capsys, tmp_path)
    thinned(tmp_path)

    error = refused(capsys, rerun_words(tmp_path, "--prior-material", THIN_PRIOR))

    assert error["reason"] == composition.RefusalReason.DIGEST_MISMATCH.value
    assert "the whole contract the recorded outcome answers for" in error["detail"]
    held = sorted(path.name for path in case_records(tmp_path, case).iterdir())
    assert composition.RERUN_RECORD.format(key=decision_key()) not in held


def test_the_honest_prior_reports_the_clause_the_corrected_run_broke(capsys, tmp_path):
    """The same corrected run the thinned prior would have called green is red."""
    answered_rerun(capsys, tmp_path)
    _, corrected = verification_fixture.declared_document(tmp_path, "corrected.json")
    corrected["clauses"] = [
        {
            "clause": clause_id,
            "values": dict(
                (
                    verification_fixture.contract_fixture.FAILING_FACTS
                    if clause_id == "invariant"
                    else verification_fixture.contract_fixture.PASSING_FACTS
                )[clause_id]
            ),
        }
        for clause_id in verification_fixture.contract_fixture.CONTRACT_CLAUSE_IDS
    ]
    declared(tmp_path / "work" / ENGAGEMENT / "corrected.json", corrected)

    code, payload, _, _ = machine(capsys, rerun_words(tmp_path))

    reported = payload["result"]
    assert code == EXIT_OK
    assert reported["rerun"] == "red"
    assert reported["regressions"] == ["invariant"]
    assert reported["regression set"] == [
        CLAUSE_ID,
        *verification_fixture.contract_fixture.CONTRACT_CLAUSE_IDS,
    ]


# --- the fault a decision answers, and the record it may not overwrite -----------

FOREIGN_ADVICE = f"{ENGAGEMENT}/foreign-advice.json"


def test_an_advice_for_a_fault_this_case_never_reported_is_refused(capsys, tmp_path):
    case = verified(capsys, tmp_path)
    foreign = replace(
        advice_for(),
        fault=Identity("fault-nobody-reported", "v1", fingerprint("fault-nobody-reported")),
    )
    serialized(tmp_path / "work" / ENGAGEMENT / "foreign-advice.json", foreign)

    error = refused(capsys, remediation_words(tmp_path, "--advice", FOREIGN_ADVICE))

    assert error["reason"] == composition.RefusalReason.RECORD_NOT_HELD.value
    assert "no gated packet is held for the fault" in error["detail"]
    assert not list(case_records(tmp_path, case).glob("decision-*"))


def test_an_approved_correction_is_not_changed_by_a_later_decision(capsys, tmp_path):
    case = verified(capsys, tmp_path)
    code, _, error = run(capsys, remediation_words(tmp_path))
    assert (code, error) == (EXIT_OK, "")
    written = decision_record(tmp_path, case).read_text(encoding="ascii")

    error = refused(capsys, remediation_words(tmp_path, disposition="rejected"))

    assert error["reason"] == composition.RefusalReason.DIGEST_MISMATCH.value
    assert "already approved a correction for this fault" in error["detail"]
    assert decision_record(tmp_path, case).read_text(encoding="ascii") == written
    held = sorted(path.name for path in case_records(tmp_path, case).iterdir())
    assert composition.DECISION_RECORD.format(key=decision_key("rejected")) not in held


def test_a_fault_left_open_may_be_decided_again_and_both_records_survive(capsys, tmp_path):
    case = verified(capsys, tmp_path)
    code, _, error = run(capsys, remediation_words(tmp_path, disposition="rejected"))
    assert (code, error) == (EXIT_OK, "")

    code, _, error = run(
        capsys,
        remediation_words(
            tmp_path, disposition="rejected", rationale=SECOND_RATIONALE_DOCUMENT
        ),
    )

    assert (code, error) == (EXIT_OK, "")
    held = sorted(path.name for path in case_records(tmp_path, case).iterdir())
    assert composition.DECISION_RECORD.format(key=decision_key("rejected")) in held
    assert (
        composition.DECISION_RECORD.format(key=decision_key("rejected", SECOND_RATIONALE_ID))
        in held
    )
    code, payload, _, _ = machine(capsys, acceptance_words(tmp_path))
    assert code == EXIT_OK
    assert len(payload["result"]["decisions"]) == 2


def test_a_decision_recorded_under_a_name_that_already_states_something_else_is_refused(
    capsys, tmp_path
):
    verified(capsys, tmp_path)
    code, _, error = run(capsys, remediation_words(tmp_path, disposition="rejected"))
    assert (code, error) == (EXIT_OK, "")

    error = refused(
        capsys,
        remediation_words(
            tmp_path, "--certificate", CERTIFICATE_DOCUMENT, disposition="rejected"
        ),
    )

    assert error["reason"] == composition.RefusalReason.DIGEST_MISMATCH.value
    assert "already recorded under this name" in error["detail"]


# --- the clause line writer and the names it declares ----------------------------


def test_the_clause_lines_a_record_holds_carry_the_fields_their_names_declare(capsys, tmp_path):
    case = verified(
        capsys,
        tmp_path,
        unanswered_scenario(),
        clauses=verification_fixture.passing_clause_observations(),
    )

    held = composition.read_case_record(
        recorded(tmp_path, case, composition.OUTCOME_RECORD), report.OUTCOME_RECORD_FORM
    )

    read = {}
    for written in held["clause"]:
        fields = report.clause_fields(written)
        assert fields is not None, written
        entry = dict(zip(report.CLAUSE_FIELDS, fields))
        read[entry["clause"]] = entry
    assert set(read) == {CLAUSE_ID, *verification_fixture.contract_fixture.CONTRACT_CLAUSE_IDS}
    assert read["operational"]["family"] == "operational-evidence"
    assert read["integrity"]["family"] == "delivery-integrity"
    assert {entry["status"] for entry in read.values()} <= {
        "pass",
        "fail",
        "insufficient-evidence",
    }
    assert {entry["execution"] for entry in read.values()} <= {"executed", "not executed"}


# --- the acceptance evidence ----------------------------------------------------


def test_the_acceptance_evidence_lays_out_the_uncertainty_without_upgrading_anything(
    capsys, tmp_path
):
    case = verified(capsys, tmp_path, unanswered_scenario())
    code, _, _ = run(capsys, remediation_words(tmp_path))
    assert code == EXIT_OK

    code, payload, out, error = machine(capsys, acceptance_words(tmp_path))

    reported = payload["result"]
    held = composition.read_case_record(
        recorded(tmp_path, case, composition.OUTCOME_RECORD), report.OUTCOME_RECORD_FORM
    )
    assert (code, error) == (EXIT_OK, "")
    assert payload["command"] == "verification acceptance-evidence"
    assert reported["status"] == held["status"][0]
    assert reported["clauses without sufficient evidence"] == list(
        verification_fixture.contract_fixture.CONTRACT_CLAUSE_IDS
    )
    assert reported["unread clause lines"] == "0"
    assert reported["declared assurance"] == "declared"
    assert reported["owner presented records"] == "0"
    assert reported["environment certificates"] == "0"
    assert reported["evidence provenance"] == "real"
    assert reported["decisions"] == [f"{DECISION_IDENTITY}: accepted: declared"]
    assert out.isascii()
    assert not any("accept" in name for name in reported)


def contract_failure(capsys, tmp_path):
    """One seeded engagement taken in and verified over a failing contract clause.

    The clause that failed is answered over the facts the run declared, so no
    output failed, nothing is diagnosed here and no packet is written.
    """
    case = verification_fixture.seeded(
        tmp_path,
        verification_fixture.contract_scenario(),
        clauses=verification_fixture.contract_observations(
            failing=verification_fixture.CONTRACT_CLAUSE
        ),
    )
    documents(tmp_path)
    code, _, error = run(capsys, verification_fixture.words("intake-case", tmp_path))
    assert (code, error) == (EXIT_OK, "")
    code, _, error = run(capsys, verification_fixture.verify_words(tmp_path))
    assert (code, error) == (EXIT_OK, "")
    return case


def passing_lines(held) -> tuple[str, ...]:
    """The recorded clause lines, with every one of them answered as passing."""
    written = []
    for entry in held[report.OUTCOME_CLAUSE_FIELD]:
        fields = report.clause_fields(entry)
        assert fields is not None, entry
        read = dict(zip(report.CLAUSE_FIELDS, fields))
        read["status"] = report.PASSED
        written.append(report.line(*(read[name] for name in report.CLAUSE_FIELDS)))
    return tuple(written)


def test_every_outcome_field_a_reader_reads_is_one_the_outcome_writer_wrote(capsys, tmp_path):
    """The names of a recorded outcome's fields have one owner: the writer."""
    case = verified(capsys, tmp_path)

    held = composition.read_case_record(
        recorded(tmp_path, case, composition.OUTCOME_RECORD), report.OUTCOME_RECORD_FORM
    )

    assert set(report.OUTCOME_FIELDS) <= set(held)


def test_a_recorded_outcome_whose_field_name_drifted_is_read_as_nothing(capsys, tmp_path):
    """Red proof of the one owner: a fact under another name is not the fact.

    The acceptance reads the recorded status under the name the writer wrote
    it under. Writing the same fact under a drifted name leaves the reading
    with nothing, so a reader and a writer that named different fields could
    not both pass.
    """
    case = verified(capsys, tmp_path)
    path = recorded(tmp_path, case, composition.OUTCOME_RECORD)
    held = composition.read_case_record(path, report.OUTCOME_RECORD_FORM)
    composition.store_case_record(
        path,
        {
            (f"{name} drifted" if name == report.OUTCOME_STATUS_FIELD else name): value
            for name, value in held.items()
        },
    )

    code, payload, _, _ = machine(capsys, acceptance_words(tmp_path))

    assert code == EXIT_OK
    assert held[report.OUTCOME_STATUS_FIELD] != ()
    assert payload["result"][report.OUTCOME_STATUS_FIELD] == report.NOTHING


def test_the_acceptance_evidence_names_the_clauses_the_recorded_run_failed(capsys, tmp_path):
    """The failing clauses are read off the record, so a record without one names none.

    A run that failed a clause is more than a status: the acceptance names the
    clauses that failed and the family each one answers for. The second half is
    the red proof of that reading: with every recorded clause line answered as
    passing, the same route names no failing clause at all.
    """
    case = contract_failure(capsys, tmp_path)
    path = recorded(tmp_path, case, composition.OUTCOME_RECORD)
    held = composition.read_case_record(path, report.OUTCOME_RECORD_FORM)

    code, payload, _, _ = machine(capsys, acceptance_words(tmp_path))
    assert code == EXIT_OK
    assert payload["result"][report.FAILING_CLAUSE_FIELD] == [
        report.line(verification_fixture.CONTRACT_CLAUSE, verification_fixture.CONTRACT_FAMILY)
    ]

    composition.store_case_record(path, {**held, report.OUTCOME_CLAUSE_FIELD: passing_lines(held)})
    code, payload, _, _ = machine(capsys, acceptance_words(tmp_path))

    assert code == EXIT_OK
    assert payload["result"][report.FAILING_CLAUSE_FIELD] == []


def test_the_acceptance_evidence_reports_a_localisation_the_evidence_left_unknown(
    capsys, tmp_path
):
    verified(capsys, tmp_path)

    code, payload, _, _ = machine(capsys, acceptance_words(tmp_path))

    reported = payload["result"]
    assert code == EXIT_OK
    assert len(reported["localisation"]) == 1
    assert reported["localisation"][0].endswith(": unknown")
    assert len(reported["records"]) == 2


def test_the_acceptance_evidence_reports_the_clauses_a_rerun_left_unanswered(capsys, tmp_path):
    prepared_rerun(capsys, tmp_path)
    code, _, _ = run(capsys, rerun_words(tmp_path))
    assert code == EXIT_OK

    code, payload, _, _ = machine(capsys, acceptance_words(tmp_path))

    reported = payload["result"]
    assert code == EXIT_OK
    assert reported["unanswered clauses"] == []
    assert len(reported["reruns"]) == 1
    assert reported["reruns"][0].endswith("green")


def test_a_recorded_outcome_that_answers_for_another_case_is_refused(capsys, tmp_path):
    case = verified(capsys, tmp_path)
    path = recorded(tmp_path, case, composition.OUTCOME_RECORD)
    held = composition.read_case_record(path, report.OUTCOME_RECORD_FORM)
    composition.store_case_record(path, {**held, "case version": ("v2",)})

    error = refused(capsys, remediation_words(tmp_path))

    assert error["reason"] == composition.RefusalReason.MALFORMED_RECORD.value
    assert "the case document the route was given" in error["detail"]


def test_a_recorded_outcome_that_states_no_case_digest_is_refused(capsys, tmp_path):
    case = verified(capsys, tmp_path)
    path = recorded(tmp_path, case, composition.OUTCOME_RECORD)
    held = composition.read_case_record(path, report.OUTCOME_RECORD_FORM)
    composition.store_case_record(
        path, {name: value for name, value in held.items() if name != "case digest"}
    )

    error = refused(capsys, remediation_words(tmp_path))

    assert error["reason"] == composition.RefusalReason.MALFORMED_RECORD.value
    assert "states one case digest" in error["detail"]


def test_a_case_with_no_recorded_outcome_has_no_acceptance_evidence(capsys, tmp_path):
    verification_fixture.seeded(tmp_path, divergent_scenario())
    documents(tmp_path)

    error = refused(capsys, acceptance_words(tmp_path))

    assert error["reason"] == composition.RefusalReason.RECORD_NOT_HELD.value


def test_the_acceptance_route_writes_no_record_of_its_own(capsys, tmp_path):
    case = verified(capsys, tmp_path)
    directory = case_records(tmp_path, case)
    before = sorted(path.name for path in directory.iterdir())

    code, _, _, _ = machine(capsys, acceptance_words(tmp_path))

    assert code == EXIT_OK
    assert sorted(path.name for path in directory.iterdir()) == before
    assert before == [
        composition.PACKET_RECORD.format(output=OUTPUT_ID),
        composition.INTAKE_RECORD,
        composition.OUTCOME_RECORD,
    ]


# --- bounded rendering, and where a record may sit -------------------------------


@pytest.mark.parametrize(
    "route",
    ["record-remediation", "rerun", "acceptance-evidence"],
    ids=("record-remediation", "rerun", "acceptance-evidence"),
)
def test_no_declared_value_of_the_advice_or_the_material_reaches_either_output(
    capsys, tmp_path, route
):
    if route == "record-remediation":
        case = verified(capsys, tmp_path)
    else:
        case = prepared_rerun(capsys, tmp_path)
    words = {
        "record-remediation": remediation_words(
            tmp_path, "--edited-remedy", REMEDY_DOCUMENT, disposition="modified"
        ),
        "rerun": rerun_words(tmp_path),
        "acceptance-evidence": acceptance_words(tmp_path),
    }[route]

    code, _, out, _ = machine(capsys, words)

    assert code == EXIT_OK
    directory = case_records(tmp_path, case)
    written = "\n".join(
        path.read_text(encoding="ascii") for path in sorted(directory.iterdir())
    )
    for value in (RATIONALE_SUMMARY, EDIT_STATEMENT, EDITED_FIX, ASKED, "customer-a", "10.00"):
        assert value not in out
        assert value not in written


def test_every_record_these_routes_write_sits_under_the_records_root(capsys, tmp_path):
    case = prepared_rerun(capsys, tmp_path)
    code, _, _ = run(capsys, rerun_words(tmp_path))
    assert code == EXIT_OK

    directory = case_records(tmp_path, case)
    held = sorted(path.name for path in directory.iterdir())
    assert held == [
        composition.DECISION_RECORD.format(key=decision_key()),
        composition.PACKET_RECORD.format(output=OUTPUT_ID),
        composition.INTAKE_RECORD,
        composition.OUTCOME_RECORD,
        composition.RERUN_RECORD.format(key=decision_key()),
    ]
    assert directory.is_relative_to(tmp_path / "work")


def test_an_advice_document_that_is_not_one_is_refused_as_a_malformed_record(capsys, tmp_path):
    verified(capsys, tmp_path)

    error = refused(capsys, remediation_words(tmp_path, "--advice", RATIONALE_DOCUMENT))

    assert error["reason"] == composition.RefusalReason.MALFORMED_RECORD.value
    assert "RemediationAdvice" in error["detail"]


# --- what the surface and the root may not do ------------------------------------


def imported_modules(path: Path) -> list[str]:
    """Name every module one source imports, however it imports it."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    return imported


def reached_pinax_names(path: Path) -> set[str]:
    """Name every delivery capability one source imports from the tracker adapter."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and "pinax" in (node.module or "")
        for alias in node.names
    }


def injected(tmp_path: Path, source: Path, addition: str) -> Path:
    """One scratch copy of a source with a violation added, so a gate can be seen red."""
    copy = tmp_path / source.name
    copy.write_text(source.read_text(encoding="utf-8") + addition, encoding="utf-8")
    return copy


def test_the_command_surface_reaches_no_delivery_and_no_verification_module():
    imported = imported_modules(COMMAND_SOURCE)

    assert imported
    for name in imported:
        assert "delivery" not in name
        assert "verification" not in name


def test_the_command_surface_import_gate_reddens_on_an_injected_reach(tmp_path):
    copy = injected(
        tmp_path, COMMAND_SOURCE, "\nfrom .verification.workflows import remediation\n"
    )

    assert any("verification" in name for name in imported_modules(copy))


def test_the_disposition_gate_reddens_on_an_injected_member(tmp_path):
    copy = injected(
        tmp_path, ROUTE_SOURCES[0], "\nINJECTED = RemediationDisposition.ACCEPTED\n"
    )

    assert enumeration_members(copy) == ["RemediationDisposition.ACCEPTED"]


def test_the_decision_gate_reddens_on_an_injected_record(tmp_path):
    copy = injected(tmp_path, ROUTE_SOURCES[0], "\nINJECTED = RemediationDecision()\n")

    assert constructed_values(copy) == ["RemediationDecision"]


def test_the_tracker_capability_gate_reddens_on_an_injected_reach(tmp_path):
    copy = injected(
        tmp_path, ROUTE_SOURCES[0], "\nfrom .delivery.pinax import PinaxProjectionResult\n"
    )

    assert reached_pinax_names(copy) != DELIVERY_CAPABILITIES | {"PinaxProjectionError"}


@pytest.mark.parametrize("source", ROUTE_SOURCES, ids=lambda path: path.name)
def test_no_route_states_a_disposition_or_an_assurance_class_of_its_own(source):
    assert enumeration_members(source) == []


@pytest.mark.parametrize("source", ROUTE_SOURCES, ids=lambda path: path.name)
def test_no_route_builds_a_decision_or_a_rerun_of_its_own(source):
    assert constructed_values(source) == []


def test_the_root_reaches_the_tracker_only_through_the_named_adapter_capabilities():
    """No route writes a tracker command: it hands declared values to the projector."""
    assert reached_pinax_names(ROUTE_SOURCES[0]) == DELIVERY_CAPABILITIES | {
        "PinaxProjectionError"
    }
    for source in ROUTE_SOURCES:
        written = source.read_text(encoding="utf-8")
        assert "import subprocess" not in written


def test_every_declared_remediation_refusal_is_reported_under_one_declared_reason():
    from evorthon_data.verification.workflows import RemediationRefusalReason

    assert set(composition.REMEDIATION_REASONS) == set(RemediationRefusalReason)
    assert set(composition.REMEDIATION_REASONS.values()) <= set(composition.RefusalReason)


def test_the_deciding_actor_reader_keeps_the_digest_with_the_identity():
    written = (
        f"{ANOTHER_AUTHORITY.identifier}:{ANOTHER_AUTHORITY.version}:"
        f"{ANOTHER_AUTHORITY.digest}:human"
    )

    actor = composition.deciding_actor(written)

    assert ANOTHER_AUTHORITY.digest.count(SEPARATOR) == 1
    assert actor.identity == ANOTHER_AUTHORITY
    assert actor.kind.value == "human"
