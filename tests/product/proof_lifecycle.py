"""The shared harness the executable proofs drive the delivery lifecycle through.

An executable proof turns one shipped example into a complete run of the one
supported application route. Two things are the same whatever the example is,
and both live here.

The first is the frozen material. Every proof holds its fixtures under one root
with a provenance record beside them. The record declares every file: what
produced it, under which licence, and where it came from. Material declared for
projection carries a deterministic seed or a named hand author; material
declared as withheld carries the reason its provenance cannot be resolved, is
never read as data, and reaches no projection. The declaration shape is the
product's own and the export gates a candidate on it, so a proof and a
projection read one owner. The reader here is the only way a proof opens a
fixture, so a file nobody declared, a file declared without its licence or its
source, and a file declared as withheld are all refused at the one place a
proof reads.

The second is the run. A proof lays one engagement out under a scratch
repository, is given the mechanisms this module owns, and drives every stage in
order. The scripted transport, the intake authorization, the co-worker session
and the set of fakes are declared here once and read by every proof that drives
the route, the shared end-to-end proof included, so no two proofs give the
route different mechanisms. Nothing here reaches a network, a clock, a model
provider, a tracker or a build tool: the Koine co-worker and the adviser answer
through that one scripted transport behind the egress gateway, and the tracker,
the generator and the campaign answer through the fake runners their own proofs
own.

Nothing in this module decides anything a product module owns. It reads
declarations, lays out documents, drives the route and reads back what each
stage reported.
"""
from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from evorthon_data import composition, lifecycle
from evorthon_data.engagement import (
    Actor,
    ActorKind,
    Engagement,
    EngagementMode,
    ImmutableReference,
    ReferenceKind,
    ReviewDisposition,
)
from evorthon_data.koine_session import (
    INTAKE_GENERATOR_ROUTE,
    INTAKE_REVIEW_ROUTE,
    KoineSession,
    ReviewProposal,
    artefact_sample_field,
    credential_findings,
)
from evorthon_data.security import (
    ModelCallPurpose,
    ModelDestination,
    ModelEgressAuthorization,
    ModelEgressGateway,
    ModelEgressMode,
)
from evorthon_data.public_boundary import (
    DECLARED,
    PROVENANCE_FORM,
    PROVENANCE_RECORD,
    WITHHELD,
    FixtureDeclaration,
    FixtureProvenance,
    scan_candidate,
)
from evorthon_data.synthetic.generator import generate
from evorthon_data.synthetic.request import read_request
from evorthon_data.verification.adapters import (
    CONFORMANCE_CANDIDATE,
    CONFORMANCE_DECLARED_OUTPUTS,
    CONFORMANCE_EVIDENCE,
    ReplayDeclaration,
    write_fixture_material,
)
from evorthon_data.verification.core.canonical import case_digest
from evorthon_data.verification.domain.contracts import DatasetProvenance
from evorthon_data.verification.enforcement.serialization import serialize_json, serialize_record
from evorthon_data.verification.ports.contracts import ProducedOutput
from evorthon_data.verification.workflows import (
    ADVISER_ROUTE,
    SUPPORTING_IDENTITIES_FIELD,
    AdviserHypothesis,
    AdviserReply,
    AdviserRoute,
    ADVISER_REPLY_FORM,
)

import declaration_draft_support as draft_support  # noqa: E402
import test_autobuild_route as campaign_fixture  # noqa: E402
import test_ergasterion_route as generation_fixture  # noqa: E402
import test_koine_session as koine_fixture  # noqa: E402
import test_pinax_projection as tracker_fixture  # noqa: E402

ROOT = Path(__file__).parents[2]
PROOF_FIXTURES = ROOT / "tests" / "fixtures" / "proofs"
# How the repository names that tree, so a refusal never carries a machine path.
PROOF_TREE = PROOF_FIXTURES.relative_to(ROOT).as_posix()

# The policy document a candidate scan reads its forbidden tokens from, and the
# private list those tokens are declared in.
LEAKAGE_POLICY = "PUBLIC-LEAKAGE-POLICY.json"
PRIVATE_TOKENS = ROOT / "release" / "private-token-hashes.txt"
TOKEN_LENGTH = 64

