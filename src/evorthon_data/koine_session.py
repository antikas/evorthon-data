"""Provider-neutral, governed lifecycle sessions for the Koine coworker.

The session owns the order in which setup, framing, discovery, design and
delivery-contract records are generated, independently reviewed, and
human-approved.  It deliberately does not own a provider client or an egress
policy: every model call travels through the supplied
:class:`~evorthon_data.security.ModelEgressPort`.

It does own what each call carries.  A generation or review call carries record
identities, digests, declared facts and the questions still open.  On the intake
generator route an admitted artefact's text crosses only as a bounded sample and
only when its handling classification is at or below the level the
authorization's field scope names; nothing else puts artefact text into a call.

A locator travels with each artefact, and the record has already refused every
machine route it declares.  What is left can still read like a dotted server
name with a path or a port after it, or like a connection string, which no
reading can tell from an ordinary written name, so the round reports a warning
beside its crossing report and admits the artefact.
"""
# evorthon-implements: EVD-README-044
# evorthon-implements: EVD-README-041
# evorthon-implements: EVD-README-024
# evorthon-implements: EVD-README-014
# evorthon-implements: EVD-README-006
# evorthon-implements: EVD-README-004
from __future__ import annotations

# evorthon-component: koine_projection

import csv
import hashlib
import io
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import Enum
from types import MappingProxyType
from typing import Any

from .boundary_patterns import (
    ADVISORY_PATTERNS,
    ADVISORY_SHAPES,
    ASSIGNED_SECRET,
    BEARER_AUTHORIZATION,
    CONNECTION_CREDENTIAL,
    KEY_BLOCK,
    shape_carried,
    shapes,
)
from .boundary_patterns import CREDENTIAL_PATTERNS as DECLARED_CREDENTIAL_PATTERNS
from .engagement import (
    Actor,
    ActorKind,
    CheckFamily,
    DecisionKind,
    DiscoveryKind,
    ENGAGEMENT_RECORD_FIELDS,
    Engagement,
    EngagementError,
    EngagementMode,
    ExpectedCheckResult,
    ImmutableReference,
    LifecyclePhase,
    NamedHumanDecision,
    RecordReview,
    ReferenceKind,
    ReviewDisposition,
    StageRecord,
    is_placeholder_identity,
    validate_record_projection,
    validate_success_criterion_contract,
)
from .engagement.use_case import (
    Authority,
    BuildRouteDeclaration,
    CONDITION_DEFAULTS,
    CONTINUITY_OR_ACCIDENT_INTAKE_FIELD,
    CUTOVER_CONDITIONS,
    ConditionDeclaration,
    ConditionKey,
    ConsumerDependency,
    DatasetPlaceholder,
    FactLocator,
    FactProvenance,
    FactStatus,
    INTAKE_PROVENANCE_FIELDS,
    IntakeArtefact,
    IntermediateResult,
    REPLACED_OUTPUT_INTAKE_FIELD,
    ScenarioReference,
    TargetOutput,
    USE_CASE_INTAKE_SECTIONS,
    USE_CASE_INTAKE_TEMPLATE_FIELDS,
    UseCase,
)
from .security import (
    ModelCall,
    ModelCallPurpose,
    ModelDestination,
    ModelEgressAuthorization,
    ModelEgressMode,
    ModelEgressPort,
)


SETUP_GENERATOR_ROUTE = "koine.generate.setup"
OUTCOME_GENERATOR_ROUTE = "koine.generate.outcome"
ESTATE_DISCOVERY_GENERATOR_ROUTE = "koine.generate.estate-discovery"
CAPABILITY_DISCOVERY_GENERATOR_ROUTE = "koine.generate.capability-discovery"
DESIGN_GENERATOR_ROUTE = "koine.generate.design"
DELIVERY_CONTRACT_GENERATOR_ROUTE = "koine.generate.delivery-contract"
SETUP_REVIEW_ROUTE = "koine.review.setup"
OUTCOME_REVIEW_ROUTE = "koine.review.outcome"
ESTATE_DISCOVERY_REVIEW_ROUTE = "koine.review.estate-discovery"
CAPABILITY_DISCOVERY_REVIEW_ROUTE = "koine.review.capability-discovery"
DESIGN_REVIEW_ROUTE = "koine.review.design"
DELIVERY_CONTRACT_REVIEW_ROUTE = "koine.review.delivery-contract"
INTAKE_GENERATOR_ROUTE = "koine.generate.intake"
INTAKE_REVIEW_ROUTE = "koine.review.intake"


class KoineSessionError(ValueError):
    """Raised when a coworker session cannot take the requested governed step."""


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise KoineSessionError(f"{field_name} is required")
    if any(character in value for character in ("\n", "\r", "\x00")):
        raise KoineSessionError(f"{field_name} must not contain a control character")
    return value


def _required_texts(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple) or not values:
        raise KoineSessionError(f"{field_name} must contain at least one value")
    normalized = tuple(_required_text(value, field_name) for value in values)
    if len(normalized) != len(set(normalized)):
        raise KoineSessionError(f"{field_name} must not contain duplicates")
    return normalized


def _optional_texts(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise KoineSessionError(f"{field_name} must be a tuple")
    normalized = tuple(_required_text(value, field_name) for value in values)
    if len(normalized) != len(set(normalized)):
        raise KoineSessionError(f"{field_name} must not contain duplicates")
    return normalized


def _canonical_identifier(value: str, field_name: str) -> str:
    """Require a portable lower-kebab identifier rather than a prose label."""
    identifier = _required_text(value, field_name)
    segments = identifier.split("-")
    if (
        not identifier.isascii()
        or any(
            not segment
            or not segment[0].isalpha()
            or not segment.isalnum()
            or segment != segment.lower()
            for segment in segments
        )
    ):
        raise KoineSessionError(f"{field_name} must be a canonical lower-kebab identifier")
    return identifier


def _named_identifier(value: str, field_name: str) -> str:
    """Return a canonical accountable identity, rejecting placeholder ownership."""
    identifier = _canonical_identifier(value, field_name)
    if is_placeholder_identity(identifier):
        raise KoineSessionError(f"{field_name} must name an accountable identity, not a placeholder")
    return identifier


def _inventory_entry(**values: object) -> str:
    """Return a stable, lossless projection of one structured contract item."""
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _record_content(value: str) -> str:
    """Accept non-empty record text while preserving its authored layout."""
    if not isinstance(value, str) or not value.strip():
        raise KoineSessionError("generated record content is required")
    if "\x00" in value:
        raise KoineSessionError("generated record content must not contain a null character")
    return value


RecordFactValue = str | tuple[str, ...]
OPTIONAL_SEQUENCE_RECORD_FACT_FIELDS = frozenset({"dependency inventory"})


@dataclass(frozen=True)
class RecordFacts:
    """Structured record facts that can be validated independently of prose."""

    entries: tuple[tuple[str, RecordFactValue], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple) or not self.entries:
            raise KoineSessionError("record facts must contain at least one field")
        names: list[str] = []
        normalized: list[tuple[str, RecordFactValue]] = []
        for entry in self.entries:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise KoineSessionError("each record fact must be a field/value pair")
            name, value = entry
            name = _required_text(name, "record fact field")
            if isinstance(value, str):
                value = _required_text(value, f"record fact {name}")
            elif isinstance(value, tuple):
                validator = _optional_texts if name in OPTIONAL_SEQUENCE_RECORD_FACT_FIELDS else _required_texts
                value = validator(value, f"record fact {name}")
            else:
                raise KoineSessionError(f"record fact {name} must be text or a tuple of text")
            names.append(name)
            normalized.append((name, value))
        if len(names) != len(set(names)):
            raise KoineSessionError("record fact fields must not contain duplicates")
        object.__setattr__(self, "entries", tuple(normalized))

    def as_mapping(self) -> dict[str, RecordFactValue]:
        """Return a copy suitable for exact schema and source-fact validation."""
        return dict(self.entries)


def record_digest(
    content: str,
    facts: RecordFacts,
    approved_inputs: tuple["ApprovedInput", ...],
) -> str:
    """Return the canonical digest binding a record's prose, facts and inputs."""
    normalized_content = _record_content(content)
    if not isinstance(facts, RecordFacts):
        raise KoineSessionError("record digest requires structured RecordFacts")
    inputs = _approved_inputs(approved_inputs)
    payload = {
        "approved_inputs": [
            {"digest": item.digest, "identifier": item.identifier, "version": item.version}
            for item in inputs
        ],
        "content": normalized_content,
        "facts": [
            {"field": field, "value": list(value) if isinstance(value, tuple) else value}
            for field, value in facts.entries
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


@dataclass(frozen=True)
class ApprovedInput:
    """A versioned input identity approved for use in one generated record.

    The session stores only a stable identity, version, and digest.  It neither
    copies the input's payload nor assumes how the adopting environment stores
    or authenticates it.
    """

    identifier: str
    version: str
    digest: str

    def __post_init__(self) -> None:
        for field in ("identifier", "version", "digest"):
            value = _required_text(getattr(self, field), f"input {field}")
            if is_placeholder_identity(value):
                raise KoineSessionError(f"input {field} must not be a placeholder")
            object.__setattr__(self, field, value)

    @classmethod
    def from_reference(cls, reference: ImmutableReference) -> "ApprovedInput":
        """Bind a prior approved record without copying its contents."""
        if not isinstance(reference, ImmutableReference):
            raise KoineSessionError("approved record input must be an immutable reference")
        return cls(identifier=reference.identifier, version=reference.version, digest=reference.digest)


def _approved_inputs(inputs: tuple[ApprovedInput, ...]) -> tuple[ApprovedInput, ...]:
    if not isinstance(inputs, tuple) or not inputs:
        raise KoineSessionError("approved_inputs must contain at least one input")
    if any(not isinstance(item, ApprovedInput) for item in inputs):
        raise KoineSessionError("approved_inputs must contain ApprovedInput values")
    identities = [item.identifier for item in inputs]
    if len(identities) != len(set(identities)):
        raise KoineSessionError("approved_inputs must have distinct identities")
    return inputs


@dataclass(frozen=True)
class SessionAuthorities:
    """The named human authorities needed before the coworker can proceed."""

    owner: Actor
    evidence_authority: Actor
    acceptance_authority: Actor

    def __post_init__(self) -> None:
        for name, authority in (
            ("owner", self.owner),
            ("evidence authority", self.evidence_authority),
            ("acceptance authority", self.acceptance_authority),
        ):
            if not isinstance(authority, Actor) or authority.kind is not ActorKind.HUMAN:
                raise KoineSessionError(f"{name} must be a named human authority")
            _named_identifier(authority.identity, name)


@dataclass(frozen=True)
class SetupBrief:
    """The approved facts needed to create the setup record."""

    platform_boundary: str
    constraints: tuple[str, ...]
    approved_inputs: tuple[ApprovedInput, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "platform_boundary", _required_text(self.platform_boundary, "platform boundary"))
        object.__setattr__(self, "constraints", _required_texts(self.constraints, "constraints"))
        object.__setattr__(self, "approved_inputs", _approved_inputs(self.approved_inputs))


@dataclass(frozen=True)
class OutcomeFraming:
    """The approved facts needed to create the outcome brief."""

    consumer_outcome: str
    success_signals: tuple[str, ...]
    scope: str
    approved_inputs: tuple[ApprovedInput, ...]
    verification: "VerificationPlanning"
    success_criteria: tuple["SuccessCriterion", ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "consumer_outcome", _required_text(self.consumer_outcome, "consumer outcome"))
        object.__setattr__(self, "success_signals", _required_texts(self.success_signals, "success signals"))
        object.__setattr__(self, "scope", _required_text(self.scope, "scope"))
        object.__setattr__(self, "approved_inputs", _approved_inputs(self.approved_inputs))
        if not isinstance(self.verification, VerificationPlanning):
            raise KoineSessionError("outcome framing requires verification planning")
        if not isinstance(self.success_criteria, tuple) or not self.success_criteria:
            raise KoineSessionError("every success signal requires a verification criterion")
        if any(not isinstance(item, SuccessCriterion) for item in self.success_criteria):
            raise KoineSessionError("success criteria must contain SuccessCriterion values")
        criteria_by_signal = {item.signal: item for item in self.success_criteria}
        if (
            len(criteria_by_signal) != len(self.success_criteria)
            or tuple(criteria_by_signal) != self.success_signals
        ):
            raise KoineSessionError("every success signal requires one ordered verification criterion")
        for criterion in self.success_criteria:
            if criterion.check_family not in self.verification.check_families:
                raise KoineSessionError("a success criterion must use a declared check family")
            if criterion.acceptance_rule not in self.verification.acceptance_rules:
                raise KoineSessionError("a success criterion must use a declared acceptance rule")
            required_inputs = (
                ApprovedInput.from_reference(criterion.validator),
                *criterion.evidence,
            )
            if any(item not in self.approved_inputs for item in required_inputs):
                raise KoineSessionError(
                    "a success criterion validator and evidence must be approved framing inputs"
                )


class VerificationCaseIntent(str, Enum):
    """The approved verification purpose captured before implementation."""

    SNAPSHOT_PARITY = "snapshot-parity"
    APPROVED_EXPECTED_OUTPUT = "approved-expected-output"
    CONTRACT_CONFORMANCE = "contract-conformance"


@dataclass(frozen=True)
class CheckpointExpectation:
    """A declared lineage checkpoint and the person accountable for its evidence."""

    checkpoint: str
    owner: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "checkpoint", _required_text(self.checkpoint, "checkpoint"))
        object.__setattr__(self, "owner", _named_identifier(self.owner, "checkpoint owner"))

    @property
    def inventory(self) -> str:
        return f"{self.checkpoint}@{self.owner}"


@dataclass(frozen=True)
class VerificationPlanning:
    """Framing-time verification intent, without defining verification semantics.

    This is an engagement-record planning boundary only.  The versioned case
    and deterministic comparison model remain owned by the later verification
    domain rather than by the coworker session.
    """

    case_intent: VerificationCaseIntent
    check_families: tuple[CheckFamily, ...]
    checkpoint_expectations: tuple[CheckpointExpectation, ...]
    acceptance_rules: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.case_intent, VerificationCaseIntent):
            raise KoineSessionError("verification case intent must be a VerificationCaseIntent")
        if not isinstance(self.check_families, tuple) or not self.check_families:
            raise KoineSessionError("verification planning requires check families")
        if any(not isinstance(item, CheckFamily) for item in self.check_families):
            raise KoineSessionError("check families must contain CheckFamily values")
        if len(self.check_families) != len(set(self.check_families)):
            raise KoineSessionError("check families must not contain duplicates")
        if not isinstance(self.checkpoint_expectations, tuple) or not self.checkpoint_expectations:
            raise KoineSessionError("verification planning requires owned checkpoint expectations")
        if any(not isinstance(item, CheckpointExpectation) for item in self.checkpoint_expectations):
            raise KoineSessionError("checkpoint expectations must contain CheckpointExpectation values")
        checkpoints = [item.checkpoint for item in self.checkpoint_expectations]
        if len(checkpoints) != len(set(checkpoints)):
            raise KoineSessionError("checkpoint expectations must not contain duplicate checkpoints")
        object.__setattr__(self, "acceptance_rules", _required_texts(self.acceptance_rules, "acceptance rules"))
        if self.case_intent is VerificationCaseIntent.SNAPSHOT_PARITY and CheckFamily.PARITY not in self.check_families:
            raise KoineSessionError("snapshot parity intent requires the parity check family")

    def validate_for(self, mode: EngagementMode) -> None:
        """Reject legacy-parity claims for a greenfield engagement before egress."""
        if not isinstance(mode, EngagementMode):
            raise KoineSessionError("verification planning requires an engagement mode")
        if mode is EngagementMode.GREENFIELD and (
            self.case_intent is VerificationCaseIntent.SNAPSHOT_PARITY or CheckFamily.PARITY in self.check_families
        ):
            raise KoineSessionError("greenfield verification planning cannot claim legacy parity")

    @property
    def checkpoint_inventory(self) -> tuple[str, ...]:
        return tuple(item.inventory for item in self.checkpoint_expectations)


@dataclass(frozen=True)
class SuccessCriterion:
    """A resolvable validator, approved evidence and pass result for one signal."""

    signal: str
    check_family: CheckFamily
    validator: ImmutableReference
    evidence: tuple[ApprovedInput, ...]
    required_result: ExpectedCheckResult
    acceptance_rule: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "signal", _required_text(self.signal, "success criterion signal"))
        if not isinstance(self.check_family, CheckFamily):
            raise KoineSessionError("success criterion check family must be a CheckFamily")
        if not isinstance(self.validator, ImmutableReference):
            raise KoineSessionError("success criterion validator must be an immutable reference")
        if self.validator.kind is not ReferenceKind.VALIDATOR_SPECIFICATION:
            raise KoineSessionError("success criterion validator must use a validator_specification identity")
        _named_identifier(self.validator.identifier, "success criterion validator")
        object.__setattr__(self, "evidence", _approved_inputs(self.evidence))
        if not isinstance(self.required_result, ExpectedCheckResult):
            raise KoineSessionError("success criterion required result must be an ExpectedCheckResult")
        object.__setattr__(self, "acceptance_rule", _required_text(self.acceptance_rule, "success criterion acceptance rule"))
        failures = validate_success_criterion_contract(self.as_mapping)
        if failures:
            raise KoineSessionError("invalid success criterion: " + "; ".join(failures))

    @property
    def as_mapping(self) -> dict[str, object]:
        return {
            "signal": self.signal,
            "check_family": self.check_family.value,
            "validator": {
                "kind": self.validator.kind.value,
                "identifier": self.validator.identifier,
                "version": self.validator.version,
                "digest": self.validator.digest,
            },
            "evidence": [
                {"identifier": item.identifier, "version": item.version, "digest": item.digest}
                for item in self.evidence
            ],
            "required_result": self.required_result.value,
            "acceptance_rule": self.acceptance_rule,
        }

    @property
    def inventory(self) -> str:
        return json.dumps(self.as_mapping, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True)
