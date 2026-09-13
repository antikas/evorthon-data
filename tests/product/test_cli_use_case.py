"""The use-case command routes: one envelope, one exit-code table, one error shape.

Every route is driven through the command surface itself, so the proof covers
what a caller actually runs: the words are parsed, the composition root builds
the declared values, and the surface writes the result down. The tracker route
is driven through a fake released command, so nothing here reaches a real
tracker, a network or a clock.
"""
# evorthon-verifies: EVD-README-049
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from evorthon_data import cli, composition
from evorthon_data.engagement import EngagementError
from evorthon_data.composition import CompositionError, RefusalReason
from evorthon_data.presentation.use_case import ENVELOPE_FORM, EXIT_OK, EXIT_REFUSED, EXIT_USAGE

# The fake released tracker command, owned by the projection's own proof.
from test_pinax_projection import ACTOR, FakePinax


ROOT = Path(__file__).parents[2]
PRESENTATION_SOURCES = (
    ROOT / "src/evorthon_data/cli.py",
    ROOT / "src/evorthon_data/presentation/__init__.py",
    ROOT / "src/evorthon_data/presentation/use_case.py",
)
CONSTRAINT_DOCUMENT = ROOT / "tests/fixtures/synthetic/constraints/region-reference.json"

ENGAGEMENT = "eng-customer-service"
USE_CASE = "uc-order-volume"
ARTEFACT = "order-extract-workbook"
POSITION = "sheet=orders;row=14"
PROVENANCE = f"{ARTEFACT}:v1:digest-{ARTEFACT}:intake-coworker:model:extracted:{POSITION}"
HUMAN = "acceptance-authority:human"
OUTPUT = "daily-order-report"
STEP = "settled-orders"
INPUT_DATASET = "order-extract"
CASE = "case-normal-day"
CASE_IDENTITY = f"{CASE}:v1:digest-{CASE}"
RESULT_IDENTITY = f"result-{CASE}:v1:digest-result-{CASE}"
VERSION = "uc-order-volume-v1"
LATER_VERSION = "uc-order-volume-v2"
# The integrity reasons a route may refuse for. Nothing here refuses for a
# readiness state, a synthetic label or the strength of a provenance, and
# nothing refuses for a disclosure decision either: a packet the policy
# withheld is reported as that decision by every route that holds one. The last
# two are the reasons the verification routes need, and they are pinned here
# with the rest because the set is one closed set for the whole surface.
INTEGRITY_REASONS = {
    "unknown-engagement",
    "record-outside-work",
    "malformed-record",
    "malformed-value",
    "digest-mismatch",
    "disposition-mismatch",
    "record-not-held",
    "evidence-digest-mismatch",
}
# One declaration of every kind the use-case aggregate holds, by the field
# names the composition root declares for that kind.
DECLARATIONS = {
    "authority": {
        "authority role": "accepting",
        "authority actor": HUMAN,
        "provenance": PROVENANCE,
    },
    "dataset": {
        "dataset identity": INPUT_DATASET,
        "dataset role": "input",
        "source system": "order-book",
        "delivery mode": "nightly file drop",
        "dataset cadence": "daily",
        "access owner": "data-owner:human",
        "classification": "confidential",
        "availability state": "obtained",
        "availability subject": f"{INPUT_DATASET}-2026-09:v1:digest-{INPUT_DATASET}-2026-09",
        "provenance": PROVENANCE,
    },
    "target-output": {
        "output identity": OUTPUT,
        "output kind": "table",
        "schema declaration": "customer-orders:v1:tabular",
        "schema fields": (
            "order_id:string:not-null:::order key"
            ";order_value:decimal:not-null:18:2:settled order value"
        ),
        "grain declaration": (
            "one-row-per-order:v1:unique-keys:settled orders in the reporting period"
        ),
        "grain keys": "order_id",
        "output cadence": "daily",
        "cutoff semantics": "rows settled before the evening cutoff",
        "effective-time semantics": "effective-dated on the settlement date",
        "stored name": "DAILY_ORDER_REPORT",
        "stored column names": "order_id:ORDER_ID",
        "defining specification": "orders-specification:v1:digest-orders-specification",
        "provenance": PROVENANCE,
    },
    "intermediate-result": {
        "step identity": STEP,
        "step description": "orders settled before the cutoff, one row per order",
        "evidence owner": HUMAN,
        "checkpoint candidate": "checkpoint",
        "continuity": "continuity",
        "provenance": PROVENANCE,
    },
    "build-route": {
        "segment identity": OUTPUT,
        "build route": "engineered",
        "target shape": "table",
        "layer": "reporting",
        "provenance": PROVENANCE,
    },
    "scenario": {"scenario case": CASE_IDENTITY, "provenance": PROVENANCE},
    "condition": {
        "condition key": "freshness_deadline",
        "condition state": "declared",
        "condition value": "before the morning shift",
        "provenance": PROVENANCE,
    },
    "intake-artefact": {
        "intake artefact": f"{ARTEFACT}:v1:digest-{ARTEFACT}",
        "artefact classification": "confidential",
        "artefact locator": "intake/order-extract-workbook",
        "provenance": PROVENANCE,
    },
    "consumer-dependency": {
        "providing use case": "uc-staffing-plan:v1:digest-uc-staffing-plan",
        "consumed product": "staffing-plan",
        "consumed major version": "v1",
        "provenance": PROVENANCE,
    },
    "scenario-result": {
        "scenario case": CASE_IDENTITY,
        "verification result": RESULT_IDENTITY,
        "verification status": "pass",
    },
}


