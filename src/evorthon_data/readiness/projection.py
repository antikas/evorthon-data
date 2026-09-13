"""Per-segment readiness: what can be built now, on what evidence, and what is missing.

Readiness is a projection. It reads the use-case record and a case index the
caller supplies, and it reports, for each lineage span the record derives, a
state, the facts that state rests on, and the gaps that remain. It computes the
spans by asking the use case for them, so the record and the projection cannot
disagree.

Each segment needs only its own facts. The fact table has six rows, and the
last is read only by a segment that reads more than one source.

1. Input datasets. A declared input among the segment's sources. It reads as
   real when it is in hand, as synthetic when the record holds a synthetic fill
   or a case declares it synthetic or derived, and as missing otherwise. A
   synthetic dataset fills it.
2. Reference data. The same rule for a reference, enrichment or prior-state
   dataset. A synthetic dataset fills it.
3. The output definition. A target output declares its shape as part of being a
   target output, so the shape cannot be absent from the record. What can be
   absent is what defines the output: the specification or golden example a
   greenfield output is built to, or the existing output a modernisation target
   replaces. A named step is its own definition. Nothing fills this row: it has
   to be answered before the segment builds, and a segment whose own definition
   is missing is the one segment state that cannot build.
4. The expected output. A case holds it for a target output, with the approved
   origin it came from. Without an origin it is missing, and rule derivation
   fills it as labelled synthetic evidence.
5. The checkpoint. A named step is checkpointed when the use case names the
   evidence owner for it and a case declares a checkpoint of that name. Without
   both, the segment still builds and runs output-only, so localisation is
   weaker rather than absent.
6. The source combination. A segment reading two or more sources needs the
   record to say how they come together. A segment reading one source is not
   read for this row at all. Nothing fills it: no generated data can decide
   whether sources stack or merge, and on what keys. Like the checkpoint, its
   absence is a listed gap and not a state the segment cannot leave.

A use case is buildable when at least one segment is. Nothing here reports a
use case that cannot start: the state vocabulary carries no such word, because
what is buildable builds and the rest is a listed gap.

Readiness is advice. A gap, a missing fact and synthetic evidence are all
recorded and none of them raises. The refusals are integrity refusals only: a
supplied value outside the vocabulary the projection reads, a case entry that
contradicts itself or the result the record already holds, and a case identity
the use case does not reference.

The projection owns its own canonical rendering and digest. The bytes are one
JSON object with sorted ASCII keys, compact separators and a closing line feed,
and every leaf is a plain value or the string form the declaring enumeration
owns. No record of the verification domain is written in any form here; the
domain values reach the bytes as their own enumerated text.
"""
# evorthon-implements: EVD-README-049
# evorthon-implements: EVD-README-045
from __future__ import annotations

# evorthon-component: readiness
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from ..engagement.aggregate import Actor
from ..engagement.use_case import (
    AuthorityRole,
    AvailabilityState,
    BuildRoute,
    ConditionKey,
    ConditionState,
    DatasetPlaceholder,
    Segment,
    SegmentBoundary,
    TargetOutput,
    UseCase,
)
from ..verification.domain.contracts import (
    DatasetProvenance,
    DatasetRole,
    DiagnosticStrength,
    ExpectedOutputOrigin,
    Identity,
    VerificationStatus,
)


READINESS_PROJECTION_FORM = "evorthon.readiness.projection.v1"
# The one hash declaration for the projection digest.
DIGEST_ALGORITHM = "blake2b"
DIGEST_SIZE_BYTES = 32


class RefusalReason(str, Enum):
    """The closed set of integrity reasons for refusing to project readiness."""

    INVALID_INPUT = "invalid-input"
    UNKNOWN_CASE_IDENTITY = "unknown-case-identity"
    CONTRADICTORY_CASE_ENTRY = "contradictory-case-entry"
    UNDECLARED_REPRESENTATION = "undeclared-representation"