class EstateDiscovery:
    """Approved inputs for an existing-estate trace, distinct from target design."""

    processing: tuple[str, ...]
    data: tuple[str, ...]
    interfaces: tuple[str, ...]
    controls: tuple[str, ...]
    continuity_needs: tuple[str, ...]
    accidental_legacy_behaviour: tuple[str, ...]
    uncertainty: tuple[str, ...]
    approved_inputs: tuple[ApprovedInput, ...]

    def __post_init__(self) -> None:
        for field in (
            "processing",
            "data",
            "interfaces",
            "controls",
            "continuity_needs",
            "accidental_legacy_behaviour",
            "uncertainty",
        ):
            object.__setattr__(self, field, _required_texts(getattr(self, field), field.replace("_", " ")))
        object.__setattr__(self, "approved_inputs", _approved_inputs(self.approved_inputs))


@dataclass(frozen=True)
class CapabilityDiscovery:
    """Approved inputs for greenfield capability discovery, with no legacy estate."""

    required_capabilities: tuple[str, ...]
    constraints: tuple[str, ...]
    uncertainty: tuple[str, ...]
    approved_inputs: tuple[ApprovedInput, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "required_capabilities", _required_texts(self.required_capabilities, "required capabilities"))
        object.__setattr__(self, "constraints", _required_texts(self.constraints, "constraints"))
        object.__setattr__(self, "uncertainty", _required_texts(self.uncertainty, "uncertainty"))
        object.__setattr__(self, "approved_inputs", _approved_inputs(self.approved_inputs))


@dataclass(frozen=True)
class TargetDesign:
    """Approved target design and transition inputs, after mode-specific discovery."""

    architecture: str
    operating_model: tuple[str, ...]
    contracts: tuple[str, ...]
    transition: tuple[str, ...]
    increments: tuple[str, ...]
    risks: tuple[str, ...]
    acceptance_signals: tuple[str, ...]
    approved_inputs: tuple[ApprovedInput, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "architecture", _required_text(self.architecture, "architecture"))
        for field in ("operating_model", "contracts", "transition", "increments", "risks", "acceptance_signals"):
            object.__setattr__(self, field, _required_texts(getattr(self, field), field.replace("_", " ")))
        object.__setattr__(self, "approved_inputs", _approved_inputs(self.approved_inputs))


@dataclass(frozen=True)
class DeliveryGate:
    """A uniquely identified gate that blocks one delivery package."""

    identifier: str
    requirement: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "identifier", _canonical_identifier(self.identifier, "delivery gate identifier"))
        object.__setattr__(self, "requirement", _required_text(self.requirement, "delivery gate requirement"))


@dataclass(frozen=True)
class DeliveryWorkPackage:
    """One projectable increment with explicit ownership, validation and gates."""

    identifier: str
    summary: str
    owner: str
    validator: str
    gates: tuple[DeliveryGate, ...]
    depends_on: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "identifier", _canonical_identifier(self.identifier, "delivery package identifier"))
        object.__setattr__(self, "summary", _required_text(self.summary, "delivery package summary"))
        for field in ("owner", "validator"):
            object.__setattr__(self, field, _named_identifier(getattr(self, field), f"delivery package {field}"))
        if not isinstance(self.gates, tuple) or not self.gates:
            raise KoineSessionError("every delivery package requires at least one gate")
        if any(not isinstance(gate, DeliveryGate) for gate in self.gates):
            raise KoineSessionError("delivery package gates must contain DeliveryGate values")
        gate_ids = [gate.identifier for gate in self.gates]
        if len(gate_ids) != len(set(gate_ids)):
            raise KoineSessionError("delivery package gates must not contain duplicate identifiers")
        dependencies = _optional_texts(self.depends_on, "delivery package dependencies")
        object.__setattr__(
            self,
            "depends_on",
            tuple(_canonical_identifier(item, "delivery package dependency") for item in dependencies),
        )

    @property
    def inventory(self) -> str:
        """Return the canonical package metadata; edges and gates project separately."""
        return _inventory_entry(
            identifier=self.identifier,
            owner=self.owner,
            summary=self.summary,
            validator=self.validator,
        )


@dataclass(frozen=True)
class DeliveryContract:
    """A closed, projectable delivery graph retained with its approved record.

    The contract owns the declared package graph only.  Pinax owns all live
    readiness, claims and completion state projected from it later.
    """

    work_packages: tuple[DeliveryWorkPackage, ...]
    exclusions: tuple[str, ...]
    acceptance: tuple[str, ...]
    approved_inputs: tuple[ApprovedInput, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.work_packages, tuple) or not self.work_packages:
            raise KoineSessionError("delivery contract requires work packages")
        if any(not isinstance(package, DeliveryWorkPackage) for package in self.work_packages):
            raise KoineSessionError("delivery work packages must contain DeliveryWorkPackage values")
        package_ids = [package.identifier for package in self.work_packages]
        if len(package_ids) != len(set(package_ids)):
            raise KoineSessionError("delivery work package identifiers must be unique")
        known_packages = set(package_ids)
        gate_ids: list[str] = []
        edges: dict[str, tuple[str, ...]] = {}
        for package in self.work_packages:
            unknown = set(package.depends_on) - known_packages
            if unknown:
                raise KoineSessionError(f"delivery package {package.identifier} depends on an unknown package")
            if package.identifier in package.depends_on:
                raise KoineSessionError("delivery package cannot depend on itself")
            gate_ids.extend(gate.identifier for gate in package.gates)
            edges[package.identifier] = package.depends_on
        if len(gate_ids) != len(set(gate_ids)):
            raise KoineSessionError("delivery gate identifiers must be unique across the contract")
        self._reject_dependency_cycles(edges)
        object.__setattr__(self, "exclusions", _required_texts(self.exclusions, "exclusions"))
        object.__setattr__(self, "acceptance", _required_texts(self.acceptance, "acceptance"))
        object.__setattr__(self, "approved_inputs", _approved_inputs(self.approved_inputs))

    @staticmethod
    def _reject_dependency_cycles(edges: dict[str, tuple[str, ...]]) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(identifier: str) -> None:
            if identifier in visiting:
                raise KoineSessionError("delivery package dependencies must not contain a cycle")
            if identifier in visited:
                return
            visiting.add(identifier)
            for dependency in edges[identifier]:
                visit(dependency)
            visiting.remove(identifier)
            visited.add(identifier)

        for identifier in edges:
            visit(identifier)

    @property
    def package_inventory(self) -> tuple[str, ...]:
        """Canonical package records for the generated contract and the tracker projection."""
        return tuple(package.inventory for package in self.work_packages)

    @property
    def dependency_inventory(self) -> tuple[str, ...]:
        """Directed edges: the blocked package requires the listed package."""
        return tuple(
            _inventory_entry(blocked=package.identifier, requires=dependency)
            for package in self.work_packages
            for dependency in package.depends_on
        )

    @property
    def gate_inventory(self) -> tuple[str, ...]:
        """Canonical, package-scoped gate inventory for a later projection."""
        return tuple(
            _inventory_entry(
                identifier=gate.identifier,
                package=package.identifier,
                requirement=gate.requirement,
            )
            for package in self.work_packages
            for gate in package.gates
        )


@dataclass(frozen=True)
class SessionModelRoute:
    """Provider-neutral destination and handling policy for one session role."""

    destination: ModelDestination
    mode: ModelEgressMode
    data_class: str
    retention_policy: str
    evidence_policy: str

    def __post_init__(self) -> None:
        if not isinstance(self.destination, ModelDestination):
            raise KoineSessionError("model destination must be a ModelDestination")
        if not isinstance(self.mode, ModelEgressMode):
            raise KoineSessionError("model route mode must be a ModelEgressMode")
        object.__setattr__(self, "data_class", _required_text(self.data_class, "data class"))
        object.__setattr__(self, "retention_policy", _required_text(self.retention_policy, "retention policy"))
        object.__setattr__(self, "evidence_policy", _required_text(self.evidence_policy, "evidence policy"))


@dataclass(frozen=True)
class SessionModelRoutes:
    """Distinct call contracts for generation and independent review."""

    generator: SessionModelRoute
    reviewer: SessionModelRoute

    def __post_init__(self) -> None:
        if not isinstance(self.generator, SessionModelRoute) or not isinstance(self.reviewer, SessionModelRoute):
            raise KoineSessionError("generator and reviewer routes must be SessionModelRoute values")


@dataclass(frozen=True)
class GeneratedRecordProposal:
    """A generator's immutable identity and exact readable projection of its facts."""

    document: ImmutableReference
    content: str
    facts: RecordFacts

    def __post_init__(self) -> None:
        if not isinstance(self.document, ImmutableReference) or self.document.kind is not ReferenceKind.STAGE_RECORD:
            raise KoineSessionError("a generated record must be a stage_record identity")
        object.__setattr__(self, "content", _record_content(self.content))
        if not isinstance(self.facts, RecordFacts):
            raise KoineSessionError("a generated record must include structured RecordFacts")
        projection_failures = validate_record_projection(self.content, self.facts.as_mapping())
        if projection_failures:
            raise KoineSessionError(
                "generated readable record does not match structured facts: "
                + "; ".join(projection_failures)
            )