def run(capsys, argv):
    """Drive one command and return its exit code and both output streams."""
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def machine(capsys, argv):
    """Drive one command in the machine convention and read its envelope."""
    code, out, err = run(capsys, [*argv, "--json"])
    return code, json.loads(out), out, err


def route(repository, name, *arguments):
    """The words that drive one route against one held use case."""
    return [
        "use-case",
        name,
        "--repository",
        str(repository),
        "--engagement",
        ENGAGEMENT,
        "--use-case",
        USE_CASE,
        *arguments,
    ]


def open_words(repository, **overrides):
    declared = {
        "--engagement": ENGAGEMENT,
        "--use-case": USE_CASE,
        "--use-case-version": "v1",
        "--use-case-digest": f"digest-{USE_CASE}",
        "--mode": "modernisation",
        "--consumer": "the customer service operations manager",
        "--outcome": "decide the next day staffing from settled order volume",
        "--done-definition": "the manager can staff the rota without the old report",
        "--cadence": "every working day before the morning shift",
        "--deadline": "2026-12-01",
        "--provenance": PROVENANCE,
    }
    declared.update(overrides)
    words = ["use-case", "open", "--repository", str(repository)]
    for name, value in declared.items():
        words.extend((name, value))
    return words


def fact_words(repository, kind, declared=None):
    """The words that record one declaration of one kind."""
    fields = DECLARATIONS[kind] if declared is None else declared
    words = route(repository, "record-fact", "--kind", kind)
    for name, value in fields.items():
        words.extend(("--field", f"{name}={value}"))
    return words


def opened(capsys, tmp_path, skip=()):
    """One held use case carrying every declaration kind the aggregate holds."""
    code, _, _ = run(capsys, open_words(tmp_path))
    assert code == EXIT_OK
    for kind in DECLARATIONS:
        if kind in skip:
            continue
        code, _, error = run(capsys, fact_words(tmp_path, kind))
        assert code == EXIT_OK, f"{kind}: {error}"
    return tmp_path


def readiness_digest(capsys, repository):
    code, payload, _, _ = machine(capsys, route(repository, "readiness", *case_words()))
    assert code == EXIT_OK
    return payload["result"]["readiness digest"]


def case_words():
    """The case facts every readiness reading in this proof is given."""
    return (
        "--case-dataset",
        f"{CASE}:{INPUT_DATASET}:input:real",
        "--case-status",
        f"{CASE}:pass",
    )


def cut_words(repository, digest, reading=None, version=VERSION, covered=(STEP, OUTPUT)):
    segments = []
    for segment in covered:
        segments.extend(("--covered-segment", segment))
    return route(
        repository,
        "cut-version",
        "--version",
        version,
        "--version-version",
        "v1",
        "--version-digest",
        f"digest-{version}",
        "--projection",
        f"readiness-{USE_CASE}",
        "--projection-version",
        "v1",
        "--readiness-digest",
        digest,
        *segments,
        "--scenario-case",
        CASE_IDENTITY,
        "--evidence",
        RESULT_IDENTITY,
        *(case_words() if reading is None else reading),
    )


def acceptance_words(repository, reading=None, version=VERSION, decision="accept-1", taken="real"):
    return route(
        repository,
        "record-acceptance",
        "--version",
        version,
        "--decision",
        decision,
        "--decided-by",
        HUMAN,
        "--rationale",
        f"rationale-{decision}:v1:digest-rationale-{decision}",
        "--case-reading",
        f"{CASE_IDENTITY}:{taken}",
        *(case_words() if reading is None else reading),
    )


def cut(capsys, tmp_path, reading=None):
    """One held use case carrying one version cut on one readiness reading."""
    repository = opened(capsys, tmp_path)
    words = case_words() if reading is None else reading
    code, payload, _, _ = machine(capsys, route(repository, "readiness", *words))
    assert code == EXIT_OK
    digest = payload["result"]["readiness digest"]
    code, _, error = run(capsys, cut_words(repository, digest, words))
    assert (code, error) == (EXIT_OK, "")
    return repository, digest


