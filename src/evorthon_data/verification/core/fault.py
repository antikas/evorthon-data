"""Deterministic fault classification and the smallest safe investigation packet.

This module answers two questions over evidence the verification domain has
already produced: what class of fault the evidence shows, and what the smallest
record is that a person or an adviser can read without receiving the data
itself. It compares nothing, it reads no artefact, and it decides nothing about
acceptance.

The classification is a pure function from declared results to one member of the
closed fault vocabulary. It reads four kinds of evidence and nothing else: the
independently derived receipts of the run, the reconciled findings of the failed
output, the declared checkpoint comparisons for its lineage, and the
localisation that follows from them. It runs in a declared order and the first
rule that decides wins, so one set of evidence always produces one class.

1. What the run read. A receipt whose observed digest differs from the identity
   it answers for says the run did not read what the case froze, so the class is
   the identity of that subject and no later rule can override it. The receipt's
   own deriver writes the digest it observed into the identity it answers for,
   so the two agree for an unaltered declaration and differ only for a receipt
   taken over an altered one. A declared replay whose observed inputs or context
   differ from the frozen ones says the same thing in the comparison engine's
   own words.
2. Where the state diverged. A confirmed localisation whose later boundary is a
   checkpoint that declares a replay of its own, and whose comparison failed,
   places the fault in retained state rather than in the final transformation.
3. What the output shows. The failing findings, read by their declared
   comparison dimension in a fixed precedence, so that a difference in the
   declared shape is read before a difference in the population, and both
   before a difference in a single value.
4. Unknown. When no rule above decides, the class is unknown. Unknown is a real
   answer and never a guess: a value that differs, or a control total that
   differs with no row behind it, does not say which of the declared causes
   produced it.

Two refinements sit inside the third step and are declared here rather than
inferred from any text. A population that both lost keys and gained them is a
boundary that moved, not a population that shrank or grew. A field whose
declared nullability differs between the approved schema and the observed one,
and which also carries a failing value difference, is a default or null
substitution rather than a plain shape difference.

The packet is the domain's own fault record. It carries the class, the scope as
counts and declared names, the evidence for and the evidence against as
references to the domain's records by identity and digest, the localisation, and
a disclosure decision from a policy with declared thresholds. Every evidence
reference is rebuilt so that it carries the referenced record's identity and
digest with a declared summary of its own; no approved text travels inside a
packet unread. The packet carries no row, no key, no field value and no
approved summary from the case.

The disclosure policy has two thresholds and one honest refusal. A packet whose
observed rows number fewer than the declared floor withholds the small cell. A
packet with more differences than the declared ceiling cannot be carried inside
the declared bound and is withheld by policy. A packet whose class is unknown
has nothing decided to disclose. Nothing is withheld, weakened or refused for
being synthetic, derived or inferred: weak evidence lowers the declared
confidence and never closes the packet.

The module reads no file, no clock, no environment and no locale, and it draws
no random value. Two builds over the same evidence produce identical records.
"""
# evorthon-implements: EVD-README-022
from __future__ import annotations

# evorthon-component: verification_core

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from evorthon_data.verification.core.canonical import record_digest
from evorthon_data.verification.core.localisation import CheckpointComparison, OutputLocalisation
from evorthon_data.verification.core.reconciliation import Finding, FindingKind, FindingSeverity
from evorthon_data.verification.domain.contracts import (
    AdviserConfidence,
    ComparisonDimension,
    DatasetRole,
    DiagnosticLocalisation,
    DisclosureDecision,
    EvidenceReference,
    FaultClass,
    FaultRecord,
    Identity,
    LineageFrontier,
    LocalisationStatus,
    ParityClause,
    ReceiptSubject,
    UncoveredPath,
    VerificationCase,
    VerificationResult,
    VerificationStatus,
)

FAULT_PACKET_FORM = "evorthon.verification.fault.v1"

# The declared disclosure thresholds. The floor is the smallest number of
# distinct observed rows a packet may describe; a smaller cohort is a small
# cell and is withheld. The ceiling is the largest number of distinct
# differences a bounded packet can stand for; more than that is withheld by
# policy rather than summarised into something nobody declared.
SMALL_CELL_FLOOR = 5
DISCLOSURE_CEILING = 50

# The declared maximum number of evidence references a packet carries on each
# side of the argument. The scope states the totals those examples stand for.
MAX_DISCLOSED_EXAMPLES = 8

