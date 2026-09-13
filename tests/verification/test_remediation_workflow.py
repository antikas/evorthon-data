"""Human-controlled remediation: who may decide, what each disposition leaves, and the rerun."""
# evorthon-verifies: EVD-README-024
# evorthon-verifies: EVD-README-022
from __future__ import annotations

import ast
import inspect as introspection
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import test_contract_engine as contract_fixture
import test_diagnostic_adviser as adviser_fixture
from evorthon_data.verification.core.canonical import (
    canonical_digest,
    canonical_record_bytes,
    case_digest,
    record_digest,
)
from evorthon_data.verification.domain.contracts import (
    DOMAIN_FIELD_INVENTORY,
    AssuranceLevel,
    EnvironmentCertificateClaim,
    EvidenceReference,
    Identity,
    OwnerPresentedEvidence,
    RemediationAdvice,
    RemediationDecision,
    RemediationDisposition,
    VerificationStatus,
)
from evorthon_data.verification.workflows import remediation as workflow
from evorthon_data.verification.workflows.adviser import read_adviser_reply
from evorthon_data.verification.workflows.remediation import (
    APPROVING_DISPOSITIONS,
    HUMAN_DISPOSITIONS,
    REMEDIATION_DECISION_VERSION,
    REMEDIATION_WORK_VERSION,
    WORK_REMAINDER,
    DecidingActor,
    HumanDisposition,
    RemediationActorKind,
    RemediationOutcome,
    RemediationRefusalReason,
    RemediationRefused,
    record_remediation_decision,
    rerun_corrected_case,
)

AUTHORITY = adviser_fixture.AUTHORITY
CASE = Identity("case-daily-output", "v1", canonical_digest(b"case-daily-output"))
ANOTHER = Identity("another-authority", "v1", canonical_digest(b"another-authority"))
EDITED_FIX = "restore the declared population filter for the reported window only"
EDIT_STATEMENT = "the accepting authority narrowed the remedy to the reported window"
ASKED = "the run log of the window the fault reports"
REQUEST_SUMMARY = f"the decision waits on {ASKED}"
# The clause the prepared delivery contract is driven to fail, and the one used
# to prove a regression on work that passed before.
DEFECT_CLAUSE = "conformance"
REGRESSION_CLAUSE = "invariant"
# The modules that must never build a recorded decision for themselves: the
# adviser writes the advice a person disposes of, and the composition root
# carries what this workflow decided without deciding any of it.
NON_BUILDERS = (
    Path(__file__).parents[2] / "src/evorthon_data/verification/workflows/adviser.py",
    Path(__file__).parents[2] / "src/evorthon_data/composition.py",
)
ADVISER = NON_BUILDERS[0]
# The records neither of them may build.
DECISION_RECORDS = ("RemediationDecision", "RemediationOutcome")
# The two entry points that record a decision and rerun a correction. The
# adviser must not reach either; the composition root drives exactly these two
# and decides nothing of its own, which its route proof holds it to.
DECISION_ROUTES = ("record_remediation_decision", "rerun_corrected_case")


def advice(**changes: object) -> RemediationAdvice:
    """One recorded advice record, written by the adviser from a gated packet."""
    gated = adviser_fixture.packet()
    recorded = read_adviser_reply(
        adviser_fixture.reply(gated), gated, required_authority=AUTHORITY
    )
    assert isinstance(recorded, RemediationAdvice)
    return replace(recorded, **changes) if changes else recorded


def actor(kind: RemediationActorKind = RemediationActorKind.HUMAN, identity: Identity = AUTHORITY):
    return DecidingActor(identity=identity, kind=kind)


def rationale(summary: str = "the authority disposed of the advice") -> EvidenceReference:
    return EvidenceReference(
        "remediation-rationale", "v1", canonical_digest(b"remediation-rationale"), summary
    )


def owner_evidence(identity: Identity = AUTHORITY) -> OwnerPresentedEvidence:
    return OwnerPresentedEvidence(
        "owner-approval",
        "v1",
        canonical_digest(b"owner-approval"),
        identity,
        EvidenceReference("approval", "v1", canonical_digest(b"approval"), "approved by the owner"),
    )


def certificate(
    identity: Identity = AUTHORITY,
    level: AssuranceLevel = AssuranceLevel.ENVIRONMENT_CERTIFIED,
) -> EnvironmentCertificateClaim:
    return EnvironmentCertificateClaim(
        "certificate-claim", "v1", canonical_digest(b"certificate"), identity, level
    )