def answered_reading():
    """A case reading that answers the expected output, so the projection differs."""
    return ("--case-expected-output", f"{CASE}:{OUTPUT}:real:modernisation-capture")


def digest_of(capsys, repository, reading):
    """The digest the record's readiness has under one supplied reading."""
    code, payload, _, _ = machine(capsys, route(repository, "readiness", *reading))
    assert code == EXIT_OK
    return payload["result"]["readiness digest"]


def record_text(repository):
    return (repository / "work" / ENGAGEMENT / f"{USE_CASE}.md").read_text(encoding="ascii")


def falsify_stored_disposition(repository, version=None):
    """Change the disposition a stored version carries, and nothing else.

    Naming a version changes that one alone, so a record holding more than one
    version can be read with exactly one of them falsified.
    """
    path = repository / "work" / ENGAGEMENT / f"{USE_CASE}.md"
    written = path.read_text(encoding="ascii")
    header, recorded = composition.read_record(written)
    changed = []
    for line in recorded:
        kind, parts = composition.read_entry(line)
        named = kind == composition.VERSION_KIND and (
            version is None or parts[0].split(":")[0] == version
        )
        if named:
            parts = (*parts[:-1], "every segment buildable and nothing outstanding")
            line = composition.write_entry(kind, parts)
        changed.append(line)
    path.write_text(composition.render_record(header, tuple(changed)), encoding="ascii")
    return path


def held(repository):
    """Replay the held record and return the use case it records."""
    return composition.load_use_case(repository, "work", ENGAGEMENT, USE_CASE)[0]


def test_the_command_surface_carries_every_declared_use_case_route(capsys):
    with pytest.raises(SystemExit) as exited:
        cli.main(["use-case", "--help"])

    printed = capsys.readouterr().out
    assert exited.value.code == 0
    declared = {
        "open",
        "record-fact",
        "readiness",
        "synthesise-dataset",
        "cut-version",
        "record-acceptance",
        "project-gaps",
    }
    assert set(cli.ROUTES) == declared
    for name in declared:
        assert name in printed


def test_a_completed_route_writes_the_declared_envelope(capsys, tmp_path):
    code, payload, out, error = machine(capsys, open_words(tmp_path))

    assert code == EXIT_OK
    assert error == ""
    assert out.endswith("\n") and out.count("\n") == 1
    assert out.isascii()
    assert out == json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    assert set(payload) == {"form", "command", "status", "exit code", "result"}
    assert payload["form"] == ENVELOPE_FORM
    assert payload["command"] == "use-case open"
    assert payload["status"] == "ok"
    assert payload["exit code"] == EXIT_OK
    assert payload["result"]["use case"] == USE_CASE
    assert payload["result"]["state"] == "opened"


def test_a_refused_route_writes_the_declared_error_shape(capsys, tmp_path):
    code, payload, _, error = machine(capsys, route(tmp_path, "readiness"))

    assert code == EXIT_REFUSED
    assert error == ""
    assert set(payload) == {"form", "command", "status", "exit code", "error"}
    assert payload["status"] == "refused"
    assert payload["exit code"] == EXIT_REFUSED
    assert set(payload["error"]) == {"reason", "detail"}
    assert payload["error"]["reason"] == RefusalReason.UNKNOWN_ENGAGEMENT.value
    assert USE_CASE in payload["error"]["detail"]


def test_every_refusal_the_routes_carry_is_an_integrity_refusal():
    assert {reason.value for reason in RefusalReason} == INTEGRITY_REASONS


def test_a_record_is_the_canonical_engagement_record_projection(capsys, tmp_path):
    run(capsys, open_words(tmp_path))
    run(capsys, fact_words(tmp_path, "dataset"))

    written = (tmp_path / "work" / ENGAGEMENT / f"{USE_CASE}.md").read_text(encoding="ascii")

    header, recorded = composition.read_record(written)
    assert written == composition.render_record(header, recorded)
    assert written.splitlines()[0] == f"- **form:** {composition.RECORD_FORM}"
    assert recorded[0].startswith("dataset|")


def test_a_records_root_outside_the_work_directory_is_refused(capsys, tmp_path):
    code, payload, _, _ = machine(
        capsys, [*open_words(tmp_path), "--records-root", "records"]
    )

    assert code == EXIT_REFUSED
    assert payload["error"]["reason"] == RefusalReason.RECORD_OUTSIDE_WORK.value
    assert not (tmp_path / "records").exists()


