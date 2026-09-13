"""Read-only intake, environment port contracts and independently derived receipts."""
# evorthon-verifies: EVD-README-020
from __future__ import annotations

import ast
from dataclasses import fields, is_dataclass, replace
from pathlib import Path

import pytest

import test_domain_contracts as domain_fixture
from evorthon_data.verification.core.canonical import canonical_digest, case_digest, record_digest
from evorthon_data.verification.domain.contracts import (
    ContextIdentity,
    DatasetProvenance,
    DatasetRole,
    DiagnosticStrength,
    EvidenceProvenance,
    EvidenceReference,
    ReceiptSubject,
    VerificationMode,
)
from evorthon_data.verification.enforcement.validation import inspect_verification_record
from evorthon_data.verification.ports import contracts as port_contracts
from evorthon_data.verification.ports import (
    BINDING_KINDS,
    CandidateDeclaration,
    CandidateRunnerPort,
    EvidenceNotHeld,
    EvidenceRepositoryPort,
    PortRefusal,
    ProducedOutput,
    StoredEvidence,
)
from evorthon_data.verification.workflows import (
    INTAKE_RECEIPT_VERSION,
    IntakeRefusalReason,
    IntakeRefused,
    RECEIPT_SUBJECT_BY_ROLE,
    declared_evidence,
    inspect_intake,
    intake_case,
)


PORTS_DIRECTORY = Path(port_contracts.__file__).parent
FORBIDDEN_PORT_TERMS = ("legacy", "network", "capture", "connect", "fetch", "download", "upload")

RECORDED_AT = "2026-08-01T00:00:00Z"
VALID_UNTIL = "2026-12-31T23:59:59Z"
CANDIDATE = CandidateDeclaration("candidate-artifact", "v1", "sha256:candidate-artifact")


def evidence_content(evidence_id: str, version: str) -> bytes:
    """Return the stored bytes a test repository holds for one evidence reference."""
    return f"approved evidence bytes for {evidence_id} at {version}".encode("ascii")


def deep_replace(record, mapper):
    """Return the record with mapper applied to every nested record it holds."""
    mapped = mapper(record)
    if mapped is not None:
        return mapped
    if isinstance(record, tuple):
        return tuple(deep_replace(item, mapper) for item in record)
    if is_dataclass(record) and not isinstance(record, type):
        return replace(record, **{field.name: deep_replace(getattr(record, field.name), mapper) for field in fields(record)})
    return record


def with_stored_evidence_digests(record):
    """Return the record with every evidence digest set to the digest of its stored bytes."""

    def mapper(node):
        if isinstance(node, EvidenceReference):
            return replace(node, digest=canonical_digest(evidence_content(node.evidence_id, node.version)))
        return None

    return deep_replace(record, mapper)


def with_context(record, context: ContextIdentity):
    """Return the record with every declared context replaced by one context."""

    def mapper(node):
        return context if isinstance(node, ContextIdentity) else None

    return deep_replace(record, mapper)


def case_fixture(
    mode: VerificationMode = VerificationMode.MODERNISATION,
    strength: DiagnosticStrength = DiagnosticStrength.REPLAYABLE,
    provenance=None,
):
    """Return the shared contract fixture with evidence digests a repository can meet."""
    built = (
        domain_fixture.case(mode, strength)
        if provenance is None
        else domain_fixture.case(mode, strength, provenance)
    )
    return with_stored_evidence_digests(built)


def stored(
    reference: EvidenceReference,
    *,
    content: bytes | None = None,
    declared_digest: str | None = None,
    recorded_at: str = RECORDED_AT,
    valid_until: str = VALID_UNTIL,
    evidence_id: str | None = None,
    version: str | None = None,
) -> StoredEvidence:
    """Return one stored evidence record for a declared reference."""
    body = evidence_content(reference.evidence_id, reference.version) if content is None else content
    return StoredEvidence(
        evidence_id=reference.evidence_id if evidence_id is None else evidence_id,
        version=reference.version if version is None else version,
        content=body,
        declared_digest=canonical_digest(body) if declared_digest is None else declared_digest,
        recorded_at=recorded_at,
        valid_until=valid_until,
        summary=reference.summary,
    )


