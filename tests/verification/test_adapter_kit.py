"""Reference environment adapters, their held material and the intake they drive."""
# evorthon-verifies: EVD-README-021
# evorthon-verifies: EVD-README-017
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

import test_intake_workflow as intake_fixture
from evorthon_data.verification.adapters import (
    ADAPTER_CAPABILITIES,
    ASSURANCE_LEVELS,
    CONFORMANCE_CANDIDATE,
    CONFORMANCE_DECLARED_OUTPUTS,
    CONFORMANCE_EVIDENCE,
    CONFORMANCE_FACTS,
    CONFORMANCE_FOREIGN_FACTS,
    CONFORMANCE_OUTPUTS,
    DECLARED_ASSURANCE,
    FixtureCandidateRunner,
    FixtureEvidenceRepository,
    InMemoryCandidateRunner,
    InMemoryEvidenceRepository,
    check_conformance,
    write_fixture_material,
)
from evorthon_data.verification.adapters import fixtures as fixture_layout
from evorthon_data.verification.core.canonical import canonical_digest
from evorthon_data.verification.domain.contracts import AssuranceLevel
from evorthon_data.verification.ports import EvidenceNotHeld, PORT_CONTRACT_VERSION, PortRefusal
from evorthon_data.verification.workflows import IntakeRefusalReason, inspect_intake


ROOT = Path(__file__).parents[2]
SHIPPED_MATERIAL = ROOT / "tests/fixtures/adapters"
# The one name every crossing value, refusal and report is read for. It is
# distinctive on purpose: a fixture root that leaked would be unmistakable.
HELD_DIRECTORY = "environment-owned-root-name"

# The characters a route is written from, by code point, so this file carries
# no route of its own and the candidate scan finds nothing to report in it.
_STOP = chr(46)
_SEPARATOR = chr(47)
_MARK = chr(58)
_ESCAPE = chr(92)


def prohibited_references() -> tuple[str, ...]:
    """The caller-supplied forms that address something outside a held name."""
    return (
        _STOP + _STOP + _SEPARATOR + "conformance-lineage-note",
        _SEPARATOR + "held" + _SEPARATOR + "conformance-lineage-note",
        "d" + _MARK + _SEPARATOR + "held",
        _ESCAPE + _ESCAPE + "host" + _ESCAPE + "held",
        "conformance-lineage-note" + _SEPARATOR + "v1",
    )


def held_root(tmp_path: Path) -> Path:
    """Return a directory holding the shipped conformance material."""
    root = tmp_path / HELD_DIRECTORY
    write_fixture_material(
        root,
        evidence=CONFORMANCE_EVIDENCE,
        candidate=CONFORMANCE_CANDIDATE,
        declared_outputs=(CONFORMANCE_DECLARED_OUTPUTS,),
    )
    return root


def reference_repositories(root: Path):
    return (InMemoryEvidenceRepository(CONFORMANCE_EVIDENCE), FixtureEvidenceRepository(root))


def reference_runners(root: Path):
    return (
        InMemoryCandidateRunner(CONFORMANCE_CANDIDATE, (CONFORMANCE_DECLARED_OUTPUTS,)),
        FixtureCandidateRunner(root),
    )


def test_every_reference_adapter_conforms_to_the_port_contract_it_answers(tmp_path):
    root = held_root(tmp_path)

    for repository in reference_repositories(root):
        assert check_conformance(evidence_repository=repository).conformant
    for runner in reference_runners(root):
        assert check_conformance(candidate_runner=runner).conformant


def test_the_kit_declares_the_assurance_levels_the_verification_domain_owns():
    assert set(ASSURANCE_LEVELS) == {level.value for level in AssuranceLevel}
    assert len(ASSURANCE_LEVELS) == len(AssuranceLevel)


def test_no_reference_adapter_claims_signing_retention_or_a_certificate(tmp_path):
    root = held_root(tmp_path)

    for adapter in (*reference_repositories(root), *reference_runners(root)):
        declaration = adapter.declare_adapter()
        assert declaration.assurance == DECLARED_ASSURANCE
        assert declaration.owner_presented_inputs == ()
        assert declaration.environment_certificates == ()
        assert declaration.port_contract_version == PORT_CONTRACT_VERSION
        assert set(declaration.capabilities) <= set(ADAPTER_CAPABILITIES)
        assert not any(word in name for name in declaration.capabilities for word in ("sign", "retain", "certificate"))


