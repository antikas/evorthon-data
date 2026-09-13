"""The use-case aggregate: header and lifecycle, outputs and datasets, the named steps
between them, build routes, scenarios, authorities, standing conditions, intake
artefacts, consumer dependencies, and the provenance every recorded fact carries."""
# evorthon-verifies: EVD-README-044
# evorthon-verifies: EVD-README-043
import ast
import re
from dataclasses import FrozenInstanceError, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import get_args, get_type_hints

import pytest

from evorthon_data.engagement import (
    Actor,
    ActorKind,
    AvailabilityState,
    DatasetAvailability,
    DatasetPlaceholder,
    DecisionKind,
    DecisionOutcome,
    EngagementError,
    EngagementMode,
    Fact,
    FactLocator,
    FactProvenance,
    FactStatus,
    ImmutableReference,
    LIFECYCLE_TRANSITIONS,
    NamedHumanDecision,
    ReferenceKind,
    ReplacedOutput,
    ScenarioResult,
    StateTransition,
    StoredColumnName,
    TargetOutput,
    USE_CASE_SCHEMA_VERSION,
    UseCase,
    UseCaseHeader,
    UseCaseState,
)
from evorthon_data.engagement import use_case as module
from evorthon_data.engagement.use_case import (
    Authority,
    AuthorityRole,
    BuildRoute,
    BuildRouteDeclaration,
    CONDITION_DEFAULTS,
    CONDITION_KEYS,
    CONDITION_TOPIC_KEYS,
    CONSUMED_FIELD_NULLABILITY_INTAKE_FIELD,
    CUTOVER_CONDITIONS,
    CombinationJoin,
    CombinationMethod,
    ConditionDeclaration,
    ConditionKey,
    ConditionOverride,
    ConditionState,
    ConditionTopic,
    ConsumedFieldExpectation,
    ConsumerDependency,
    ContinuityLabel,
    CoverageStatement,
    IntakeArtefact,
    IntermediateResult,
    SOURCE_COMBINATION_INTAKE_FIELD,
    ScenarioReference,
    Segment,
    SegmentBoundary,
    SourceCombination,
    USE_CASE_INTAKE_TEMPLATE_FIELDS,
    Version,
)
from evorthon_data.verification.domain.contracts import (
    DOMAIN_FIELD_INVENTORY,
    DOMAIN_RECORD_TYPES,
    DOMAIN_TYPE_VERSIONS,
    DatasetRole,
    ExpectedOutputOrigin,
    GrainDeclaration,
    Identity,
    SchemaDeclaration,
    SchemaField,
    SchemaValueType,
    VerificationCase,
    VerificationStatus,
)


# Every machine-route form a fact locator must refuse, assembled from character
# codes so the file itself carries no such route. The shapes are declared once
# for the whole product; this aggregate reads all of them, so a locator is
# refused here for the same reasons a packet, a note and a shipped file are.
ABSOLUTE_LOCATOR = "/estate/extracts/orders.csv"
DRIVE_LOCATOR = "C" + chr(58) + "/estate/extracts/orders.csv"
NETWORK_LOCATOR = chr(92) * 2 + "estate" + chr(92) + "extracts"
HOME_LOCATOR = "/" + "home" + "/analyst/extracts"
FILE_ADDRESS_LOCATOR = "file" + chr(58) + "//estate/extracts/orders.csv"
WEB_ADDRESS_LOCATOR = "http" + chr(58) + "//estate.example/extracts"
TRAVERSAL_LOCATOR = chr(46) * 2 + "/estate/extracts/orders.csv"
BACKSLASH_LOCATOR = "estate" + chr(92) + "extracts" + chr(92) + "orders.csv"
MACHINE_ROUTES = (
    ABSOLUTE_LOCATOR,
    DRIVE_LOCATOR,
    NETWORK_LOCATOR,
    HOME_LOCATOR,
    FILE_ADDRESS_LOCATOR,
    WEB_ADDRESS_LOCATOR,
    TRAVERSAL_LOCATOR,
    BACKSLASH_LOCATOR,
)
SAFE_POSITION = "sheet=orders;row=14"
# A digit of another script, assembled from its character code so the file
# itself stays plain text.
SUPERSCRIPT_DIGIT = chr(179)
MODULE_SOURCE = Path(module.__file__).read_text(encoding="utf-8")
MODULE_RECORDS = tuple(
    value
    for value in vars(module).values()
    if is_dataclass(value) and getattr(value, "__module__", "") == module.__name__
)
PUBLIC_MOVES = {
    "verify": UseCaseState.VERIFIED,
    "accept": UseCaseState.ACCEPTED,
    "enter_service": UseCaseState.IN_SERVICE,
    "supersede": UseCaseState.SUPERSEDED,
}


def human(identity: str = "acceptance-authority") -> Actor:
    return Actor(identity=identity, kind=ActorKind.HUMAN)


def model(identity: str = "intake-coworker") -> Actor:
    return Actor(identity=identity, kind=ActorKind.MODEL)


def reference(kind: ReferenceKind, identifier: str) -> ImmutableReference:
    return ImmutableReference(kind=kind, identifier=identifier, version="v1", digest=f"digest-{identifier}")


def identity(identifier: str) -> Identity:
    return Identity(identifier=identifier, version="v1", digest=f"digest-{identifier}")


def locator(position: str = SAFE_POSITION, artefact_identifier: str = "order-extract-workbook") -> FactLocator:
    return FactLocator(
        artefact=reference(ReferenceKind.INTAKE_ARTEFACT, artefact_identifier),
        position=position,
    )


def provenance(status: FactStatus = FactStatus.EXTRACTED, position: str = SAFE_POSITION) -> FactProvenance:
    return FactProvenance(locator=locator(position=position), extracted_by=model(), status=status)


def fact(value: str) -> Fact:
    return Fact(value=value, provenance=provenance())


def schema() -> SchemaDeclaration:
    return SchemaDeclaration(
        schema_id="customer-orders",
        version="v1",
        fields=(
            SchemaField(
                field_id="order_id",
                value_type=SchemaValueType.STRING,
                nullable=False,
                semantic_role="order key",
                precision=None,
                scale=None,
            ),
            SchemaField(
                field_id="order_value",
                value_type=SchemaValueType.DECIMAL,
                nullable=False,
                semantic_role="settled order value",
                precision=18,
                scale=2,
            ),
        ),
        format_name="tabular",
    )


def grain(key_fields: tuple[str, ...] = ("order_id",)) -> GrainDeclaration:
    return GrainDeclaration(
        grain_id="one-row-per-order",
        version="v1",
        key_fields=key_fields,
        population_description="settled orders in the reporting period",
        duplicate_keys_permitted=False,
    )


def target_output(**overrides) -> TargetOutput:
    declared = {
        "output_id": "daily-order-report",
        "kind": "table",
        "schema": schema(),
        "grain": grain(),
        "cadence": "daily",
        "cutoff_semantics": "rows settled before 22:00 in the reporting timezone",
        "effective_time_semantics": "effective-dated on the settlement date",
        "provenance": provenance(),
    }
    declared.update(overrides)
    return TargetOutput(**declared)


def dataset(**overrides) -> DatasetPlaceholder:
    declared = {
        "placeholder_id": "order-extract",
        "role": DatasetRole.INPUT,
        "source_system": "order-book",
        "delivery_mode": "nightly file drop",
        "cadence": "daily",
        "access_owner": human("data-owner"),
        "classification": "confidential",
        "availability": DatasetAvailability(
            state=AvailabilityState.OBTAINED, dataset=identity("order-extract-2026-09")
        ),
        "provenance": provenance(),
    }
    declared.update(overrides)
    return DatasetPlaceholder(**declared)


def header(mode: EngagementMode = EngagementMode.MODERNISATION) -> UseCaseHeader:
    return UseCaseHeader(
        engagement_id="eng-customer-service",
        engagement_mode=mode,
        consumer=fact("the customer service operations manager"),
        outcome=fact("decide the next day staffing from settled order volume"),
        done_definition=fact("the manager can staff the rota without the legacy report"),
        cadence=fact("every working day before 07:00"),
        deadline=fact("2026-12-01"),
    )


def opened(mode: EngagementMode = EngagementMode.MODERNISATION) -> UseCase:
    return UseCase.open(reference(ReferenceKind.USE_CASE, "uc-order-volume"), header(mode))


def scenario_result(case_identifier: str = "case-normal-day", status: VerificationStatus = VerificationStatus.PASS):
    return ScenarioResult(
        case=identity(case_identifier),
        result=reference(ReferenceKind.VERIFICATION_RESULT, f"result-{case_identifier}"),
        status=status,
    )


def acceptance(decision_id: str = "accept-1", decided_by: Actor | None = None) -> NamedHumanDecision:
    return NamedHumanDecision(
        decision_id=decision_id,
        kind=DecisionKind.VERSION_ACCEPTANCE,
        outcome=DecisionOutcome.ACCEPTED,
        subject=reference(ReferenceKind.USE_CASE_VERSION, "uc-order-volume-v1"),
        decided_by=decided_by or human(),
        rationale=reference(ReferenceKind.DECISION_RATIONALE, "rationale-accept-1"),
    )


def intermediate(**overrides) -> IntermediateResult:
    declared = {
        "result_id": "settled-orders",
        "description": "orders settled before the cutoff, one row per order",
        "evidence_owner": human("evidence-owner"),
        "provenance": provenance(),
    }
    declared.update(overrides)
    return IntermediateResult(**declared)


def build_route(**overrides) -> BuildRouteDeclaration:
    declared = {
        "segment_id": "orders-to-settled",
        "route": BuildRoute.ENGINEERED,
        "provenance": provenance(),
    }
    declared.update(overrides)
    return BuildRouteDeclaration(**declared)


def scenario(case_identifier: str = "case-normal-day", **overrides) -> ScenarioReference:
    declared = {"case": identity(case_identifier), "provenance": provenance()}
    declared.update(overrides)
    return ScenarioReference(**declared)


def authority(**overrides) -> Authority:
    declared = {"role": AuthorityRole.ACCEPTING, "actor": human(), "provenance": provenance()}
    declared.update(overrides)
    return Authority(**declared)


def answered(key: ConditionKey = ConditionKey.RETENTION_WINDOW, **overrides) -> ConditionDeclaration:
    declared = {
        "key": key,
        "state": ConditionState.DECLARED,
        "provenance": provenance(),
        "value": "seven years of settled orders",
    }
    declared.update(overrides)
    return ConditionDeclaration(**declared)


def unanswered(key: ConditionKey = ConditionKey.RETENTION_WINDOW, **overrides) -> ConditionDeclaration:
    declared = {
        "key": key,
        "state": ConditionState.UNKNOWN,
        "provenance": provenance(),
        "default_value": CONDITION_DEFAULTS[key],
    }
    declared.update(overrides)
    return ConditionDeclaration(**declared)