def answers_for(case) -> dict[tuple[str, str], StoredEvidence]:
    """Return one well-formed stored record for every reference the case declares."""
    return {(reference.evidence_id, reference.version): stored(reference) for reference in declared_evidence(case)}


class FakeEvidenceRepository:
    """A test-only evidence repository over a fixed set of answers."""

    def __init__(self, answers):
        self._answers = dict(answers)
        self.requested: list[tuple[str, str]] = []

    def read_evidence(self, evidence_id: str, version: str) -> StoredEvidence:
        self.requested.append((evidence_id, version))
        key = (evidence_id, version)
        if key not in self._answers:
            raise EvidenceNotHeld(f"no evidence record for {evidence_id} at {version}")
        return self._answers[key]


class ListingEvidenceRepository(FakeEvidenceRepository):
    """A second, independently written repository that keeps its answers in a list."""

    def __init__(self, answers):
        super().__init__({})
        self._records = [record for record in answers.values() if record is not None]

    def read_evidence(self, evidence_id: str, version: str) -> StoredEvidence:
        self.requested.append((evidence_id, version))
        for record in self._records:
            if record.evidence_id == evidence_id and record.version == version:
                return record
        raise EvidenceNotHeld(f"no evidence record for {evidence_id} at {version}")


class RefusingEvidenceRepository:
    """A test-only repository that refuses to answer through the port refusal type."""

    def read_evidence(self, evidence_id: str, version: str) -> StoredEvidence:
        raise PortRefusal(f"the store cannot answer for {evidence_id} at {version}")


class FakeCandidateRunner:
    """A test-only candidate runner that records the frozen facts it receives."""

    def __init__(self, declaration=CANDIDATE, outputs: tuple[ProducedOutput, ...] = ()):
        self._declaration = declaration
        self._outputs = outputs
        self.received: list[object] = []

    def declare_candidate(self):
        return self._declaration

    def produce_outputs(self, facts):
        self.received.append(facts)
        return self._outputs


class ReadOnlyCandidateRunner(FakeCandidateRunner):
    """A runner that fails the test if intake asks it to produce anything."""

    def produce_outputs(self, facts):
        raise AssertionError("intake must not ask a candidate to produce outputs")


class RefusingCandidateRunner(ReadOnlyCandidateRunner):
    """A runner that refuses to declare a candidate through the port refusal type."""

    def declare_candidate(self):
        raise PortRefusal("the environment offers no candidate artefact for this case")


def report_for(case, answers=None, runner=None):
    repository = FakeEvidenceRepository(answers_for(case) if answers is None else answers)
    return inspect_intake(
        case,
        evidence_repository=repository,
        candidate_runner=ReadOnlyCandidateRunner() if runner is None else runner,
    )


def accepted(case, answers=None, runner=None):
    report = report_for(case, answers, runner)
    assert report.refusals == ()
    assert report.accepted
    return report.require_accepted()


def refused(case, answers=None, runner=None):
    report = report_for(case, answers, runner)
    assert report.refusals
    assert not report.accepted
    with pytest.raises(IntakeRefused):
        report.require_accepted()
    return {refusal.reason for refusal in report.refusals}


def test_a_complete_case_intakes_and_derives_input_and_context_receipts():
    case = case_fixture()

    intake = accepted(case)

    assert intake.case.identifier == case.case_id
    assert intake.candidate.candidate_id == CANDIDATE.candidate_id
    assert intake.context == case.context
    assert {receipt.subject for receipt in intake.receipts} >= {ReceiptSubject.INPUT, ReceiptSubject.CONTEXT}
    assert len({receipt.receipt_id for receipt in intake.receipts}) == len(intake.receipts)
    for receipt in intake.receipts:
        assert receipt.version == INTAKE_RECEIPT_VERSION
        assert inspect_verification_record(receipt).valid
    assert {item.reference.evidence_id for item in intake.confirmed_evidence} == {
        reference.evidence_id for reference in declared_evidence(case)
    }


