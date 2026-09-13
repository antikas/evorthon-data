"""The shared end-to-end route: one traversal of every stage, on fakes only.

The whole lifecycle is driven here exactly as a caller would drive it: one use
case is opened and taken in from the shipped intake artefacts, its readiness is
read with the case facts the approved verification case supplies, its gaps are
projected, one segment is drafted and emitted, the approved items are
dispatched, the case is verified and its failing output diagnosed, advised on,
disposed of and rerun, and a version is cut and accepted.

Nothing here reaches a network, a clock, a model provider, a tracker or a build
tool. The Koine session and the adviser answer through one scripted transport
behind the egress gateway; the tracker, the generator and the campaign answer
through the fake runners their own proofs own. Every external mechanism is
given to the route, and the route is proved to refuse when one is withheld.
"""
# evorthon-verifies: EVD-README-040
# evorthon-verifies: EVD-README-037
from __future__ import annotations

import ast
import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from evorthon_data import composition, lifecycle
from evorthon_data.composition import CompositionError
from evorthon_data.delivery import FixtureSeed
from evorthon_data.engagement import ReviewDisposition
from evorthon_data.koine_session import (
    INTAKE_GENERATOR_ROUTE,
    INTAKE_REVIEW_ROUTE,
    KoineSession,
)
from evorthon_data.security import (
    ModelEgressAuthorization,
    ModelEgressGateway,
    ModelEgressMode,
)
from evorthon_data.verification import presentation as report
from evorthon_data.verification.core.canonical import record_digest
from evorthon_data.verification.domain import AdviserConfidence, RemediationAdvice
from evorthon_data.verification.enforcement.serialization import deserialize_json
from evorthon_data.verification.workflows import (
    ADVISER_REPLY_FORM,
    ADVISER_ROUTE,
    SUPPORTING_IDENTITIES_FIELD,
    AdviserHypothesis,
    AdviserReply,
    AdviserRoute,
)

import declaration_draft_support as draft_support  # noqa: E402
import proof_lifecycle as harness  # noqa: E402
import test_autobuild_route as campaign_fixture  # noqa: E402
import test_cli_remediation as remediation_fixture  # noqa: E402
import test_cli_use_case as use_case_fixture  # noqa: E402
import test_cli_verification as verification_fixture  # noqa: E402
import test_ergasterion_route as generation_fixture  # noqa: E402
import test_koine_session as koine_fixture  # noqa: E402
import test_pinax_projection as tracker_fixture  # noqa: E402

ROOT = Path(__file__).parents[2]
LIFECYCLE_SOURCE = ROOT / "src/evorthon_data/lifecycle.py"

ENGAGEMENT = verification_fixture.ENGAGEMENT
USE_CASE = use_case_fixture.USE_CASE
SESSION = "session-lifecycle"
# The case the approved verification material freezes, and the identities it
# binds its evidence to. The use-case record names the same case, so readiness
# reads the evidence route's own facts rather than an index typed by hand.
CASE = verification_fixture.parity_fixture.scenario().case.case_id
CASE_IDENTITY = f"{CASE}:v1:digest-{CASE}"
RESULT_IDENTITY = f"result-{CASE}:v1:digest-result-{CASE}"
OUTPUT = verification_fixture.OUTPUT_ID
INPUT_DATASET = "input-dataset"
STEP = use_case_fixture.STEP
VERSION = "uc-order-volume-v1"
PROVENANCE = use_case_fixture.PROVENANCE
HUMAN = use_case_fixture.HUMAN

# The items the fake campaign reports, read off the campaign proof's own result
# so the selection this route is given and the outcome it reads back agree.
SELECTED = tuple(
    item["item_id"] for item in campaign_fixture.run_result_payload()["items"]
)

AUTHORITY = remediation_fixture.AUTHORITY
ADVISER_AUTHORITY = f"{AUTHORITY.identifier}:{AUTHORITY.version}:{AUTHORITY.digest}"
# The prose an adviser wrote. No record and no reported value may carry it.
CAUSE = "the candidate run left out the population the frozen input declares"
FIX = "restore the declared population filter in the transformation"
DISCRIMINATING = "a regression test that counts the declared population at the reported grain"
ASSUMPTION = "the localisation is not confirmed"

# The shapes a record must never carry: a lettered volume, a share host, a
# separator between two names, and the words a private tree is laid out under.
SLASH = chr(47)
BACKSLASH = chr(92)
COLON = chr(58)
DRIVE = re.compile("[A-Za-z]" + COLON + "[" + SLASH + re.escape(BACKSLASH) + "]")

# The declared enumerations this route may never state a member of, and the
# declared values it may never build for itself.
DOMAIN_ENUMERATIONS = (
    "VerificationStatus",
    "FaultClass",
    "ClauseFamily",
    "AssuranceLevel",
    "RemediationDisposition",
    "RemediationActorKind",
    "GenerationDisposition",
    "DatasetRole",
    "DatasetProvenance",
    "SegmentState",
    "ConditionState",
)
DOMAIN_VALUES = (
    "ClauseOutcome",
    "VerificationResult",
    "FaultRecord",
    "DeliveryContractOutcome",
    "RemediationDecision",
    "RemediationOutcome",
    "RemediationRerun",
    "ReadinessProjection",
    "UseCase",
    "Version",
    "CaseFacts",
    "QueueSelection",
    "ExactGenerationContract",
)
# The components the architecture record lets the composition root reach, plus
# the standard library this route may read.
PERMITTED_IMPORTS = {
    "__future__.annotations",
    "collections.abc.Mapping",
    "dataclasses.dataclass",
    "pathlib.Path",
}