def disposition(
    taken: RemediationDisposition = RemediationDisposition.ACCEPTED, **changes: object
) -> HumanDisposition:
    values: dict[str, object] = {
        "disposition": taken,
        "decided_by": actor(),
        "rationale": rationale(),
    }
    if taken is RemediationDisposition.MODIFIED:
        values["edited_fixes"] = (EDITED_FIX,)
        values["edit_statement"] = EDIT_STATEMENT
    if taken is RemediationDisposition.REQUEST_MORE_EVIDENCE:
        values["requested_evidence"] = (ASKED,)
        values["rationale"] = rationale(REQUEST_SUMMARY)
    values.update(changes)
    return HumanDisposition(**values)  # type: ignore[arg-type]


def record(
    taken: RemediationDisposition = RemediationDisposition.ACCEPTED,
    *,
    case: Identity = CASE,
    recorded: RemediationAdvice | None = None,
    **changes: object,
) -> RemediationOutcome:
    return record_remediation_decision(
        advice() if recorded is None else recorded, disposition(taken, **changes), case=case
    )


def refusal(**changes: object) -> RemediationRefusalReason:
    with pytest.raises(RemediationRefused) as raised:
        record(**changes)  # type: ignore[arg-type]
    return raised.value.reason


def case_identity(case) -> Identity:
    return Identity(identifier=case.case_id, version=case.version, digest=case_digest(case))


def failing_facts(clause_id: str):
    return contract_fixture.observations_with(
        contract_fixture.facts_for(clause_id, contract_fixture.FAILING_FACTS)
    )


@pytest.fixture(scope="module")
def corrected():
    """One prepared case whose interface clause failed, and the approved remedy for it."""
    prepared = contract_fixture.Prepared()
    prior = prepared.execute(observations=failing_facts(DEFECT_CLAUSE))
    approved = record(case=case_identity(prepared.case))
    return SimpleNamespace(prepared=prepared, prior=prior, outcome=approved)


def rerun(corrected, **changes: object):
    values: dict[str, object] = {
        "prior": corrected.prior,
        "reconciliation": corrected.prepared.reconciliation,
        "observations": contract_fixture.passing_observations(),
    }
    values.update(changes)
    return rerun_corrected_case(
        values.pop("outcome", corrected.outcome),
        values.pop("case", corrected.prepared.case),
        corrected.prepared.intake,
        **values,  # type: ignore[arg-type]
    )


def rerun_refusal(corrected, **changes: object) -> RemediationRefusalReason:
    with pytest.raises(RemediationRefused) as raised:
        rerun(corrected, **changes)
    return raised.value.reason


# --- Advice alone changes nothing ---


def test_advice_alone_reaches_no_work_and_no_decision():
    """Every public route into a record takes a human disposition or a recorded one."""
    routes = [
        getattr(workflow, name)
        for name in workflow.__all__
        if callable(getattr(workflow, name)) and not isinstance(getattr(workflow, name), type)
    ]

    assert [route.__name__ for route in routes] == ["record_remediation_decision", "rerun_corrected_case"]
    for route in routes:
        parameters = set(introspection.signature(route).parameters)
        assert {"disposition", "outcome"} & parameters, route.__name__
    with pytest.raises(TypeError):
        record_remediation_decision(advice())
    with pytest.raises(TypeError):
        record_remediation_decision(advice(), case=CASE)
    with pytest.raises(TypeError):
        rerun_corrected_case(advice())


def test_the_one_decision_and_the_one_work_identity_are_built_from_a_disposition():
    tree = ast.parse(Path(workflow.__file__).read_text(encoding="utf-8"))
    built = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") in {"RemediationDecision", "_work_identity"}
    ]
    holders = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and any(inner in built for inner in ast.walk(node))
    ]

    assert len(built) == 2
    assert set(holders) == {"record_remediation_decision"}
    parameters = set(introspection.signature(record_remediation_decision).parameters)
    assert "disposition" in parameters


def test_these_workflows_never_reach_the_tracker():
    """The delivery adapters read these workflows; nothing here reads them back."""
    tree = ast.parse(Path(workflow.__file__).read_text(encoding="utf-8"))

    assert [
        item
        for item in adviser_fixture.imported_paths(tree)
        if item.startswith("evorthon_data.delivery") or "pinax" in item
    ] == []


@pytest.mark.parametrize("path", NON_BUILDERS, ids=[path.name for path in NON_BUILDERS])
def test_no_module_outside_these_workflows_builds_a_recorded_decision(path):
    source = path.read_text(encoding="utf-8")

    for name in DECISION_RECORDS:
        assert name not in source, name


