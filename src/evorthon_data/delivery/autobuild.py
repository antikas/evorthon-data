"""Narrow public-CLI route from an approved item selection to AutoBuild.

The route composes and issues one released ``autobuild run`` command for a
selection of already-approved, already-ready tracker items. It never selects,
sequences, or accepts work itself: AutoBuild owns the build sequence, commits
the tracker itself, and delivers according to the mode it is given.

Every refusal here is an integrity refusal: a selected item that is blocked or
unapproved, an attempt to add ``--allow-delivery`` without an explicit
delivery authority, an unsupported installed command set, or a reported
result that does not match its declared schema. No policy gate beyond these
is added. The returned run record carries only identities and a content
digest; no filesystem path from the released report is retained.
"""
# evorthon-implements: EVD-README-025
# evorthon-implements: EVD-README-016
from __future__ import annotations

# evorthon-component: delivery_adapters

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from ..verification.domain import Identity

DISTRIBUTION = "autobuild-factory"

# The public AutoBuild subcommand this adapter contract names. Presence in the
# installed subcommand set is part of the compatibility contract; no version
# is asserted anywhere.
REQUIRED_COMMANDS: tuple[str, ...] = ("run",)

# The public `autobuild run` options this route composes or relies on being
# present. Presence of every one of them in the installed option set is the
# rest of the compatibility contract.
REQUIRED_RUN_FLAGS: tuple[str, ...] = (
    "--repository",
    "--profile",
    "--harness",
    "--delivery-mode",
    "--allow-item",
    "--exclude-item",
    "--allow-delivery",
)

# The delivery mode this route always composes. AutoBuild delivers from the
# invoking branch; no other mode is ever selected here.
DELIVERY_MODE = "current-branch-pr"

# The schema identifier the released command's own JSON result declares. This
# names a result shape, never a tool version.
RUN_RESULT_SCHEMA = "autobuild.campaign-result.v1"


class AutoBuildRouteError(ValueError):
    """Raised when a campaign dispatch cannot proceed or its result fails integrity."""


class AutoBuildRunner(Protocol):
    """The small released-CLI capability required by this adapter."""

    def run(self, arguments: Sequence[str], *, working_directory: Path | None) -> str:
        """Run one public AutoBuild command and return its standard output."""


@dataclass(frozen=True)
class SubprocessAutoBuildRunner:
    """Run the released AutoBuild command without importing tool internals.

    The command is a vector so that the same released entry point can be
    reached through its console script or through the interpreter that holds
    it. The environment owns which one is available.
    """

    command: tuple[str, ...] = ("autobuild",)

    def run(self, arguments: Sequence[str], *, working_directory: Path | None) -> str:
        if not self.command or not all(isinstance(part, str) and part.strip() for part in self.command):
            raise AutoBuildRouteError("an AutoBuild command is required")
        try:
            completed = subprocess.run(
                [*self.command, *arguments],
                cwd=None if working_directory is None else str(working_directory),
                capture_output=True,
                check=False,
                text=True,
            )
        except OSError as exc:
            raise AutoBuildRouteError("the released AutoBuild command is unavailable") from exc
        if completed.returncode:
            detail = (completed.stderr or completed.stdout).strip()
            raise AutoBuildRouteError(f"AutoBuild command failed: {detail or 'unknown error'}")
        return completed.stdout


@dataclass(frozen=True)
class QueueSelection:
    """One tracker item this route may add to a composed campaign.

    Readiness and approval are supplied by the caller from its own owning
    source (the tracker and the human approval record); this route never
    computes either. It only refuses to compose a blocked or unapproved item.
    """

    item_id: str
    ready: bool
    approved: bool


@dataclass(frozen=True)
class DeliveryAuthority:
    """An explicit, identified grant to add ``--allow-delivery`` to one dispatch."""

    granted_by: Identity


@dataclass(frozen=True)
class AutoBuildItemOutcome:
    """One item's reported outcome, referenced by identity: no path is kept."""

    item_id: str
    disposition: str
    item_commit: str | None
    tracker_commit: str | None
    merged_commit: str | None
    pushed: bool


@dataclass(frozen=True)
class AutoBuildRunRecord:
    """A completed dispatch, referenced by identity and content digest.

    Every filesystem path the released report carries (the repository, the
    scratch root, the progress log) is deliberately not retained here: the
    digest of the exact reported result is this record's evidence anchor.
    """

    campaign_id: str
    stop_reason: str
    digest: str
    items: tuple[AutoBuildItemOutcome, ...]