def test_receipt_digests_are_recomputed_from_the_canonical_identity_of_each_receipt():
    case = case_fixture()

    intake = accepted(case)

    assert intake.receipt_digests == tuple(record_digest(receipt) for receipt in intake.receipts)
    assert intake.intake_digest == canonical_digest(
        "\n".join((case_digest(case), *intake.receipt_digests)).encode("ascii")
    )
    assert intake.case.digest == case_digest(case)


def test_every_receipt_carries_the_digest_it_observed_as_the_identity_it_answers_for():
    """A receipt answers for what it read, so its two digests agree.

    Intake reads the declaration and not the rows, so what it observes is the
    declaration. The identity a receipt answers for carries that same digest,
    and a reader that finds the two apart is reading a receipt taken over an
    altered declaration. The declared content digest is the runner's claim
    about bytes and stays on the frozen dataset and the frozen facts.
    """
    case = case_fixture()

    intake = accepted(case)

    for receipt in intake.receipts:
        assert receipt.observed_digest == receipt.subject_identity.digest
    context_receipt = next(receipt for receipt in intake.receipts if receipt.subject is ReceiptSubject.CONTEXT)
    assert context_receipt.subject_identity.identifier == case.context.context_id
    assert context_receipt.subject_identity.version == case.context.version
    assert context_receipt.observed_digest == record_digest(case.context)
    assert context_receipt.observed_digest != case.context.digest
    input_dataset = next(dataset for dataset in case.frozen_datasets if dataset.role is DatasetRole.INPUT)
    input_receipt = next(
        receipt for receipt in intake.receipts if receipt.subject_identity.identifier == input_dataset.dataset_id
    )
    assert input_receipt.observed_digest == record_digest(input_dataset)
    assert input_receipt.observed_digest != input_dataset.content_digest
    carried = {fact.content_digest for fact in intake.candidate_facts.facts}
    assert input_dataset.content_digest in carried


def test_a_receipt_taken_over_an_altered_declaration_no_longer_answers_for_the_frozen_one():
    """Move one declared fact and the receipt over it observes a different digest."""
    case = case_fixture()
    altered = next(dataset for dataset in case.frozen_datasets if dataset.role is DatasetRole.INPUT)
    moved = replace(
        case,
        frozen_datasets=tuple(
            replace(dataset, row_count=dataset.row_count + 1) if dataset is altered else dataset
            for dataset in case.frozen_datasets
        ),
    )

    first = accepted(case)
    second = accepted(moved)

    taken = {receipt.receipt_id: receipt for receipt in first.receipts}
    for receipt in second.receipts:
        held = taken[receipt.receipt_id]
        if receipt.subject_identity.identifier != altered.dataset_id:
            assert receipt.observed_digest == held.observed_digest
            continue
        assert receipt.observed_digest != held.observed_digest
        assert receipt.observed_digest == receipt.subject_identity.digest


def test_repeat_intake_across_two_runs_and_two_repositories_yields_identical_receipts():
    case = case_fixture()
    answers = answers_for(case)

    first = inspect_intake(
        case,
        evidence_repository=FakeEvidenceRepository(answers),
        candidate_runner=ReadOnlyCandidateRunner(),
    ).require_accepted()
    second = inspect_intake(
        case,
        evidence_repository=FakeEvidenceRepository(answers),
        candidate_runner=ReadOnlyCandidateRunner(),
    ).require_accepted()
    third = inspect_intake(
        case,
        evidence_repository=ListingEvidenceRepository(answers),
        candidate_runner=ReadOnlyCandidateRunner(),
    ).require_accepted()

    assert first.receipts == second.receipts == third.receipts
    assert first.receipt_digests == second.receipt_digests == third.receipt_digests
    assert first.intake_digest == second.intake_digest == third.intake_digest
    assert first.candidate_facts == third.candidate_facts