@pytest.mark.parametrize(
    ("tamper", "expected"),
    [
        ("drop a line", "canonical projection"),
        ("add an entry", "kind the record form does not declare"),
        ("rename a field", "one recorded fact per line"),
    ],
)
def test_a_record_that_is_not_its_own_canonical_projection_is_refused(
    capsys, tmp_path, tamper, expected
):
    run(capsys, open_words(tmp_path))
    path = tmp_path / "work" / ENGAGEMENT / f"{USE_CASE}.md"
    written = path.read_text(encoding="ascii")
    if tamper == "drop a line":
        written = written.replace(f"- **entry:** {composition.EMPTY_LIST}\n", "")
    elif tamper == "add an entry":
        written = written + "- **entry:** invented|something\n"
    else:
        written = written.replace("- **header:**", "- **Header:**")
    path.write_text(written, encoding="ascii")

    code, payload, _, _ = machine(capsys, route(tmp_path, "readiness"))

    assert code == EXIT_REFUSED
    assert payload["error"]["reason"] == RefusalReason.MALFORMED_RECORD.value
    assert expected in payload["error"]["detail"]


def test_a_declared_value_the_record_cannot_take_is_refused(capsys, tmp_path):
    run(capsys, open_words(tmp_path))

    code, payload, _, _ = machine(
        capsys, fact_words(tmp_path, "dataset", {"invented field": "anything"})
    )

    assert code == EXIT_REFUSED
    assert payload["error"]["reason"] == RefusalReason.MALFORMED_VALUE.value
    assert "invented field" in payload["error"]["detail"]


def test_the_work_directory_is_ignored_so_staging_never_commits_a_record():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert f"{composition.WORK_ROOT}/" in ignored


def test_record_fact_covers_every_declaration_kind_the_aggregate_holds(capsys, tmp_path):
    repository = opened(capsys, tmp_path)

    use_case = held(repository)

    assert set(DECLARATIONS) == set(composition.DECLARATION_KINDS)
    assert [output.output_id for output in use_case.target_outputs] == [OUTPUT]
    assert [placeholder.placeholder_id for placeholder in use_case.datasets] == [INPUT_DATASET]
    assert [result.result_id for result in use_case.intermediate_results] == [STEP]
    assert [declared.segment_id for declared in use_case.build_routes] == [OUTPUT]
    assert [scenario.case.identifier for scenario in use_case.scenarios] == [CASE]
    assert [authority.role.value for authority in use_case.authorities] == ["accepting"]
    assert [condition.key.value for condition in use_case.conditions] == ["freshness_deadline"]
    assert [held.artefact.identifier for held in use_case.intake_artefacts] == [ARTEFACT]
    assert [read.product_id for read in use_case.consumer_dependencies] == ["staffing-plan"]
    assert [result.status.value for result in use_case.scenario_results] == ["pass"]


def test_the_record_replays_into_the_use_case_it_recorded(capsys, tmp_path):
    repository = opened(capsys, tmp_path)
    first = held(repository)

    again = held(repository)

    assert first == again
    assert first.target_outputs[0].schema.fields[1].scale == 2
    assert first.target_outputs[0].grain.key_fields == ("order_id",)
    assert first.datasets[0].availability.dataset.identifier == f"{INPUT_DATASET}-2026-09"


def test_a_readiness_listing_reports_the_gaps_their_owners_and_their_fills(capsys, tmp_path):
    repository = opened(capsys, tmp_path)

    code, payload, _, _ = machine(capsys, route(repository, "readiness", *case_words()))

    assert code == EXIT_OK
    reported = payload["result"]
    assert reported["buildable"] is True
    assert [segment["segment"] for segment in reported["segments"]] == [STEP, OUTPUT]
    gaps = {gap["kind"] for gap in reported["gaps"]}
    assert "expected_output" in gaps
    for gap in reported["gaps"]:
        assert gap["suggested title"]
        assert isinstance(gap["synthetic fillable"], bool)
    assert reported["suggested disposition"]


def test_a_full_round_trip_runs_from_open_to_a_named_human_acceptance(capsys, tmp_path):
    repository = opened(capsys, tmp_path)

    digest = readiness_digest(capsys, repository)
    cut, version, _, _ = machine(capsys, cut_words(repository, digest))
    accepted, acceptance, _, _ = machine(capsys, acceptance_words(repository))

    assert (cut, accepted) == (EXIT_OK, EXIT_OK)
    assert version["result"]["readiness digest"] == digest
    assert sorted(version["result"]["covered segments"]) == sorted((STEP, OUTPUT))
    assert version["result"]["segments outside"] == []
    assert acceptance["result"]["state"] == "accepted"
    assert acceptance["result"]["evidence provenance"] == "real"
    assert acceptance["result"]["decided by"] == "acceptance-authority"
    # The route reports the text of the reading it verified the version against.
    assert acceptance["result"]["suggested disposition"] == version["result"]["suggested disposition"]
    use_case = held(repository)
    assert use_case.state.value == "accepted"
    assert use_case.acceptance.decision_id == "accept-1"
    assert use_case.current_version.readiness_digest == digest