# The declared maximum shape of the localisation a packet carries. These
# mirror the bounds the privacy gate enforces at the boundary, because the
# builder may not emit a packet its own gate would refuse and the core may not
# reach the enforcement package. One test pins the two owners to each other.
MAX_EVIDENCE_REFERENCES = 16
MAX_FRONTIER_CHECKPOINTS = 16
MAX_UNCOVERED_PATHS = 16
MAX_CHECKPOINTS_PER_PATH = 32

# The locators the comparison engine writes for a declared replay. They are
# named here so a replay difference can be read as an identity difference in
# the declared input, the declared context, or the declared output shape.
REPLAY_CONTEXT_LOCATOR = "context"
REPLAY_INPUT_LOCATOR_PREFIX = "inputs/"
REPLAY_OUTPUT_SHAPE_LOCATOR = "output_shape"

# The declared summaries a packet writes for itself. A packet never carries the
# approved text of a case, so every reference it holds says only what the
# reference stands for.
SUPPORTING_SUMMARY = "observed evidence for a comparison this packet reports as failing"
CONTRADICTING_SUMMARY = "observed evidence for a comparison this packet reports as matching"
UPPER_FRONTIER_SUMMARY = "evidence at the later lineage boundary of this fault"
LOWER_FRONTIER_SUMMARY = "evidence at the earlier lineage boundary of this fault"
UNCOVERED_PATH_SUMMARY = "evidence for a lineage path this fault could not separate"
LOCALISATION_SUMMARY = "evidence the localisation of this fault rests on"

RECEIPT_FAULT_CLASS = MappingProxyType(
    {
        ReceiptSubject.INPUT: FaultClass.INPUT_IDENTITY,
        ReceiptSubject.REFERENCE: FaultClass.REFERENCE_IDENTITY,
        ReceiptSubject.ENRICHMENT: FaultClass.REFERENCE_IDENTITY,
        ReceiptSubject.PRIOR_STATE: FaultClass.REFERENCE_IDENTITY,
        ReceiptSubject.CONTEXT: FaultClass.RUNTIME_CONFIGURATION_DRIFT,
    }
)
DATASET_ROLE_FAULT_CLASS = MappingProxyType(
    {
        DatasetRole.INPUT: FaultClass.INPUT_IDENTITY,
        DatasetRole.REFERENCE: FaultClass.REFERENCE_IDENTITY,
        DatasetRole.ENRICHMENT: FaultClass.REFERENCE_IDENTITY,
        DatasetRole.PRIOR_STATE: FaultClass.REFERENCE_IDENTITY,
    }
)

# The declared order in which a failing difference is read. A difference in the
# declared shape is read before a difference in the population, and both before
# a difference in one value, because the earlier classes explain the later ones
# and never the other way round.
DIMENSION_PRECEDENCE = (
    ComparisonDimension.SCHEMA,
    ComparisonDimension.KEY,
    ComparisonDimension.JOIN_CARDINALITY,
    ComparisonDimension.POPULATION,
    ComparisonDimension.EFFECTIVE_TIME,
    ComparisonDimension.CALCULATION,
    ComparisonDimension.ORDERING,
    ComparisonDimension.OUTPUT_FORMAT,
    ComparisonDimension.VALUE,
    ComparisonDimension.AGGREGATE,
)
# The last two entries are the dimensions that decide nothing on their own, so
# their order relative to each other carries no meaning: either reading
# answers that the evidence does not decide.
UNDECIDED_DIMENSIONS = (ComparisonDimension.VALUE, ComparisonDimension.AGGREGATE)
_RECEIPT_ORDER = MappingProxyType(
    {subject: index for index, subject in enumerate(ReceiptSubject)}
)
_ROLE_ORDER = MappingProxyType({role: index for index, role in enumerate(DatasetRole)})


class FaultRefusalReason(str, Enum):
    """The closed set of integrity reasons for refusing to build a packet."""

    UNRESOLVED_OUTPUT = "unresolved-output"
    UNRESOLVED_CHECKPOINT = "unresolved-checkpoint"
    CONTRADICTORY_COMPARISON = "contradictory-comparison"
    NOT_A_FAILED_OUTPUT = "not-a-failed-output"
    DECLARED_BOUND_EXCEEDED = "declared-bound-exceeded"