# --- the scripted transport and the fake runners -------------------------------
#
# The transport, the intake authorization, the co-worker session and the fakes
# themselves have one owner, the shared proof harness, so this proof and the
# executable example proofs are given the same mechanisms. What stays here is
# what belongs to this proof: the reply its adviser is scripted with, and the
# engagement and session it names them for.


def adviser_reply(call) -> AdviserReply:
    """One declared reply citing the evidence identities the packet carried."""
    supporting = tuple(call.fields[SUPPORTING_IDENTITIES_FIELD])
    return AdviserReply(
        form=ADVISER_REPLY_FORM,
        confidence=AdviserConfidence.MEDIUM,
        hypotheses=(
            AdviserHypothesis(
                cause=CAUSE,
                proposed_fix=FIX,
                discriminating_test=DISCRIMINATING,
                supporting_evidence_ids=supporting[:1],
                contradicting_evidence_ids=(),
            ),
        ),
        assumptions=(ASSUMPTION,),
    )


def adviser_route() -> AdviserRoute:
    return harness.adviser_route()


def intake_authorization() -> ModelEgressAuthorization:
    """The scope an environment issues for one intake round of this engagement."""
    return harness.intake_authorization(ENGAGEMENT, SESSION)


def session(gateway: ModelEgressGateway) -> KoineSession:
    """One cold-started co-worker session for this engagement, with the artefacts admitted."""
    return harness.coworker_session(gateway, ENGAGEMENT, SESSION)


class Fakes(harness.ProofFakes):
    """Every fake one traversal is given, scripted with this proof's own reply."""

    def __init__(self) -> None:
        super().__init__(ENGAGEMENT, SESSION, adviser_reply)


# --- the words, documents and fixtures one traversal is given ------------------


def declarations(status: str = "pass") -> tuple[tuple[str, dict], ...]:
    """The declarations the environment holds for what the first round read.

    The shared use-case fixture owns the shape of every declaration kind. Only
    the identities the approved verification case binds its evidence to are
    stated here, so the record and the case name one dataset and one output.
    The recorded scenario result is the status this run ends on, because a
    readiness reading refuses a case whose status the record contradicts.
    """
    held = {kind: dict(fields) for kind, fields in use_case_fixture.DECLARATIONS.items()}
    held.pop("consumer-dependency")
    held["dataset"]["dataset identity"] = INPUT_DATASET
    held["dataset"]["availability subject"] = (
        f"{INPUT_DATASET}-2026-09:v1:digest-{INPUT_DATASET}-2026-09"
    )
    held["target-output"]["output identity"] = OUTPUT
    held["build-route"]["segment identity"] = OUTPUT
    held["scenario"]["scenario case"] = CASE_IDENTITY
    held["scenario-result"]["scenario case"] = CASE_IDENTITY
    held["scenario-result"]["verification result"] = RESULT_IDENTITY
    held["scenario-result"]["verification status"] = status
    return tuple(held.items())


CONFIRMED = (
    (
        "authority",
        {
            "authority role": "evidence_owner",
            "authority actor": "evidence-owner:human",
            "authority subject": STEP,
            "provenance": PROVENANCE,
        },
    ),
)


def header_parts() -> tuple[str, ...]:
    return (
        f"{USE_CASE}:v1:digest-{USE_CASE}",
        ENGAGEMENT,
        "modernisation",
        "the customer service operations manager",
        "decide the next day staffing from settled order volume",
        "the manager can staff the rota without the old report",
        "every working day before the morning shift",
        "2026-12-01",
        PROVENANCE,
    )


def intake(status: str = "pass") -> lifecycle.UseCaseIntake:
    return lifecycle.UseCaseIntake(
        header_parts=header_parts(),
        readings=koine_fixture.intake_readings(),
        answers=koine_fixture.bulk_confirmation(),
        authorization=intake_authorization(),
        declarations=declarations(status),
        confirmed=CONFIRMED,
    )


def delivery(repository: Path) -> lifecycle.SegmentDelivery:
    return lifecycle.SegmentDelivery(
        declaration_request=draft_support.request(),
        proposal_reference="settled-positions-declaration:v1",
        drafted_by="declaration-drafter",
        reviewer="declaration-reviewer:v1:digest-declaration-reviewer",
        disposition="accepted",
        generation_reference="risk-settlement-generation:v1:digest-risk-settlement-generation",
        generation_actor="generation-actor",
        estate_name="settled-positions",
        profile="use-case-build",
        harness="coding-assistant",
        target_repository=repository,
        seeds=(
            FixtureSeed(
                "raw_risk_position_feed.csv", "position_id,booked_at\np-1,2026-01-01\n"
            ),
        ),
        canonicalisation=generation_fixture.CANONICALISATION,
        selections=tuple(f"{item}:ready:approved" for item in SELECTED),
    )