class ReadinessError(ValueError):
    """Raised when the supplied record or case index cannot be read as declared."""

    def __init__(self, reason: RefusalReason, detail: str) -> None:
        super().__init__(f"{reason.value}: {detail}")
        self.reason = reason


class SegmentState(str, Enum):
    """What one segment can do now.

    There is no member for a segment that must wait for something outside
    itself, and none for a use case at all. A segment whose own output
    definition is missing is gapped; every other missing fact has a fallback
    that keeps the segment building.
    """

    BUILDABLE = "buildable"
    BUILDABLE_WITH_FALLBACKS = "buildable_with_fallbacks"
    GAPPED = "gapped"


class FactKind(str, Enum):
    """The facts a segment is read for, one per row of the fallback table.

    The last row is read only by a segment that reads more than one source, so
    a segment reading one source carries five.
    """

    INPUT_DATASET = "input_dataset"
    REFERENCE_DATASET = "reference_dataset"
    OUTPUT_DEFINITION = "output_definition"
    EXPECTED_OUTPUT = "expected_output"
    CHECKPOINT = "checkpoint"
    SOURCE_COMBINATION = "source_combination"


class FactEvidence(str, Enum):
    """How one fact is satisfied, or that it is not satisfied at all."""

    REAL = "real"
    SYNTHETIC = "synthetic"
    MISSING = "missing"


# Whether a missing fact has a synthetic fill. The output definition, the
# checkpoint and the source combination have none: intake answers the first, the
# second is answered by naming an owner and declaring the evidence, and no
# generated data can decide how two sources come together.
SYNTHETIC_FILLABLE: Mapping[FactKind, bool] = MappingProxyType(
    {
        FactKind.INPUT_DATASET: True,
        FactKind.REFERENCE_DATASET: True,
        FactKind.OUTPUT_DEFINITION: False,
        FactKind.EXPECTED_OUTPUT: True,
        FactKind.CHECKPOINT: False,
        FactKind.SOURCE_COMBINATION: False,
    }
)
# The fact row each declared dataset role is read under.
DATASET_FACT_KINDS: Mapping[DatasetRole, FactKind] = MappingProxyType(
    {
        DatasetRole.INPUT: FactKind.INPUT_DATASET,
        DatasetRole.REFERENCE: FactKind.REFERENCE_DATASET,
        DatasetRole.ENRICHMENT: FactKind.REFERENCE_DATASET,
        DatasetRole.PRIOR_STATE: FactKind.REFERENCE_DATASET,
    }
)
# What a declared availability state says about the evidence in hand, before a
# case refines an obtained dataset to synthetic.
AVAILABILITY_EVIDENCE: Mapping[AvailabilityState, FactEvidence] = MappingProxyType(
    {
        AvailabilityState.OBTAINED: FactEvidence.REAL,
        AvailabilityState.SYNTHETIC_FILLED: FactEvidence.SYNTHETIC,
        AvailabilityState.OBTAINABLE_BY: FactEvidence.MISSING,
        AvailabilityState.UNOBTAINABLE: FactEvidence.MISSING,
    }
)
# The authorities to suggest as the owner of a gap, in the order they are read.
# A dataset names its own access owner, so no authority is consulted for one.
GAP_OWNER_ROLES: Mapping[FactKind, tuple[AuthorityRole, ...]] = MappingProxyType(
    {
        FactKind.INPUT_DATASET: (),
        FactKind.REFERENCE_DATASET: (),
        FactKind.OUTPUT_DEFINITION: (AuthorityRole.ACCEPTING, AuthorityRole.AMBIGUITY_RESOLVER),
        FactKind.EXPECTED_OUTPUT: (
            AuthorityRole.EVIDENCE_OWNER,
            AuthorityRole.ACCEPTING,
            AuthorityRole.AMBIGUITY_RESOLVER,
        ),
        FactKind.CHECKPOINT: (AuthorityRole.AMBIGUITY_RESOLVER, AuthorityRole.ACCEPTING),
        FactKind.SOURCE_COMBINATION: (AuthorityRole.AMBIGUITY_RESOLVER, AuthorityRole.ACCEPTING),
    }
)
# The words a suggested item title opens with. This module is the sole author of
# the title; a projector that creates the item uses it verbatim.
GAP_TITLE_ACTIONS: Mapping[FactKind, str] = MappingProxyType(
    {
        FactKind.INPUT_DATASET: "Obtain the input dataset",
        FactKind.REFERENCE_DATASET: "Obtain the reference dataset",
        FactKind.OUTPUT_DEFINITION: "Define the target output",
        FactKind.EXPECTED_OUTPUT: "Approve the expected output for",
        FactKind.CHECKPOINT: "Name the evidence owner for the checkpoint",
        FactKind.SOURCE_COMBINATION: "Declare how the sources combine for",
    }
)
# An expected output whose origin is a derivation is synthetic evidence.
DERIVED_ORIGINS = frozenset({ExpectedOutputOrigin.SYNTHETIC_DERIVATION})