class FaultRefused(ValueError):
    """Raised when a packet cannot be built with declared meaning."""

    def __init__(self, reason: FaultRefusalReason, subject: str, detail: str) -> None:
        super().__init__(f"{reason.value} at {subject}: {detail}")
        self.reason = reason
        self.subject = subject
        self.detail = detail


@dataclass(frozen=True)
class FaultEvidence:
    """Everything one packet is built from, all of it already produced.

    ``findings`` may hold the findings of a whole run; the packet reads the
    ones that name its own output. ``checkpoint_comparisons`` holds the
    comparisons the lineage walk rested on, the supplied ones and any a
    declared replay produced.
    """

    case: VerificationCase
    result: VerificationResult
    output_id: str
    findings: tuple[Finding, ...]
    localisation: DiagnosticLocalisation
    checkpoint_comparisons: tuple[CheckpointComparison, ...] = ()


def _refuse(reason: FaultRefusalReason, subject: str, detail: str) -> FaultRefused:
    return FaultRefused(reason, subject, detail)


def _parity_clause_outputs(case: VerificationCase) -> dict[str, str]:
    """Return the expected output every declared parity clause answers for."""
    return {
        clause.clause_id: clause.expected_output_id
        for clause in case.comparison_policy.clauses
        if isinstance(clause, ParityClause)
    }


def _own_findings(evidence: FaultEvidence) -> tuple[Finding, ...]:
    """Return the findings that name this packet's output, in a stable order."""
    return tuple(
        sorted(
            (finding for finding in evidence.findings if finding.output_id == evidence.output_id),
            key=lambda finding: (finding.dimension.value, finding.kind.value, finding.clause_id, finding.locator),
        )
    )


def _failing(findings: Sequence[Finding]) -> tuple[Finding, ...]:
    return tuple(finding for finding in findings if finding.severity is FindingSeverity.FAILING)


def _own_outcomes(evidence: FaultEvidence, status: VerificationStatus) -> tuple[str, ...]:
    """Return the clause outcomes of this output that carry one declared status."""
    outputs = _parity_clause_outputs(evidence.case)
    return tuple(
        sorted(
            outcome.outcome_id
            for outcome in evidence.result.clause_outcomes
            if outcome.status is status and outputs.get(outcome.clause.identifier) == evidence.output_id
        )
    )


def _mismatched_receipts(evidence: FaultEvidence):
    """Return the receipts whose observed digest is not the identity they answer for."""
    return sorted(
        (
            receipt
            for receipt in evidence.result.independent_receipts
            if receipt.observed_digest != receipt.subject_identity.digest
        ),
        key=lambda receipt: (_RECEIPT_ORDER[receipt.subject], receipt.receipt_id),
    )


def _identity_class(evidence: FaultEvidence) -> FaultClass | None:
    """Return the class of a run that did not read what the case froze."""
    for receipt in _mismatched_receipts(evidence):
        return RECEIPT_FAULT_CLASS[receipt.subject]
    roles: dict[str, set[DatasetRole]] = {}
    for dataset in evidence.case.frozen_datasets:
        roles.setdefault(dataset.dataset_id, set()).add(dataset.role)
    for finding in _failing(_own_findings(evidence)):
        if finding.kind is not FindingKind.REPLAY_METADATA_DIVERGENCE:
            continue
        if finding.locator == REPLAY_CONTEXT_LOCATOR:
            return FaultClass.RUNTIME_CONFIGURATION_DRIFT
        if finding.locator == REPLAY_OUTPUT_SHAPE_LOCATOR:
            return FaultClass.SCHEMA_COERCION
        if finding.locator.startswith(REPLAY_INPUT_LOCATOR_PREFIX):
            declared = roles.get(finding.locator[len(REPLAY_INPUT_LOCATOR_PREFIX) :])
            if declared:
                return DATASET_ROLE_FAULT_CLASS[min(declared, key=lambda role: _ROLE_ORDER[role])]
    return None


def _state_replay_class(evidence: FaultEvidence) -> FaultClass | None:
    """Return the state class when a declared replay confirms the later boundary."""
    if evidence.localisation.status is not LocalisationStatus.CONFIRMED:
        return None
    declared = {
        checkpoint.checkpoint_id: checkpoint for checkpoint in evidence.case.lineage.checkpoints
    }
    held = {comparison.checkpoint_id: comparison for comparison in evidence.checkpoint_comparisons}
    for frontier in evidence.localisation.upper_frontier:
        checkpoint = declared.get(frontier.checkpoint_id)
        comparison = held.get(frontier.checkpoint_id)
        if checkpoint is None or comparison is None or checkpoint.replay is None:
            continue
        if comparison.status is VerificationStatus.FAIL:
            return FaultClass.STATE_REPLAY
    return None


