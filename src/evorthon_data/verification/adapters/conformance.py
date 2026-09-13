"""The suite an adopter runs against an adapter of their own.

An adapter written for one environment cannot be read by this product, run by
it or audited by it. What this product can do is watch an adapter answer the
port contract it claims and say, in closed words, where the answer contradicts
the claim. That is what this suite is: an adopter builds their adapter over the
material this module carries, hands the suite the surface, and reads the
report.

The material is plain values. Evidence records, a candidate declaration,
frozen case facts, the declared outputs for those facts, and a second set of
facts for a case nothing here is declared against. It is invented material and
it names no system.

What the suite refuses is a contradiction and nothing else. A declaration is
labelling: it says what an adapter claims. So a claim that the port shows to be
false is a finding, and a claim the port has nothing to say about is left
alone. Six contradictions are read.

* A capability the adapter claims and the port does not show.
* The two holding capabilities claimed together, when material is held in one
  place and a port can never show which.
* An assurance above the plainest one with no input named to rest it on.
* A port contract version other than the one the ports declare.
* A value of the wrong shape where the contract declares a plain one.
* A value carrying a route to somebody's machine or a written credential.

That last one is why this module reads the one owner of the machine-route and
credential shapes rather than writing a shape of its own. Every plain value an
adapter sends across a port is read: the fields of its declaration, the fields
of a stored evidence record, the fields of a candidate declaration, the fields
of every produced output, and the words of every refusal. Stored evidence
content is not read: those bytes are the environment's own material, which the
intake workflow digests and compares, and reading them here would be this
product deciding what an adopter's evidence may say.

The layering around digests is worth stating plainly, because it is easy to
assume the opposite. This suite reads the form of a declared digest and never
its truth. Whether the bytes of a record produce the digest the record claims
is the intake workflow's question, it is answered there over every case, and no
adapter is trusted for it.

A finding names the port contract it was found against, the version of that
contract, the method or the field it was found in, and one closed reason. It
never carries the value it found. A report that repeated an offending value
would carry the leak onward into whatever read the report, which is the failure
this suite exists to catch.
"""
# evorthon-implements: EVD-README-017
from __future__ import annotations

# evorthon-component: verification_adapters

from dataclasses import dataclass, replace
from enum import Enum

from evorthon_data.boundary_patterns import (
    CONTROL_CHARACTER,
    CREDENTIAL_PATTERNS as DECLARED_CREDENTIAL_PATTERNS,
    CREDENTIAL_SHAPES,
    MACHINE_ROUTE_PATTERNS,
    MACHINE_ROUTE_SHAPES,
    RAW_ROW_PATTERNS as DECLARED_RAW_ROW_PATTERNS,
    shape_carried,
    shapes,
)
from evorthon_data.verification.adapters.declaration import (
    ADAPTER_CAPABILITIES,
    ASSURANCE_INPUT_FIELDS,
    ASSURANCE_LEVELS,
    AdapterDeclaration,
    HOLDING_CAPABILITIES,
    PRESENTS_A_CERTIFICATE,
    READS_HELD_EVIDENCE,
    REPLAYS_DECLARED_OUTPUTS,
)
from evorthon_data.verification.adapters.material import ReplayDeclaration
from evorthon_data.verification.ports.contracts import (
    CANONICALISATION_BINDING,
    CandidateDeclaration,
    CandidateRunnerPort,
    EvidenceNotHeld,
    EvidenceRepositoryPort,
    FactBinding,
    FrozenCaseFacts,
    FrozenFact,
    GRAIN_BINDING,
    PORT_CONTRACT_VERSION,
    PortRefusal,
    ProducedOutput,
    SCHEMA_BINDING,
    StoredEvidence,
)


# The two contracts a finding can be found against, named by the contracts
# themselves so a renamed port cannot leave a stale name in a report.
CANDIDATE_RUNNER_CONTRACT = CandidateRunnerPort.__name__
EVIDENCE_REPOSITORY_CONTRACT = EvidenceRepositoryPort.__name__

