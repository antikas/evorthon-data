# evorthon-verifies: EVD-README-039
# evorthon-verifies: EVD-README-001
import copy
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import evorthon_data
from evorthon_data import cli
from evorthon_data.public_boundary import private_classifiers
from evorthon_data.public_boundary import write_inventory


ROOT = Path(__file__).parents[2]
# The private work records. They narrate what was built and when, so they are
# not status-bearing product pages and the status gate never reads them.
PRIVATE_RECORD_PREFIXES = ("docs/campaigns/", "docs/cycles/", "docs/items/", "plans/", "release/", "tests/")
# The verbs the verification engine and the delivery routes are described by.
# A future-tense promise about one of them is a status statement.
CAPABILITY_VERBS = (
    "run|validate|reconcile|report|produce|contain|carry|retain|localise|replay|generate"
    "|accept|verify|compare|leave|confirm|classify|diagnose|advise|freeze|emit|project|check"
)
# The closed set of future or in-development language. Each pattern is read
# against one sentence of a shipped page, without case.
FUTURE_LANGUAGE_PATTERNS = (
    r"\bin development\b",
    r"\bnot yet (?:shipped|available|built|implemented|supported|provided|delivered|an available)\b",
    r"\bbeing built\b",
    r"\bfuture (?:release|version|work)\b",
    r"\bin a later (?:release|version)\b",
    r"\bcoming soon\b",
    r"\bforthcoming\b",
    r"\bplanned\b",
    r"\bapproved direction\b",
    r"\bwill (?:" + CAPABILITY_VERBS + r")\b",
    r"\bwill be (?:able|available|shipped|built)\b",
    r"\buntil (?:that|the) (?:engine|capability|route|command)\b",
)
# The only sentences allowed to carry that language: the reference page that defines
# what the marks mean. Each is named by its file and by its exact sentence, so
# a definition cannot grow into a status statement without this list changing.
STATUS_TERM_DEFINITIONS = {
    "docs/product/capability-status.md": (
        "- **In development** means the behaviour is approved product scope but is not yet an available capability.",
    ),
}


def shipped_pages(root: Path) -> list[tuple[str, str]]:
    """Read every Markdown page the product ships, private work records excluded."""
    pages = []
    for path in sorted(root.rglob("*.md")):
        relative = path.relative_to(root).as_posix()
        if relative.startswith(PRIVATE_RECORD_PREFIXES) or relative.startswith("."):
            continue
        pages.append((relative, path.read_text(encoding="utf-8")))
    return pages


def page_sentences(text: str) -> list[str]:
    """Split a page into the sentences the gate reads, one list item at a time."""
    found = []
    for line in text.split(chr(10)):
        for sentence in re.split(r"(?<=[.!?])\s+", line.strip()):
            if sentence.strip():
                found.append(sentence.strip())
    return found


def future_language_findings(pages: list[tuple[str, str]]) -> list[str]:
    """Name every sentence of a shipped page that calls a capability future.

    What this gate reads is language, not meaning. It matches a closed set of
    declared words against one sentence at a time, so three limits hold. It
    cannot see a page that puts a capability in the future without one of those
    words. It cannot tell a sentence about a product capability from a sentence
    about anything else, so a legitimate use of a declared word has to be
    admitted by file and exact sentence in STATUS_TERM_DEFINITIONS. And it
    reads a sentence as the text between full stops on one line, so language
    spread across two sentences escapes it.
    """
    findings = []
    for relative, text in pages:
        allowed = STATUS_TERM_DEFINITIONS.get(relative, ())
        for sentence in page_sentences(text):
            if sentence in allowed:
                continue
            for pattern in FUTURE_LANGUAGE_PATTERNS:
                if re.search(pattern, sentence, re.IGNORECASE):
                    findings.append(relative + ": " + sentence)
                    break
    return findings


def registry_module():
    specification = importlib.util.spec_from_file_location("evorthon_readme_claim_registry", ROOT / "scripts/check_readme_claim_registry.py")
    module = importlib.util.module_from_spec(specification)
    assert specification.loader is not None
    specification.loader.exec_module(module)
    return module


def registry_data(module):
    return module.load_registry(ROOT / "docs/product/readme-claim-registry.toml")


def windows_drive_path():
    return "C" + chr(58) + "/outside.txt"


def test_current_readme_claim_relations_are_complete_and_valid():
    module = registry_module()
    assert module.validate_registry_data(ROOT, registry_data(module)) == {"claims": 50, "relations": 50}


def test_top_level_claim_text_copy_is_rejected():
    module = registry_module()
    data = copy.deepcopy(registry_data(module))
    data["claim_text"] = {"EVD-README-001": "duplicated claim text"}
    with pytest.raises(module.RegistryValidationError, match="registry may contain only"):
        module.validate_registry_data(ROOT, data)


