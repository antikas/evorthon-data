"""Mechanical validation for readable Koine projections and runtime adapters."""
from __future__ import annotations

# evorthon-component: koine_projection
import re
from collections.abc import Mapping
from pathlib import Path

from .engagement import FILE_STAGES, validate_template_projection
from .engagement.aggregate import _labels
from .engagement.use_case import USE_CASE_INTAKE_TEMPLATE_FIELDS

GENERATOR_REFERENCE = re.compile(r"`(?P<path>\.\./\.\./prompts/generators/[a-z0-9-]+\.md)`")
REQUIRED_STANDALONE_TEMPLATES = ("instance-context.md",)
SECTION_HEADING = re.compile(r"^##\s+(?P<name>.+?)\s*$")
# A sectioned template records one aggregate's fields under named sections. The
# aggregate owns the section names and the fields under each, so the projection
# cannot invent a section or move a field between them.
SECTIONED_TEMPLATES = {"use-case-intake.md": USE_CASE_INTAKE_TEMPLATE_FIELDS}


def _add(failures: dict[str, list[str]], root: Path, path: Path, message: str) -> None:
    failures.setdefault(path.relative_to(root).as_posix(), []).append(message)


def validate_koine_projections(root: Path) -> dict[str, list[str]]:
    """Return projection drift without creating a second semantic owner."""
    root = root.resolve()
    failures: dict[str, list[str]] = {}
    templates = root / "templates"

    for filename, stage in FILE_STAGES.items():
        path = templates / filename
        if not path.is_file():
            _add(failures, root, path, "projection is missing")
            continue
        _add_template_drift(failures, root, path)

    for filename in REQUIRED_STANDALONE_TEMPLATES:
        path = templates / filename
        if not path.is_file():
            _add(failures, root, path, "projection is missing or empty")
            continue
        _add_template_drift(failures, root, path)

    for filename, inventory in SECTIONED_TEMPLATES.items():
        path = templates / filename
        if not path.is_file():
            _add(failures, root, path, "projection is missing")
            continue
        _add_sectioned_template_drift(failures, root, path, inventory)

    generators = root / "prompts" / "generators"
    reviewers = root / "prompts" / "reviewers"
    generator_files = {path.name: path for path in generators.glob("*.md")}
    reviewer_files = {path.name: path for path in reviewers.glob("*.md")}

    for name, path in generator_files.items():
        reviewer_name = f"{path.stem}-reviewer.md"
        if reviewer_name not in reviewer_files:
            _add(failures, root, path, f"paired reviewer is missing: {reviewer_name}")
    for name, path in reviewer_files.items():
        generator_name = name.removesuffix("-reviewer.md") + ".md"
        if not name.endswith("-reviewer.md") or generator_name not in generator_files:
            _add(failures, root, path, f"paired generator is missing: {generator_name}")

    referenced_generators: set[str] = set()
    for skill in sorted((root / "skills").glob("*/SKILL.md")):
        references = GENERATOR_REFERENCE.findall(skill.read_text(encoding="utf-8"))
        if len(references) != 1:
            _add(failures, root, skill, "skill must reference exactly one canonical generator")
            continue
        target = (skill.parent / references[0]).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            _add(failures, root, skill, "generator reference escapes the Koine projection root")
            continue
        if target.parent != generators or not target.is_file():
            _add(failures, root, skill, "generator reference is not a canonical projection")
            continue
        referenced_generators.add(target.name)

    for name, path in generator_files.items():
        if name not in referenced_generators:
            _add(failures, root, path, "canonical generator has no skill projection")

    return {path: sorted(messages) for path, messages in sorted(failures.items())}


def validate_koine_runtime_adapters(root: Path, github_root: Path) -> dict[str, list[str]]:
    """Return missing or stale GitHub adapters for every canonical Koine route."""
    root = root.resolve()
    github_root = github_root.resolve()
    repository_root = github_root.parent
    failures: dict[str, list[str]] = {}
    generators = root / "prompts" / "generators"
    reviewers = root / "prompts" / "reviewers"

    for generator in sorted(generators.glob("*.md")):
        adapter = github_root / "prompts" / f"koine-{generator.stem}.prompt.md"
        expected = f"Read `../../koine/prompts/generators/{generator.name}`."
        _add_adapter_drift(failures, repository_root, adapter, expected)

    for reviewer in sorted(reviewers.glob("*-reviewer.md")):
        stem = reviewer.name.removesuffix("-reviewer.md")
        adapter = github_root / "prompts" / f"koine-{stem}-review.prompt.md"
        expected = f"Read `../../koine/prompts/reviewers/{reviewer.name}`."
        _add_adapter_drift(failures, repository_root, adapter, expected)

    for skill in sorted((root / "skills").glob("*/SKILL.md")):
        references = GENERATOR_REFERENCE.findall(skill.read_text(encoding="utf-8"))
        if len(references) != 1:
            continue
        generator_stem = Path(references[0]).stem
        adapter = github_root / "skills" / generator_stem / "SKILL.md"
        expected = f"Read `../../../koine/skills/{skill.parent.name}/SKILL.md`."
        _add_adapter_drift(failures, repository_root, adapter, expected)

    return {path: sorted(messages) for path, messages in sorted(failures.items())}


def _add_adapter_drift(
    failures: dict[str, list[str]],
    repository_root: Path,
    path: Path,
    expected: str,
) -> None:
    if not path.is_file():
        _add(failures, repository_root, path, "adapter projection is missing")
        return
    if path.read_text(encoding="utf-8").strip() != expected:
        _add(failures, repository_root, path, "adapter pointer does not match its canonical projection")


def _template_sections(markdown: str) -> tuple[str, list[tuple[str, str]]]:
    """Split a readable template into its preamble and its named sections."""
    preamble: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    for line in markdown.splitlines():
        heading = SECTION_HEADING.match(line)
        if heading:
            sections.append((heading.group("name"), []))
        elif sections:
            sections[-1][1].append(line)
        else:
            preamble.append(line)
    return "\n".join(preamble), [(name, "\n".join(body)) for name, body in sections]


def _add_sectioned_template_drift(
    failures: dict[str, list[str]],
    root: Path,
    path: Path,
    inventory: Mapping[str, tuple[str, ...]],
) -> None:
    """Reject a sectioned template that omits, invents or misplaces a field."""
    preamble, sections = _template_sections(path.read_text(encoding="utf-8"))
    if _labels(preamble):
        _add(failures, root, path, "the preamble must declare no fields")
    observed = [name for name, _ in sections]
    if observed != list(inventory):
        _add(failures, root, path, "sections do not match the aggregate: " + ", ".join(inventory))
        return
    for name, body in sections:
        expected = set(inventory[name])
        labels = _labels(body)
        missing = sorted(expected - labels)
        unexpected = sorted(labels - expected)
        if missing:
            _add(failures, root, path, f"{name}: missing use-case fields: " + ", ".join(missing))
        if unexpected:
            _add(failures, root, path, f"{name}: unexpected use-case fields: " + ", ".join(unexpected))


def _add_template_drift(failures: dict[str, list[str]], root: Path, path: Path) -> None:
    drift = validate_template_projection(path)
    missing = [item for item in drift if not item.startswith("unexpected field: ")]
    unexpected = [item.removeprefix("unexpected field: ") for item in drift if item.startswith("unexpected field: ")]
    if missing:
        _add(failures, root, path, "missing engagement fields: " + ", ".join(missing))
    if unexpected:
        _add(failures, root, path, "unexpected engagement fields: " + ", ".join(unexpected))