def intake_artefact(**overrides) -> IntakeArtefact:
    declared = {
        "artefact": reference(ReferenceKind.INTAKE_ARTEFACT, "order-extract-workbook"),
        "classification": "confidential",
        "locator": "intake/order-extract-workbook",
        "provenance": provenance(),
    }
    declared.update(overrides)
    return IntakeArtefact(**declared)


def consumer_dependency(**overrides) -> ConsumerDependency:
    declared = {
        "provider": reference(ReferenceKind.USE_CASE, "uc-settled-orders"),
        "product_id": "settled-orders-table",
        "major_version": "v2",
        "provenance": provenance(),
    }
    declared.update(overrides)
    return ConsumerDependency(**declared)


def consumed_field(**overrides) -> ConsumedFieldExpectation:
    declared = {"field_id": "customer_id", "nullable": False}
    declared.update(overrides)
    return ConsumedFieldExpectation(**declared)


def source_combination(**overrides) -> SourceCombination:
    declared = {
        "segment_id": "daily-order-report",
        "method": CombinationMethod.MERGE,
        "sources": ("customer-reference", "order-extract"),
        "provenance": provenance(),
        "keys": ("customer_id",),
        "join": CombinationJoin.INNER,
    }
    declared.update(overrides)
    return SourceCombination(**declared)


def union(**overrides) -> SourceCombination:
    declared = {
        "segment_id": "daily-order-report",
        "method": CombinationMethod.UNION,
        "sources": ("customer-reference", "order-extract"),
        "provenance": provenance(),
    }
    declared.update(overrides)
    return SourceCombination(**declared)


def at_state(state: UseCaseState) -> UseCase:
    """Build a use case standing in the requested lifecycle state."""
    subject = opened().record_scenario_result(scenario_result())
    if state is UseCaseState.OPENED:
        return subject
    subject = subject.verify(human())
    if state is UseCaseState.VERIFIED:
        return subject
    subject = subject.accept(acceptance())
    if state is UseCaseState.ACCEPTED:
        return subject
    if state is UseCaseState.SUPERSEDED:
        return subject.supersede(human())
    return subject.enter_service(human())


def tokens(text: str) -> set[str]:
    return {token for token in re.split(r"[^a-z]+", text.lower()) if token}


def annotated_types(record) -> set[object]:
    found: set[object] = set()
    pending = list(get_type_hints(record).values())
    while pending:
        hint = pending.pop()
        arguments = [item for item in get_args(hint) if item is not type(None) and item is not Ellipsis]
        if arguments:
            pending.extend(arguments)
        else:
            found.add(hint)
    return found


def vocabularies_by_field() -> dict[str, set]:
    """The closed vocabularies a refusal message can interpolate, keyed by field name."""
    vocabularies: dict[str, set] = {}
    for record in MODULE_RECORDS:
        for name, hint in get_type_hints(record).items():
            if isinstance(hint, type) and issubclass(hint, Enum):
                vocabularies.setdefault(name, set()).add(hint)
    return vocabularies


VOCABULARIES_BY_FIELD = vocabularies_by_field()


def refusal_messages() -> list[str]:
    """Every text a refusal in the module can emit.

    A message is read as its literal segments, the literal segments of any
    formatted string, and, where a segment interpolates one of the module's own
    closed vocabularies, every value that vocabulary can supply. Text a caller
    supplies is the caller's own and is out of scope.
    """
    messages: list[str] = []
    for node in ast.walk(ast.parse(MODULE_SOURCE)):
        if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
            continue
        for argument in node.exc.args:
            for part in ast.walk(argument):
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    messages.append(part.value)
                elif isinstance(part, ast.Attribute):
                    messages.extend(
                        str(member.value)
                        for vocabulary in VOCABULARIES_BY_FIELD.get(part.attr, ())
                        for member in vocabulary
                    )
    return messages


def test_an_opened_use_case_records_its_header_outputs_and_datasets():
    subject = opened().record_target_output(
        target_output(
            stored_name="RPT_DAILY_ORDERS",
            stored_column_names=(StoredColumnName(field_id="order_value", stored_name="ORD_VAL"),),
            replaces=ReplacedOutput(
                identity=identity("legacy-daily-orders"),
                system="legacy reporting warehouse",
                location="reporting.dbo.rpt_daily_orders",
            ),
            defined_by=identity("order-report-specification"),
        )
    ).record_dataset(dataset())

    assert subject.schema_version == USE_CASE_SCHEMA_VERSION == "evorthon.use-case.v1"
    assert subject.state is UseCaseState.OPENED
    assert subject.header.engagement_id == "eng-customer-service"
    assert subject.header.engagement_mode is EngagementMode.MODERNISATION
    assert subject.header.done_definition.value.startswith("the manager can staff")
    assert subject.header.cadence.provenance.status is FactStatus.EXTRACTED
    output = subject.target_outputs[0]
    assert output.keys == output.grain.key_fields == ("order_id",)
    assert output.schema.schema_id == "customer-orders"
    assert output.cadence == "daily"
    assert output.cutoff_semantics.startswith("rows settled before")
    assert output.effective_time_semantics.startswith("effective-dated")
    assert output.stored_name == "RPT_DAILY_ORDERS"
    assert output.stored_column_names[0].stored_name == "ORD_VAL"
    assert output.replaces.identity == identity("legacy-daily-orders")
    assert output.replaces.location == "reporting.dbo.rpt_daily_orders"
    assert subject.datasets[0].role is DatasetRole.INPUT
    assert subject.datasets[0].availability.state is AvailabilityState.OBTAINED
    assert subject.revision == 3


@pytest.mark.parametrize("role", list(DatasetRole))
def test_every_dataset_role_is_recorded_with_its_declared_facts(role):
    placeholder = dataset(placeholder_id=f"dataset-{role.value}", role=role)

    assert placeholder.role is role
    assert placeholder.source_system == "order-book"
    assert placeholder.delivery_mode == "nightly file drop"
    assert placeholder.cadence == "daily"
    assert placeholder.access_owner.identity == "data-owner"
    assert placeholder.classification == "confidential"


@pytest.mark.parametrize(
    ("availability", "expected"),
    [
        (
            DatasetAvailability(state=AvailabilityState.OBTAINED, dataset=identity("frozen-orders")),
            identity("frozen-orders"),
        ),
        (DatasetAvailability(state=AvailabilityState.OBTAINABLE_BY, obtainable_by="2026-10-31"), None),
        (DatasetAvailability(state=AvailabilityState.UNOBTAINABLE), None),
        (
            DatasetAvailability(state=AvailabilityState.SYNTHETIC_FILLED, dataset=identity("generated-orders")),
            identity("generated-orders"),
        ),
    ],
)
def test_every_availability_state_is_recordable_and_never_stops_the_use_case(availability, expected):
    subject = opened().record_dataset(dataset(availability=availability))

    assert subject.datasets[0].availability.dataset == expected
    assert subject.state is UseCaseState.OPENED


@pytest.mark.parametrize(
    ("availability", "message"),
    [
        ({"state": AvailabilityState.OBTAINED}, "requires a dataset identity"),
        ({"state": AvailabilityState.SYNTHETIC_FILLED}, "requires a dataset identity"),
        ({"state": AvailabilityState.OBTAINABLE_BY}, "requires the date"),
        ({"state": AvailabilityState.OBTAINABLE_BY, "obtainable_by": "the end of October"}, "calendar date"),
        (
            {"state": AvailabilityState.OBTAINABLE_BY, "obtainable_by": "2026-10-31", "dataset": identity("x")},
            "carries no dataset identity",
        ),
        ({"state": AvailabilityState.UNOBTAINABLE, "dataset": identity("x")}, "carries no dataset identity"),
        (
            {"state": AvailabilityState.OBTAINED, "dataset": identity("x"), "obtainable_by": "2026-10-31"},
            "only an expected dataset carries an expected date",
        ),
        ({"state": "obtained"}, "known availability state"),
    ],
)
def test_a_self_contradicting_availability_is_refused(availability, message):
    with pytest.raises(EngagementError, match=message):
        DatasetAvailability(**availability)


@pytest.mark.parametrize("route", MACHINE_ROUTES)
def test_a_locator_position_in_a_machine_route_form_is_refused(route):
    with pytest.raises(EngagementError, match="must be logical"):
        locator(position=route)


@pytest.mark.parametrize("route", MACHINE_ROUTES)
def test_a_locator_artefact_identity_in_a_machine_route_form_is_refused(route):
    with pytest.raises(EngagementError, match="must be logical"):
        locator(artefact_identifier=route)


@pytest.mark.parametrize("route", MACHINE_ROUTES)
def test_a_replaced_output_location_in_a_machine_route_form_is_refused(route):
    with pytest.raises(EngagementError, match="must be logical"):
        ReplacedOutput(identity=identity("legacy"), system="legacy warehouse", location=route)


def test_a_logical_locator_is_accepted():
    recorded = locator()

    assert recorded.position == SAFE_POSITION
    assert recorded.artefact.kind is ReferenceKind.INTAKE_ARTEFACT
    assert provenance().artefact == recorded.artefact
    assert ReplacedOutput(
        identity=identity("legacy"), system="legacy warehouse", location="reporting.dbo.rpt_daily_orders"
    ).location == "reporting.dbo.rpt_daily_orders"


def test_a_locator_that_is_not_an_intake_artefact_identity_is_refused():
    with pytest.raises(EngagementError, match="intake_artefact identity"):
        FactLocator(artefact=reference(ReferenceKind.STAGE_RECORD, "outcome-brief"), position=SAFE_POSITION)


@pytest.mark.parametrize("status", list(FactStatus))
def test_every_fact_status_is_recorded_with_its_artefact_and_extractor(status):
    recorded = fact("the report is produced every working day")
    recorded = Fact(value=recorded.value, provenance=provenance(status=status))

    assert recorded.provenance.status is status
    assert recorded.provenance.artefact.identifier == "order-extract-workbook"
    assert recorded.provenance.extracted_by.kind is ActorKind.MODEL


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: Fact(value="the consumer is the operations manager", provenance=None), "recorded fact"),
        (lambda: target_output(provenance=None), "target output requires recorded provenance"),
        (lambda: dataset(provenance=None), "dataset requires recorded provenance"),
        (lambda: FactProvenance(locator=None, extracted_by=model(), status=FactStatus.EXTRACTED), "fact locator"),
        (lambda: FactProvenance(locator=locator(), extracted_by=None, status=FactStatus.EXTRACTED), "named extractor"),
        (lambda: FactProvenance(locator=locator(), extracted_by=model(), status="extracted"), "declared fact status"),
    ],
)
def test_a_fact_without_provenance_is_refused(build, message):
    with pytest.raises(EngagementError, match=message):
        build()


def test_a_well_formed_fact_carries_its_provenance():
    assert fact("daily").provenance.status is FactStatus.EXTRACTED
    assert target_output().provenance.artefact.kind is ReferenceKind.INTAKE_ARTEFACT
    assert dataset().provenance.extracted_by.identity == "intake-coworker"