def test_missing_evidence_is_refused_and_a_complete_repository_is_accepted():
    case = case_fixture()
    answers = answers_for(case)
    absent = dict(answers)
    absent.pop(next(iter(absent)))

    assert refused(case, absent) == {IntakeRefusalReason.EVIDENCE_MISSING}
    accepted(case, answers)


def test_a_repository_answering_with_nothing_is_a_refusal_and_never_an_empty_record():
    case = case_fixture()
    answers = dict(answers_for(case))
    answers[next(iter(answers))] = None

    assert refused(case, answers) == {IntakeRefusalReason.EVIDENCE_MISSING}


def test_a_repository_that_refuses_to_answer_fails_closed_rather_than_raising():
    case = case_fixture()

    report = inspect_intake(
        case,
        evidence_repository=RefusingEvidenceRepository(),
        candidate_runner=ReadOnlyCandidateRunner(),
    )

    assert {refusal.reason for refusal in report.refusals} == {IntakeRefusalReason.EVIDENCE_MISSING}
    assert len(report.refusals) == len(declared_evidence(case))
    assert report.intake is None
    with pytest.raises(IntakeRefused):
        report.require_accepted()
    accepted(case)


def test_a_runner_that_refuses_to_declare_a_candidate_fails_closed_rather_than_raising():
    case = case_fixture()

    report = report_for(case, runner=RefusingCandidateRunner())

    assert {refusal.reason for refusal in report.refusals} == {IntakeRefusalReason.CANDIDATE_INCONSISTENT}
    assert report.intake is None
    with pytest.raises(IntakeRefused):
        report.require_accepted()
    accepted(case)


def test_altered_evidence_bytes_are_refused_against_the_digest_the_case_approved():
    case = case_fixture()
    answers = dict(answers_for(case))
    key = next(iter(answers))
    reference = next(item for item in declared_evidence(case) if (item.evidence_id, item.version) == key)
    answers[key] = stored(reference, content=b"altered stored bytes")

    assert refused(case, answers) == {IntakeRefusalReason.EVIDENCE_ALTERED}
    accepted(case)


def test_a_repository_that_lies_about_a_digest_is_caught():
    case = case_fixture()
    answers = dict(answers_for(case))
    key = next(iter(answers))
    reference = next(item for item in declared_evidence(case) if (item.evidence_id, item.version) == key)
    answers[key] = stored(reference, declared_digest=reference.digest.replace("b", "c"))

    assert refused(case, answers) == {IntakeRefusalReason.EVIDENCE_INCONSISTENT}


def test_a_repository_that_lies_about_bytes_and_their_digest_together_is_still_caught():
    case = case_fixture()
    answers = dict(answers_for(case))
    key = next(iter(answers))
    reference = next(item for item in declared_evidence(case) if (item.evidence_id, item.version) == key)
    body = b"altered stored bytes"
    answers[key] = stored(reference, content=body, declared_digest=canonical_digest(body))

    assert refused(case, answers) == {IntakeRefusalReason.EVIDENCE_ALTERED}


@pytest.mark.parametrize(
    ("recorded_at", "valid_until"),
    [
        (RECORDED_AT, "2026-09-01T00:00:00Z"),
        ("2026-09-03T00:00:00Z", VALID_UNTIL),
    ],
)
def test_evidence_outside_the_declared_run_instant_is_refused_as_expired(recorded_at, valid_until):
    case = case_fixture()
    answers = dict(answers_for(case))
    key = next(iter(answers))
    reference = next(item for item in declared_evidence(case) if (item.evidence_id, item.version) == key)
    answers[key] = stored(reference, recorded_at=recorded_at, valid_until=valid_until)

    assert refused(case, answers) == {IntakeRefusalReason.EVIDENCE_EXPIRED}
    accepted(case)