def _refuse(reason: RefusalReason, detail: str) -> ReadinessError:
    return ReadinessError(reason, detail)


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _refuse(RefusalReason.INVALID_INPUT, f"{label} must be recorded in text")
    return value


def _required_member(value: object, declared: type, label: str) -> None:
    if not isinstance(value, declared):
        raise _refuse(RefusalReason.UNDECLARED_REPRESENTATION, f"{label} must be a declared {declared.__name__}")


def _required_tuple(value: object, label: str) -> None:
    if not isinstance(value, tuple):
        raise _refuse(RefusalReason.INVALID_INPUT, f"{label} must be recorded in a tuple")


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def suggested_item_title(kind: FactKind, subject: str) -> str:
    """Return the item title suggested for one gap.

    The form is the words the kind opens with, a space, and the subject the gap
    names. This module is the only author of the text.
    """
    _required_member(kind, FactKind, "a gap kind")
    action = GAP_TITLE_ACTIONS[kind]
    return f"{action} {_required_text(subject, 'a gap subject')}"


@dataclass(frozen=True)
class CaseDataset:
    """One frozen dataset a case holds: what it fills and how it was made."""

    dataset_id: str
    role: DatasetRole
    provenance: DatasetProvenance

    def __post_init__(self) -> None:
        _required_text(self.dataset_id, "a case dataset identity")
        _required_member(self.role, DatasetRole, "a case dataset role")
        _required_member(self.provenance, DatasetProvenance, "a case dataset provenance")


@dataclass(frozen=True)
class CaseExpectedOutput:
    """One expected output a case holds, its approved origin and its provenance.

    An expected output with no origin is a fact intake has not answered, not a
    refusal. An origin that disagrees with the provenance is a refusal, because
    the entry then says two different things about the same evidence.
    """

    output_id: str
    provenance: DatasetProvenance
    origin: ExpectedOutputOrigin | None = None

    def __post_init__(self) -> None:
        _required_text(self.output_id, "a case expected output identity")
        _required_member(self.provenance, DatasetProvenance, "a case expected output provenance")
        if self.origin is None:
            return
        _required_member(self.origin, ExpectedOutputOrigin, "a case expected output origin")
        derived = self.origin in DERIVED_ORIGINS
        if derived and self.provenance is DatasetProvenance.REAL:
            raise _refuse(
                RefusalReason.CONTRADICTORY_CASE_ENTRY,
                f"expected output {self.output_id} is derived and declares real provenance",
            )
        if not derived and self.provenance is DatasetProvenance.SYNTHETIC:
            raise _refuse(
                RefusalReason.CONTRADICTORY_CASE_ENTRY,
                f"expected output {self.output_id} declares synthetic provenance and a captured origin",
            )