def test_the_declared_transitions_are_exactly_the_five_lifecycle_edges():
    assert LIFECYCLE_TRANSITIONS == {
        (UseCaseState.OPENED, UseCaseState.VERIFIED),
        (UseCaseState.VERIFIED, UseCaseState.ACCEPTED),
        (UseCaseState.ACCEPTED, UseCaseState.IN_SERVICE),
        (UseCaseState.ACCEPTED, UseCaseState.SUPERSEDED),
        (UseCaseState.IN_SERVICE, UseCaseState.SUPERSEDED),
    }


@pytest.mark.parametrize("target", list(UseCaseState))
@pytest.mark.parametrize("source", list(UseCaseState))
def test_every_state_pair_is_a_declared_edge_or_refused(source, target):
    if (source, target) in LIFECYCLE_TRANSITIONS:
        move = StateTransition(source=source, target=target, moved_by=human())
        assert (move.source, move.target) == (source, target)
        return
    with pytest.raises(EngagementError, match="does not transition"):
        StateTransition(source=source, target=target, moved_by=human())


@pytest.mark.parametrize("move", sorted(PUBLIC_MOVES))
@pytest.mark.parametrize("state", list(UseCaseState))
def test_every_public_move_follows_the_declared_edges(state, move):
    subject = at_state(state)
    target = PUBLIC_MOVES[move]

    def call():
        if move == "accept":
            return subject.accept(acceptance(decision_id=f"accept-from-{state.value}"))
        return getattr(subject, move)(human())

    if (state, target) in LIFECYCLE_TRANSITIONS:
        moved = call()
        assert moved.state is target
        assert moved.transitions[-1].source is state
        assert moved.revision > subject.revision
        return
    with pytest.raises(EngagementError, match="does not transition"):
        call()


def test_the_lifecycle_walks_from_opened_to_in_service_and_then_superseded():
    subject = opened().record_target_output(target_output()).record_dataset(dataset())
    assert subject.state is UseCaseState.OPENED

    subject = subject.record_scenario_result(scenario_result("case-normal-day"))
    subject = subject.record_scenario_result(scenario_result("case-late-rows"))
    subject = subject.verify(human("verification-owner"))
    assert subject.state is UseCaseState.VERIFIED

    subject = subject.accept(acceptance())
    assert subject.state is UseCaseState.ACCEPTED
    assert subject.acceptance.decided_by.kind is ActorKind.HUMAN

    subject = subject.enter_service(human("operations-owner"))
    assert subject.state is UseCaseState.IN_SERVICE

    subject = subject.supersede(human("acceptance-authority"))
    assert subject.state is UseCaseState.SUPERSEDED
    assert [move.target for move in subject.transitions] == [
        UseCaseState.VERIFIED,
        UseCaseState.ACCEPTED,
        UseCaseState.IN_SERVICE,
        UseCaseState.SUPERSEDED,
    ]


def test_an_accepted_use_case_may_be_superseded_without_entering_service():
    subject = at_state(UseCaseState.ACCEPTED).supersede(human())

    assert subject.state is UseCaseState.SUPERSEDED
    assert [move.source for move in subject.transitions][-1] is UseCaseState.ACCEPTED


@pytest.mark.parametrize(
    ("results", "message"),
    [
        ((), "requires a recorded scenario result"),
        ((scenario_result("case-normal-day", VerificationStatus.FAIL),), "passing result for every scenario"),
        (
            (scenario_result("case-normal-day", VerificationStatus.INSUFFICIENT_EVIDENCE),),
            "passing result for every scenario",
        ),
        (
            (scenario_result("case-normal-day"), scenario_result("case-late-rows", VerificationStatus.FAIL)),
            "passing result for every scenario",
        ),
    ],
)
def test_verification_needs_a_passing_result_for_every_recorded_scenario(results, message):
    subject = opened()
    for result in results:
        subject = subject.record_scenario_result(result)

    with pytest.raises(EngagementError, match=message):
        subject.verify(human())


def test_verification_succeeds_when_every_recorded_scenario_passes():
    subject = opened()
    for case_identifier in ("case-normal-day", "case-late-rows", "case-empty-input"):
        subject = subject.record_scenario_result(scenario_result(case_identifier))

    verified = subject.verify(human())

    assert verified.state is UseCaseState.VERIFIED
    assert len(verified.scenario_results) == 3


@pytest.mark.parametrize("move", ["verify", "enter_service", "supersede"])
def test_a_model_actor_cannot_move_the_lifecycle(move):
    state = {"verify": UseCaseState.OPENED, "enter_service": UseCaseState.ACCEPTED, "supersede": UseCaseState.ACCEPTED}
    subject = at_state(state[move])

    with pytest.raises(EngagementError, match="only a named human"):
        getattr(subject, move)(model())


def test_a_model_actor_cannot_accept_a_use_case_version():
    with pytest.raises(EngagementError, match="only a named human"):
        acceptance(decided_by=model())


def test_a_named_human_moves_the_lifecycle():
    assert at_state(UseCaseState.IN_SERVICE).transitions[-1].moved_by.kind is ActorKind.HUMAN


def test_a_greenfield_use_case_has_no_replaced_output():
    replaced = ReplacedOutput(
        identity=identity("legacy-daily-orders"), system="legacy warehouse", location="reporting.dbo.rpt_daily_orders"
    )

    with pytest.raises(EngagementError, match="only a modernisation use case"):
        opened(EngagementMode.GREENFIELD).record_target_output(target_output(replaces=replaced))

    modernisation = opened().record_target_output(target_output(replaces=replaced))
    greenfield = opened(EngagementMode.GREENFIELD).record_target_output(
        target_output(defined_by=identity("order-report-specification"))
    )

    assert modernisation.target_outputs[0].replaces == replaced
    assert greenfield.target_outputs[0].replaces is None
    assert greenfield.target_outputs[0].defined_by == identity("order-report-specification")


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: target_output(grain=grain(key_fields=())), "must declare its keys"),
        (lambda: target_output(grain=grain(key_fields=("customer_id",))), "not declared schema fields"),
        (
            lambda: target_output(stored_column_names=(StoredColumnName(field_id="customer_id", stored_name="C"),)),
            "undeclared field",
        ),
        (
            lambda: target_output(
                stored_column_names=(
                    StoredColumnName(field_id="order_id", stored_name="A"),
                    StoredColumnName(field_id="order_id", stored_name="B"),
                )
            ),
            "two stored column names",
        ),
        (lambda: target_output(schema=None), "must declare a schema"),
        (lambda: target_output(grain=None), "must declare a grain"),
    ],
)
def test_a_self_contradicting_target_output_is_refused(build, message):
    with pytest.raises(EngagementError, match=message):
        build()


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (
            lambda: opened().record_target_output(target_output()).record_target_output(target_output()),
            "output identities must be unique",
        ),
        (
            lambda: opened().record_dataset(dataset()).record_dataset(dataset()),
            "dataset identities must be unique",
        ),
        (
            lambda: opened().record_scenario_result(scenario_result()).record_scenario_result(scenario_result()),
            "only one result",
        ),
        (
            lambda: UseCase.open(reference(ReferenceKind.STAGE_RECORD, "uc-1"), header()),
            "use_case identity",
        ),
        (
            lambda: UseCase(
                identity=reference(ReferenceKind.USE_CASE, "uc-1"),
                header=header(),
                schema_version="evorthon.use-case.v2",
            ),
            "unsupported use-case schema version",
        ),
        (
            lambda: UseCase(
                identity=reference(ReferenceKind.USE_CASE, "uc-1"),
                header=header(),
                state=UseCaseState.VERIFIED,
                scenario_results=(scenario_result(),),
                transitions=(
                    StateTransition(
                        source=UseCaseState.ACCEPTED, target=UseCaseState.IN_SERVICE, moved_by=human()
                    ),
                ),
            ),
            "unbroken chain",
        ),
        (
            lambda: UseCase(
                identity=reference(ReferenceKind.USE_CASE, "uc-1"),
                header=header(),
                state=UseCaseState.VERIFIED,
                scenario_results=(scenario_result(),),
            ),
            "does not end at the current state",
        ),
        (
            lambda: UseCase(
                identity=reference(ReferenceKind.USE_CASE, "uc-1"),
                header=header(),
                state=UseCaseState.ACCEPTED,
                scenario_results=(scenario_result(),),
                transitions=(
                    StateTransition(source=UseCaseState.OPENED, target=UseCaseState.VERIFIED, moved_by=human()),
                    StateTransition(source=UseCaseState.VERIFIED, target=UseCaseState.ACCEPTED, moved_by=human()),
                ),
            ),
            "requires a named human acceptance decision",
        ),
    ],
)
def test_a_self_contradicting_use_case_record_is_refused(build, message):
    with pytest.raises(EngagementError, match=message):
        build()


@pytest.mark.parametrize(
    ("decision", "message"),
    [
        (
            NamedHumanDecision(
                decision_id="approve-1",
                kind=DecisionKind.RECORD_APPROVAL,
                outcome=DecisionOutcome.APPROVED,
                subject=reference(ReferenceKind.STAGE_RECORD, "outcome-brief"),
                decided_by=human(),
                rationale=reference(ReferenceKind.DECISION_RATIONALE, "rationale-approve-1"),
            ),
            "version_acceptance decisions only",
        ),
        (
            NamedHumanDecision(
                decision_id="accept-2",
                kind=DecisionKind.VERSION_ACCEPTANCE,
                outcome=DecisionOutcome.APPROVED,
                subject=reference(ReferenceKind.USE_CASE_VERSION, "uc-order-volume-v1"),
                decided_by=human(),
                rationale=reference(ReferenceKind.DECISION_RATIONALE, "rationale-accept-2"),
            ),
            "accepted outcome",
        ),
        (
            NamedHumanDecision(
                decision_id="accept-3",
                kind=DecisionKind.VERSION_ACCEPTANCE,
                outcome=DecisionOutcome.ACCEPTED,
                subject=reference(ReferenceKind.APPROVED_WORK, "package-1"),
                decided_by=human(),
                rationale=reference(ReferenceKind.DECISION_RATIONALE, "rationale-accept-3"),
            ),
            "use_case_version identity",
        ),
    ],
)
def test_an_acceptance_that_is_not_a_version_acceptance_is_refused(decision, message):
    subject = at_state(UseCaseState.VERIFIED)

    with pytest.raises(EngagementError, match=message):
        subject.accept(decision)


def test_a_scenario_result_is_held_by_case_and_result_identity_only():
    recorded = scenario_result()

    assert recorded.case == identity("case-normal-day")
    assert recorded.result.kind is ReferenceKind.VERIFICATION_RESULT
    assert recorded.passed is True

    with pytest.raises(EngagementError, match="verification_result identity"):
        ScenarioResult(
            case=identity("case-normal-day"),
            result=reference(ReferenceKind.BUILD_EVIDENCE, "build-1"),
            status=VerificationStatus.PASS,
        )
    with pytest.raises(EngagementError, match="name its case by identity"):
        ScenarioResult(
            case="case-normal-day",
            result=reference(ReferenceKind.VERIFICATION_RESULT, "result-1"),
            status=VerificationStatus.PASS,
        )