class AutoBuildDeliveryRoute:
    """Drive the released ``autobuild run`` command over an approved item selection."""

    def __init__(self, runner: AutoBuildRunner, *, capabilities: Mapping[str, Any]) -> None:
        self._runner = runner
        if not isinstance(capabilities, Mapping):
            raise AutoBuildRouteError("an installed capability report is required")
        self._capabilities = capabilities

    def assert_supported(self) -> tuple[str, ...]:
        """Check the compatibility contract: the distribution, the run subcommand and its flags."""
        record = self._capabilities.get(DISTRIBUTION)
        if not isinstance(record, Mapping) or record.get("installed") is not True:
            raise AutoBuildRouteError(
                f"the AutoBuild delivery capability is unavailable: {DISTRIBUTION} is not installed"
            )
        subcommands = _supported_subcommands(self._runner.run(("--help",), working_directory=None))
        missing = tuple(name for name in REQUIRED_COMMANDS if name not in subcommands)
        if missing:
            raise AutoBuildRouteError(
                "the installed AutoBuild command set does not support: " + ", ".join(missing)
            )
        run_help = self._runner.run(("run", "--help"), working_directory=None)
        flags = _supported_run_flags(run_help)
        missing_flags = tuple(name for name in REQUIRED_RUN_FLAGS if name not in flags)
        if missing_flags:
            raise AutoBuildRouteError(
                "the installed AutoBuild run command does not support: " + ", ".join(missing_flags)
            )
        modes = _delivery_mode_choices(run_help)
        if DELIVERY_MODE not in modes:
            raise AutoBuildRouteError(
                f"the installed AutoBuild run command does not support delivery mode: {DELIVERY_MODE}"
            )
        return REQUIRED_COMMANDS

    def dispatch(
        self,
        *,
        repository: Path,
        profile: str,
        harness: str,
        items: tuple[QueueSelection, ...],
        delivery_authority: DeliveryAuthority | None = None,
    ) -> AutoBuildRunRecord:
        """Compose and issue one campaign run over approved ready items only."""
        vector = _compose(
            repository=repository,
            profile=profile,
            harness=harness,
            items=items,
            delivery_authority=delivery_authority,
        )
        self.assert_supported()
        output = self._runner.run(vector, working_directory=None)
        return _read_run_record(output)


def _nonempty_text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character in value for character in "\r\n\x00")
    ):
        raise AutoBuildRouteError(f"{label} is required")
    return value


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _nonempty_text(value, label)


def _identity(value: object, label: str) -> Identity:
    if not isinstance(value, Identity):
        raise AutoBuildRouteError(f"{label} must be a declared identity")
    _nonempty_text(value.identifier, f"{label} identifier")
    _nonempty_text(value.version, f"{label} version")
    _nonempty_text(value.digest, f"{label} digest")
    return value


def _compose(
    *,
    repository: Path,
    profile: str,
    harness: str,
    items: tuple[QueueSelection, ...],
    delivery_authority: DeliveryAuthority | None,
) -> tuple[str, ...]:
    """Build the argument vector, refusing a blocked, unapproved or duplicate item.

    Nothing here calls the runner: every refusal in this function is reported
    before any released command is issued.
    """
    repository_text = _nonempty_text(str(repository), "AutoBuild target repository")
    profile_text = _nonempty_text(profile, "AutoBuild profile")
    harness_text = _nonempty_text(harness, "AutoBuild harness")
    if not isinstance(items, tuple) or not items:
        raise AutoBuildRouteError("at least one approved ready item is required")

    vector: list[str] = [
        "run",
        "--repository",
        repository_text,
        "--profile",
        profile_text,
        "--harness",
        harness_text,
        "--delivery-mode",
        DELIVERY_MODE,
    ]
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, QueueSelection):
            raise AutoBuildRouteError("every selected item must be a declared queue selection")
        item_id = _nonempty_text(item.item_id, "selected item identifier")
        if item_id in seen:
            raise AutoBuildRouteError(f"an item may be selected once: {item_id}")
        seen.add(item_id)
        if not item.ready:
            raise AutoBuildRouteError(f"a blocked item cannot be added to a campaign: {item_id}")
        if not item.approved:
            raise AutoBuildRouteError(f"an unapproved item cannot be added to a campaign: {item_id}")
        vector.extend(("--allow-item", item_id))

    if delivery_authority is not None:
        if not isinstance(delivery_authority, DeliveryAuthority):
            raise AutoBuildRouteError("--allow-delivery requires an explicit delivery authority")
        _identity(delivery_authority.granted_by, "delivery authority")
        vector.append("--allow-delivery")

    return tuple(vector)


