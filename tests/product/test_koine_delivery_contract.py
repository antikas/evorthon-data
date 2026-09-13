# evorthon-verifies: EVD-README-041
# evorthon-verifies: EVD-README-006
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

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
    ExpectedCheckResult,
    ImmutableReference,
    LifecyclePhase,
    NamedHumanDecision,
    ReferenceKind,
    ReviewDisposition,
    render_record_projection,
)
from evorthon_data.koine_session import (
    ApprovedInput,
    CapabilityDiscovery,
    CheckFamily,
    CheckpointExpectation,
    DeliveryContract,
    DeliveryGate,
    DeliveryWorkPackage,
    EstateDiscovery,
    GeneratedRecordProposal,
    KoineSession,
    KoineSessionError,
    OutcomeFraming,
    RecordFacts,
    ReviewProposal,
    SessionAuthorities,
    SessionModelRoute,
    SessionModelRoutes,
    SuccessCriterion,
    SetupBrief,
    TargetDesign,
    VerificationCaseIntent,
    VerificationPlanning,
    record_digest,
)
from evorthon_data.security import ModelCall, ModelDestination, ModelEgressGateway, ModelEgressMode


NOW = datetime(2026, 9, 2, 12, tzinfo=timezone.utc)
DESTINATION = ModelDestination("provider-neutral", "https://model.example.test/v1/respond", "reviewable-model")


def actor(identity: str, kind: ActorKind) -> Actor:
    return Actor(identity=identity, kind=kind)


def reference(kind: ReferenceKind, identifier: str) -> ImmutableReference:
    return ImmutableReference(kind=kind, identifier=identifier, version="v1", digest=f"digest-{identifier}")


def evidence(inputs) -> tuple[str, ...]:
    return tuple(f"{identifier}@{version}#{digest}" for identifier, version, digest in inputs)


class DeliveryTransport:
    def __init__(self, fact_mutator=None) -> None:
        self.calls: list[ModelCall] = []
        self.count = 0
        self.fact_mutator = fact_mutator

    def __call__(self, call: ModelCall):
        self.calls.append(call)
        self.count += 1
        if call.purpose.value == "reviewer":
            return ReviewProposal(
                disposition=ReviewDisposition.APPROVED,
                findings=reference(ReferenceKind.REVIEW_FINDINGS, f"findings-{self.count}"),
            )
        facts = generated_facts(call)
        if self.fact_mutator is not None:
            facts = self.fact_mutator(call, facts)
        content = render_record_projection(facts.as_mapping())
        inputs = tuple(ApprovedInput(*item) for item in call.fields["approved_inputs"])
        return GeneratedRecordProposal(
            document=ImmutableReference(
                kind=ReferenceKind.STAGE_RECORD,
                identifier=f"record-{self.count}",
                version="v1",
                digest=record_digest(content, facts, inputs),
            ),
            content=content,
            facts=facts,
        )