@dataclass(frozen=True)
class ReviewProposal:
    """An independent review result, returned through the same egress port."""

    disposition: ReviewDisposition
    findings: ImmutableReference

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, ReviewDisposition):
            raise KoineSessionError("review disposition must be a ReviewDisposition")
        if not isinstance(self.findings, ImmutableReference) or self.findings.kind is not ReferenceKind.REVIEW_FINDINGS:
            raise KoineSessionError("review findings must be a review_findings identity")


@dataclass(frozen=True)
class BoundGeneratedRecord:
    """A generated stage record, its text, and the exact inputs it used."""

    record: StageRecord
    content: str
    facts: RecordFacts
    approved_inputs: tuple[ApprovedInput, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.record, StageRecord):
            raise KoineSessionError("bound record must be a StageRecord")
        object.__setattr__(self, "content", _record_content(self.content))
        if not isinstance(self.facts, RecordFacts):
            raise KoineSessionError("bound record must retain structured RecordFacts")
        projection_failures = validate_record_projection(self.content, self.facts.as_mapping())
        if projection_failures:
            raise KoineSessionError(
                "bound readable record does not match structured facts: "
                + "; ".join(projection_failures)
            )
        inputs = _approved_inputs(self.approved_inputs)
        object.__setattr__(self, "approved_inputs", inputs)
        if self.record.document.digest != record_digest(self.content, self.facts, inputs):
            raise KoineSessionError("bound record content, facts and inputs do not match its immutable digest")


# The closed set of secret-shaped patterns artefact intake refuses. Each names a
# shape a stored artefact must never carry, not one supplier's key format, so
# nothing here has to be revised when a supplier changes its own. The shapes
# have one owner that every boundary of this product reads; what intake refuses
# is this scan's own choice from them.
#
# Intake reads an adopting team's artefact, not a text this product wrote, so
# it reads the shapes that name a secret and carry its value with it. The
# shapes that fire on the bare word for a secret or a key are not read here: a
# column called password_reset_date, a dictionary row describing an access key,
# or a sentence about credentials is ordinary content in an estate's own
# artefact, and refusing it would refuse the artefact for describing itself.
# The gate that reads a packet this product wrote does read those shapes,
# because nothing it reads has any reason to name a secret at all.
CREDENTIAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = shapes(
    DECLARED_CREDENTIAL_PATTERNS,
    (ASSIGNED_SECRET, KEY_BLOCK, CONNECTION_CREDENTIAL, BEARER_AUTHORIZATION),
)
# The advisory shapes a locator is read for, both of them the owner's. They are
# read for a label and never for a refusal: the aggregate has already refused
# every machine route it declares, and what is left here is a dotted name with a
# path or a port after it, or a connection key written against a value. Neither
# can be told from an ordinary written name by reading it, so this boundary says
# what it saw and admits the artefact. Nothing here adds a refusal reason.
LOCATOR_ADVISORY_SHAPES: tuple[tuple[str, re.Pattern[str]], ...] = shapes(
    ADVISORY_PATTERNS, ADVISORY_SHAPES
)
# The position an artefact's own intake record is read at. An artefact is frozen
# as a whole; the finer positions belong to the facts read out of it.
ARTEFACT_INTAKE_POSITION = "whole artefact"
# evorthon-implements: EVD-README-050
# The two bounds on what one artefact's text may put into a model call. They are
# the only bounds, they are declared here and nowhere else, and every round
# reports them beside what actually crossed. A row is one line of the artefact as
# it was read, so a sample is cut on a line boundary and then on the character
# bound; the whole text of an artefact never crosses.
INTAKE_SAMPLE_ROWS = 20
INTAKE_SAMPLE_CHARACTERS = 2000
# The closed handling-classification order this boundary reads, from least to
# most restricted. The use case records a handling classification as free text
# with a confidential default, so the order lives here: it is a rule about what
# may cross a model boundary, not a new value the record carries. A label outside
# this order never crosses.
HANDLING_CLASSIFICATION_ORDER: tuple[str, ...] = (
    "public",
    "internal",
    "confidential",
    "restricted",
)
# The call field artefact samples travel in. The authorized classification is
# part of the field name, so an environment authorizes one level and the egress
# gateway's exact field-scope check refuses a call built for any other level.
ARTEFACT_SAMPLE_FIELD_PREFIX = "artefact_samples_at_or_below_"
# The questions a greenfield use case is never asked, because there is no earlier
# run to compare with. Every label is read from the aggregate's own declarations,
# so a rename there cannot silently narrow the greenfield parity refusal here.
PARITY_INTAKE_FIELDS: frozenset[str] = frozenset(
    {REPLACED_OUTPUT_INTAKE_FIELD, CONTINUITY_OR_ACCIDENT_INTAKE_FIELD}
    | {key.value.replace("_", " ") for key in CUTOVER_CONDITIONS}
)
IntakeRecord = (
    TargetOutput
    | DatasetPlaceholder
    | IntermediateResult
    | BuildRouteDeclaration
    | ScenarioReference
    | Authority
    | ConditionDeclaration
    | ConsumerDependency
)
# The one route from a declaration intake recorded to the aggregate method that
# owns it. Every rule about a declaration stays with the aggregate; nothing is
# re-checked here.
INTAKE_RECORD_ROUTES: Mapping[type, str] = MappingProxyType(
    {
        TargetOutput: "record_target_output",
        DatasetPlaceholder: "record_dataset",
        IntermediateResult: "record_intermediate_result",
        BuildRouteDeclaration: "record_build_route",
        ScenarioReference: "record_scenario",
        Authority: "record_authority",
        ConditionDeclaration: "record_condition",
        ConsumerDependency: "record_consumer_dependency",
    }
)


def credential_findings(text: str) -> tuple[str, ...]:
    """Name every secret-shaped pattern one artefact's text carries.

    This is the one credential scan over an intake artefact. Intake refuses an
    artefact with any finding before the artefact is admitted, recorded, or
    sent anywhere.
    """
    if not isinstance(text, str):
        raise KoineSessionError("a credential scan reads artefact text")
    return tuple(name for name, pattern in CREDENTIAL_PATTERNS if pattern.search(text))


def residual_questions(facts: tuple["IntakeFact", ...]) -> tuple[str, ...]:
    """The intake sections no recorded fact answers, in the record's own order."""
    if not isinstance(facts, tuple) or any(not isinstance(item, IntakeFact) for item in facts):
        raise KoineSessionError("residual questions are read from recorded intake facts")
    answered = {fact.section for fact in facts}
    return tuple(section for section in USE_CASE_INTAKE_SECTIONS if section not in answered)


def _intake_field(section: str, field: str) -> tuple[str, str]:
    """Read one section and field against the intake record the aggregate owns."""
    section = _required_text(section, "intake section")
    if section not in USE_CASE_INTAKE_TEMPLATE_FIELDS:
        raise KoineSessionError(f"no intake section is declared as {section!r}")
    field = _required_text(field, "intake field")
    if field in INTAKE_PROVENANCE_FIELDS:
        raise KoineSessionError("provenance travels with an intake fact, it is not one of its values")
    if field not in USE_CASE_INTAKE_TEMPLATE_FIELDS[section]:
        raise KoineSessionError(f"intake section {section!r} declares no field {field!r}")
    return section, field


class IntakeArtefactForm(str, Enum):
    """How one artefact is read, using base tools alone.

    There are two readings and no third: the delimited rows the standard reader
    returns, and plain lines. No reader is built for an artefact shape.
    """

    DELIMITED = "delimited"
    TEXT = "text"


@dataclass(frozen=True)
class IntakeReading:
    """What base-tool reading recovered from one artefact: its text and its rows.

    A text artefact yields its lines, one value each, because plain reading
    recovers nothing finer and no format-specific reader is built to.
    """

    text: str
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class IntakeArtefactSource:
    """One artefact offered to intake: its identity, its logical locator and its bytes.

    The session keeps the identity, digest, classification and locator. It never
    keeps the bytes, so a later round supplies them again and is checked against
    the digest admitted for them.
    """

    identifier: str
    locator: str
    form: IntakeArtefactForm
    content: bytes
    classification: str | None = None
    version: str = "v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "identifier", _required_text(self.identifier, "intake artefact identifier"))
        object.__setattr__(self, "locator", _required_text(self.locator, "intake artefact locator"))
        object.__setattr__(self, "version", _required_text(self.version, "intake artefact version"))
        if not isinstance(self.form, IntakeArtefactForm):
            raise KoineSessionError("an intake artefact must declare how it is read")
        if not isinstance(self.content, bytes):
            raise KoineSessionError("an intake artefact must carry the bytes that were read")
        if self.classification is not None:
            object.__setattr__(
                self, "classification", _required_text(self.classification, "intake artefact classification")
            )

    @property
    def digest(self) -> str:
        """The digest of exactly the bytes read, so a later round cannot swap them."""
        return f"sha256:{hashlib.sha256(self.content).hexdigest()}"

    def read(self) -> IntakeReading:
        """Read the artefact with base tools alone, refusing what cannot be read.

        An artefact that is not text, or whose delimited rows the standard
        reader cannot return, is refused. It is never partly read in silence.
        """
        try:
            text = self.content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise KoineSessionError(f"intake artefact {self.identifier} cannot be read as text") from error
        if "\x00" in text:
            raise KoineSessionError(f"intake artefact {self.identifier} cannot be read as text")
        if self.form is IntakeArtefactForm.TEXT:
            return IntakeReading(text=text, rows=tuple((line,) for line in text.splitlines()))
        try:
            rows = tuple(tuple(row) for row in csv.reader(io.StringIO(text)))
        except csv.Error as error:
            raise KoineSessionError(
                f"intake artefact {self.identifier} cannot be read as delimited rows"
            ) from error
        return IntakeReading(text=text, rows=rows)


class ArtefactEgressRefusal(str, Enum):
    """The closed reasons one artefact's text does not cross on an intake route.

    Each is a privacy refusal, not a judgement of the artefact. Nothing here
    refuses an artefact for being synthetic, incomplete or unreviewed, and a
    refusal never stops the round: it proceeds on the artefact's digest and the
    record alone.
    """

    READING_NOT_AUTHORIZED = "artefact_reading_not_authorized"
    ABOVE_AUTHORIZED_CLASSIFICATION = "above_authorized_classification"
    CLASSIFICATION_NOT_ORDERED = "classification_outside_the_closed_order"


@dataclass(frozen=True)
class ArtefactEgress:
    """What crossed for one admitted artefact on one round, or why nothing did.

    The counts are of the sample that actually crossed, not of the artefact.
    ``rows`` is the number of lines present in that sample, so a final line the
    character bound cut short counts as one: it is counted because part of it
    crossed, and the report says what crossed rather than what was whole.
    ``characters`` is the exact length of the sample. A refused artefact carries
    a closed reason and zero counts.
    """

    identifier: str
    classification: str
    rows: int
    characters: int
    refusal: ArtefactEgressRefusal | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "identifier", _required_text(self.identifier, "artefact egress identifier"))
        object.__setattr__(
            self, "classification", _required_text(self.classification, "artefact egress classification")
        )
        for name, value in (("rows", self.rows), ("characters", self.characters)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise KoineSessionError(f"artefact egress {name} must be a count")
        if self.refusal is not None and not isinstance(self.refusal, ArtefactEgressRefusal):
            raise KoineSessionError("an artefact egress refusal must be a closed reason")
        if self.refusal is not None and (self.rows or self.characters):
            raise KoineSessionError("a refused artefact crossing reports nothing crossed")

    @property
    def crossed(self) -> bool:
        """Whether any of this artefact's text reached the call."""
        return self.refusal is None


@dataclass(frozen=True)
class ArtefactLocatorWarning:
    """One admitted artefact whose locator reads like an address, and how it reads.

    This is a label beside the crossing report, not a refusal: the artefact was
    admitted, it stays admitted, and the round proceeds. The shape is one of the
    owner's advisory shapes, so a warning cannot name a reading no shape
    declares. What a reader does about it is the adopting team's locator
    discipline: connection details belong in their environment's configuration
    and not in a record, and a locator that reads like one is admitted with a
    warning rather than refused.
    """

    identifier: str
    shape: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "identifier", _required_text(self.identifier, "artefact locator warning identifier")
        )
        if self.shape not in ADVISORY_SHAPES:
            raise KoineSessionError("an artefact locator warning names a declared advisory shape")


def locator_warning(identifier: str, locator: str) -> ArtefactLocatorWarning | None:
    """Read one admitted artefact's locator for an advisory shape, or nothing.

    The read happens after admission and never stops it. A locator carrying a
    machine route never reaches here: the record refused it before the artefact
    was frozen.
    """
    if not isinstance(locator, str):
        raise KoineSessionError("a locator warning is read from a locator")
    carried = shape_carried(LOCATOR_ADVISORY_SHAPES, locator)
    if carried is None:
        return None
    return ArtefactLocatorWarning(identifier=identifier, shape=carried)