def _nullability_divergent_fields(evidence: FaultEvidence) -> set[str]:
    """Return the fields whose declared null policy differs from the observed one."""
    observed = {output.output_id: output for output in evidence.result.actual_outputs}.get(
        evidence.output_id
    )
    if observed is None:
        return set()
    seen = {field.field_id: field.nullable for field in observed.schema.fields}
    divergent: set[str] = set()
    for clause in evidence.case.comparison_policy.clauses:
        if not isinstance(clause, ParityClause) or clause.expected_output_id != evidence.output_id:
            continue
        for field in clause.comparison.schema.fields:
            if field.field_id in seen and seen[field.field_id] != field.nullable:
                divergent.add(field.field_id)
    return divergent


def _population_class(findings: Sequence[Finding]) -> FaultClass:
    kinds = {finding.kind for finding in findings}
    missing = FindingKind.POPULATION_ROW_MISSING in kinds
    additional = FindingKind.POPULATION_ROW_ADDITIONAL in kinds
    if missing and additional:
        return FaultClass.FILTER_WINDOW_BOUNDARY
    return FaultClass.MISSING_POPULATION if missing else FaultClass.ADDITIONAL_POPULATION


def _key_class(findings: Sequence[Finding]) -> FaultClass:
    kinds = {finding.kind for finding in findings}
    if FindingKind.KEY_DUPLICATE in kinds:
        return FaultClass.DUPLICATE_JOIN_CARDINALITY
    return FaultClass.SCHEMA_COERCION


def _finding_class(evidence: FaultEvidence) -> FaultClass | None:
    """Return the class the failing differences of this output declare."""
    failing = _failing(_own_findings(evidence))
    if not failing:
        return None
    grouped: dict[ComparisonDimension, list[Finding]] = {}
    for finding in failing:
        grouped.setdefault(finding.dimension, []).append(finding)
    valued = {
        finding.locator
        for finding in failing
        if finding.dimension in (ComparisonDimension.VALUE, ComparisonDimension.CALCULATION)
    }
    if ComparisonDimension.SCHEMA in grouped and _nullability_divergent_fields(evidence) & valued:
        return FaultClass.DEFAULT_NULL
    for dimension in DIMENSION_PRECEDENCE:
        held = grouped.get(dimension)
        if not held:
            continue
        if dimension is ComparisonDimension.SCHEMA:
            return FaultClass.SCHEMA_COERCION
        if dimension is ComparisonDimension.KEY:
            return _key_class(held)
        if dimension is ComparisonDimension.JOIN_CARDINALITY:
            return FaultClass.DUPLICATE_JOIN_CARDINALITY
        if dimension is ComparisonDimension.POPULATION:
            return _population_class(held)
        if dimension is ComparisonDimension.EFFECTIVE_TIME:
            return FaultClass.TEMPORAL_EFFECTIVE_DATE
        if dimension is ComparisonDimension.CALCULATION:
            return FaultClass.CALCULATION_PRECISION_ROUNDING
        if dimension is ComparisonDimension.ORDERING:
            return FaultClass.NONDETERMINISTIC_ORDERING
        if dimension is ComparisonDimension.OUTPUT_FORMAT:
            return FaultClass.OUTPUT_FORMATTING
        # A value that differs, and a control total with no row behind it, do
        # not say which declared cause produced them.
        return None
    return None


def classify_fault(evidence: FaultEvidence) -> FaultClass:
    """Return the one declared class the evidence of this output supports."""
    _confirm(evidence)
    for rule in (_identity_class, _state_replay_class, _finding_class):
        decided = rule(evidence)
        if decided is not None:
            return decided
    return FaultClass.UNKNOWN


def declare_confidence(evidence: FaultEvidence) -> AdviserConfidence:
    """Return the calibrated confidence the evidence of this output supports.

    Confidence follows how far the declared lineage narrowed the fault and
    whether the class is decided. It never follows how the evidence was
    produced: real, synthetic and derived evidence of the same shape declare
    the same confidence.
    """
    if classify_fault(evidence) is FaultClass.UNKNOWN:
        return AdviserConfidence.UNKNOWN
    status = evidence.localisation.status
    if status is LocalisationStatus.UNKNOWN:
        return AdviserConfidence.UNKNOWN
    if status is LocalisationStatus.CONFIRMED:
        return AdviserConfidence.HIGH
    return AdviserConfidence.LOW if evidence.localisation.uncovered_paths else AdviserConfidence.MEDIUM