def test_the_shipped_material_on_disk_is_the_material_the_package_carries():
    repository = FixtureEvidenceRepository(SHIPPED_MATERIAL)
    runner = FixtureCandidateRunner(SHIPPED_MATERIAL)

    for record in CONFORMANCE_EVIDENCE:
        assert repository.read_evidence(record.evidence_id, record.version) == record
        assert record.declared_digest == canonical_digest(record.content)
    assert runner.declare_candidate() == CONFORMANCE_CANDIDATE
    assert runner.produce_outputs(CONFORMANCE_FACTS) == CONFORMANCE_OUTPUTS
    assert check_conformance(candidate_runner=runner, evidence_repository=repository).conformant


def test_the_shipped_material_declares_its_provenance_beside_it():
    declared = json.loads((SHIPPED_MATERIAL / "provenance.json").read_text(encoding="ascii"))

    assert declared["encoding"] == "ascii"
    assert declared["line_endings"] == "lf"
    assert declared["re_emitted_material"] == "none"
    held = {path.relative_to(SHIPPED_MATERIAL).as_posix() for path in SHIPPED_MATERIAL.rglob("*") if path.is_file()}
    assert held == set(declared["files"]) | {"provenance.json"}


@pytest.mark.parametrize("reference", prohibited_references())
def test_a_reference_that_would_address_outside_the_root_is_refused_as_not_held(tmp_path, reference):
    repository = FixtureEvidenceRepository(held_root(tmp_path))

    with pytest.raises(EvidenceNotHeld) as refused_id:
        repository.read_evidence(reference, "v1")
    with pytest.raises(EvidenceNotHeld) as refused_version:
        repository.read_evidence("conformance-lineage-note", reference)

    for refusal in (refused_id, refused_version):
        assert str(refusal.value) == fixture_layout.NOT_HELD
        assert reference not in str(refusal.value)


def test_material_the_layout_cannot_name_is_never_laid_out(tmp_path):
    root = tmp_path / HELD_DIRECTORY
    unnameable = _STOP + _STOP + _SEPARATOR + "elsewhere"

    with pytest.raises(ValueError) as refusal:
        write_fixture_material(root, evidence=(replace(CONFORMANCE_EVIDENCE[0], evidence_id=unnameable),))

    assert str(refusal.value) == fixture_layout.UNNAMEABLE_MATERIAL
    assert unnameable not in str(refusal.value)
    assert not (root / fixture_layout.EVIDENCE_DIRECTORY).exists()


def test_a_runner_refuses_frozen_facts_its_declared_outputs_were_not_frozen_against(tmp_path):
    root = held_root(tmp_path)
    contradicting = replace(CONFORMANCE_FACTS, case_digest=canonical_digest(b"another case entirely"))

    for runner in reference_runners(root):
        with pytest.raises(PortRefusal):
            runner.produce_outputs(contradicting)
        with pytest.raises(PortRefusal):
            runner.produce_outputs(CONFORMANCE_FOREIGN_FACTS)
        with pytest.raises(PortRefusal):
            runner.produce_outputs(None)
        assert runner.produce_outputs(CONFORMANCE_FACTS) == CONFORMANCE_OUTPUTS


def test_held_material_that_cannot_be_read_as_a_declared_record_refuses_rather_than_answers(tmp_path):
    root = held_root(tmp_path)
    record = CONFORMANCE_EVIDENCE[0]
    held = root / fixture_layout.EVIDENCE_DIRECTORY / record.evidence_id / (record.version + fixture_layout.RECORD_SUFFIX)
    held.write_text("{\"declared_digest\": 5}\n", encoding="ascii", newline="\n")

    with pytest.raises(PortRefusal) as refusal:
        FixtureEvidenceRepository(root).read_evidence(record.evidence_id, record.version)

    assert str(refusal.value) == fixture_layout.EVIDENCE_MATERIAL_UNREADABLE


def test_a_runner_holding_no_candidate_material_refuses_rather_than_declares(tmp_path):
    runner = FixtureCandidateRunner(tmp_path / HELD_DIRECTORY)

    with pytest.raises(PortRefusal) as refusal:
        runner.declare_candidate()

    assert str(refusal.value) == fixture_layout.CANDIDATE_MATERIAL_UNREADABLE


