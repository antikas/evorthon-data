"""Narrow public-CLI projection of approved use-case scope to Pinax.

The use case is the unit of intake, readiness, build and acceptance. This
adapter creates one parent item for each use case, and one child item for each
approved package, each readiness gap, each iteration on a span and each
approved remedy. It joins the children to the parent with parent-child edges,
records the gates it can state as blocks edges, and attaches one note to each
gap item naming the gap kind, the suggested owner and whether synthetic data
can fill it, and one note to each remedy item naming the fault and how many
discriminating tests the decision carries.

A remedy reaches this adapter only as a decision a named human already
recorded. The adapter reads that outcome, projects an approved or edited remedy
as one item gated behind the iteration it corrects, and refuses to project a
rejection or a request for more evidence, because neither approves any work.
The decision is made in the verification workflows and never here.

A gap is projected as work, never as a block on the use case, and a
synthetic-fillable gap is labelled rather than refused. The adapter refuses only
integrity failures: scope in the managed namespace the use case does not
declare, a dependency graph wider than the projected one, a machine route where
a logical reference belongs, an actor handle that is not a role and a host, and
a caption the tracker cannot carry.

An edge joins two items this projection creates. A declaration that names no
item at one of its ends, such as a consumed product with no iteration declared
on either side of it, creates no edge rather than an invented one.

Pinax owns every live item state after the graph exists. The module imports no
tracker package and reads no tracker file; it drives the released command and
reads folded state back through the public board response.
"""
# evorthon-implements: EVD-README-025
# evorthon-implements: EVD-README-015
# evorthon-implements: EVD-README-007
from __future__ import annotations

# evorthon-component: delivery_adapters

import json
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol, Sequence
from urllib.parse import quote

from ..boundary_patterns import (
    LOGICAL_REFERENCE_FORM,
    MACHINE_ROUTE_PATTERNS,
    MACHINE_ROUTE_SHAPES,
    shape_carried,
    shapes,
)
from ..engagement.use_case import UseCase
from ..readiness import FactKind, ReadinessGap, ReadinessProjection, projection_digest
from ..verification.workflows.remediation import APPROVING_DISPOSITIONS, RemediationOutcome

# The stable form name of this projection. It namespaces every managed title so
# two projections of different shapes can never read each other's items.
PROJECTION_FORM = "evorthon-use-case-v1"
# The remainder that names the parent item of a use case, and the markers that
# open the three work children. A gap child carries none of them, because its
# title is the suggested title of the gap exactly as readiness wrote it.
PARENT_REMAINDER = "use case"
PACKAGE_MARKER = "package:"
ITERATION_MARKER = "iteration:"
REMEDY_MARKER = "remedy:"
WORK_MARKERS = (PACKAGE_MARKER, ITERATION_MARKER, REMEDY_MARKER)
# The reference form every note this projection writes carries. It points at
# the record the note was read from and never at a stored document. The form
# itself is declared with the boundary shapes, because it is the one address
# form this product writes and every boundary has to read it the same way. The
# scan allows exactly this form, so composing it here from anything else would
# let the notes and the allowance drift apart.
NOTE_SCHEME = LOGICAL_REFERENCE_FORM
# The two records this projection writes a note from, each under its own
# remainder, so a gap note and a remedy note are never read for each other.
READINESS_NOTE_REMAINDER = "readiness"
REMEDIATION_NOTE_REMAINDER = "remediation"
# The gate name this adapter blocks a gated item under until its edges exist.
SCOPE_GATE = "scope"
# The tracker states that finish an item. Pinax owns the vocabulary; the
# projection only asks whether an item is still open.
CLOSED_ITEM_STATES = frozenset({"done", "parked"})
# The tracker's own caption limit.
CAPTION_LIMIT = 200
# The headings a remedy note is captioned under. The second one counts the
# discriminating tests rather than naming them, so the caption fits whatever an
# adviser wrote and the identities stay in the record the reference names.
REMEDY_CAPTION_SUBJECT = "fault"
REMEDY_CAPTION_TESTS = "discriminating tests"
# What a caption says where the record names nothing under a heading it carries.
NOTHING_NAMED = "none named"
# The words each gap kind is captioned with. A kind with no wording here is a
# kind this adapter cannot describe, and it is refused rather than guessed.
GAP_KIND_CAPTIONS: Mapping[FactKind, str] = MappingProxyType(
    {
        FactKind.INPUT_DATASET: "gap kind input dataset",
        FactKind.REFERENCE_DATASET: "gap kind reference dataset",
        FactKind.OUTPUT_DEFINITION: "gap kind output definition",
        FactKind.EXPECTED_OUTPUT: "gap kind expected output",
        FactKind.CHECKPOINT: "gap kind checkpoint",
        FactKind.SOURCE_COMBINATION: "gap kind source combination",
    }
)
# Why an open gap item no longer matches the projection.
DROPPED_REASON = "the current reading no longer states this gap"
CHANGED_REASON = "the gap kind, suggested owner or synthetic fill no longer matches"

_BACKSLASH = chr(92)
# The machine routes that must never reach the tracker. A note is one declared
# value this adapter wrote, so it reads every shape the product declares,
# including the declared-value readings and the generic address one. Their
# shapes are owned in one place; the refusal below is this adapter's own.
MACHINE_ROUTES = shapes(MACHINE_ROUTE_PATTERNS, MACHINE_ROUTE_SHAPES)
# A reference segment carries a plain identity, so a composed reference has one
# reading and no segment can be mistaken for another.
REFERENCE_SEGMENT = re.compile(r"[A-Za-z0-9._-]+")
# An actor handle is a role and a host.
ACTOR_HANDLE = re.compile(r"[!-?A-~]+@[!-?A-~]+")