# The shapes this suite reads, from the one owner of all three families. A
# crossing value is one declared value and not a page of prose, so every
# machine-route and credential shape is read. The control-character shape is
# read for a value that is not plain text at all.
MACHINE_ROUTES = shapes(MACHINE_ROUTE_PATTERNS, MACHINE_ROUTE_SHAPES)
CREDENTIALS = shapes(DECLARED_CREDENTIAL_PATTERNS, CREDENTIAL_SHAPES)
CONTROL_CHARACTERS = shapes(DECLARED_RAW_ROW_PATTERNS, (CONTROL_CHARACTER,))

# The characters a route is written from, by code point, so the references
# below carry no route this file spells out.
_STOP = chr(46)
_SEPARATOR = chr(47)
_MARK = chr(58)
_ESCAPE = chr(92)

CONFORMANCE_EVIDENCE: tuple[StoredEvidence, ...] = (
    StoredEvidence(
        evidence_id="conformance-lineage-note",
        version="v1",
        content=b"A lineage note the conformance material carries. Invented content, and no real system.\n",
        declared_digest="blake2b-256:ed4fe646fdc17fa0944679cd7e3aac2b6470bdd95f23398de4ff5bb96ac58fda",
        recorded_at="2026-01-05T00:00:00Z",
        valid_until="2030-01-05T00:00:00Z",
        summary="An invented lineage note held for the conformance run.",
    ),
    StoredEvidence(
        evidence_id="conformance-checkpoint-note",
        version="v1",
        content=b"A checkpoint note the conformance material carries. Invented content, and no real system.\n",
        declared_digest="blake2b-256:5f85349c0ea9b47d5ddbfde68646c8b33f0705ffa7ed3e9424d91209c6730be6",
        recorded_at="2026-01-05T00:00:00Z",
        valid_until="2030-01-05T00:00:00Z",
        summary="An invented checkpoint note held for the conformance run.",
    ),
)

# References no conforming adapter holds. The first is an ordinary name that is
# simply absent. The rest are the forms a caller reaches with when it is trying
# to address something the adapter was never given: a climb upward, a path from
# the root, a lettered volume and a share host. Each must be refused as not
# held, and the refusal must carry none of it onward.
CONFORMANCE_ABSENT_REFERENCES: tuple[tuple[str, str], ...] = (
    ("conformance-absent-note", "v1"),
    (_STOP + _STOP + _SEPARATOR + "conformance-lineage-note", "v1"),
    (_SEPARATOR + "held" + _SEPARATOR + "conformance-lineage-note", "v1"),
    ("c" + _MARK + _SEPARATOR + "held", "v1"),
    (_ESCAPE + _ESCAPE + "host" + _ESCAPE + "held", "v1"),
    ("conformance-lineage-note", _STOP + _STOP + _SEPARATOR + "v1"),
)

CONFORMANCE_FACTS = FrozenCaseFacts(
    case_id="conformance-case",
    case_version="v1",
    case_digest="blake2b-256:19dd459cff22b093302615f57981b466ca3cdf941f8f528a0cad482f3c5e64c4",
    context_id="conformance-context",
    context_version="v1",
    context_digest="blake2b-256:90e0ed97e76e1bc026a3298b6bbefadcc00b69dae6599c1b4520b42dc91c9de0",
    logical_run_time="2026-03-01T00:00:00Z",
    cutoff_time="2026-02-28T23:59:59Z",
    timezone="UTC",
    facts=(
        FrozenFact(
            subject="input",
            fact_id="conformance-input-fact",
            version="v1",
            content_digest="blake2b-256:46cd6ebc1b15ac17fca6b819df1019f5b86344e1e13d817b855549bfa8b34871",
            row_count=5,
            bindings=(
                FactBinding(
                    SCHEMA_BINDING,
                    "conformance-schema",
                    "v1",
                    "blake2b-256:bd5aded8555e8990e92c18abbaf7cb99c09c2d217bb674e740be8b965472bd42",
                ),
                FactBinding(
                    GRAIN_BINDING,
                    "conformance-grain",
                    "v1",
                    "blake2b-256:5b0dfcb7250a715c0a0b922607cab357fc328b2e1f3104b92e369adad57f0dce",
                ),
                FactBinding(
                    CANONICALISATION_BINDING,
                    "conformance-canonicalisation",
                    "v1",
                    "blake2b-256:d44bfd1f47d87d95dea490a35bb340105be10c4d774793342a741eae0d5f7633",
                ),
            ),
        ),
    ),
)