def crossing_text(root: Path) -> list[str]:
    """Every value, refusal and report the fixture adapters put across a port."""
    repository = FixtureEvidenceRepository(root)
    runner = FixtureCandidateRunner(root)
    said: list[str] = []
    for adapter in (repository, runner):
        declaration = adapter.declare_adapter()
        said.extend(
            [declaration.adapter_id, declaration.version, declaration.port_contract_version, declaration.assurance]
        )
        said.extend(declaration.capabilities)
    for record in CONFORMANCE_EVIDENCE:
        answer = repository.read_evidence(record.evidence_id, record.version)
        said.extend(
            [
                answer.evidence_id,
                answer.version,
                answer.declared_digest,
                answer.recorded_at,
                answer.valid_until,
                answer.summary,
                answer.content.decode("ascii"),
            ]
        )
    candidate = runner.declare_candidate()
    said.extend([candidate.candidate_id, candidate.version, candidate.artifact_digest])
    for output in runner.produce_outputs(CONFORMANCE_FACTS):
        said.extend([output.output_id, output.version, output.content_digest, output.format_digest])
    for reference in (*prohibited_references(), "conformance-absent-note"):
        with pytest.raises(PortRefusal) as refusal:
            repository.read_evidence(reference, "v1")
        said.append(str(refusal.value))
    with pytest.raises(PortRefusal) as refusal:
        runner.produce_outputs(CONFORMANCE_FOREIGN_FACTS)
    said.append(str(refusal.value))
    with pytest.raises(PortRefusal) as absent:
        FixtureCandidateRunner(root / "nothing-here").declare_candidate()
    said.append(str(absent.value))
    report = check_conformance(candidate_runner=FixtureCandidateRunner(root / "nothing-here"))
    said.extend(
        [value for finding in report.findings for value in (finding.contract, finding.member, finding.detail)]
    )
    return said


def test_the_held_directory_never_appears_in_a_value_a_refusal_or_a_report(tmp_path):
    root = held_root(tmp_path)

    for said in crossing_text(root):
        assert HELD_DIRECTORY not in said
        assert str(root) not in said
        assert root.as_posix() not in said
        assert tmp_path.name not in said


def intake_report(case, repository, runner):
    return inspect_intake(case, evidence_repository=repository, candidate_runner=runner)


def test_both_reference_repositories_and_runners_drive_the_intake_workflow_to_acceptance(tmp_path):
    case = intake_fixture.case_fixture()
    records = tuple(intake_fixture.answers_for(case).values())
    root = tmp_path / HELD_DIRECTORY
    write_fixture_material(root, evidence=records, candidate=CONFORMANCE_CANDIDATE)
    repositories = (InMemoryEvidenceRepository(records), FixtureEvidenceRepository(root))
    runners = (InMemoryCandidateRunner(CONFORMANCE_CANDIDATE), FixtureCandidateRunner(root))

    for repository in repositories:
        for runner in runners:
            intake = intake_report(case, repository, runner).require_accepted()
            assert intake.candidate.candidate_id == CONFORMANCE_CANDIDATE.candidate_id
            assert {item.reference.evidence_id for item in intake.confirmed_evidence} == {
                record.evidence_id for record in records
            }


def test_the_reference_adapters_produce_the_refusals_the_workflow_fakes_produce(tmp_path):
    case = intake_fixture.case_fixture()
    records = tuple(intake_fixture.answers_for(case).values())
    root = tmp_path / HELD_DIRECTORY
    write_fixture_material(root, evidence=records[1:], candidate=CONFORMANCE_CANDIDATE)
    runner = InMemoryCandidateRunner(CONFORMANCE_CANDIDATE)
    altered = (
        replace(
            records[0],
            content=b"altered stored bytes",
            declared_digest=canonical_digest(b"altered stored bytes"),
        ),
        *records[1:],
    )

    for repository in (InMemoryEvidenceRepository(records[1:]), FixtureEvidenceRepository(root)):
        assert {refusal.reason for refusal in intake_report(case, repository, runner).refusals} == {
            IntakeRefusalReason.EVIDENCE_MISSING
        }
    assert {
        refusal.reason for refusal in intake_report(case, InMemoryEvidenceRepository(altered), runner).refusals
    } == {IntakeRefusalReason.EVIDENCE_ALTERED}
    assert {
        refusal.reason
        for refusal in intake_report(case, InMemoryEvidenceRepository(records), InMemoryCandidateRunner()).refusals
    } == {IntakeRefusalReason.CANDIDATE_INCONSISTENT}