def test_the_aggregate_stores_no_verification_case_content_beyond_identity():
    case_content = set(DOMAIN_FIELD_INVENTORY["VerificationCase"]) - {"case_id", "version"}
    stored_fields = {declared.name for record in MODULE_RECORDS for declared in fields(record)}
    referenced = set()
    for record in MODULE_RECORDS:
        referenced |= annotated_types(record)
    domain_referenced = {
        item for item in referenced if getattr(item, "__name__", "") in set(DOMAIN_TYPE_VERSIONS)
    }

    assert stored_fields & case_content == set()
    assert VerificationCase not in referenced
    assert domain_referenced == {
        SchemaDeclaration,
        GrainDeclaration,
        Identity,
        DatasetRole,
        VerificationStatus,
        ExpectedOutputOrigin,
    }
    assert domain_referenced & set(DOMAIN_RECORD_TYPES) == {SchemaDeclaration, GrainDeclaration, Identity}


def test_the_state_vocabulary_names_no_blocked_use_case():
    forbidden = {
        "block",
        "blocked",
        "blocker",
        "blocking",
        "blocks",
        "deferred",
        "gated",
        "halted",
        "impeded",
        "paused",
        "stalled",
        "stuck",
        "suspended",
        "waiting",
    }
    vocabulary = set()
    for state in UseCaseState:
        vocabulary |= tokens(state.name) | tokens(state.value)
    for record in MODULE_RECORDS:
        vocabulary |= tokens(record.__name__)
        for field in fields(record):
            vocabulary |= tokens(field.name)
    for name in vars(module):
        if not name.startswith("__"):
            vocabulary |= tokens(name)

    assert [state.value for state in UseCaseState] == [
        "opened",
        "verified",
        "accepted",
        "in_service",
        "superseded",
    ]
    assert vocabulary & forbidden == set()


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: FactLocator(artefact=None, position=SAFE_POSITION), "intake_artefact identity"),
        (lambda: locator(position="  "), "locator position is required"),
        (lambda: Fact(value="  ", provenance=provenance()), "fact value is required"),
        (lambda: UseCaseHeader(**{**vars(header()), "engagement_id": " "}), "engagement identity is required"),
        (lambda: UseCaseHeader(**{**vars(header()), "engagement_id": "tbd"}), "must not be a placeholder"),
        (
            lambda: UseCaseHeader(**{**vars(header()), "engagement_mode": "modernisation"}),
            "declare the engagement mode",
        ),
        (
            lambda: UseCaseHeader(**{**vars(header()), "consumer": "the operations manager"}),
            "the consumer must be a recorded fact",
        ),
        (lambda: UseCaseHeader(**{**vars(header()), "deadline": None}), "the deadline must be a recorded fact"),
        (lambda: StoredColumnName(field_id=" ", stored_name="ORD"), "stored column field is required"),
        (lambda: StoredColumnName(field_id="order_id", stored_name=" "), "stored column name is required"),
        (
            lambda: ReplacedOutput(identity="legacy", system="legacy warehouse", location="reporting.rpt"),
            "must be named by identity",
        ),
        (
            lambda: ReplacedOutput(identity=identity("legacy"), system=" ", location="reporting.rpt"),
            "replaced output system is required",
        ),
        (
            lambda: ReplacedOutput(identity=identity("legacy"), system="legacy warehouse", location=" "),
            "replaced output location is required",
        ),
        (lambda: target_output(output_id=" "), "output identity is required"),
        (lambda: target_output(kind=" "), "output kind is required"),
        (lambda: target_output(cadence=" "), "output cadence is required"),
        (lambda: target_output(cutoff_semantics=" "), "output cutoff semantics is required"),
        (lambda: target_output(effective_time_semantics=" "), "output effective-time semantics is required"),
        (lambda: target_output(stored_name=" "), "output stored name is required"),
        (lambda: target_output(stored_column_names=("order_id",)), "declared stored column names"),
        (lambda: target_output(replaces="the legacy report"), "declared replaced output"),
        (lambda: target_output(defined_by="the specification"), "named by identity"),
        (lambda: dataset(placeholder_id=" "), "dataset identity is required"),
        (lambda: dataset(role="input"), "must declare its role"),
        (lambda: dataset(source_system=" "), "dataset source system is required"),
        (lambda: dataset(delivery_mode=" "), "dataset delivery mode is required"),
        (lambda: dataset(cadence=" "), "dataset cadence is required"),
        (lambda: dataset(access_owner="the data owner"), "must name an access owner"),
        (lambda: dataset(classification=" "), "dataset classification is required"),
        (lambda: dataset(availability="obtained"), "must declare its availability"),
        (
            lambda: ScenarioResult(
                case=identity("case-normal-day"), result="result-1", status=VerificationStatus.PASS
            ),
            "verification_result identity",
        ),
        (
            lambda: ScenarioResult(
                case=identity("case-normal-day"),
                result=reference(ReferenceKind.VERIFICATION_RESULT, "result-1"),
                status="pass",
            ),
            "deterministic status",
        ),
        (
            lambda: StateTransition(source="opened", target=UseCaseState.VERIFIED, moved_by=human()),
            "must name declared states",
        ),
        (
            lambda: StateTransition(source=UseCaseState.OPENED, target="verified", moved_by=human()),
            "must name declared states",
        ),
        (lambda: UseCase.open(reference(ReferenceKind.USE_CASE, "uc-1"), None), "must carry a header"),
        (lambda: UseCase.open("uc-1", header()), "use_case identity"),
        (
            lambda: UseCase(identity=reference(ReferenceKind.USE_CASE, "uc-1"), header=header(), revision=0),
            "revision must be positive",
        ),
        (
            lambda: UseCase(identity=reference(ReferenceKind.USE_CASE, "uc-1"), header=header(), state="opened"),
            "declared lifecycle state",
        ),
        (
            lambda: UseCase(
                identity=reference(ReferenceKind.USE_CASE, "uc-1"), header=header(), target_outputs=("report",)
            ),
            "declared target outputs",
        ),
        (
            lambda: UseCase(
                identity=reference(ReferenceKind.USE_CASE, "uc-1"), header=header(), datasets=("extract",)
            ),
            "must be declared datasets",
        ),
        (
            lambda: UseCase(
                identity=reference(ReferenceKind.USE_CASE, "uc-1"), header=header(), scenario_results=("result",)
            ),
            "declared scenario results",
        ),
        (
            lambda: UseCase(
                identity=reference(ReferenceKind.USE_CASE, "uc-1"), header=header(), decisions=("accepted",)
            ),
            "must be named human decisions",
        ),
        (
            lambda: UseCase(
                identity=reference(ReferenceKind.USE_CASE, "uc-1"),
                header=header(),
                decisions=(acceptance("accept-1"), acceptance("accept-1")),
            ),
            "decision ids must be unique",
        ),
        (
            lambda: UseCase(
                identity=reference(ReferenceKind.USE_CASE, "uc-1"), header=header(), transitions=("moved",)
            ),
            "declared lifecycle moves",
        ),
        (lambda: opened().accept(None), "requires a named human decision"),
    ],
)
def test_an_incomplete_or_wrongly_typed_declaration_is_refused(build, message):
    with pytest.raises(EngagementError, match=message):
        build()


def test_every_refusal_in_the_module_is_an_integrity_refusal():
    messages = refusal_messages()
    gate_words = {"assurance", "blocked", "policy", "readiness", "ready", "synthetic", "unproven"}
    used = set()
    for message in messages:
        used |= tokens(message)

    assert messages
    assert {state.value for state in UseCaseState} <= set(messages)
    assert used & gate_words == set()


# The standing conditions the intake asks once and may have answered at any
# time, transcribed from the scope record topic by topic.
CONDITION_KEYS_BY_TOPIC = {
    # The data class, the owner and the steward, the permitted purpose,
    # residency, masking outside production, and who may see the evidence.
    ConditionTopic.CLASSIFICATION_AND_HANDLING: (
        "handling_classification",
        "data_owner",
        "data_steward",
        "permitted_purpose",
        "residency",
        "non_production_masking",
        "evidence_visibility",
    ),
    # Retention, backfill depth, as-of reproducibility, how history is kept,
    # how slowly changing attributes are held, how a restatement is handled,
    # what stays online against what is archived, and any erasure obligation.
    ConditionTopic.HISTORY_AND_TIME: (
        "retention_window",
        "backfill_depth",
        "as_of_reproducibility",
        "historisation_kind",
        "slowly_changing_attributes",
        "restatement_handling",
        "archive_or_online",
        "erasure_obligation",
    ),
    # Freshness and its deadline, what a missed deadline means and who hears of
    # it, the reconciliation controls the consumer expects, who runs and fixes
    # it, monitoring, and the run settings a runtime manifest needs.
    ConditionTopic.FRESHNESS_AND_OPERATIONS: (
        "freshness_deadline",
        "missed_deadline_response",
        "reconciliation_controls",
        "operational_owner",
        "monitoring",
        "checkpoint_granularity",
        "max_retries",
        "backoff",
    ),
    # Rows per load and in total, growth and peaks, the consumer query pattern,
    # and any cost ceiling.
    ConditionTopic.VOLUME_AND_PERFORMANCE: (
        "load_volume",
        "growth_and_peaks",
        "query_pattern",
        "cost_ceiling",
    ),
    # Who reads the output and through what, authentication and authorisation,
    # row or column restrictions, and the downstream consumers.
    ConditionTopic.ACCESS_AND_CONSUMPTION: (
        "consumption_route",
        "authentication_and_authorisation",
        "row_or_column_restrictions",
        "downstream_consumers",
    ),
    # Accepted known source defects, what warns against what fails, and the
    # completeness the consumer expects.
    ConditionTopic.QUALITY_TOLERANCES: (
        "accepted_source_defects",
        "warning_and_failure_classes",
        "completeness_expectation",
    ),
    # Change frequency and approver, compatibility obligations, the audit and
    # lineage evidence a regulator asks for and how long it is kept, and, for a
    # modernisation only, the parallel run, the cutover, who decommissions the
    # old output and how it is rolled back.
    ConditionTopic.CHANGE_AND_AUDIT: (
        "change_frequency",
        "change_approver",
        "compatibility_obligation",
        "audit_evidence",
        "audit_evidence_retention",
        "parallel_run_period",
        "cutover_criteria",
        "decommission_owner",
        "rollback",
    ),
}


