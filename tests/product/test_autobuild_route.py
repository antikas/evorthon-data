"""Hermetic proofs for the AutoBuild delivery route and its run-record mapping.

The deep-marked test at the foot of this file proves the compatibility
contract against the installed wheel. It imports the delivery tool inside the
test body, through `pytest.importorskip`, and it never runs `autobuild run`
for real: only `--help` and `run --help`, the compatibility contract's own
read surface, are issued.
"""
# evorthon-verifies: EVD-README-025
# evorthon-verifies: EVD-README-016
from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field

import pytest

from evorthon_data.delivery import (
    AutoBuildDeliveryRoute,
    AutoBuildRouteError,
    AutoBuildRunRecord,
    DeliveryAuthority,
    QueueSelection,
    SubprocessAutoBuildRunner,
)
from evorthon_data.delivery.autobuild import REQUIRED_COMMANDS
from evorthon_data.verification.domain import Identity

TOP_HELP_TEXT = (
    "usage: autobuild [-h] {run,watch} ...\n"
    "\n"
    "Run the portable AutoBuild campaign workflow.\n"
    "\n"
    "positional arguments:\n"
    "  {run,watch}\n"
    "    run        Run ready tracker items until a bound or stop condition\n"
    "    watch      Follow the progress lines of a running or finished campaign\n"
    "\n"
    "options:\n"
    "  -h, --help   show this help message and exit\n"
)

RUN_HELP_TEXT = (
    "usage: autobuild run [-h] [--repository REPOSITORY] [--profile PROFILE]\n"
    "                     [--harness HARNESS] [--allow-item ALLOW_ITEM]\n"
    "                     [--exclude-item EXCLUDE_ITEM] [--allow-delivery]\n"
    "                     [--delivery-mode {protected-default,current-branch-pr}]\n"
    "\n"
    "options:\n"
    "  -h, --help            show this help message and exit\n"
    "  --repository REPOSITORY\n"
    "  --profile PROFILE\n"
    "  --harness HARNESS\n"
    "  --allow-item ALLOW_ITEM\n"
    "  --exclude-item EXCLUDE_ITEM\n"
    "  --allow-delivery\n"
    "  --delivery-mode {protected-default,current-branch-pr}\n"
)


def run_result_payload(**overrides) -> dict:
    payload = {
        "schema": "autobuild.campaign-result.v1",
        "version": "0.5.0",
        "campaign_id": "autobuild-20260908T120000Z",
        "repository": "the-repository-tree",
        "scratch_root": "the-scratch-tree",
        "adapters": [],
        "stop_reason": "queue_exhausted",
        "selection": {},
        "refill": {"enabled": False, "proposal_count": 0, "fog_count": 0},
        "report_ref": "durable evidence reference",
        "repository_report_ref": "the-repository-tree/campaign-report.md",
        "progress_ref": "the-scratch-tree/runs/autobuild-20260908T120000Z/progress.log",
        "items": [
            {
                "item_id": "evd-aaaa",
                "disposition": "accepted",
                "states": ["claimed", "built", "reviewed", "accepted"],
                "reason": None,
                "item_commit": "abc1234",
                "tracker_commit": "def5678",
                "merged_commit": "abc1234",
                "pushed": True,
            },
            {
                "item_id": "evd-bbbb",
                "disposition": "accepted",
                "states": ["claimed", "built", "reviewed", "accepted"],
                "reason": None,
                "item_commit": "111aaaa",
                "tracker_commit": "222bbbb",
                "merged_commit": "111aaaa",
                "pushed": True,
            },
        ],
    }
    payload.update(overrides)
    return payload


def result_text(**overrides) -> str:
    return json.dumps(run_result_payload(**overrides), indent=2, sort_keys=True) + "\n"


def result_with_item(item_overrides: dict | None = None, *, drop_keys: tuple[str, ...] = ()) -> str:
    payload = run_result_payload()
    item = dict(payload["items"][0])
    for key in drop_keys:
        item.pop(key, None)
    if item_overrides:
        item.update(item_overrides)
    payload["items"] = [item]
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