def generated_facts(call: ModelCall) -> RecordFacts:
    if call.route == "koine.generate.setup":
        return RecordFacts(
            (
                ("status", "draft for independent review"),
                ("users", (call.fields["owner"],)),
                ("platform boundary", call.fields["platform_boundary"]),
                ("authorities", (call.fields["owner"], call.fields["evidence_authority"], call.fields["acceptance_authority"])),
                ("constraints", call.fields["constraints"]),
                ("evidence identifiers", evidence(call.fields["approved_inputs"])),
                ("open decisions", "none declared"),
            )
        )
    verification = (
        ("verification case intent", call.fields["verification case intent"]),
        ("check families", call.fields["check families"]),
        ("lineage/checkpoint expectations", call.fields["lineage/checkpoint expectations"]),
        ("acceptance rules", call.fields["acceptance rules"]),
    )
    if call.route == "koine.generate.outcome":
        return RecordFacts(
            (
                ("consumer outcome", call.fields["consumer_outcome"]),
                ("success signals", call.fields["success_signals"]),
                ("success criteria", call.fields["success_criteria"]),
                ("scope", call.fields["scope"]),
                ("authorities", (call.fields["owner"], call.fields["evidence_authority"], call.fields["acceptance_authority"])),
                ("evidence", evidence(call.fields["approved_inputs"])),
                ("constraints", "none declared"),
                ("open questions", "none declared"),
                *verification,
            )
        )
    if call.route == "koine.generate.estate-discovery":
        return RecordFacts(
            (
                ("processing", call.fields["processing"]),
                ("data", call.fields["data"]),
                ("interfaces", call.fields["interfaces"]),
                ("controls", call.fields["controls"]),
                ("continuity needs", call.fields["continuity_needs"]),
                ("accidental legacy behaviour", call.fields["accidental_legacy_behaviour"]),
                ("evidence", evidence(call.fields["approved_inputs"])),
                ("uncertainty", call.fields["uncertainty"]),
                *verification,
            )
        )
    if call.route == "koine.generate.capability-discovery":
        return RecordFacts(
            (
                ("required capabilities", call.fields["required_capabilities"]),
                ("constraints", call.fields["constraints"]),
                ("evidence", evidence(call.fields["approved_inputs"])),
                ("uncertainty", call.fields["uncertainty"]),
                *verification,
            )
        )
    if call.route == "koine.generate.design":
        return RecordFacts(
            (
                ("architecture", call.fields["architecture"]),
                ("operating model", call.fields["operating_model"]),
                ("contracts", call.fields["contracts"]),
                ("transition", call.fields["transition"]),
                ("increments", call.fields["increments"]),
                ("risks", call.fields["risks"]),
                ("acceptance signals", call.fields["acceptance_signals"]),
                ("evidence", evidence(call.fields["approved_inputs"])),
                *verification,
            )
        )
    if call.route == "koine.generate.delivery-contract":
        return RecordFacts(
            (
                ("package inventory", call.fields["package_inventory"]),
                ("dependency inventory", call.fields["dependency_inventory"]),
                ("gate inventory", call.fields["gate_inventory"]),
                ("exclusions", call.fields["exclusions"]),
                ("acceptance", call.fields["acceptance"]),
                ("evidence", evidence(call.fields["approved_inputs"])),
                *verification,
            )
        )
    raise AssertionError(f"unexpected generator route: {call.route}")


def planning(mode: EngagementMode) -> VerificationPlanning:
    if mode is EngagementMode.MODERNISATION:
        return VerificationPlanning(
            case_intent=VerificationCaseIntent.SNAPSHOT_PARITY,
            check_families=(CheckFamily.PARITY, CheckFamily.DELIVERY_INTEGRITY),
            checkpoint_expectations=(CheckpointExpectation("published-report", "data-owner"),),
            acceptance_rules=("two accepted synthetic publications",),
        )
    return VerificationPlanning(
        case_intent=VerificationCaseIntent.CONTRACT_CONFORMANCE,
        check_families=(CheckFamily.CONFORMANCE, CheckFamily.INVARIANT),
        checkpoint_expectations=(CheckpointExpectation("consumer-view", "platform-owner"),),
        acceptance_rules=("approved golden scenarios and invariants pass",),
    )


def framing(mode: EngagementMode) -> OutcomeFraming:
    verification = planning(mode)
    signal = "published report reconciles" if mode is EngagementMode.MODERNISATION else "approved golden scenarios pass"
    family = CheckFamily.PARITY if mode is EngagementMode.MODERNISATION else CheckFamily.CONFORMANCE
    validator = reference(ReferenceKind.VALIDATOR_SPECIFICATION, "success-signal-validator")
    success_evidence = ApprovedInput("success-signal-evidence", "v1", "digest-success-signal-evidence")
    return OutcomeFraming(
        consumer_outcome="a trusted consumer view is available on time",
        success_signals=(signal,),
        scope="synthetic data platform delivery",
        approved_inputs=(
            ApprovedInput("outcome-decision", "v1", "digest-outcome-decision"),
            ApprovedInput.from_reference(validator),
            success_evidence,
        ),
        verification=verification,
        success_criteria=(
            SuccessCriterion(
                signal,
                family,
                validator,
                (success_evidence,),
                ExpectedCheckResult.PASS,
                verification.acceptance_rules[0],
            ),
        ),
    )