def test_an_opened_use_case_records_its_steps_routes_scenarios_and_authorities():
    subject = (
        opened()
        .record_intermediate_result(
            intermediate(
                origin=ExpectedOutputOrigin.MODERNISATION_CAPTURE, continuity=ContinuityLabel.CONTINUITY
            )
        )
        .record_build_route(
            build_route(
                route=BuildRoute.GENERATED, target_shape="table", layer="curated", product_domain="orders"
            )
        )
        .record_scenario(scenario())
        .record_authority(authority())
        .record_authority(
            authority(role=AuthorityRole.EVIDENCE_OWNER, actor=human("data-owner"), subject="order-extract")
        )
        .record_authority(authority(role=AuthorityRole.AMBIGUITY_RESOLVER, actor=human("chief-analyst")))
        .record_condition(answered())
        .record_condition(unanswered(ConditionKey.FRESHNESS_DEADLINE))
        .record_intake_artefact(intake_artefact())
        .record_consumer_dependency(consumer_dependency())
    )

    step = subject.intermediate_results[0]
    assert step.result_id == "settled-orders"
    assert step.checkpoint_candidate is True
    assert step.evidence_owner.identity == "evidence-owner"
    assert step.continuity is ContinuityLabel.CONTINUITY
    assert step.origin is ExpectedOutputOrigin.MODERNISATION_CAPTURE
    assert step.provenance.status is FactStatus.EXTRACTED
    route = subject.build_routes[0]
    assert (route.segment_id, route.route, route.target_shape, route.layer, route.product_domain) == (
        "orders-to-settled",
        BuildRoute.GENERATED,
        "table",
        "curated",
        "orders",
    )
    assert subject.scenarios[0].case == identity("case-normal-day")
    assert [item.role for item in subject.authorities] == [
        AuthorityRole.ACCEPTING,
        AuthorityRole.EVIDENCE_OWNER,
        AuthorityRole.AMBIGUITY_RESOLVER,
    ]
    assert subject.conditions[0].effective_value == "seven years of settled orders"
    assert subject.conditions[1].effective_value == "no deadline"
    assert subject.intake_artefacts[0].artefact.digest == "digest-order-extract-workbook"
    assert subject.intake_artefacts[0].classification == "confidential"
    assert subject.consumer_dependencies[0].major_version == "v2"
    assert subject.state is UseCaseState.OPENED
    assert subject.revision == 11


def test_every_named_step_is_a_checkpoint_candidate_unless_it_says_otherwise():
    assert intermediate().checkpoint_candidate is True
    assert intermediate(checkpoint_candidate=False).checkpoint_candidate is False

    with pytest.raises(EngagementError, match="whether it is a checkpoint candidate"):
        intermediate(checkpoint_candidate="yes")


@pytest.mark.parametrize("route", list(BuildRoute))
def test_every_build_route_is_recorded_for_its_segment(route):
    declared = build_route(
        segment_id=f"segment-{route.value}",
        route=route,
        target_shape="table",
        layer="curated",
        product_domain="orders" if route is BuildRoute.GENERATED else None,
    )

    assert declared.route is route
    assert declared.segment_id == f"segment-{route.value}"
    assert declared.target_shape == "table"
    assert declared.layer == "curated"
    assert (declared.product_domain is not None) is (route is BuildRoute.GENERATED)


def test_a_generated_segment_names_its_product_domain_and_no_other_route_does():
    with pytest.raises(EngagementError, match="must name the product domain"):
        build_route(route=BuildRoute.GENERATED)
    with pytest.raises(EngagementError, match="only a generated segment names a product domain"):
        build_route(route=BuildRoute.EXISTING, product_domain="orders")

    assert build_route(route=BuildRoute.GENERATED, product_domain="orders").product_domain == "orders"
    assert build_route(route=BuildRoute.EXISTING).product_domain is None


def test_a_segment_declares_one_build_route():
    with pytest.raises(EngagementError, match="one build route"):
        opened().record_build_route(build_route()).record_build_route(build_route())

    subject = (
        opened()
        .record_build_route(build_route())
        .record_build_route(build_route(segment_id="settled-to-report"))
    )
    assert [item.segment_id for item in subject.build_routes] == ["orders-to-settled", "settled-to-report"]


def test_a_greenfield_use_case_carries_no_continuity_label():
    with pytest.raises(EngagementError, match="only a modernisation use case labels continuity"):
        opened(EngagementMode.GREENFIELD).record_intermediate_result(
            intermediate(continuity=ContinuityLabel.ACCIDENT)
        )

    modernisation = opened().record_intermediate_result(intermediate(continuity=ContinuityLabel.ACCIDENT))
    greenfield = opened(EngagementMode.GREENFIELD).record_intermediate_result(intermediate())

    assert modernisation.intermediate_results[0].continuity is ContinuityLabel.ACCIDENT
    assert greenfield.intermediate_results[0].continuity is None


@pytest.mark.parametrize("origin", list(ExpectedOutputOrigin))
def test_a_greenfield_use_case_takes_no_expected_value_from_an_old_run(origin):
    step = intermediate(origin=origin)
    greenfield = opened(EngagementMode.GREENFIELD)

    if origin is ExpectedOutputOrigin.MODERNISATION_CAPTURE:
        with pytest.raises(EngagementError, match="from an old run"):
            greenfield.record_intermediate_result(step)
        assert opened().record_intermediate_result(step).intermediate_results[0].origin is origin
        return
    assert greenfield.record_intermediate_result(step).intermediate_results[0].origin is origin


def test_a_scenario_reference_stores_the_case_identity_and_version_and_no_case_content():
    case_content = set(DOMAIN_FIELD_INVENTORY["VerificationCase"]) - {"case_id", "version"}
    declared = scenario()

    assert {item.name for item in fields(ScenarioReference)} == {"case", "provenance"}
    assert {item.name for item in fields(ScenarioReference)} & case_content == set()
    assert (declared.case.identifier, declared.case.version) == ("case-normal-day", "v1")

    with pytest.raises(EngagementError, match="scenario case version is required"):
        scenario(case=Identity(identifier="case-normal-day", version=" ", digest="digest-case"))
    with pytest.raises(EngagementError, match="name its case by identity"):
        scenario(case="case-normal-day")


def test_a_scenario_is_named_once():
    with pytest.raises(EngagementError, match="a scenario is named once"):
        opened().record_scenario(scenario()).record_scenario(scenario())

    subject = opened().record_scenario(scenario()).record_scenario(scenario("case-late-rows"))
    assert [item.case.identifier for item in subject.scenarios] == ["case-normal-day", "case-late-rows"]


@pytest.mark.parametrize("role", list(AuthorityRole))
def test_only_a_named_human_holds_a_deciding_authority(role):
    subject = "order-extract" if role is AuthorityRole.EVIDENCE_OWNER else None

    assert authority(role=role, actor=human(), subject=subject).actor.kind is ActorKind.HUMAN
    if role is AuthorityRole.EVIDENCE_OWNER:
        service = Actor(identity="extract-service", kind=ActorKind.SERVICE)
        assert authority(role=role, actor=service, subject=subject).actor.kind is ActorKind.SERVICE
        return
    with pytest.raises(EngagementError, match="only a named human may hold a deciding authority"):
        authority(role=role, actor=model())


def test_an_evidence_owner_names_its_subject_and_no_other_authority_does():
    owned = authority(role=AuthorityRole.EVIDENCE_OWNER, actor=human("data-owner"), subject="order-extract")

    assert owned.subject == "order-extract"
    assert authority().subject is None

    with pytest.raises(EngagementError, match="must name the subject it owns the evidence for"):
        authority(role=AuthorityRole.EVIDENCE_OWNER, actor=human("data-owner"))
    with pytest.raises(EngagementError, match="only an evidence owner names a subject"):
        authority(subject="order-extract")


def test_the_use_case_names_one_accepting_authority_one_resolver_and_one_owner_for_each_subject():
    owner = authority(role=AuthorityRole.EVIDENCE_OWNER, actor=human("data-owner"), subject="order-extract")

    with pytest.raises(EngagementError, match="one accepting authority"):
        opened().record_authority(authority()).record_authority(authority(actor=human("deputy")))
    with pytest.raises(EngagementError, match="one evidence owner is named for each subject"):
        opened().record_authority(owner).record_authority(owner)

    subject = (
        opened()
        .record_authority(owner)
        .record_authority(
            authority(
                role=AuthorityRole.EVIDENCE_OWNER, actor=human("finance-owner"), subject="settled-orders"
            )
        )
    )
    assert [item.subject for item in subject.authorities] == ["order-extract", "settled-orders"]


def test_the_standing_conditions_cover_every_topic_the_intake_asks_about():
    declared = {topic: tuple(key.value for key in keys) for topic, keys in CONDITION_TOPIC_KEYS.items()}

    assert declared == CONDITION_KEYS_BY_TOPIC
    assert set(CONDITION_KEYS) == set(ConditionKey)
    assert len(CONDITION_KEYS) == len(set(CONDITION_KEYS)) == len(ConditionKey) == 43
    assert set(CONDITION_DEFAULTS) == set(ConditionKey)
    assert CUTOVER_CONDITIONS < set(ConditionKey)


def test_the_run_settings_and_the_named_handling_defaults_are_the_declared_values():
    assert CONDITION_DEFAULTS[ConditionKey.CHECKPOINT_GRANULARITY] == "step"
    assert CONDITION_DEFAULTS[ConditionKey.MAX_RETRIES] == "3"
    assert CONDITION_DEFAULTS[ConditionKey.BACKOFF] == "exponential"
    assert CONDITION_DEFAULTS[ConditionKey.HANDLING_CLASSIFICATION] == "confidential"
    assert CONDITION_DEFAULTS[ConditionKey.RETENTION_WINDOW] == "keep everything"
    assert CONDITION_DEFAULTS[ConditionKey.FRESHNESS_DEADLINE] == "no deadline"


@pytest.mark.parametrize("key", list(ConditionKey))
def test_an_unanswered_condition_records_the_default_it_falls_back_to(key):
    declared = unanswered(key)

    assert declared.state is ConditionState.UNKNOWN
    assert declared.value is None
    assert declared.default_value == CONDITION_DEFAULTS[key]
    assert declared.effective_value == CONDITION_DEFAULTS[key]


def test_an_unanswered_condition_without_a_recorded_default_is_refused():
    with pytest.raises(EngagementError, match="must record the default it falls back to"):
        unanswered(default_value=None)
    with pytest.raises(EngagementError, match="must be the default the condition key declares"):
        unanswered(default_value="six months")

    assert unanswered().effective_value == "keep everything"


def test_an_answered_condition_carries_the_value_it_was_given_and_no_default():
    declared = answered()

    assert declared.state is ConditionState.DECLARED
    assert declared.default_value is None
    assert declared.effective_value == "seven years of settled orders"

    with pytest.raises(EngagementError, match="requires the value it was given"):
        answered(value=None)
    with pytest.raises(EngagementError, match="records no default"):
        answered(default_value="keep everything")
    with pytest.raises(EngagementError, match="carries no given value"):
        unanswered(value="seven years of settled orders")


def test_a_named_human_overrides_a_default_and_the_override_carries_its_author():
    override = ConditionOverride(value="two years", author=human("data-protection-owner"))
    declared = unanswered(ConditionKey.RETENTION_WINDOW, override=override)

    assert declared.default_value == "keep everything"
    assert declared.effective_value == "two years"
    assert declared.override.author.kind is ActorKind.HUMAN

    with pytest.raises(EngagementError, match="an override must name its author"):
        ConditionOverride(value="two years", author=None)
    with pytest.raises(EngagementError, match="only a named human may override a default"):
        ConditionOverride(value="two years", author=model())
    with pytest.raises(EngagementError, match="only an unanswered condition carries an override"):
        answered(override=override)