def accepted(capsys, tmp_path):
    """One held use case standing accepted on the one version it was cut with."""
    repository, digest = cut(capsys, tmp_path)
    code, _, error = run(capsys, acceptance_words(repository))
    assert (code, error) == (EXIT_OK, "")
    return repository, digest


def test_a_later_version_is_accepted_beside_the_first_without_a_second_move(capsys, tmp_path):
    """A record that already stands accepted takes the next version beside the first.

    The later version is cut on the readiness this record recomputes and
    accepted through the same route. Its named acceptance is recorded on that
    version, the lifecycle stays where the first acceptance left it, and the
    earlier version and the acceptance it was taken through are untouched.
    """
    repository, digest = accepted(capsys, tmp_path)
    first = held(repository)
    written = record_text(repository)
    later = {"version": LATER_VERSION, "covered": (OUTPUT,)}

    # The later cut is held to the digest this record's readiness recomputes,
    # exactly as the first cut was.
    refused, mismatch, _, _ = machine(capsys, cut_words(repository, "0" * 64, **later))
    code, _, error = run(capsys, cut_words(repository, digest, **later))
    assert (refused, mismatch["error"]["reason"]) == (EXIT_REFUSED, RefusalReason.DIGEST_MISMATCH.value)
    assert (code, error) == (EXIT_OK, "")

    code, payload, _, _ = machine(
        capsys,
        acceptance_words(repository, version=LATER_VERSION, decision="accept-2", taken="synthetic"),
    )

    assert code == EXIT_OK
    assert payload["result"]["version"] == LATER_VERSION
    assert payload["result"]["decision"] == "accept-2"
    assert payload["result"]["evidence provenance"] == "synthetic"
    assert payload["result"]["state"] == "accepted"
    use_case = held(repository)
    # One move to verified and one to accepted, made by the first acceptance
    # and by no other.
    assert [move.target.value for move in use_case.transitions] == ["verified", "accepted"]
    assert [version.identity.identifier for version in use_case.versions] == [VERSION, LATER_VERSION]
    assert [decision.decision_id for decision in use_case.decisions] == ["accept-1", "accept-2"]
    assert use_case.acceptance.subject.identifier == LATER_VERSION
    # The later version carries its own coverage statement and the readiness
    # this reading recomputed for it.
    assert use_case.versions[1].covered_segments == (OUTPUT,)
    assert use_case.versions[1].segments_outside == (STEP,)
    assert use_case.versions[1].readiness_digest == digest
    # The earlier version and its acceptance stand exactly as they were taken,
    # in the use case the record replays and in the bytes of the record itself.
    assert (use_case.versions[0], use_case.decisions[0]) == (first.versions[0], first.decisions[0])
    assert record_text(repository).startswith(written)


def test_a_version_that_already_carries_an_acceptance_takes_no_other(capsys, tmp_path):
    """A version is the boundary one named human takes, so its record is fixed there.

    The later version is taken beside the first; the first is not taken twice.
    A second decision on a version the record has already accepted would let
    one boundary carry two readings of its evidence, and it is refused.
    """
    repository, _ = accepted(capsys, tmp_path)
    written = record_text(repository)

    code, payload, _, _ = machine(
        capsys, acceptance_words(repository, decision="accept-again", taken="synthetic")
    )

    assert code == EXIT_REFUSED
    assert payload["error"]["reason"] == RefusalReason.MALFORMED_VALUE.value
    assert VERSION in payload["error"]["detail"]
    assert record_text(repository) == written
    assert [decision.decision_id for decision in held(repository).decisions] == ["accept-1"]


def test_an_in_service_record_takes_a_later_acceptance_beside_its_own(capsys, tmp_path):
    """A record in service takes a later version's acceptance as an accepted one does."""
    repository, digest = accepted(capsys, tmp_path)
    code, _, error = run(
        capsys, cut_words(repository, digest, version=LATER_VERSION, covered=(OUTPUT,))
    )
    assert (code, error) == (EXIT_OK, "")
    in_service = held(repository).enter_service(composition.actor(HUMAN))
    later = composition.held_version(in_service, LATER_VERSION)
    names_the_later = (
        LATER_VERSION,
        "accept-2",
        HUMAN,
        "rationale-accept-2:v1:digest-rationale-accept-2",
        f"{CASE_IDENTITY}:synthetic",
    )

    taken, record = composition.apply_acceptance(in_service, names_the_later, later)

    assert taken.state.value == "in_service"
    assert [move.target.value for move in taken.transitions] == [
        "verified",
        "accepted",
        "in_service",
    ]
    assert [decision.decision_id for decision in taken.decisions] == ["accept-1", "accept-2"]
    assert record.evidence_provenance.value == "synthetic"