def verification() -> lifecycle.CaseVerification:
    return lifecycle.CaseVerification(
        case_document=verification_fixture.CASE_DOCUMENT,
        material_document=verification_fixture.MATERIAL_DOCUMENT,
        corrected_material_document=remediation_fixture.CORRECTED_MATERIAL,
        evidence_identity=verification_fixture.EVIDENCE_ADAPTER,
        candidate_identity=verification_fixture.CANDIDATE_ADAPTER,
        corrected_candidate_identity=remediation_fixture.CORRECTED_ADAPTER,
        output_id=OUTPUT,
        advice_document=remediation_fixture.ADVICE_DOCUMENT,
        rationale_document=remediation_fixture.RATIONALE_DOCUMENT,
        adviser_route=adviser_route(),
        adviser_authority=ADVISER_AUTHORITY,
        disposition="accepted",
        decided_by=remediation_fixture.DECIDED_BY,
        iteration=f"first-report-loop:{OUTPUT}:build and verify the report span",
        remedy_summary="correct the declared population of the report",
    )


def acceptance() -> lifecycle.VersionAcceptance:
    return lifecycle.VersionAcceptance(
        version_reference=f"{VERSION}:v1:digest-{VERSION}",
        version_identity=VERSION,
        covered_segments=f"{STEP};{OUTPUT}",
        projection_reference=f"readiness-{USE_CASE}:v1",
        decision_identity="accept-1",
        decided_by=HUMAN,
        rationale="rationale-accept-1:v1:digest-rationale-accept-1",
        scenario_case_versions=CASE_IDENTITY,
        evidence=RESULT_IDENTITY,
        case_readings=f"{CASE_IDENTITY}:real",
    )


def advice_place(base: Path) -> Path:
    """The one document the adviser stage writes and the remediation stage reads."""
    return base / "work" / remediation_fixture.ADVICE_DOCUMENT


def withheld_scenario():
    """One run whose divergence names no declared cause, so its packet is withheld.

    A measure that simply differs is a real divergence the run reports, and it
    decides no class, so the packet built over it has nothing decided to
    disclose and the disclosure policy withholds it. The withholding is a
    completed diagnosis, so the traversal goes on.
    """
    return verification_fixture.parity_fixture.value_failure()


def contract_failure_scenario():
    """One run whose published rows reproduce and whose declared facts fail a clause.

    The case declares the four clause families answered over the facts a run
    declares beside the parity clause. A failure of one of them is a real
    failure with no difference between published rows behind it, so the run
    names no failing output and there is no packet for a diagnosis to build.
    """
    return verification_fixture.contract_scenario()


def contract_failure_clauses():
    """The declared facts such a run answers its non-parity clauses over."""
    return verification_fixture.contract_observations(
        failing=verification_fixture.CONTRACT_CLAUSE,
        unobserved=verification_fixture.OPEN_CLAUSE,
    )


def seeded(base: Path, scenario=None, clauses=()):
    """Lay one whole engagement out: the case, the adapters, the material, the documents.

    The shared remediation fixture pre-writes an advice document of its own,
    and it is removed here. A run that failed to write the advice its own
    adviser round produced would otherwise read that one and pass.
    """
    case = verification_fixture.seeded(
        base,
        remediation_fixture.divergent_scenario() if scenario is None else scenario,
        clauses=clauses,
    )
    remediation_fixture.documents(base)
    remediation_fixture.corrected_material(
        base, case, remediation_fixture.corrected_scenario()
    )
    advice_place(base).unlink()
    return case


def traversed(
    base: Path,
    fakes: Fakes | None = None,
    *,
    scenario=None,
    clauses=(),
    declared_status: str = "pass",
    accepting=None,
    **withheld,
):
    """Drive one whole traversal over one scratch repository."""
    fakes = Fakes() if fakes is None else fakes
    seeded(base, scenario, clauses)
    record = lifecycle.run_lifecycle(
        repository=base,
        root="work",
        mechanisms=fakes.mechanisms(**withheld),
        intake=intake(declared_status),
        tracker=lifecycle.TrackerRoute(
            actor_handle=tracker_fixture.ACTOR, prefix="evd", repository=base
        ),
        delivery=delivery(base),
        verification=verification(),
        acceptance=acceptance() if accepting is None else accepting,
    )
    return record, fakes


def written_records(base: Path) -> dict[str, str]:
    """Every record one traversal wrote, by its repository-relative name."""
    held = base / "work"
    return {
        path.relative_to(held).as_posix(): path.read_text(encoding="ascii")
        for path in sorted(held.rglob("*.md"))
    }


# --- the traversal -------------------------------------------------------------


def test_one_traversal_drives_every_stage_in_the_order_the_route_declares(tmp_path):
    record, _ = traversed(tmp_path)

    assert record.form == lifecycle.LIFECYCLE_RECORD_FORM
    assert (record.engagement_id, record.use_case_id) == (ENGAGEMENT, USE_CASE)
    assert [stage.name for stage in record.stages] == list(lifecycle.STAGES)