@dataclass(frozen=True)
class CaseFacts:
    """What one scenario case supplies to readiness, as verification-domain values."""

    datasets: tuple[CaseDataset, ...] = ()
    expected_outputs: tuple[CaseExpectedOutput, ...] = ()
    checkpoints: tuple[str, ...] = ()
    result_status: VerificationStatus | None = None

    def __post_init__(self) -> None:
        _required_tuple(self.datasets, "the datasets of a case")
        _required_tuple(self.expected_outputs, "the expected outputs of a case")
        _required_tuple(self.checkpoints, "the checkpoints of a case")
        self._named_once(self.datasets, "dataset_id", "dataset")
        self._named_once(self.expected_outputs, "output_id", "expected output")
        for checkpoint in self.checkpoints:
            _required_text(checkpoint, "a case checkpoint identity")
        if len(set(self.checkpoints)) != len(self.checkpoints):
            raise _refuse(RefusalReason.CONTRADICTORY_CASE_ENTRY, "a case declares one checkpoint twice")
        if self.result_status is not None:
            _required_member(self.result_status, VerificationStatus, "a case result status")

    @staticmethod
    def _named_once(entries: tuple[object, ...], attribute: str, label: str) -> None:
        names = []
        for entry in entries:
            if not hasattr(entry, attribute):
                raise _refuse(RefusalReason.INVALID_INPUT, f"a case {label} must be a declared case {label}")
            names.append(getattr(entry, attribute))
        if len(set(names)) != len(names):
            raise _refuse(RefusalReason.CONTRADICTORY_CASE_ENTRY, f"a case declares one {label} twice")


@dataclass(frozen=True)
class ReadinessFact:
    """One row of a segment's fact table and the evidence behind it."""

    kind: FactKind
    subject: str
    evidence: FactEvidence

    @property
    def satisfied(self) -> bool:
        """Whether the fact is satisfied at all, on real or synthetic evidence."""
        return self.evidence is not FactEvidence.MISSING


@dataclass(frozen=True)
class ReadinessGap:
    """One missing fact, who to suggest for it, and the work it suggests.

    A gap whose segment is None belongs to the use case rather than to one
    segment, because the fact it names is not the boundary of any derived span.
    """

    kind: FactKind
    subject: str
    segment_id: str | None
    suggested_owner: Actor | None
    synthetic_fillable: bool
    suggested_title: str


@dataclass(frozen=True)
class SegmentReadiness:
    """One lineage span: what it can do now, on what facts, and what is missing."""

    segment_id: str
    reaches: SegmentBoundary
    route: BuildRoute | None
    state: SegmentState
    diagnostic_strength: DiagnosticStrength
    acceptable_now: bool
    facts: tuple[ReadinessFact, ...]
    gaps: tuple[ReadinessGap, ...]


@dataclass(frozen=True)
class OpenCondition:
    """One standing condition still unanswered, and what stands in for it."""

    key: ConditionKey
    default_value: str
    value: str


@dataclass(frozen=True)
class ReadinessProjection:
    """The readiness of one use case: its segments, its gaps and its open questions."""

    use_case_id: str
    segments: tuple[SegmentReadiness, ...]
    use_case_gaps: tuple[ReadinessGap, ...]
    open_conditions: tuple[OpenCondition, ...]

    @property
    def gaps(self) -> tuple[ReadinessGap, ...]:
        """Every gap, the use-case gaps first, then each segment's own in span order."""
        return (*self.use_case_gaps, *(gap for segment in self.segments for gap in segment.gaps))

    @property
    def buildable(self) -> bool:
        """Whether at least one segment can be built now."""
        return any(segment.state is not SegmentState.GAPPED for segment in self.segments)

    @property
    def acceptable_now(self) -> bool:
        """Whether at least one segment carries a passing result for every case that covers it."""
        return any(segment.acceptable_now for segment in self.segments)

    @property
    def suggested_disposition(self) -> str:
        """The advice this projection suggests, in one line owned here.

        A route that cuts a version stores this text as it is given. It is
        advice in the same class as diagnostic advice and decides nothing.
        """
        total = len(self.segments)
        buildable = sum(1 for segment in self.segments if segment.state is not SegmentState.GAPPED)
        fallbacks = sum(
            1 for segment in self.segments if segment.state is SegmentState.BUILDABLE_WITH_FALLBACKS
        )
        acceptable = sum(1 for segment in self.segments if segment.acceptable_now)
        return "; ".join(
            (
                f"{buildable} of {_plural(total, 'segment')} buildable",
                f"{fallbacks} built on labelled fallbacks",
                f"{_plural(len(self.gaps), 'gap')} outstanding",
                f"{_plural(len(self.open_conditions), 'condition')} open",
                f"{acceptable} acceptable now",
            )
        )