# A second case, so the suite can watch what a runner does with facts it holds
# nothing for. Either answer is conforming: declared outputs, or a refusal.
CONFORMANCE_FOREIGN_FACTS = replace(
    CONFORMANCE_FACTS,
    case_id="conformance-other-case",
    case_digest="blake2b-256:621111592dc9422b1cc0a62e101a81fa00113410f2248e6d514fe955563e911e",
)

CONFORMANCE_CANDIDATE = CandidateDeclaration(
    candidate_id="conformance-candidate",
    version="v1",
    artifact_digest="blake2b-256:6d3d1688a131329f2720841382bc9fd5c853a5049eed7988b4067275c49f5f4e",
)

CONFORMANCE_OUTPUTS: tuple[ProducedOutput, ...] = (
    ProducedOutput(
        output_id="conformance-output",
        version="v1",
        content_digest="blake2b-256:6b086c3455ea3b59170744a85126feb315e86b5397273e8480773fd3f5ccbdf2",
        format_digest="blake2b-256:d0f89537691cbf880b81ea8c4bfa45e08c8963608b8966e88b36cc86d70e0236",
        row_count=5,
    ),
)

CONFORMANCE_DECLARED_OUTPUTS = ReplayDeclaration(
    case_id=CONFORMANCE_FACTS.case_id,
    case_version=CONFORMANCE_FACTS.case_version,
    case_digest=CONFORMANCE_FACTS.case_digest,
    outputs=CONFORMANCE_OUTPUTS,
)

# The fields of each crossing record this suite reads as plain text.
STORED_EVIDENCE_TEXT_FIELDS = (
    "evidence_id",
    "version",
    "declared_digest",
    "recorded_at",
    "valid_until",
    "summary",
)
CANDIDATE_TEXT_FIELDS = ("candidate_id", "version", "artifact_digest")
PRODUCED_OUTPUT_TEXT_FIELDS = ("output_id", "version", "content_digest", "format_digest")


class ConformanceReason(str, Enum):
    """The closed set of reasons an adapter contradicts what it claims."""

    DECLARATION_MISSING = "declaration-missing"
    DECLARATION_MALFORMED = "declaration-malformed"
    CONTRACT_VERSION_UNKNOWN = "contract-version-unknown"
    CAPABILITY_UNKNOWN = "capability-unknown"
    CAPABILITY_CONFLICTING = "capability-conflicting"
    CAPABILITY_NOT_OBSERVED = "capability-not-observed"
    ASSURANCE_UNKNOWN = "assurance-unknown"
    ASSURANCE_UNSUPPORTED = "assurance-unsupported"
    VALUE_MALFORMED = "value-malformed"
    MACHINE_ROUTE_CARRIED = "machine-route-carried"
    CREDENTIAL_CARRIED = "credential-carried"
    CONTRACT_NOT_HONOURED = "contract-not-honoured"
    ABSENCE_NOT_REFUSED = "absence-not-refused"


@dataclass(frozen=True)
class ConformanceFinding:
    """One contradiction, against one contract, in one method or field."""

    contract: str
    contract_version: str
    member: str
    reason: ConformanceReason
    detail: str


@dataclass(frozen=True)
class ConformanceReport:
    """Every contradiction the suite found, and nothing else."""

    findings: tuple[ConformanceFinding, ...]

    @property
    def conformant(self) -> bool:
        return not self.findings


def _finding(contract: str, member: str, reason: ConformanceReason, detail: str) -> ConformanceFinding:
    return ConformanceFinding(
        contract=contract,
        contract_version=PORT_CONTRACT_VERSION,
        member=member,
        reason=reason,
        detail=detail,
    )