def test_a_falsified_disposition_on_the_later_version_is_refused(capsys, tmp_path):
    """The gate the first version passed through is the gate the later one passes through."""
    repository, digest = accepted(capsys, tmp_path)
    code, _, error = run(
        capsys, cut_words(repository, digest, version=LATER_VERSION, covered=(OUTPUT,))
    )
    assert (code, error) == (EXIT_OK, "")
    path = falsify_stored_disposition(repository, LATER_VERSION)
    falsified = path.read_text(encoding="ascii")

    code, payload, _, _ = machine(
        capsys, acceptance_words(repository, version=LATER_VERSION, decision="accept-2")
    )

    assert code == EXIT_REFUSED
    assert payload["error"]["reason"] == RefusalReason.DISPOSITION_MISMATCH.value
    assert LATER_VERSION in payload["error"]["detail"]
    assert VERSION not in payload["error"]["detail"]
    assert path.read_text(encoding="ascii") == falsified
    assert [decision.decision_id for decision in held(repository).decisions] == ["accept-1"]


def test_an_acceptance_on_a_record_whose_scenario_does_not_pass_is_refused(capsys, tmp_path):
    """A record a scenario reports as failing has nothing for a named human to accept."""
    repository = opened(capsys, tmp_path, skip=("scenario-result",))
    failing = {**DECLARATIONS["scenario-result"], "verification status": "fail"}
    code, _, error = run(capsys, fact_words(repository, "scenario-result", failing))
    assert (code, error) == (EXIT_OK, "")
    # The reading a caller supplies says what the record's own result says, so
    # only the failing result itself is at issue here.
    reading = ("--case-dataset", f"{CASE}:{INPUT_DATASET}:input:real", "--case-status", f"{CASE}:fail")
    digest = digest_of(capsys, repository, reading)
    code, _, error = run(capsys, cut_words(repository, digest, reading))
    assert (code, error) == (EXIT_OK, "")

    code, payload, _, _ = machine(capsys, acceptance_words(repository, reading))

    assert code == EXIT_REFUSED
    assert payload["error"]["reason"] == RefusalReason.MALFORMED_VALUE.value
    assert "passing result for every scenario" in payload["error"]["detail"]
    assert held(repository).state.value == "opened"


def test_an_acceptance_on_a_superseded_record_is_refused(capsys, tmp_path):
    """A superseded record crosses no edge back towards an acceptance."""
    repository, _ = accepted(capsys, tmp_path)
    superseded = held(repository).supersede(composition.actor(HUMAN))
    verified = composition.held_version(superseded, VERSION)
    names_the_first = (
        VERSION,
        "accept-2",
        HUMAN,
        "rationale-accept-2:v1:digest-rationale-accept-2",
        f"{CASE_IDENTITY}:real",
    )

    with pytest.raises(CompositionError) as refused:
        composition.apply_acceptance(superseded, names_the_first, verified)

    assert refused.value.reason is RefusalReason.MALFORMED_VALUE
    assert "does not transition" in refused.value.detail
    assert superseded.state.value == "superseded"
    # The aggregate refuses the same record a later acceptance beside its own,
    # because only a record that stands accepted has one to be taken beside.
    with pytest.raises(EngagementError, match="takes a later acceptance beside"):
        superseded.take_acceptance(superseded.decisions[0])


def test_a_cut_on_a_digest_the_projection_does_not_have_is_refused(capsys, tmp_path):
    repository = opened(capsys, tmp_path)

    code, payload, _, _ = machine(capsys, cut_words(repository, "0" * 64))

    assert code == EXIT_REFUSED
    assert payload["error"]["reason"] == RefusalReason.DIGEST_MISMATCH.value
    assert held(repository).versions == ()


@pytest.mark.parametrize("driven", ["readiness", "cut-version", "record-acceptance"])
def test_a_stored_disposition_that_is_not_the_text_readiness_owns_is_refused(
    capsys, tmp_path, driven
):
    repository, digest = cut(capsys, tmp_path)
    path = falsify_stored_disposition(repository)
    falsified = path.read_text(encoding="ascii")
    words = {
        "readiness": route(repository, "readiness", *case_words()),
        "cut-version": cut_words(repository, digest),
        "record-acceptance": acceptance_words(repository),
    }[driven]

    code, payload, _, _ = machine(capsys, words)

    assert code == EXIT_REFUSED
    assert payload["error"]["reason"] == RefusalReason.DISPOSITION_MISMATCH.value
    assert VERSION in payload["error"]["detail"]
    assert path.read_text(encoding="ascii") == falsified
    assert held(repository).state.value == "opened"