def project_readiness(use_case: UseCase, case_index: Mapping[Identity, CaseFacts]) -> ReadinessProjection:
    """Project the readiness of one use case from its record and a case index.

    The index maps each scenario case identity the use case references to the
    facts that case supplies: its dataset roles and provenance, its expected
    outputs and their origins, its checkpoints, and its recorded result status.
    The function reads nothing else, writes nothing and draws no clock value.
    """
    if not isinstance(use_case, UseCase):
        raise _refuse(RefusalReason.INVALID_INPUT, "a use case is required")
    index = _validated_index(use_case, case_index)
    datasets = {placeholder.placeholder_id: placeholder for placeholder in use_case.datasets}
    outputs = {output.output_id: output for output in use_case.target_outputs}
    segments = tuple(
        _segment_readiness(use_case, span, index, datasets, outputs) for span in use_case.segments()
    )
    return ReadinessProjection(
        use_case_id=use_case.identity.identifier,
        segments=segments,
        use_case_gaps=_use_case_gaps(use_case),
        open_conditions=_open_conditions(use_case),
    )


def render_projection(projection: ReadinessProjection) -> bytes:
    """Return the canonical bytes of one projection.

    The bytes are one JSON object with keys in code-point order, no spaces
    between members, every character in printable ASCII, and a closing line
    feed. Every leaf is a plain value or the text its own enumeration declares.
    """
    if not isinstance(projection, ReadinessProjection):
        raise _refuse(RefusalReason.INVALID_INPUT, "a readiness projection is required")
    payload = {
        "form": READINESS_PROJECTION_FORM,
        "use_case_id": projection.use_case_id,
        "buildable": projection.buildable,
        "acceptable_now": projection.acceptable_now,
        "suggested_disposition": projection.suggested_disposition,
        "segments": [_segment_node(segment) for segment in projection.segments],
        "use_case_gaps": [_gap_node(gap) for gap in projection.use_case_gaps],
        "open_conditions": [
            {
                "key": condition.key.value,
                "default_value": condition.default_value,
                "value": condition.value,
            }
            for condition in projection.open_conditions
        ],
    }
    written = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return written.encode("ascii") + b"\n"


def projection_digest(projection: ReadinessProjection) -> str:
    """Return the digest of exactly the bytes the projection renders."""
    fingerprint = hashlib.blake2b(render_projection(projection), digest_size=DIGEST_SIZE_BYTES)
    return fingerprint.hexdigest()


def _segment_node(segment: SegmentReadiness) -> dict[str, object]:
    return {
        "segment_id": segment.segment_id,
        "reaches": segment.reaches.value,
        "route": None if segment.route is None else segment.route.value,
        "state": segment.state.value,
        "diagnostic_strength": segment.diagnostic_strength.value,
        "acceptable_now": segment.acceptable_now,
        "facts": [
            {"kind": fact.kind.value, "subject": fact.subject, "evidence": fact.evidence.value}
            for fact in segment.facts
        ],
        "gaps": [_gap_node(gap) for gap in segment.gaps],
    }


