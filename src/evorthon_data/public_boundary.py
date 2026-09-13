"""Fail-only public-candidate identity and leakage policy.

The machine-route shapes this scan reads have one owner, which every boundary
of this product reads, so no two boundaries disagree about what a machine route
is. What this scan does with a carried shape, and what it allows, stays here.

This boundary reads whole files of source, fixtures and documentation rather
than one declared value, and that changes what some shapes mean in it. Four
allowances follow, each with the reason it exists.

* A web address is reported unless it is one of two allowed forms. A secure
  address is how this product's own documentation links to published material.
  One insecure address, the drawing namespace an SVG declares, is written into
  every generated diagram. Every other web address is reported, which is how an
  address on an internal host is caught here.
* An address under any other scheme is reported too, which is how a cloud
  store, a transfer, a share, a database or a lake address is caught here. Two
  forms are skipped. A scheme this scan already names in a finding of its own,
  which is the file scheme and the two web ones, is left to that finding so one
  address is reported once. This product's own logical reference scheme is
  allowed under two readings, because neither names a host: the composed form,
  which is the scheme with this product's own record root written after it, and
  the scheme written with no name after it at all, which is how the tracker
  adapter's contract states the form it accepts. The scheme in front of
  anything a host can be spelled with is reported, whether that is a letter, a
  digit, a bracketed address or a leading mark. Two shipped files write the
  scheme, in three forms between them.
* The absolute-path shapes are not read, and neither are the three other
  declared-value shapes: a lettered volume with no separator after it, a share
  host with nothing after it, and a traversal in the middle of a value. Each
  reports a form that a line of ordinary prose or program source carries often
  enough that reading it here would report the candidate's own documentation
  rather than a leak. The boundaries that read one declared value read all
  five, because a declared value is not prose.
* The backslash-relative shape is not read in program source or in the JSON
  family, where a backslash writes a character escape rather than a separator.
  It is read in every other shipped file, which is where a relative path from
  somebody's machine would land.

This module also owns the declaration every fixture root states about its own
material, and the gate an export runs over that declaration before it writes
anything. The shape is declared once here, so the tests that own each root and
the export that projects it read the same record and cannot disagree about what
a complete declaration is.
"""
from __future__ import annotations

# evorthon-component: presentation

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .boundary_patterns import (
    ABSOLUTE_PATH,
    ALLOWED_SCHEME_FORMS,
    BACKSLASH_RELATIVE_PATH,
    DECLARED_ABSOLUTE_PATH,
    DECLARED_TRAVERSAL,
    DRAWING_NAMESPACE,
    DRIVE_PATH,
    DRIVE_RELATIVE_PATH,
    LOCAL_FILE_ADDRESS,
    LOGICAL_REFERENCE_SCHEME,
    MACHINE_ROUTE_PATTERNS,
    MACHINE_ROUTE_SHAPES,
    NAMED_SCHEME_FORMS,
    NETWORK_SHARE_HOST,
    NETWORK_SHARE_PATH,
    SCHEME_ADDRESS,
    SECURE_WEB_SCHEME,
    TRAVERSAL,
    USER_HOME_PATH,
    WEB_ADDRESS,
    shapes,
)