class PinaxProjectionError(ValueError):
    """Raised when approved use-case scope cannot be projected safely."""


class PinaxRunner(Protocol):
    """The small released-CLI capability required by this adapter."""

    def run(self, arguments: Sequence[str], *, repository: Path) -> str:
        """Run one public Pinax command and return its standard output."""


@dataclass(frozen=True)
class SubprocessPinaxRunner:
    """Run the released Pinax executable without importing tracker internals."""

    command: str = "pinax"

    def run(self, arguments: Sequence[str], *, repository: Path) -> str:
        command = self.command.strip()
        if not command:
            raise PinaxProjectionError("a Pinax command is required")
        try:
            completed = subprocess.run(
                [command, "--root", str(repository), *arguments],
                cwd=repository,
                capture_output=True,
                check=False,
                text=True,
            )
        except OSError as exc:
            raise PinaxProjectionError("the released Pinax command is unavailable") from exc
        if completed.returncode:
            detail = (completed.stderr or completed.stdout).strip()
            raise PinaxProjectionError(f"Pinax command failed: {detail or 'unknown error'}")
        return completed.stdout


@dataclass(frozen=True)
class ApprovedContractIdentity:
    """The stable identity of one projected use case.

    The identity carries no projection digest and no revision, so the titles it
    namespaces survive every later reading of the same use case.
    """

    engagement_id: str
    use_case_id: str

    def __post_init__(self) -> None:
        _identity_text(self.engagement_id, "engagement identifier")
        _identity_text(self.use_case_id, "use case identifier")

    @property
    def title_prefix(self) -> str:
        """Return the stable title namespace of this use case."""
        return (
            f"Evorthon {PROJECTION_FORM}/"
            f"{quote(self.engagement_id, safe='')}/{quote(self.use_case_id, safe='')} | "
        )


@dataclass(frozen=True)
class ApprovedPackage:
    """One approved build package under a use case."""

    package_id: str
    summary: str
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class SegmentIteration:
    """One build-and-verify loop on one span of a use case."""

    iteration_id: str
    segment_id: str
    summary: str


@dataclass(frozen=True)
class ApprovedRemedy:
    """One correction a named human approved, and the iteration it corrects.

    ``outcome`` is the recorded decision exactly as the verification workflows
    wrote it. The adapter reads it and never decides anything about it: a
    decision that approves no work is refused rather than projected.
    """

    outcome: RemediationOutcome
    iteration_id: str
    summary: str


@dataclass(frozen=True)
class UseCaseScope:
    """One use case, the readiness it was read on, and the work under it."""

    use_case: UseCase
    readiness: ReadinessProjection
    packages: tuple[ApprovedPackage, ...] = ()
    iterations: tuple[SegmentIteration, ...] = ()
    remedies: tuple[ApprovedRemedy, ...] = ()


@dataclass(frozen=True)
class ProjectedUseCase:
    """The opaque Pinax identities one use case was projected onto."""

    identity: ApprovedContractIdentity
    parent_item: str
    package_items: tuple[tuple[str, str], ...]
    gap_items: tuple[tuple[str, str], ...]
    iteration_items: tuple[tuple[str, str], ...]
    remedy_items: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class StaleGapItem:
    """An open gap item the current projection no longer states."""

    use_case_id: str
    item_id: str
    title: str
    reason: str


@dataclass(frozen=True)
class PinaxProjectionResult:
    """Opaque Pinax item identities and the gap items that have gone stale."""

    use_cases: tuple[ProjectedUseCase, ...]
    stale_gap_items: tuple[StaleGapItem, ...]


@dataclass(frozen=True)
class _GapChild:
    title: str
    caption: str
    reference: str
    segment_id: str | None


@dataclass(frozen=True)
class _PackageChild:
    identifier: str
    title: str
    depends_on: tuple[str, ...]


@dataclass(frozen=True)
class _IterationChild:
    identifier: str
    title: str
    segment_id: str


@dataclass(frozen=True)
class _RemedyChild:
    identifier: str
    title: str
    caption: str
    reference: str
    corrects_title: str


@dataclass(frozen=True)
class _ReadScope:
    """One validated use case, ready to project, with no tracker call made yet."""

    identity: ApprovedContractIdentity
    parent_title: str
    note_prefix: str
    managed_note_prefix: str
    packages: tuple[_PackageChild, ...]
    gaps: tuple[_GapChild, ...]
    iterations: tuple[_IterationChild, ...]
    remedies: tuple[_RemedyChild, ...]
    segment_sources: Mapping[str, tuple[str, ...]]
    consumed: tuple[tuple[str, str], ...]

    @property
    def titles(self) -> tuple[str, ...]:
        """Every title this use case declares, the parent first."""
        return (
            self.parent_title,
            *(package.title for package in self.packages),
            *(gap.title for gap in self.gaps),
            *(iteration.title for iteration in self.iterations),
            *(remedy.title for remedy in self.remedies),
        )

    @property
    def noted(self) -> tuple[tuple[str, str, str, str], ...]:
        """Every item this projection notes, with the record each note comes from.

        A note is read for the item it sits on and for the record kind it came
        from, so a remedy note on a gap item never stands in for that gap's
        readiness note.
        """
        return tuple(
            (child.title, child.caption, child.reference, remainder)
            for children, remainder in (
                (self.gaps, READINESS_NOTE_REMAINDER),
                (self.remedies, REMEDIATION_NOTE_REMAINDER),
            )
            for child in children
        )

    def package_title(self, identifier: str) -> str | None:
        for package in self.packages:
            if package.identifier == identifier:
                return package.title
        return None

    def iteration_titles_on(self, segment_id: str) -> tuple[str, ...]:
        """The titles of the items on one span, in declaration order."""
        return tuple(
            iteration.title for iteration in self.iterations if iteration.segment_id == segment_id
        )

    def iteration_titles_sourcing(self, product_id: str) -> tuple[str, ...]:
        """The titles of the items on every span that reads one product."""
        return tuple(
            iteration.title
            for iteration in self.iterations
            if product_id in self.segment_sources.get(iteration.segment_id, ())
        )