def _gap_node(gap: ReadinessGap) -> dict[str, object]:
    return {
        "kind": gap.kind.value,
        "subject": gap.subject,
        "segment_id": gap.segment_id,
        "suggested_owner": None if gap.suggested_owner is None else gap.suggested_owner.identity,
        "synthetic_fillable": gap.synthetic_fillable,
        "suggested_title": gap.suggested_title,
    }


def _validated_index(
    use_case: UseCase, case_index: Mapping[Identity, CaseFacts]
) -> Mapping[Identity, CaseFacts]:
    """Read the supplied index, refusing anything it cannot mean."""
    if not isinstance(case_index, Mapping):
        raise _refuse(RefusalReason.INVALID_INPUT, "the case index must be a mapping of case identity to facts")
    referenced = {scenario.case for scenario in use_case.scenarios}
    recorded = {result.case: result.status for result in use_case.scenario_results}
    for case, facts in case_index.items():
        if not isinstance(case, Identity):
            raise _refuse(RefusalReason.INVALID_INPUT, "the case index is keyed by case identity")
        if not isinstance(facts, CaseFacts):
            raise _refuse(RefusalReason.INVALID_INPUT, f"case {case.identifier} supplies no declared case facts")
        if case not in referenced:
            raise _refuse(
                RefusalReason.UNKNOWN_CASE_IDENTITY,
                f"the case index names case {case.identifier}, which the use case does not reference",
            )
        held = recorded.get(case)
        if held is not None and facts.result_status is not None and facts.result_status is not held:
            raise _refuse(
                RefusalReason.CONTRADICTORY_CASE_ENTRY,
                f"case {case.identifier} supplies a status the use case does not record for it",
            )
    return case_index


def _open_conditions(use_case: UseCase) -> tuple[OpenCondition, ...]:
    """The standing conditions still unanswered, in the order they were recorded."""
    return tuple(
        OpenCondition(
            key=condition.key,
            default_value=str(condition.default_value),
            value=condition.effective_value,
        )
        for condition in use_case.conditions
        if condition.state is ConditionState.UNKNOWN
    )


def _use_case_gaps(use_case: UseCase) -> tuple[ReadinessGap, ...]:
    """The gaps that belong to the use case rather than to one derived span.

    A use case with no target output has no defined end, so no span reaches one
    and the gap has no segment to hang on.
    """
    if use_case.target_outputs:
        return ()
    subject = use_case.identity.identifier
    return (_gap(use_case, FactKind.OUTPUT_DEFINITION, subject, None, None),)


def _gap(
    use_case: UseCase,
    kind: FactKind,
    subject: str,
    segment_id: str | None,
    declared_owner: Actor | None,
) -> ReadinessGap:
    return ReadinessGap(
        kind=kind,
        subject=subject,
        segment_id=segment_id,
        suggested_owner=_suggested_owner(use_case, kind, subject, declared_owner),
        synthetic_fillable=SYNTHETIC_FILLABLE[kind],
        suggested_title=suggested_item_title(kind, subject),
    )


def _suggested_owner(
    use_case: UseCase, kind: FactKind, subject: str, declared_owner: Actor | None
) -> Actor | None:
    """Suggest who owns the work: the declaration's own owner, else an authority."""
    if declared_owner is not None:
        return declared_owner
    for role in GAP_OWNER_ROLES[kind]:
        if role is AuthorityRole.EVIDENCE_OWNER:
            owner = _evidence_owner(use_case, subject)
            if owner is not None:
                return owner
            continue
        for authority in use_case.authorities:
            if authority.role is role:
                return authority.actor
    return None


def _evidence_owner(use_case: UseCase, subject: str) -> Actor | None:
    """The one rule for reading the named evidence owner of a subject."""
    for authority in use_case.authorities:
        if authority.role is AuthorityRole.EVIDENCE_OWNER and authority.subject == subject:
            return authority.actor
    return None