def test_the_adviser_never_reaches_a_recorded_decision():
    source = ADVISER.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for name in DECISION_ROUTES:
        assert name not in source, name
    assert [item for item in adviser_fixture.imported_paths(tree) if "remediation" in item] == []


# --- The four dispositions ---


def test_accepting_the_advice_approves_one_work_identity_and_repeats_it():
    outcome = record()
    again = record()
    work = outcome.approved_work

    assert outcome == again
    assert outcome.decision.disposition is RemediationDisposition.ACCEPTED
    assert work is not None and work == again.approved_work
    assert work.identifier.startswith(f"{WORK_REMAINDER}-")
    assert work.version == REMEDIATION_WORK_VERSION
    assert outcome.decision.version == REMEDIATION_DECISION_VERSION
    assert outcome.decision.advice == Identity(
        outcome.advice.advice_id, outcome.advice.version, record_digest(outcome.advice)
    )
    assert outcome.fault == outcome.advice.fault
    assert outcome.fault_open is False


def test_the_approved_work_is_derived_from_the_advice_identity_and_the_case():
    first = record()
    other_case = record(case=replace(CASE, version="v2"))
    other_advice = record(recorded=advice(version="evorthon.verification.adviser.advice.v2"))

    approved = {first.approved_work, other_case.approved_work, other_advice.approved_work}
    assert len(approved) == 3


def test_an_edit_records_a_new_advice_version_and_leaves_the_original_untouched():
    original = advice()
    before = canonical_record_bytes(original)

    outcome = record_remediation_decision(
        original, disposition(RemediationDisposition.MODIFIED), case=CASE
    )
    edited = outcome.advice

    assert canonical_record_bytes(original) == before
    assert edited is not original
    assert edited.advice_id == original.advice_id
    assert edited.version != original.version
    assert workflow.EDITED_ADVICE_MARKER in edited.version
    assert edited.proposed_fixes == (EDITED_FIX,)
    assert edited.discriminating_tests == original.discriminating_tests
    assert edited.supporting_evidence == original.supporting_evidence
    assert edited.contradicting_evidence == original.contradicting_evidence
    assert edited.assumptions == (*original.assumptions, EDIT_STATEMENT)
    assert edited.required_authority == original.required_authority
    assert outcome.decision.disposition is RemediationDisposition.MODIFIED
    assert outcome.decision.advice.digest == record_digest(edited)
    assert outcome.approved_work is not None
    assert outcome.approved_work != record().approved_work


def test_rejecting_the_advice_approves_no_work_and_leaves_the_fault_open():
    outcome = record(RemediationDisposition.REJECTED)

    assert outcome.decision.disposition is RemediationDisposition.REJECTED
    assert outcome.decision.approved_work is None
    assert outcome.fault_open is True
    assert outcome.advice == advice()
    assert outcome.requested_evidence == ()


def test_an_evidence_request_approves_no_work_and_names_what_is_asked_for():
    outcome = record(RemediationDisposition.REQUEST_MORE_EVIDENCE)

    assert outcome.decision.disposition is RemediationDisposition.REQUEST_MORE_EVIDENCE
    assert outcome.decision.approved_work is None
    assert outcome.fault_open is True
    assert outcome.requested_evidence == (ASKED,)
    assert ASKED in outcome.decision.rationale.summary


def test_an_evidence_request_whose_rationale_names_nothing_asked_for_is_refused():
    reason = refusal(
        taken=RemediationDisposition.REQUEST_MORE_EVIDENCE,
        rationale=rationale("the decision waits on something the rationale does not name"),
    )

    assert reason is RemediationRefusalReason.INCOMPLETE_DISPOSITION


@pytest.mark.parametrize(
    "taken, changes",
    (
        (RemediationDisposition.MODIFIED, {"edited_fixes": ()}),
        (RemediationDisposition.MODIFIED, {"edit_statement": None}),
        (RemediationDisposition.ACCEPTED, {"edited_fixes": (EDITED_FIX,)}),
        (RemediationDisposition.ACCEPTED, {"requested_evidence": (ASKED,)}),
        (RemediationDisposition.REJECTED, {"edit_statement": EDIT_STATEMENT}),
        (RemediationDisposition.REQUEST_MORE_EVIDENCE, {"requested_evidence": ()}),
    ),
)
def test_a_disposition_carrying_material_it_does_not_own_is_refused(taken, changes):
    assert refusal(taken=taken, **changes) is RemediationRefusalReason.INCOMPLETE_DISPOSITION