@dataclass
class FakeAutoBuildRunner:
    """Answer the public commands the route drives, without the released tool."""

    top_help: object = TOP_HELP_TEXT
    run_help: object = RUN_HELP_TEXT
    run_result: str = field(default_factory=result_text)
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def run(self, arguments, *, working_directory):
        recorded = tuple(arguments)
        self.calls.append(recorded)
        if recorded == ("--help",):
            return self.top_help
        if recorded == ("run", "--help"):
            return self.run_help
        if recorded and recorded[0] == "run":
            return self.run_result
        raise AssertionError(f"unexpected AutoBuild command: {recorded!r}")


CAPABILITIES = {"autobuild-factory": {"installed": True, "version": "0.5.0"}}


def route(runner: FakeAutoBuildRunner) -> AutoBuildDeliveryRoute:
    return AutoBuildDeliveryRoute(runner, capabilities=CAPABILITIES)


def selection(item_id: str, *, ready: bool = True, approved: bool = True) -> QueueSelection:
    return QueueSelection(item_id=item_id, ready=ready, approved=approved)


def two_items() -> tuple[QueueSelection, ...]:
    return (selection("evd-aaaa"), selection("evd-bbbb"))


def test_a_well_formed_request_composes_the_exact_run_vector_and_reads_the_run_record(tmp_path):
    runner = FakeAutoBuildRunner()
    repository = tmp_path / "repo"

    result = route(runner).dispatch(
        repository=repository,
        profile="use-case-build",
        harness="claude-code",
        items=two_items(),
    )

    assert runner.calls == [
        ("--help",),
        ("run", "--help"),
        (
            "run",
            "--repository",
            str(repository),
            "--profile",
            "use-case-build",
            "--harness",
            "claude-code",
            "--delivery-mode",
            "current-branch-pr",
            "--allow-item",
            "evd-aaaa",
            "--allow-item",
            "evd-bbbb",
        ),
    ]
    assert result.campaign_id == "autobuild-20260908T120000Z"
    assert result.stop_reason == "queue_exhausted"
    assert result.digest.startswith("sha256:")
    assert [outcome.item_id for outcome in result.items] == ["evd-aaaa", "evd-bbbb"]
    assert result.items[0].disposition == "accepted"
    assert result.items[0].item_commit == "abc1234"
    assert result.items[0].pushed is True


def test_the_run_record_carries_no_path_field_by_construction():
    field_names = {declared.name for declared in dataclasses.fields(AutoBuildRunRecord)}

    assert field_names == {"campaign_id", "stop_reason", "digest", "items"}


def test_an_explicit_delivery_authority_adds_allow_delivery_at_the_end(tmp_path):
    runner = FakeAutoBuildRunner()
    authority = DeliveryAuthority(
        granted_by=Identity(identifier="owner-approval", version="v1", digest="sha256:authority-digest")
    )

    route(runner).dispatch(
        repository=tmp_path,
        profile="use-case-build",
        harness="claude-code",
        items=two_items(),
        delivery_authority=authority,
    )

    assert runner.calls[-1] == (
        "run",
        "--repository",
        str(tmp_path),
        "--profile",
        "use-case-build",
        "--harness",
        "claude-code",
        "--delivery-mode",
        "current-branch-pr",
        "--allow-item",
        "evd-aaaa",
        "--allow-item",
        "evd-bbbb",
        "--allow-delivery",
    )


def test_a_blocked_item_is_refused_before_any_runner_call(tmp_path):
    runner = FakeAutoBuildRunner()
    items = (selection("evd-aaaa"), selection("evd-bbbb", ready=False))

    with pytest.raises(AutoBuildRouteError, match="blocked item cannot be added to a campaign: evd-bbbb"):
        route(runner).dispatch(repository=tmp_path, profile="p", harness="h", items=items)
    assert runner.calls == []


def test_an_unapproved_item_is_refused_before_any_runner_call(tmp_path):
    runner = FakeAutoBuildRunner()
    items = (selection("evd-aaaa"), selection("evd-bbbb", approved=False))

    with pytest.raises(AutoBuildRouteError, match="unapproved item cannot be added to a campaign: evd-bbbb"):
        route(runner).dispatch(repository=tmp_path, profile="p", harness="h", items=items)
    assert runner.calls == []


