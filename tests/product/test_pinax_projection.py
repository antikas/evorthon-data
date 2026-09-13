"""Use-case parents, gap items, iteration items and cross-use-case blocks in the tracker.

The projection is proved against the released command on disposable repositories
under the temporary tree, and its refusals are proved against a fake released
command so each one is shown to happen before the tracker is touched.
"""
# evorthon-verifies: EVD-README-025
# evorthon-verifies: EVD-README-015
# evorthon-verifies: EVD-README-007
import json
import shutil
import subprocess
from copy import deepcopy
from dataclasses import replace
from enum import Enum
from pathlib import Path
from types import SimpleNamespace

import pytest

from evorthon_data.delivery.pinax import (
    CAPTION_LIMIT,
    CHANGED_REASON,
    DROPPED_REASON,
    ITERATION_MARKER,
    PACKAGE_MARKER,
    PARENT_REMAINDER,
    REMEDY_MARKER,
    ApprovedContractIdentity,
    ApprovedPackage,
    ApprovedRemedy,
    PinaxContractProjector,
    PinaxProjectionError,
    SegmentIteration,
    SubprocessPinaxRunner,
    UseCaseScope,
    _bind_edges,
)
from evorthon_data.engagement import ReferenceKind, UseCase
from evorthon_data.engagement.use_case import (
    AuthorityRole,
    AvailabilityState,
    ConsumerDependency,
    CoverageStatement,
    DatasetAvailability,
    Version,
)
from evorthon_data.readiness import (
    CaseExpectedOutput,
    CaseFacts,
    FactKind,
    ReadinessGap,
    ReadinessProjection,
    project_readiness,
    projection_digest,
    suggested_item_title,
)
from evorthon_data.verification.core.canonical import canonical_digest
from evorthon_data.verification.domain.contracts import (
    AdviserConfidence,
    DatasetProvenance,
    DatasetRole,
    DiagnosticLocalisation,
    DisclosureDecision,
    EvidenceReference,
    ExpectedOutputOrigin,
    FaultClass,
    FaultRecord,
    Identity,
    LocalisationStatus,
    RemediationAdvice,
    RemediationDisposition,
)
from evorthon_data.verification.enforcement.privacy import gate_fault_packet
from evorthon_data.verification.workflows.adviser import (
    ADVISER_REPLY_FORM,
    AdviserHypothesis,
    AdviserReply,
    read_adviser_reply,
)
from evorthon_data.verification.workflows.remediation import (
    DecidingActor,
    HumanDisposition,
    RemediationActorKind,
    record_remediation_decision,
)

# The use-case aggregate's own fixture builders. Reusing them keeps one owner for
# the shape of a recorded use case.
from test_use_case_aggregate import (
    authority,
    dataset,
    header,
    human,
    identity,
    provenance,
    reference,
    scenario,
    target_output,
)


ACTOR = "test@evorthon"
ENGAGEMENT = "eng-customer-service"
PRODUCER = "uc-order-volume"
CONSUMER = "uc-staffing-plan"
PRODUCT = "daily-order-report"
STAFFING = "staffing-plan"
INPUT_ID = "order-extract"
REFERENCE_ID = "product-master"
CASE = "case-normal-day"
BUILD_PACKAGE = "build-report-pipeline"
PUBLISH_PACKAGE = "publish-report"
PRODUCER_LOOP = "first-report-loop"
CONSUMER_LOOP = "first-staffing-loop"
# The machine routes a reference and a caption must refuse, assembled from
# character codes so this file carries no such route. The shapes are declared
# once for the whole product, so this adapter refuses every form the use-case
# aggregate, the privacy gate and the public-candidate scan refuse.
DRIVE_ROUTE = "C" + chr(58) + "/orders"
NETWORK_ROUTE = chr(92) * 2 + "estate" + chr(92) + "owners"
HOME_ROUTE = "/" + "home" + "/analyst/owners"
FILE_ADDRESS_ROUTE = "file" + chr(58) + "//estate/owners"
WEB_ADDRESS_ROUTE = "http" + chr(58) + "//estate.example/owners"
TRAVERSAL_ROUTE = chr(46) * 2 + "/estate/owners"
BACKSLASH_ROUTE = "estate" + chr(92) + "owners"
CAPTION_ROUTES = (
    DRIVE_ROUTE,
    NETWORK_ROUTE,
    HOME_ROUTE,
    FILE_ADDRESS_ROUTE,
    WEB_ADDRESS_ROUTE,
    TRAVERSAL_ROUTE,
    BACKSLASH_ROUTE,
)


class InventedKind(str, Enum):
    """A gap kind this adapter has no wording for."""

    INVENTED = "invented"


def absent() -> DatasetAvailability:
    return DatasetAvailability(state=AvailabilityState.UNOBTAINABLE)


def in_hand(dataset_id: str) -> DatasetAvailability:
    return DatasetAvailability(state=AvailabilityState.OBTAINED, dataset=identity(dataset_id))


def producer_use_case(*, use_case_id: str = PRODUCER) -> UseCase:
    """A use case that reaches one target output and delivers two approved packages."""
    subject = UseCase.open(reference(ReferenceKind.USE_CASE, use_case_id), header())
    subject = subject.record_target_output(target_output(defined_by=identity("orders-specification")))
    subject = subject.record_dataset(dataset())
    subject = subject.record_dataset(
        dataset(placeholder_id=REFERENCE_ID, role=DatasetRole.REFERENCE, availability=absent())
    )
    subject = subject.record_authority(authority())
    return subject.cut_version(
        Version(
            identity=reference(ReferenceKind.USE_CASE_VERSION, f"{use_case_id}-v1"),
            coverage=CoverageStatement(covered_segments=(PRODUCT,), covered_outputs=(PRODUCT,)),
            readiness_projection=reference(ReferenceKind.READINESS_PROJECTION, f"readiness-{use_case_id}"),
            packages=(
                reference(ReferenceKind.APPROVED_WORK, BUILD_PACKAGE),
                reference(ReferenceKind.APPROVED_WORK, PUBLISH_PACKAGE),
            ),
        )
    )