def session(mode: EngagementMode, transport: DeliveryTransport) -> KoineSession:
    route = SessionModelRoute(
        destination=DESTINATION,
        mode=ModelEgressMode.FAKE,
        data_class="synthetic-delivery-record",
        retention_policy="no-provider-retention",
        evidence_policy="record-call-identity-only",
    )
    gateway = ModelEgressGateway(local_transport=transport, fake_transport=transport, clock=lambda: NOW)
    return KoineSession.cold_start(
        session_id=f"session-{mode.value}",
        engagement=Engagement.create(f"engagement-{mode.value}", mode),
        authorities=SessionAuthorities(
            owner=actor("outcome-owner", ActorKind.HUMAN),
            evidence_authority=actor("evidence-owner", ActorKind.HUMAN),
            acceptance_authority=actor("acceptance-authority", ActorKind.HUMAN),
        ),
        generator=actor("generator-model", ActorKind.MODEL),
        reviewer=actor("reviewer-model", ActorKind.MODEL),
        routes=SessionModelRoutes(generator=route, reviewer=route),
        egress=gateway,
    )


def approve_current(running: KoineSession) -> KoineSession:
    record = running.engagement.current_record
    assert record is not None
    decision = NamedHumanDecision(
        decision_id=f"approve-{record.phase.value}-{record.document.identifier}",
        kind=DecisionKind.RECORD_APPROVAL,
        outcome=DecisionOutcome.APPROVED,
        subject=record.document,
        decided_by=actor("acceptance-authority", ActorKind.HUMAN),
        rationale=reference(ReferenceKind.DECISION_RATIONALE, f"rationale-{record.document.identifier}"),
    )
    return running.review_current().adjudicate_current(decision).advance()


def setup_and_frame(running: KoineSession, mode: EngagementMode) -> KoineSession:
    running = running.generate_setup(
        SetupBrief(
            platform_boundary="synthetic data platform",
            constraints=("synthetic-only",),
            approved_inputs=(ApprovedInput("setup-decision", "v1", "digest-setup-decision"),),
        )
    )
    running = approve_current(running)
    return approve_current(running.generate_outcome_brief(framing(mode)))


def estate_discovery() -> EstateDiscovery:
    return EstateDiscovery(
        processing=("scheduled extracts",),
        data=("case, interaction and workforce populations",),
        interfaces=("source extracts and consumer report",),
        controls=("reconciliation before publication",),
        continuity_needs=("retain business-day cut-off",),
        accidental_legacy_behaviour=("manual reconciliation",),
        uncertainty=("source ownership needs confirmation",),
        approved_inputs=(ApprovedInput("estate-evidence", "v1", "digest-estate-evidence"),),
    )


def capability_discovery() -> CapabilityDiscovery:
    return CapabilityDiscovery(
        required_capabilities=("contract-valid asset observations",),
        constraints=("synthetic-only",),
        uncertainty=("consumer timing threshold needs approval",),
        approved_inputs=(ApprovedInput("capability-evidence", "v1", "digest-capability-evidence"),),
    )


def target_design() -> TargetDesign:
    return TargetDesign(
        architecture="contract-defined ingestion and consumer measures",
        operating_model=("platform owner triages exceptions",),
        contracts=("source identity and timing",),
        transition=("accept each increment before retirement",),
        increments=("source contracts", "quality controls", "consumer view"),
        risks=("unreconciled publication blocks release",),
        acceptance_signals=("named acceptance after checks",),
        approved_inputs=(ApprovedInput("design-decision", "v1", "digest-design-decision"),),
    )