# The fixed moment the scripted transport answers at, so no run reads a clock.
NOW = datetime(2026, 9, 2, 12, tzinfo=timezone.utc)
# The destination the fake routes name. Nothing is sent to it.
DESTINATION = ModelDestination(
    "provider-neutral", "https://model.example.test/v1/respond", "reviewable-model"
)
# The records root every proof lays its engagement out under.
RECORDS_ROOT = "work"


# --- the frozen material and what may be read of it ----------------------------


class ProofFixtures(FixtureProvenance):
    """One proof's frozen material, opened only where its provenance is declared.

    The declaration shape, and the findings a root's record produces against
    the material it holds, are the product's own, so a proof and the export
    read one owner. What a proof adds is the reading itself: every read goes
    through this reader and every read is remembered, so a proof can be held to
    what it actually opened. A file the record does not declare, a declaration
    that does not carry what its kind requires, and a file declared as withheld
    are each refused here rather than read.
    """

    def __init__(self, name: str, root: Path | None = None) -> None:
        super().__init__(
            PROOF_FIXTURES / name if root is None else Path(root),
            named=f"{PROOF_TREE}/{name}",
        )
        self.name = name
        self.reads: list[str] = []

    def path(self, name: str) -> Path:
        """The place of one declared, projected file, refusing any other."""
        declaration = self.declarations.get(name)
        if declaration is None:
            raise AssertionError(f"a proof reads no undeclared fixture: {name}")
        if not declaration.projected:
            raise AssertionError(f"a proof reads no withheld fixture as data: {name}")
        if declaration.missing():
            raise AssertionError(f"a proof reads no under-declared fixture: {name}")
        self.reads.append(name)
        return self.root / name

    def read(self, name: str) -> dict:
        """Read one declared document."""
        return json.loads(self.text(name))

    def text(self, name: str) -> str:
        """Read one declared file as the text it holds."""
        return self.path(name).read_text(encoding="ascii")

    def dataset(self, name: str):
        """Generate one frozen dataset from a declared constraint document.

        The seed and the generator version are the ones the provenance record
        declares for that document, so the dataset a proof freezes is the one
        the record says it is.
        """
        declaration = self.declarations[name].fields
        request = read_request(self.path(name).read_text(encoding="ascii"))
        return generate(
            request.schema,
            request.grain,
            request.keys,
            request.constraints,
            seed=declaration["seed"],
            generator_version=declaration["generator_version"],
        )

    def copy_projected(self, destination: Path, *, withhold: bool = True) -> Path:
        """Write the tree a projection takes, for a candidate scan to read.

        The policy the scan reads is written from the private token list, so
        the copy is scanned exactly as a public candidate is. Where a caller
        asks for the withheld material too, it is copied in as it stands, which
        is how the scan is shown reporting it.
        """
        destination.mkdir(parents=True, exist_ok=True)
        hashes = (
            [
                line.strip()
                for line in PRIVATE_TOKENS.read_text(encoding="utf-8").splitlines()
                if len(line.strip()) == TOKEN_LENGTH
            ]
            if PRIVATE_TOKENS.is_file()
            else []
        )
        (destination / LEAKAGE_POLICY).write_text(
            json.dumps({"forbidden_token_hashes": hashes}), encoding="utf-8"
        )
        taken = self.projected() if withhold else self.held()
        for name in (PROVENANCE_RECORD, *taken):
            source = self.root / name
            if not source.is_file():
                continue
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
        return destination


# --- the fakes one proof run is given ------------------------------------------


class ScriptedTransport:
    """One fake behind the egress gateway: two intake rounds, two reviews, one adviser.

    There is no model provider behind it and no provider text is parsed: each
    route is answered with the typed object its own reader declares.
    """

    def __init__(self, rounds, reply) -> None:
        self.rounds = list(rounds)
        self.reply = reply
        self.calls = []

    @property
    def routes(self) -> list[str]:
        return [call.route for call in self.calls]

    def __call__(self, call):
        self.calls.append(call)
        if call.route == INTAKE_GENERATOR_ROUTE:
            return self.rounds.pop(0)(call)
        if call.route == INTAKE_REVIEW_ROUTE:
            return ReviewProposal(
                disposition=ReviewDisposition.APPROVED,
                findings=ImmutableReference(
                    kind=ReferenceKind.REVIEW_FINDINGS,
                    identifier=f"intake-findings-{len(self.calls)}",
                    version="v1",
                    digest=f"digest-intake-findings-{len(self.calls)}",
                ),
            )
        if call.route == ADVISER_ROUTE:
            return self.reply(call)
        raise AssertionError(f"the lifecycle sent an unexpected call: {call.route}")