def test_a_condition_is_declared_once():
    with pytest.raises(EngagementError, match="a condition is declared once"):
        opened().record_condition(answered()).record_condition(unanswered())

    subject = opened().record_condition(answered()).record_condition(unanswered(ConditionKey.BACKOFF))
    assert [item.key for item in subject.conditions] == [ConditionKey.RETENTION_WINDOW, ConditionKey.BACKOFF]


@pytest.mark.parametrize("key", sorted(CUTOVER_CONDITIONS, key=lambda item: item.value))
def test_only_a_modernisation_use_case_declares_a_cutover_condition(key):
    with pytest.raises(EngagementError, match="only a modernisation use case declares a cutover condition"):
        opened(EngagementMode.GREENFIELD).record_condition(unanswered(key))

    assert opened().record_condition(unanswered(key)).conditions[0].key is key


def test_an_intake_artefact_is_held_by_identity_digest_classification_and_a_logical_locator():
    declared = intake_artefact()

    assert declared.artefact.kind is ReferenceKind.INTAKE_ARTEFACT
    assert declared.artefact.digest == "digest-order-extract-workbook"
    assert declared.classification == "confidential"
    assert declared.locator == "intake/order-extract-workbook"

    with pytest.raises(EngagementError, match="intake_artefact identity"):
        intake_artefact(artefact=reference(ReferenceKind.STAGE_RECORD, "outcome-brief"))


@pytest.mark.parametrize("route", MACHINE_ROUTES)
def test_an_intake_artefact_locator_in_a_machine_route_form_is_refused(route):
    with pytest.raises(EngagementError, match="must be logical"):
        intake_artefact(locator=route)


@pytest.mark.parametrize("route", MACHINE_ROUTES)
def test_an_intake_artefact_identity_in_a_machine_route_form_is_refused(route):
    with pytest.raises(EngagementError, match="must be logical"):
        intake_artefact(artefact=reference(ReferenceKind.INTAKE_ARTEFACT, route))


def test_intake_artefact_identities_are_unique():
    with pytest.raises(EngagementError, match="intake artefact identities must be unique"):
        opened().record_intake_artefact(intake_artefact()).record_intake_artefact(intake_artefact())

    subject = (
        opened()
        .record_intake_artefact(intake_artefact())
        .record_intake_artefact(
            intake_artefact(
                artefact=reference(ReferenceKind.INTAKE_ARTEFACT, "order-data-dictionary"),
                locator="intake/order-data-dictionary",
            )
        )
    )
    assert [item.artefact.identifier for item in subject.intake_artefacts] == [
        "order-extract-workbook",
        "order-data-dictionary",
    ]


@pytest.mark.parametrize("pin", ["v2", "2", "v10"])
def test_a_consumed_product_is_pinned_to_a_major_version(pin):
    declared = consumer_dependency(major_version=pin)

    assert declared.major_version == pin
    assert declared.provider.kind is ReferenceKind.USE_CASE
    assert declared.product_id == "settled-orders-table"


@pytest.mark.parametrize(
    "pin",
    [
        "",
        "  ",
        "v2.1",
        "2.1.3",
        "latest",
        None,
        # A superscript three reads as a digit to Python but is not a number a
        # reader can compare, so it is not a pin.
        SUPERSCRIPT_DIGIT,
        "v" + SUPERSCRIPT_DIGIT,
    ],
)
def test_a_consumer_dependency_without_a_major_version_pin_is_refused(pin):
    with pytest.raises(EngagementError, match="must pin a major version"):
        consumer_dependency(major_version=pin)


def test_a_use_case_does_not_consume_its_own_product():
    with pytest.raises(EngagementError, match="does not consume its own product"):
        opened().record_consumer_dependency(
            consumer_dependency(provider=reference(ReferenceKind.USE_CASE, "uc-order-volume"))
        )


def test_a_consumed_product_is_pinned_once():
    with pytest.raises(EngagementError, match="a consumed product is pinned once"):
        opened().record_consumer_dependency(consumer_dependency()).record_consumer_dependency(
            consumer_dependency()
        )

    subject = (
        opened()
        .record_consumer_dependency(consumer_dependency())
        .record_consumer_dependency(consumer_dependency(product_id="settled-orders-summary"))
    )
    assert [item.product_id for item in subject.consumer_dependencies] == [
        "settled-orders-table",
        "settled-orders-summary",
    ]


def test_a_consumed_product_names_which_of_the_fields_it_is_read_for_can_be_empty():
    pinned = consumer_dependency(
        expected_fields=(consumed_field(), consumed_field(field_id="segment_name", nullable=True))
    )

    recorded = opened().record_consumer_dependency(pinned).consumer_dependencies[0]

    assert [item.field_id for item in recorded.expected_fields] == ["customer_id", "segment_name"]
    assert [item.nullable for item in recorded.expected_fields] == [False, True]
    assert recorded.provenance.status is FactStatus.EXTRACTED
    assert consumer_dependency().expected_fields == ()

    with pytest.raises(EngagementError, match="a consumed field is expected twice: customer_id"):
        consumer_dependency(expected_fields=(consumed_field(), consumed_field(nullable=True)))


def test_a_segment_declares_how_the_sources_it_reads_combine():
    subject = joining_use_case().record_source_combination(source_combination())

    reached = subject.segments()[0]
    assert reached.sources == ("customer-reference", "order-extract")
    assert reached.combination.method is CombinationMethod.MERGE
    assert reached.combination.sources == ("customer-reference", "order-extract")
    assert reached.combination.keys == ("customer_id",)
    assert reached.combination.join is CombinationJoin.INNER
    assert reached.combination.provenance.artefact.kind is ReferenceKind.INTAKE_ARTEFACT
    assert [item.value for item in CombinationMethod] == ["union", "merge"]
    assert [item.value for item in CombinationJoin] == ["inner", "outer"]


def test_a_union_carries_its_method_alone_and_an_undeclared_span_carries_no_combination():
    declared = joining_use_case().record_source_combination(union()).segments()[0].combination

    assert declared.method is CombinationMethod.UNION
    assert (declared.keys, declared.join) == ((), None)
    assert joining_use_case().segments()[0].combination is None


def test_a_combination_naming_a_source_the_segment_does_not_read_is_refused():
    unread = source_combination(sources=("order-extract", "supplier-extract"))

    with pytest.raises(EngagementError, match="does not read: supplier-extract"):
        joining_use_case().record_source_combination(unread)

    # A segment the record does not derive yet is an incomplete record, not a
    # contradiction, so the declaration waits for the span it belongs to.
    early = source_combination(segment_id="weekly-order-report")
    assert joining_use_case().record_source_combination(early).source_combinations == (early,)


def test_a_segment_declares_one_source_combination():
    subject = joining_use_case().record_source_combination(source_combination())

    with pytest.raises(EngagementError, match="a segment declares one source combination"):
        subject.record_source_combination(union())


def test_the_intake_record_names_each_new_declaration_once():
    named = [
        section
        for section, declared in USE_CASE_INTAKE_TEMPLATE_FIELDS.items()
        if SOURCE_COMBINATION_INTAKE_FIELD in declared
    ]
    every = [field for declared in USE_CASE_INTAKE_TEMPLATE_FIELDS.values() for field in declared]

    assert named == ["14. Access and consumption"]
    assert every.count(SOURCE_COMBINATION_INTAKE_FIELD) == 1
    assert every.count(CONSUMED_FIELD_NULLABILITY_INTAKE_FIELD) == 1


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: intermediate(provenance=None), "an intermediate result requires recorded provenance"),
        (lambda: build_route(provenance=None), "a build route requires recorded provenance"),
        (lambda: scenario(provenance=None), "a scenario requires recorded provenance"),
        (lambda: authority(provenance=None), "an authority requires recorded provenance"),
        (lambda: answered(provenance=None), "a condition requires recorded provenance"),
        (lambda: unanswered(provenance=None), "a condition requires recorded provenance"),
        (lambda: intake_artefact(provenance=None), "an intake artefact requires recorded provenance"),
        (
            lambda: consumer_dependency(provenance=None),
            "a consumer dependency requires recorded provenance",
        ),
        (
            lambda: source_combination(provenance=None),
            "a source combination requires recorded provenance",
        ),
    ],
)
def test_every_new_fact_kind_without_provenance_is_refused(build, message):
    with pytest.raises(EngagementError, match=message):
        build()


def test_every_well_formed_new_fact_carries_its_provenance():
    assert intermediate().provenance.artefact.kind is ReferenceKind.INTAKE_ARTEFACT
    assert build_route().provenance.status is FactStatus.EXTRACTED
    assert scenario().provenance.extracted_by.identity == "intake-coworker"
    assert authority().provenance.locator.position == SAFE_POSITION
    assert answered().provenance.status is FactStatus.EXTRACTED
    assert intake_artefact().provenance.artefact.identifier == "order-extract-workbook"
    assert consumer_dependency().provenance.status is FactStatus.EXTRACTED
    assert source_combination().provenance.locator.position == SAFE_POSITION


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: intermediate(result_id=" "), "intermediate result identity is required"),
        (lambda: intermediate(description=" "), "intermediate result description is required"),
        (lambda: intermediate(evidence_owner="the analyst"), "must name an evidence owner"),
        (lambda: intermediate(origin="a capture of the old run"), "must name a declared origin"),
        (lambda: intermediate(continuity="continuity"), "declared continuity label"),
        (lambda: build_route(segment_id=" "), "segment identity is required"),
        (lambda: build_route(route="generated"), "known build route"),
        (lambda: build_route(target_shape=" "), "target shape is required"),
        (lambda: build_route(layer=" "), "layer label is required"),
        (lambda: build_route(route=BuildRoute.GENERATED, product_domain=" "), "product domain is required"),
        (lambda: authority(role="accepting"), "known role"),
        (lambda: authority(actor="the sponsor"), "an authority must name an actor"),
        (
            lambda: authority(role=AuthorityRole.EVIDENCE_OWNER, actor=human("data-owner"), subject=" "),
            "authority subject is required",
        ),
        (lambda: ConditionOverride(value=" ", author=human()), "override value is required"),
        (lambda: answered(key="retention_window"), "declared condition key"),
        (lambda: answered(state="declared"), "whether it was answered"),
        (lambda: answered(value=" "), "condition value is required"),
        (lambda: unanswered(override="two years"), "must be a declared override"),
        (lambda: intake_artefact(artefact=None), "intake_artefact identity"),
        (lambda: intake_artefact(classification=" "), "artefact classification is required"),
        (lambda: intake_artefact(locator=" "), "artefact locator is required"),
        (lambda: consumer_dependency(provider=None), "providing use_case identity"),
        (
            lambda: consumer_dependency(provider=reference(ReferenceKind.USE_CASE_VERSION, "uc-1-v1")),
            "providing use_case identity",
        ),
        (lambda: consumer_dependency(product_id=" "), "consumed product identity is required"),
        (
            lambda: consumer_dependency(expected_fields=[consumed_field()]),
            "the expected fields of a consumed product must be recorded in a tuple",
        ),
        (
            lambda: consumer_dependency(expected_fields=("customer_id",)),
            "declares consumed field expectations",
        ),
        (lambda: consumed_field(field_id=" "), "consumed field identity is required"),
        (lambda: consumed_field(nullable="yes"), "whether it can be empty"),
        (lambda: source_combination(segment_id=" "), "segment identity is required"),
        (lambda: source_combination(method="merge"), "known combination method"),
        (
            lambda: source_combination(sources=["customer-reference", "order-extract"]),
            "the sources of a combination must be recorded in a tuple",
        ),
        (
            lambda: source_combination(sources=("order-extract",)),
            "names the two or more sources it combines",
        ),
        (lambda: source_combination(keys=()), "must name the keys it merges its sources on"),
        (
            lambda: source_combination(keys=("customer_id", "customer_id")),
            "the keys of a merge names each entry once",
        ),
        (lambda: source_combination(join=None), "a merge must declare which rows it keeps"),
        (lambda: source_combination(join="inner"), "a merge must declare which rows it keeps"),
        (lambda: union(keys=("customer_id",)), "only a merge names the keys it merges on"),
        (
            lambda: union(join=CombinationJoin.INNER),
            "only a merge declares which rows it keeps",
        ),
    ],
)
def test_an_incomplete_or_wrongly_typed_new_declaration_is_refused(build, message):
    with pytest.raises(EngagementError, match=message):
        build()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"intermediate_results": ("settled orders",)}, "declared intermediate results"),
        ({"build_routes": ("generated",)}, "declared build routes"),
        ({"scenarios": ("case-normal-day",)}, "declared scenario references"),
        ({"authorities": ("the sponsor",)}, "declared authorities"),
        ({"conditions": ("retention",)}, "declared conditions"),
        ({"intake_artefacts": ("workbook",)}, "declared intake artefacts"),
        ({"consumer_dependencies": ("settled-orders",)}, "declared consumer dependencies"),
        ({"source_combinations": ("merge",)}, "declared source combinations"),
        (
            {"intermediate_results": (intermediate(), intermediate())},
            "intermediate result identities must be unique",
        ),
    ],
)
def test_a_use_case_holding_an_undeclared_new_fact_is_refused(changes, message):
    with pytest.raises(EngagementError, match=message):
        UseCase(identity=reference(ReferenceKind.USE_CASE, "uc-1"), header=header(), **changes)