def artefact_sample(text: str) -> str:
    """Bound one artefact's text to the declared row and character limits.

    This is the one place an artefact's text is trimmed for a model call. The
    first rows up to the row bound are taken, so the sample stops on a line
    boundary, and what they produce is then cut to the character bound.
    """
    if not isinstance(text, str):
        raise KoineSessionError("an artefact sample is read from artefact text")
    return "\n".join(text.splitlines()[:INTAKE_SAMPLE_ROWS])[:INTAKE_SAMPLE_CHARACTERS]


def artefact_sample_field(classification: str) -> str:
    """Name the call field carrying samples at or below one classification."""
    if classification not in HANDLING_CLASSIFICATION_ORDER:
        raise KoineSessionError(f"no declared handling classification is named {classification!r}")
    return f"{ARTEFACT_SAMPLE_FIELD_PREFIX}{classification}"


def authorized_sample_classification(authorization: ModelEgressAuthorization | None) -> str | None:
    """Read the one classification level an authorization's field scope names.

    An authorization whose field scope names no artefact sample field authorizes
    no artefact text at all, and one naming more than one level is refused rather
    than read as the higher of them.
    """
    if authorization is None:
        return None
    if not isinstance(authorization, ModelEgressAuthorization):
        raise KoineSessionError("an artefact sample level is read from a ModelEgressAuthorization")
    named = sorted(
        field for field in authorization.permitted_fields if field.startswith(ARTEFACT_SAMPLE_FIELD_PREFIX)
    )
    if not named:
        return None
    if len(named) > 1:
        raise KoineSessionError(
            "an authorization names one artefact sample level, not several: " + ", ".join(named)
        )
    level = named[0][len(ARTEFACT_SAMPLE_FIELD_PREFIX) :]
    if level not in HANDLING_CLASSIFICATION_ORDER:
        raise KoineSessionError(f"an authorization names no declared handling classification: {level!r}")
    return level


@dataclass(frozen=True)
class IntakeFact:
    """One value a round recorded, the section it answers, and where it was read.

    The provenance is the aggregate's own: the artefact identity, the position
    inside it, who or what extracted it, and whether it is extracted, inferred
    or confirmed.
    """

    section: str
    field: str
    value: str
    provenance: FactProvenance

    def __post_init__(self) -> None:
        section, field = _intake_field(self.section, self.field)
        object.__setattr__(self, "section", section)
        object.__setattr__(self, "field", field)
        object.__setattr__(self, "value", _required_text(self.value, "intake fact value"))
        if not isinstance(self.provenance, FactProvenance):
            raise KoineSessionError("an intake fact requires recorded provenance")

    @property
    def artefact(self) -> ImmutableReference:
        """The artefact this fact was read from, owned by its provenance."""
        return self.provenance.artefact

    @property
    def position(self) -> str:
        """The position inside that artefact, owned by its provenance."""
        return self.provenance.locator.position

    @property
    def status(self) -> FactStatus:
        """How the fact reached the record, owned by its provenance."""
        return self.provenance.status


@dataclass(frozen=True)
class IntakeAnswer:
    """One residual question answered between rounds."""

    section: str
    field: str
    value: str

    def __post_init__(self) -> None:
        section, field = _intake_field(self.section, self.field)
        object.__setattr__(self, "section", section)
        object.__setattr__(self, "field", field)
        object.__setattr__(self, "value", _required_text(self.value, "intake answer value"))


@dataclass(frozen=True)
class IntakeAnswers:
    """One named human's answers to the residual questions, confirmed in bulk."""

    answered_by: Actor
    answers: tuple[IntakeAnswer, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.answered_by, Actor) or self.answered_by.kind is not ActorKind.HUMAN:
            raise KoineSessionError("only a named human answers a residual question")
        if not isinstance(self.answers, tuple) or not self.answers:
            raise KoineSessionError("a bulk confirmation carries at least one answer")
        if any(not isinstance(item, IntakeAnswer) for item in self.answers):
            raise KoineSessionError("a bulk confirmation carries IntakeAnswer values")
        asked = [(item.section, item.field, item.value) for item in self.answers]
        if len(asked) != len(set(asked)):
            raise KoineSessionError("a bulk confirmation answers each question once")

    @property
    def inventory(self) -> tuple[tuple[str, str, str], ...]:
        """The answers as the bounded call and the frozen answer record carry them."""
        return tuple((item.section, item.field, item.value) for item in self.answers)


@dataclass(frozen=True)
class IntakeRoundProposal:
    """What one intake generator returns: the facts it read and what they record."""

    facts: tuple[IntakeFact, ...]
    declarations: tuple[IntakeRecord, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.facts, tuple) or not self.facts:
            raise KoineSessionError("an intake round returns at least one recorded fact")
        if any(not isinstance(item, IntakeFact) for item in self.facts):
            raise KoineSessionError("an intake round returns IntakeFact values")
        if not isinstance(self.declarations, tuple):
            raise KoineSessionError("intake declarations must be recorded in a tuple")
        unknown = sorted({type(item).__name__ for item in self.declarations if type(item) not in INTAKE_RECORD_ROUTES})
        if unknown:
            raise KoineSessionError("an intake round records only what the use case owns: " + ", ".join(unknown))


def _validate_delivery_contract_binding(
    record: BoundGeneratedRecord,
    contract: DeliveryContract,
    expected_inputs: tuple[ApprovedInput, ...],
) -> None:
    """Ensure the immutable record covers the complete contract the tracker projection may project."""
    if record.record.phase is not LifecyclePhase.DELIVERY_CONTRACT:
        raise KoineSessionError("a delivery contract binding must use a delivery-contract record")
    inputs = _approved_inputs(expected_inputs)
    if record.approved_inputs != inputs:
        raise KoineSessionError("delivery contract record does not bind the approved inputs")
    facts = record.facts.as_mapping()
    expected = {
        "package inventory": contract.package_inventory,
        "dependency inventory": contract.dependency_inventory,
        "gate inventory": contract.gate_inventory,
        "exclusions": contract.exclusions,
        "acceptance": contract.acceptance,
        "evidence": tuple(f"{item.identifier}@{item.version}#{item.digest}" for item in inputs),
    }
    for field, value in expected.items():
        if facts.get(field) != value:
            raise KoineSessionError(f"delivery contract record does not bind the {field}")