INVENTORY = "PUBLIC-INVENTORY.json"
POLICY = "PUBLIC-LEAKAGE-POLICY.json"
# Where a tree declares what git does to the files it holds, and the one
# declaration a candidate carries, which is what makes a carriage return in a
# text file a byte no clone reproduces.
ATTRIBUTES = ".gitattributes"
CHECKOUT_ATTRIBUTES = "* text=auto eol=lf"
# How much of a file git reads before it decides the content is binary.
BINARY_SNIFF_BYTES = 8000
CARRIAGE_RETURN = b"\r"
NUL = b"\x00"
# The name a repository gives its own git entry at the top of its tree. A clone
# of a published repository holds a directory of that name there, and a linked
# worktree holds a file of that name there instead. Neither is part of the
# candidate, and neither was ever written by a projection. Below the top of a
# tree the same name is a private path like the others named here.
GIT_ENTRY = ".git"
PRIVATE_PARTS = {GIT_ENTRY, ".ergon", "plans", "release", "artifacts", "__pycache__"}
# The name this scan reports each declared shape under. These are the words the
# published evidence has always carried, so a finding reads as it did before.
REPORTED_AS = {
    LOCAL_FILE_ADDRESS: "file URL",
    DRIVE_PATH: "Windows drive path",
    NETWORK_SHARE_PATH: "UNC path",
    USER_HOME_PATH: "user-home POSIX path",
    WEB_ADDRESS: "non-public HTTP URL",
    SCHEME_ADDRESS: "non-public address scheme",
    TRAVERSAL: "traversal",
    BACKSLASH_RELATIVE_PATH: "backslash-relative path",
}
# The five shapes this scan does not read, and why, are in the module docstring.
UNREAD_SHAPES = (
    ABSOLUTE_PATH,
    DECLARED_ABSOLUTE_PATH,
    DRIVE_RELATIVE_PATH,
    NETWORK_SHARE_HOST,
    DECLARED_TRAVERSAL,
)
SCANNED_SHAPES = tuple(name for name in MACHINE_ROUTE_SHAPES if name not in UNREAD_SHAPES)
LOCAL_PATTERNS = tuple(
    (REPORTED_AS[name], pattern) for name, pattern in shapes(MACHINE_ROUTE_PATTERNS, SCANNED_SHAPES)
) + (
    ("private operational record", re.compile(r"(?:^|[\\/\s])(?:\.ergon|docs/cycles|plans|release)(?:[\\/\s]|$)", re.I)),
)
# The address forms this candidate is allowed to carry, and the schemes this
# scan reports under a name of their own, are declared once with the shapes.
# The files whose bytes write a backslash as a character escape.
ESCAPED_SUFFIXES = {".py", ".json", ".canonical"}
TOKEN = re.compile(r"[a-z0-9][a-z0-9._/-]{2,}", re.I)
# How much of the text after a scheme an allowed form can need.
ALLOWED_FORM_TAIL = max(len(form) for form in ALLOWED_SCHEME_FORMS)
# The characters a written host is spelled with, beyond letters and digits: the
# marks that open an address in brackets, separate its labels, lead a name, or
# stand in for a character. A scheme with one of these after it is naming a
# host, however unusual the name looks.
HOST_CHARACTERS = frozenset("-._~%[]:@")


def _web_address_carried(material: str) -> bool:
    """Whether the material carries a web address that is not an allowed one."""
    pattern = MACHINE_ROUTE_PATTERNS[WEB_ADDRESS]
    for found in pattern.finditer(material):
        if found.group(0).lower().endswith(SECURE_WEB_SCHEME):
            continue
        if material[found.end() :].startswith(DRAWING_NAMESPACE):
            continue
        return True
    return False


def _names_a_host(after: str) -> bool:
    """Whether what follows a scheme begins a written host name or address."""
    first = after[:1]
    return bool(first) and (first.isalnum() or first in HOST_CHARACTERS)


def _scheme_address_carried(material: str) -> bool:
    """Whether the material carries an address under a scheme this scan reports.

    A scheme this scan already names in a finding of its own is skipped, so one
    address is reported once. An allowed form is read as the whole composed
    form and not as a scheme prefix, so this product's own reference scheme in
    front of a host is a finding like any other, whatever the host is spelled
    with. That scheme with no name after it is skipped too, because it names no
    host: it is how the tracker adapter's contract states the form it accepts.
    Every other scheme is a finding.
    """
    pattern = MACHINE_ROUTE_PATTERNS[SCHEME_ADDRESS]
    for found in pattern.finditer(material):
        form = found.group(0).lower()
        if form in NAMED_SCHEME_FORMS:
            continue
        after = material[found.end() : found.end() + ALLOWED_FORM_TAIL].lower()
        if any((form + after).startswith(allowed) for allowed in ALLOWED_SCHEME_FORMS):
            continue
        if form == LOGICAL_REFERENCE_SCHEME and not _names_a_host(after):
            continue
        return True
    return False