def test_every_stage_reports_its_outcome_by_identity_and_digest(tmp_path):
    record, _ = traversed(tmp_path)

    first = record.stage(lifecycle.INTAKE_ROUND)
    second = record.stage(lifecycle.RESIDUAL_ROUND)
    assert first.value("facts") == "9"
    assert first.value("review") == ReviewDisposition.APPROVED.value
    assert second.value("facts") == "3"
    # The residual list shrinks because the second round answered a section the
    # first left open, and no other section changed.
    assert len(second.value("residual questions")) < len(first.value("residual questions"))
    assert "8. Authorities" in first.value("residual questions")
    assert "8. Authorities" not in second.value("residual questions")

    readiness = record.stage(lifecycle.READINESS)
    assert readiness.value("use case") == USE_CASE
    assert readiness.value("buildable") == "yes"
    assert len(readiness.value("readiness digest")) == 64

    gaps = record.stage(lifecycle.GAP_PROJECTION)
    assert gaps.value("engagement") == ENGAGEMENT
    assert gaps.value("parent item").startswith("evd-")

    generated = record.stage(lifecycle.SEGMENT_GENERATION)
    assert generated.value("declaration digest").startswith("sha256")
    assert generated.value("disposition") == "accepted"
    assert generated.value("generation") == "risk-settlement-generation"
    assert generated.value("lineage")

    dispatched = record.stage(lifecycle.CAMPAIGN_DISPATCH)
    assert dispatched.value("campaign") == "autobuild-20260908T120000Z"
    assert dispatched.value("stop reason") == "queue_exhausted"
    assert dispatched.value("run digest").startswith("sha256")

    taken = record.stage(lifecycle.CASE_INTAKE)
    verified = record.stage(lifecycle.VERIFICATION)
    assert taken.value("case") == CASE
    assert verified.value("status") == "fail"
    assert verified.value("failed outputs") == OUTPUT

    diagnosed = record.stage(lifecycle.DIAGNOSIS)
    advised = record.stage(lifecycle.ADVICE)
    assert diagnosed.value("gate")
    assert advised.value("case") == CASE
    assert advised.value("hypotheses") == "1"
    assert advised.value("advice") == f"{advised.value('fault')}{SLASH}advice"
    assert advised.value("required authority") == AUTHORITY.identifier

    decided = record.stage(lifecycle.REMEDIATION)
    assert decided.value("disposition") == "accepted"
    assert decided.value("fault") == advised.value("fault")
    assert decided.value("remedy item").startswith("evd-")

    rerun = record.stage(lifecycle.CORRECTED_RERUN)
    assert rerun.value("rerun") == "green"
    assert rerun.value("status") == "pass"
    assert rerun.value("decision") == decided.value("decision")

    cut = record.stage(lifecycle.VERSION_CUT)
    accepted = record.stage(lifecycle.ACCEPTANCE)
    assert cut.value("version") == VERSION
    assert len(cut.value("readiness digest")) == 64
    assert accepted.value("version") == VERSION
    assert accepted.value("decision") == "accept-1"
    assert accepted.value("evidence provenance") == "real"


def test_a_withheld_diagnosis_is_carried_past_the_open_fault_to_a_completed_run(tmp_path):
    """A withholding is a decision the run records, not a wall the run stops at.

    The diagnosis reports the decision; the three stages that needed the
    withheld material are recorded as not reached with that decision as the
    reason; the failing status the verification reported is the status the run
    carries on; and the acceptance evidence and the version cut still run and
    render the open fault. The acceptance itself is recorded as not reached,
    because the aggregate does not verify a use case a scenario reports as
    failing, and the run completes with that record.
    """
    record, fakes = traversed(tmp_path, scenario=withheld_scenario(), declared_status="fail")

    assert [stage.name for stage in record.stages] == list(lifecycle.STAGES)
    diagnosed = record.stage(lifecycle.DIAGNOSIS)
    decision = diagnosed.value(composition.DISCLOSURE_LABEL)
    assert composition.withheld_decision(decision)
    assert diagnosed.value("fault class")
    # Nothing the withheld packet observed reaches the stage the run recorded.
    assert {"diagnostic scope", "localisation status", "confidence"}.isdisjoint(
        label for label, _ in diagnosed.values
    )
    for name in (lifecycle.ADVICE, lifecycle.REMEDIATION, lifecycle.CORRECTED_RERUN):
        stage = record.stage(name)
        assert stage.value(lifecycle.REACHED_LABEL) == lifecycle.NOT_REACHED
        assert stage.value(lifecycle.REASON_LABEL) == decision
    # No adviser was asked anything, so no reply crossed the egress gateway.
    assert ADVISER_ROUTE not in fakes.transport.routes
    assert not advice_place(tmp_path).exists()
    assert record.stage(lifecycle.VERIFICATION).value(lifecycle.STATUS_LABEL) == "fail"
    evidence = record.stage(lifecycle.ACCEPTANCE_EVIDENCE)
    assert evidence.value("case") == CASE
    assert evidence.value(lifecycle.STATUS_LABEL) == "fail"
    assert diagnosed.value("fault id") in evidence.value("localisation")
    assert record.stage(lifecycle.VERSION_CUT).value("version") == VERSION
    accepted = record.stage(lifecycle.ACCEPTANCE)
    assert accepted.value(lifecycle.REACHED_LABEL) == lifecycle.NOT_REACHED
    assert accepted.value(lifecycle.REASON_LABEL) == lifecycle.UNVERIFIED_SCENARIO.format(
        status="fail"
    )


def contract_traversal(base: Path):
    """Drive one whole traversal over a run that failed with no output to diagnose."""
    return traversed(
        base,
        scenario=contract_failure_scenario(),
        clauses=contract_failure_clauses(),
        declared_status="fail",
    )


