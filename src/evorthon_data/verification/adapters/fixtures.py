"""Reference adapters that answer from material held on a file system.

These two adapters read material an adopting environment lays out in a
directory it names when it builds them. They are how a team runs the product
against held material before any platform of theirs is wired to a port, and
they are the worked example an environment adapter is written from.

The directory is the environment's own configuration. It is named once, at
construction, and it never leaves this module: it appears in no value that
crosses a port, in no refusal and in no conformance report. That is the whole
reason the addressing below is what it is.

Addressing is by logical identity and version, never by a path a caller
supplies. A reference is a name and a version, both written from letters,
digits and the three joining marks, neither beginning with a stop and neither
carrying a climb upward. Anything else is not a name this layout can hold, so
it is refused as not held, and the refusal says only that. A reference that
still resolved outside the named directory after all of that would be refused
the same way, and the check stays in because the rule it protects is worth more
than the cost of reading it twice.

The layout is closed. Under the named directory, evidence sits in one directory
of its own, one directory per evidence name, and one pair of files per version:
the stored bytes, and the record the environment declares about them. A
candidate declaration sits in one file. Declared outputs sit in one directory
of their own, one directory per case name and one file per case version.
Nothing else in the named directory is read.

What this module does not do is as deliberate as what it does. It holds no
credential, signs nothing, retains nothing, expires nothing and certifies
nothing. It never writes to the material it reads. It recomputes no digest: the
record it reads carries the environment's own declared digest, and the intake
workflow is the one place that computes a digest over the bytes and compares.
"""
from __future__ import annotations

# evorthon-component: verification_adapters

import json
from collections.abc import Sequence
from pathlib import Path
from string import ascii_letters, digits

from evorthon_data.verification.adapters.declaration import (
    AdapterDeclaration,
    DECLARED_ASSURANCE,
    HOLDS_MATERIAL_ON_A_FILE_SYSTEM,
    READS_HELD_EVIDENCE,
    REPLAYS_DECLARED_OUTPUTS,
)
from evorthon_data.verification.adapters.material import (
    NOT_HELD,
    ReplayDeclaration,
    replayed_outputs,
)
from evorthon_data.verification.ports.contracts import (
    CandidateDeclaration,
    EvidenceNotHeld,
    FrozenCaseFacts,
    PortRefusal,
    PORT_CONTRACT_VERSION,
    ProducedOutput,
    StoredEvidence,
)


FIXTURE_EVIDENCE_ADAPTER_ID = "reference-fixture-evidence-repository"
FIXTURE_CANDIDATE_ADAPTER_ID = "reference-fixture-candidate-runner"
FIXTURE_ADAPTER_VERSION = "v1"

# The closed layout. These names are the whole of what this family reads.
EVIDENCE_DIRECTORY = "evidence"
DECLARED_OUTPUT_DIRECTORY = "declared-outputs"
CANDIDATE_FILE = "candidate.json"
CONTENT_SUFFIX = ".content"
RECORD_SUFFIX = ".record.json"
DECLARED_OUTPUT_SUFFIX = ".json"

# The characters a held name is written from. A name is one segment: it carries
# no separator, no mark and no climb upward, so no held name can address
# anything but the material this layout holds.
HELD_NAME_CHARACTERS = frozenset(ascii_letters + digits + "._-")
HELD_NAME_STOP = "."

EVIDENCE_MATERIAL_UNREADABLE = (
    "the repository holds material for the reference that cannot be read as a declared record"
)
CANDIDATE_MATERIAL_UNREADABLE = (
    "the runner holds no candidate declaration that can be read as a declared artefact"
)
DECLARED_OUTPUT_MATERIAL_UNREADABLE = (
    "the runner holds material for the case that cannot be read as declared outputs"
)
UNNAMEABLE_MATERIAL = "the material carries a name this layout cannot hold"


def held_name(value: object) -> bool:
    """Whether one identity or version is a name this layout can hold."""
    return (
        isinstance(value, str)
        and bool(value)
        and not value.startswith(HELD_NAME_STOP)
        and HELD_NAME_STOP * 2 not in value
        and set(value) <= HELD_NAME_CHARACTERS
    )


def _held_path(root: Path, layout: str, *names: str) -> Path | None:
    """Return where one held name sits under the root, or nothing at all.

    ``layout`` is one of this module's own closed layout names. Everything
    after it came from a caller, so every one of those is read as a held name
    first. Nothing is returned for a name this layout cannot hold or for a
    resolved location that would sit outside the root. The caller turns that
    into its own refusal, which is why no path is named here.
    """
    if not all(held_name(name) for name in names):
        return None
    resolved_root = Path(root).resolve()
    resolved = resolved_root.joinpath(layout, *names).resolve()
    if not resolved.is_relative_to(resolved_root):
        return None
    return resolved