def _shape_is_read(name: str, suffix: str) -> bool:
    """Whether this scan reads one declared shape in a file of this kind."""
    if name == REPORTED_AS[BACKSLASH_RELATIVE_PATH]:
        return suffix not in ESCAPED_SUFFIXES
    return True


def policy_hashes(policy_path: Path) -> set[str]:
    data = json.loads(policy_path.read_text(encoding="utf-8"))
    hashes = data.get("forbidden_token_hashes", [])
    if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes):
        raise ValueError("invalid forbidden-token policy")
    return set(hashes)


def candidate_files(root: Path) -> list[Path]:
    """Every file one candidate root holds, sorted, its own git entry aside.

    This is the one owner of what the files of a candidate are. The scan, the
    checkout rewrite check, the inventory writer, the inventory validator and
    the fixture readers all ask this question and all get the same answer, so
    no two of them disagree about which files a tree is made of.

    The check ships with the candidate and is run on a checkout of the
    published repository, which holds a git entry at the top of its tree that
    no projection ever wrote. That entry is left out here, whether it is the
    directory a clone holds or the file a linked worktree holds in its place.

    Nothing else is left out. A git entry below the top of the root is a file
    of the tree like any other, so it is still named wherever a private or
    undeclared path is named. A root nothing holds yields nothing, which is the
    answer a walk of a directory that is not there has always given.
    """
    root = Path(root)
    if not root.is_dir():
        return []
    found: list[Path] = []
    for entry in root.iterdir():
        if entry.name == GIT_ENTRY:
            continue
        if entry.is_file():
            found.append(entry)
            continue
        found.extend(path for path in entry.rglob("*") if path.is_file())
    return sorted(found)


def scan_candidate(root: Path) -> list[str]:
    root = root.resolve()
    hashes = policy_hashes(root / POLICY)
    findings: list[str] = []
    for path in candidate_files(root):
        relative = path.relative_to(root).as_posix()
        if relative == INVENTORY:
            continue  # Its content is self-excluded by the final inventory rule.
        if any(part in PRIVATE_PARTS for part in path.relative_to(root).parts):
            findings.append(f"private or undeclared path: {relative}")
            continue
        data = path.read_bytes()
        if NUL in data:
            findings.append(f"undeclared binary: {relative}")
            continue
        material = relative + "\n" + data.decode("utf-8", "replace")
        for name, pattern in LOCAL_PATTERNS:
            if name == REPORTED_AS[WEB_ADDRESS]:
                carried = _web_address_carried(material)
            elif name == REPORTED_AS[SCHEME_ADDRESS]:
                carried = _scheme_address_carried(material)
            elif not _shape_is_read(name, path.suffix):
                continue
            else:
                carried = bool(pattern.search(material))
            if carried:
                findings.append(f"{name}: {relative}")
        for token in TOKEN.findall(material.lower()):
            if hashlib.sha256(token.encode("utf-8")).hexdigest() in hashes:
                findings.append(f"hashed forbidden token: {relative}")
                break
    return findings


def reads_as_text(data: bytes) -> bool:
    """Whether git reads these bytes as text under an automatic text attribute.

    Git decides with a heuristic of its own: content carrying a zero byte near
    its start is binary and is stored and written back byte for byte. Every
    other file is text, so its line endings are normalised when it is committed
    and written as line feeds when it is checked out.
    """
    return NUL not in data[:BINARY_SNIFF_BYTES]


def declares_checkout_attributes(root: Path) -> bool:
    """Whether this tree declares that git normalises every text file it holds.

    A published candidate carries that declaration, which is what gives the
    rule below its authority. A tree that declares nothing states no
    normalisation, so nothing in it is read against a rule it never took.
    """
    try:
        declaration = (root / ATTRIBUTES).read_text(encoding="utf-8")
    except OSError:
        return False
    return any(line.strip() == CHECKOUT_ATTRIBUTES for line in declaration.splitlines())