def decide_disclosure(
    fault_class: FaultClass, *, distinct_rows: int, distinct_differences: int
) -> DisclosureDecision:
    """Return the declared disclosure decision for one packet's measured scope.

    ``distinct_rows`` counts the observed rows the failing differences name and
    ``distinct_differences`` counts the differences themselves. Both are counts
    of the packet's own scope and never a judgement about the evidence behind
    it.
    """
    if fault_class is FaultClass.UNKNOWN:
        return DisclosureDecision.WITHHOLD_UNKNOWN
    if 0 < distinct_rows < SMALL_CELL_FLOOR:
        return DisclosureDecision.WITHHOLD_SMALL_CELL
    if distinct_differences > DISCLOSURE_CEILING:
        return DisclosureDecision.WITHHOLD_POLICY
    return DisclosureDecision.DISCLOSE


def _rebuilt(references: Sequence[EvidenceReference], summary: str) -> tuple[EvidenceReference, ...]:
    """Return references to the same records, carrying a declared summary only."""
    held: dict[tuple[str, str], EvidenceReference] = {}
    for reference in references:
        key = (reference.evidence_id, reference.digest)
        if key in held:
            continue
        held[key] = EvidenceReference(
            evidence_id=reference.evidence_id,
            version=FAULT_PACKET_FORM,
            digest=reference.digest,
            summary=summary,
        )
    return tuple(held[key] for key in sorted(held))


def _bounded(references: Sequence[EvidenceReference]) -> tuple[EvidenceReference, ...]:
    return tuple(references[:MAX_DISCLOSED_EXAMPLES])


def _safe_frontier(frontiers: Sequence[LineageFrontier], summary: str) -> tuple[LineageFrontier, ...]:
    return tuple(
        LineageFrontier(frontier.checkpoint_id, _rebuilt(frontier.evidence, summary))
        for frontier in frontiers
    )


def _confirm_localisation_bounds(localisation: DiagnosticLocalisation) -> None:
    """Refuse a localisation larger than the declared maximum shape of a packet.

    The builder refuses rather than trimming, because a trimmed lineage
    boundary or a dropped uncovered path would narrow the honest interval by
    silence.
    """
    counted = (
        ("lower_frontier", len(localisation.lower_frontier), MAX_FRONTIER_CHECKPOINTS),
        ("upper_frontier", len(localisation.upper_frontier), MAX_FRONTIER_CHECKPOINTS),
        ("uncovered_paths", len(localisation.uncovered_paths), MAX_UNCOVERED_PATHS),
        ("supporting_evidence", len(localisation.supporting_evidence), MAX_EVIDENCE_REFERENCES),
    )
    for name, measured, maximum in counted:
        if measured > maximum:
            raise _refuse(
                FaultRefusalReason.DECLARED_BOUND_EXCEEDED,
                f"localisation.{name}",
                f"the localisation carries {measured} where the declared bound is {maximum}",
            )
    for path in localisation.uncovered_paths:
        if len(path.checkpoint_ids) > MAX_CHECKPOINTS_PER_PATH:
            raise _refuse(
                FaultRefusalReason.DECLARED_BOUND_EXCEEDED,
                f"localisation.uncovered_paths[{path.path_id}].checkpoint_ids",
                f"the path names {len(path.checkpoint_ids)} checkpoints where the declared bound is {MAX_CHECKPOINTS_PER_PATH}",
            )


def _safe_localisation(localisation: DiagnosticLocalisation) -> DiagnosticLocalisation:
    """Return the localisation with every reference reduced to identity and digest."""
    _confirm_localisation_bounds(localisation)
    return DiagnosticLocalisation(
        localisation_id=localisation.localisation_id,
        version=localisation.version,
        status=localisation.status,
        lower_frontier=_safe_frontier(localisation.lower_frontier, LOWER_FRONTIER_SUMMARY),
        upper_frontier=_safe_frontier(localisation.upper_frontier, UPPER_FRONTIER_SUMMARY),
        uncovered_paths=tuple(
            UncoveredPath(
                path_id=path.path_id,
                checkpoint_ids=path.checkpoint_ids,
                reason=path.reason,
                evidence=_rebuilt(path.evidence, UNCOVERED_PATH_SUMMARY),
            )
            for path in localisation.uncovered_paths
        ),
        supporting_evidence=_rebuilt(localisation.supporting_evidence, LOCALISATION_SUMMARY),
    )