def delivery_contract() -> DeliveryContract:
    return DeliveryContract(
        work_packages=(
            DeliveryWorkPackage(
                identifier="source-contracts",
                summary="approve source identities and contracts",
                owner="evidence-owner",
                validator="source-contract-validator",
                gates=(DeliveryGate("source-contracts-reviewed", "source owner review is approved"),),
                depends_on=(),
            ),
            DeliveryWorkPackage(
                identifier="quality-controls",
                summary="implement declared quality controls",
                owner="evidence-owner",
                validator="quality-control-validator",
                gates=(DeliveryGate("quality-controls-reviewed", "control review is approved"),),
                depends_on=("source-contracts",),
            ),
            DeliveryWorkPackage(
                identifier="consumer-view",
                summary="deliver the approved consumer view",
                owner="acceptance-authority",
                validator="consumer-view-validator",
                gates=(DeliveryGate("consumer-view-accepted", "named human acceptance is recorded"),),
                depends_on=("quality-controls",),
            ),
        ),
        exclusions=("production connections",),
        acceptance=("named authority accepts only after declared checks",),
        approved_inputs=(ApprovedInput("contract-decision", "v1", "digest-contract-decision"),),
    )


def edge_free_delivery_contracts() -> tuple[DeliveryContract, ...]:
    contract = delivery_contract()
    return (
        replace(contract, work_packages=contract.work_packages[:1]),
        replace(contract, work_packages=tuple(replace(package, depends_on=()) for package in contract.work_packages)),
    )


@pytest.mark.parametrize("mode", [EngagementMode.MODERNISATION, EngagementMode.GREENFIELD])
def test_both_modes_reach_independently_reviewed_versioned_delivery_contracts(mode):
    transport = DeliveryTransport()
    running = setup_and_frame(session(mode, transport), mode)

    if mode is EngagementMode.MODERNISATION:
        running = approve_current(running.generate_estate_discovery(estate_discovery()))
        discovery = running.generated_records[-1]
        assert discovery.record.discovery_kind is DiscoveryKind.ESTATE
        assert discovery.facts.as_mapping()["continuity needs"] == estate_discovery().continuity_needs
        assert discovery.facts.as_mapping()["accidental legacy behaviour"] == estate_discovery().accidental_legacy_behaviour
    else:
        running = approve_current(running.generate_capability_discovery(capability_discovery()))
        discovery = running.generated_records[-1]
        assert discovery.record.discovery_kind is DiscoveryKind.CAPABILITY
        assert "parity" not in " ".join(discovery.facts.as_mapping()["check families"])

    running = approve_current(running.generate_target_design(target_design()))
    running = running.generate_delivery_contract(delivery_contract())
    contract = running.engagement.current_record
    assert contract is not None
    running = running.review_current().adjudicate_current(
        NamedHumanDecision(
            decision_id=f"approve-contract-{mode.value}",
            kind=DecisionKind.RECORD_APPROVAL,
            outcome=DecisionOutcome.APPROVED,
            subject=contract.document,
            decided_by=actor("acceptance-authority", ActorKind.HUMAN),
            rationale=reference(ReferenceKind.DECISION_RATIONALE, f"contract-rationale-{mode.value}"),
        )
    )

    approved = running.approved_delivery_contract
    assert approved.record.phase is LifecyclePhase.DELIVERY_CONTRACT
    assert approved.record.document.identifier == contract.document.identifier
    graph = running.approved_delivery_graph
    assert graph == delivery_contract()
    assert graph.dependency_inventory == (
        '{"blocked":"quality-controls","requires":"source-contracts"}',
        '{"blocked":"consumer-view","requires":"quality-controls"}',
    )
    assert graph.gate_inventory == (
        '{"identifier":"source-contracts-reviewed","package":"source-contracts","requirement":"source owner review is approved"}',
        '{"identifier":"quality-controls-reviewed","package":"quality-controls","requirement":"control review is approved"}',
        '{"identifier":"consumer-view-accepted","package":"consumer-view","requirement":"named human acceptance is recorded"}',
    )
    assert approved.facts.as_mapping()["lineage/checkpoint expectations"] == planning(mode).checkpoint_inventory
    assert [call.purpose.value for call in transport.calls] == [
        "generator", "reviewer", "generator", "reviewer", "generator", "reviewer", "generator", "reviewer", "generator", "reviewer"
    ]