@dataclass(frozen=True)
class KoineSession:
    """An immutable, provider-neutral session through the delivery contract.

    ``ModelEgressPort`` is the complete generator/reviewer capability.  The
    session constructs bounded calls and hands their authorization unchanged to
    that port; it has no provider client, credential, or authorization policy.
    """

    session_id: str
    engagement: Engagement
    authorities: SessionAuthorities
    generator: Actor
    reviewer: Actor
    routes: SessionModelRoutes
    egress: ModelEgressPort
    generated_records: tuple[BoundGeneratedRecord, ...] = ()
    verification_planning: VerificationPlanning | None = None
    success_criteria: tuple[SuccessCriterion, ...] = ()
    delivery_contract: DeliveryContract | None = None
    intake_artefacts: tuple[IntakeArtefact, ...] = ()
    intake_facts: tuple[IntakeFact, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _required_text(self.session_id, "session id"))
        if not isinstance(self.engagement, Engagement):
            raise KoineSessionError("session engagement must be an Engagement")
        if self.engagement.phase not in {
            LifecyclePhase.SETUP,
            LifecyclePhase.FRAMING,
            LifecyclePhase.DISCOVERY,
            LifecyclePhase.DESIGN,
            LifecyclePhase.DELIVERY_CONTRACT,
        }:
            raise KoineSessionError("a discovery and contract session cannot run after delivery begins")
        if not isinstance(self.authorities, SessionAuthorities):
            raise KoineSessionError("session authorities are required")
        for name, actor in (("generator", self.generator), ("reviewer", self.reviewer)):
            if not isinstance(actor, Actor) or actor.kind is ActorKind.HUMAN:
                raise KoineSessionError(f"{name} must be a non-human session identity")
        if self.generator.identity == self.reviewer.identity:
            raise KoineSessionError("generator and reviewer identities must differ")
        if not isinstance(self.routes, SessionModelRoutes):
            raise KoineSessionError("session model routes are required")
        if not isinstance(self.egress, ModelEgressPort):
            raise KoineSessionError("session egress must implement ModelEgressPort")
        if not isinstance(self.generated_records, tuple) or any(
            not isinstance(item, BoundGeneratedRecord) for item in self.generated_records
        ):
            raise KoineSessionError("generated_records must contain BoundGeneratedRecord values")
        if self.verification_planning is not None and not isinstance(self.verification_planning, VerificationPlanning):
            raise KoineSessionError("verification_planning must be a VerificationPlanning when supplied")
        if not isinstance(self.success_criteria, tuple) or any(
            not isinstance(item, SuccessCriterion) for item in self.success_criteria
        ):
            raise KoineSessionError("success_criteria must contain SuccessCriterion values")
        if self.delivery_contract is not None and not isinstance(self.delivery_contract, DeliveryContract):
            raise KoineSessionError("delivery_contract must be a DeliveryContract when supplied")
        self._validate_intake()
        self._validate_generated_records()

    @classmethod
    def cold_start(
        cls,
        *,
        session_id: str,
        engagement: Engagement,
        authorities: SessionAuthorities,
        generator: Actor,
        reviewer: Actor,
        routes: SessionModelRoutes,
        egress: ModelEgressPort,
    ) -> "KoineSession":
        """Create a session only at the governed cold-start setup phase."""
        if engagement.phase is not LifecyclePhase.SETUP or engagement.records:
            raise KoineSessionError("a cold-start session requires an empty setup-phase engagement")
        return cls(
            session_id=session_id,
            engagement=engagement,
            authorities=authorities,
            generator=generator,
            reviewer=reviewer,
            routes=routes,
            egress=egress,
        )

    @property
    def intake_questions(self) -> tuple[str, ...]:
        """The intake sections no admitted artefact has answered yet."""
        return residual_questions(self.intake_facts)

    def admit_intake_artefact(self, source: IntakeArtefactSource, read_by: Actor) -> "KoineSession":
        """Admit one artefact after a deterministic credential scan.

        The artefact is read with base tools, scanned, then frozen with a digest
        and a classification. An artefact that names no classification is
        admitted at the confidential default the standing conditions declare, and
        the record shows that default rather than an empty field.

        The refusals here are integrity refusals: an artefact that cannot be
        read, an artefact carrying a secret-shaped pattern, and a second
        artefact under an identity already admitted. Nothing else stops
        admission. A locator that reads like a dotted server name with a path or
        a port after it is one of the things that does not: the record refuses
        every machine route it declares, and what is left reads like an ordinary
        name, so the artefact is admitted and the round reports a warning on it.
        """
        if not isinstance(source, IntakeArtefactSource):
            raise KoineSessionError("artefact intake requires an IntakeArtefactSource")
        if not isinstance(read_by, Actor):
            raise KoineSessionError("artefact intake must name who read the artefact")
        findings = credential_findings(source.read().text)
        if findings:
            raise KoineSessionError(
                f"intake artefact {source.identifier} carries a secret-shaped pattern: " + ", ".join(findings)
            )
        if any(item.artefact.identifier == source.identifier for item in self.intake_artefacts):
            raise KoineSessionError(f"intake artefact {source.identifier} is already admitted")
        document = ImmutableReference(
            kind=ReferenceKind.INTAKE_ARTEFACT,
            identifier=source.identifier,
            version=source.version,
            digest=source.digest,
        )
        try:
            admitted = IntakeArtefact(
                artefact=document,
                classification=source.classification or CONDITION_DEFAULTS[ConditionKey.HANDLING_CLASSIFICATION],
                locator=source.locator,
                provenance=FactProvenance(
                    locator=FactLocator(artefact=document, position=ARTEFACT_INTAKE_POSITION),
                    extracted_by=read_by,
                    status=FactStatus.EXTRACTED,
                ),
            )
        except EngagementError as exc:
            raise KoineSessionError(str(exc)) from exc
        return self._evolve(intake_artefacts=(*self.intake_artefacts, admitted))

    def intake_call(
        self,
        use_case: UseCase,
        readings: tuple[IntakeArtefactSource, ...],
        answers: IntakeAnswers | None = None,
        *,
        authorization: ModelEgressAuthorization | None = None,
    ) -> ModelCall:
        """Build the bounded intake call so an environment can authorize it exactly.

        The call carries the admitted artefacts by identity, digest and
        classification, the sections still open, any answers a named human
        confirmed in bulk, and a bounded sample of the text of each artefact the
        authorization's field scope lets cross. It never carries an artefact
        whole, and it carries no artefact text at all unless an authorization
        names the level to cross at.
        """
        return self._intake_call_and_egress(use_case, readings, answers, authorization)[0]

    def intake_egress(
        self,
        use_case: UseCase,
        readings: tuple[IntakeArtefactSource, ...],
        answers: IntakeAnswers | None = None,
        *,
        authorization: ModelEgressAuthorization | None = None,
    ) -> tuple[ArtefactEgress, ...]:
        """Report what one intake call would cross per artefact, before sending it."""
        return self._intake_call_and_egress(use_case, readings, answers, authorization)[1]

    def intake_locator_warnings(
        self,
        use_case: UseCase,
        readings: tuple[IntakeArtefactSource, ...],
        answers: IntakeAnswers | None = None,
        *,
        authorization: ModelEgressAuthorization | None = None,
    ) -> tuple[ArtefactLocatorWarning, ...]:
        """Report the admitted locators that read like an address, before sending.

        This reports; it never refuses. An environment reads it the way it reads
        the crossing report, and the round reports the same warnings.
        """
        return self._intake_call_and_egress(use_case, readings, answers, authorization)[2]

    def _intake_call_and_egress(
        self,
        use_case: UseCase,
        readings: tuple[IntakeArtefactSource, ...],
        answers: IntakeAnswers | None,
        authorization: ModelEgressAuthorization | None,
    ) -> tuple[ModelCall, tuple[ArtefactEgress, ...], tuple[ArtefactLocatorWarning, ...]]:
        """Build the intake call, the crossing report and the locator warnings.

        The classification gate is closed and stated once here. A classification
        at or below the level the authorization's field scope names crosses as a
        bounded sample. A higher classification, a classification outside the
        declared order, and every artefact where no authorization names a level
        cross nothing, and the round proceeds on the record instead.

        The locator warnings are read in the same pass, one at most for each
        admitted artefact. They label a locator that reads like an address and
        change nothing else: no call field, no crossing, no refusal.
        """
        self._expect_use_case(use_case)
        if answers is not None and not isinstance(answers, IntakeAnswers):
            raise KoineSessionError("bulk confirmation requires IntakeAnswers")
        supplied = self._verified_readings(readings)
        authorized = authorized_sample_classification(authorization)
        permitted_rank = None if authorized is None else HANDLING_CLASSIFICATION_ORDER.index(authorized)

        crossings: list[ArtefactEgress] = []
        warnings: list[ArtefactLocatorWarning] = []
        samples: list[tuple[str, int, int, str]] = []
        for admitted, _, reading in supplied:
            identifier = admitted.artefact.identifier
            classification = admitted.classification
            warned = locator_warning(identifier, admitted.locator)
            if warned is not None:
                warnings.append(warned)
            if permitted_rank is None:
                refusal = ArtefactEgressRefusal.READING_NOT_AUTHORIZED
            elif classification not in HANDLING_CLASSIFICATION_ORDER:
                refusal = ArtefactEgressRefusal.CLASSIFICATION_NOT_ORDERED
            elif HANDLING_CLASSIFICATION_ORDER.index(classification) > permitted_rank:
                refusal = ArtefactEgressRefusal.ABOVE_AUTHORIZED_CLASSIFICATION
            else:
                refusal = None
            if refusal is not None:
                crossings.append(
                    ArtefactEgress(
                        identifier=identifier,
                        classification=classification,
                        rows=0,
                        characters=0,
                        refusal=refusal,
                    )
                )
                continue
            sample = artefact_sample(reading.text)
            rows = len(sample.splitlines())
            crossings.append(
                ArtefactEgress(
                    identifier=identifier,
                    classification=classification,
                    rows=rows,
                    characters=len(sample),
                )
            )
            samples.append((identifier, rows, len(sample), sample))

        fields: dict[str, object] = {
            "use_case": self._reference_inventory(use_case.identity),
            "engagement_mode": use_case.header.engagement_mode.value,
            "artefacts": tuple(
                (
                    admitted.artefact.identifier,
                    admitted.artefact.version,
                    admitted.artefact.digest,
                    admitted.classification,
                    admitted.locator,
                    source.form.value,
                )
                for admitted, source, _ in supplied
            ),
            "residual_questions": self.intake_questions,
            "answered_by": "" if answers is None else answers.answered_by.identity,
            "answers": () if answers is None else answers.inventory,
        }
        if authorized is not None:
            fields[artefact_sample_field(authorized)] = tuple(samples)
        return (
            self._model_call(
                purpose=ModelCallPurpose.GENERATOR,
                route=INTAKE_GENERATOR_ROUTE,
                role_route=self.routes.generator,
                fields=fields,
            ),
            tuple(crossings),
            tuple(warnings),
        )

    def intake_review_call(self, use_case: UseCase, facts: tuple[IntakeFact, ...]) -> ModelCall:
        """Build the bounded intake review call for the distinct reviewer identity.

        The reviewer receives each fact beside the artefact, position, extractor
        and status behind it, so it can open the same artefact and check it. No
        artefact text crosses on this route at all, at any classification: the
        reviewer opens the artefacts in the adopting environment.
        """
        self._expect_use_case(use_case)
        if not isinstance(facts, tuple) or any(not isinstance(item, IntakeFact) for item in facts):
            raise KoineSessionError("an intake review reads recorded intake facts")
        return self._model_call(
            purpose=ModelCallPurpose.REVIEWER,
            route=INTAKE_REVIEW_ROUTE,
            role_route=self.routes.reviewer,
            fields={
                "subject": self._reference_inventory(use_case.identity),
                "recorded_facts": tuple(
                    (
                        item.section,
                        item.field,
                        item.value,
                        item.artefact.identifier,
                        item.position,
                        item.provenance.extracted_by.identity,
                        item.status.value,
                    )
                    for item in facts
                ),
                "artefacts": tuple(
                    (item.artefact.identifier, item.artefact.digest, item.classification, item.locator)
                    for item in self.intake_artefacts
                ),
                "generator_identity": self.generator.identity,
                "residual_questions": self.intake_questions,
            },
        )

    def run_intake_round(
        self,
        use_case: UseCase,
        readings: tuple[IntakeArtefactSource, ...],
        *,
        answers: IntakeAnswers | None = None,
        authorization: ModelEgressAuthorization | None = None,
    ) -> "IntakeRound":
        """Run one artefact-first intake round through the model-egress port.

        The generator reads the admitted artefacts and returns facts with their
        provenance; the record takes the declarations those facts stand for; a
        distinct reviewer identity sees the same facts through the same port.

        What crosses for each artefact is bounded and gated, and the round
        reports it: the sample that crossed, or the closed reason nothing did.

        The round computes no readiness and reads no readiness module. A review
        finding is advice and never undoes what the round recorded. The refusals
        are integrity refusals: a reading that does not match the digest it was
        admitted under, a fact from an artefact intake never admitted, a fact
        without provenance, and a parity question where there is no earlier run.
        A parity answer is refused before anything is frozen or sent.
        """
        self._expect_use_case(use_case)
        running = self
        supplied = readings
        if answers is not None:
            if not isinstance(answers, IntakeAnswers):
                raise KoineSessionError("bulk confirmation requires IntakeAnswers")
            self._reject_parity_questions(use_case, (), answers)
            answer_source = self._answer_source(use_case, answers)
            running = running.admit_intake_artefact(answer_source, answers.answered_by)
            supplied = (*self._required_readings(readings), answer_source)
        call, crossings, warnings = running._intake_call_and_egress(
            use_case, supplied, answers, authorization
        )
        proposal = running.egress.invoke(call, authorization)
        if not isinstance(proposal, IntakeRoundProposal):
            raise KoineSessionError("intake generator response must be an IntakeRoundProposal")
        running._reject_parity_questions(use_case, proposal.facts, None)
        running = running._evolve(intake_facts=(*running.intake_facts, *proposal.facts))
        updated = running._record_intake(use_case, proposal.declarations)
        review = running.egress.invoke(running.intake_review_call(updated, proposal.facts), authorization)
        if not isinstance(review, ReviewProposal):
            raise KoineSessionError("intake reviewer response must be a ReviewProposal")
        return IntakeRound(
            session=running,
            use_case=updated,
            facts=proposal.facts,
            residual_questions=running.intake_questions,
            review=review,
            artefact_egress=crossings,
            locator_warnings=warnings,
        )

    def _validate_intake(self) -> None:
        """Read the admitted artefacts and recorded facts as one consistent record."""
        if not isinstance(self.intake_artefacts, tuple) or any(
            not isinstance(item, IntakeArtefact) for item in self.intake_artefacts
        ):
            raise KoineSessionError("intake_artefacts must contain IntakeArtefact values")
        identifiers = [item.artefact.identifier for item in self.intake_artefacts]
        if len(identifiers) != len(set(identifiers)):
            raise KoineSessionError("intake artefact identities must be unique")
        if not isinstance(self.intake_facts, tuple) or any(
            not isinstance(item, IntakeFact) for item in self.intake_facts
        ):
            raise KoineSessionError("intake_facts must contain IntakeFact values")
        admitted = {item.artefact for item in self.intake_artefacts}
        unknown = sorted({item.artefact.identifier for item in self.intake_facts if item.artefact not in admitted})
        if unknown:
            raise KoineSessionError("an intake fact names an artefact intake did not admit: " + ", ".join(unknown))

    def _expect_use_case(self, use_case: UseCase) -> None:
        """Refuse a record that does not belong to this session's engagement."""
        if not isinstance(use_case, UseCase):
            raise KoineSessionError("an intake round requires a use case")
        if use_case.header.engagement_id != self.engagement.engagement_id:
            raise KoineSessionError("an intake round reads a use case of the session's engagement")
        if use_case.header.engagement_mode is not self.engagement.mode:
            raise KoineSessionError("an intake round reads a use case in the session's engagement mode")

    @staticmethod
    def _required_readings(readings: tuple[IntakeArtefactSource, ...]) -> tuple[IntakeArtefactSource, ...]:
        if not isinstance(readings, tuple) or any(
            not isinstance(item, IntakeArtefactSource) for item in readings
        ):
            raise KoineSessionError("an intake round reads IntakeArtefactSource values")
        identifiers = [item.identifier for item in readings]
        if len(identifiers) != len(set(identifiers)):
            raise KoineSessionError("an intake round reads each artefact once")
        return readings

    def _verified_readings(
        self, readings: tuple[IntakeArtefactSource, ...]
    ) -> tuple[tuple[IntakeArtefact, IntakeArtefactSource, IntakeReading], ...]:
        """Match each supplied reading to the artefact admitted under its digest."""
        admitted = {item.artefact.identifier: item for item in self.intake_artefacts}
        verified: list[tuple[IntakeArtefact, IntakeArtefactSource, IntakeReading]] = []
        for source in self._required_readings(readings):
            record = admitted.get(source.identifier)
            if record is None:
                raise KoineSessionError(f"intake artefact {source.identifier} was never admitted")
            if record.artefact.version != source.version or record.artefact.digest != source.digest:
                raise KoineSessionError(
                    f"intake artefact {source.identifier} does not match the digest it was admitted under"
                )
            verified.append((record, source, source.read()))
        return tuple(verified)

    def _answer_source(self, use_case: UseCase, answers: IntakeAnswers) -> IntakeArtefactSource:
        """Freeze one bulk confirmation as the artefact its confirmed facts cite."""
        prefix = f"{use_case.identity.identifier}-answers-"
        ordinal = 1 + sum(1 for item in self.intake_artefacts if item.artefact.identifier.startswith(prefix))
        identifier = f"{prefix}{ordinal}"
        lines = [f"answered by {answers.answered_by.identity}"]
        lines.extend(f"{section} | {field} | {value}" for section, field, value in answers.inventory)
        return IntakeArtefactSource(
            identifier=identifier,
            locator=f"intake/{identifier}",
            form=IntakeArtefactForm.TEXT,
            content=("\n".join(lines) + "\n").encode("utf-8"),
        )

    def _reject_parity_questions(
        self,
        use_case: UseCase,
        facts: tuple[IntakeFact, ...],
        answers: IntakeAnswers | None,
    ) -> None:
        """Refuse a parity question where there is no earlier run to compare with."""
        if use_case.header.engagement_mode is EngagementMode.MODERNISATION:
            return
        asked = {item.field for item in facts if item.field in PARITY_INTAKE_FIELDS}
        if answers is not None:
            asked |= {item.field for item in answers.answers if item.field in PARITY_INTAKE_FIELDS}
        if asked:
            raise KoineSessionError(
                "a greenfield use case is never asked a parity question: " + ", ".join(sorted(asked))
            )

    def _record_intake(self, use_case: UseCase, declarations: tuple[IntakeRecord, ...]) -> UseCase:
        """Record the admitted artefacts and the round's declarations on the use case."""
        recorded = {item.artefact.identifier for item in use_case.intake_artefacts}
        updated = use_case
        try:
            for artefact in self.intake_artefacts:
                if artefact.artefact.identifier not in recorded:
                    updated = updated.record_intake_artefact(artefact)
            for declaration in declarations:
                updated = getattr(updated, INTAKE_RECORD_ROUTES[type(declaration)])(declaration)
        except EngagementError as exc:
            raise KoineSessionError(str(exc)) from exc
        return updated

    def setup_call(self, brief: SetupBrief) -> ModelCall:
        """Build the bounded setup call so an environment can authorize it exactly."""
        if not isinstance(brief, SetupBrief):
            raise KoineSessionError("setup generation requires a SetupBrief")
        self._expect_phase(LifecyclePhase.SETUP)
        return self._model_call(
            purpose=ModelCallPurpose.GENERATOR,
            route=SETUP_GENERATOR_ROUTE,
            role_route=self.routes.generator,
            fields=self._setup_fields(brief),
        )

    def revise_setup_call(self, brief: SetupBrief) -> ModelCall:
        """Build a bounded correction call from an audited changes-requested review."""
        if not isinstance(brief, SetupBrief):
            raise KoineSessionError("setup revision requires a SetupBrief")
        fields = {**self._setup_fields(brief), **self._revision_fields(LifecyclePhase.SETUP)}
        return self._model_call(
            purpose=ModelCallPurpose.GENERATOR,
            route=SETUP_GENERATOR_ROUTE,
            role_route=self.routes.generator,
            fields=fields,
        )

    def outcome_call(self, framing: OutcomeFraming) -> ModelCall:
        """Build the bounded outcome-framing call after approved setup."""
        if not isinstance(framing, OutcomeFraming):
            raise KoineSessionError("outcome generation requires an OutcomeFraming")
        framing.verification.validate_for(self.engagement.mode)
        self._expect_phase(LifecyclePhase.FRAMING)
        setup = self._bound_record_for(LifecyclePhase.SETUP)
        inputs = (*framing.approved_inputs, ApprovedInput.from_reference(setup.record.document))
        _approved_inputs(inputs)
        return self._model_call(
            purpose=ModelCallPurpose.GENERATOR,
            route=OUTCOME_GENERATOR_ROUTE,
            role_route=self.routes.generator,
            fields=self._outcome_fields(framing, inputs),
        )

    def revise_outcome_call(self, framing: OutcomeFraming) -> ModelCall:
        """Build a bounded outcome correction call with prior findings in scope."""
        if not isinstance(framing, OutcomeFraming):
            raise KoineSessionError("outcome revision requires an OutcomeFraming")
        framing.verification.validate_for(self.engagement.mode)
        setup = self._bound_record_for(LifecyclePhase.SETUP)
        inputs = (*framing.approved_inputs, ApprovedInput.from_reference(setup.record.document))
        fields = {**self._outcome_fields(framing, inputs), **self._revision_fields(LifecyclePhase.FRAMING)}
        return self._model_call(
            purpose=ModelCallPurpose.GENERATOR,
            route=OUTCOME_GENERATOR_ROUTE,
            role_route=self.routes.generator,
            fields=fields,
        )

    def review_call(self) -> ModelCall:
        """Build the bounded independent-review call for the current record."""
        record = self.engagement.current_record
        if record is None:
            raise KoineSessionError("review requires a generated current record")
        bound = self._bound_record_for(record.phase)
        return self._model_call(
            purpose=ModelCallPurpose.REVIEWER,
            route=self._review_route(record.phase),
            role_route=self.routes.reviewer,
            fields={
                "subject": self._reference_inventory(record.document),
                "record_content": bound.content,
                "record_facts": bound.facts.entries,
                "generator_identity": self.generator.identity,
                "approved_inputs": self._input_inventory(bound.approved_inputs),
            },
        )

    def generate_setup(
        self, brief: SetupBrief, authorization: ModelEgressAuthorization | None = None
    ) -> "KoineSession":
        """Generate and bind the setup record through the model-egress port."""
        return self._generate(
            phase=LifecyclePhase.SETUP,
            call=self.setup_call(brief),
            approved_inputs=brief.approved_inputs,
            expected_facts=self._setup_expected_facts(brief),
            authorization=authorization,
        )

    def revise_setup(
        self, brief: SetupBrief, authorization: ModelEgressAuthorization | None = None
    ) -> "KoineSession":
        """Replace a changes-requested setup draft while retaining its review."""
        return self._generate(
            phase=LifecyclePhase.SETUP,
            call=self.revise_setup_call(brief),
            approved_inputs=brief.approved_inputs,
            expected_facts=self._setup_expected_facts(brief),
            authorization=authorization,
            revising=True,
        )

    def generate_outcome_brief(
        self, framing: OutcomeFraming, authorization: ModelEgressAuthorization | None = None
    ) -> "KoineSession":
        """Generate and bind the outcome brief through the model-egress port."""
        setup = self._bound_record_for(LifecyclePhase.SETUP)
        inputs = (*framing.approved_inputs, ApprovedInput.from_reference(setup.record.document))
        return self._generate(
            phase=LifecyclePhase.FRAMING,
            call=self.outcome_call(framing),
            approved_inputs=inputs,
            expected_facts=self._outcome_expected_facts(framing, inputs),
            authorization=authorization,
            verification_planning=framing.verification,
            success_criteria=framing.success_criteria,
        )

    def revise_outcome_brief(
        self, framing: OutcomeFraming, authorization: ModelEgressAuthorization | None = None
    ) -> "KoineSession":
        """Replace a changes-requested outcome draft while retaining its review."""
        setup = self._bound_record_for(LifecyclePhase.SETUP)
        inputs = (*framing.approved_inputs, ApprovedInput.from_reference(setup.record.document))
        return self._generate(
            phase=LifecyclePhase.FRAMING,
            call=self.revise_outcome_call(framing),
            approved_inputs=inputs,
            expected_facts=self._outcome_expected_facts(framing, inputs),
            authorization=authorization,
            revising=True,
            verification_planning=framing.verification,
            success_criteria=framing.success_criteria,
        )

    def estate_discovery_call(self, discovery: EstateDiscovery) -> ModelCall:
        """Build the bounded existing-estate tracing call after approved framing."""
        if not isinstance(discovery, EstateDiscovery):
            raise KoineSessionError("estate discovery requires an EstateDiscovery")
        self._expect_mode(EngagementMode.MODERNISATION, "estate discovery")
        self._expect_phase(LifecyclePhase.DISCOVERY)
        inputs = self._inputs_with_prior(discovery.approved_inputs, LifecyclePhase.FRAMING)
        return self._model_call(
            purpose=ModelCallPurpose.GENERATOR,
            route=ESTATE_DISCOVERY_GENERATOR_ROUTE,
            role_route=self.routes.generator,
            fields=self._estate_discovery_fields(discovery, inputs),
        )

    def revise_estate_discovery_call(self, discovery: EstateDiscovery) -> ModelCall:
        """Build a bounded correction call for an estate trace."""
        if not isinstance(discovery, EstateDiscovery):
            raise KoineSessionError("estate discovery requires an EstateDiscovery")
        self._expect_mode(EngagementMode.MODERNISATION, "estate discovery")
        inputs = self._inputs_with_prior(discovery.approved_inputs, LifecyclePhase.FRAMING)
        return self._model_call(
            purpose=ModelCallPurpose.GENERATOR,
            route=ESTATE_DISCOVERY_GENERATOR_ROUTE,
            role_route=self.routes.generator,
            fields={**self._estate_discovery_fields(discovery, inputs), **self._revision_fields(LifecyclePhase.DISCOVERY)},
        )

    def capability_discovery_call(self, discovery: CapabilityDiscovery) -> ModelCall:
        """Build the bounded greenfield capability-discovery call after framing."""
        if not isinstance(discovery, CapabilityDiscovery):
            raise KoineSessionError("capability discovery requires a CapabilityDiscovery")
        self._expect_mode(EngagementMode.GREENFIELD, "capability discovery")
        self._expect_phase(LifecyclePhase.DISCOVERY)
        inputs = self._inputs_with_prior(discovery.approved_inputs, LifecyclePhase.FRAMING)
        return self._model_call(
            purpose=ModelCallPurpose.GENERATOR,
            route=CAPABILITY_DISCOVERY_GENERATOR_ROUTE,
            role_route=self.routes.generator,
            fields=self._capability_discovery_fields(discovery, inputs),
        )

    def revise_capability_discovery_call(self, discovery: CapabilityDiscovery) -> ModelCall:
        """Build a bounded correction call for greenfield capability discovery."""
        if not isinstance(discovery, CapabilityDiscovery):
            raise KoineSessionError("capability discovery requires a CapabilityDiscovery")
        self._expect_mode(EngagementMode.GREENFIELD, "capability discovery")
        inputs = self._inputs_with_prior(discovery.approved_inputs, LifecyclePhase.FRAMING)
        return self._model_call(
            purpose=ModelCallPurpose.GENERATOR,
            route=CAPABILITY_DISCOVERY_GENERATOR_ROUTE,
            role_route=self.routes.generator,
            fields={**self._capability_discovery_fields(discovery, inputs), **self._revision_fields(LifecyclePhase.DISCOVERY)},
        )

    def design_call(self, design: TargetDesign) -> ModelCall:
        """Build the bounded target-design call after the mode-specific discovery."""
        if not isinstance(design, TargetDesign):
            raise KoineSessionError("target design requires a TargetDesign")
        self._expect_phase(LifecyclePhase.DESIGN)
        inputs = self._inputs_with_prior(design.approved_inputs, LifecyclePhase.DISCOVERY)
        return self._model_call(
            purpose=ModelCallPurpose.GENERATOR,
            route=DESIGN_GENERATOR_ROUTE,
            role_route=self.routes.generator,
            fields=self._design_fields(design, inputs),
        )

    def revise_design_call(self, design: TargetDesign) -> ModelCall:
        """Build a bounded correction call for target design."""
        if not isinstance(design, TargetDesign):
            raise KoineSessionError("target design requires a TargetDesign")
        inputs = self._inputs_with_prior(design.approved_inputs, LifecyclePhase.DISCOVERY)
        return self._model_call(
            purpose=ModelCallPurpose.GENERATOR,
            route=DESIGN_GENERATOR_ROUTE,
            role_route=self.routes.generator,
            fields={**self._design_fields(design, inputs), **self._revision_fields(LifecyclePhase.DESIGN)},
        )

    def delivery_contract_call(self, contract: DeliveryContract) -> ModelCall:
        """Build the bounded, versioned delivery-contract call after approved design."""
        if not isinstance(contract, DeliveryContract):
            raise KoineSessionError("delivery contract requires a DeliveryContract")
        self._expect_phase(LifecyclePhase.DELIVERY_CONTRACT)
        inputs = self._inputs_with_prior(contract.approved_inputs, LifecyclePhase.DESIGN)
        return self._model_call(
            purpose=ModelCallPurpose.GENERATOR,
            route=DELIVERY_CONTRACT_GENERATOR_ROUTE,
            role_route=self.routes.generator,
            fields=self._delivery_contract_fields(contract, inputs),
        )

    def revise_delivery_contract_call(self, contract: DeliveryContract) -> ModelCall:
        """Build a bounded correction call for the delivery contract."""
        if not isinstance(contract, DeliveryContract):
            raise KoineSessionError("delivery contract requires a DeliveryContract")
        inputs = self._inputs_with_prior(contract.approved_inputs, LifecyclePhase.DESIGN)
        return self._model_call(
            purpose=ModelCallPurpose.GENERATOR,
            route=DELIVERY_CONTRACT_GENERATOR_ROUTE,
            role_route=self.routes.generator,
            fields={**self._delivery_contract_fields(contract, inputs), **self._revision_fields(LifecyclePhase.DELIVERY_CONTRACT)},
        )

    def generate_estate_discovery(
        self, discovery: EstateDiscovery, authorization: ModelEgressAuthorization | None = None
    ) -> "KoineSession":
        """Trace current estate facts without collapsing continuity into legacy accident."""
        inputs = self._inputs_with_prior(discovery.approved_inputs, LifecyclePhase.FRAMING)
        return self._generate(
            phase=LifecyclePhase.DISCOVERY,
            call=self.estate_discovery_call(discovery),
            approved_inputs=inputs,
            expected_facts=self._estate_discovery_expected_facts(discovery, inputs),
            authorization=authorization,
        )

    def revise_estate_discovery(
        self, discovery: EstateDiscovery, authorization: ModelEgressAuthorization | None = None
    ) -> "KoineSession":
        """Revise an estate trace only through its retained review finding."""
        inputs = self._inputs_with_prior(discovery.approved_inputs, LifecyclePhase.FRAMING)
        return self._generate(
            phase=LifecyclePhase.DISCOVERY,
            call=self.revise_estate_discovery_call(discovery),
            approved_inputs=inputs,
            expected_facts=self._estate_discovery_expected_facts(discovery, inputs),
            authorization=authorization,
            revising=True,
        )

    def generate_capability_discovery(
        self, discovery: CapabilityDiscovery, authorization: ModelEgressAuthorization | None = None
    ) -> "KoineSession":
        """Discover greenfield capabilities without inventing an estate or parity claim."""
        inputs = self._inputs_with_prior(discovery.approved_inputs, LifecyclePhase.FRAMING)
        return self._generate(
            phase=LifecyclePhase.DISCOVERY,
            call=self.capability_discovery_call(discovery),
            approved_inputs=inputs,
            expected_facts=self._capability_discovery_expected_facts(discovery, inputs),
            authorization=authorization,
        )

    def revise_capability_discovery(
        self, discovery: CapabilityDiscovery, authorization: ModelEgressAuthorization | None = None
    ) -> "KoineSession":
        """Revise a greenfield capability record through its retained review finding."""
        inputs = self._inputs_with_prior(discovery.approved_inputs, LifecyclePhase.FRAMING)
        return self._generate(
            phase=LifecyclePhase.DISCOVERY,
            call=self.revise_capability_discovery_call(discovery),
            approved_inputs=inputs,
            expected_facts=self._capability_discovery_expected_facts(discovery, inputs),
            authorization=authorization,
            revising=True,
        )

    def generate_target_design(
        self, design: TargetDesign, authorization: ModelEgressAuthorization | None = None
    ) -> "KoineSession":
        """Generate target architecture, operating model and transition increments."""
        inputs = self._inputs_with_prior(design.approved_inputs, LifecyclePhase.DISCOVERY)
        return self._generate(
            phase=LifecyclePhase.DESIGN,
            call=self.design_call(design),
            approved_inputs=inputs,
            expected_facts=self._design_expected_facts(design, inputs),
            authorization=authorization,
        )

    def revise_target_design(
        self, design: TargetDesign, authorization: ModelEgressAuthorization | None = None
    ) -> "KoineSession":
        """Revise a target design only through its retained review finding."""
        inputs = self._inputs_with_prior(design.approved_inputs, LifecyclePhase.DISCOVERY)
        return self._generate(
            phase=LifecyclePhase.DESIGN,
            call=self.revise_design_call(design),
            approved_inputs=inputs,
            expected_facts=self._design_expected_facts(design, inputs),
            authorization=authorization,
            revising=True,
        )

    def generate_delivery_contract(
        self, contract: DeliveryContract, authorization: ModelEgressAuthorization | None = None
    ) -> "KoineSession":
        """Generate the versioned delivery contract that later adapters may project."""
        inputs = self._inputs_with_prior(contract.approved_inputs, LifecyclePhase.DESIGN)
        return self._generate(
            phase=LifecyclePhase.DELIVERY_CONTRACT,
            call=self.delivery_contract_call(contract),
            approved_inputs=inputs,
            expected_facts=self._delivery_contract_expected_facts(contract, inputs),
            authorization=authorization,
            delivery_contract=contract,
        )

    def revise_delivery_contract(
        self, contract: DeliveryContract, authorization: ModelEgressAuthorization | None = None
    ) -> "KoineSession":
        """Revise a delivery contract only through its retained review finding."""
        inputs = self._inputs_with_prior(contract.approved_inputs, LifecyclePhase.DESIGN)
        return self._generate(
            phase=LifecyclePhase.DELIVERY_CONTRACT,
            call=self.revise_delivery_contract_call(contract),
            approved_inputs=inputs,
            expected_facts=self._delivery_contract_expected_facts(contract, inputs),
            authorization=authorization,
            revising=True,
            delivery_contract=contract,
        )

    def review_current(self, authorization: ModelEgressAuthorization | None = None) -> "KoineSession":
        """Obtain a distinct review identity's disposition through the model-egress port."""
        record = self.engagement.current_record
        if record is None:
            raise KoineSessionError("review requires a generated current record")
        if any(item.subject == record.document for item in self.engagement.reviews):
            raise KoineSessionError("the current record already has an independent review")
        proposal = self.egress.invoke(self.review_call(), authorization)
        if not isinstance(proposal, ReviewProposal):
            raise KoineSessionError("reviewer response must be a ReviewProposal")
        try:
            engagement = self.engagement.review(
                RecordReview(
                    subject=record.document,
                    reviewer=self.reviewer,
                    disposition=proposal.disposition,
                    findings=proposal.findings,
                )
            )
        except EngagementError as exc:
            raise KoineSessionError(str(exc)) from exc
        return self._evolve(engagement=engagement)

    def adjudicate_current(self, decision: NamedHumanDecision) -> "KoineSession":
        """Record the named acceptance authority's disposition of the review."""
        if not isinstance(decision, NamedHumanDecision):
            raise KoineSessionError("adjudication requires a NamedHumanDecision")
        if decision.kind is not DecisionKind.RECORD_APPROVAL:
            raise KoineSessionError("setup and framing adjudication requires a record approval")
        if decision.decided_by.identity != self.authorities.acceptance_authority.identity:
            raise KoineSessionError("only the named acceptance authority may adjudicate this record")
        try:
            engagement = self.engagement.approve(decision)
        except EngagementError as exc:
            raise KoineSessionError(str(exc)) from exc
        return self._evolve(engagement=engagement)

    def advance(self) -> "KoineSession":
        """Advance after independent review and named human adjudication."""
        try:
            engagement = self.engagement.advance()
        except EngagementError as exc:
            raise KoineSessionError(str(exc)) from exc
        return self._evolve(engagement=engagement)

    @property
    def approved_outcome_brief(self) -> BoundGeneratedRecord:
        """Return the outcome brief only once its review and human approval exist."""
        return self._approved_record(LifecyclePhase.FRAMING, "outcome brief")

    @property
    def approved_delivery_contract(self) -> BoundGeneratedRecord:
        """Return the approved contract record without changing the stages facade."""
        return self._approved_record(LifecyclePhase.DELIVERY_CONTRACT, "delivery contract")

    @property
    def approved_delivery_graph(self) -> DeliveryContract:
        """Return the exact graph only after its bound record is independently approved."""
        self.approved_delivery_contract
        if self.delivery_contract is None:
            raise KoineSessionError("no typed delivery contract is retained for the approved record")
        return self.delivery_contract

    def _approved_record(self, phase: LifecyclePhase, label: str) -> BoundGeneratedRecord:
        record = self._bound_record_for(phase)
        review = next((item for item in self.engagement.reviews if item.subject == record.record.document), None)
        approval = next(
            (
                item
                for item in self.engagement.decisions
                if item.subject == record.record.document and item.kind is DecisionKind.RECORD_APPROVAL
            ),
            None,
        )
        if review is None or review.disposition is not ReviewDisposition.APPROVED or approval is None:
            raise KoineSessionError(f"{label} is not independently reviewed and human-approved")
        return record

    def _generate(
        self,
        *,
        phase: LifecyclePhase,
        call: ModelCall,
        approved_inputs: tuple[ApprovedInput, ...],
        expected_facts: dict[str, RecordFactValue],
        authorization: ModelEgressAuthorization | None,
        revising: bool = False,
        verification_planning: VerificationPlanning | None = None,
        success_criteria: tuple[SuccessCriterion, ...] = (),
        delivery_contract: DeliveryContract | None = None,
    ) -> "KoineSession":
        if revising:
            self._expect_revision(phase)
        else:
            self._expect_phase(phase)
        inputs = _approved_inputs(approved_inputs)
        proposal = self.egress.invoke(call, authorization)
        if not isinstance(proposal, GeneratedRecordProposal):
            raise KoineSessionError("generator response must be a GeneratedRecordProposal")
        self._validate_record_facts(phase, proposal.facts, expected_facts, mode=self.engagement.mode)
        discovery_kind = None
        if phase is LifecyclePhase.DISCOVERY:
            discovery_kind = (
                DiscoveryKind.ESTATE
                if self.engagement.mode is EngagementMode.MODERNISATION
                else DiscoveryKind.CAPABILITY
            )
        record = StageRecord(
            phase=phase,
            document=proposal.document,
            authored_by=self.generator,
            discovery_kind=discovery_kind,
        )
        bound = BoundGeneratedRecord(
            record=record,
            content=proposal.content,
            facts=proposal.facts,
            approved_inputs=inputs,
        )
        try:
            engagement = self.engagement.revise(record) if revising else self.engagement.submit(record)
        except EngagementError as exc:
            raise KoineSessionError(str(exc)) from exc
        if phase is LifecyclePhase.DELIVERY_CONTRACT and delivery_contract is None:
            raise KoineSessionError("delivery-contract generation requires a typed DeliveryContract")
        if phase is not LifecyclePhase.DELIVERY_CONTRACT and delivery_contract is not None:
            raise KoineSessionError("only delivery-contract generation may retain a DeliveryContract")
        return self._evolve(
            engagement=engagement,
            generated_records=(*self.generated_records, bound),
            verification_planning=verification_planning or self.verification_planning,
            success_criteria=success_criteria or self.success_criteria,
            delivery_contract=delivery_contract or self.delivery_contract,
        )

    def _model_call(
        self,
        *,
        purpose: ModelCallPurpose,
        route: str,
        role_route: SessionModelRoute,
        fields: dict[str, object],
    ) -> ModelCall:
        return ModelCall(
            engagement_id=self.engagement.engagement_id,
            case_id=self.session_id,
            purpose=purpose,
            route=route,
            destination=role_route.destination,
            fields=fields,
            data_class=role_route.data_class,
            retention_policy=role_route.retention_policy,
            evidence_policy=role_route.evidence_policy,
            mode=role_route.mode,
        )

    def _evolve(self, **changes: Any) -> "KoineSession":
        return replace(self, **changes)

    def _expect_phase(self, phase: LifecyclePhase) -> None:
        if self.engagement.phase is not phase:
            raise KoineSessionError(f"expected {phase.value} phase, got {self.engagement.phase.value}")
        if self.engagement.current_record is not None:
            raise KoineSessionError(f"{phase.value} already has a generated record")

    def _expect_revision(self, phase: LifecyclePhase) -> None:
        if self.engagement.phase is not phase:
            raise KoineSessionError(f"expected {phase.value} phase, got {self.engagement.phase.value}")
        record = self.engagement.current_record
        if record is None:
            raise KoineSessionError(f"{phase.value} has no generated record to revise")
        review = next((item for item in self.engagement.reviews if item.subject == record.document), None)
        if review is None or review.disposition is not ReviewDisposition.CHANGES_REQUESTED:
            raise KoineSessionError("record revision requires a changes-requested independent review")

    def _bound_record_for(self, phase: LifecyclePhase) -> BoundGeneratedRecord:
        active = next((item for item in self.engagement.records if item.phase is phase), None)
        record = next((item for item in reversed(self.generated_records) if item.record == active), None)
        if record is None:
            raise KoineSessionError(f"{phase.value} record is not available in this session")
        return record

    def _validate_generated_records(self) -> None:
        expected = tuple(record for record in self.engagement.records if record.phase in {
            LifecyclePhase.SETUP,
            LifecyclePhase.FRAMING,
            LifecyclePhase.DISCOVERY,
            LifecyclePhase.DESIGN,
            LifecyclePhase.DELIVERY_CONTRACT,
        })
        superseded = {revision.superseded.document for revision in self.engagement.record_revisions}
        observed = tuple(item.record for item in self.generated_records if item.record.document not in superseded)
        if observed != expected:
            raise KoineSessionError("session-generated records must exactly match the engagement contract prefix")
        generated_by_document = {item.record.document: item for item in self.generated_records}
        if len(generated_by_document) != len(self.generated_records):
            raise KoineSessionError("session-generated record identities must be unique")
        active_framing_record = next(
            (
                item
                for item in self.generated_records
                if item.record.phase is LifecyclePhase.FRAMING
                and item.record.document not in superseded
            ),
            None,
        )
        if active_framing_record is None:
            if self.success_criteria:
                raise KoineSessionError("retained success criteria require an active framing record")
        else:
            if not self.success_criteria or self.verification_planning is None:
                raise KoineSessionError("an active framing record requires retained executable success criteria")
            facts = active_framing_record.facts.as_mapping()
            if facts.get("success signals") != tuple(item.signal for item in self.success_criteria):
                raise KoineSessionError("framing record does not bind the retained success signals")
            if facts.get("success criteria") != tuple(item.inventory for item in self.success_criteria):
                raise KoineSessionError("framing record does not bind the retained success criteria")
            for criterion in self.success_criteria:
                if criterion.check_family not in self.verification_planning.check_families:
                    raise KoineSessionError("retained success criterion uses an undeclared check family")
                if criterion.acceptance_rule not in self.verification_planning.acceptance_rules:
                    raise KoineSessionError("retained success criterion uses an undeclared acceptance rule")
                required_inputs = (
                    ApprovedInput.from_reference(criterion.validator),
                    *criterion.evidence,
                )
                if any(item not in active_framing_record.approved_inputs for item in required_inputs):
                    raise KoineSessionError(
                        "retained success criterion validator and evidence are not approved framing inputs"
                    )
        for revision in self.engagement.record_revisions:
            superseded_bound = generated_by_document.get(revision.superseded.document)
            replacement_bound = generated_by_document.get(revision.replacement.document)
            if (
                superseded_bound is None
                or replacement_bound is None
                or superseded_bound.record != revision.superseded
                or replacement_bound.record != revision.replacement
            ):
                raise KoineSessionError("session-generated records must retain every audited record revision")
            if revision.review.reviewer.identity != self.reviewer.identity:
                raise KoineSessionError("every retained revision must use the configured reviewer identity")
        for bound in self.generated_records:
            if bound.record.authored_by != self.generator:
                raise KoineSessionError("all session-generated records must retain the configured generator identity")
            schema_name = self._schema_name(bound.record.phase, self.engagement.mode)
            expected_facts: dict[str, RecordFactValue] = {}
            if schema_name == "setup":
                expected_facts["authorities"] = self._authority_fact()
                expected_facts["evidence identifiers"] = self._evidence_fact(bound.approved_inputs)
            else:
                expected_facts["evidence"] = self._evidence_fact(bound.approved_inputs)
                if schema_name == "framing":
                    expected_facts["authorities"] = self._authority_fact()
            active_record = bound.record.document not in superseded
            if active_record and bound.record.phase is not LifecyclePhase.SETUP and self.verification_planning is None:
                raise KoineSessionError("framing and later records require retained verification planning")
            if active_record and bound.record.phase is not LifecyclePhase.SETUP:
                assert self.verification_planning is not None
                self.verification_planning.validate_for(self.engagement.mode)
                expected_facts.update(self._verification_facts(self.verification_planning))
            self._validate_record_facts(
                bound.record.phase,
                bound.facts,
                expected_facts,
                mode=self.engagement.mode,
            )
        session_documents = set(generated_by_document)
        for review in self.engagement.reviews:
            if review.subject in session_documents and review.reviewer.identity != self.reviewer.identity:
                raise KoineSessionError("session records must retain the configured reviewer identity")
        for decision in self.engagement.decisions:
            if (
                decision.kind is DecisionKind.RECORD_APPROVAL
                and decision.subject in session_documents
                and decision.decided_by.identity != self.authorities.acceptance_authority.identity
            ):
                raise KoineSessionError("session records must retain the named acceptance authority")
        active_delivery_records = tuple(
            bound
            for bound in self.generated_records
            if bound.record.phase is LifecyclePhase.DELIVERY_CONTRACT
            and bound.record.document not in superseded
        )
        if active_delivery_records:
            if len(active_delivery_records) != 1 or self.delivery_contract is None:
                raise KoineSessionError("an active delivery-contract record requires one retained typed contract")
            expected_inputs = self._inputs_with_prior(
                self.delivery_contract.approved_inputs,
                LifecyclePhase.DESIGN,
            )
            _validate_delivery_contract_binding(
                active_delivery_records[0],
                self.delivery_contract,
                expected_inputs,
            )
        elif self.delivery_contract is not None:
            raise KoineSessionError("a retained typed delivery contract requires an active delivery-contract record")

    @staticmethod
    def _input_inventory(inputs: tuple[ApprovedInput, ...]) -> tuple[tuple[str, str, str], ...]:
        return tuple((item.identifier, item.version, item.digest) for item in inputs)

    @staticmethod
    def _reference_inventory(reference: ImmutableReference) -> tuple[str, str, str]:
        return (reference.identifier, reference.version, reference.digest)

    def _review_route(self, phase: LifecyclePhase) -> str:
        routes = {
            LifecyclePhase.SETUP: SETUP_REVIEW_ROUTE,
            LifecyclePhase.FRAMING: OUTCOME_REVIEW_ROUTE,
            LifecyclePhase.DISCOVERY: (
                ESTATE_DISCOVERY_REVIEW_ROUTE
                if self.engagement.mode is EngagementMode.MODERNISATION
                else CAPABILITY_DISCOVERY_REVIEW_ROUTE
            ),
            LifecyclePhase.DESIGN: DESIGN_REVIEW_ROUTE,
            LifecyclePhase.DELIVERY_CONTRACT: DELIVERY_CONTRACT_REVIEW_ROUTE,
        }
        try:
            return routes[phase]
        except KeyError as exc:
            raise KoineSessionError(f"no Koine review route exists for {phase.value}") from exc

    def _setup_fields(self, brief: SetupBrief) -> dict[str, object]:
        return {
            "owner": self.authorities.owner.identity,
            "evidence_authority": self.authorities.evidence_authority.identity,
            "acceptance_authority": self.authorities.acceptance_authority.identity,
            "platform_boundary": brief.platform_boundary,
            "constraints": brief.constraints,
            "approved_inputs": self._input_inventory(brief.approved_inputs),
        }

    def _outcome_fields(
        self, framing: OutcomeFraming, inputs: tuple[ApprovedInput, ...]
    ) -> dict[str, object]:
        return {
            "owner": self.authorities.owner.identity,
            "evidence_authority": self.authorities.evidence_authority.identity,
            "acceptance_authority": self.authorities.acceptance_authority.identity,
            "consumer_outcome": framing.consumer_outcome,
            "success_signals": framing.success_signals,
            "scope": framing.scope,
            "approved_inputs": self._input_inventory(inputs),
            **self._verification_facts(framing.verification),
            "success_criteria": tuple(item.inventory for item in framing.success_criteria),
        }

    def _estate_discovery_fields(
        self, discovery: EstateDiscovery, inputs: tuple[ApprovedInput, ...]
    ) -> dict[str, object]:
        return {
            "processing": discovery.processing,
            "data": discovery.data,
            "interfaces": discovery.interfaces,
            "controls": discovery.controls,
            "continuity_needs": discovery.continuity_needs,
            "accidental_legacy_behaviour": discovery.accidental_legacy_behaviour,
            "uncertainty": discovery.uncertainty,
            "approved_inputs": self._input_inventory(inputs),
            **self._verification_facts(self._require_verification_planning()),
        }

    def _capability_discovery_fields(
        self, discovery: CapabilityDiscovery, inputs: tuple[ApprovedInput, ...]
    ) -> dict[str, object]:
        return {
            "required_capabilities": discovery.required_capabilities,
            "constraints": discovery.constraints,
            "uncertainty": discovery.uncertainty,
            "approved_inputs": self._input_inventory(inputs),
            **self._verification_facts(self._require_verification_planning()),
        }

    def _design_fields(self, design: TargetDesign, inputs: tuple[ApprovedInput, ...]) -> dict[str, object]:
        return {
            "architecture": design.architecture,
            "operating_model": design.operating_model,
            "contracts": design.contracts,
            "transition": design.transition,
            "increments": design.increments,
            "risks": design.risks,
            "acceptance_signals": design.acceptance_signals,
            "approved_inputs": self._input_inventory(inputs),
            **self._verification_facts(self._require_verification_planning()),
        }

    def _delivery_contract_fields(
        self, contract: DeliveryContract, inputs: tuple[ApprovedInput, ...]
    ) -> dict[str, object]:
        return {
            "package_inventory": contract.package_inventory,
            "dependency_inventory": contract.dependency_inventory,
            "gate_inventory": contract.gate_inventory,
            "exclusions": contract.exclusions,
            "acceptance": contract.acceptance,
            "approved_inputs": self._input_inventory(inputs),
            **self._verification_facts(self._require_verification_planning()),
        }

    def _inputs_with_prior(
        self, approved_inputs: tuple[ApprovedInput, ...], prior_phase: LifecyclePhase
    ) -> tuple[ApprovedInput, ...]:
        prior = self._bound_record_for(prior_phase)
        inputs = (*approved_inputs, ApprovedInput.from_reference(prior.record.document))
        return _approved_inputs(inputs)

    def _expect_mode(self, mode: EngagementMode, action: str) -> None:
        if self.engagement.mode is not mode:
            raise KoineSessionError(f"{action} is not permitted for {self.engagement.mode.value}")

    def _require_verification_planning(self) -> VerificationPlanning:
        if self.verification_planning is None:
            raise KoineSessionError("discovery and later records require approved outcome verification planning")
        self.verification_planning.validate_for(self.engagement.mode)
        return self.verification_planning

    @staticmethod
    def _verification_facts(planning: VerificationPlanning) -> dict[str, RecordFactValue]:
        return {
            "verification case intent": planning.case_intent.value,
            "check families": tuple(item.value for item in planning.check_families),
            "lineage/checkpoint expectations": planning.checkpoint_inventory,
            "acceptance rules": planning.acceptance_rules,
        }

    def _revision_fields(self, phase: LifecyclePhase) -> dict[str, object]:
        self._expect_revision(phase)
        record = self.engagement.current_record
        assert record is not None
        review = next(item for item in self.engagement.reviews if item.subject == record.document)
        return {
            "revision_of": self._reference_inventory(record.document),
            "review_findings": self._reference_inventory(review.findings),
        }

    def _setup_expected_facts(self, brief: SetupBrief) -> dict[str, RecordFactValue]:
        return {
            "platform boundary": brief.platform_boundary,
            "authorities": self._authority_fact(),
            "constraints": brief.constraints,
            "evidence identifiers": self._evidence_fact(brief.approved_inputs),
        }

    def _outcome_expected_facts(
        self, framing: OutcomeFraming, inputs: tuple[ApprovedInput, ...]
    ) -> dict[str, RecordFactValue]:
        return {
            "consumer outcome": framing.consumer_outcome,
            "success signals": framing.success_signals,
            "scope": framing.scope,
            "authorities": self._authority_fact(),
            "evidence": self._evidence_fact(inputs),
            "success criteria": tuple(item.inventory for item in framing.success_criteria),
            **self._verification_facts(framing.verification),
        }

    def _estate_discovery_expected_facts(
        self, discovery: EstateDiscovery, inputs: tuple[ApprovedInput, ...]
    ) -> dict[str, RecordFactValue]:
        return {
            "processing": discovery.processing,
            "data": discovery.data,
            "interfaces": discovery.interfaces,
            "controls": discovery.controls,
            "continuity needs": discovery.continuity_needs,
            "accidental legacy behaviour": discovery.accidental_legacy_behaviour,
            "evidence": self._evidence_fact(inputs),
            "uncertainty": discovery.uncertainty,
            **self._verification_facts(self._require_verification_planning()),
        }

    def _capability_discovery_expected_facts(
        self, discovery: CapabilityDiscovery, inputs: tuple[ApprovedInput, ...]
    ) -> dict[str, RecordFactValue]:
        return {
            "required capabilities": discovery.required_capabilities,
            "constraints": discovery.constraints,
            "evidence": self._evidence_fact(inputs),
            "uncertainty": discovery.uncertainty,
            **self._verification_facts(self._require_verification_planning()),
        }

    def _design_expected_facts(
        self, design: TargetDesign, inputs: tuple[ApprovedInput, ...]
    ) -> dict[str, RecordFactValue]:
        return {
            "architecture": design.architecture,
            "operating model": design.operating_model,
            "contracts": design.contracts,
            "transition": design.transition,
            "increments": design.increments,
            "risks": design.risks,
            "acceptance signals": design.acceptance_signals,
            "evidence": self._evidence_fact(inputs),
            **self._verification_facts(self._require_verification_planning()),
        }

    def _delivery_contract_expected_facts(
        self, contract: DeliveryContract, inputs: tuple[ApprovedInput, ...]
    ) -> dict[str, RecordFactValue]:
        return {
            "package inventory": contract.package_inventory,
            "dependency inventory": contract.dependency_inventory,
            "gate inventory": contract.gate_inventory,
            "exclusions": contract.exclusions,
            "acceptance": contract.acceptance,
            "evidence": self._evidence_fact(inputs),
            **self._verification_facts(self._require_verification_planning()),
        }

    def _authority_fact(self) -> tuple[str, ...]:
        return (
            self.authorities.owner.identity,
            self.authorities.evidence_authority.identity,
            self.authorities.acceptance_authority.identity,
        )

    @staticmethod
    def _evidence_fact(inputs: tuple[ApprovedInput, ...]) -> tuple[str, ...]:
        return tuple(f"{item.identifier}@{item.version}#{item.digest}" for item in inputs)

    @staticmethod
    def _validate_record_facts(
        phase: LifecyclePhase,
        facts: RecordFacts,
        expected_facts: dict[str, RecordFactValue],
        *,
        mode: EngagementMode,
    ) -> None:
        schema_name = KoineSession._schema_name(phase, mode)
        required = ENGAGEMENT_RECORD_FIELDS[schema_name]
        observed = facts.as_mapping()
        missing = tuple(field for field in required if field not in observed)
        unexpected = tuple(field for field in observed if field not in required)
        if missing or unexpected:
            raise KoineSessionError(
                f"generated {schema_name} facts do not match the owned schema; "
                f"missing={missing!r}, unexpected={unexpected!r}"
            )
        for field, expected in expected_facts.items():
            if observed[field] != expected:
                raise KoineSessionError(f"generated {schema_name} fact {field!r} does not match approved framing")

    @staticmethod
    def _schema_name(phase: LifecyclePhase, mode: EngagementMode) -> str:
        if phase is LifecyclePhase.SETUP:
            return "setup"
        if phase is LifecyclePhase.FRAMING:
            return "framing"
        if phase is LifecyclePhase.DISCOVERY:
            return "estate_discovery" if mode is EngagementMode.MODERNISATION else "capability_discovery"
        if phase is LifecyclePhase.DESIGN:
            return "design"
        if phase is LifecyclePhase.DELIVERY_CONTRACT:
            return "delivery_contract"
        raise KoineSessionError(f"no record-fact schema exists for {phase.value}")