def _outcome_evidence(evidence: FaultEvidence, outcome_ids: Sequence[str]) -> tuple[EvidenceReference, ...]:
    held = {outcome.outcome_id: outcome for outcome in evidence.result.clause_outcomes}
    references: list[EvidenceReference] = []
    for outcome_id in outcome_ids:
        outcome = held.get(outcome_id)
        if outcome is not None:
            references.extend(outcome.observed_evidence)
    return tuple(references)


def _correction_surface(evidence: FaultEvidence) -> Identity | None:
    """Return the transformation a confirmed later boundary names, if it names one."""
    if evidence.localisation.status is not LocalisationStatus.CONFIRMED:
        return None
    if len(evidence.localisation.upper_frontier) != 1:
        return None
    checkpoint_id = evidence.localisation.upper_frontier[0].checkpoint_id
    for checkpoint in evidence.case.lineage.checkpoints:
        if checkpoint.checkpoint_id == checkpoint_id:
            return checkpoint.transformation
    return None


def _scope(
    evidence: FaultEvidence,
    *,
    affected: Sequence[str],
    total_clauses: int,
    dimensions: Sequence[ComparisonDimension],
    differences: int,
    rows: int,
) -> str:
    """Return the declared scope of one packet: names and counts, never a value."""
    named = ", ".join(dimension.value for dimension in dimensions) if dimensions else "none"
    return (
        f"output {evidence.output_id}; "
        f"clauses {len(affected)} of {total_clauses}; "
        f"dimensions {named}; "
        f"differences {differences}; "
        f"rows {rows}; "
        f"localisation {evidence.localisation.status.value}; "
        f"uncovered {len(evidence.localisation.uncovered_paths)}"
    )


def _confirm(evidence: FaultEvidence) -> None:
    """Refuse evidence that cannot produce a packet with declared meaning."""
    subject = f"result.actual_outputs[{evidence.output_id}]"
    if evidence.output_id not in {output.output_id for output in evidence.case.expected_outputs}:
        raise _refuse(
            FaultRefusalReason.UNRESOLVED_OUTPUT,
            subject,
            "the case declares no expected output the packet could answer for",
        )
    declared = {checkpoint.checkpoint_id for checkpoint in evidence.case.lineage.checkpoints}
    held: dict[str, VerificationStatus] = {}
    for comparison in evidence.checkpoint_comparisons:
        if comparison.checkpoint_id not in declared:
            raise _refuse(
                FaultRefusalReason.UNRESOLVED_CHECKPOINT,
                f"checkpoint_comparisons[{comparison.checkpoint_id}]",
                "the comparison names a checkpoint the case does not declare",
            )
        previous = held.setdefault(comparison.checkpoint_id, comparison.status)
        if previous is not comparison.status:
            raise _refuse(
                FaultRefusalReason.CONTRADICTORY_COMPARISON,
                f"checkpoint_comparisons[{comparison.checkpoint_id}]",
                "two comparisons of one checkpoint report different outcomes",
            )


def _confirm_failed(evidence: FaultEvidence) -> tuple[str, ...]:
    """Return the failing clause outcomes of this output, refusing a passing one."""
    affected = _own_outcomes(evidence, VerificationStatus.FAIL)
    if affected:
        return affected
    raise _refuse(
        FaultRefusalReason.NOT_A_FAILED_OUTPUT,
        f"result.clause_outcomes[{evidence.output_id}]",
        "the run reports no failing comparison for the output a packet would answer for",
    )