@pytest.mark.parametrize(
    ("changes", "bound_field"),
    (
        ({"exclusions": ("rewritten exclusion",)}, "exclusions"),
        ({"acceptance": ("rewritten acceptance rule",)}, "acceptance"),
        (
            {"approved_inputs": (ApprovedInput("rewritten-contract", "v2", "digest-rewritten-contract"),)},
            "approved inputs",
        ),
    ),
)
def test_rehydration_cannot_replace_any_unreviewed_delivery_contract_terms(changes, bound_field):
    transport = DeliveryTransport()
    running = setup_and_frame(
        session(EngagementMode.MODERNISATION, transport),
        EngagementMode.MODERNISATION,
    )
    running = approve_current(running.generate_estate_discovery(estate_discovery()))
    running = approve_current(running.generate_target_design(target_design()))
    running = running.generate_delivery_contract(delivery_contract())
    record = running.engagement.current_record
    assert record is not None
    running = running.review_current().adjudicate_current(
        NamedHumanDecision(
            decision_id=f"approve-contract-{bound_field.replace(' ', '-')}",
            kind=DecisionKind.RECORD_APPROVAL,
            outcome=DecisionOutcome.APPROVED,
            subject=record.document,
            decided_by=actor("acceptance-authority", ActorKind.HUMAN),
            rationale=reference(ReferenceKind.DECISION_RATIONALE, f"contract-{bound_field.replace(' ', '-')}"),
        )
    )

    rewritten = replace(delivery_contract(), **changes)
    with pytest.raises(KoineSessionError, match=rf"does not bind the {bound_field}"):
        replace(running, delivery_contract=rewritten)


@pytest.mark.parametrize("contract", edge_free_delivery_contracts(), ids=("single-package", "independent-packages"))
def test_edge_free_delivery_contracts_can_be_generated_reviewed_and_approved(contract):
    transport = DeliveryTransport()
    running = setup_and_frame(session(EngagementMode.MODERNISATION, transport), EngagementMode.MODERNISATION)
    running = approve_current(running.generate_estate_discovery(estate_discovery()))
    running = approve_current(running.generate_target_design(target_design()))

    running = running.generate_delivery_contract(contract)
    assert running.generated_records[-1].facts.as_mapping()["dependency inventory"] == ()

    record = running.engagement.current_record
    assert record is not None
    running = running.review_current().adjudicate_current(
        NamedHumanDecision(
            decision_id=f"approve-edge-free-contract-{record.document.identifier}",
            kind=DecisionKind.RECORD_APPROVAL,
            outcome=DecisionOutcome.APPROVED,
            subject=record.document,
            decided_by=actor("acceptance-authority", ActorKind.HUMAN),
            rationale=reference(ReferenceKind.DECISION_RATIONALE, f"rationale-{record.document.identifier}"),
        )
    )
    assert running.approved_delivery_graph == contract
    assert running.approved_delivery_contract.facts.as_mapping()["dependency inventory"] == ()


def test_record_facts_continue_to_reject_empty_non_dependency_inventories():
    with pytest.raises(KoineSessionError, match="record fact acceptance must contain at least one value"):
        RecordFacts((("acceptance", ()),))


def test_discovery_rejects_invented_evidence_after_egress_before_it_can_enter_the_contract():
    def invent_evidence(call: ModelCall, facts: RecordFacts) -> RecordFacts:
        if call.route != "koine.generate.estate-discovery":
            return facts
        return RecordFacts(
            tuple((field, ("invented-evidence@v1#digest-invented",) if field == "evidence" else value) for field, value in facts.entries)
        )

    transport = DeliveryTransport(fact_mutator=invent_evidence)
    running = setup_and_frame(session(EngagementMode.MODERNISATION, transport), EngagementMode.MODERNISATION)

    with pytest.raises(KoineSessionError, match="evidence.*approved framing"):
        running.generate_estate_discovery(estate_discovery())

    assert running.engagement.current_record is None