def test_the_advisers_own_proposed_state_is_not_a_human_disposition():
    assert RemediationDisposition.PROPOSED not in HUMAN_DISPOSITIONS
    assert set(HUMAN_DISPOSITIONS) == set(RemediationDisposition) - {RemediationDisposition.PROPOSED}
    assert refusal(taken=RemediationDisposition.PROPOSED) is RemediationRefusalReason.UNDECLARED_DISPOSITION


def test_advice_that_is_not_a_recorded_record_and_a_disposition_that_is_not_declared_are_refused():
    with pytest.raises(RemediationRefused) as unrecorded:
        record_remediation_decision("the adviser said so", disposition(), case=CASE)
    with pytest.raises(RemediationRefused) as undeclared:
        record_remediation_decision(advice(), RemediationDisposition.ACCEPTED, case=CASE)

    assert unrecorded.value.reason is RemediationRefusalReason.UNDECLARED_ADVICE
    assert undeclared.value.reason is RemediationRefusalReason.UNDECLARED_DISPOSITION


# --- Who may decide ---


@pytest.mark.parametrize(
    "named",
    (
        ANOTHER,
        Identity(AUTHORITY.identifier, "v2", AUTHORITY.digest),
        Identity(AUTHORITY.identifier, AUTHORITY.version, canonical_digest(b"another-digest")),
    ),
    ids=["another identity", "another version", "another digest"],
)
def test_only_the_authority_the_advice_requires_can_record_the_decision(named):
    assert refusal(decided_by=actor(identity=named)) is RemediationRefusalReason.UNNAMED_AUTHORITY


@pytest.mark.parametrize("kind", (RemediationActorKind.MODEL, RemediationActorKind.SERVICE))
def test_an_actor_that_is_not_a_human_cannot_record_the_decision(kind):
    assert refusal(decided_by=actor(kind=kind)) is RemediationRefusalReason.NON_HUMAN_ACTOR


@pytest.mark.parametrize("taken", HUMAN_DISPOSITIONS)
def test_no_disposition_at_all_is_recorded_for_the_wrong_person(taken):
    for named in (actor(identity=ANOTHER), actor(kind=RemediationActorKind.MODEL)):
        with pytest.raises(RemediationRefused):
            record(taken=taken, decided_by=named)


# --- The assurance class ---


def test_a_named_authority_on_its_own_states_the_declared_class():
    outcome = record()

    assert outcome.assurance is AssuranceLevel.DECLARED
    assert outcome.presented_owner_evidence is None
    assert outcome.presented_certificate is None


def test_owner_presented_evidence_states_the_owner_presented_class():
    presented = owner_evidence()

    outcome = record(owner_presented=presented)

    assert outcome.assurance is AssuranceLevel.OWNER_PRESENTED
    assert outcome.presented_owner_evidence == presented


def test_a_certificate_at_that_level_states_the_environment_certified_class():
    claim = certificate()

    outcome = record(environment_certificate=claim, owner_presented=owner_evidence())

    assert outcome.assurance is AssuranceLevel.ENVIRONMENT_CERTIFIED
    assert outcome.presented_certificate == claim


@pytest.mark.parametrize("level", (AssuranceLevel.DECLARED, AssuranceLevel.OWNER_PRESENTED))
def test_a_certificate_below_that_level_states_neither_higher_class_and_is_still_carried(level):
    claim = certificate(level=level)

    outcome = record(environment_certificate=claim)

    assert outcome.assurance is AssuranceLevel.DECLARED
    assert outcome.presented_certificate == claim


@pytest.mark.parametrize(
    "presented",
    (
        {"owner_presented": owner_evidence(ANOTHER)},
        {"environment_certificate": certificate(ANOTHER)},
    ),
    ids=["owner evidence", "certificate"],
)
def test_material_presented_for_another_identity_is_refused_as_inconsistent(presented):
    assert refusal(**presented) is RemediationRefusalReason.INCONSISTENT_ASSURANCE


def test_the_assurance_class_lives_on_the_outcome_and_not_on_the_domain_record():
    outcome = record(environment_certificate=certificate())

    assert "assurance" not in DOMAIN_FIELD_INVENTORY["RemediationDecision"]
    assert [field.name for field in fields(RemediationDecision)] == list(
        DOMAIN_FIELD_INVENTORY["RemediationDecision"]
    )
    assert "assurance" in {field.name for field in fields(RemediationOutcome)}
    assert isinstance(outcome.assurance, AssuranceLevel)


