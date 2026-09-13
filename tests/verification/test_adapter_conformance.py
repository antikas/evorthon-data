"""The conformance suite: what it refuses, what it names and what it leaves alone."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from evorthon_data.verification.adapters import (
    ADAPTER_CAPABILITIES,
    CONFORMANCE_CANDIDATE,
    CONFORMANCE_EVIDENCE,
    CONFORMANCE_FACTS,
    CONFORMANCE_OUTPUTS,
    AdapterDeclaration,
    ConformanceReason,
    DECLARED_ASSURANCE,
    ENVIRONMENT_CERTIFIED_ASSURANCE,
    HOLDS_MATERIAL_IN_MEMORY,
    HOLDS_MATERIAL_ON_A_FILE_SYSTEM,
    OWNER_PRESENTED_ASSURANCE,
    PRESENTS_A_CERTIFICATE,
    READS_HELD_EVIDENCE,
    REPLAYS_DECLARED_OUTPUTS,
    check_conformance,
)
from evorthon_data.verification.adapters.conformance import (
    CANDIDATE_RUNNER_CONTRACT,
    EVIDENCE_REPOSITORY_CONTRACT,
)
from evorthon_data.verification.ports import EvidenceNotHeld, PORT_CONTRACT_VERSION, PortRefusal


# The characters a route and a written assignment are made from, by code point,
# so this file carries no route and no credential of its own.
_STOP = chr(46)
_SEPARATOR = chr(47)
_MARK = chr(58)
_EQUALS = chr(61)

NOT_HELD_HERE = "this repository does not hold the requested reference"


def drive_path() -> str:
    """An invented route to a lettered volume on somebody's machine."""
    return "d" + _MARK + _SEPARATOR + "held" + _SEPARATOR + "evidence"


def traversal() -> str:
    """An invented reference that climbs out of wherever it starts."""
    return _STOP + _STOP + _SEPARATOR + "conformance-lineage-note"


def written_secret() -> str:
    """An invented secret written against its name. It opens nothing."""
    return "password" + _EQUALS + "not-a-real-one-either"


def repository_declaration(**changes) -> AdapterDeclaration:
    return replace(
        AdapterDeclaration(
            adapter_id="proof-evidence-repository",
            version="v1",
            capabilities=(READS_HELD_EVIDENCE, HOLDS_MATERIAL_IN_MEMORY),
            assurance=DECLARED_ASSURANCE,
        ),
        **changes,
    )


def runner_declaration(**changes) -> AdapterDeclaration:
    return replace(
        AdapterDeclaration(
            adapter_id="proof-candidate-runner",
            version="v1",
            capabilities=(REPLAYS_DECLARED_OUTPUTS, HOLDS_MATERIAL_IN_MEMORY),
            assurance=DECLARED_ASSURANCE,
        ),
        **changes,
    )


class ProofRepository:
    """One repository the proofs bend, one option at a time."""

    def __init__(self, *, declaration=None, records=CONFORMANCE_EVIDENCE, echoes=False, answers_anything=False):
        self._declaration = repository_declaration() if declaration is None else declaration
        self._records = tuple(records)
        self._echoes = echoes
        self._answers_anything = answers_anything

    def declare_adapter(self) -> AdapterDeclaration:
        return self._declaration

    def read_evidence(self, evidence_id: str, version: str):
        for record in self._records:
            if record.evidence_id == evidence_id and record.version == version:
                return record
        if self._answers_anything:
            return replace(CONFORMANCE_EVIDENCE[0], evidence_id=evidence_id, version=version)
        if self._echoes:
            raise EvidenceNotHeld(f"no record for {evidence_id} at {version}")
        raise EvidenceNotHeld(NOT_HELD_HERE)


class ProofRunner:
    """One runner the proofs bend, one option at a time."""

    def __init__(self, *, declaration=None, candidate=CONFORMANCE_CANDIDATE, outputs=CONFORMANCE_OUTPUTS, raises=None):
        self._declaration = runner_declaration() if declaration is None else declaration
        self._candidate = candidate
        self._outputs = outputs
        self._raises = raises

    def declare_adapter(self) -> AdapterDeclaration:
        return self._declaration

    def declare_candidate(self):
        return self._candidate

    def produce_outputs(self, facts):
        if self._raises is not None:
            raise self._raises
        if facts.case_id != CONFORMANCE_FACTS.case_id:
            raise PortRefusal("this runner holds no declared outputs for the case it received")
        return self._outputs


def reasons(report) -> set[ConformanceReason]:
    return {finding.reason for finding in report.findings}