def test_a_contract_family_failure_is_carried_past_the_open_clauses_to_a_completed_run(
    tmp_path,
):
    """A run with no output to diagnose is carried on exactly as a withheld one is.

    The clauses that failed were answered over the facts the run declared, so
    the comparison named no failing output and there is no packet to build.
    The diagnosis reports that decision; the three stages that needed a packet
    are recorded as not reached with it as the reason; the failing status the
    verification reported is the status the run carries on; and the acceptance
    evidence and the version cut still run and render what is still open. The
    acceptance itself is recorded as not reached on that status.
    """
    record, fakes = contract_traversal(tmp_path)

    assert [stage.name for stage in record.stages] == list(lifecycle.STAGES)
    diagnosed = record.stage(lifecycle.DIAGNOSIS)
    decision = composition.diagnosis_decision(diagnosed.values)
    assert decision == report.NO_FAILING_OUTPUT
    assert diagnosed.value(report.FAILING_FAMILY_FIELD) == verification_fixture.CONTRACT_FAMILY
    assert diagnosed.value(report.FAILING_CLAUSE_FIELD) == verification_fixture.CONTRACT_CLAUSE
    # Nothing a packet would have carried reaches the stage the run recorded.
    assert report.PACKET_LABELS.isdisjoint(
        label for label, _ in diagnosed.values
    )
    for name in (lifecycle.ADVICE, lifecycle.REMEDIATION, lifecycle.CORRECTED_RERUN):
        stage = record.stage(name)
        assert stage.value(lifecycle.REACHED_LABEL) == lifecycle.NOT_REACHED
        assert stage.value(lifecycle.REASON_LABEL) == decision
    # No adviser was asked anything, so no reply crossed the egress gateway.
    assert ADVISER_ROUTE not in fakes.transport.routes
    assert not advice_place(tmp_path).exists()
    assert record.stage(lifecycle.VERIFICATION).value(lifecycle.STATUS_LABEL) == "fail"
    evidence = record.stage(lifecycle.ACCEPTANCE_EVIDENCE)
    assert evidence.value("case") == CASE
    assert evidence.value(lifecycle.STATUS_LABEL) == "fail"
    # The clause that failed is named with the family it answers for, so a run
    # that failed nothing a comparison reported is read as more than a status.
    assert evidence.value(report.FAILING_CLAUSE_FIELD) == report.line(
        verification_fixture.CONTRACT_CLAUSE, verification_fixture.CONTRACT_FAMILY
    )
    assert (
        evidence.value("clauses without sufficient evidence")
        == verification_fixture.OPEN_CLAUSE
    )
    # No packet was built, so the evidence names no localisation to read.
    assert evidence.value("localisation") == lifecycle.NOTHING
    assert record.stage(lifecycle.VERSION_CUT).value("version") == VERSION
    accepted = record.stage(lifecycle.ACCEPTANCE)
    assert accepted.value(lifecycle.REACHED_LABEL) == lifecycle.NOT_REACHED
    assert accepted.value(lifecycle.REASON_LABEL) == lifecycle.UNVERIFIED_SCENARIO.format(
        status="fail"
    )


def test_two_traversals_over_a_contract_family_failure_yield_identical_digests(tmp_path):
    first, _ = contract_traversal(tmp_path / "first")
    second, _ = contract_traversal(tmp_path / "second")

    assert [stage.values for stage in first.stages] == [
        stage.values for stage in second.stages
    ]
    assert written_records(tmp_path / "first") == written_records(tmp_path / "second")


# Three acceptances a route reads and refuses, each for a reason of its own and
# none of them anything to do with a disclosure decision.
REFUSED_ACCEPTANCES = {
    "malformed rationale": {"rationale": "not a written reference"},
    "malformed accepting authority": {"decided_by": ""},
    "wrong version identity": {"version_identity": "uc-not-the-cut-version"},
}


@pytest.mark.parametrize(
    "declared", sorted(REFUSED_ACCEPTANCES), ids=sorted(REFUSED_ACCEPTANCES)
)
def test_the_acceptance_route_s_own_refusal_leaves_a_run_as_it_stands(tmp_path, declared):
    """Nothing the acceptance refuses for is ever written down as a stage not reached.

    The route is driven whenever the case this run carries passed, and whatever
    it then refuses for is its own refusal and leaves the run as it stands. No
    refusal is caught here, so no reason of the acceptance's can be recorded
    under a narrative about a decision somewhere else.
    """
    written = replace(acceptance(), **REFUSED_ACCEPTANCES[declared])

    with pytest.raises(CompositionError) as refused:
        traversed(tmp_path, accepting=written)

    assert refused.value.reason is composition.RefusalReason.MALFORMED_VALUE


def test_an_acceptance_a_withheld_run_never_reaches_is_never_read_either(tmp_path):
    """A run with nothing to accept does not read the acceptance it was given.

    The stage is recorded as not reached because the case this run carries did
    not pass, and the reason says exactly that. The acceptance the run was
    handed is never read, so nothing about it can reach that record.
    """
    written = replace(acceptance(), **REFUSED_ACCEPTANCES["malformed rationale"])

    record, _ = traversed(
        tmp_path,
        scenario=withheld_scenario(),
        declared_status="fail",
        accepting=written,
    )

    stage = record.stage(lifecycle.ACCEPTANCE)
    assert stage.value(lifecycle.REACHED_LABEL) == lifecycle.NOT_REACHED
    assert stage.value(lifecycle.REASON_LABEL) == lifecycle.UNVERIFIED_SCENARIO.format(
        status="fail"
    )