def consumer_use_case(*, sources_product: bool = True, product_id: str = PRODUCT) -> UseCase:
    """A use case that reads another use case's product at a pinned major version."""
    subject = UseCase.open(reference(ReferenceKind.USE_CASE, CONSUMER), header())
    subject = subject.record_target_output(
        target_output(output_id=STAFFING, defined_by=identity("staffing-specification"))
    )
    sourced = PRODUCT if sources_product else "roster-extract"
    subject = subject.record_dataset(
        dataset(placeholder_id=sourced, availability=in_hand(f"{sourced}-2026-09"))
    )
    subject = subject.record_authority(authority())
    return subject.record_consumer_dependency(
        ConsumerDependency(
            provider=reference(ReferenceKind.USE_CASE, PRODUCER),
            product_id=product_id,
            major_version="v1",
            provenance=provenance(),
        )
    )


def solo_use_case() -> UseCase:
    """One use case with a single span, one scenario and one outstanding fact."""
    subject = UseCase.open(reference(ReferenceKind.USE_CASE, PRODUCER), header())
    subject = subject.record_target_output(target_output(defined_by=identity("orders-specification")))
    subject = subject.record_dataset(dataset())
    subject = subject.record_authority(authority())
    return subject.record_scenario(scenario(CASE))


def producer_scope(**overrides) -> UseCaseScope:
    subject = overrides.pop("use_case", None) or producer_use_case()
    declared = {
        "use_case": subject,
        "readiness": project_readiness(subject, overrides.pop("index", {})),
        "packages": (
            ApprovedPackage(BUILD_PACKAGE, "build the report pipeline"),
            ApprovedPackage(PUBLISH_PACKAGE, "publish the report", depends_on=(BUILD_PACKAGE,)),
        ),
        "iterations": (SegmentIteration(PRODUCER_LOOP, PRODUCT, "build and verify the report span"),),
    }
    declared.update(overrides)
    return UseCaseScope(**declared)


def consumer_scope(**overrides) -> UseCaseScope:
    subject = overrides.pop("use_case", None) or consumer_use_case()
    declared = {
        "use_case": subject,
        "readiness": project_readiness(subject, overrides.pop("index", {})),
        "iterations": (SegmentIteration(CONSUMER_LOOP, STAFFING, "build and verify the staffing span"),),
    }
    declared.update(overrides)
    return UseCaseScope(**declared)


def solo_scope(**overrides) -> UseCaseScope:
    subject = overrides.pop("use_case", None) or solo_use_case()
    declared = {
        "use_case": subject,
        "readiness": project_readiness(subject, overrides.pop("index", {})),
        "iterations": (SegmentIteration(PRODUCER_LOOP, PRODUCT, "build and verify the report span"),),
    }
    declared.update(overrides)
    return UseCaseScope(**declared)


def solo_titles() -> dict[str, str]:
    prefix = ApprovedContractIdentity(engagement_id=ENGAGEMENT, use_case_id=PRODUCER).title_prefix
    return {
        "prefix": prefix,
        "parent": f"{prefix}{PARENT_REMAINDER}",
        "iteration": f"{prefix}{ITERATION_MARKER}{PRODUCER_LOOP} | build and verify the report span",
        "gap": f"{prefix}{suggested_item_title(FactKind.EXPECTED_OUTPUT, PRODUCT)}",
    }


def satisfied_index() -> dict:
    return {
        identity(CASE): CaseFacts(
            expected_outputs=(
                CaseExpectedOutput(
                    output_id=PRODUCT,
                    provenance=DatasetProvenance.REAL,
                    origin=ExpectedOutputOrigin.MODERNISATION_CAPTURE,
                ),
            )
        )
    }


def pinax_command() -> str:
    command = shutil.which("pinax")
    if command is None or shutil.which("git") is None:
        pytest.skip("Pinax projection tests require the optional delivery extra and Git")
    return command


def initialise_repository(path: Path) -> None:
    path.mkdir()
    git = shutil.which("git")
    if git is None:
        raise AssertionError("pinax_command must verify Git before repository initialisation")
    subprocess.run([git, "init", "--quiet"], cwd=path, check=True, capture_output=True, text=True)