@pytest.mark.parametrize(
    ("cut_reading", "acceptance_reading"),
    [(answered_reading(), ()), ((), answered_reading())],
    ids=["omit the reading the cut used", "supply a reading the cut did not use"],
)
def test_an_acceptance_on_a_reading_that_does_not_reproduce_the_version_is_refused(
    capsys, tmp_path, cut_reading, acceptance_reading
):
    repository, digest = cut(capsys, tmp_path, cut_reading)
    # The two readings must really disagree, or the check is not being reached.
    assert digest_of(capsys, repository, acceptance_reading) != digest
    falsify_stored_disposition(repository)
    falsified = record_text(repository)

    code, payload, _, _ = machine(capsys, acceptance_words(repository, acceptance_reading))

    assert code == EXIT_REFUSED
    assert payload["error"]["reason"] == RefusalReason.DIGEST_MISMATCH.value
    assert VERSION in payload["error"]["detail"]
    assert record_text(repository) == falsified
    assert held(repository).state.value == "opened"


def test_an_acceptance_is_refused_on_any_reading_that_does_not_reproduce_the_version(
    capsys, tmp_path
):
    # The record is untouched here, so only the reading divergence is at issue.
    repository, digest = cut(capsys, tmp_path, answered_reading())
    written = record_text(repository)
    assert digest_of(capsys, repository, ()) != digest

    code, payload, _, _ = machine(capsys, acceptance_words(repository, ()))

    assert code == EXIT_REFUSED
    assert payload["error"]["reason"] == RefusalReason.DIGEST_MISMATCH.value
    assert VERSION in payload["error"]["detail"]
    assert record_text(repository) == written
    assert held(repository).state.value == "opened"


def test_a_version_cut_on_a_reading_the_record_no_longer_makes_is_not_compared(
    capsys, tmp_path
):
    repository, _ = cut(capsys, tmp_path)
    falsify_stored_disposition(repository)
    # A fact recorded after the cut changes the reading, so the digest the
    # stored version carries is no longer this projection's.
    later = {**DECLARATIONS["dataset"], "dataset identity": "late-reference"}
    later["dataset role"] = "reference"
    later["availability state"] = "unobtainable"
    later["availability subject"] = ""
    code, _, error = run(capsys, fact_words(repository, "dataset", later))
    assert (code, error) == (EXIT_OK, "")

    code, payload, _, _ = machine(capsys, route(repository, "readiness", *case_words()))

    assert code == EXIT_OK
    use_case = held(repository)
    assert use_case.current_version.readiness_digest != payload["result"]["readiness digest"]


def test_an_acceptance_must_record_the_version_it_was_verified_against(capsys, tmp_path):
    repository, _ = cut(capsys, tmp_path)
    use_case = held(repository)
    verified = composition.held_version(use_case, VERSION)
    names_another = (
        f"{VERSION}-later",
        "accept-1",
        HUMAN,
        "rationale-accept-1:v1:digest-rationale-accept-1",
        f"{CASE_IDENTITY}:real",
    )

    with pytest.raises(CompositionError) as refused:
        composition.apply_acceptance(use_case, names_another, verified)

    assert refused.value.reason is RefusalReason.MALFORMED_VALUE
    assert "verified against" in refused.value.detail
    assert use_case.state.value == "opened"


def test_an_unparsable_command_line_leaves_with_the_usage_code(capsys):
    with pytest.raises(SystemExit) as exited:
        cli.main(["use-case", "readiness"])

    assert exited.value.code == EXIT_USAGE
    assert "error:" in capsys.readouterr().err


def test_a_cut_stores_the_suggested_disposition_readiness_owns(capsys, tmp_path):
    repository = opened(capsys, tmp_path)
    digest = readiness_digest(capsys, repository)

    code, payload, _, _ = machine(capsys, cut_words(repository, digest))

    use_case = held(repository)
    projection = composition.read_readiness(
        use_case, composition.case_index(use_case, case_datasets=(f"{CASE}:{INPUT_DATASET}:input:real",), case_statuses=(f"{CASE}:pass",))
    )
    assert code == EXIT_OK
    assert use_case.current_version.suggested_disposition == projection.suggested_disposition
    assert payload["result"]["suggested disposition"] == projection.suggested_disposition