def test_two_traversals_over_a_withheld_diagnosis_yield_identical_digests(tmp_path):
    first, _ = traversed(tmp_path / "first", scenario=withheld_scenario(), declared_status="fail")
    second, _ = traversed(tmp_path / "second", scenario=withheld_scenario(), declared_status="fail")

    assert [stage.values for stage in first.stages] == [
        stage.values for stage in second.stages
    ]
    assert written_records(tmp_path / "first") == written_records(tmp_path / "second")


def test_the_adviser_round_over_a_withheld_packet_asks_nobody_anything(tmp_path):
    """A withholding closes the crossing, and closing it is the round's answer.

    The run itself never asks, so this drives the adviser route over the same
    withheld diagnosis. The route completes, reports which fault it answers for
    and the decision that withheld it, says no advice was asked for, writes no
    advice document, and makes no call across the egress port at all.
    """
    fakes = Fakes()
    traversed(tmp_path, fakes, scenario=withheld_scenario(), declared_status="fail")
    declared = verification()
    before = len(fakes.transport.calls)

    reported = dict(
        composition.ask_case_adviser(
            repository=tmp_path,
            root="work",
            engagement_id=ENGAGEMENT,
            case_document=declared.case_document,
            material_document=declared.material_document,
            evidence_identity=declared.evidence_identity,
            candidate_identity=declared.candidate_identity,
            output_id=declared.output_id,
            advice_document=declared.advice_document,
            adviser_route=declared.adviser_route,
            egress=fakes.mechanisms().egress,
            required_authority=declared.adviser_authority,
            authorization=declared.adviser_authorization,
        ).values
    )

    assert composition.withheld_decision(reported[composition.DISCLOSURE_LABEL])
    assert reported["case"] == CASE
    assert reported["fault"]
    assert reported["required authority"] == AUTHORITY.identifier
    assert len(fakes.transport.calls) == before
    assert ADVISER_ROUTE not in fakes.transport.routes
    assert not advice_place(tmp_path).exists()


def test_every_fake_saw_exactly_the_calls_the_route_declares_and_nothing_else(tmp_path):
    _, fakes = traversed(tmp_path)

    assert fakes.transport.routes == [
        INTAKE_GENERATOR_ROUTE,
        INTAKE_REVIEW_ROUTE,
        INTAKE_GENERATOR_ROUTE,
        INTAKE_REVIEW_ROUTE,
        ADVISER_ROUTE,
    ]
    assert [call.mode for call in fakes.transport.calls] == [ModelEgressMode.FAKE] * 5

    estate = str(tmp_path / "work" / ENGAGEMENT / composition.ESTATE_DIRECTORY / "settled-positions")
    assert fakes.generator.calls == [
        ("--help",),
        ("init", estate),
        ("validate", "--estate-root", estate),
        ("emit-products", "--estate-root", estate),
        ("emit-products", "--check", "--estate-root", estate),
        ("product-graph", "--check", "--estate-root", estate),
        ("contracts", "--check", "--estate-root", estate),
    ]
    assert fakes.campaign.calls == [
        ("--help",),
        ("run", "--help"),
        (
            "run",
            "--repository",
            str(tmp_path),
            "--profile",
            "use-case-build",
            "--harness",
            "coding-assistant",
            "--delivery-mode",
            "current-branch-pr",
            "--allow-item",
            SELECTED[0],
            "--allow-item",
            SELECTED[1],
        ),
    ]
    issued = {command[0] for command in fakes.tracker.commands}
    assert issued <= {"init", "board", "add", "block", "note", "dep"}
    assert "--allow-delivery" not in fakes.campaign.calls[-1]


# --- the mechanisms a run refuses without -------------------------------------


@pytest.mark.parametrize("name", lifecycle.MECHANISM_NAMES)
def test_withholding_any_mechanism_refuses_before_any_stage_runs(tmp_path, name):
    fakes = Fakes()

    with pytest.raises(CompositionError) as refused:
        traversed(tmp_path, fakes, **{name: None})

    assert refused.value.reason is composition.RefusalReason.MALFORMED_VALUE
    assert name in refused.value.detail
    assert fakes.transport.calls == []
    assert fakes.tracker.commands == []
    assert fakes.generator.calls == []
    assert fakes.campaign.calls == []
    assert not (tmp_path / "work" / ENGAGEMENT / f"{USE_CASE}.md").exists()


def test_a_run_given_no_mechanisms_at_all_names_every_one_it_drives(tmp_path):
    with pytest.raises(CompositionError) as refused:
        lifecycle.run_lifecycle(
            repository=tmp_path,
            root="work",
            mechanisms=lifecycle.LifecycleMechanisms(),
            intake=intake(),
            tracker=lifecycle.TrackerRoute(actor_handle=tracker_fixture.ACTOR, prefix="evd"),
            delivery=delivery(tmp_path),
            verification=verification(),
            acceptance=acceptance(),
        )

    for name in lifecycle.MECHANISM_NAMES:
        assert name in refused.value.detail


# --- what the records may carry ------------------------------------------------