def members(report, reason: ConformanceReason) -> set[str]:
    return {finding.member for finding in report.findings if finding.reason is reason}


def report_text(report) -> str:
    return " ".join(
        f"{finding.contract} {finding.contract_version} {finding.member} {finding.reason.value} {finding.detail}"
        for finding in report.findings
    )


def test_a_conforming_proof_adapter_keeps_the_suite_green():
    report = check_conformance(candidate_runner=ProofRunner(), evidence_repository=ProofRepository())

    assert report.conformant
    assert report.findings == ()


def test_a_location_in_a_stored_summary_turns_the_suite_red():
    held = (replace(CONFORMANCE_EVIDENCE[0], summary=f"held at {drive_path()}"), CONFORMANCE_EVIDENCE[1])

    report = check_conformance(evidence_repository=ProofRepository(records=held))

    assert ConformanceReason.MACHINE_ROUTE_CARRIED in reasons(report)
    assert "read_evidence.summary" in members(report, ConformanceReason.MACHINE_ROUTE_CARRIED)
    assert all(finding.contract == EVIDENCE_REPOSITORY_CONTRACT for finding in report.findings)
    assert all(finding.contract_version == PORT_CONTRACT_VERSION for finding in report.findings)
    assert drive_path() not in report_text(report)


def test_a_credential_in_a_declaration_field_turns_the_suite_red():
    declaration = repository_declaration(adapter_id=written_secret())

    report = check_conformance(evidence_repository=ProofRepository(declaration=declaration))

    assert ConformanceReason.CREDENTIAL_CARRIED in reasons(report)
    assert members(report, ConformanceReason.CREDENTIAL_CARRIED) == {"declaration.adapter_id"}
    assert written_secret() not in report_text(report)


def test_a_traversal_repeated_back_in_a_refusal_turns_the_suite_red():
    report = check_conformance(evidence_repository=ProofRepository(echoes=True))

    assert ConformanceReason.MACHINE_ROUTE_CARRIED in reasons(report)
    assert members(report, ConformanceReason.MACHINE_ROUTE_CARRIED) == {"read_evidence"}
    assert traversal() not in report_text(report)
    assert check_conformance(evidence_repository=ProofRepository()).conformant


def test_a_repository_that_answers_for_a_reference_it_cannot_hold_turns_the_suite_red():
    report = check_conformance(evidence_repository=ProofRepository(answers_anything=True))

    assert ConformanceReason.ABSENCE_NOT_REFUSED in reasons(report)
    assert members(report, ConformanceReason.ABSENCE_NOT_REFUSED) == {"read_evidence"}


@pytest.mark.parametrize(
    ("declaration", "surface"),
    [
        (repository_declaration(capabilities=(READS_HELD_EVIDENCE, REPLAYS_DECLARED_OUTPUTS)), "repository"),
        (repository_declaration(capabilities=(READS_HELD_EVIDENCE, PRESENTS_A_CERTIFICATE)), "repository"),
        (runner_declaration(capabilities=(REPLAYS_DECLARED_OUTPUTS, READS_HELD_EVIDENCE)), "runner"),
    ],
)
def test_a_capability_the_port_never_showed_turns_the_suite_red(declaration, surface):
    report = (
        check_conformance(evidence_repository=ProofRepository(declaration=declaration))
        if surface == "repository"
        else check_conformance(candidate_runner=ProofRunner(declaration=declaration))
    )

    assert ConformanceReason.CAPABILITY_NOT_OBSERVED in reasons(report)
    assert members(report, ConformanceReason.CAPABILITY_NOT_OBSERVED) == {"declaration.capabilities"}


def test_a_runner_that_replays_nothing_cannot_claim_that_it_does():
    report = check_conformance(candidate_runner=ProofRunner(outputs=()))

    assert ConformanceReason.CAPABILITY_NOT_OBSERVED in reasons(report)
    assert check_conformance(candidate_runner=ProofRunner()).conformant


def test_holding_material_in_two_places_at_once_turns_the_suite_red():
    declaration = repository_declaration(
        capabilities=(READS_HELD_EVIDENCE, HOLDS_MATERIAL_IN_MEMORY, HOLDS_MATERIAL_ON_A_FILE_SYSTEM)
    )

    report = check_conformance(evidence_repository=ProofRepository(declaration=declaration))

    assert ConformanceReason.CAPABILITY_CONFLICTING in reasons(report)
    assert members(report, ConformanceReason.CAPABILITY_CONFLICTING) == {"declaration.capabilities"}