def _dataset_evidence(placeholder: DatasetPlaceholder, index: Mapping[Identity, CaseFacts]) -> FactEvidence:
    """Read one declared dataset: in hand, filled synthetically, or missing."""
    availability = placeholder.availability
    _required_member(availability.state, AvailabilityState, "a dataset availability state")
    evidence = AVAILABILITY_EVIDENCE.get(availability.state)
    if evidence is None:
        raise _refuse(
            RefusalReason.UNDECLARED_REPRESENTATION,
            f"no evidence rule is declared for availability state {availability.state.value}",
        )
    if evidence is not FactEvidence.REAL:
        return evidence
    for facts in index.values():
        for entry in facts.datasets:
            if entry.dataset_id == placeholder.placeholder_id and entry.provenance is not DatasetProvenance.REAL:
                return FactEvidence.SYNTHETIC
    return FactEvidence.REAL


def _expected_output_evidence(output_id: str, index: Mapping[Identity, CaseFacts]) -> FactEvidence:
    """Read the expected output for one target output across every case that holds it."""
    declared = [
        entry for facts in index.values() for entry in facts.expected_outputs if entry.output_id == output_id
    ]
    if not declared or any(entry.origin is None for entry in declared):
        return FactEvidence.MISSING
    synthetic = any(
        entry.origin in DERIVED_ORIGINS or entry.provenance is not DatasetProvenance.REAL
        for entry in declared
    )
    return FactEvidence.SYNTHETIC if synthetic else FactEvidence.REAL


def _output_definition_evidence(output: TargetOutput) -> FactEvidence:
    """Read whether a declared target output says what defines it.

    The shape is part of being a target output and cannot be absent from the
    record. What defines the output can be: a greenfield output names the
    specification or golden example it is built to, and a modernisation target
    names the output it replaces.
    """
    if output.defined_by is not None or output.replaces is not None:
        return FactEvidence.REAL
    return FactEvidence.MISSING


def _covering_cases(span: Segment, index: Mapping[Identity, CaseFacts]) -> list[CaseFacts]:
    """The cases that judge one span, read from what each case declares it holds."""
    if span.reaches is SegmentBoundary.TARGET_OUTPUT:
        return [
            facts
            for facts in index.values()
            if any(entry.output_id == span.segment_id for entry in facts.expected_outputs)
        ]
    return [facts for facts in index.values() if span.segment_id in facts.checkpoints]


def _dataset_fact(placeholder: DatasetPlaceholder, index: Mapping[Identity, CaseFacts]) -> ReadinessFact:
    """Read one declared dataset under the fact row its role belongs to."""
    _required_member(placeholder.role, DatasetRole, "a dataset role")
    kind = DATASET_FACT_KINDS.get(placeholder.role)
    if kind is None:
        raise _refuse(
            RefusalReason.UNDECLARED_REPRESENTATION,
            f"no fact row is declared for dataset role {placeholder.role.value}",
        )
    return ReadinessFact(
        kind=kind,
        subject=placeholder.placeholder_id,
        evidence=_dataset_evidence(placeholder, index),
    )


def _checkpoint_evidence(use_case: UseCase, step_id: str, index: Mapping[Identity, CaseFacts]) -> FactEvidence:
    """A step is checkpointed when it has a named evidence owner and a case declares it."""
    owned = _evidence_owner(use_case, step_id) is not None
    declared = any(step_id in facts.checkpoints for facts in index.values())
    return FactEvidence.REAL if owned and declared else FactEvidence.MISSING


def _combination_fact(span: Segment) -> ReadinessFact | None:
    """Read how one span's sources come together, where it reads more than one.

    A span reading one source has nothing to combine and is not read for this
    row. A span reading several is read for it, and the declaration the record
    carries under the span's own name is what satisfies it. Its absence is a
    listed gap, never a state the span cannot leave.
    """
    if len(span.sources) < 2:
        return None
    declared = span.combination is not None
    return ReadinessFact(
        kind=FactKind.SOURCE_COMBINATION,
        subject=span.segment_id,
        evidence=FactEvidence.REAL if declared else FactEvidence.MISSING,
    )