def test_no_record_this_route_writes_carries_a_path_or_a_declared_value(tmp_path):
    record, _ = traversed(tmp_path)
    held = written_records(tmp_path)
    reported = "\n".join(
        f"{stage.name} {label} {text}"
        for stage in record.stages
        for label, text in stage.values
    )
    stage_records = "\n".join(
        text for name, text in held.items() if f"/{lifecycle.LIFECYCLE_DIRECTORY}/" in name
    )

    assert stage_records
    # No record this run wrote anywhere, of any kind, names a machine place.
    for name, text in held.items():
        assert DRIVE.search(text) is None, name
        assert str(tmp_path) not in text, name
    for written in (reported, stage_records):
        assert written.isascii()
        assert DRIVE.search(written) is None
        assert BACKSLASH not in written
        assert f"{SLASH}{SLASH}" not in written
        assert str(tmp_path) not in written
        for value in (
            CAUSE,
            FIX,
            DISCRIMINATING,
            ASSUMPTION,
            remediation_fixture.RATIONALE_SUMMARY,
            remediation_fixture.EDITED_FIX,
            remediation_fixture.EDIT_STATEMENT,
            "customer-0",
            "work" + SLASH,
        ):
            assert value not in written


def test_every_stage_record_is_the_canonical_projection_of_its_own_facts(tmp_path):
    record, _ = traversed(tmp_path)

    for stage in record.stages:
        read = composition.read_case_record(
            tmp_path
            / "work"
            / ENGAGEMENT
            / lifecycle.LIFECYCLE_DIRECTORY
            / lifecycle.STAGE_RECORD.format(stage=stage.name),
            lifecycle.LIFECYCLE_RECORD_FORM,
        )
        assert read["stage"] == (stage.name,)
        assert read["outcome"] == tuple(
            lifecycle.VALUE_LINE.format(label=label, text=text) for label, text in stage.values
        )


# --- the route decides nothing -------------------------------------------------


def called_names(tree: ast.AST) -> set[str]:
    """Name every plain function this source calls by name."""
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def attribute_calls(tree: ast.AST) -> set[str]:
    """Name every call this source makes on something it reached through a name."""
    return {
        f"{node.func.value.id}.{node.func.attr}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
    }


def call_roots(tree: ast.AST) -> set[str]:
    """Name the root of every call this source makes through an attribute chain.

    A call written as one name reached through another, however deep, is
    counted under the name it started from, so a stage driven on something
    reached through a mechanism cannot slip past the gate.
    """
    roots: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        target = node.func
        while isinstance(target, ast.Attribute):
            target = target.value
        roots.add(target.id if isinstance(target, ast.Name) else type(target).__name__)
    return roots


def stated_members(tree: ast.AST) -> set[str]:
    """Name every declared enumeration member one source states for itself."""
    return {
        f"{node.value.id}.{node.attr}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in DOMAIN_ENUMERATIONS
    }


def branch_names(tree: ast.AST) -> set[str]:
    """Name everything one source reads inside a condition of its own."""
    return {
        node.id
        for statement in ast.walk(tree)
        if isinstance(statement, (ast.If, ast.IfExp))
        for node in ast.walk(statement.test)
        if isinstance(node, ast.Name)
    }


def test_the_route_states_no_declared_member_and_builds_no_declared_value():
    tree = ast.parse(LIFECYCLE_SOURCE.read_text(encoding="utf-8"))

    assert stated_members(tree) == set()
    assert called_names(tree) & set(DOMAIN_VALUES) == set()
    assert attribute_calls(tree) & {f"composition.{name}" for name in DOMAIN_VALUES} == set()


def test_the_route_calls_only_the_composition_root_its_mechanisms_and_its_own_helpers():
    source = LIFECYCLE_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    own = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    declared = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef))
    }

    # Every plain call is one this module declares or a builtin it reads with.
    assert called_names(tree) - own - declared <= {
        "CompositionError",
        "dataclass",
        "frozenset",
        "getattr",
        "isinstance",
        "len",
        "list",
        "property",
        "str",
        "tuple",
    }
    # Every call through a name is the composition root's, one of the injected
    # mechanisms', or a value a stage already returned.
    reached = call_roots(tree)
    aliases = set()
    for statement in ast.walk(tree):
        if isinstance(statement, (ast.Import, ast.ImportFrom)):
            aliases.update(
                alias.asname or alias.name.split(".")[0] for alias in statement.names
            )
    # The one module this route reaches into is the composition root. Every
    # other name it calls through is a given mechanism, a value a stage
    # returned, or one of this module's own written forms.
    assert reached & aliases == {"composition"}
    assert reached - aliases == {
        "Constant",
        "LIST_SEPARATOR",
        "STAGE_RECORD",
        "UNVERIFIED_SCENARIO",
        "VALUE_LINE",
        "decided",
        "fields",
        "first",
        "held",
        "mechanisms",
        "rerun",
        "verified",
    }


def test_the_route_holds_no_branch_on_an_engagement_or_a_use_case_identity():
    source = LIFECYCLE_SOURCE.read_text(encoding="utf-8")

    assert {"engagement_id", "use_case_id"}.isdisjoint(branch_names(ast.parse(source)))
    # No identity of this proof, and no name either shipped example is built
    # from, appears anywhere in the route.
    for example in (
        ENGAGEMENT,
        USE_CASE,
        CASE,
        OUTPUT,
        INPUT_DATASET,
        STEP,
        "customer-service",
        "renewable",
        "observability",
    ):
        assert example not in source