def _nonempty_text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character in value for character in "\r\n\x00")
    ):
        raise PinaxProjectionError(f"{label} is required")
    return value


def _identity_text(value: object, label: str) -> str:
    text = _nonempty_text(value, label)
    if "|" in text:
        raise PinaxProjectionError(f"{label} must not contain a projection delimiter")
    return text


def _reject_machine_route(value: str, label: str) -> None:
    """Refuse a machine route where only a logical reference belongs.

    A tracker note is plain logical text, so this adapter adds one rule of its
    own beyond the declared shapes: the separator a machine path is written
    with has no meaning in a note at all, and a text carrying one is refused
    wherever it sits. An address is refused under every scheme, the two web
    ones included, because a note names a record and never a host. The one
    reference the projection writes is composed from segments this adapter has
    already read, so the scheme it carries is never read as a note's own text.
    """
    if _BACKSLASH in value or shape_carried(MACHINE_ROUTES, value) is not None:
        raise PinaxProjectionError(f"{label} must be logical, not a machine route")


def _tracker_text(value: object, label: str) -> str:
    """Read one text the tracker will carry, refusing anything unprintable."""
    text = _nonempty_text(value, label)
    if not text.isascii() or not text.isprintable():
        raise PinaxProjectionError(f"{label} must be plain printable text")
    _reject_machine_route(text, label)
    return text


def _reference_segment(value: object, label: str) -> str:
    """Read one segment of a tracker reference, which carries a plain identity."""
    text = _tracker_text(value, label)
    if not REFERENCE_SEGMENT.fullmatch(text):
        raise PinaxProjectionError(f"{label} must carry a plain identity in a tracker reference")
    return text


def _actor_handle(value: object) -> str:
    """Read the actor handle, which names a role and the host it acts on."""
    text = _tracker_text(value, "a Pinax actor handle")
    if not ACTOR_HANDLE.fullmatch(text):
        raise PinaxProjectionError("a Pinax actor handle must name a role and a host")
    return text


def _gap_caption(gap: ReadinessGap) -> str:
    """Compose the one caption that says what a gap is, in one place."""
    wording = GAP_KIND_CAPTIONS.get(gap.kind)
    if wording is None:
        raise PinaxProjectionError("no note wording is declared for this gap kind")
    if gap.suggested_owner is None:
        owner = NOTHING_NAMED
    else:
        owner = _tracker_text(getattr(gap.suggested_owner, "identity", None), "a suggested gap owner")
    if not isinstance(gap.synthetic_fillable, bool):
        raise PinaxProjectionError("a gap must say whether synthetic data can fill it")
    filled = "yes" if gap.synthetic_fillable else "no"
    return _note_caption(
        f"{wording}; suggested owner {owner}; synthetic fill {filled}", "a gap note caption"
    )


def _note_caption(caption: str, label: str) -> str:
    """Read one composed caption, which the tracker carries whole or not at all."""
    if len(caption) > CAPTION_LIMIT:
        raise PinaxProjectionError(f"{label} does not fit the tracker caption limit")
    return _tracker_text(caption, label)


def _remedy_caption(outcome: RemediationOutcome) -> str:
    """Compose the one caption that says what a remedy corrects, in one place.

    The caption names the fault and how many discriminating tests the decision
    carries. It does not name those tests, because a test is identified by the
    whole sentence that describes it and two of them do not fit a tracker
    caption; their identities are in the record the note's reference points at,
    where a reader has them in full. What is left is a fault identity and a
    count, so a caption composed here fits whatever an adviser wrote.
    """
    fault = _tracker_text(getattr(outcome.fault, "identifier", None), "a remedy fault identity")
    return _note_caption(
        f"{REMEDY_CAPTION_SUBJECT} {fault}; {REMEDY_CAPTION_TESTS} {len(outcome.discriminating_tests)}",
        "a remedy note caption",
    )


def _reject_reserved_remainder(remainder: str, label: str) -> None:
    if remainder == PARENT_REMAINDER or remainder.startswith(WORK_MARKERS):
        raise PinaxProjectionError(f"{label} uses a title the projection reserves")