def checkout_rewrite_findings(root: Path) -> list[str]:
    """Name every candidate file a checkout of that candidate would rewrite.

    The candidate declares one attribute over all of its own files, so every
    text file it carries is stored and checked out with line feeds alone. A
    text file whose bytes carry a carriage return is therefore a file no clone
    reproduces: the published tree would hold different bytes, the inventory
    would record hashes nothing in that tree matches, and the candidate check
    would refuse the published repository's own contents. Reporting it here
    keeps such a candidate from ever being finalized or published.

    A binary file is left alone, because a checkout writes its bytes back
    unchanged whatever they carry. A tree carrying no such declaration is left
    alone too, because the rule read here is the one the tree states about
    itself.
    """
    root = Path(root).resolve()
    if not declares_checkout_attributes(root):
        return []
    findings: list[str] = []
    for path in candidate_files(root):
        data = path.read_bytes()
        if CARRIAGE_RETURN in data and reads_as_text(data):
            findings.append(f"a checkout would rewrite: {path.relative_to(root).as_posix()}")
    return findings


def _tree_digest(root: Path, files: list[str]) -> str:
    lines = []
    for relative in files:
        if relative == INVENTORY:
            continue
        lines.append(f"{relative}:{hashlib.sha256((root / relative).read_bytes()).hexdigest()}")
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def write_inventory(root: Path, source_commit: str, provisional: bool) -> dict:
    held = [path.relative_to(root).as_posix() for path in candidate_files(root)]
    files = sorted(relative for relative in held if relative != INVENTORY)
    files.append(INVENTORY)
    files.sort()
    payload = {
        "schema": "evorthon.public-inventory.v2",
        "source_commit": source_commit,
        "inventory_self_exclusion": "The inventory is listed but excluded from its own file digest and tree digest.",
        "provisional": provisional,
        "files": [{"path": relative, "sha256": "self-excluded" if relative == INVENTORY else hashlib.sha256((root / relative).read_bytes()).hexdigest()} for relative in files],
        "tree_digest": _tree_digest(root, files),
    }
    # The inventory is a file of the candidate like any other, so it is written
    # with the line endings the candidate declares. Taking the platform's own
    # endings would put a file in the tree that no clone reproduces.
    (root / INVENTORY).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return payload


def validate_inventory(root: Path, require_final: bool) -> dict:
    data = json.loads((root / INVENTORY).read_text(encoding="utf-8"))
    if data.get("schema") != "evorthon.public-inventory.v2":
        raise ValueError("unknown inventory schema")
    if require_final and data.get("provisional"):
        raise ValueError("candidate inventory is provisional")
    actual = sorted(path.relative_to(root).as_posix() for path in candidate_files(root))
    listed = [entry["path"] for entry in data.get("files", [])]
    if actual != listed or INVENTORY not in listed:
        raise ValueError("candidate inventory does not cover final files")
    for entry in data["files"]:
        if entry["path"] != INVENTORY and entry["sha256"] != hashlib.sha256((root / entry["path"]).read_bytes()).hexdigest():
            raise ValueError(f"candidate inventory hash mismatch: {entry['path']}")
    if data["tree_digest"] != _tree_digest(root, listed):
        raise ValueError("candidate tree digest mismatch")
    return data


# --- the fixture declarations a projection may take ---------------------------
# Every fixture root that projects holds one record beside its material. The
# record declares the material once and names every file the root holds, so a
# file nobody declared is a finding wherever the record is read. The export
# reads the same record before it writes anything, and the tests that own each
# root read it too, so one shape is declared here and nowhere else.
FIXTURE_TREE = "tests/fixtures"
PROVENANCE_RECORD = "provenance.json"
PROVENANCE_FORM = "evorthon.fixture.provenance.v1"
# The two dispositions a declaration states. Material declared for projection is
# read as data and reaches the public candidate; material declared as withheld
# is neither.
DECLARED = "declared"
WITHHELD = "withheld"
# What a projected declaration must carry: one of the two ways its content was
# produced, and both of the declarations that say what may be done with it.
PRODUCED_BY = ("seed", "author")
REQUIRED_DECLARATIONS = ("licence", "source")
# What a withheld declaration must carry instead.
WITHHELD_DECLARATIONS = ("provenance", "reason")
UNRESOLVED = "unresolved"
# The one handling classification a projection may take. It is the least
# restricted label of the closed handling order the session boundary owns. Any
# other label, and no label at all, keeps the file out of a candidate.
OPEN_CLASSIFICATION = "public"
# What a root states once for all of its material. A file the record names with
# a note is held on these. A file the record names with a record of its own
# states its own, except its classification, which the root states for all its
# material unless that record narrows it.
ROOT_DECLARATION = ("seed", "author", "licence", "source", "classification")


