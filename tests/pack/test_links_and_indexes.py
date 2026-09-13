from pathlib import Path

import pytest

# A Markdown file carries YAML frontmatter when a delimiter line stands among
# its opening lines. The runtimes that read a pack file parse that block only
# when it is the first thing in the file, so a line placed above it, such as a
# claim marker, silently removes the frontmatter.
FRONTMATTER_DELIMITER = "---"
FRONTMATTER_WINDOW = 6


def frontmatter_carriers(root: Path) -> list[str]:
    """Name every Markdown file whose opening lines hold a frontmatter delimiter."""
    carriers = []
    for path in sorted(root.rglob("*.md")):
        relative = path.relative_to(root).as_posix()
        if relative.startswith("."):
            continue
        lines = path.read_text(encoding="utf-8").split(chr(10))
        if FRONTMATTER_DELIMITER in lines[:FRONTMATTER_WINDOW]:
            carriers.append(relative)
    return carriers


def files_not_opening_with_frontmatter(root: Path) -> list[str]:
    """Name every frontmatter carrier that does not begin with its delimiter."""
    broken = []
    for relative in frontmatter_carriers(root):
        first = (root / relative).read_text(encoding="utf-8").split(chr(10))[0]
        if first != FRONTMATTER_DELIMITER:
            broken.append(relative)
    return broken


def test_every_markdown_file_that_carries_frontmatter_starts_with_it():
    root = Path(__file__).parents[2]
    assert frontmatter_carriers(root), "no Markdown file carries frontmatter"
    assert files_not_opening_with_frontmatter(root) == []


@pytest.mark.parametrize("above", ["<!-- evorthon-implements: EVD-PROBE -->", "# A title"])
def test_a_line_above_the_frontmatter_reddens_the_gate(tmp_path, above):
    page = tmp_path / "SKILL.md"
    page.write_text(
        chr(10).join([above, FRONTMATTER_DELIMITER, "name: probe", FRONTMATTER_DELIMITER, "", "Body."]),
        encoding="utf-8",
    )
    assert frontmatter_carriers(tmp_path) == ["SKILL.md"]
    assert files_not_opening_with_frontmatter(tmp_path) == ["SKILL.md"]


# evorthon-verifies: EVD-README-032
def test_core_indexes_exist():
    root=Path(__file__).parents[2]
    for path in ['koine/INDEX.md','docs/INDEX.md','context/INDEX.md','examples/INDEX.md']:
        assert (root/path).exists()


def test_repository_workflow_selects_the_tree_appropriate_verdict():
    root = Path(__file__).parents[2]
    workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "[ -f PUBLIC-INVENTORY.json ] && [ -f PUBLIC-LEAKAGE-POLICY.json ]" in workflow
    assert "python scripts/check_public_candidate.py" in workflow
    assert "uv run --locked --group dev python scripts/run_tests.py --lane fast" in workflow