def _read_declaration(path: Path) -> dict[str, object] | None:
    """Return one declared record read from the layout, or nothing at all."""
    try:
        declared = json.loads(path.read_text(encoding="ascii"))
    except (OSError, ValueError):
        return None
    return declared if isinstance(declared, dict) else None


def _declared_text(declared: dict[str, object], field: str) -> str | None:
    value = declared.get(field)
    return value if isinstance(value, str) else None


def _declared_output(declared: object) -> ProducedOutput | None:
    """Return one produced output read from the layout, or nothing at all."""
    if not isinstance(declared, dict):
        return None
    texts = [_declared_text(declared, field) for field in ("output_id", "version", "content_digest", "format_digest")]
    row_count = declared.get("row_count")
    if any(text is None for text in texts) or not isinstance(row_count, int) or isinstance(row_count, bool):
        return None
    output_id, version, content_digest, format_digest = texts
    return ProducedOutput(
        output_id=output_id,
        version=version,
        content_digest=content_digest,
        format_digest=format_digest,
        row_count=row_count,
    )


class FixtureEvidenceRepository:
    """An evidence repository over material held in a named directory."""

    def __init__(
        self,
        root: Path | str,
        *,
        adapter_id: str = FIXTURE_EVIDENCE_ADAPTER_ID,
        version: str = FIXTURE_ADAPTER_VERSION,
    ):
        self._root = Path(root)
        self._adapter_id = adapter_id
        self._version = version

    def declare_adapter(self) -> AdapterDeclaration:
        """Return what this adapter says about itself."""
        return AdapterDeclaration(
            adapter_id=self._adapter_id,
            version=self._version,
            port_contract_version=PORT_CONTRACT_VERSION,
            capabilities=(READS_HELD_EVIDENCE, HOLDS_MATERIAL_ON_A_FILE_SYSTEM),
            assurance=DECLARED_ASSURANCE,
        )

    def read_evidence(self, evidence_id: str, version: str) -> StoredEvidence:
        """Return the held record for one reference, or refuse as not held."""
        directory = _held_path(self._root, EVIDENCE_DIRECTORY, evidence_id)
        if directory is None or not held_name(version):
            raise EvidenceNotHeld(NOT_HELD)
        content_path = directory / (version + CONTENT_SUFFIX)
        record_path = directory / (version + RECORD_SUFFIX)
        if not content_path.is_file() or not record_path.is_file():
            raise EvidenceNotHeld(NOT_HELD)
        declared = _read_declaration(record_path)
        if declared is None:
            raise PortRefusal(EVIDENCE_MATERIAL_UNREADABLE)
        texts = [_declared_text(declared, field) for field in ("declared_digest", "recorded_at", "valid_until", "summary")]
        if any(text is None for text in texts):
            raise PortRefusal(EVIDENCE_MATERIAL_UNREADABLE)
        try:
            content = content_path.read_bytes()
        except OSError:
            raise PortRefusal(EVIDENCE_MATERIAL_UNREADABLE) from None
        declared_digest, recorded_at, valid_until, summary = texts
        return StoredEvidence(
            evidence_id=evidence_id,
            version=version,
            content=content,
            declared_digest=declared_digest,
            recorded_at=recorded_at,
            valid_until=valid_until,
            summary=summary,
        )


class FixtureCandidateRunner:
    """A candidate runner that replays declared outputs from a named directory."""

    def __init__(
        self,
        root: Path | str,
        *,
        adapter_id: str = FIXTURE_CANDIDATE_ADAPTER_ID,
        version: str = FIXTURE_ADAPTER_VERSION,
    ):
        self._root = Path(root)
        self._adapter_id = adapter_id
        self._version = version

    def declare_adapter(self) -> AdapterDeclaration:
        """Return what this adapter says about itself."""
        return AdapterDeclaration(
            adapter_id=self._adapter_id,
            version=self._version,
            port_contract_version=PORT_CONTRACT_VERSION,
            capabilities=(REPLAYS_DECLARED_OUTPUTS, HOLDS_MATERIAL_ON_A_FILE_SYSTEM),
            assurance=DECLARED_ASSURANCE,
        )

    def declare_candidate(self) -> CandidateDeclaration:
        """Return the candidate artefact this runner produces outputs from."""
        path = _held_path(self._root, CANDIDATE_FILE)
        declared = None if path is None else _read_declaration(path)
        if declared is None:
            raise PortRefusal(CANDIDATE_MATERIAL_UNREADABLE)
        texts = [_declared_text(declared, field) for field in ("candidate_id", "version", "artifact_digest")]
        if any(text is None for text in texts):
            raise PortRefusal(CANDIDATE_MATERIAL_UNREADABLE)
        candidate_id, version, artifact_digest = texts
        return CandidateDeclaration(candidate_id=candidate_id, version=version, artifact_digest=artifact_digest)

    def produce_outputs(self, facts: FrozenCaseFacts) -> tuple[ProducedOutput, ...]:
        """Return the declared outputs for the frozen facts, or refuse."""
        return replayed_outputs(self._declarations(facts), facts)

    def _declarations(self, facts: FrozenCaseFacts) -> tuple[ReplayDeclaration, ...]:
        """Return the held declaration for the case these facts name, if any.

        Only the case identity and version are read from the facts, so this
        reaches for nothing the approved case does not declare. The declared
        digest is compared by the one rule that owns the comparison.
        """
        if not isinstance(facts, FrozenCaseFacts):
            return ()
        directory = _held_path(self._root, DECLARED_OUTPUT_DIRECTORY, facts.case_id)
        if directory is None or not held_name(facts.case_version):
            return ()
        path = directory / (facts.case_version + DECLARED_OUTPUT_SUFFIX)
        if not path.is_file():
            return ()
        declared = _read_declaration(path)
        case_digest = None if declared is None else _declared_text(declared, "case_digest")
        outputs = [] if declared is None else declared.get("outputs")
        if case_digest is None or not isinstance(outputs, list):
            raise PortRefusal(DECLARED_OUTPUT_MATERIAL_UNREADABLE)
        produced = tuple(_declared_output(output) for output in outputs)
        if any(output is None for output in produced):
            raise PortRefusal(DECLARED_OUTPUT_MATERIAL_UNREADABLE)
        return (
            ReplayDeclaration(
                case_id=facts.case_id,
                case_version=facts.case_version,
                case_digest=case_digest,
                outputs=produced,
            ),
        )


