# evorthon-verifies: EVD-README-038
# evorthon-verifies: EVD-README-030
# evorthon-verifies: EVD-README-023
# evorthon-verifies: EVD-README-018
# evorthon-verifies: EVD-README-013
# evorthon-verifies: EVD-README-005
from dataclasses import asdict

import pytest

from evorthon_data.engagement import (
    Actor,
    ActorKind,
    DecisionKind,
    DecisionOutcome,
    DiscoveryKind,
    Engagement,
    EngagementError,
    EngagementMode,
    ImmutableReference,
    LifecyclePhase,
    NamedHumanDecision,
    RecordRevision,
    RecordReview,
    ReferenceKind,
    ReviewDisposition,
    StageRecord,
    validate_template_projection,
)
from evorthon_data.engagement import aggregate
from evorthon_data.engagement import stages as compatibility


def actor(identity: str, kind: ActorKind = ActorKind.HUMAN) -> Actor:
    return Actor(identity=identity, kind=kind)


def reference(kind: ReferenceKind, identifier: str) -> ImmutableReference:
    return ImmutableReference(kind=kind, identifier=identifier, version="v1", digest=f"digest-{identifier}")


def approval(subject: ImmutableReference, decision_id: str, approver: Actor | None = None) -> NamedHumanDecision:
    return NamedHumanDecision(
        decision_id=decision_id,
        kind=DecisionKind.RECORD_APPROVAL,
        outcome=DecisionOutcome.APPROVED,
        subject=subject,
        decided_by=approver or actor("delivery-authority"),
        rationale=reference(ReferenceKind.DECISION_RATIONALE, f"rationale-{decision_id}"),
    )


def submit_review_approve(engagement: Engagement, *, identifier: str) -> Engagement:
    discovery_kind = None
    if engagement.phase is LifecyclePhase.DISCOVERY:
        discovery_kind = (
            DiscoveryKind.ESTATE if engagement.mode is EngagementMode.MODERNISATION else DiscoveryKind.CAPABILITY
        )
    record = StageRecord(
        phase=engagement.phase,
        document=reference(ReferenceKind.STAGE_RECORD, identifier),
        authored_by=actor(f"generator-{identifier}", ActorKind.MODEL),
        discovery_kind=discovery_kind,
    )
    engagement = engagement.submit(record)
    engagement = engagement.review(
        RecordReview(
            subject=record.document,
            reviewer=actor(f"reviewer-{identifier}", ActorKind.MODEL),
            disposition=ReviewDisposition.APPROVED,
            findings=reference(ReferenceKind.REVIEW_FINDINGS, f"findings-{identifier}"),
        )
    )
    engagement = engagement.approve(approval(record.document, f"approve-{identifier}"))
    return engagement.advance()


@pytest.mark.parametrize("mode", [EngagementMode.MODERNISATION, EngagementMode.GREENFIELD])
def test_both_modes_cover_the_complete_governed_lifecycle(mode):
    engagement = Engagement.create(f"eng-{mode.value}", mode)
    for phase in (
        LifecyclePhase.SETUP,
        LifecyclePhase.FRAMING,
        LifecyclePhase.DISCOVERY,
        LifecyclePhase.DESIGN,
        LifecyclePhase.DELIVERY_CONTRACT,
    ):
        assert engagement.phase is phase
        engagement = submit_review_approve(engagement, identifier=phase.value)

    assert engagement.phase is LifecyclePhase.DELIVERY
    engagement = engagement.add_approved_work(reference(ReferenceKind.APPROVED_WORK, "work-1"))
    engagement = engagement.add_build_evidence(reference(ReferenceKind.BUILD_EVIDENCE, "build-1"))
    result = reference(ReferenceKind.VERIFICATION_RESULT, "verification-1")
    engagement = engagement.add_verification_result(result)
    engagement = engagement.advance()
    assert engagement.phase is LifecyclePhase.VERIFIED

    engagement = engagement.accept(
        NamedHumanDecision(
            decision_id="accept-1",
            kind=DecisionKind.ENGAGEMENT_ACCEPTANCE,
            outcome=DecisionOutcome.ACCEPTED,
            subject=result,
            decided_by=actor("acceptance-authority"),
            rationale=reference(ReferenceKind.DECISION_RATIONALE, "rationale-accept-1"),
        )
    ).advance()

    assert engagement.phase is LifecyclePhase.ACCEPTED
    assert engagement.schema_version == "evorthon.engagement.v1"
    assert engagement.revision > 1


def test_greenfield_refuses_a_fictional_current_estate():
    engagement = Engagement.create("eng-greenfield", EngagementMode.GREENFIELD)
    engagement = submit_review_approve(engagement, identifier="setup")
    engagement = submit_review_approve(engagement, identifier="framing")

    with pytest.raises(EngagementError, match="fictional estate"):
        engagement.submit(
            StageRecord(
                phase=LifecyclePhase.DISCOVERY,
                document=reference(ReferenceKind.STAGE_RECORD, "estate-map"),
                authored_by=actor("generator", ActorKind.MODEL),
                discovery_kind=DiscoveryKind.ESTATE,
            )
        )