# The lineage spans and the acceptance boundaries cut over them.


def projection(identifier: str = "projection-cut-1") -> ImmutableReference:
    return reference(ReferenceKind.READINESS_PROJECTION, identifier)


def package(identifier: str = "package-settled-orders") -> ImmutableReference:
    return reference(ReferenceKind.APPROVED_WORK, identifier)


def coverage(**overrides) -> CoverageStatement:
    declared = {
        "covered_segments": ("daily-order-report",),
        "covered_outputs": ("daily-order-report",),
    }
    declared.update(overrides)
    return CoverageStatement(**declared)


def version(**overrides) -> Version:
    declared = {
        "identity": reference(ReferenceKind.USE_CASE_VERSION, "uc-order-volume-v1"),
        "coverage": coverage(),
        "readiness_projection": projection(),
    }
    declared.update(overrides)
    return Version(**declared)


def span(**overrides) -> Segment:
    declared = {
        "segment_id": "daily-order-report",
        "sources": ("order-extract",),
        "passes_through": (),
        "reaches": SegmentBoundary.TARGET_OUTPUT,
    }
    declared.update(overrides)
    return Segment(**declared)


def one_span_use_case() -> UseCase:
    """One declared input reaching one declared output."""
    return opened().record_dataset(dataset()).record_target_output(target_output())


def chained_use_case() -> UseCase:
    """Two named steps, the first kept as a checkpoint, then the declared output."""
    return (
        opened()
        .record_dataset(dataset())
        .record_intermediate_result(intermediate())
        .record_intermediate_result(intermediate(result_id="enriched-orders", checkpoint_candidate=False))
        .record_target_output(target_output())
        .record_build_route(build_route(segment_id="settled-orders"))
        .record_build_route(build_route(segment_id="daily-order-report", route=BuildRoute.EXISTING))
    )


def joining_use_case() -> UseCase:
    """Two declared inputs joining into one declared output."""
    return (
        opened()
        .record_dataset(dataset())
        .record_dataset(dataset(placeholder_id="customer-reference", role=DatasetRole.REFERENCE))
        .record_target_output(target_output())
    )


def recorded_in_order(placeholders: tuple[str, ...], outputs: tuple[str, ...]) -> UseCase:
    """One use case whose inputs and outputs were recorded in the given order."""
    subject = opened()
    for placeholder_id in placeholders:
        subject = subject.record_dataset(dataset(placeholder_id=placeholder_id))
    subject = subject.record_intermediate_result(intermediate())
    for output_id in outputs:
        subject = subject.record_target_output(target_output(output_id=output_id))
    return subject


def test_one_declared_input_and_one_declared_output_derive_one_span():
    spans = one_span_use_case().segments()

    assert len(spans) == 1
    assert spans[0].segment_id == "daily-order-report"
    assert spans[0].sources == ("order-extract",)
    assert spans[0].passes_through == ()
    assert spans[0].reaches is SegmentBoundary.TARGET_OUTPUT
    assert spans[0].route is None


def test_a_chain_through_two_steps_breaks_at_the_checkpoint_and_carries_each_route():
    spans = chained_use_case().segments()

    assert [item.segment_id for item in spans] == ["settled-orders", "daily-order-report"]
    assert (spans[0].sources, spans[0].passes_through) == (("order-extract",), ())
    assert spans[0].reaches is SegmentBoundary.INTERMEDIATE_RESULT
    assert spans[0].route.segment_id == "settled-orders"
    assert spans[0].route.route is BuildRoute.ENGINEERED
    assert (spans[1].sources, spans[1].passes_through) == (("settled-orders",), ("enriched-orders",))
    assert spans[1].reaches is SegmentBoundary.TARGET_OUTPUT
    assert spans[1].route.route is BuildRoute.EXISTING


def test_two_declared_inputs_join_into_one_span():
    spans = joining_use_case().segments()

    assert len(spans) == 1
    assert spans[0].sources == ("customer-reference", "order-extract")
    assert spans[0].segment_id == "daily-order-report"
    assert spans[0].reaches is SegmentBoundary.TARGET_OUTPUT


def test_the_derivation_is_the_same_twice_and_under_a_shuffled_recording_order():
    first = recorded_in_order(
        ("order-extract", "customer-reference"), ("daily-order-report", "weekly-order-report")
    )
    second = recorded_in_order(
        ("customer-reference", "order-extract"), ("weekly-order-report", "daily-order-report")
    )

    assert first.segments() == first.segments()
    assert first.segments() == second.segments()
    assert [item.segment_id for item in first.segments()] == [
        "settled-orders",
        "daily-order-report",
        "weekly-order-report",
    ]
    assert first.segments()[0].sources == ("customer-reference", "order-extract")
    assert first.segments()[1].sources == first.segments()[2].sources == ("settled-orders",)


def test_a_use_case_with_nothing_declared_yet_derives_no_span():
    assert opened().segments() == ()
    assert opened().record_dataset(dataset()).segments() == ()
    assert (
        opened()
        .record_dataset(dataset())
        .record_intermediate_result(intermediate(checkpoint_candidate=False))
        .segments()
        == ()
    )


def test_a_step_that_is_not_a_checkpoint_stays_inside_the_span_that_spans_it():
    subject = (
        opened()
        .record_dataset(dataset())
        .record_intermediate_result(intermediate(checkpoint_candidate=False))
        .record_target_output(target_output())
    )

    spans = subject.segments()

    assert len(spans) == 1
    assert spans[0].passes_through == ("settled-orders",)
    assert spans[0].sources == ("order-extract",)


def test_a_step_after_the_last_checkpoint_before_two_outputs_is_refused_as_two_readings():
    subject = (
        opened()
        .record_dataset(dataset())
        .record_intermediate_result(intermediate(checkpoint_candidate=False))
        .record_target_output(target_output())
        .record_target_output(target_output(output_id="weekly-order-report"))
    )

    with pytest.raises(EngagementError, match="could belong to more than one target output"):
        subject.segments()

    kept = subject.record_intermediate_result(
        intermediate(result_id="reconciled-orders", checkpoint_candidate=True)
    )
    assert [item.segment_id for item in kept.segments()] == [
        "reconciled-orders",
        "daily-order-report",
        "weekly-order-report",
    ]


@pytest.mark.parametrize("checkpoint", [True, False])
def test_a_step_and_a_target_output_sharing_a_name_is_refused_as_two_readings(checkpoint):
    subject = (
        opened()
        .record_dataset(dataset())
        .record_intermediate_result(
            intermediate(result_id="daily-order-report", checkpoint_candidate=checkpoint)
        )
        .record_target_output(target_output())
    )

    with pytest.raises(EngagementError, match="share one span name"):
        subject.segments()

    distinct = (
        opened()
        .record_dataset(dataset())
        .record_intermediate_result(intermediate(checkpoint_candidate=checkpoint))
        .record_target_output(target_output())
    )
    spans = distinct.segments()

    assert all(item.segment_id not in item.passes_through for item in spans)
    assert [item.segment_id for item in spans] == (
        ["settled-orders", "daily-order-report"] if checkpoint else ["daily-order-report"]
    )


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: span(segment_id=" "), "span identity is required"),
        (lambda: span(sources=["order-extract"]), "the sources of a span must be recorded in a tuple"),
        (lambda: span(sources=("order-extract", "order-extract")), "names each entry once"),
        (lambda: span(sources=(None,)), "the sources of a span names each entry in text"),
        (lambda: span(sources=(" ",)), "the sources of a span entry is required"),
        (lambda: span(passes_through=["settled-orders"]), "the steps a span passes must be recorded in a tuple"),
        (lambda: span(reaches="target_output"), "what kind of boundary it reaches"),
        (lambda: span(route="engineered"), "a span carries a declared build route"),
        (lambda: span(route=build_route()), "a span carries the build route declared for it"),
        (lambda: span(combination="merge"), "a span carries a declared source combination"),
        (
            lambda: span(combination=source_combination(segment_id="weekly-order-report")),
            "a span carries the source combination declared for it",
        ),
        (
            lambda: span(combination=source_combination()),
            "a combination names a source the span does not read: customer-reference",
        ),
    ],
)
def test_a_self_contradicting_span_is_refused(build, message):
    with pytest.raises(EngagementError, match=message):
        build()