def test_the_gap_route_drives_the_projector_through_a_supplied_runner(capsys, tmp_path, monkeypatch):
    # The projector reads a consumed product from the use case that provides
    # it, so a record naming a provider outside the projection is left aside.
    repository = opened(capsys, tmp_path, skip=("consumer-dependency",))
    runner = FakePinax()
    monkeypatch.setattr(composition, "pinax_runner", lambda: runner)

    code, payload, _, _ = machine(
        capsys, route(repository, "project-gaps", "--actor", ACTOR, *case_words())
    )

    assert code == EXIT_OK
    assert payload["result"]["parent item"].startswith("evd-")
    assert payload["result"]["gap items"]
    assert payload["result"]["stale gap items"] == []
    assert {command[0] for command in runner.commands} <= {"init", "board", "add", "block", "note", "dep"}
    titles = {item["title"] for item in runner.items.values()}
    assert any("use case" in title for title in titles)


def test_a_synthesised_dataset_is_reported_as_labelled_generated_data(capsys):
    code, payload, _, _ = machine(
        capsys,
        [
            "use-case",
            "synthesise-dataset",
            "--request",
            str(CONSTRAINT_DOCUMENT),
            "--seed",
            "campaign-seed-one",
            "--generator-version",
            "1.0.0",
        ],
    )

    reported = payload["result"]
    assert code == EXIT_OK
    assert reported["provenance"] == "synthetic"
    assert reported["dataset"] == "region-reference-synthetic"
    assert reported["rows"] == 5
    assert reported["content digest"]
    assert reported["generator"] == "evorthon_data.synthetic.generator"
    assert reported["seed"] == "campaign-seed-one"


def test_a_request_document_that_cannot_be_read_is_refused(capsys, tmp_path):
    code, payload, _, _ = machine(
        capsys,
        [
            "use-case",
            "synthesise-dataset",
            "--request",
            str(tmp_path / "absent.json"),
            "--seed",
            "campaign-seed-one",
            "--generator-version",
            "1.0.0",
        ],
    )

    assert code == EXIT_REFUSED
    assert payload["error"]["reason"] == RefusalReason.MALFORMED_VALUE.value


def test_human_output_is_concise_lines_and_a_refusal_reaches_standard_error(capsys, tmp_path):
    code, out, error = run(capsys, open_words(tmp_path))

    assert (code, error) == (EXIT_OK, "")
    assert out.splitlines()[0] == f"engagement: {ENGAGEMENT}"
    assert all(": " in line for line in out.splitlines())

    refused, out, error = run(capsys, route(tmp_path, "readiness", "--use-case", "uc-absent"))

    assert refused == EXIT_REFUSED
    assert out == ""
    assert error.startswith(f"refused: {RefusalReason.UNKNOWN_ENGAGEMENT.value}: ")


def test_the_command_surface_imports_no_synthetic_and_no_delivery_module():
    imported = {}
    for path in PRESENTATION_SOURCES:
        for statement in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(statement, ast.ImportFrom) and statement.module:
                reached = "." * statement.level + statement.module
                imported.setdefault(reached, set()).update(alias.name for alias in statement.names)
            elif isinstance(statement, ast.Import):
                for alias in statement.names:
                    imported.setdefault(alias.name, set())

    reached = {name.lstrip(".") for name in imported}
    assert not any(name.startswith("synthetic") for name in reached)
    assert not any(name.startswith("delivery") for name in reached)
    assert not any(name.startswith("verification") for name in reached)
    assert not any(name.startswith("engagement") for name in reached)
    assert imported["..readiness"] == {"ReadinessProjection"}


def test_no_route_refuses_for_a_readiness_state_a_synthetic_label_or_a_weak_provenance(
    capsys, tmp_path
):
    repository = opened(capsys, tmp_path)
    absent = {**DECLARATIONS["dataset"], "dataset identity": "reference-list"}
    absent["availability state"] = "unobtainable"
    absent["availability subject"] = ""
    absent["dataset role"] = "reference"
    inferred = {
        **DECLARATIONS["intake-artefact"],
        "intake artefact": "desk-note:v1:digest-desk-note",
        "provenance": PROVENANCE.replace(":extracted:", ":inferred:"),
    }

    for declared in (absent, inferred):
        kind = "dataset" if declared is absent else "intake-artefact"
        code, _, error = run(capsys, fact_words(repository, kind, declared))
        assert (code, error) == (EXIT_OK, "")

    code, payload, _, _ = machine(capsys, route(repository, "readiness", *case_words()))
    assert code == EXIT_OK
    assert any(gap["kind"] == "reference_dataset" for gap in payload["result"]["gaps"])


def test_the_composition_root_names_the_fields_of_every_declaration_kind():
    for kind, labels in composition.DECLARATION_PARTS.items():
        with pytest.raises(CompositionError) as refused:
            composition.declaration_parts(kind, {"not a field": "value"})

        assert refused.value.reason is RefusalReason.MALFORMED_VALUE
        for label in labels:
            assert label in refused.value.detail