def scripted_reply(hypothesis, assumptions, confidence):
    """Return the reply an adviser is scripted to give for one gated packet.

    The cause, the fix and the discriminating test are the declared text the
    proof's own fixture holds. The evidence the reply cites is read off the
    packet the call carried, so a reply cites only what it was given.
    """

    def reply(call) -> AdviserReply:
        supporting = tuple(call.fields[SUPPORTING_IDENTITIES_FIELD])
        return AdviserReply(
            form=ADVISER_REPLY_FORM,
            confidence=confidence,
            hypotheses=(
                AdviserHypothesis(
                    cause=hypothesis["cause"],
                    proposed_fix=hypothesis["proposed_fix"],
                    discriminating_test=hypothesis["discriminating_test"],
                    supporting_evidence_ids=supporting[:1],
                    contradicting_evidence_ids=(),
                ),
            ),
            assumptions=tuple(assumptions),
        )

    return reply


def adviser_route() -> AdviserRoute:
    return AdviserRoute(
        destination=DESTINATION,
        mode=ModelEgressMode.FAKE,
        data_class="bounded-fault-packet",
        retention_policy="environment-30-days",
        evidence_policy="authorization-receipt-only",
    )


def intake_authorization(engagement: str, session_id: str) -> ModelEgressAuthorization:
    """The scope an environment issues for one intake round of one engagement."""
    return ModelEgressAuthorization(
        authorization_id=f"{session_id}-authorization",
        engagement_id=engagement,
        case_id=session_id,
        purpose=ModelCallPurpose.GENERATOR,
        route=INTAKE_GENERATOR_ROUTE,
        destination=DESTINATION,
        permitted_fields=frozenset(
            {artefact_sample_field("confidential"), "use_case"}
        ),
        data_class="synthetic-delivery-record",
        retention_policy="no-provider-retention",
        evidence_policy="record-call-identity-only",
        expected_authenticated_identity="model-egress-service",
        not_before=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=1),
    )


def coworker_session(
    gateway: ModelEgressGateway,
    engagement: str,
    session_id: str,
    mode: EngagementMode = EngagementMode.MODERNISATION,
) -> KoineSession:
    """One cold-started co-worker session with the shipped intake artefacts admitted.

    The mode is the engagement's own, so a proof of a greenfield delivery runs
    its rounds in a session that holds the greenfield rules.
    """
    running = KoineSession.cold_start(
        session_id=session_id,
        engagement=Engagement.create(engagement, mode),
        authorities=koine_fixture.authorities(),
        generator=Actor(identity="intake-generator", kind=ActorKind.MODEL),
        reviewer=Actor(identity="intake-reviewer", kind=ActorKind.MODEL),
        routes=koine_fixture.routes(),
        egress=gateway,
    )
    return koine_fixture.admit_all(running)


class ProofFakes:
    """Every fake one proof run is given, and what each one was asked."""

    def __init__(
        self,
        engagement: str,
        session_id: str,
        reply,
        generator=None,
        mode: EngagementMode = EngagementMode.MODERNISATION,
    ) -> None:
        self.engagement = engagement
        self.session_id = session_id
        self.mode = mode
        self.transport = ScriptedTransport(
            (koine_fixture.first_intake_round, koine_fixture.second_intake_round), reply
        )
        self.gateway = ModelEgressGateway(
            local_transport=self.transport, fake_transport=self.transport, clock=lambda: NOW
        )
        self.tracker = tracker_fixture.FakePinax()
        # A caller that wants the fake released tool to emit its own engagement's
        # estate gives one; otherwise the generation proof's own is used.
        self.generator = (
            generation_fixture.FakeErgasterionRunner() if generator is None else generator
        )
        self.campaign = campaign_fixture.FakeAutoBuildRunner()

    def mechanisms(self, **withheld) -> lifecycle.LifecycleMechanisms:
        declared = {
            "session": coworker_session(
                self.gateway, self.engagement, self.session_id, self.mode
            ),
            "egress": self.gateway,
            "pinax_runner": self.tracker,
            "ergasterion_runner": self.generator,
            "autobuild_runner": self.campaign,
            "capabilities": {
                **generation_fixture.CAPABILITIES,
                **campaign_fixture.CAPABILITIES,
            },
        }
        declared.update(withheld)
        return lifecycle.LifecycleMechanisms(**declared)