@pytest.mark.parametrize("capability", ["signs-material", "retains-material", "certifies-material"])
def test_a_capability_this_package_does_not_name_turns_the_suite_red(capability):
    declaration = repository_declaration(capabilities=(READS_HELD_EVIDENCE, HOLDS_MATERIAL_IN_MEMORY, capability))

    report = check_conformance(evidence_repository=ProofRepository(declaration=declaration))

    assert ConformanceReason.CAPABILITY_UNKNOWN in reasons(report)
    assert members(report, ConformanceReason.CAPABILITY_UNKNOWN) == {"declaration.capabilities[2]"}
    assert capability not in ADAPTER_CAPABILITIES
    assert capability not in report_text(report)


def test_a_port_contract_version_the_ports_do_not_declare_turns_the_suite_red():
    declaration = repository_declaration(port_contract_version=PORT_CONTRACT_VERSION + "-of-our-own")

    report = check_conformance(evidence_repository=ProofRepository(declaration=declaration))

    assert ConformanceReason.CONTRACT_VERSION_UNKNOWN in reasons(report)
    assert members(report, ConformanceReason.CONTRACT_VERSION_UNKNOWN) == {"declaration.port_contract_version"}


@pytest.mark.parametrize(
    ("assurance", "field", "named"),
    [
        (OWNER_PRESENTED_ASSURANCE, "owner_presented_inputs", "owner-presented-review-note"),
        (ENVIRONMENT_CERTIFIED_ASSURANCE, "environment_certificates", "environment-certificate-claim"),
    ],
)
def test_an_assurance_above_declared_with_no_input_to_name_turns_the_suite_red(assurance, field, named):
    unsupported = repository_declaration(assurance=assurance)
    supported = repository_declaration(assurance=assurance, **{field: (named,)})

    report = check_conformance(evidence_repository=ProofRepository(declaration=unsupported))

    assert ConformanceReason.ASSURANCE_UNSUPPORTED in reasons(report)
    assert members(report, ConformanceReason.ASSURANCE_UNSUPPORTED) == {f"declaration.{field}"}
    assert check_conformance(evidence_repository=ProofRepository(declaration=supported)).conformant


def test_an_assurance_this_product_does_not_use_turns_the_suite_red():
    declaration = repository_declaration(assurance="independently-audited")

    report = check_conformance(evidence_repository=ProofRepository(declaration=declaration))

    assert ConformanceReason.ASSURANCE_UNKNOWN in reasons(report)
    assert members(report, ConformanceReason.ASSURANCE_UNKNOWN) == {"declaration.assurance"}


def test_an_adapter_that_says_nothing_about_itself_turns_the_suite_red():
    class SilentRepository:
        def read_evidence(self, evidence_id: str, version: str):
            return ProofRepository().read_evidence(evidence_id, version)

    report = check_conformance(evidence_repository=SilentRepository())

    assert reasons(report) == {ConformanceReason.DECLARATION_MISSING}
    assert members(report, ConformanceReason.DECLARATION_MISSING) == {"declare_adapter"}


def test_a_runner_that_raises_something_other_than_a_refusal_turns_the_suite_red():
    report = check_conformance(candidate_runner=ProofRunner(raises=KeyError("a key it reached for")))

    assert ConformanceReason.CONTRACT_NOT_HONOURED in reasons(report)
    assert "produce_outputs" in members(report, ConformanceReason.CONTRACT_NOT_HONOURED)


def test_a_produced_output_of_the_wrong_shape_turns_the_suite_red():
    outputs = (replace(CONFORMANCE_OUTPUTS[0], row_count=-1),)

    report = check_conformance(candidate_runner=ProofRunner(outputs=outputs))

    assert ConformanceReason.VALUE_MALFORMED in reasons(report)
    assert members(report, ConformanceReason.VALUE_MALFORMED) == {"produce_outputs.outputs[0].row_count"}