def _read_scope(scope: object) -> _ReadScope:
    """Read one declared use case, refusing anything the record does not carry."""
    if not isinstance(scope, UseCaseScope):
        raise PinaxProjectionError("projection requires declared use-case scope")
    use_case = scope.use_case
    if not isinstance(use_case, UseCase):
        raise PinaxProjectionError("projection requires a declared use case")
    readiness = scope.readiness
    if not isinstance(readiness, ReadinessProjection):
        raise PinaxProjectionError("projection requires the readiness of that use case")
    use_case_id = _identity_text(use_case.identity.identifier, "use case identifier")
    if readiness.use_case_id != use_case_id:
        raise PinaxProjectionError("the readiness projection reads a different use case")
    identity = ApprovedContractIdentity(
        engagement_id=_identity_text(use_case.header.engagement_id, "engagement identifier"),
        use_case_id=use_case_id,
    )
    prefix = identity.title_prefix
    managed_note_prefix = f"{NOTE_SCHEME}{_reference_segment(use_case_id, 'a use case identifier')}/"
    note_prefix = f"{managed_note_prefix}{READINESS_NOTE_REMAINDER}/"
    reference = (
        f"{note_prefix}{_reference_segment(projection_digest(readiness), 'a projection digest')}"
    )

    spans = use_case.segments()
    segment_sources = {span.segment_id: tuple(span.sources) for span in spans}
    packages = _read_packages(scope, use_case, prefix)
    iterations = _read_iterations(scope, segment_sources, prefix)
    gaps = _read_gaps(readiness, segment_sources, prefix, reference)
    remedies = _read_remedies(
        scope, iterations, prefix, f"{managed_note_prefix}{REMEDIATION_NOTE_REMAINDER}/"
    )
    consumed = tuple(
        (
            _identity_text(dependency.provider.identifier, "a providing use case identifier"),
            _identity_text(dependency.product_id, "a consumed product identifier"),
        )
        for dependency in use_case.consumer_dependencies
    )
    return _ReadScope(
        identity=identity,
        parent_title=f"{prefix}{PARENT_REMAINDER}",
        note_prefix=note_prefix,
        managed_note_prefix=managed_note_prefix,
        packages=packages,
        gaps=gaps,
        iterations=iterations,
        remedies=remedies,
        segment_sources=segment_sources,
        consumed=consumed,
    )


def _read_packages(scope: UseCaseScope, use_case: UseCase, prefix: str) -> tuple[_PackageChild, ...]:
    """Read the declared packages, refusing any the use case has not approved."""
    if not isinstance(scope.packages, tuple):
        raise PinaxProjectionError("the packages of a use case must be recorded in a tuple")
    approved = {
        package.identifier for version in use_case.versions for package in version.packages
    }
    declared: list[_PackageChild] = []
    seen: set[str] = set()
    for package in scope.packages:
        if not isinstance(package, ApprovedPackage):
            raise PinaxProjectionError("packages must be declared approved packages")
        identifier = _tracker_text(package.package_id, "a package identifier")
        if identifier in seen:
            raise PinaxProjectionError("a package is declared once under a use case")
        seen.add(identifier)
        if identifier not in approved:
            raise PinaxProjectionError("the use case does not approve one of the declared packages")
        summary = _tracker_text(package.summary, "a package summary")
        depends_on = tuple(
            _tracker_text(value, "a package dependency") for value in package.depends_on
        )
        declared.append(
            _PackageChild(
                identifier=identifier,
                title=f"{prefix}{PACKAGE_MARKER}{identifier} | {summary}",
                depends_on=depends_on,
            )
        )
    for package in declared:
        if package.identifier in package.depends_on or not set(package.depends_on) <= seen:
            raise PinaxProjectionError("a package depends on work outside the declared packages")
    return tuple(declared)


def _read_iterations(
    scope: UseCaseScope, segment_sources: Mapping[str, tuple[str, ...]], prefix: str
) -> tuple[_IterationChild, ...]:
    """Read the declared iterations, refusing one that names an unknown span."""
    if not isinstance(scope.iterations, tuple):
        raise PinaxProjectionError("the iterations of a use case must be recorded in a tuple")
    declared: list[_IterationChild] = []
    seen: set[str] = set()
    for iteration in scope.iterations:
        if not isinstance(iteration, SegmentIteration):
            raise PinaxProjectionError("iterations must be declared span iterations")
        identifier = _tracker_text(iteration.iteration_id, "an iteration identifier")
        if identifier in seen:
            raise PinaxProjectionError("an iteration is declared once under a use case")
        seen.add(identifier)
        segment_id = _tracker_text(iteration.segment_id, "an iteration span")
        if segment_id not in segment_sources:
            raise PinaxProjectionError("an iteration names a span the use case does not have")
        summary = _tracker_text(iteration.summary, "an iteration summary")
        declared.append(
            _IterationChild(
                identifier=identifier,
                title=f"{prefix}{ITERATION_MARKER}{identifier} | {summary}",
                segment_id=segment_id,
            )
        )
    return tuple(declared)