def test_unmarked_material_readme_text_is_rejected(tmp_path):
    module = registry_module()
    readme = tmp_path / "README.md"
    readme.write_text(
        (ROOT / "README.md").read_text(encoding="utf-8")
        + "\nA new material product claim without a stable registry marker.\n",
        encoding="utf-8",
    )
    with pytest.raises(module.RegistryValidationError, match="unmarked README claim text"):
        module.readme_claim_ids(readme)


def test_blank_line_starts_a_new_material_claim_block():
    module = registry_module()
    text = "First material claim.\n\nSecond material claim.\n<!-- evorthon-claim: EVD-PROBE -->\n"
    with pytest.raises(module.RegistryValidationError, match="unmarked README claim text"):
        module.readme_claim_ids_from_text(text)


def test_windows_drive_reference_is_rejected():
    module = registry_module()
    with pytest.raises(module.RegistryValidationError, match="invalid relative reference"):
        module._validate_reference(ROOT, windows_drive_path() + "::EVD-PROBE", "EVD-PROBE", "verifies")


def test_claim_source_must_be_repository_relative():
    module = registry_module()
    data = copy.deepcopy(registry_data(module))
    data["claim_source"] = windows_drive_path()
    with pytest.raises(module.RegistryValidationError, match="invalid claim source"):
        module.validate_registry_data(ROOT, data)


def test_resolved_reference_target_must_stay_under_repository_root(monkeypatch, tmp_path):
    module = registry_module()
    root = tmp_path / "repository"
    root.mkdir()
    escaped = root / "escaped.txt"
    outside = tmp_path / "outside.txt"
    original_resolve = Path.resolve

    def resolve(path, *args, **kwargs):
        if path == escaped:
            return outside
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(module.pathlib.Path, "resolve", resolve)
    with pytest.raises(module.RegistryValidationError, match="invalid relative reference"):
        module._validate_reference(root, "escaped.txt::EVD-PROBE", "EVD-PROBE", "verifies")


def test_status_guide_must_be_repository_relative():
    module = registry_module()
    data = copy.deepcopy(registry_data(module))
    data["status_guide"] = windows_drive_path()
    with pytest.raises(module.RegistryValidationError, match="invalid status guide"):
        module.validate_registry_data(ROOT, data)


def test_duplicate_readme_claim_marker_is_rejected(monkeypatch):
    module = registry_module()
    monkeypatch.setattr(module, "readme_claim_ids", lambda _readme: ["EVD-README-001", "EVD-README-001"])
    with pytest.raises(module.RegistryValidationError, match="duplicate README claim identifier"):
        module.validate_registry_data(ROOT, registry_data(module))


def test_orphan_registry_relation_is_rejected():
    module = registry_module()
    data = copy.deepcopy(registry_data(module))
    orphan = copy.deepcopy(data["relation"][0])
    orphan["claim_id"] = "EVD-README-404"
    data["relation"].append(orphan)
    with pytest.raises(module.RegistryValidationError, match="orphan registry relation"):
        module.validate_registry_data(ROOT, data)


def test_duplicate_registry_relation_is_rejected():
    module = registry_module()
    data = copy.deepcopy(registry_data(module))
    data["relation"].append(copy.deepcopy(data["relation"][0]))
    with pytest.raises(module.RegistryValidationError, match="duplicate registry relation"):
        module.validate_registry_data(ROOT, data)


def test_falsely_implemented_relation_is_rejected():
    module = registry_module()
    data = copy.deepcopy(registry_data(module))
    relation = data["relation"][0]
    relation.update(
        {
            "status": "available",
            "implementation_state": "available",
            "evidence_state": "verified",
            "implementation_refs": ["ADOPTION-GUIDE.md"],
            "evidence_refs": ["tests/pack/test_links_and_indexes.py::test_core_indexes_exist"],
        }
    )
    with pytest.raises(module.RegistryValidationError, match="claim-bound reference"):
        module.validate_registry_data(ROOT, data)


def test_verifier_claims_are_available_and_the_status_page_agrees():
    module = registry_module()
    relations = {relation["claim_id"]: relation for relation in registry_data(module)["relation"]}
    for claim_id in ("EVD-README-009", "EVD-README-019", "EVD-README-020", "EVD-README-021", "EVD-README-022"):
        relation = relations[claim_id]
        assert relation["status"] == "available"
        assert relation["implementation_refs"] and relation["evidence_refs"]
    verification_status = (ROOT / "docs/verification/README.md").read_text(encoding="utf-8").lower()
    assert "does not ship a verification engine" not in verification_status
    assert "in development" not in verification_status


def test_no_shipped_page_calls_an_available_capability_future_or_in_development():
    module = registry_module()
    available = {
        relation["claim_id"]
        for relation in registry_data(module)["relation"]
        if relation["status"] == "available"
    }
    assert available, "the registry states no available claim"
    assert future_language_findings(shipped_pages(ROOT)) == []