def _segment_facts(
    use_case: UseCase,
    span: Segment,
    index: Mapping[Identity, CaseFacts],
    datasets: Mapping[str, DatasetPlaceholder],
    outputs: Mapping[str, TargetOutput],
) -> tuple[tuple[ReadinessFact, Actor | None], ...]:
    """Read the fact table of one span, each row beside the owner it already names."""
    rows: list[tuple[ReadinessFact, Actor | None]] = []
    for source in sorted(span.sources):
        placeholder = datasets.get(source)
        if placeholder is None:
            continue  # The source is the boundary the previous span reached.
        rows.append((_dataset_fact(placeholder, index), placeholder.access_owner))
    combination = _combination_fact(span)
    if combination is not None:
        rows.append((combination, None))
    boundary = span.segment_id
    if span.reaches is SegmentBoundary.TARGET_OUTPUT:
        definition = _output_definition_evidence(outputs[boundary])
        expected = _expected_output_evidence(boundary, index)
        rows.append((ReadinessFact(FactKind.OUTPUT_DEFINITION, boundary, definition), None))
        rows.append((ReadinessFact(FactKind.EXPECTED_OUTPUT, boundary, expected), None))
        return tuple(rows)
    # A named step is the definition of its own boundary.
    rows.append((ReadinessFact(FactKind.OUTPUT_DEFINITION, boundary, FactEvidence.REAL), None))
    checkpoint = _checkpoint_evidence(use_case, boundary, index)
    rows.append((ReadinessFact(FactKind.CHECKPOINT, boundary, checkpoint), None))
    return tuple(rows)


def _segment_state(facts: tuple[ReadinessFact, ...]) -> SegmentState:
    """Decide what one span can do from its own fact table.

    The output definition is the only hard floor. Every other missing fact has
    a fallback: a synthetic dataset or a derived expected output keeps the span
    building on labelled evidence, and a span with no checkpoint or no declared
    source combination still builds, the first running output-only and the
    second carrying the question as a listed gap.
    """
    for fact in facts:
        if fact.kind is FactKind.OUTPUT_DEFINITION and not fact.satisfied:
            return SegmentState.GAPPED
    for fact in facts:
        if fact.evidence is FactEvidence.SYNTHETIC:
            return SegmentState.BUILDABLE_WITH_FALLBACKS
        if not fact.satisfied and SYNTHETIC_FILLABLE[fact.kind]:
            return SegmentState.BUILDABLE_WITH_FALLBACKS
    return SegmentState.BUILDABLE


def _segment_readiness(
    use_case: UseCase,
    span: Segment,
    index: Mapping[Identity, CaseFacts],
    datasets: Mapping[str, DatasetPlaceholder],
    outputs: Mapping[str, TargetOutput],
) -> SegmentReadiness:
    rows = _segment_facts(use_case, span, index, datasets, outputs)
    facts = tuple(fact for fact, _ in rows)
    gaps = tuple(
        _gap(use_case, fact.kind, fact.subject, span.segment_id, owner)
        for fact, owner in rows
        if not fact.satisfied
    )
    state = _segment_state(facts)
    checkpointed = any(fact.kind is FactKind.CHECKPOINT and fact.satisfied for fact in facts)
    covering = _covering_cases(span, index)
    acceptable = (
        state is not SegmentState.GAPPED
        and bool(covering)
        and all(facts_for_case.result_status is VerificationStatus.PASS for facts_for_case in covering)
    )
    return SegmentReadiness(
        segment_id=span.segment_id,
        reaches=span.reaches,
        route=None if span.route is None else span.route.route,
        state=state,
        diagnostic_strength=(
            DiagnosticStrength.CHECKPOINTED if checkpointed else DiagnosticStrength.OUTPUT_ONLY
        ),
        acceptable_now=acceptable,
        facts=facts,
        gaps=gaps,
    )