# --- the engagement one run is laid out under ----------------------------------


@dataclass(frozen=True)
class DeclaredCandidate:
    """One candidate an environment holds, and the material it was observed over.

    ``adapter`` is the logical identity the adapter configuration names,
    ``directory`` the held directory it reads, and ``observations`` the
    observed outputs and rows the candidate declared, one pair per published
    output. ``clauses`` carries what the candidate declared for the clauses
    that are answered over observed facts rather than over rows, one entry per
    clause in the form a material document holds it; a candidate whose case
    declares no such clause carries none.
    """

    adapter: str
    directory: str
    document: str
    observations: tuple
    clauses: tuple = ()


def declared_document(path: Path, document) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="ascii", newline="\n"
    )


def serialized_document(path: Path, record) -> None:
    """Write one domain record where a route reads it, in its own wire form."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_json(record), encoding="ascii", newline="\n")


def state_case(base: Path, engagement: str, case) -> None:
    """Write the approved case of one engagement where every route reads it.

    Writing it again states the case as the engagement now holds it, so a later
    version taken on the same record is read against the case it was taken on.
    """
    serialized_document(base / RECORDS_ROOT / engagement / "case.json", case)


def produced_from(output) -> ProducedOutput:
    return ProducedOutput(
        output_id=output.output_id,
        version=output.version,
        content_digest=output.content_digest,
        format_digest=output.format_digest,
        row_count=output.row_count,
    )


def written_rows(rows, written):
    """Write typed rows in the form a declared material document carries them."""
    return [{name: written(value) for name, value in row.items()} for row in rows]


def seed_engagement(
    base: Path,
    *,
    engagement: str,
    case,
    evidence,
    evidence_adapter: str,
    evidence_directory: str,
    expected,
    candidates,
    written,
) -> None:
    """Lay one whole engagement out under a scratch repository.

    The case document, the adapter configuration and one material document per
    candidate are written where the routes read them, and the material an
    environment holds is laid out by the shipped adapters' own writer.
    """
    held = base / RECORDS_ROOT
    (held / engagement).mkdir(parents=True, exist_ok=True)
    write_fixture_material(
        held / evidence_directory,
        evidence=(*CONFORMANCE_EVIDENCE, *evidence),
        candidate=CONFORMANCE_CANDIDATE,
        declared_outputs=(CONFORMANCE_DECLARED_OUTPUTS,),
    )
    state_case(base, engagement, case)
    adapters = {
        evidence_adapter: {"family": "fixture", "directory": evidence_directory},
    }
    for candidate in candidates:
        write_fixture_material(
            held / candidate.directory,
            candidate=CONFORMANCE_CANDIDATE,
            declared_outputs=(
                CONFORMANCE_DECLARED_OUTPUTS,
                ReplayDeclaration(
                    case_id=case.case_id,
                    case_version=case.version,
                    case_digest=case_digest(case),
                    outputs=tuple(
                        produced_from(observation.output)
                        for observation in candidate.observations
                    ),
                ),
            ),
        )
        adapters[candidate.adapter] = {
            "family": "fixture",
            "directory": candidate.directory,
        }
        declared_document(
            held / candidate.document,
            {
                "form": composition.RUN_MATERIAL_FORM,
                "expected": [
                    {"output": material.output.output_id, "rows": written_rows(material.rows, written)}
                    for material in expected
                ],
                "observed": [
                    {
                        "output": serialize_record(observation.output),
                        "rows": written_rows(observation.rows, written),
                    }
                    for observation in candidate.observations
                ],
                "clauses": [dict(entry) for entry in candidate.clauses],
            },
        )
    declared_document(
        held / engagement / "adapters.json",
        {"form": composition.ADAPTER_CONFIGURATION_FORM, "adapters": adapters},
    )


def written_records(base: Path) -> dict:
    """Every record one run wrote, by its repository-relative name."""
    held = base / RECORDS_ROOT
    return {
        path.relative_to(held).as_posix(): path.read_text(encoding="ascii")
        for path in sorted(held.rglob("*.md"))
    }


def stage_values(record, name: str) -> dict:
    """Read one stage's reported values back as a mapping."""
    return dict(record.stage(name).values)