def resolved(value) -> bool:
    """Whether one declared value states a fact a projection may rely on.

    A blank value states nothing. The unresolved marker states that the fact is
    not known, which is also nothing, so the two are read the same way wherever
    a projected declaration is required to carry a statement.
    """
    stated = str(value).strip()
    return bool(stated) and stated.casefold() != UNRESOLVED


@dataclass(frozen=True)
class FixtureDeclaration:
    """One file a fixture root declares, and what the record says about it."""

    name: str
    disposition: str
    classification: str
    fields: dict

    @property
    def projected(self) -> bool:
        return self.disposition == DECLARED

    def missing(self) -> tuple[str, ...]:
        """Name every way this declaration falls short of what its kind requires.

        A projected declaration states how its content was produced, under
        which licence it is held, where it came from, and a handling
        classification a projection may take. A withheld declaration states
        that its provenance is unresolved and why.

        A projected declaration that writes the unresolved marker where a
        statement belongs has declared nothing: it says the fact is not known.
        So an unresolved licence, source, seed, author or provenance is read
        here exactly as an absent one, and is named as the field it is.
        """
        if self.projected:
            held = tuple(
                f"undeclared {name}"
                for name in REQUIRED_DECLARATIONS
                if not resolved(self.fields.get(name, ""))
            )
            produced = any(resolved(self.fields.get(name, "")) for name in PRODUCED_BY)
            stated = (
                ("undeclared provenance",)
                if "provenance" in self.fields and not resolved(self.fields["provenance"])
                else ()
            )
            if not self.classification.strip():
                classified: tuple[str, ...] = ("undeclared classification",)
            elif self.classification != OPEN_CLASSIFICATION:
                classified = ("classification the projection refuses",)
            else:
                classified = ()
            produced_by = () if produced else ("undeclared seed or author",)
            return held + produced_by + stated + classified
        held = tuple(
            f"undeclared {name}"
            for name in WITHHELD_DECLARATIONS
            if not str(self.fields.get(name, "")).strip()
        )
        return held + (
            ()
            if str(self.fields.get("provenance", "")) == UNRESOLVED
            else ("undeclared unresolved provenance",)
        )


def _declaration(name: str, entry, held: dict) -> FixtureDeclaration:
    """Read one named file's declaration, on the root's where it states none."""
    if isinstance(entry, dict):
        fields = dict(entry)
        fields.setdefault("classification", held["classification"])
        disposition = str(fields.get("projection", ""))
    else:
        fields = {**held, "note": str(entry), "projection": DECLARED}
        disposition = DECLARED
    return FixtureDeclaration(
        name=name,
        disposition=disposition,
        classification=str(fields.get("classification", "")),
        fields=fields,
    )