def test_the_route_carries_the_composition_marker_and_imports_only_what_it_may():
    source = LIFECYCLE_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for statement in ast.walk(tree):
        if isinstance(statement, ast.Import):
            imported.update(alias.name for alias in statement.names)
        elif isinstance(statement, ast.ImportFrom):
            target = statement.module or ""
            if statement.level:
                target = "evorthon_data" + (f".{target}" if target else "")
            imported.update(f"{target}.{alias.name}" for alias in statement.names)

    assert "# evorthon-component: composition\n" in source
    product = {name for name in imported if name.startswith("evorthon_data")}
    assert product
    for name in product:
        assert name.startswith("evorthon_data.composition"), name
    assert imported - product <= PERMITTED_IMPORTS
    assert source.isascii()
    assert "\r" not in source
    assert not re.search(r"evd-[a-z0-9]{4}", source)


# --- the same inputs give the same run -----------------------------------------


def test_the_advice_the_remediation_reads_is_the_one_this_run_s_round_produced(tmp_path):
    """The recorded advice digest is the digest of this run's own scripted reply."""
    record, fakes = traversed(tmp_path)
    written = advice_place(tmp_path).read_text(encoding="ascii")
    advice = deserialize_json(written)
    decided = record.stage(lifecycle.REMEDIATION)

    assert isinstance(advice, RemediationAdvice)
    assert decided.value("advice digest") == record_digest(advice)
    assert decided.value("advice") == record.stage(lifecycle.ADVICE).value("advice")
    # It is the reply the transport scripted for this run, not a document an
    # environment happened to be holding.
    scripted = adviser_reply(fakes.transport.calls[-1])
    assert advice.hypotheses == tuple(item.cause for item in scripted.hypotheses)
    assert advice.proposed_fixes == tuple(item.proposed_fix for item in scripted.hypotheses)
    assert advice.assumptions == scripted.assumptions
    assert advice.confidence is scripted.confidence


def test_without_the_advice_the_adviser_wrote_the_next_stage_goes_red(tmp_path):
    """Remove the one write the adviser stage makes and the disposition has nothing to read."""
    traversed(tmp_path)
    advice_place(tmp_path).unlink()

    with pytest.raises(CompositionError) as refused:
        composition.record_remediation(
            repository=tmp_path,
            root="work",
            engagement_id=ENGAGEMENT,
            case_document=verification_fixture.CASE_DOCUMENT,
            advice_document=remediation_fixture.ADVICE_DOCUMENT,
            disposition="accepted",
            decided_by=remediation_fixture.DECIDED_BY,
            rationale_document=remediation_fixture.RATIONALE_DOCUMENT,
        )

    assert refused.value.reason is composition.RefusalReason.MALFORMED_VALUE
    assert "could not be read" in refused.value.detail


def test_two_traversals_over_the_same_inputs_yield_identical_digests(tmp_path):
    first, _ = traversed(tmp_path / "first")
    second, _ = traversed(tmp_path / "second")

    assert [stage.values for stage in first.stages] == [
        stage.values for stage in second.stages
    ]
    assert written_records(tmp_path / "first") == written_records(tmp_path / "second")


def test_the_case_index_readiness_is_given_is_read_off_the_approved_case(tmp_path):
    seeded(tmp_path)
    base = composition.records_root(tmp_path, "work")

    declared = lifecycle.case_facts(base, verification())
    reached = lifecycle.case_facts(base, verification(), status="pass")

    case = json.loads(
        (tmp_path / "work" / ENGAGEMENT / "case.json").read_text(encoding="ascii")
    )
    assert declared["case_datasets"] == (
        f"{CASE}:{INPUT_DATASET}:input:real",
    )
    assert declared["case_expected_outputs"] == (
        f"{CASE}:{OUTPUT}:real:modernisation-capture",
    )
    assert declared["case_statuses"] == ()
    assert reached["case_statuses"] == (f"{CASE}:pass",)
    assert case["record"]["case_id"] == CASE


INJECTED = {
    "a stated declared member": "def _injected():\n    return VerificationStatus.PASS\n",
    "a built declared value": "def _injected():\n    return CaseFacts(datasets=())\n",
    "a call past the composition root": (
        "def _injected(runner):\n    return runner.session.dispatch()\n"
    ),
    "a branch on the engagement": (
        'def _injected(engagement_id):\n'
        '    if engagement_id == "an engagement":\n'
        "        return 1\n"
        "    return 0\n"
    ),
    "a stated closed decision": (
        f'def _injected():\n    return "{report.NO_FAILING_OUTPUT}"\n'
    ),
}


def test_the_route_states_no_closed_decision_of_its_own():
    """The decision that shapes which stages are driven is read, not written here."""
    source = LIFECYCLE_SOURCE.read_text(encoding="utf-8")

    assert verification_fixture.stated_decisions(source) == []


@pytest.mark.parametrize("violation", sorted(INJECTED), ids=sorted(INJECTED))
def test_an_injected_violation_reddens_the_gate_that_answers_for_it(violation):
    """Each gate this proof adds is driven red once, on the source it reads."""
    clean = LIFECYCLE_SOURCE.read_text(encoding="utf-8")
    written = clean + "\n\n" + INJECTED[violation]
    tree = ast.parse(written)
    aliases = {"composition", "CompositionError", "RefusalReason", "Mapping", "dataclass", "Path"}
    reddened = (
        stated_members(tree) != set()
        or called_names(tree) & set(DOMAIN_VALUES) != set()
        or call_roots(tree) - aliases != call_roots(ast.parse(clean)) - aliases
        or not {"engagement_id", "use_case_id"}.isdisjoint(branch_names(tree))
        or verification_fixture.stated_decisions(written) != []
    )

    assert reddened, violation