def build_fault_packet(evidence: FaultEvidence) -> FaultRecord:
    """Return the smallest safe investigation packet for one failed output."""
    _confirm(evidence)
    affected = _confirm_failed(evidence)
    matched = _own_outcomes(evidence, VerificationStatus.PASS)
    findings = _own_findings(evidence)
    failing = _failing(findings)
    fault_class = classify_fault(evidence)
    rows = len({finding.row_digest for finding in failing if finding.row_digest is not None})
    dimensions = tuple(
        dimension for dimension in ComparisonDimension if any(finding.dimension is dimension for finding in failing)
    )
    supporting = _rebuilt(_outcome_evidence(evidence, affected), SUPPORTING_SUMMARY) + _rebuilt(
        tuple(
            reference
            for frontier in evidence.localisation.upper_frontier
            for reference in frontier.evidence
        ),
        UPPER_FRONTIER_SUMMARY,
    )
    contradicting = _rebuilt(_outcome_evidence(evidence, matched), CONTRADICTING_SUMMARY) + _rebuilt(
        tuple(
            reference
            for frontier in evidence.localisation.lower_frontier
            for reference in frontier.evidence
        ),
        LOWER_FRONTIER_SUMMARY,
    )
    total_clauses = len(affected) + len(matched)
    return FaultRecord(
        fault_id=f"{evidence.result.result_id}/{evidence.output_id}",
        version=FAULT_PACKET_FORM,
        result=Identity(
            evidence.result.result_id, evidence.result.version, record_digest(evidence.result)
        ),
        affected_clause_outcome_ids=affected,
        fault_class=fault_class,
        localisation=_safe_localisation(evidence.localisation),
        diagnostic_scope=_scope(
            evidence,
            affected=affected,
            total_clauses=total_clauses,
            dimensions=dimensions,
            differences=len(failing),
            rows=rows,
        ),
        disclosure_decision=decide_disclosure(
            fault_class, distinct_rows=rows, distinct_differences=len(failing)
        ),
        supporting_evidence=_bounded(supporting),
        contradicting_evidence=_bounded(contradicting),
        correction_surface=_correction_surface(evidence),
    )


def build_fault_packets(
    case: VerificationCase,
    result: VerificationResult,
    *,
    findings: Sequence[Finding],
    localisations: Sequence[OutputLocalisation],
    checkpoint_comparisons: Sequence[CheckpointComparison] = (),
) -> tuple[FaultRecord, ...]:
    """Return one packet per localised output, in the order the walk reported."""
    material = tuple(findings)
    comparisons = tuple(checkpoint_comparisons)
    return tuple(
        build_fault_packet(
            FaultEvidence(
                case=case,
                result=result,
                output_id=item.output_id,
                findings=material,
                localisation=item.localisation,
                checkpoint_comparisons=comparisons,
            )
        )
        for item in localisations
    )


def packet_fields(record: FaultRecord) -> Mapping[str, str]:
    """Return the packet as declared text, for a caller that gates it onward.

    The mapping holds the packet's declared names, counts and opaque digests.
    It holds no row, no key, no field value and no approved text of a case.
    """
    return MappingProxyType(
        {
            "fault_id": record.fault_id,
            "packet_form": record.version,
            "result_identity": record.result.identifier,
            "result_digest": record.result.digest,
            "fault_class": record.fault_class.value,
            "disclosure_decision": record.disclosure_decision.value,
            "diagnostic_scope": record.diagnostic_scope,
            "localisation_status": record.localisation.status.value,
            "supporting_evidence_count": str(len(record.supporting_evidence)),
            "contradicting_evidence_count": str(len(record.contradicting_evidence)),
        }
    )


__all__ = [
    "CONTRADICTING_SUMMARY",
    "DATASET_ROLE_FAULT_CLASS",
    "DIMENSION_PRECEDENCE",
    "DISCLOSURE_CEILING",
    "FAULT_PACKET_FORM",
    "FaultEvidence",
    "FaultRefusalReason",
    "FaultRefused",
    "LOCALISATION_SUMMARY",
    "LOWER_FRONTIER_SUMMARY",
    "MAX_CHECKPOINTS_PER_PATH",
    "MAX_DISCLOSED_EXAMPLES",
    "MAX_EVIDENCE_REFERENCES",
    "MAX_FRONTIER_CHECKPOINTS",
    "MAX_UNCOVERED_PATHS",
    "RECEIPT_FAULT_CLASS",
    "REPLAY_CONTEXT_LOCATOR",
    "REPLAY_INPUT_LOCATOR_PREFIX",
    "REPLAY_OUTPUT_SHAPE_LOCATOR",
    "SMALL_CELL_FLOOR",
    "SUPPORTING_SUMMARY",
    "UNCOVERED_PATH_SUMMARY",
    "UNDECIDED_DIMENSIONS",
    "UPPER_FRONTIER_SUMMARY",
    "build_fault_packet",
    "build_fault_packets",
    "classify_fault",
    "decide_disclosure",
    "declare_confidence",
    "packet_fields",
]