def write_fixture_material(
    root: Path | str,
    *,
    evidence: Sequence[StoredEvidence] = (),
    candidate: CandidateDeclaration | None = None,
    declared_outputs: Sequence[ReplayDeclaration] = (),
) -> None:
    """Lay plain values out under a directory in the closed layout.

    This is how an adopting environment seeds a directory the fixture adapters
    can read, and it is the one place the layout is written, so what is read
    and what is written cannot drift apart. It refuses a name the layout cannot
    hold, and it names no value and no directory when it does, because a name
    this layout refuses is exactly the kind of name worth not repeating.
    """
    base = Path(root)
    for record in evidence:
        directory = _held_path(base, EVIDENCE_DIRECTORY, record.evidence_id)
        if directory is None or not held_name(record.version):
            raise ValueError(UNNAMEABLE_MATERIAL)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / (record.version + CONTENT_SUFFIX)).write_bytes(record.content)
        _write_declaration(
            directory / (record.version + RECORD_SUFFIX),
            {
                "declared_digest": record.declared_digest,
                "recorded_at": record.recorded_at,
                "summary": record.summary,
                "valid_until": record.valid_until,
            },
        )
    if candidate is not None:
        base.mkdir(parents=True, exist_ok=True)
        _write_declaration(
            base / CANDIDATE_FILE,
            {
                "artifact_digest": candidate.artifact_digest,
                "candidate_id": candidate.candidate_id,
                "version": candidate.version,
            },
        )
    for declaration in declared_outputs:
        directory = _held_path(base, DECLARED_OUTPUT_DIRECTORY, declaration.case_id)
        if directory is None or not held_name(declaration.case_version):
            raise ValueError(UNNAMEABLE_MATERIAL)
        directory.mkdir(parents=True, exist_ok=True)
        _write_declaration(
            directory / (declaration.case_version + DECLARED_OUTPUT_SUFFIX),
            {
                "case_digest": declaration.case_digest,
                "outputs": [
                    {
                        "content_digest": output.content_digest,
                        "format_digest": output.format_digest,
                        "output_id": output.output_id,
                        "row_count": output.row_count,
                        "version": output.version,
                    }
                    for output in declaration.outputs
                ],
            },
        )


def _write_declaration(path: Path, declared: dict[str, object]) -> None:
    """Write one declared record in the one written form this layout reads."""
    body = json.dumps(declared, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    path.write_text(body, encoding="ascii", newline="\n")


__all__ = [
    "CANDIDATE_FILE",
    "CANDIDATE_MATERIAL_UNREADABLE",
    "CONTENT_SUFFIX",
    "DECLARED_OUTPUT_DIRECTORY",
    "DECLARED_OUTPUT_MATERIAL_UNREADABLE",
    "DECLARED_OUTPUT_SUFFIX",
    "EVIDENCE_DIRECTORY",
    "EVIDENCE_MATERIAL_UNREADABLE",
    "FIXTURE_ADAPTER_VERSION",
    "FIXTURE_CANDIDATE_ADAPTER_ID",
    "FIXTURE_EVIDENCE_ADAPTER_ID",
    "FixtureCandidateRunner",
    "FixtureEvidenceRepository",
    "RECORD_SUFFIX",
    "UNNAMEABLE_MATERIAL",
    "held_name",
    "write_fixture_material",
]