class FixtureProvenance:
    """One fixture root's record, read as the declarations it states.

    The record declares its material once at the root and names every file the
    root holds. A file named with a note is held on the root's own declaration.
    A file named with a record of its own states that record instead, except
    its classification, which the root states unless the file's record narrows
    it. Nothing else is inherited, so a declaration that drops its licence is
    short of what it requires rather than quietly held on the root's.

    A refusal from this reader names the root the way the repository names it,
    never the place it happens to sit on one machine. The caller says which
    name that is; with none given the root's own directory name is used.
    """

    def __init__(self, root: Path, named: str | None = None) -> None:
        self.root = Path(root)
        self.declared_as = named or self.root.name
        try:
            payload = (self.root / PROVENANCE_RECORD).read_text(encoding="ascii")
        except OSError as exc:
            raise ValueError(
                f"a fixture root holds no readable {PROVENANCE_RECORD}: {self.declared_as}"
            ) from exc
        try:
            record = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"a fixture root holds an unreadable {PROVENANCE_RECORD}: {self.declared_as}"
            ) from exc
        if record.get("form") != PROVENANCE_FORM:
            raise ValueError(
                f"a fixture root declares the form {PROVENANCE_FORM}: {self.declared_as}"
            )
        if not isinstance(record.get("files"), dict):
            raise ValueError(f"a fixture root names every file it holds: {self.declared_as}")
        self.record = record
        held = {name: str(record.get(name, "")) for name in ROOT_DECLARATION}
        self.declarations = {
            name: _declaration(name, entry, held) for name, entry in record["files"].items()
        }

    def held(self) -> tuple[str, ...]:
        """Every file this root holds, by its root-relative name.

        The files of this root are read through the one owner of what a
        candidate's files are, so a fixture root and the candidate that carries
        it are made of the same files. The record itself is not one of them,
        because it is the statement about the material rather than material.
        """
        return tuple(
            sorted(
                path.relative_to(self.root).as_posix()
                for path in candidate_files(self.root)
                if path.name != PROVENANCE_RECORD
            )
        )

    def projected(self) -> tuple[str, ...]:
        """Every declared file a projection takes, by its root-relative name."""
        return tuple(sorted(name for name, held in self.declarations.items() if held.projected))

    def withheld(self) -> tuple[str, ...]:
        """Every declared file a projection leaves behind."""
        return tuple(sorted(name for name, held in self.declarations.items() if not held.projected))

    def findings(self) -> tuple[str, ...]:
        """Name every way this root's material and its record disagree.

        A file nobody declared, a declaration carrying less than its kind
        requires, and a projected declaration nothing holds are all findings.
        A withheld file the root does not hold is not: a projection leaves it
        behind, so a projected tree holds every declared file it may and none
        of the ones it may not.
        """
        held = set(self.held())
        found = [f"undeclared file: {name}" for name in sorted(held - set(self.declarations))]
        for name in sorted(self.declarations):
            declaration = self.declarations[name]
            if declaration.disposition not in (DECLARED, WITHHELD):
                found.append(f"undeclared projection: {name}")
                continue
            for absent in declaration.missing():
                found.append(f"{absent}: {name}")
            if declaration.projected and name not in held:
                found.append(f"declared file nothing holds: {name}")
        return tuple(found)


def declaring_root(tree: Path, path: str) -> str | None:
    """The nearest directory above one path that holds a provenance record."""
    parts = PurePosixPath(path).parts
    for depth in range(len(parts) - 1, 0, -1):
        candidate = "/".join(parts[:depth])
        if candidate != FIXTURE_TREE and not candidate.startswith(FIXTURE_TREE + "/"):
            break
        if (tree / candidate / PROVENANCE_RECORD).is_file():
            return candidate
    return None


def fixture_gate_findings(tree: Path, projected) -> list[str]:
    """Name every projected fixture path the declarations do not cover.

    The export runs this over the paths the manifest projects, before it writes
    a candidate or an inventory, so a fixture nobody declared, a declaration
    that does not carry its licence, its source or the way its content was
    produced, a declaration stating no handling classification, and a file
    classified above what a projection may take never reach a candidate. The
    candidate self-check runs it again over the fixtures a candidate holds.
    """
    tree = Path(tree)
    findings: list[str] = []
    records: dict[str, FixtureProvenance | None] = {}
    for path in sorted(set(projected)):
        if path != FIXTURE_TREE and not path.startswith(FIXTURE_TREE + "/"):
            continue
        if PurePosixPath(path).name == PROVENANCE_RECORD:
            continue
        root = declaring_root(tree, path)
        if root is None:
            findings.append(f"fixture outside every declared root: {path}")
            continue
        if root not in records:
            try:
                records[root] = FixtureProvenance(tree / root, named=root)
            except ValueError as exc:
                records[root] = None
                findings.append(f"unreadable fixture record: {exc}")
        record = records[root]
        if record is None:
            continue
        declaration = record.declarations.get(path[len(root) + 1 :])
        if declaration is None:
            findings.append(f"undeclared fixture: {path}")
            continue
        if not declaration.projected:
            findings.append(f"withheld fixture in the projection: {path}")
            continue
        findings.extend(f"{absent}: {path}" for absent in declaration.missing())
    return findings