def board(command: str, repository: Path) -> dict:
    completed = subprocess.run(
        [command, "--root", str(repository), "board", "--json"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)["state"]


def add_item(command: str, repository: Path, title: str, *, actor: str) -> str:
    completed = subprocess.run(
        [
            command,
            "--root",
            str(repository),
            "add",
            "--title",
            title,
            "--prefix",
            "evd",
            "--allow-new-prefix",
            "--actor",
            actor,
            "--json",
        ],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)["item_id"]


def run_pinax(command: str, repository: Path, *arguments: str) -> dict:
    completed = subprocess.run(
        [command, "--root", str(repository), *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def live_projector(tmp_path: Path):
    command = pinax_command()
    repository = tmp_path / "delivery"
    initialise_repository(repository)
    return command, repository, PinaxContractProjector(SubprocessPinaxRunner(command), actor=ACTOR)


def typed_edges(state: dict) -> set[tuple[str, str, str]]:
    return {
        (edge_type, edge[0], edge[1])
        for edge_type, edges in state.get("edges", {}).items()
        for edge in edges
    }


def notes_by_item(state: dict) -> dict[str, dict]:
    return {note["item_id"]: note for note in state.get("notes", [])}


class RefusingRunner:
    """A released command that must never be reached."""

    def run(self, arguments, *, repository):
        raise AssertionError(f"the projection must refuse before any tracker command: {arguments!r}")


class FakePinax:
    """A fake released command: items, typed edges, notes and status folded in memory."""

    def __init__(self, *, items=None, edges=None, notes=None, fail_block_once=False):
        self.commands: list[tuple[str, ...]] = []
        self.items: dict[str, dict] = dict(items or {})
        self.edges: dict[str, list[list[str]]] = {
            edge_type: [list(edge) for edge in pairs] for edge_type, pairs in (edges or {}).items()
        }
        self.notes: list[dict] = list(notes or [])
        self.next_item = 1
        self.board_calls = 0
        self.fail_block_once = fail_block_once

    @property
    def state(self) -> dict:
        return {
            "ergon": {"actor": ACTOR, "created_at": "2026-09-03T00:00:00Z"},
            "phases": {
                "init": {
                    "opened_at": "2026-09-03T00:00:00Z",
                    "opened_by": ACTOR,
                    "opened_seq": 1,
                    "status": "open",
                }
            },
            "items": self.items,
            "edges": self.edges,
            "notes": self.notes,
        }

    def add(self, title: str, *, status: str = "queued") -> str:
        item_id = f"evd-{self.next_item}"
        self.next_item += 1
        self.items[item_id] = {"id": item_id, "title": title, "status": status}
        return item_id

    def run(self, arguments, *, repository):
        command = tuple(arguments)
        self.commands.append(command)
        if command[0] == "init":
            return ""
        if command == ("board", "--json"):
            self.board_calls += 1
            self.on_board()
            return json.dumps({"state": self.state})
        if command[0] == "add":
            return json.dumps({"item_id": self.add(command[command.index("--title") + 1])})
        if command[0] == "block":
            if self.fail_block_once:
                self.fail_block_once = False
                raise PinaxProjectionError("injected block interruption")
            self.items[command[-1]].update(status="blocked", gate="scope")
            return json.dumps({})
        if command[:2] == ("note", "add"):
            self.notes.append(
                {
                    "item_id": command[2],
                    "ref": command[command.index("--ref") + 1],
                    "caption": command[command.index("--caption") + 1],
                }
            )
            return json.dumps({})
        if command[:2] == ("dep", "add"):
            edge_type = command[command.index("--type") + 1]
            self.edges.setdefault(edge_type, []).append(
                [command[2], command[command.index("--to") + 1]]
            )
            return json.dumps({})
        raise AssertionError(f"unexpected Pinax command: {command!r}")

    def on_board(self) -> None:
        """Hook for a fake that changes the board between reads."""


@pytest.fixture(scope="module")
def projected_pair(tmp_path_factory):
    """One disposable repository carrying two use-case parents, projected twice."""
    command = pinax_command()
    repository = tmp_path_factory.mktemp("two-use-cases") / "delivery"
    initialise_repository(repository)
    projector = PinaxContractProjector(SubprocessPinaxRunner(command), actor=ACTOR)
    scopes = (producer_scope(), consumer_scope())
    first = projector.project(scopes, repository=repository)
    after_first = board(command, repository)
    second = projector.project(scopes, repository=repository)
    return SimpleNamespace(
        scopes=scopes,
        first=first,
        after_first=after_first,
        second=second,
        after_second=board(command, repository),
    )


def test_two_use_case_parents_get_the_exact_typed_graph_and_project_idempotently(projected_pair):
    first = projected_pair.first
    after_first = projected_pair.after_first

    assert projected_pair.second == first
    assert projected_pair.after_second == after_first
    assert first.stale_gap_items == ()
    projected_producer, projected_consumer = first.use_cases
    packages = dict(projected_producer.package_items)
    producer_gaps = dict(projected_producer.gap_items)
    producer_loops = dict(projected_producer.iteration_items)
    consumer_gaps = dict(projected_consumer.gap_items)
    consumer_loops = dict(projected_consumer.iteration_items)
    reference_gap = producer_gaps[suggested_item_title(FactKind.REFERENCE_DATASET, REFERENCE_ID)]
    expected_gap = producer_gaps[suggested_item_title(FactKind.EXPECTED_OUTPUT, PRODUCT)]
    combination_gap = producer_gaps[suggested_item_title(FactKind.SOURCE_COMBINATION, PRODUCT)]
    staffing_gap = consumer_gaps[suggested_item_title(FactKind.EXPECTED_OUTPUT, STAFFING)]

    assert set(after_first["items"]) == {
        projected_producer.parent_item,
        projected_consumer.parent_item,
        *packages.values(),
        *producer_gaps.values(),
        *producer_loops.values(),
        *consumer_gaps.values(),
        *consumer_loops.values(),
    }
    assert typed_edges(after_first) == {
        ("parent-child", projected_producer.parent_item, packages[BUILD_PACKAGE]),
        ("parent-child", projected_producer.parent_item, packages[PUBLISH_PACKAGE]),
        ("parent-child", projected_producer.parent_item, reference_gap),
        ("parent-child", projected_producer.parent_item, expected_gap),
        ("parent-child", projected_producer.parent_item, combination_gap),
        ("parent-child", projected_producer.parent_item, producer_loops[PRODUCER_LOOP]),
        ("parent-child", projected_consumer.parent_item, staffing_gap),
        ("parent-child", projected_consumer.parent_item, consumer_loops[CONSUMER_LOOP]),
        ("blocks", packages[BUILD_PACKAGE], packages[PUBLISH_PACKAGE]),
        ("blocks", reference_gap, producer_loops[PRODUCER_LOOP]),
        ("blocks", expected_gap, producer_loops[PRODUCER_LOOP]),
        ("blocks", combination_gap, producer_loops[PRODUCER_LOOP]),
        ("blocks", staffing_gap, consumer_loops[CONSUMER_LOOP]),
        ("blocks", producer_loops[PRODUCER_LOOP], consumer_loops[CONSUMER_LOOP]),
    }
    for gated in (packages[PUBLISH_PACKAGE], producer_loops[PRODUCER_LOOP], consumer_loops[CONSUMER_LOOP]):
        assert after_first["items"][gated]["status"] == "blocked"
        assert after_first["items"][gated]["gate"] == "scope"
    assert after_first["items"][projected_producer.parent_item]["status"] == "queued"


def test_each_gap_item_is_titled_and_noted_from_the_readiness_reading(projected_pair):
    result = projected_pair.first
    state = projected_pair.after_first
    notes = notes_by_item(state)
    projected_producer, projected_consumer = result.use_cases

    for projected, scope in zip(result.use_cases, projected_pair.scopes):
        digest = projection_digest(scope.readiness)
        identifier = projected.identity.use_case_id
        for suggested, item_id in projected.gap_items:
            assert state["items"][item_id]["title"] == projected.identity.title_prefix + suggested
            assert notes[item_id]["ref"] == f"koine://use-case/{identifier}/readiness/{digest}"
            assert len(notes[item_id]["caption"]) <= CAPTION_LIMIT
    producer_gaps = dict(projected_producer.gap_items)
    assert notes[producer_gaps[suggested_item_title(FactKind.REFERENCE_DATASET, REFERENCE_ID)]]["caption"] == (
        "gap kind reference dataset; suggested owner data-owner; synthetic fill yes"
    )
    assert notes[producer_gaps[suggested_item_title(FactKind.EXPECTED_OUTPUT, PRODUCT)]]["caption"] == (
        "gap kind expected output; suggested owner acceptance-authority; synthetic fill yes"
    )
    assert notes[producer_gaps[suggested_item_title(FactKind.SOURCE_COMBINATION, PRODUCT)]]["caption"] == (
        "gap kind source combination; suggested owner acceptance-authority; synthetic fill no"
    )
    assert set(notes) == {item_id for projected in result.use_cases for _, item_id in projected.gap_items}


def test_a_gap_with_no_span_hangs_on_the_use_case_parent_alone(tmp_path):
    command, repository, projector = live_projector(tmp_path)
    subject = UseCase.open(reference(ReferenceKind.USE_CASE, PRODUCER), header())
    subject = subject.record_dataset(dataset())
    subject = subject.record_authority(authority())
    scope = UseCaseScope(use_case=subject, readiness=project_readiness(subject, {}))

    result = projector.project((scope,), repository=repository)
    state = board(command, repository)
    projected = result.use_cases[0]
    gap_item = dict(projected.gap_items)[suggested_item_title(FactKind.OUTPUT_DEFINITION, PRODUCER)]

    assert projected.iteration_items == ()
    assert typed_edges(state) == {("parent-child", projected.parent_item, gap_item)}
    assert state["items"][gap_item]["status"] == "queued"
    assert notes_by_item(state)[gap_item]["caption"] == (
        "gap kind output definition; suggested owner acceptance-authority; synthetic fill no"
    )


def test_a_changed_reading_reports_open_gap_items_without_mutating_the_tracker(tmp_path):
    command, repository, projector = live_projector(tmp_path)
    first = projector.project((solo_scope(),), repository=repository)
    projected = board(command, repository)
    gap_item = dict(first.use_cases[0].gap_items)[suggested_item_title(FactKind.EXPECTED_OUTPUT, PRODUCT)]

    answered = projector.project((solo_scope(index=satisfied_index()),), repository=repository)

    assert board(command, repository) == projected
    assert answered.use_cases[0].gap_items == ()
    assert [(entry.item_id, entry.reason) for entry in answered.stale_gap_items] == [
        (gap_item, DROPPED_REASON)
    ]

    moved = solo_use_case().record_authority(
        authority(role=AuthorityRole.EVIDENCE_OWNER, actor=human("evidence-owner"), subject=PRODUCT)
    )
    changed = projector.project((solo_scope(use_case=moved),), repository=repository)

    assert board(command, repository) == projected
    assert [(entry.item_id, entry.reason) for entry in changed.stale_gap_items] == [
        (gap_item, CHANGED_REASON)
    ]


@pytest.mark.parametrize(
    "remainder",
    (
        f"{PACKAGE_MARKER}unapproved | work added outside the use case",
        f"{REMEDY_MARKER}unapproved | a remedy nobody recorded",
        "Obtain the input dataset unapproved-source",
    ),
)
def test_tracker_scope_the_use_case_does_not_declare_is_refused_without_absorbing_it(tmp_path, remainder):
    command, repository, projector = live_projector(tmp_path)
    projector.project((solo_scope(),), repository=repository)
    add_item(command, repository, solo_titles()["prefix"] + remainder, actor="outside@evorthon")
    before_refusal = board(command, repository)

    with pytest.raises(PinaxProjectionError, match="scope the use case does not declare"):
        projector.project((solo_scope(),), repository=repository)

    assert board(command, repository) == before_refusal


def test_reprojection_leaves_pinax_resolved_item_state_to_pinax(tmp_path):
    command, repository, projector = live_projector(tmp_path)
    initial = projector.project((solo_scope(),), repository=repository)
    loop_item = dict(initial.use_cases[0].iteration_items)[PRODUCER_LOOP]
    run_pinax(command, repository, "status", "--actor", "pinax@operator", "--json", loop_item, "ready")
    resolved = board(command, repository)
    assert resolved["items"][loop_item]["status"] == "ready"

    assert projector.project((solo_scope(),), repository=repository) == initial
    assert board(command, repository) == resolved


def test_the_projection_drives_only_the_released_commands_and_repeats_without_an_event(tmp_path):
    runner = FakePinax()
    projector = PinaxContractProjector(runner, actor=ACTOR)

    projector.project((producer_scope(), consumer_scope()), repository=tmp_path)

    assert {command[0] for command in runner.commands} == {"init", "board", "add", "block", "note", "dep"}
    assert {command for command in runner.commands if command[0] == "board"} == {("board", "--json")}

    runner.commands.clear()
    projector.project((producer_scope(), consumer_scope()), repository=tmp_path)

    assert runner.commands == [("init", "--actor", ACTOR), *[("board", "--json")] * 4]


def test_a_package_the_use_case_has_not_approved_is_refused_before_any_command(tmp_path):
    scope = producer_scope(packages=(ApprovedPackage("unapproved-work", "work nobody approved"),))
    projector = PinaxContractProjector(RefusingRunner(), actor=ACTOR)

    with pytest.raises(PinaxProjectionError, match="does not approve"):
        projector.project((scope,), repository=tmp_path)


def test_a_readiness_reading_of_another_use_case_is_refused_before_any_command(tmp_path):
    borrowed = consumer_use_case()
    scope = UseCaseScope(
        use_case=producer_use_case(), readiness=project_readiness(borrowed, {}), packages=()
    )
    projector = PinaxContractProjector(RefusingRunner(), actor=ACTOR)

    with pytest.raises(PinaxProjectionError, match="reads a different use case"):
        projector.project((scope,), repository=tmp_path)


def test_a_machine_route_in_a_reference_is_refused_before_any_command(tmp_path):
    subject = producer_use_case(use_case_id=DRIVE_ROUTE)
    scope = UseCaseScope(
        use_case=subject, readiness=project_readiness(subject, {}), packages=(), iterations=()
    )
    projector = PinaxContractProjector(RefusingRunner(), actor=ACTOR)

    with pytest.raises(PinaxProjectionError, match="not a machine route"):
        projector.project((scope,), repository=tmp_path)


@pytest.mark.parametrize("route", CAPTION_ROUTES)
def test_a_machine_route_in_a_caption_is_refused_before_any_command(tmp_path, route):
    subject = UseCase.open(reference(ReferenceKind.USE_CASE, PRODUCER), header())
    subject = subject.record_target_output(target_output(defined_by=identity("orders-specification")))
    subject = subject.record_dataset(
        dataset(placeholder_id=REFERENCE_ID, role=DatasetRole.REFERENCE, availability=absent(), access_owner=human(route))
    )
    scope = UseCaseScope(use_case=subject, readiness=project_readiness(subject, {}))
    projector = PinaxContractProjector(RefusingRunner(), actor=ACTOR)

    with pytest.raises(PinaxProjectionError, match="not a machine route"):
        projector.project((scope,), repository=tmp_path)


def test_an_actor_handle_without_a_host_is_refused_before_any_command():
    with pytest.raises(PinaxProjectionError, match="a role and a host"):
        PinaxContractProjector(RefusingRunner(), actor="operator")


def test_a_caption_the_tracker_cannot_carry_is_refused_before_any_command(tmp_path):
    subject = UseCase.open(reference(ReferenceKind.USE_CASE, PRODUCER), header())
    subject = subject.record_target_output(target_output(defined_by=identity("orders-specification")))
    subject = subject.record_dataset(
        dataset(
            placeholder_id=REFERENCE_ID,
            role=DatasetRole.REFERENCE,
            availability=absent(),
            access_owner=human("o" * CAPTION_LIMIT),
        )
    )
    scope = UseCaseScope(use_case=subject, readiness=project_readiness(subject, {}))
    projector = PinaxContractProjector(RefusingRunner(), actor=ACTOR)

    with pytest.raises(PinaxProjectionError, match="caption limit"):
        projector.project((scope,), repository=tmp_path)


def test_a_gap_kind_the_projection_cannot_describe_is_refused_before_any_command(tmp_path):
    subject = solo_use_case()
    invented = ReadinessGap(
        kind=InventedKind.INVENTED,
        subject=PRODUCT,
        segment_id=PRODUCT,
        suggested_owner=None,
        synthetic_fillable=True,
        suggested_title="Answer the invented fact",
    )
    scope = UseCaseScope(
        use_case=subject,
        readiness=ReadinessProjection(
            use_case_id=PRODUCER, segments=(), use_case_gaps=(invented,), open_conditions=()
        ),
    )
    projector = PinaxContractProjector(RefusingRunner(), actor=ACTOR)

    with pytest.raises(PinaxProjectionError, match="no note wording is declared"):
        projector.project((scope,), repository=tmp_path)


def test_a_gap_title_the_projection_reserves_is_refused_before_any_command(tmp_path):
    subject = solo_use_case()
    reserved = ReadinessGap(
        kind=FactKind.EXPECTED_OUTPUT,
        subject=PRODUCT,
        segment_id=PRODUCT,
        suggested_owner=None,
        synthetic_fillable=True,
        suggested_title=f"{PACKAGE_MARKER}approve the expected output",
    )
    scope = UseCaseScope(
        use_case=subject,
        readiness=ReadinessProjection(
            use_case_id=PRODUCER, segments=(), use_case_gaps=(reserved,), open_conditions=()
        ),
    )
    projector = PinaxContractProjector(RefusingRunner(), actor=ACTOR)

    with pytest.raises(PinaxProjectionError, match="reserves"):
        projector.project((scope,), repository=tmp_path)


def test_an_iteration_on_a_span_the_use_case_does_not_have_is_refused_before_any_command(tmp_path):
    scope = solo_scope(iterations=(SegmentIteration("stray-loop", "no-such-span", "a loop nowhere"),))
    projector = PinaxContractProjector(RefusingRunner(), actor=ACTOR)

    with pytest.raises(PinaxProjectionError, match="a span the use case does not have"):
        projector.project((scope,), repository=tmp_path)


def test_one_use_case_is_projected_once(tmp_path):
    projector = PinaxContractProjector(RefusingRunner(), actor=ACTOR)

    with pytest.raises(PinaxProjectionError, match="projected once"):
        projector.project((producer_scope(), producer_scope()), repository=tmp_path)


@pytest.mark.parametrize(
    "scopes, message",
    (
        (lambda: (consumer_scope(),), "outside this projection"),
        (
            lambda: (
                producer_scope(),
                consumer_scope(use_case=consumer_use_case(product_id="settled-orders")),
            ),
            "does not reach the consumed product",
        ),
        (
            lambda: (
                producer_scope(),
                consumer_scope(use_case=consumer_use_case(sources_product=False)),
            ),
            "does not source the consumed product",
        ),
    ),
)
def test_a_consumed_product_the_projection_cannot_bind_is_refused_before_any_command(tmp_path, scopes, message):
    projector = PinaxContractProjector(RefusingRunner(), actor=ACTOR)

    with pytest.raises(PinaxProjectionError, match=message):
        projector.project(scopes(), repository=tmp_path)


@pytest.mark.parametrize(
    "edge_type",
    ("blocks", "parent-child", "discovered-from", "related", "supersedes", "future-relation"),
)
def test_existing_edge_scope_drift_across_every_relation_is_refused_before_mutation(tmp_path, edge_type):
    titles = solo_titles()
    runner = FakePinax()
    parent = runner.add(titles["parent"])
    loop = runner.add(titles["iteration"])
    outside = runner.add("outside the projected scope")
    runner.edges[edge_type] = [[outside, loop]]
    runner.edges.setdefault("parent-child", []).append([parent, loop])
    projector = PinaxContractProjector(runner, actor=ACTOR)

    with pytest.raises(PinaxProjectionError, match="enlarges the projected scope"):
        projector.project((solo_scope(),), repository=tmp_path)

    assert runner.commands == [("init", "--actor", ACTOR), ("board", "--json")]


def test_edge_binding_leaves_a_declared_title_with_no_item_unbound():
    """The reading before any item is added binds a declared title that has none."""
    titles = solo_titles()
    declared = {
        ("parent-child", titles["parent"], titles["iteration"]),
        ("parent-child", titles["parent"], titles["gap"]),
        ("blocks", titles["gap"], titles["iteration"]),
    }

    bound = _bind_edges(declared, {titles["parent"]: "evd-1", titles["iteration"]: "evd-2"})

    assert bound == {("parent-child", "evd-1", "evd-2")}
    assert _bind_edges(declared, {}) == set()


def test_a_partly_projected_tracker_is_completed_without_inventing_an_edge(tmp_path):
    """The reading taken before any item is added binds only the edges it can.

    The tracker already holds two of the three declared items, so the edges that
    need the third cannot be bound to identities yet. The projection adds the
    missing item and records every declared edge exactly once.
    """
    titles = solo_titles()
    runner = FakePinax()
    parent = runner.add(titles["parent"])
    loop = runner.add(titles["iteration"])
    projector = PinaxContractProjector(runner, actor=ACTOR)

    result = projector.project((solo_scope(),), repository=tmp_path)

    projected = result.use_cases[0]
    gap = dict(projected.gap_items)[suggested_item_title(FactKind.EXPECTED_OUTPUT, PRODUCT)]
    assert projected.parent_item == parent
    assert dict(projected.iteration_items)[PRODUCER_LOOP] == loop
    assert [command[command.index("--title") + 1] for command in runner.commands if command[0] == "add"] == [
        titles["gap"]
    ]
    assert {
        (edge_type, edge[0], edge[1])
        for edge_type, edges in runner.edges.items()
        for edge in edges
    } == {
        ("parent-child", parent, loop),
        ("parent-child", parent, gap),
        ("blocks", gap, loop),
    }


def test_an_interrupted_projection_recovers_gated_items_before_adding_edges(tmp_path):
    runner = FakePinax(fail_block_once=True)
    projector = PinaxContractProjector(runner, actor=ACTOR)

    with pytest.raises(PinaxProjectionError, match="injected block interruption"):
        projector.project((solo_scope(),), repository=tmp_path)
    assert not runner.edges
    assert not runner.notes

    recovered = projector.project((solo_scope(),), repository=tmp_path)
    recovered_state = deepcopy(runner.state)
    loop_item = dict(recovered.use_cases[0].iteration_items)[PRODUCER_LOOP]

    assert len(runner.items) == 3
    assert len(runner.notes) == 1
    assert runner.items[loop_item]["status"] == "blocked"
    assert runner.items[loop_item]["gate"] == "scope"
    assert projector.project((solo_scope(),), repository=tmp_path) == recovered
    assert runner.state == recovered_state


def test_a_late_duplicate_managed_item_is_refused_at_the_final_validation(tmp_path):
    class ConcurrentDuplicate(FakePinax):
        def on_board(self):
            if self.board_calls == 4:
                first = next(iter(self.items.values()))
                self.add(first["title"])

    runner = ConcurrentDuplicate()
    projector = PinaxContractProjector(runner, actor=ACTOR)

    with pytest.raises(PinaxProjectionError, match="duplicate items"):
        projector.project((solo_scope(),), repository=tmp_path)

    assert len(runner.items) == 4


@pytest.mark.parametrize(
    "state, message",
    (
        ({}, "item state"),
        ({"items": {}}, "dependency state"),
        ({"edges": {}}, "item state"),
        ({"items": [], "edges": {}}, "item state"),
        ({"items": {}, "edges": []}, "dependency state"),
        ({"items": {}, "edges": {}, "notes": {}}, "note state"),
        ({"ergon": {}, "phases": {}}, "item state"),
        ({"items": {}, "edges": {}}, "initialisation metadata"),
        ({"ergon": {}, "phases": {}, "items": {}, "edges": {}}, "initialisation metadata"),
    ),
)
def test_malformed_board_collections_are_refused_before_projection_mutation(tmp_path, state, message):
    class MalformedBoard:
        def __init__(self):
            self.commands = []

        def run(self, arguments, *, repository):
            command = tuple(arguments)
            self.commands.append(command)
            if command[0] == "init":
                return ""
            if command == ("board", "--json"):
                return json.dumps({"state": state})
            raise AssertionError(f"malformed state must be refused before mutation: {arguments!r}")

    runner = MalformedBoard()
    projector = PinaxContractProjector(runner, actor=ACTOR)

    with pytest.raises(PinaxProjectionError, match=message):
        projector.project((solo_scope(),), repository=tmp_path)

    assert runner.commands == [("init", "--actor", ACTOR), ("board", "--json")]


def test_distinct_delimited_use_case_identities_cannot_share_a_projection_namespace():
    nested_engagement = ApprovedContractIdentity(engagement_id="a/b", use_case_id="c")
    nested_use_case = ApprovedContractIdentity(engagement_id="a", use_case_id="b/c")

    assert nested_engagement.title_prefix != nested_use_case.title_prefix
    assert "a%2Fb/c" in nested_engagement.title_prefix
    assert "a/b%2Fc" in nested_use_case.title_prefix


# --- Approved remedies ---

REMEDY_AUTHORITY = identity("accepting-authority")
REMEDY_CASE = identity(CASE)
REMEDY_FAULT_ID = "fault-report-parity"
REMEDY_SUMMARY = "correct the declared population of the report"
REMEDY_ASKED = "the run log of the window the fault reports"


def fingerprint(name: str) -> str:
    return canonical_digest(name.encode("utf-8"))


REMEDY_EVIDENCE = EvidenceReference(
    "parity-observed", "v1", fingerprint("parity-observed"), "the observed parity of the report"
)


def remedy_fault_record() -> FaultRecord:
    """One disclosing fault packet about the report span, in the shape the core writes."""
    return FaultRecord(
        fault_id=REMEDY_FAULT_ID,
        version="v1",
        result=Identity("result-report-parity", "v1", fingerprint("result-report-parity")),
        affected_clause_outcome_ids=("parity-daily-order-report",),
        fault_class=FaultClass.MISSING_POPULATION,
        localisation=DiagnosticLocalisation(
            localisation_id="localisation-report-parity",
            version="v1",
            status=LocalisationStatus.UNKNOWN,
            lower_frontier=(),
            upper_frontier=(),
            uncovered_paths=(),
            supporting_evidence=(REMEDY_EVIDENCE,),
        ),
        diagnostic_scope="output daily-order-report",
        disclosure_decision=DisclosureDecision.DISCLOSE,
        supporting_evidence=(REMEDY_EVIDENCE,),
        contradicting_evidence=(),
        correction_surface=None,
    )


def adviser_hypothesis(number: int) -> AdviserHypothesis:
    """One hypothesis in the form an adviser answers in, each part a whole sentence."""
    return AdviserHypothesis(
        cause=f"reading {number}: the run left out the declared population of the report",
        proposed_fix=f"change {number}: restore the declared population filter in the transformation",
        discriminating_test=(
            f"a regression test numbered {number} that counts the declared population at the "
            "reported grain and fails when one is absent"
        ),
        supporting_evidence_ids=(REMEDY_EVIDENCE.evidence_id,),
    )


def remedy_advice(hypotheses: int = 1) -> RemediationAdvice:
    """The advice an adviser records for that packet, read through the adviser's own reader."""
    reply = AdviserReply(
        form=ADVISER_REPLY_FORM,
        confidence=AdviserConfidence.MEDIUM,
        hypotheses=tuple(adviser_hypothesis(number) for number in range(1, hypotheses + 1)),
        assumptions=("the localisation is not confirmed",),
    )
    recorded = read_adviser_reply(
        reply, gate_fault_packet(remedy_fault_record()), required_authority=REMEDY_AUTHORITY
    )
    assert recorded is not None
    return recorded


def remedy_outcome(taken=RemediationDisposition.ACCEPTED, *, recorded=None):
    """One decision a named human recorded about that advice."""
    values = {
        "disposition": taken,
        "decided_by": DecidingActor(identity=REMEDY_AUTHORITY, kind=RemediationActorKind.HUMAN),
        "rationale": EvidenceReference(
            "remedy-rationale", "v1", "digest-remedy-rationale", "the authority disposed of the advice"
        ),
    }
    if taken is RemediationDisposition.MODIFIED:
        values["edited_fixes"] = ("restore the filter for the reported window only",)
        values["edit_statement"] = "the authority narrowed the remedy to the reported window"
    if taken is RemediationDisposition.REQUEST_MORE_EVIDENCE:
        values["requested_evidence"] = (REMEDY_ASKED,)
        values["rationale"] = EvidenceReference(
            "remedy-rationale",
            "v1",
            "digest-remedy-rationale",
            f"the decision waits on {REMEDY_ASKED}",
        )
    return record_remediation_decision(
        remedy_advice() if recorded is None else recorded, HumanDisposition(**values), case=REMEDY_CASE
    )


def remedy_scope(outcome=None, *, iteration_id: str = PRODUCER_LOOP, **overrides):
    declared = remedy_outcome() if outcome is None else outcome
    return solo_scope(remedies=(ApprovedRemedy(declared, iteration_id, REMEDY_SUMMARY),), **overrides)


def test_an_approved_remedy_projects_one_gated_item_with_its_edges_and_its_note(tmp_path):
    runner = FakePinax()
    projector = PinaxContractProjector(runner, actor=ACTOR)
    outcome = remedy_outcome()
    scope = remedy_scope(outcome)
    titles = solo_titles()

    result = projector.project((scope,), repository=tmp_path)

    projected = result.use_cases[0]
    work = outcome.approved_work.identifier
    remedy_item = dict(projected.remedy_items)[work]
    loop_item = dict(projected.iteration_items)[PRODUCER_LOOP]
    gap_item = dict(projected.gap_items)[suggested_item_title(FactKind.EXPECTED_OUTPUT, PRODUCT)]
    state = runner.state
    notes = notes_by_item(state)

    assert projected.remedy_items == ((work, remedy_item),)
    assert state["items"][remedy_item]["title"] == (
        f"{titles['prefix']}{REMEDY_MARKER}{work} | {REMEDY_SUMMARY}"
    )
    assert typed_edges(state) == {
        ("parent-child", projected.parent_item, gap_item),
        ("parent-child", projected.parent_item, loop_item),
        ("parent-child", projected.parent_item, remedy_item),
        ("blocks", gap_item, loop_item),
        ("blocks", loop_item, remedy_item),
    }
    assert state["items"][remedy_item]["status"] == "blocked"
    assert state["items"][remedy_item]["gate"] == "scope"
    assert notes[remedy_item]["ref"] == f"koine://use-case/{PRODUCER}/remediation/{work}"
    assert notes[remedy_item]["caption"] == f"fault {REMEDY_FAULT_ID}; discriminating tests 1"
    assert len(notes[remedy_item]["caption"]) <= CAPTION_LIMIT
    assert set(notes) == {gap_item, remedy_item}


def test_advice_with_three_discriminating_tests_projects_one_item_with_one_note(tmp_path):
    """An adviser names a test by the whole sentence; three of them still project."""
    runner = FakePinax()
    projector = PinaxContractProjector(runner, actor=ACTOR)
    recorded = remedy_advice(hypotheses=3)
    outcome = remedy_outcome(recorded=recorded)

    projected = projector.project((remedy_scope(outcome),), repository=tmp_path).use_cases[0]

    remedy_item = dict(projected.remedy_items)[outcome.approved_work.identifier]
    written = [note for note in runner.notes if note["item_id"] == remedy_item]
    named = sum(len(test.identifier) for test in recorded.discriminating_tests)

    assert len(recorded.discriminating_tests) == 3
    assert named > CAPTION_LIMIT
    assert len(projected.remedy_items) == 1
    assert len(written) == 1
    assert written[0]["caption"] == f"fault {REMEDY_FAULT_ID}; discriminating tests 3"
    assert len(written[0]["caption"]) <= CAPTION_LIMIT


def test_a_remediation_note_on_a_gap_item_does_not_stand_in_for_its_readiness_note(tmp_path):
    runner = FakePinax()
    titles = solo_titles()
    runner.add(titles["parent"])
    runner.add(titles["iteration"])
    gap_item = runner.add(titles["gap"])
    runner.notes.append(
        {
            "item_id": gap_item,
            "ref": f"koine://use-case/{PRODUCER}/remediation/remedy-elsewhere",
            "caption": f"fault {REMEDY_FAULT_ID}; discriminating tests 1",
        }
    )
    projector = PinaxContractProjector(runner, actor=ACTOR)

    result = projector.project((solo_scope(),), repository=tmp_path)

    written = [note["ref"] for note in runner.notes if note["item_id"] == gap_item]
    assert len(written) == 2
    assert any(ref.startswith(f"koine://use-case/{PRODUCER}/readiness/") for ref in written)
    assert result.stale_gap_items == ()


def test_the_same_approved_remedy_projects_to_the_same_single_item(tmp_path):
    runner = FakePinax()
    projector = PinaxContractProjector(runner, actor=ACTOR)

    first = projector.project((remedy_scope(),), repository=tmp_path)
    projected = deepcopy(runner.state)
    runner.commands.clear()
    second = projector.project((remedy_scope(),), repository=tmp_path)

    assert second == first
    assert runner.state == projected
    assert runner.commands == [("init", "--actor", ACTOR), *[("board", "--json")] * 4]
    assert len(first.use_cases[0].remedy_items) == 1


def test_an_edited_remedy_projects_its_own_item_beside_an_accepted_one(tmp_path):
    accepted = remedy_outcome()
    edited = remedy_outcome(RemediationDisposition.MODIFIED)
    runner = FakePinax()
    projector = PinaxContractProjector(runner, actor=ACTOR)
    scope = solo_scope(
        remedies=(
            ApprovedRemedy(accepted, PRODUCER_LOOP, REMEDY_SUMMARY),
            ApprovedRemedy(edited, PRODUCER_LOOP, "correct the reported window only"),
        )
    )

    projected = projector.project((scope,), repository=tmp_path).use_cases[0]

    assert accepted.approved_work != edited.approved_work
    assert [work for work, _ in projected.remedy_items] == [
        accepted.approved_work.identifier,
        edited.approved_work.identifier,
    ]
    assert len({item for _, item in projected.remedy_items}) == 2


@pytest.mark.parametrize(
    "taken", (RemediationDisposition.REJECTED, RemediationDisposition.REQUEST_MORE_EVIDENCE)
)
def test_a_decision_that_approves_no_work_is_refused_before_any_command(tmp_path, taken):
    projector = PinaxContractProjector(RefusingRunner(), actor=ACTOR)
    outcome = remedy_outcome(taken)

    assert outcome.approved_work is None
    with pytest.raises(PinaxProjectionError, match="a named human approved"):
        projector.project((remedy_scope(outcome),), repository=tmp_path)


def test_a_remedy_that_is_not_a_recorded_decision_is_refused_before_any_command(tmp_path):
    projector = PinaxContractProjector(RefusingRunner(), actor=ACTOR)
    scope = solo_scope(remedies=(ApprovedRemedy(remedy_advice(), PRODUCER_LOOP, REMEDY_SUMMARY),))

    with pytest.raises(PinaxProjectionError, match="declared approved remedies"):
        projector.project((scope,), repository=tmp_path)


def test_a_remedy_on_an_iteration_the_use_case_does_not_declare_is_refused_before_any_command(tmp_path):
    projector = PinaxContractProjector(RefusingRunner(), actor=ACTOR)

    with pytest.raises(PinaxProjectionError, match="an iteration the use case does not declare"):
        projector.project((remedy_scope(iteration_id="no-such-loop"),), repository=tmp_path)


def test_a_remedy_note_caption_the_tracker_cannot_carry_is_refused_before_any_command(tmp_path):
    projector = PinaxContractProjector(RefusingRunner(), actor=ACTOR)
    named = replace(remedy_advice(), fault=identity("f" * CAPTION_LIMIT))

    with pytest.raises(PinaxProjectionError, match="caption limit"):
        projector.project((remedy_scope(remedy_outcome(recorded=named)),), repository=tmp_path)


@pytest.mark.parametrize("route", CAPTION_ROUTES)
def test_a_machine_route_in_a_remedy_caption_is_refused_before_any_command(tmp_path, route):
    projector = PinaxContractProjector(RefusingRunner(), actor=ACTOR)
    named = replace(remedy_advice(), fault=identity(route))

    with pytest.raises(PinaxProjectionError, match="not a machine route"):
        projector.project((remedy_scope(remedy_outcome(recorded=named)),), repository=tmp_path)


def test_one_approved_remedy_is_declared_once_under_a_use_case(tmp_path):
    projector = PinaxContractProjector(RefusingRunner(), actor=ACTOR)
    outcome = remedy_outcome()
    scope = solo_scope(
        remedies=(
            ApprovedRemedy(outcome, PRODUCER_LOOP, REMEDY_SUMMARY),
            ApprovedRemedy(outcome, PRODUCER_LOOP, "the same work under another summary"),
        )
    )

    with pytest.raises(PinaxProjectionError, match="declared once"):
        projector.project((scope,), repository=tmp_path)