def test_every_named_status_term_definition_is_a_sentence_its_page_still_carries():
    for relative, sentences in STATUS_TERM_DEFINITIONS.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        for sentence in sentences:
            assert sentence in text, relative


@pytest.mark.parametrize(
    ("relative", "injected"),
    [
        (
            "docs/product/capability-status.md",
            "The diagnostic adviser is in development and the verification engine will reconcile outputs in a future release.",
        ),
        (
            "README.md",
            "The engine will reconcile actual and expected output once the platform is delivered.",
        ),
        ("docs/verification/README.md", "This capability is not yet shipped."),
    ],
)
def test_an_injected_future_sentence_reddens_the_status_gate(relative, injected):
    pages = []
    for page_relative, text in shipped_pages(ROOT):
        if page_relative == relative:
            text = text + chr(10) + injected + chr(10)
        pages.append((page_relative, text))
    findings = future_language_findings(pages)
    assert findings == [relative + ": " + injected]


# evorthon-verifies: EVD-README-034
def test_shipped_diagnose_command_reports_dependency_capabilities(monkeypatch, capsys):
    expected = {"pinax-tracker": {"installed": True, "version": "0.1.3"}}
    monkeypatch.setattr(cli, "installed_capabilities", lambda: expected)
    assert cli.main(["diagnose"]) == 0
    assert json.loads(capsys.readouterr().out) == {"capabilities": expected, "product": "evorthon-data-harness"}


def candidate_licence_text() -> str:
    """The MIT licence a candidate carries, read wherever the running tree holds it."""
    for relative in ("LICENSE", "release/public/LICENSE"):
        path = ROOT / relative
        if path.is_file() and path.read_text(encoding="utf-8").startswith("MIT License"):
            return path.read_text(encoding="utf-8")
    raise AssertionError("no MIT licence payload is available to assemble a candidate")


def child_environment() -> dict[str, str]:
    """Give a child the product package this test itself imported."""
    package_root = str(Path(evorthon_data.__file__).resolve().parents[1])
    inherited = os.environ.get("PYTHONPATH")
    return {
        **os.environ,
        "PYTHONPATH": package_root if not inherited else package_root + os.pathsep + inherited,
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def scratch_candidate(tmp_path: Path) -> Path:
    """Assemble the smallest candidate the self-check reads, the command included.

    The check resolves its own tree from where the command file sits, so a copy
    of the command under a scratch root makes that root the candidate. The
    hashed-token policy is written empty: this drive proves the command
    resolves and runs, and the scanner's own fixtures prove what it catches.
    """
    candidate = tmp_path / "candidate"
    (candidate / "scripts").mkdir(parents=True)
    shutil.copy(ROOT / "scripts/check_public_candidate.py", candidate / "scripts/check_public_candidate.py")
    shutil.copy(ROOT / "README.md", candidate / "README.md")
    # The project file a candidate carries is the projected one: the private
    # build's do-not-upload classifier never reaches a candidate, and the check
    # refuses a project file that still carries it.
    project_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    marked = set(private_classifiers(project_text))
    projected = "".join(
        line for line in project_text.splitlines(keepends=True)
        if line.strip().strip(",").strip().strip('"') not in marked
    )
    (candidate / "pyproject.toml").write_text(projected, encoding="utf-8", newline=chr(10))
    (candidate / "LICENSE").write_text(candidate_licence_text(), encoding="utf-8")
    (candidate / "PUBLIC-LEAKAGE-POLICY.json").write_text(
        json.dumps({"forbidden_token_hashes": []}, indent=2) + chr(10), encoding="utf-8"
    )
    write_inventory(candidate, "scratch-candidate", provisional=True)
    return candidate


# evorthon-verifies: EVD-README-035
def test_contributor_commands_the_readme_offers_resolve_and_run(tmp_path):
    """Drive both offered commands rather than asserting that their text exists.

    The lane wrapper is driven through the interpreter for its own help, which
    fails if the wrapper cannot be parsed or its arguments cannot be built. The
    candidate check is driven in scan-only mode over an assembled candidate,
    with the finalizing step the published precondition names, so the command
    the README offers is shown to run to a green answer.
    """
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "python scripts/run_tests.py --lane fast" in text
    assert "python scripts/check_public_candidate.py" in text

    lane_help = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_tests.py"), "--help"],
        capture_output=True, text=True, cwd=ROOT, env=child_environment(), check=False,
    )
    assert lane_help.returncode == 0, lane_help.stdout + lane_help.stderr
    assert "--lane" in lane_help.stdout

    candidate = scratch_candidate(tmp_path)
    checked = subprocess.run(
        [sys.executable, str(candidate / "scripts/check_public_candidate.py"), "--scan-only", "--finalize"],
        capture_output=True, text=True, cwd=candidate, env=child_environment(), check=False,
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert json.loads(checked.stdout) == {"status": "green", "tree": "final"}