def _text_findings(contract: str, member: str, value: object) -> list[ConformanceFinding]:
    """Read one crossing text value, naming what it carries and never repeating it."""
    if not isinstance(value, str) or not value or value.strip() != value or not value.isascii():
        return [
            _finding(
                contract,
                member,
                ConformanceReason.VALUE_MALFORMED,
                "the contract declares plain bounded text here and the value is not that",
            )
        ]
    findings: list[ConformanceFinding] = []
    if shape_carried(CONTROL_CHARACTERS, value) is not None:
        findings.append(
            _finding(
                contract,
                member,
                ConformanceReason.VALUE_MALFORMED,
                "the value carries a character below the printable range",
            )
        )
    route = shape_carried(MACHINE_ROUTES, value)
    if route is not None:
        findings.append(
            _finding(
                contract,
                member,
                ConformanceReason.MACHINE_ROUTE_CARRIED,
                f"the value carries a {route}, and a location stays in the environment",
            )
        )
    credential = shape_carried(CREDENTIALS, value)
    if credential is not None:
        findings.append(
            _finding(
                contract,
                member,
                ConformanceReason.CREDENTIAL_CARRIED,
                f"the value carries a {credential}, and a credential stays in the environment",
            )
        )
    return findings


def _count_findings(contract: str, member: str, value: object) -> list[ConformanceFinding]:
    """Read one crossing count value."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return [
            _finding(
                contract,
                member,
                ConformanceReason.VALUE_MALFORMED,
                "the contract declares a count of rows here and the value is not one",
            )
        ]
    return []


def _record_findings(contract: str, member: str, record: object, fields: tuple[str, ...]) -> list[ConformanceFinding]:
    findings: list[ConformanceFinding] = []
    for field in fields:
        findings.extend(_text_findings(contract, f"{member}.{field}", getattr(record, field, None)))
    return findings


def _refusal_findings(contract: str, member: str, refusal: BaseException) -> list[ConformanceFinding]:
    """Read the words of one refusal, which cross the port like any other value."""
    words = str(refusal)
    findings: list[ConformanceFinding] = []
    route = shape_carried(MACHINE_ROUTES, words)
    if route is not None:
        findings.append(
            _finding(
                contract,
                member,
                ConformanceReason.MACHINE_ROUTE_CARRIED,
                f"the refusal names a {route}, and a refusal carries no location onward",
            )
        )
    credential = shape_carried(CREDENTIALS, words)
    if credential is not None:
        findings.append(
            _finding(
                contract,
                member,
                ConformanceReason.CREDENTIAL_CARRIED,
                f"the refusal names a {credential}, and a refusal carries no credential onward",
            )
        )
    return findings


def _held_read_findings(
    repository: EvidenceRepositoryPort, record: StoredEvidence
) -> tuple[list[ConformanceFinding], bool]:
    """Read one record the adapter was built over, and say whether it answered."""
    contract, member = EVIDENCE_REPOSITORY_CONTRACT, "read_evidence"
    try:
        answer = repository.read_evidence(record.evidence_id, record.version)
    except EvidenceNotHeld as refusal:
        findings = _refusal_findings(contract, member, refusal)
        findings.append(
            _finding(
                contract,
                member,
                ConformanceReason.CONTRACT_NOT_HONOURED,
                "the repository does not hold the conformance material it was built over",
            )
        )
        return findings, False
    except PortRefusal as refusal:
        findings = _refusal_findings(contract, member, refusal)
        findings.append(
            _finding(
                contract,
                member,
                ConformanceReason.CONTRACT_NOT_HONOURED,
                "the repository refused the conformance material it was built over",
            )
        )
        return findings, False
    except Exception:
        return [
            _finding(
                contract,
                member,
                ConformanceReason.CONTRACT_NOT_HONOURED,
                "the repository raised an error that is not a refusal this contract declares",
            )
        ], False
    if not isinstance(answer, StoredEvidence):
        return [
            _finding(
                contract,
                member,
                ConformanceReason.CONTRACT_NOT_HONOURED,
                "the repository answered with something that is not a stored evidence record",
            )
        ], False
    findings = []
    if answer.evidence_id != record.evidence_id or answer.version != record.version:
        findings.append(
            _finding(
                contract,
                member,
                ConformanceReason.CONTRACT_NOT_HONOURED,
                "the repository answered for a different evidence identity or version",
            )
        )
    if not isinstance(answer.content, bytes):
        findings.append(
            _finding(
                contract,
                f"{member}.content",
                ConformanceReason.VALUE_MALFORMED,
                "the contract declares the stored bytes here and the value is not bytes",
            )
        )
    findings.extend(_record_findings(contract, member, answer, STORED_EVIDENCE_TEXT_FIELDS))
    return findings, True


def _absent_read_findings(repository: EvidenceRepositoryPort) -> list[ConformanceFinding]:
    """Read what the adapter does with references no conforming adapter holds."""
    contract, member = EVIDENCE_REPOSITORY_CONTRACT, "read_evidence"
    findings: list[ConformanceFinding] = []
    for evidence_id, version in CONFORMANCE_ABSENT_REFERENCES:
        try:
            repository.read_evidence(evidence_id, version)
        except EvidenceNotHeld as refusal:
            findings.extend(_refusal_findings(contract, member, refusal))
        except PortRefusal as refusal:
            findings.extend(_refusal_findings(contract, member, refusal))
            findings.append(
                _finding(
                    contract,
                    member,
                    ConformanceReason.CONTRACT_NOT_HONOURED,
                    "a reference the repository does not hold is refused as not held and not otherwise",
                )
            )
        except Exception:
            findings.append(
                _finding(
                    contract,
                    member,
                    ConformanceReason.CONTRACT_NOT_HONOURED,
                    "the repository raised an error that is not a refusal this contract declares",
                )
            )
        else:
            findings.append(
                _finding(
                    contract,
                    member,
                    ConformanceReason.ABSENCE_NOT_REFUSED,
                    "the repository answered for a reference no conforming adapter holds",
                )
            )
    return findings


def _candidate_findings(runner: CandidateRunnerPort) -> list[ConformanceFinding]:
    contract, member = CANDIDATE_RUNNER_CONTRACT, "declare_candidate"
    try:
        declaration = runner.declare_candidate()
    except PortRefusal as refusal:
        findings = _refusal_findings(contract, member, refusal)
        findings.append(
            _finding(
                contract,
                member,
                ConformanceReason.CONTRACT_NOT_HONOURED,
                "the runner refused to declare the candidate artefact it produces outputs from",
            )
        )
        return findings
    except Exception:
        return [
            _finding(
                contract,
                member,
                ConformanceReason.CONTRACT_NOT_HONOURED,
                "the runner raised an error that is not a refusal this contract declares",
            )
        ]
    if not isinstance(declaration, CandidateDeclaration):
        return [
            _finding(
                contract,
                member,
                ConformanceReason.CONTRACT_NOT_HONOURED,
                "the runner declared something that is not a candidate declaration",
            )
        ]
    return _record_findings(contract, member, declaration, CANDIDATE_TEXT_FIELDS)


def _produced_findings(
    runner: CandidateRunnerPort, facts: FrozenCaseFacts, *, declared_for: bool
) -> tuple[list[ConformanceFinding], bool]:
    """Read what one runner produces, and say whether it replayed anything."""
    contract, member = CANDIDATE_RUNNER_CONTRACT, "produce_outputs"
    try:
        outputs = runner.produce_outputs(facts)
    except PortRefusal as refusal:
        findings = _refusal_findings(contract, member, refusal)
        if declared_for:
            findings.append(
                _finding(
                    contract,
                    member,
                    ConformanceReason.CONTRACT_NOT_HONOURED,
                    "the runner refused the conformance facts its declared outputs were built over",
                )
            )
        return findings, False
    except Exception:
        return [
            _finding(
                contract,
                member,
                ConformanceReason.CONTRACT_NOT_HONOURED,
                "the runner raised an error that is not a refusal this contract declares",
            )
        ], False
    if not isinstance(outputs, tuple):
        return [
            _finding(
                contract,
                member,
                ConformanceReason.CONTRACT_NOT_HONOURED,
                "the runner answered with something that is not a tuple of produced outputs",
            )
        ], False
    findings: list[ConformanceFinding] = []
    for index, output in enumerate(outputs):
        at = f"{member}.outputs[{index}]"
        if not isinstance(output, ProducedOutput):
            findings.append(
                _finding(
                    contract,
                    at,
                    ConformanceReason.CONTRACT_NOT_HONOURED,
                    "the runner answered with something that is not a produced output",
                )
            )
            continue
        findings.extend(_record_findings(contract, at, output, PRODUCED_OUTPUT_TEXT_FIELDS))
        findings.extend(_count_findings(contract, f"{at}.row_count", output.row_count))
    return findings, bool(outputs)


def _declaration_findings(surface: object, contract: str, observed: set[str]) -> list[ConformanceFinding]:
    """Read what an adapter claims against what its port showed."""
    declare = getattr(surface, "declare_adapter", None)
    if not callable(declare):
        return [
            _finding(
                contract,
                "declare_adapter",
                ConformanceReason.DECLARATION_MISSING,
                "an adapter says what it is, what it can do and what its answers are worth",
            )
        ]
    try:
        declaration = declare()
    except Exception:
        return [
            _finding(
                contract,
                "declare_adapter",
                ConformanceReason.DECLARATION_MISSING,
                "the adapter raised rather than saying what it is",
            )
        ]
    if not isinstance(declaration, AdapterDeclaration):
        return [
            _finding(
                contract,
                "declare_adapter",
                ConformanceReason.DECLARATION_MALFORMED,
                "an adapter says what it is through the declaration this package declares",
            )
        ]
    findings = _text_findings(contract, "declaration.adapter_id", declaration.adapter_id)
    findings.extend(_text_findings(contract, "declaration.version", declaration.version))
    if declaration.port_contract_version != PORT_CONTRACT_VERSION:
        findings.append(
            _finding(
                contract,
                "declaration.port_contract_version",
                ConformanceReason.CONTRACT_VERSION_UNKNOWN,
                "the adapter implements a port contract version these ports do not declare",
            )
        )
    findings.extend(_named_input_findings(contract, declaration))
    findings.extend(_capability_findings(contract, declaration, observed))
    findings.extend(_assurance_findings(contract, declaration))
    return findings


def _named_input_findings(contract: str, declaration: AdapterDeclaration) -> list[ConformanceFinding]:
    findings: list[ConformanceFinding] = []
    for _, field in ASSURANCE_INPUT_FIELDS:
        named = getattr(declaration, field)
        if not isinstance(named, tuple):
            findings.append(
                _finding(
                    contract,
                    f"declaration.{field}",
                    ConformanceReason.DECLARATION_MALFORMED,
                    "the declaration names its inputs as a closed run of identities",
                )
            )
            continue
        for index, identity in enumerate(named):
            findings.extend(_text_findings(contract, f"declaration.{field}[{index}]", identity))
    return findings


def _capability_findings(
    contract: str, declaration: AdapterDeclaration, observed: set[str]
) -> list[ConformanceFinding]:
    if not isinstance(declaration.capabilities, tuple):
        return [
            _finding(
                contract,
                "declaration.capabilities",
                ConformanceReason.DECLARATION_MALFORMED,
                "the declaration names its capabilities as a closed run of names",
            )
        ]
    findings: list[ConformanceFinding] = []
    for index, capability in enumerate(declaration.capabilities):
        if capability not in ADAPTER_CAPABILITIES:
            findings.append(
                _finding(
                    contract,
                    f"declaration.capabilities[{index}]",
                    ConformanceReason.CAPABILITY_UNKNOWN,
                    "the adapter claims a capability this package does not name",
                )
            )
    claimed = set(declaration.capabilities)
    if claimed.issuperset(HOLDING_CAPABILITIES):
        findings.append(
            _finding(
                contract,
                "declaration.capabilities",
                ConformanceReason.CAPABILITY_CONFLICTING,
                "an adapter answers from material held in one place and this one claims both",
            )
        )
    shown = set(observed)
    if isinstance(declaration.environment_certificates, tuple) and declaration.environment_certificates:
        shown.add(PRESENTS_A_CERTIFICATE)
    for capability in ADAPTER_CAPABILITIES:
        if capability in claimed and capability not in shown:
            findings.append(
                _finding(
                    contract,
                    "declaration.capabilities",
                    ConformanceReason.CAPABILITY_NOT_OBSERVED,
                    f"the adapter claims {capability} and the port showed none of it",
                )
            )
    return findings


def _assurance_findings(contract: str, declaration: AdapterDeclaration) -> list[ConformanceFinding]:
    if declaration.assurance not in ASSURANCE_LEVELS:
        return [
            _finding(
                contract,
                "declaration.assurance",
                ConformanceReason.ASSURANCE_UNKNOWN,
                "an adapter declares one of the three assurance levels this product uses",
            )
        ]
    findings: list[ConformanceFinding] = []
    for level, field in ASSURANCE_INPUT_FIELDS:
        named = getattr(declaration, field)
        if declaration.assurance == level and not (isinstance(named, tuple) and named):
            findings.append(
                _finding(
                    contract,
                    f"declaration.{field}",
                    ConformanceReason.ASSURANCE_UNSUPPORTED,
                    f"the adapter declares {level} assurance and names no input it rests on",
                )
            )
    return findings


def check_conformance(
    *,
    candidate_runner: CandidateRunnerPort | None = None,
    evidence_repository: EvidenceRepositoryPort | None = None,
) -> ConformanceReport:
    """Run the suite over one runner, one repository, or one of each.

    Build the adapter over the material this module carries, hand the surface
    in, and read the report. The suite changes nothing, keeps nothing and
    recomputes no digest: a declared digest is read for its form here and for
    its truth in the intake workflow.
    """
    if candidate_runner is None and evidence_repository is None:
        raise ValueError("a candidate runner or an evidence repository is required")
    findings: list[ConformanceFinding] = []
    if evidence_repository is not None:
        findings.extend(_repository_findings(evidence_repository))
    if candidate_runner is not None:
        findings.extend(_runner_findings(candidate_runner))
    return ConformanceReport(tuple(findings))


def _repository_findings(repository: EvidenceRepositoryPort) -> list[ConformanceFinding]:
    findings: list[ConformanceFinding] = []
    answered = False
    for record in CONFORMANCE_EVIDENCE:
        read, held = _held_read_findings(repository, record)
        findings.extend(read)
        answered = answered or held
    findings.extend(_absent_read_findings(repository))
    observed = {READS_HELD_EVIDENCE, *HOLDING_CAPABILITIES} if answered else set()
    findings.extend(_declaration_findings(repository, EVIDENCE_REPOSITORY_CONTRACT, observed))
    return findings


def _runner_findings(runner: CandidateRunnerPort) -> list[ConformanceFinding]:
    findings = _candidate_findings(runner)
    declared, replayed = _produced_findings(runner, CONFORMANCE_FACTS, declared_for=True)
    findings.extend(declared)
    foreign, _ = _produced_findings(runner, CONFORMANCE_FOREIGN_FACTS, declared_for=False)
    findings.extend(foreign)
    observed = {REPLAYS_DECLARED_OUTPUTS, *HOLDING_CAPABILITIES} if replayed else set()
    findings.extend(_declaration_findings(runner, CANDIDATE_RUNNER_CONTRACT, observed))
    return findings


__all__ = [
    "CANDIDATE_RUNNER_CONTRACT",
    "CANDIDATE_TEXT_FIELDS",
    "CONFORMANCE_ABSENT_REFERENCES",
    "CONFORMANCE_CANDIDATE",
    "CONFORMANCE_DECLARED_OUTPUTS",
    "CONFORMANCE_EVIDENCE",
    "CONFORMANCE_FACTS",
    "CONFORMANCE_FOREIGN_FACTS",
    "CONFORMANCE_OUTPUTS",
    "ConformanceFinding",
    "ConformanceReason",
    "ConformanceReport",
    "EVIDENCE_REPOSITORY_CONTRACT",
    "PRODUCED_OUTPUT_TEXT_FIELDS",
    "STORED_EVIDENCE_TEXT_FIELDS",
    "check_conformance",
]