def test_every_finding_names_a_port_contract_its_version_a_member_and_a_closed_reason():
    declaration = repository_declaration(
        adapter_id=written_secret(),
        version="",
        port_contract_version="another-contract-entirely",
        capabilities=(REPLAYS_DECLARED_OUTPUTS, "signs-material"),
        assurance=OWNER_PRESENTED_ASSURANCE,
    )
    held = (replace(CONFORMANCE_EVIDENCE[0], summary=f"held at {drive_path()}"), CONFORMANCE_EVIDENCE[1])

    report = check_conformance(evidence_repository=ProofRepository(declaration=declaration, records=held))

    assert not report.conformant
    for finding in report.findings:
        assert finding.contract in (CANDIDATE_RUNNER_CONTRACT, EVIDENCE_REPOSITORY_CONTRACT)
        assert finding.contract_version == PORT_CONTRACT_VERSION
        assert finding.member
        assert finding.reason in set(ConformanceReason)
        assert finding.detail
    assert {
        ConformanceReason.CREDENTIAL_CARRIED,
        ConformanceReason.VALUE_MALFORMED,
        ConformanceReason.CONTRACT_VERSION_UNKNOWN,
        ConformanceReason.CAPABILITY_UNKNOWN,
        ConformanceReason.CAPABILITY_NOT_OBSERVED,
        ConformanceReason.ASSURANCE_UNSUPPORTED,
        ConformanceReason.MACHINE_ROUTE_CARRIED,
    } <= reasons(report)


def test_the_suite_needs_a_surface_to_read():
    with pytest.raises(ValueError):
        check_conformance()


def test_a_fixture_adapter_written_outside_the_package_passes_the_suite(tmp_path):
    root = tmp_path / "another-environment"
    root.mkdir()
    for record in CONFORMANCE_EVIDENCE:
        (root / f"{record.evidence_id}@{record.version}.json").write_text(
            json.dumps(
                {
                    "content": record.content.decode("ascii"),
                    "declared_digest": record.declared_digest,
                    "recorded_at": record.recorded_at,
                    "summary": record.summary,
                    "valid_until": record.valid_until,
                }
            ),
            encoding="ascii",
            newline="\n",
        )
    (root / "candidate@v1.json").write_text(
        json.dumps(
            {
                "artifact_digest": CONFORMANCE_CANDIDATE.artifact_digest,
                "candidate_id": CONFORMANCE_CANDIDATE.candidate_id,
                "version": CONFORMANCE_CANDIDATE.version,
            }
        ),
        encoding="ascii",
        newline="\n",
    )

    class AnotherEnvironmentRepository:
        """An adapter written here, over a layout of its own, touching no package code."""

        def __init__(self, held: Path):
            self._held = held

        def declare_adapter(self) -> AdapterDeclaration:
            return AdapterDeclaration(
                adapter_id="another-environment-evidence-repository",
                version="v1",
                capabilities=(READS_HELD_EVIDENCE, HOLDS_MATERIAL_ON_A_FILE_SYSTEM),
                assurance=DECLARED_ASSURANCE,
            )

        def read_evidence(self, evidence_id: str, version: str):
            from evorthon_data.verification.ports import StoredEvidence

            for path in sorted(self._held.glob("*@*.json")):
                name, _, held_version = path.stem.partition("@")
                if name != evidence_id or held_version != version:
                    continue
                declared = json.loads(path.read_text(encoding="ascii"))
                return StoredEvidence(
                    evidence_id=name,
                    version=held_version,
                    content=declared["content"].encode("ascii"),
                    declared_digest=declared["declared_digest"],
                    recorded_at=declared["recorded_at"],
                    valid_until=declared["valid_until"],
                    summary=declared["summary"],
                )
            raise EvidenceNotHeld("this environment holds no record for the requested reference")

    class AnotherEnvironmentRunner:
        """A runner written here, replaying what the same directory declares."""

        def __init__(self, held: Path):
            self._held = held

        def declare_adapter(self) -> AdapterDeclaration:
            return AdapterDeclaration(
                adapter_id="another-environment-candidate-runner",
                version="v1",
                capabilities=(REPLAYS_DECLARED_OUTPUTS, HOLDS_MATERIAL_ON_A_FILE_SYSTEM),
                assurance=DECLARED_ASSURANCE,
            )

        def declare_candidate(self):
            from evorthon_data.verification.ports import CandidateDeclaration

            declared = json.loads((self._held / "candidate@v1.json").read_text(encoding="ascii"))
            return CandidateDeclaration(
                candidate_id=declared["candidate_id"],
                version=declared["version"],
                artifact_digest=declared["artifact_digest"],
            )

        def produce_outputs(self, facts):
            if facts.case_id != CONFORMANCE_FACTS.case_id or facts.case_digest != CONFORMANCE_FACTS.case_digest:
                raise PortRefusal("this environment declares no outputs for the case it received")
            return CONFORMANCE_OUTPUTS

    report = check_conformance(
        candidate_runner=AnotherEnvironmentRunner(root),
        evidence_repository=AnotherEnvironmentRepository(root),
    )

    assert report.conformant