def _supported_subcommands(help_text: object) -> frozenset[str]:
    """Read the installed subcommand set out of the tool's own top-level help."""
    if not isinstance(help_text, str):
        raise AutoBuildRouteError("the installed AutoBuild command set could not be read")
    match = re.search(r"\{([a-zA-Z0-9_,\-]+)\}", help_text)
    if not match:
        raise AutoBuildRouteError("the installed AutoBuild command set could not be read")
    return frozenset(name.strip() for name in match.group(1).split(",") if name.strip())


def _supported_run_flags(help_text: object) -> frozenset[str]:
    """Read the installed `run` option set out of the tool's own `run --help` output."""
    if not isinstance(help_text, str):
        raise AutoBuildRouteError("the installed AutoBuild run command options could not be read")
    flags = frozenset(re.findall(r"(?m)^ {2,}(--[a-zA-Z][a-zA-Z0-9-]*)", help_text))
    if not flags:
        raise AutoBuildRouteError("the installed AutoBuild run command options could not be read")
    return flags


def _delivery_mode_choices(help_text: str) -> frozenset[str]:
    """Read the installed `--delivery-mode` choice set out of the same help output."""
    match = re.search(r"--delivery-mode\s+\{([^}]*)\}", help_text)
    if not match:
        raise AutoBuildRouteError(
            "the installed AutoBuild run command does not declare delivery-mode choices"
        )
    return frozenset(part.strip() for part in match.group(1).split(",") if part.strip())


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _read_run_record(output: object) -> AutoBuildRunRecord:
    """Read the released command's own JSON result, refusing anything malformed."""
    if not isinstance(output, str) or not output.strip():
        raise AutoBuildRouteError("the AutoBuild run command returned no reportable result")
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError as exc:
        raise AutoBuildRouteError("the AutoBuild run command did not return JSON") from exc
    if not isinstance(parsed, dict):
        raise AutoBuildRouteError("the AutoBuild run command returned an invalid JSON object")
    if parsed.get("schema") != RUN_RESULT_SCHEMA:
        raise AutoBuildRouteError("the AutoBuild run command result does not declare its expected schema")
    campaign_id = _nonempty_text(parsed.get("campaign_id"), "AutoBuild run campaign identifier")
    stop_reason = _nonempty_text(parsed.get("stop_reason"), "AutoBuild run stop reason")
    raw_items = parsed.get("items")
    if not isinstance(raw_items, list):
        raise AutoBuildRouteError("the AutoBuild run command result has no item outcomes")
    items = tuple(_item_outcome(entry) for entry in raw_items)
    return AutoBuildRunRecord(
        campaign_id=campaign_id,
        stop_reason=stop_reason,
        digest=_digest(output.encode("utf-8")),
        items=items,
    )


def _item_outcome(entry: object) -> AutoBuildItemOutcome:
    if not isinstance(entry, dict):
        raise AutoBuildRouteError("the AutoBuild run command reported an invalid item outcome")
    item_id = _nonempty_text(entry.get("item_id"), "AutoBuild reported item identifier")
    disposition = _nonempty_text(entry.get("disposition"), "AutoBuild reported item disposition")
    pushed = entry.get("pushed")
    if not isinstance(pushed, bool):
        raise AutoBuildRouteError(f"AutoBuild reported an invalid pushed flag: {item_id}")
    return AutoBuildItemOutcome(
        item_id=item_id,
        disposition=disposition,
        item_commit=_optional_text(entry.get("item_commit"), f"AutoBuild reported item commit: {item_id}"),
        tracker_commit=_optional_text(
            entry.get("tracker_commit"), f"AutoBuild reported tracker commit: {item_id}"
        ),
        merged_commit=_optional_text(
            entry.get("merged_commit"), f"AutoBuild reported merged commit: {item_id}"
        ),
        pushed=pushed,
    )