@dataclass(frozen=True)
class IntakeRound:
    """One completed intake round: what it left, what it read, and what remains.

    The residual questions are the intake sections no recorded fact answers. The
    review is the distinct reviewer identity's finding, held as advice beside the
    record rather than as a condition of it. The artefact egress is what the
    round put across the model boundary, artefact by artefact.

    The locator warnings sit beside that report and read the same way: one at
    most for each admitted artefact whose locator reads like an address. A
    warning is a label. It stopped nothing, it refused nothing, and every
    artefact it names was admitted and stays admitted.
    """

    session: KoineSession
    use_case: UseCase
    facts: tuple[IntakeFact, ...]
    residual_questions: tuple[str, ...]
    review: ReviewProposal
    artefact_egress: tuple[ArtefactEgress, ...] = ()
    locator_warnings: tuple[ArtefactLocatorWarning, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.session, KoineSession):
            raise KoineSessionError("an intake round leaves a session")
        if not isinstance(self.use_case, UseCase):
            raise KoineSessionError("an intake round leaves a use case")
        if not isinstance(self.facts, tuple) or any(not isinstance(item, IntakeFact) for item in self.facts):
            raise KoineSessionError("an intake round holds IntakeFact values")
        if not isinstance(self.review, ReviewProposal):
            raise KoineSessionError("an intake round holds an independent review finding")
        if not isinstance(self.artefact_egress, tuple) or any(
            not isinstance(item, ArtefactEgress) for item in self.artefact_egress
        ):
            raise KoineSessionError("an intake round reports ArtefactEgress values")
        if not isinstance(self.locator_warnings, tuple) or any(
            not isinstance(item, ArtefactLocatorWarning) for item in self.locator_warnings
        ):
            raise KoineSessionError("an intake round reports ArtefactLocatorWarning values")

    @property
    def sample_row_bound(self) -> int:
        """The declared row bound the round's samples were cut to.

        A reported row count is the lines present in a sample, which the
        character bound can leave below this bound.
        """
        return INTAKE_SAMPLE_ROWS

    @property
    def sample_character_bound(self) -> int:
        """The declared character bound the round's samples were cut to."""
        return INTAKE_SAMPLE_CHARACTERS

    @property
    def refused_crossings(self) -> tuple[ArtefactEgress, ...]:
        """The artefacts whose text did not cross, each with its closed reason."""
        return tuple(item for item in self.artefact_egress if not item.crossed)