def test_delivery_contract_requires_canonical_package_owners_validators_and_gates():
    with pytest.raises(KoineSessionError, match="DeliveryWorkPackage"):
        DeliveryContract(
            work_packages=("source contracts",),
            exclusions=("production connections",),
            acceptance=("named authority accepts after checks",),
            approved_inputs=(ApprovedInput("contract", "v1", "digest-contract"),),
        )
    with pytest.raises(KoineSessionError, match="delivery package owner"):
        DeliveryWorkPackage(
            identifier="source-contracts",
            summary="approve source identities",
            owner="",
            validator="source-contract-validator",
            gates=(DeliveryGate("source-contracts-reviewed", "source owner review is approved"),),
            depends_on=(),
        )
    with pytest.raises(KoineSessionError, match="canonical lower-kebab identifier"):
        DeliveryWorkPackage(
            identifier="source-contracts",
            summary="approve source identities",
            owner="evidence owner",
            validator="source-contract-validator",
            gates=(DeliveryGate("source-contracts-reviewed", "source owner review is approved"),),
            depends_on=(),
        )
    with pytest.raises(KoineSessionError, match="delivery package validator"):
        DeliveryWorkPackage(
            identifier="source-contracts",
            summary="approve source identities",
            owner="evidence-owner",
            validator="",
            gates=(DeliveryGate("source-contracts-reviewed", "source owner review is approved"),),
            depends_on=(),
        )
    with pytest.raises(KoineSessionError, match="at least one gate"):
        DeliveryWorkPackage(
            identifier="source-contracts",
            summary="approve source identities",
            owner="evidence-owner",
            validator="source-contract-validator",
            gates=(),
            depends_on=(),
        )
    source = DeliveryWorkPackage(
        identifier="source-contracts",
        summary="approve source identities",
        owner="evidence-owner",
        validator="source-contract-validator",
        gates=(DeliveryGate("source-contracts-reviewed", "source owner review is approved"),),
        depends_on=("missing-package",),
    )
    with pytest.raises(KoineSessionError, match="unknown package"):
        DeliveryContract(
            work_packages=(source,),
            exclusions=("production connections",),
            acceptance=("named authority accepts after checks",),
            approved_inputs=(ApprovedInput("contract", "v1", "digest-contract"),),
        )


def test_delivery_contract_rejects_an_egress_response_that_changes_the_typed_gate_inventory():
    def change_gate_inventory(call: ModelCall, facts: RecordFacts) -> RecordFacts:
        if call.route != "koine.generate.delivery-contract":
            return facts
        return RecordFacts(
            tuple(
                (field, ('{"identifier":"invented","package":"consumer-view","requirement":"invented"}',))
                if field == "gate inventory"
                else (field, value)
                for field, value in facts.entries
            )
        )

    transport = DeliveryTransport(fact_mutator=change_gate_inventory)
    running = setup_and_frame(session(EngagementMode.MODERNISATION, transport), EngagementMode.MODERNISATION)
    running = approve_current(running.generate_estate_discovery(estate_discovery()))
    running = approve_current(running.generate_target_design(target_design()))

    with pytest.raises(KoineSessionError, match="gate inventory.*approved framing"):
        running.generate_delivery_contract(delivery_contract())