def test_allow_delivery_is_refused_without_an_explicit_delivery_authority(tmp_path):
    runner = FakeAutoBuildRunner()

    with pytest.raises(AutoBuildRouteError, match="--allow-delivery requires an explicit delivery authority"):
        route(runner).dispatch(
            repository=tmp_path, profile="p", harness="h", items=two_items(), delivery_authority=True
        )
    assert runner.calls == []


def test_a_delivery_authority_without_a_declared_identity_is_refused(tmp_path):
    runner = FakeAutoBuildRunner()

    with pytest.raises(AutoBuildRouteError, match="delivery authority must be a declared identity"):
        route(runner).dispatch(
            repository=tmp_path,
            profile="p",
            harness="h",
            items=two_items(),
            delivery_authority=DeliveryAuthority(granted_by="owner-approval"),
        )
    assert runner.calls == []


def test_unsupported_capability_fails_through_the_installed_capability_report(monkeypatch, tmp_path):
    from importlib.metadata import PackageNotFoundError

    from evorthon_data import dependencies

    def absent(distribution: str):
        raise PackageNotFoundError(distribution)

    monkeypatch.setattr(dependencies, "version", absent)
    capabilities = dependencies.installed_capabilities()
    runner = FakeAutoBuildRunner()

    assert capabilities["autobuild-factory"] == {"installed": False, "version": None}
    with pytest.raises(AutoBuildRouteError, match="autobuild-factory is not installed"):
        AutoBuildDeliveryRoute(runner, capabilities=capabilities).dispatch(
            repository=tmp_path, profile="p", harness="h", items=two_items()
        )
    assert runner.calls == []


def test_missing_run_subcommand_is_refused_by_name():
    runner = FakeAutoBuildRunner(
        top_help=(
            "usage: autobuild [-h] {watch} ...\n"
            "\n"
            "positional arguments:\n"
            "  {watch}\n"
            "    watch      Follow the progress lines of a running or finished campaign\n"
        )
    )

    with pytest.raises(AutoBuildRouteError, match="does not support: run"):
        route(runner).assert_supported()
    assert runner.calls == [("--help",)]


def test_missing_run_flag_is_refused_by_name():
    runner = FakeAutoBuildRunner(run_help=RUN_HELP_TEXT.replace("  --allow-delivery\n", ""))

    with pytest.raises(AutoBuildRouteError, match=r"does not support: --allow-delivery"):
        route(runner).assert_supported()


def test_missing_delivery_mode_choice_is_refused():
    runner = FakeAutoBuildRunner(
        run_help=RUN_HELP_TEXT.replace(
            "--delivery-mode {protected-default,current-branch-pr}",
            "--delivery-mode {protected-default}",
        )
    )

    with pytest.raises(AutoBuildRouteError, match="does not support delivery mode: current-branch-pr"):
        route(runner).assert_supported()


@pytest.mark.parametrize("help_text", ["usage: autobuild\n", None])
def test_unreadable_top_level_help_is_refused(help_text):
    runner = FakeAutoBuildRunner(top_help=help_text)

    with pytest.raises(AutoBuildRouteError, match="command set could not be read"):
        route(runner).assert_supported()


@pytest.mark.parametrize("help_text", ["usage: autobuild run\n", None])
def test_unreadable_run_help_is_refused(help_text):
    runner = FakeAutoBuildRunner(run_help=help_text)

    with pytest.raises(AutoBuildRouteError, match="options could not be read"):
        route(runner).assert_supported()


def test_a_capability_report_is_required():
    with pytest.raises(AutoBuildRouteError, match="installed capability report is required"):
        AutoBuildDeliveryRoute(FakeAutoBuildRunner(), capabilities=["autobuild-factory"])


def test_at_least_one_item_is_required(tmp_path):
    runner = FakeAutoBuildRunner()

    with pytest.raises(AutoBuildRouteError, match="at least one approved ready item is required"):
        route(runner).dispatch(repository=tmp_path, profile="p", harness="h", items=())
    assert runner.calls == []


def test_items_must_be_a_declared_tuple(tmp_path):
    runner = FakeAutoBuildRunner()

    with pytest.raises(AutoBuildRouteError, match="at least one approved ready item is required"):
        route(runner).dispatch(
            repository=tmp_path, profile="p", harness="h", items=[selection("evd-aaaa")]
        )
    assert runner.calls == []