def test_skipped_review_or_human_approval_cannot_advance():
    engagement = Engagement.create("eng-negative", EngagementMode.MODERNISATION)
    with pytest.raises(EngagementError, match="no submitted"):
        engagement.advance()

    record = StageRecord(
        phase=LifecyclePhase.SETUP,
        document=reference(ReferenceKind.STAGE_RECORD, "setup"),
        authored_by=actor("generator", ActorKind.MODEL),
    )
    engagement = engagement.submit(record)
    with pytest.raises(EngagementError, match="independent review"):
        engagement.advance()

    engagement = engagement.review(
        RecordReview(
            subject=record.document,
            reviewer=actor("reviewer", ActorKind.MODEL),
            disposition=ReviewDisposition.APPROVED,
            findings=reference(ReferenceKind.REVIEW_FINDINGS, "findings-setup"),
        )
    )
    with pytest.raises(EngagementError, match="named human approval"):
        engagement.advance()

    with pytest.raises(EngagementError, match="approved independent review"):
        Engagement(
            engagement_id="fabricated-framing",
            mode=EngagementMode.MODERNISATION,
            phase=LifecyclePhase.FRAMING,
            records=(record,),
        )


def test_model_self_acceptance_and_self_review_are_refused():
    record = reference(ReferenceKind.STAGE_RECORD, "setup")
    with pytest.raises(EngagementError, match="named human"):
        NamedHumanDecision(
            decision_id="model-approval",
            kind=DecisionKind.RECORD_APPROVAL,
            outcome=DecisionOutcome.APPROVED,
            subject=record,
            decided_by=actor("generator", ActorKind.MODEL),
            rationale=reference(ReferenceKind.DECISION_RATIONALE, "model-rationale"),
        )

    engagement = Engagement.create("eng-self-review", EngagementMode.MODERNISATION).submit(
        StageRecord(phase=LifecyclePhase.SETUP, document=record, authored_by=actor("generator", ActorKind.MODEL))
    )
    with pytest.raises(EngagementError, match="cannot review their own"):
        engagement.review(
            RecordReview(
                subject=record,
                reviewer=actor("generator", ActorKind.MODEL),
                disposition=ReviewDisposition.APPROVED,
                findings=reference(ReferenceKind.REVIEW_FINDINGS, "self-findings"),
            )
        )


def test_rehydrated_revision_history_refuses_self_review_and_rewritten_authorship():
    superseded = StageRecord(
        phase=LifecyclePhase.SETUP,
        document=reference(ReferenceKind.STAGE_RECORD, "draft-1"),
        authored_by=actor("generator", ActorKind.MODEL),
    )
    self_review = RecordReview(
        subject=superseded.document,
        reviewer=superseded.authored_by,
        disposition=ReviewDisposition.CHANGES_REQUESTED,
        findings=reference(ReferenceKind.REVIEW_FINDINGS, "self-review-findings"),
    )
    replacement_reference = reference(ReferenceKind.STAGE_RECORD, "draft-2")
    replacement = StageRecord(
        phase=LifecyclePhase.SETUP,
        document=replacement_reference,
        authored_by=actor("generator", ActorKind.MODEL),
    )

    with pytest.raises(EngagementError, match="cannot review their own"):
        RecordRevision(superseded=superseded, review=self_review, replacement=replacement)

    valid_review = RecordReview(
        subject=superseded.document,
        reviewer=actor("reviewer", ActorKind.MODEL),
        disposition=ReviewDisposition.CHANGES_REQUESTED,
        findings=reference(ReferenceKind.REVIEW_FINDINGS, "valid-findings"),
    )
    revision = RecordRevision(superseded=superseded, review=valid_review, replacement=replacement)
    rewritten_active = StageRecord(
        phase=LifecyclePhase.SETUP,
        document=replacement_reference,
        authored_by=actor("rewritten-author", ActorKind.MODEL),
    )

    with pytest.raises(EngagementError, match="end of its revision chain"):
        Engagement(
            engagement_id="forged-rehydration",
            mode=EngagementMode.MODERNISATION,
            records=(rewritten_active,),
            record_revisions=(revision,),
        )


def test_external_work_build_and_verification_state_are_identity_references_only():
    engagement = Engagement.create("eng-identity", EngagementMode.MODERNISATION)
    for phase in (
        LifecyclePhase.SETUP,
        LifecyclePhase.FRAMING,
        LifecyclePhase.DISCOVERY,
        LifecyclePhase.DESIGN,
        LifecyclePhase.DELIVERY_CONTRACT,
    ):
        assert engagement.phase is phase
        engagement = submit_review_approve(engagement, identifier=phase.value)
    engagement = engagement.add_approved_work(reference(ReferenceKind.APPROVED_WORK, "work"))
    engagement = engagement.add_build_evidence(reference(ReferenceKind.BUILD_EVIDENCE, "build"))
    engagement = engagement.add_verification_result(reference(ReferenceKind.VERIFICATION_RESULT, "result"))

    payload = asdict(engagement)
    assert set(payload) >= {"approved_work", "build_evidence", "verification_results"}
    assert not {"ready", "claimed", "completed", "case_payload", "result_payload"} & set(payload)
    assert payload["verification_results"] == (
        {"kind": ReferenceKind.VERIFICATION_RESULT, "identifier": "result", "version": "v1", "digest": "digest-result"},
    )


def test_schema_projections_and_compatibility_facades_share_the_aggregate_owner(tmp_path):
    assert compatibility.STAGE_FIELDS is aggregate.STAGE_FIELDS
    assert compatibility.validate_stage is aggregate.validate_stage
    template = tmp_path / "instance-context.md"
    template.write_text("- **Status:**\n", encoding="utf-8")
    assert validate_template_projection(template) == [
        "users",
        "platform boundary",
        "authorities",
        "constraints",
        "evidence identifiers",
        "open decisions",
    ]