def test_placeholder_checkpoint_owner_and_unverifiable_success_are_refused_before_generation():
    for placeholder in ("tbd", "pending", "to-be-determined", "forthcoming"):
        with pytest.raises(KoineSessionError, match="checkpoint owner.*placeholder"):
            CheckpointExpectation("published-report", placeholder)

    invalid_inputs = (
        lambda: ApprovedInput("pending", "v1", "digest-evidence"),
        lambda: ApprovedInput("evidence", "forthcoming", "digest-evidence"),
        lambda: ApprovedInput("evidence", "v1", "to-be-determined"),
    )
    for construct in invalid_inputs:
        with pytest.raises(KoineSessionError, match="input .* must not be a placeholder"):
            construct()

    with pytest.raises(KoineSessionError, match="success criterion validator.*placeholder"):
        SuccessCriterion(
            "published report reconciles",
            CheckFamily.PARITY,
            reference(ReferenceKind.VALIDATOR_SPECIFICATION, "tbd"),
            (ApprovedInput("snapshot-evidence", "v1", "digest-snapshot-evidence"),),
            ExpectedCheckResult.PASS,
            "two accepted synthetic publications",
        )

    valid = framing(EngagementMode.MODERNISATION).success_criteria[0]
    placeholder_reference_parts = (
        lambda: replace(valid, validator=replace(valid.validator, version="tbd")),
        lambda: replace(valid, validator=replace(valid.validator, digest="pending")),
        lambda: replace(valid, evidence=(replace(valid.evidence[0], version="to-be-determined"),)),
        lambda: replace(valid, evidence=(replace(valid.evidence[0], digest="forthcoming"),)),
    )
    for construct in placeholder_reference_parts:
        with pytest.raises(KoineSessionError, match="must not be a placeholder"):
            construct()

    with pytest.raises(KoineSessionError, match="approved_inputs must contain at least one input"):
        SuccessCriterion(
            "the platform feels trustworthy",
            CheckFamily.CONFORMANCE,
            reference(ReferenceKind.VALIDATOR_SPECIFICATION, "stakeholder-feeling-validator"),
            (),
            ExpectedCheckResult.PASS,
            "stakeholders feel it is good",
        )

    with pytest.raises(EngagementError, match="actor identity.*placeholder"):
        actor("tbd", ActorKind.HUMAN)

    package = delivery_contract().work_packages[0]
    with pytest.raises(KoineSessionError, match="delivery package owner.*placeholder"):
        replace(package, owner="tbd")
    with pytest.raises(KoineSessionError, match="delivery package validator.*placeholder"):
        replace(package, validator="unknown")

    verification = planning(EngagementMode.GREENFIELD)
    validator = reference(ReferenceKind.VALIDATOR_SPECIFICATION, "unapproved-validator")
    success_evidence = ApprovedInput("unapproved-evidence", "v1", "digest-unapproved-evidence")
    with pytest.raises(KoineSessionError, match="validator and evidence must be approved framing inputs"):
        OutcomeFraming(
            consumer_outcome="a trustworthy view",
            success_signals=("view published",),
            scope="synthetic scope",
            approved_inputs=(ApprovedInput("outcome", "v1", "digest-outcome"),),
            verification=verification,
            success_criteria=(
                SuccessCriterion(
                    "view published",
                    CheckFamily.CONFORMANCE,
                    validator,
                    (success_evidence,),
                    ExpectedCheckResult.PASS,
                    verification.acceptance_rules[0],
                ),
            ),
        )

    with pytest.raises(KoineSessionError, match="every success signal"):
        OutcomeFraming(
            consumer_outcome="a trustworthy view",
            success_signals=("view published",),
            scope="synthetic scope",
            approved_inputs=(ApprovedInput("outcome", "v1", "digest-outcome"),),
            verification=verification,
            success_criteria=(),
        )


def test_greenfield_parity_claim_is_refused_before_any_outcome_egress():
    transport = DeliveryTransport()
    running = session(EngagementMode.GREENFIELD, transport)
    running = approve_current(
        running.generate_setup(
            SetupBrief(
                platform_boundary="synthetic data platform",
                constraints=("synthetic-only",),
                approved_inputs=(ApprovedInput("setup-decision", "v1", "digest-setup-decision"),),
            )
        )
    )
    parity = planning(EngagementMode.MODERNISATION)
    validator = reference(ReferenceKind.VALIDATOR_SPECIFICATION, "snapshot-parity-validator")
    snapshot_evidence = ApprovedInput("snapshot-evidence", "v1", "digest-snapshot-evidence")
    invalid = OutcomeFraming(
        consumer_outcome="a trustworthy view",
        success_signals=("view reconciles",),
        scope="synthetic scope",
        approved_inputs=(
            ApprovedInput("outcome", "v1", "digest-outcome"),
            ApprovedInput.from_reference(validator),
            snapshot_evidence,
        ),
        verification=parity,
        success_criteria=(
            SuccessCriterion(
                "view reconciles",
                CheckFamily.PARITY,
                validator,
                (snapshot_evidence,),
                ExpectedCheckResult.PASS,
                parity.acceptance_rules[0],
            ),
        ),
    )

    with pytest.raises(KoineSessionError, match="cannot claim legacy parity"):
        running.generate_outcome_brief(invalid)

    assert [call.route for call in transport.calls] == ["koine.generate.setup", "koine.review.setup"]