# --- what every proof holds in the same shape ---------------------------------
#
# Two proofs drive the same route over two examples. What differs is the
# example: its names, its declared shape and the defects it injects. What does
# not differ lives here, so one reading of a shared check serves both and the
# two proofs cannot drift into two answers for the same question.

# The two documents every proof root holds under the same name.
ADVISER_REPLIES = "declared/adviser/scripted-replies.json"
HUMAN_SELECTION = "declared/remediation/human-selection.json"
# The manifest that gives every tracked path exactly one public disposition.
MANIFEST = ROOT / "release" / "public-manifest.toml"
# The file a gate proof adds to a copied root, and the four ways a root can
# fail its own record. Each one is driven red once by each proof.
STRAY_FIXTURE = "declared/expected/stray.json"
UNDECLARED_FILE = "an undeclared file"
NO_LICENCE = "a declaration with no licence"
NO_AUTHOR = "a declaration with no seed or author"
RESOLVED_WITHHELD = "a withheld file declared as resolved"
INJECTIONS = tuple(sorted((UNDECLARED_FILE, NO_LICENCE, NO_AUTHOR, RESOLVED_WITHHELD)))


def case_document(engagement_id: str) -> str:
    """Where one engagement holds the approved case its segments are verified against."""
    return f"{engagement_id}/case.json"


def advice_document(engagement_id: str) -> str:
    """Where one engagement holds what an adviser answered about a gated packet."""
    return f"{engagement_id}/advice.json"


def rationale_document(engagement_id: str) -> str:
    """Where one engagement holds the rationale a named human wrote."""
    return f"{engagement_id}/rationale.json"