@pytest.mark.parametrize(
    ("recorded_at", "valid_until"),
    [
        (VALID_UNTIL, RECORDED_AT),
        ("2026-08-01", VALID_UNTIL),
        (RECORDED_AT, "2026-12-31T23:59:59"),
    ],
)
def test_evidence_with_a_validity_that_contradicts_itself_is_refused(recorded_at, valid_until):
    case = case_fixture()
    answers = dict(answers_for(case))
    key = next(iter(answers))
    reference = next(item for item in declared_evidence(case) if (item.evidence_id, item.version) == key)
    answers[key] = stored(reference, recorded_at=recorded_at, valid_until=valid_until)

    assert refused(case, answers) == {IntakeRefusalReason.EVIDENCE_INCONSISTENT}


def test_evidence_answering_for_another_reference_is_refused():
    case = case_fixture()
    answers = dict(answers_for(case))
    key = next(iter(answers))
    reference = next(item for item in declared_evidence(case) if (item.evidence_id, item.version) == key)
    answers[key] = stored(reference, evidence_id="another-evidence-record")

    assert refused(case, answers) == {IntakeRefusalReason.EVIDENCE_INCONSISTENT}


def test_a_case_declaring_one_evidence_identifier_with_two_digests_is_refused():
    case = case_fixture()
    clauses = case.comparison_policy.clauses
    contradiction = replace(clauses[0].required_evidence[0], digest=canonical_digest(b"a second set of bytes"))
    contradicting = replace(clauses[0], required_evidence=(contradiction,))
    case = replace(case, comparison_policy=replace(case.comparison_policy, clauses=(contradicting, *clauses[1:])))

    assert refused(case) == {IntakeRefusalReason.EVIDENCE_INCONSISTENT}


def test_an_invalid_case_is_refused_through_the_enforcement_validator_alone():
    case = replace(case_fixture(), case_id="")

    report = report_for(case)

    assert {refusal.reason for refusal in report.refusals} == {IntakeRefusalReason.CASE_INVALID}
    assert any("invalid-case-identity" in refusal.detail for refusal in report.refusals)
    assert report.intake is None


def test_a_case_context_without_a_readable_run_instant_is_refused():
    base = case_fixture(strength=DiagnosticStrength.OUTPUT_ONLY)
    case = with_context(base, replace(base.context, logical_run_time="as soon as the batch lands"))

    report = report_for(case)

    assert {refusal.reason for refusal in report.refusals} == {IntakeRefusalReason.CASE_INVALID}
    assert any(refusal.subject.endswith("logical_run_time") for refusal in report.refusals)
    accepted(base)


def test_an_incomplete_candidate_declaration_is_refused():
    case = case_fixture()

    assert refused(case, runner=ReadOnlyCandidateRunner(replace(CANDIDATE, artifact_digest=""))) == {
        IntakeRefusalReason.CANDIDATE_INCONSISTENT
    }
    assert refused(case, runner=ReadOnlyCandidateRunner(declaration=None)) == {
        IntakeRefusalReason.CANDIDATE_INCONSISTENT
    }
    accepted(case)


def test_intake_case_fails_closed_with_the_closed_reasons_it_found():
    case = case_fixture()
    answers = dict(answers_for(case))
    answers.pop(next(iter(answers)))

    with pytest.raises(IntakeRefused) as refusal:
        intake_case(
            case,
            evidence_repository=FakeEvidenceRepository(answers),
            candidate_runner=ReadOnlyCandidateRunner(),
        )

    assert {item.reason for item in refusal.value.refusals} == {IntakeRefusalReason.EVIDENCE_MISSING}