def _read_remedies(
    scope: UseCaseScope,
    iterations: tuple[_IterationChild, ...],
    prefix: str,
    note_prefix: str,
) -> tuple[_RemedyChild, ...]:
    """Read the declared remedies, refusing any a named human has not approved.

    The work identity comes from the decision, so the same approved remedy
    reads to the same title and the same reference every time. A decision that
    approves no work names no item at all and is refused here rather than
    projected as work nobody agreed to.
    """
    if not isinstance(scope.remedies, tuple):
        raise PinaxProjectionError("the remedies of a use case must be recorded in a tuple")
    corrected = {iteration.identifier: iteration.title for iteration in iterations}
    declared: list[_RemedyChild] = []
    seen: set[str] = set()
    for remedy in scope.remedies:
        if not isinstance(remedy, ApprovedRemedy) or not isinstance(remedy.outcome, RemediationOutcome):
            raise PinaxProjectionError("remedies must be declared approved remedies")
        outcome = remedy.outcome
        work = outcome.decision.approved_work
        if outcome.decision.disposition not in APPROVING_DISPOSITIONS or work is None:
            raise PinaxProjectionError(
                "a remedy is projected only when a named human approved the work it names"
            )
        identifier = _reference_segment(work.identifier, "an approved work identity")
        if identifier in seen:
            raise PinaxProjectionError("a remedy is declared once under a use case")
        seen.add(identifier)
        iteration_title = corrected.get(_tracker_text(remedy.iteration_id, "a corrected iteration"))
        if iteration_title is None:
            raise PinaxProjectionError("a remedy names an iteration the use case does not declare")
        summary = _tracker_text(remedy.summary, "a remedy summary")
        declared.append(
            _RemedyChild(
                identifier=identifier,
                title=f"{prefix}{REMEDY_MARKER}{identifier} | {summary}",
                caption=_remedy_caption(outcome),
                reference=f"{note_prefix}{identifier}",
                corrects_title=iteration_title,
            )
        )
    return tuple(declared)


def _read_gaps(
    readiness: ReadinessProjection,
    segment_sources: Mapping[str, tuple[str, ...]],
    prefix: str,
    reference: str,
) -> tuple[_GapChild, ...]:
    """Read the gaps, taking each suggested title from readiness exactly as written."""
    declared: list[_GapChild] = []
    seen: set[str] = set()
    for gap in readiness.gaps:
        suggested = _tracker_text(getattr(gap, "suggested_title", None), "a suggested gap title")
        _reject_reserved_remainder(suggested, "a suggested gap title")
        if suggested in seen:
            raise PinaxProjectionError("two gaps suggest one title under a use case")
        seen.add(suggested)
        segment_id = gap.segment_id
        if segment_id is not None:
            segment_id = _tracker_text(segment_id, "a gap span")
            if segment_id not in segment_sources:
                raise PinaxProjectionError("a gap names a span the use case does not have")
        declared.append(
            _GapChild(
                title=f"{prefix}{suggested}",
                caption=_gap_caption(gap),
                reference=reference,
                segment_id=segment_id,
            )
        )
    return tuple(declared)


def _read_scopes(scopes: object) -> tuple[_ReadScope, ...]:
    """Read every declared use case and bind the products they share."""
    if isinstance(scopes, UseCaseScope) or not isinstance(scopes, (tuple, list)):
        raise PinaxProjectionError("projection requires a sequence of declared use-case scope")
    if not scopes:
        raise PinaxProjectionError("projection requires at least one declared use case")
    read = tuple(_read_scope(scope) for scope in scopes)
    identifiers = [scope.identity.use_case_id for scope in read]
    if len(identifiers) != len(set(identifiers)):
        raise PinaxProjectionError("a use case is projected once")
    titles = [title for scope in read for title in scope.titles]
    if len(titles) != len(set(titles)):
        raise PinaxProjectionError("two declared items share one title")
    return read


def _consumer_edges(read: Sequence[_ReadScope]) -> set[tuple[str, str, str]]:
    """The blocks edges every consumed product implies, by title."""
    by_identifier = {scope.identity.use_case_id: scope for scope in read}
    edges: set[tuple[str, str, str]] = set()
    for scope in read:
        for provider_id, product_id in scope.consumed:
            provider = by_identifier.get(provider_id)
            if provider is None:
                raise PinaxProjectionError(
                    "a projected use case consumes a product from a use case outside this projection"
                )
            if product_id not in provider.segment_sources:
                raise PinaxProjectionError("the providing use case does not reach the consumed product")
            if not any(product_id in sources for sources in scope.segment_sources.values()):
                raise PinaxProjectionError("the consuming use case does not source the consumed product")
            consuming = scope.iteration_titles_sourcing(product_id)
            for producing_title in provider.iteration_titles_on(product_id):
                for consuming_title in consuming:
                    edges.add(("blocks", producing_title, consuming_title))
    return edges


def _title_edges(read: Sequence[_ReadScope]) -> set[tuple[str, str, str]]:
    """The one computation of the typed edge set, in titles rather than identities."""
    edges: set[tuple[str, str, str]] = set()
    for scope in read:
        for title in scope.titles[1:]:
            edges.add(("parent-child", scope.parent_title, title))
        for package in scope.packages:
            for dependency in package.depends_on:
                source = scope.package_title(dependency)
                if source is not None:
                    edges.add(("blocks", source, package.title))
        for gap in scope.gaps:
            if gap.segment_id is None:
                continue
            for iteration_title in scope.iteration_titles_on(gap.segment_id):
                edges.add(("blocks", gap.title, iteration_title))
        for remedy in scope.remedies:
            edges.add(("blocks", remedy.corrects_title, remedy.title))
    return edges | _consumer_edges(read)


def _bind_edges(
    title_edges: set[tuple[str, str, str]], item_ids: Mapping[str, str]
) -> set[tuple[str, str, str]]:
    """Bind the one title-level edge computation to the identities in hand.

    The binding is partial on purpose. It also runs on the reading taken before
    any item is created, where a declared title may have no identity yet, and it
    then binds the edges it can rather than inventing an end.
    """
    bound: set[tuple[str, str, str]] = set()
    for edge_type, source_title, target_title in title_edges:
        source = item_ids.get(source_title)
        target = item_ids.get(target_title)
        if source is not None and target is not None:
            bound.add((edge_type, source, target))
    return bound