# --- The rerun ---


def test_a_corrected_candidate_reruns_green_over_the_same_case(corrected):
    report = rerun(corrected)

    assert corrected.prior.failed == (DEFECT_CLAUSE,)
    assert report.green
    assert report.corrected == (DEFECT_CLAUSE,)
    assert report.restored_defects == ()
    assert report.regressions == ()
    assert report.unanswered == ()
    assert report.case == corrected.outcome.case
    assert report.work == corrected.outcome.approved_work
    assert set(report.regression_set) == {
        execution.clause_id for execution in corrected.prior.executions
    }
    assert report.contract.status is VerificationStatus.PASS


def test_a_restored_defect_is_reported_red_with_the_clause_identity(corrected):
    report = rerun(corrected, observations=failing_facts(DEFECT_CLAUSE))

    assert not report.green
    assert report.restored_defects == (DEFECT_CLAUSE,)
    assert report.corrected == ()
    assert report.regressions == ()


def test_a_regression_on_a_clause_that_passed_before_is_reported_red(corrected):
    report = rerun(corrected, observations=failing_facts(REGRESSION_CLAUSE))

    assert not report.green
    assert report.corrected == (DEFECT_CLAUSE,)
    assert report.regressions == (REGRESSION_CLAUSE,)
    assert report.restored_defects == ()


def test_a_clause_the_rerun_cannot_answer_is_not_read_as_corrected(corrected):
    report = rerun(corrected, observations=contract_fixture.observations_without(DEFECT_CLAUSE))

    assert not report.green
    assert report.unanswered == (DEFECT_CLAUSE,)
    assert report.corrected == ()


def test_the_rerun_reports_and_accepts_nothing(corrected):
    report = rerun(corrected)

    assert "accept" not in {field.name for field in fields(type(report))}
    assert not [name for name in dir(report) if "accept" in name]
    assert corrected.outcome.decision.disposition is RemediationDisposition.ACCEPTED
    assert corrected.outcome.fault_open is False


@pytest.mark.parametrize(
    "changes, reason",
    (
        ({"case": None}, RemediationRefusalReason.CASE_MISMATCH),
        ({"prior": None}, RemediationRefusalReason.CASE_MISMATCH),
    ),
    ids=["no case", "no prior outcome"],
)
def test_a_rerun_without_the_case_and_the_prior_outcome_in_hand_is_refused(corrected, changes, reason):
    assert rerun_refusal(corrected, **changes) is reason


def test_a_rerun_over_a_case_the_decision_does_not_cite_is_refused(corrected):
    elsewhere = record(case=replace(case_identity(corrected.prepared.case), version="v2"))

    assert rerun_refusal(corrected, outcome=elsewhere) is RemediationRefusalReason.CASE_MISMATCH


def test_a_prior_outcome_for_another_case_is_refused(corrected):
    borrowed = replace(corrected.prior, case=replace(corrected.prior.case, digest="blake2b-256:0"))

    assert rerun_refusal(corrected, prior=borrowed) is RemediationRefusalReason.CASE_MISMATCH


def test_a_prior_outcome_with_no_defect_leaves_a_rerun_nothing_to_correct(corrected):
    unbroken = corrected.prepared.execute()

    assert unbroken.failed == ()
    assert rerun_refusal(corrected, prior=unbroken) is RemediationRefusalReason.NO_PRIOR_DEFECT


@pytest.mark.parametrize(
    "taken", (RemediationDisposition.REJECTED, RemediationDisposition.REQUEST_MORE_EVIDENCE)
)
def test_a_rerun_runs_for_no_disposition_that_approved_nothing(corrected, taken):
    unapproved = record(taken, case=case_identity(corrected.prepared.case))

    assert unapproved.decision.disposition not in APPROVING_DISPOSITIONS
    assert rerun_refusal(corrected, outcome=unapproved) is RemediationRefusalReason.UNAPPROVED_REMEDY


def test_an_outcome_no_workflow_recorded_is_refused(corrected):
    assert rerun_refusal(corrected, outcome=advice()) is RemediationRefusalReason.UNDECLARED_OUTCOME


def test_every_exported_name_of_this_workflow_resolves_under_a_star_import():
    declared = list(workflow.__all__)
    imported: dict[str, object] = {}

    exec("from evorthon_data.verification.workflows.remediation import *", imported)

    assert declared == sorted(declared)
    assert len(declared) == len(set(declared))
    assert [name for name in declared if not hasattr(workflow, name)] == []
    assert [name for name in declared if name not in imported] == []