def written_value(value):
    """Write one typed row value in the form a declared document carries it."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def case_verification(
    held: ProofFixtures,
    *,
    engagement_id: str,
    evidence_adapter: str,
    adapter_name,
    material_document,
    candidate: str,
    corrected: str,
    output_id: str,
    adviser_authority: str,
    decided_by: str,
) -> lifecycle.CaseVerification:
    """The documents and identities one segment's case is verified through.

    The caller says how its own proof names a candidate's adapter and its
    material document, and which authority a gated packet needs. What a named
    human decided about the advice is read from the one selection document
    every proof root holds.
    """
    selection = held.read(HUMAN_SELECTION)
    return lifecycle.CaseVerification(
        case_document=case_document(engagement_id),
        material_document=material_document(candidate),
        corrected_material_document=material_document(corrected),
        evidence_identity=evidence_adapter,
        candidate_identity=adapter_name(candidate),
        corrected_candidate_identity=adapter_name(corrected),
        output_id=output_id,
        advice_document=advice_document(engagement_id),
        rationale_document=rationale_document(engagement_id),
        adviser_route=adviser_route(),
        adviser_authority=adviser_authority,
        disposition=selection["disposition"],
        decided_by=decided_by,
        iteration=(
            f"{selection['iteration']['iteration_id']}:{output_id}:"
            f"{selection['iteration']['summary']}"
        ),
        remedy_summary=selection["remedy_summary"],
    )


@dataclass(frozen=True)
class ProofRun:
    """One whole traversal: where it ran, what it recorded and what it was given."""

    base: Path
    record: lifecycle.LifecycleRecord
    fakes: ProofFakes
    held: ProofFixtures

    def stage(self, name: str) -> dict:
        return stage_values(self.record, name)


def record_text(base: Path, engagement_id: str, use_case_id: str) -> str:
    """The bytes of the one record an engagement holds its use case in."""
    return composition.record_path(
        composition.records_root(base, RECORDS_ROOT), engagement_id, use_case_id
    ).read_text(encoding="ascii")


def recorded_acceptances(base: Path, engagement_id: str, use_case_id: str) -> tuple[dict, ...]:
    """Every acceptance one record holds, by the parts it is written in."""
    recorded = composition.load_use_case(base, RECORDS_ROOT, engagement_id, use_case_id)[2]
    read = (composition.read_entry(line) for line in recorded)
    return tuple(
        dict(zip(composition.ACCEPTANCE_PARTS, parts))
        for kind, parts in read
        if kind == composition.ACCEPTANCE_KIND
    )


# --- the checks every proof makes over its own frozen material -----------------


def confirm_declared_material(held: ProofFixtures) -> None:
    """Confirm a root holds what its record declares, and declares what it holds."""
    assert held.findings() == ()
    for name in held.projected():
        declaration = held.declarations[name].fields
        assert declaration["licence"] == "MIT"
        assert declaration["source"]
        assert declaration.get("seed") or declaration.get("author")


def confirm_printable_ascii(held: ProofFixtures) -> None:
    """Confirm every file a root ships is printable ASCII with one line ending."""
    for name in (PROVENANCE_RECORD, *held.held()):
        data = (held.root / name).read_bytes()
        assert b"\r" not in data, name
        assert data.decode("ascii")
        assert data.endswith(b"\n"), name


def confirm_seeded_dataset(held: ProofFixtures, name: str) -> None:
    """Confirm the dataset a case freezes is the one the provenance record names.

    The document is generated twice, through two readers of the same record, so
    the frozen dataset is the declared seed's own and not one run's accident.
    """
    declared = held.declarations[name].fields

    generated = held.dataset(name)
    again = ProofFixtures(held.name, root=held.root).dataset(name)

    assert generated.dataset.content_digest == again.dataset.content_digest
    assert generated.dataset.provenance is DatasetProvenance.SYNTHETIC
    assert generated.dataset.synthetic_provenance.seed == declared["seed"]
    assert generated.dataset.synthetic_provenance.generator_version == declared["generator_version"]
    assert generated.dataset.row_count == len(generated.rows)


def injected_finding(injected: str, *, gated: str, negative: str) -> str:
    """The finding one injected fault must produce, by the fault it injects."""
    return {
        UNDECLARED_FILE: f"undeclared file: {STRAY_FIXTURE}",
        NO_LICENCE: f"undeclared licence: {gated}",
        NO_AUTHOR: f"undeclared seed or author: {gated}",
        RESOLVED_WITHHELD: f"undeclared unresolved provenance: {negative}",
    }[injected]


def injected_gate(
    held: ProofFixtures, destination: Path, injected: str, *, gated: str, negative: str
) -> tuple[str, ...]:
    """Break a copy of one root's own record in one way and read the gate again.

    The copy carries the withheld material too, because one of the four faults
    is a fault about a file the projection leaves behind.
    """
    root = held.copy_projected(destination, withhold=False)
    record = json.loads((root / PROVENANCE_RECORD).read_text(encoding="ascii"))
    if injected == UNDECLARED_FILE:
        stray = root / STRAY_FIXTURE
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_text("{}\n", encoding="ascii")
    elif injected == NO_LICENCE:
        record["files"][gated].pop("licence")
    elif injected == NO_AUTHOR:
        record["files"][gated].pop("author")
    else:
        record["files"][negative]["provenance"] = "resolved"
    (root / PROVENANCE_RECORD).write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="ascii", newline="\n"
    )
    (root / LEAKAGE_POLICY).unlink()
    return ProofFixtures(held.name, root=root).findings()


def confirm_withheld_sample(held: ProofFixtures, destination: Path, *, negative: str) -> None:
    """Confirm the one sample a root withholds is reported and never read.

    The sample reaches no projection, so this reads material a projected tree
    does not hold and runs where that material is.
    """
    withheld = held.withheld()
    projected = held.copy_projected(destination / "projected")
    whole = held.copy_projected(destination / "whole", withhold=False)

    assert withheld == (negative,)
    assert not (projected / negative).exists()
    assert scan_candidate(projected) == []
    reported = scan_candidate(whole)
    assert reported
    assert {finding.split(": ", 1)[1] for finding in reported} == set(withheld)
    # It carries what a confidential-class artefact carries, and the product's
    # own credential scan says so.
    text = (held.root / negative).read_text(encoding="ascii")
    assert "classification: confidential" in text
    assert credential_findings(text)
    # No proof reads it as data, and the reader refuses to open it.
    with pytest.raises(AssertionError):
        held.path(negative)
    assert negative not in held.reads


def confirm_manifest_dispositions(held: ProofFixtures) -> None:
    """Confirm the exclusion is the disposition the manifest gives that path.

    The export gates a candidate on the declaration itself, and this is the
    second mechanism beside it: every file declared for projection is included
    and the one whose provenance is unresolved is excluded. The projection
    record is private, so this check runs where that record is.
    """
    from release.export_public import classify

    rules = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))["rule"]
    root = f"tests/fixtures/proofs/{held.name}"

    assert classify(f"{root}/{PROVENANCE_RECORD}", rules) == "included"
    for name in held.projected():
        assert classify(f"{root}/{name}", rules) == "included"
    for name in held.withheld():
        assert classify(f"{root}/{name}", rules) == "excluded"


def drafted_provenance(artefact: str, position: str):
    """Where a drafted declaration's facts were read, in one engagement's words."""
    return draft_support.FactProvenance(
        locator=draft_support.FactLocator(
            artefact=draft_support.reference(draft_support.ReferenceKind.INTAKE_ARTEFACT, artefact),
            position=position,
        ),
        extracted_by=draft_support.model(),
        status=draft_support.FactStatus.EXTRACTED,
    )


def taken_beside(
    base: Path, *, engagement_id: str, use_case_id: str, taken, reached
) -> tuple[dict, dict]:
    """Cut one more version on a record that holds one, and accept it there.

    A run opens one use case, so a later version is cut and accepted through
    the same two routes the run's own last two stages drive rather than through
    a second run. The readiness is read again first, so the cut carries the
    digest this record recomputes for it now. The caller supplies the words its
    own version is cut in and the case facts its own run reached.
    """
    route = {
        "repository": base,
        "root": RECORDS_ROOT,
        "engagement_id": engagement_id,
        "use_case_id": use_case_id,
    }
    read = dict(composition.read_use_case_readiness(**route, **reached).values)
    cut = composition.cut_use_case_version(
        **route,
        version_reference=taken.version_reference,
        covered_segments=taken.covered_segments,
        projection_reference=taken.projection_reference,
        readiness_digest=read["readiness digest"],
        scenario_case_versions=taken.scenario_case_versions,
        packages=taken.packages,
        evidence=taken.evidence,
        **reached,
    )
    accepted = composition.record_use_case_acceptance(
        **route,
        version_identity=taken.version_identity,
        decision_identity=taken.decision_identity,
        decided_by=taken.decided_by,
        rationale=taken.rationale,
        case_readings=taken.case_readings,
        **reached,
    )
    return dict(cut.values), dict(accepted.values)


__all__ = [
    "ADVISER_REPLIES",
    "DECLARED",
    "DeclaredCandidate",
    "FixtureDeclaration",
    "HUMAN_SELECTION",
    "INJECTIONS",
    "LEAKAGE_POLICY",
    "MANIFEST",
    "NOW",
    "NO_AUTHOR",
    "NO_LICENCE",
    "PROOF_FIXTURES",
    "PROVENANCE_FORM",
    "PROVENANCE_RECORD",
    "ProofFakes",
    "ProofFixtures",
    "ProofRun",
    "RECORDS_ROOT",
    "RESOLVED_WITHHELD",
    "STRAY_FIXTURE",
    "ScriptedTransport",
    "UNDECLARED_FILE",
    "WITHHELD",
    "advice_document",
    "adviser_route",
    "case_document",
    "case_verification",
    "confirm_declared_material",
    "confirm_manifest_dispositions",
    "confirm_printable_ascii",
    "confirm_seeded_dataset",
    "confirm_withheld_sample",
    "drafted_provenance",
    "coworker_session",
    "declared_document",
    "injected_finding",
    "injected_gate",
    "intake_authorization",
    "produced_from",
    "rationale_document",
    "record_text",
    "recorded_acceptances",
    "scripted_reply",
    "seed_engagement",
    "serialized_document",
    "stage_values",
    "taken_beside",
    "state_case",
    "written_records",
    "written_rows",
    "written_value",
]