def test_a_span_carries_the_route_declared_under_its_own_name():
    declared = build_route(segment_id="daily-order-report", route=BuildRoute.GENERATED, product_domain="orders")

    assert span(route=declared).route.product_domain == "orders"
    assert span().route is None


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: coverage(covered_segments=()), "a version covers at least one span"),
        (
            lambda: coverage(covered_segments=("a",), covered_outputs=(), segments_outside=("a",)),
            "names one span inside and outside",
        ),
        (lambda: coverage(covered_segments=("a", "a")), "the spans a version covers names each entry once"),
        (lambda: coverage(covered_segments=["a"]), "the spans a version covers must be recorded in a tuple"),
        (
            lambda: coverage(covered_outputs=["daily-order-report"]),
            "the outputs a version covers must be recorded in a tuple",
        ),
        (
            lambda: coverage(segments_outside=["other"]),
            "the spans a version leaves outside must be recorded in a tuple",
        ),
    ],
)
def test_a_self_contradicting_coverage_statement_is_refused(build, message):
    with pytest.raises(EngagementError, match=message):
        build()


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: version(identity=None), "use_case_version identity"),
        (
            lambda: version(identity=reference(ReferenceKind.USE_CASE, "uc-order-volume")),
            "use_case_version identity",
        ),
        (lambda: version(coverage=("daily-order-report",)), "must carry a coverage statement"),
        (lambda: version(readiness_projection=None), "reference the projection it was cut on"),
        (
            lambda: version(readiness_projection=reference(ReferenceKind.BUILD_EVIDENCE, "build-1")),
            "reference the projection it was cut on",
        ),
        (
            lambda: version(scenario_case_versions=[identity("case-normal-day")]),
            "the scenario cases of a version must be recorded in a tuple",
        ),
        (lambda: version(scenario_case_versions=("case-normal-day",)), "name each scenario case by identity"),
        (
            lambda: version(
                scenario_case_versions=(Identity(identifier="case-normal-day", version=" ", digest="d"),)
            ),
            "scenario case version is required",
        ),
        (
            lambda: version(scenario_case_versions=(identity("case-normal-day"), identity("case-normal-day"))),
            "names each scenario case once",
        ),
        (lambda: version(packages=[package()]), "the packages of a version must be recorded in a tuple"),
        (lambda: version(packages=("package-1",)), "approved_work identity"),
        (
            lambda: version(packages=(reference(ReferenceKind.BUILD_EVIDENCE, "build-1"),)),
            "approved_work identity",
        ),
        (lambda: version(packages=(package(), package())), "names each package once"),
        (lambda: version(conditions=[answered()]), "the conditions of a version must be recorded in a tuple"),
        (lambda: version(conditions=("retention",)), "a version snapshot holds declared conditions"),
        (lambda: version(conditions=(answered(), answered())), "holds each condition once"),
        (lambda: version(suggested_disposition=" "), "suggested disposition is required"),
    ],
)
def test_a_self_contradicting_version_is_refused(build, message):
    with pytest.raises(EngagementError, match=message):
        build()


def test_a_version_carries_the_spans_outputs_cases_packages_conditions_and_projection_digest():
    subject = chained_use_case().record_scenario(scenario()).record_condition(answered())
    cut = subject.cut_version(
        version(
            coverage=CoverageStatement(
                covered_segments=("settled-orders", "daily-order-report"),
                covered_outputs=("daily-order-report",),
            ),
            scenario_case_versions=(identity("case-normal-day"),),
            packages=(package(),),
            conditions=(answered(),),
            suggested_disposition="the second span rests on a generated input",
        )
    ).current_version

    assert cut.covered_segments == ("settled-orders", "daily-order-report")
    assert cut.covered_outputs == ("daily-order-report",)
    assert cut.segments_outside == ()
    assert cut.scenario_case_versions == (identity("case-normal-day"),)
    assert cut.scenario_case_versions[0].version == "v1"
    assert cut.packages[0].kind is ReferenceKind.APPROVED_WORK
    assert cut.conditions[0].effective_value == "seven years of settled orders"
    assert cut.readiness_projection.kind is ReferenceKind.READINESS_PROJECTION
    assert cut.readiness_digest == "digest-projection-cut-1"
    assert cut.suggested_disposition == "the second span rests on a generated input"


def test_a_one_span_version_is_cut_and_a_later_narrowing_version_leaves_the_first_as_cut():
    subject = chained_use_case()
    wide = version(
        coverage=CoverageStatement(
            covered_segments=("settled-orders", "daily-order-report"),
            covered_outputs=("daily-order-report",),
        )
    )
    narrow = version(
        identity=reference(ReferenceKind.USE_CASE_VERSION, "uc-order-volume-v2"),
        coverage=CoverageStatement(
            covered_segments=("settled-orders",), segments_outside=("daily-order-report",)
        ),
        readiness_projection=projection("projection-cut-2"),
    )

    narrowed = subject.cut_version(wide).cut_version(narrow)
    single = one_span_use_case().cut_version(version())

    assert narrowed.current_version is narrow
    assert narrowed.versions[0] is wide
    assert narrowed.versions[0].covered_segments == ("settled-orders", "daily-order-report")
    assert narrow.covered_outputs == ()
    assert narrow.segments_outside == ("daily-order-report",)
    assert single.current_version.covered_segments == ("daily-order-report",)
    assert single.current_version.segments_outside == ()


def test_a_cut_version_cannot_be_changed_afterwards():
    subject = one_span_use_case().cut_version(version())
    cut = subject.current_version

    with pytest.raises(FrozenInstanceError):
        cut.readiness_projection = projection("projection-cut-other")
    with pytest.raises(FrozenInstanceError):
        cut.coverage.covered_segments = ("weekly-order-report",)
    with pytest.raises(FrozenInstanceError):
        cut.coverage.segments_outside = ("daily-order-report",)

    assert cut.readiness_digest == "digest-projection-cut-1"
    assert cut.covered_segments == ("daily-order-report",)
    assert cut.segments_outside == ()
    assert subject.current_version is cut


def test_a_second_version_under_a_cut_identity_is_refused():
    subject = one_span_use_case().cut_version(version())

    with pytest.raises(EngagementError, match="version identities must be unique"):
        subject.cut_version(version(readiness_projection=projection("projection-cut-2")))


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (
            lambda: one_span_use_case().cut_version(
                version(coverage=CoverageStatement(covered_segments=("settled-orders",)))
            ),
            "covers a span the use case does not have",
        ),
        (
            lambda: chained_use_case().cut_version(
                version(
                    coverage=CoverageStatement(
                        covered_segments=("daily-order-report",), covered_outputs=("daily-order-report",)
                    )
                )
            ),
            "must name every span the version leaves outside it",
        ),
        (
            lambda: chained_use_case().cut_version(
                version(
                    coverage=CoverageStatement(
                        covered_segments=("daily-order-report",),
                        covered_outputs=("daily-order-report",),
                        segments_outside=("enriched-orders",),
                    )
                )
            ),
            "must name every span the version leaves outside it",
        ),
        (
            lambda: one_span_use_case().cut_version(
                version(coverage=CoverageStatement(covered_segments=("daily-order-report",)))
            ),
            "must name every target output its spans reach and no other",
        ),
        (
            lambda: chained_use_case().cut_version(
                version(
                    coverage=CoverageStatement(
                        covered_segments=("settled-orders",),
                        covered_outputs=("daily-order-report",),
                        segments_outside=("daily-order-report",),
                    )
                )
            ),
            "must name every target output its spans reach and no other",
        ),
        (
            lambda: one_span_use_case().cut_version(
                version(scenario_case_versions=(identity("case-normal-day"),))
            ),
            "names a scenario case the use case does not reference",
        ),
        (
            lambda: one_span_use_case()
            .record_scenario(scenario())
            .cut_version(
                version(
                    scenario_case_versions=(
                        Identity(identifier="case-normal-day", version="v2", digest="digest-case-normal-day"),
                    )
                )
            ),
            "names a scenario case the use case does not reference",
        ),
        (
            lambda: UseCase(
                identity=reference(ReferenceKind.USE_CASE, "uc-1"), header=header(), versions=("v1",)
            ),
            "versions must be declared versions",
        ),
    ],
)
def test_a_version_that_contradicts_the_use_case_is_refused(build, message):
    with pytest.raises(EngagementError, match=message):
        build()


def test_verification_reads_the_scenarios_of_the_current_version_only():
    subject = (
        one_span_use_case()
        .record_scenario(scenario("case-normal-day"))
        .record_scenario(scenario("case-late-rows"))
        .record_scenario_result(scenario_result("case-normal-day", VerificationStatus.FAIL))
        .record_scenario_result(scenario_result("case-late-rows"))
    )
    first = subject.cut_version(version(scenario_case_versions=(identity("case-normal-day"),)))
    second = first.cut_version(
        version(
            identity=reference(ReferenceKind.USE_CASE_VERSION, "uc-order-volume-v2"),
            readiness_projection=projection("projection-cut-2"),
            scenario_case_versions=(identity("case-late-rows"),),
        )
    )

    with pytest.raises(EngagementError, match="passing result for every scenario"):
        first.verify(human())

    verified = second.verify(human())

    assert verified.state is UseCaseState.VERIFIED
    assert verified.current_version.scenario_case_versions == (identity("case-late-rows"),)
    assert [result.status for result in verified.scenario_results] == [
        VerificationStatus.FAIL,
        VerificationStatus.PASS,
    ]


def test_a_version_naming_a_scenario_with_no_recorded_result_cannot_be_verified():
    subject = (
        one_span_use_case()
        .record_scenario(scenario("case-normal-day"))
        .record_scenario(scenario("case-late-rows"))
        .record_scenario_result(scenario_result("case-normal-day"))
        .cut_version(
            version(scenario_case_versions=(identity("case-normal-day"), identity("case-late-rows")))
        )
    )

    with pytest.raises(EngagementError, match="requires a recorded scenario result"):
        subject.verify(human())

    covered = subject.record_scenario_result(scenario_result("case-late-rows")).verify(human())
    assert covered.state is UseCaseState.VERIFIED


def test_a_use_case_with_no_version_still_reads_every_recorded_result():
    subject = one_span_use_case().record_scenario_result(scenario_result("case-normal-day"))

    assert subject.current_version is None
    assert subject.verify(human()).state is UseCaseState.VERIFIED

    with pytest.raises(EngagementError, match="passing result for every scenario"):
        subject.record_scenario_result(
            scenario_result("case-late-rows", VerificationStatus.FAIL)
        ).verify(human())


def test_no_span_or_version_carries_a_state_that_stops_a_use_case():
    declared = {field.name for record in (Segment, CoverageStatement, Version) for field in fields(record)}
    stopping = {
        "block",
        "blocked",
        "blocking",
        "blocks",
        "deferred",
        "gated",
        "halted",
        "paused",
        "stalled",
        "suspended",
        "waiting",
    }

    assert "state" not in declared
    assert tokens(" ".join(declared)) & stopping == set()
    assert [boundary.value for boundary in SegmentBoundary] == ["intermediate_result", "target_output"]
    # A missing fact narrows what can be derived; it never refuses the record.
    assert opened().segments() == ()
    assert opened().state is UseCaseState.OPENED
    assert one_span_use_case().cut_version(version()).state is UseCaseState.OPENED