def test_intake_is_read_only_and_the_runner_receives_frozen_case_facts():
    case = case_fixture()
    read_only = ReadOnlyCandidateRunner()

    intake = accepted(case, runner=read_only)

    assert read_only.received == []
    runner = FakeCandidateRunner()
    assert runner.produce_outputs(intake.candidate_facts) == ()
    facts = runner.received[0]
    assert facts.case_id == case.case_id
    assert facts.case_digest == case_digest(case)
    assert facts.logical_run_time == case.context.logical_run_time
    assert {fact.fact_id for fact in facts.facts} == {dataset.dataset_id for dataset in case.frozen_datasets}
    for fact in facts.facts:
        assert tuple(binding.binding_kind for binding in fact.bindings) == BINDING_KINDS
        assert all(binding.digest for binding in fact.bindings)


def test_the_candidate_never_receives_an_expected_output():
    case = case_fixture()

    facts = accepted(case).candidate_facts

    declared = {value for output in case.expected_outputs for value in (output.output_id, output.content_digest, output.format_digest)}
    observed = {fact.fact_id for fact in facts.facts} | {fact.content_digest for fact in facts.facts}
    observed |= {binding.binding_id for fact in facts.facts for binding in fact.bindings}
    assert declared.isdisjoint(observed)


def test_a_synthetic_case_with_complete_evidence_intakes_like_any_other():
    case = case_fixture(provenance=DatasetProvenance.SYNTHETIC)

    intake = accepted(case)

    assert case.evidence_provenance is EvidenceProvenance.SYNTHETIC
    assert {receipt.subject for receipt in intake.receipts} >= {ReceiptSubject.INPUT, ReceiptSubject.CONTEXT}


def test_every_intake_refusal_reason_is_an_integrity_reason():
    assert {reason.value for reason in IntakeRefusalReason} == {
        "case-invalid",
        "evidence-missing",
        "evidence-altered",
        "evidence-expired",
        "evidence-inconsistent",
        "candidate-inconsistent",
    }


def test_every_frozen_dataset_role_has_a_receipt_subject():
    assert set(RECEIPT_SUBJECT_BY_ROLE) == set(DatasetRole)
    assert set(RECEIPT_SUBJECT_BY_ROLE.values()) <= set(ReceiptSubject)


def public_methods(port) -> set[str]:
    return {name for name, member in vars(port).items() if not name.startswith("_") and callable(member)}


def test_ports_declare_only_the_read_surfaces_an_environment_implements():
    assert public_methods(CandidateRunnerPort) == {"declare_candidate", "produce_outputs"}
    assert public_methods(EvidenceRepositoryPort) == {"read_evidence"}
    assert isinstance(FakeCandidateRunner(), CandidateRunnerPort)
    assert isinstance(FakeEvidenceRepository({}), EvidenceRepositoryPort)


def test_port_surfaces_name_no_live_route_operation():
    for port in (CandidateRunnerPort, EvidenceRepositoryPort):
        for name in public_methods(port):
            surface = f"{name} {getattr(port, name).__doc__ or ''}".lower()
            assert [term for term in FORBIDDEN_PORT_TERMS if term in surface] == []
    for path in sorted(PORTS_DIRECTORY.glob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        assert [term for term in FORBIDDEN_PORT_TERMS if term in text] == []


def imported_targets(path: Path) -> set[str]:
    targets: set[str] = set()
    for statement in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(statement, ast.Import):
            targets.update(alias.name for alias in statement.names)
        elif isinstance(statement, ast.ImportFrom):
            module = statement.module or ""
            targets.add(f"evorthon_data.verification.ports.{module}".rstrip(".") if statement.level else module)
    return targets


def test_ports_import_nothing_of_the_product_outside_their_own_package():
    for path in sorted(PORTS_DIRECTORY.glob("*.py")):
        for target in imported_targets(path):
            assert not target.startswith("evorthon_data") or target.startswith("evorthon_data.verification.ports")


def test_no_adapter_is_shipped_inside_the_port_contracts():
    assert sorted(path.name for path in PORTS_DIRECTORY.glob("*.py")) == ["__init__.py", "contracts.py"]