def test_every_selected_item_must_be_a_declared_queue_selection(tmp_path):
    runner = FakeAutoBuildRunner()

    with pytest.raises(AutoBuildRouteError, match="declared queue selection"):
        route(runner).dispatch(repository=tmp_path, profile="p", harness="h", items=("evd-aaaa",))
    assert runner.calls == []


def test_a_duplicate_item_id_is_refused(tmp_path):
    runner = FakeAutoBuildRunner()
    items = (selection("evd-aaaa"), selection("evd-aaaa"))

    with pytest.raises(AutoBuildRouteError, match="an item may be selected once: evd-aaaa"):
        route(runner).dispatch(repository=tmp_path, profile="p", harness="h", items=items)
    assert runner.calls == []


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"profile": ""}, "AutoBuild profile is required"),
        ({"harness": " claude-code"}, "AutoBuild harness is required"),
    ],
)
def test_malformed_dispatch_text_is_refused(tmp_path, kwargs, reason):
    runner = FakeAutoBuildRunner()
    values = {"repository": tmp_path, "profile": "p", "harness": "h", "items": two_items()}
    values.update(kwargs)

    with pytest.raises(AutoBuildRouteError, match=reason):
        route(runner).dispatch(**values)
    assert runner.calls == []


@pytest.mark.parametrize(
    ("output", "reason"),
    [
        ("", "no reportable result"),
        ("{not json", "did not return JSON"),
        ("[]\n", "invalid JSON object"),
        (result_text(schema="autobuild.campaign-result.v0"), "does not declare its expected schema"),
        (result_text(campaign_id=""), "campaign identifier is required"),
        (result_text(campaign_id=None), "campaign identifier is required"),
        (result_text(stop_reason=None), "stop reason is required"),
        (result_text(items="not-a-list"), "no item outcomes"),
        (result_text(items=["evd-aaaa"]), "invalid item outcome"),
        (result_with_item(drop_keys=("item_id",)), "item identifier is required"),
        (result_with_item(drop_keys=("disposition",)), "item disposition is required"),
        (result_with_item(item_overrides={"pushed": "yes"}), "invalid pushed flag"),
        (result_with_item(item_overrides={"item_commit": ""}), "item commit"),
    ],
)
def test_a_malformed_run_result_is_refused_with_the_reason(tmp_path, output, reason):
    runner = FakeAutoBuildRunner(run_result=output)

    with pytest.raises(AutoBuildRouteError, match=reason):
        route(runner).dispatch(repository=tmp_path, profile="p", harness="h", items=two_items())


def test_the_subprocess_runner_refuses_an_empty_command():
    with pytest.raises(AutoBuildRouteError, match="an AutoBuild command is required"):
        SubprocessAutoBuildRunner(command=()).run(("--help",), working_directory=None)


def test_an_unavailable_released_command_is_refused():
    runner = SubprocessAutoBuildRunner(command=("evorthon-absent-autobuild-command",))

    with pytest.raises(AutoBuildRouteError, match="released AutoBuild command is unavailable"):
        runner.run(("--help",), working_directory=None)


def test_a_failing_released_command_reports_its_own_output():
    import sys

    runner = SubprocessAutoBuildRunner(
        command=(sys.executable, "-c", "import sys; sys.stderr.write('campaign defect'); sys.exit(3)")
    )

    with pytest.raises(AutoBuildRouteError, match="AutoBuild command failed: campaign defect"):
        runner.run(("run", "--help"), working_directory=None)


@pytest.mark.deep
@pytest.mark.timeout(300)
def test_the_compatibility_contract_passes_against_the_installed_wheel():
    """Prove the compatibility contract against the installed wheel's own help output.

    This never starts a real campaign: only ``--help`` and ``run --help`` are
    issued, which is the compatibility contract's own read surface.
    """
    pytest.importorskip("autobuild")
    import shutil
    import sys

    from evorthon_data.dependencies import installed_capabilities

    report = installed_capabilities()
    assert report["autobuild-factory"]["installed"] is True

    found = shutil.which("autobuild")
    command = (found,) if found else (sys.executable, "-m", "autobuild")
    live_route = AutoBuildDeliveryRoute(SubprocessAutoBuildRunner(command=command), capabilities=report)

    assert live_route.assert_supported() == REQUIRED_COMMANDS