class PinaxContractProjector:
    """Project approved use-case scope through Pinax's released public CLI only."""

    def __init__(self, runner: PinaxRunner, *, actor: str, prefix: str = "evd") -> None:
        self._runner = runner
        self._actor = _actor_handle(actor)
        self._prefix = _tracker_text(prefix, "Pinax item prefix")

    def project(self, scopes: object, *, repository: Path) -> PinaxProjectionResult:
        """Create the exact graph the use cases declare, refusing anything wider."""
        read = _read_scopes(scopes)
        title_edges = _title_edges(read)
        repository = Path(repository).resolve()
        if not repository.is_dir():
            raise PinaxProjectionError("projection repository must be an existing directory")
        titles = {title for scope in read for title in scope.titles}

        self._run(("init", "--actor", self._actor), repository)
        initial = self._board(repository)
        self._reject_unapproved_scope(initial, read, titles)
        item_ids = self._resolve_existing_items(initial, titles)
        self._reject_scope_edge_drift(
            initial, read, titles, set(item_ids.values()), _bind_edges(title_edges, item_ids)
        )

        for title in sorted(titles - set(item_ids)):
            item_ids[title] = self._add(title, repository)

        after_add = self._read_state(repository, read, titles, item_ids)
        expected = _bind_edges(title_edges, item_ids)
        for item_id in self._gated_without_edges(after_add, expected):
            item = after_add["items"][item_id]
            if item.get("status") != "blocked" or item.get("gate") != SCOPE_GATE:
                self._run(
                    ("block", "--gate", SCOPE_GATE, "--actor", self._actor, "--json", item_id),
                    repository,
                )

        before_edges = self._read_state(repository, read, titles, item_ids)
        self._reject_scope_edge_drift(
            before_edges, read, titles, set(item_ids.values()), expected
        )
        self._validate_gated_items_are_blocked(
            before_edges, self._gated_without_edges(before_edges, expected)
        )
        for scope in read:
            written = self._managed_captions(before_edges, scope, item_ids)
            for title, caption, reference, remainder in scope.noted:
                if not written.get((item_ids[title], remainder)):
                    self._add_note(item_ids[title], caption, reference, repository)
        observed = _typed_edge_set(before_edges)
        for edge_type, source_id, target_id in sorted(expected - observed):
            self._run(
                (
                    "dep",
                    "add",
                    source_id,
                    "--to",
                    target_id,
                    "--type",
                    edge_type,
                    "--actor",
                    self._actor,
                    "--json",
                ),
                repository,
            )

        final = self._read_state(repository, read, titles, item_ids)
        self._validate_exact_edges(final, read, titles, set(item_ids.values()), expected)
        self._validate_managed_notes(final, read, item_ids)
        return PinaxProjectionResult(
            use_cases=tuple(self._projected(scope, item_ids) for scope in read),
            stale_gap_items=self._stale_gap_items(final, read, titles, item_ids),
        )

    def _run(self, arguments: Sequence[str], repository: Path) -> str:
        return self._runner.run(tuple(arguments), repository=repository)

    def _json(self, arguments: Sequence[str], repository: Path) -> dict[str, Any]:
        output = self._run(arguments, repository)
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError as exc:
            raise PinaxProjectionError("Pinax public command did not return JSON") from exc
        if not isinstance(parsed, dict):
            raise PinaxProjectionError("Pinax public command returned an invalid JSON object")
        return parsed

    def _board(self, repository: Path) -> dict[str, Any]:
        payload = self._json(("board", "--json"), repository)
        state = payload.get("state")
        if not isinstance(state, dict):
            raise PinaxProjectionError("Pinax board response has no item state")
        items = state.get("items", {})
        if not isinstance(items, dict):
            raise PinaxProjectionError("Pinax board response has no item state")
        edges = state.get("edges", {})
        if not isinstance(edges, dict):
            raise PinaxProjectionError("Pinax board response has no dependency state")
        notes = state.get("notes", [])
        if not isinstance(notes, list):
            raise PinaxProjectionError("Pinax board response has no note state")
        # Pinax omits an empty collection while retaining its initialisation
        # metadata. The metadata is mandatory regardless of whether any
        # collection happens to be present.
        if not self._has_initialised_board_metadata(state):
            for name, key in (("item", "items"), ("dependency", "edges")):
                if key not in state:
                    raise PinaxProjectionError(f"Pinax board response has no {name} state")
            raise PinaxProjectionError("Pinax board response has no initialisation metadata")
        return {**state, "items": items, "edges": edges, "notes": notes}

    def _read_state(
        self,
        repository: Path,
        read: Sequence[_ReadScope],
        titles: set[str],
        item_ids: dict[str, str],
    ) -> dict[str, Any]:
        """Read the board again and re-check every invariant the projection holds."""
        state = self._board(repository)
        self._validate_exact_items(state, item_ids, titles)
        self._reject_unapproved_scope(state, read, titles)
        return state

    @staticmethod
    def _has_initialised_board_metadata(state: dict[str, Any]) -> bool:
        tracker = state.get("ergon")
        phases = state.get("phases")
        if not isinstance(tracker, dict) or not isinstance(phases, dict):
            return False
        initial_phase = phases.get("init")
        if not isinstance(initial_phase, dict):
            return False
        text_fields = (
            tracker.get("actor"),
            tracker.get("created_at"),
            initial_phase.get("opened_at"),
            initial_phase.get("opened_by"),
            initial_phase.get("status"),
        )
        opened_seq = initial_phase.get("opened_seq")
        return all(isinstance(value, str) and value for value in text_fields) and (
            isinstance(opened_seq, int) and not isinstance(opened_seq, bool) and opened_seq >= 0
        )

    @staticmethod
    def _items_by_title(state: dict[str, Any]) -> dict[str, list[str]]:
        by_title: dict[str, list[str]] = {}
        for item_id, item in state["items"].items():
            if not isinstance(item_id, str) or not isinstance(item, dict):
                raise PinaxProjectionError("Pinax board contains an invalid item")
            title = item.get("title")
            if not isinstance(title, str):
                raise PinaxProjectionError("Pinax board item has no title")
            by_title.setdefault(title, []).append(item_id)
        return by_title

    def _resolve_existing_items(self, state: dict[str, Any], titles: set[str]) -> dict[str, str]:
        by_title = self._items_by_title(state)
        resolved: dict[str, str] = {}
        for title in titles:
            matches = by_title.get(title, [])
            if len(matches) > 1:
                raise PinaxProjectionError("Pinax contains duplicate items for one declared item")
            if matches:
                resolved[title] = matches[0]
        return resolved

    def _add(self, title: str, repository: Path) -> str:
        payload = self._json(
            (
                "add",
                "--title",
                title,
                "--prefix",
                self._prefix,
                "--allow-new-prefix",
                "--actor",
                self._actor,
                "--json",
            ),
            repository,
        )
        return _nonempty_text(payload.get("item_id"), "Pinax created item identifier")

    def _add_note(self, item_id: str, caption: str, reference: str, repository: Path) -> None:
        self._run(
            (
                "note",
                "add",
                item_id,
                "--ref",
                reference,
                "--caption",
                caption,
                "--actor",
                self._actor,
                "--json",
            ),
            repository,
        )

    @staticmethod
    def _notes(state: dict[str, Any]) -> list[dict[str, Any]]:
        notes: list[dict[str, Any]] = []
        for note in state["notes"]:
            if not isinstance(note, dict):
                raise PinaxProjectionError("Pinax board contains an invalid note")
            item_id = note.get("item_id")
            reference = note.get("ref")
            if not isinstance(item_id, str) or not isinstance(reference, str):
                raise PinaxProjectionError("Pinax board contains an invalid note")
            notes.append(note)
        return notes

    def _managed_captions(
        self, state: dict[str, Any], scope: _ReadScope, item_ids: Mapping[str, str]
    ) -> dict[tuple[str, str], set[str]]:
        """The captions this projection has already written, by item and record kind.

        Every note this projection writes for one use case sits under that use
        case's own reference prefix, and the segment after it names the record
        the note came from. Both are read here, so a note of one kind is never
        counted as a note of another.
        """
        owned = {item_ids[title] for title in scope.titles if title in item_ids}
        captions: dict[tuple[str, str], set[str]] = {}
        for note in self._notes(state):
            if note["item_id"] not in owned or not note["ref"].startswith(scope.managed_note_prefix):
                continue
            remainder = note["ref"][len(scope.managed_note_prefix) :].partition("/")[0]
            caption = note.get("caption")
            captions.setdefault((note["item_id"], remainder), set()).add(
                caption if isinstance(caption, str) else ""
            )
        return captions

    def _managed_note_items(self, state: dict[str, Any], scope: _ReadScope) -> set[str]:
        """Every item this projection has attached a readiness note to."""
        return {
            note["item_id"]
            for note in self._notes(state)
            if note["ref"].startswith(scope.note_prefix)
        }

    def _retained_gap_ids(
        self, state: dict[str, Any], read: Sequence[_ReadScope], titles: set[str]
    ) -> set[str]:
        """The gap items this projection wrote that the current reading has dropped.

        The fact each one named may since have been answered. Such an item is
        reported rather than absorbed, removed or refused, and the edges it
        still carries stay outside the exact comparison until Pinax closes it.
        """
        retained: set[str] = set()
        for scope in read:
            noted = self._managed_note_items(state, scope)
            prefix = scope.identity.title_prefix
            for item_id, item in state["items"].items():
                if not isinstance(item, dict):
                    raise PinaxProjectionError("Pinax board contains an invalid item")
                title = item.get("title")
                if not isinstance(title, str) or not title.startswith(prefix) or title in titles:
                    continue
                remainder = title[len(prefix) :]
                if remainder == PARENT_REMAINDER or remainder.startswith(WORK_MARKERS):
                    continue
                if item_id in noted:
                    retained.add(item_id)
        return retained

    def _reject_unapproved_scope(
        self, state: dict[str, Any], read: Sequence[_ReadScope], titles: set[str]
    ) -> None:
        """Refuse tracker scope the use cases do not declare."""
        retained = self._retained_gap_ids(state, read, titles)
        for scope in read:
            prefix = scope.identity.title_prefix
            for item_id, item in state["items"].items():
                title = item.get("title")
                if not isinstance(title, str) or not title.startswith(prefix) or title in titles:
                    continue
                if item_id not in retained:
                    raise PinaxProjectionError("tracker contains scope the use case does not declare")

    @staticmethod
    def _gated_without_edges(
        state: dict[str, Any], expected: set[tuple[str, str, str]]
    ) -> tuple[str, ...]:
        """The gated items whose declared gates are not all recorded yet."""
        observed = _typed_edge_set(state)
        missing = {
            target for edge_type, _, target in expected - observed if edge_type == "blocks"
        }
        for item_id in missing:
            if not isinstance(state["items"].get(item_id), dict):
                raise PinaxProjectionError("Pinax items no longer match the projected scope")
        return tuple(sorted(missing))

    @staticmethod
    def _validate_gated_items_are_blocked(state: dict[str, Any], item_ids: Sequence[str]) -> None:
        for item_id in item_ids:
            item = state["items"].get(item_id)
            if (
                not isinstance(item, dict)
                or item.get("status") != "blocked"
                or item.get("gate") != SCOPE_GATE
            ):
                raise PinaxProjectionError("a gated item must remain Pinax-blocked")

    def _reject_scope_edge_drift(
        self,
        state: dict[str, Any],
        read: Sequence[_ReadScope],
        titles: set[str],
        item_ids: set[str],
        expected: set[tuple[str, str, str]],
    ) -> None:
        scoped = _scoped_edges(state, item_ids, self._retained_gap_ids(state, read, titles))
        if not scoped <= expected:
            raise PinaxProjectionError("tracker dependency graph enlarges the projected scope")

    def _validate_exact_items(
        self, state: dict[str, Any], item_ids: dict[str, str], titles: set[str]
    ) -> None:
        if self._resolve_existing_items(state, titles) != item_ids:
            raise PinaxProjectionError("Pinax items no longer match the projected scope")

    def _validate_exact_edges(
        self,
        state: dict[str, Any],
        read: Sequence[_ReadScope],
        titles: set[str],
        item_ids: set[str],
        expected: set[tuple[str, str, str]],
    ) -> None:
        scoped = _scoped_edges(state, item_ids, self._retained_gap_ids(state, read, titles))
        if scoped != expected:
            raise PinaxProjectionError("Pinax dependency graph does not match the projected scope")

    def _validate_managed_notes(
        self, state: dict[str, Any], read: Sequence[_ReadScope], item_ids: Mapping[str, str]
    ) -> None:
        for scope in read:
            captions = self._managed_captions(state, scope, item_ids)
            for title, _, _, remainder in scope.noted:
                if not captions.get((item_ids[title], remainder)):
                    raise PinaxProjectionError("a noted item carries no note of its own kind")

    @staticmethod
    def _projected(scope: _ReadScope, item_ids: Mapping[str, str]) -> ProjectedUseCase:
        return ProjectedUseCase(
            identity=scope.identity,
            parent_item=item_ids[scope.parent_title],
            package_items=tuple(
                (package.identifier, item_ids[package.title]) for package in scope.packages
            ),
            gap_items=tuple(
                (gap.title[len(scope.identity.title_prefix) :], item_ids[gap.title])
                for gap in scope.gaps
            ),
            iteration_items=tuple(
                (iteration.identifier, item_ids[iteration.title]) for iteration in scope.iterations
            ),
            remedy_items=tuple(
                (remedy.identifier, item_ids[remedy.title]) for remedy in scope.remedies
            ),
        )

    def _stale_gap_items(
        self,
        state: dict[str, Any],
        read: Sequence[_ReadScope],
        titles: set[str],
        item_ids: Mapping[str, str],
    ) -> tuple[StaleGapItem, ...]:
        """Report the open gap items the current reading no longer states."""
        retained = self._retained_gap_ids(state, read, titles)
        stale: list[StaleGapItem] = []
        for scope in read:
            captions = self._managed_captions(state, scope, item_ids)
            for item_id in sorted(retained):
                item = state["items"][item_id]
                title = item["title"]
                if not title.startswith(scope.identity.title_prefix):
                    continue
                if item.get("status") in CLOSED_ITEM_STATES:
                    continue
                stale.append(
                    StaleGapItem(
                        use_case_id=scope.identity.use_case_id,
                        item_id=item_id,
                        title=title,
                        reason=DROPPED_REASON,
                    )
                )
            for gap in scope.gaps:
                item_id = item_ids[gap.title]
                if gap.caption not in captions.get((item_id, READINESS_NOTE_REMAINDER), set()):
                    stale.append(
                        StaleGapItem(
                            use_case_id=scope.identity.use_case_id,
                            item_id=item_id,
                            title=gap.title,
                            reason=CHANGED_REASON,
                        )
                    )
        return tuple(sorted(stale, key=lambda entry: (entry.use_case_id, entry.item_id, entry.reason)))


def _typed_edge_set(state: dict[str, Any]) -> set[tuple[str, str, str]]:
    edges = state.get("edges")
    if not isinstance(edges, dict):
        raise PinaxProjectionError("Pinax board contains invalid dependency edges")
    result: set[tuple[str, str, str]] = set()
    for edge_type, raw_edges in edges.items():
        if not isinstance(edge_type, str) or not isinstance(raw_edges, list):
            raise PinaxProjectionError("Pinax board contains invalid dependency edges")
        for edge in raw_edges:
            if not isinstance(edge, list) or len(edge) != 2 or not all(isinstance(end, str) for end in edge):
                raise PinaxProjectionError("Pinax board contains invalid dependency edges")
            result.add((edge_type, edge[0], edge[1]))
    return result


def _scoped_edges(
    state: dict[str, Any], item_ids: set[str], retained: set[str]
) -> set[tuple[str, str, str]]:
    """Every recorded edge with an end inside the scope and none on a retained item."""
    return {
        edge
        for edge in _typed_edge_set(state)
        if (edge[1] in item_ids or edge[2] in item_ids)
        and edge[1] not in retained
        and edge[2] not in retained
    }
