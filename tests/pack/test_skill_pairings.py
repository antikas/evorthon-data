# evorthon-verifies: EVD-README-014
from pathlib import Path

ROOT = Path(__file__).parents[2]
INTAKE_PACK = (
    "koine/skills/intaking-use-case/SKILL.md",
    "koine/prompts/generators/intake-use-case.md",
    "koine/prompts/reviewers/intake-use-case-reviewer.md",
    "koine/templates/use-case-intake.md",
    ".github/prompts/koine-intake-use-case.prompt.md",
    ".github/prompts/koine-intake-use-case-review.prompt.md",
    ".github/skills/intake-use-case/SKILL.md",
)
INTAKE_ADAPTER_POINTERS = {
    ".github/prompts/koine-intake-use-case.prompt.md": "Read `../../koine/prompts/generators/intake-use-case.md`.",
    ".github/prompts/koine-intake-use-case-review.prompt.md": "Read `../../koine/prompts/reviewers/intake-use-case-reviewer.md`.",
    ".github/skills/intake-use-case/SKILL.md": "Read `../../../koine/skills/intaking-use-case/SKILL.md`.",
}


def test_skills_name_paired_reviewers():
    assert 'paired reviewer' in (Path(__file__).parents[2]/'koine/skills/designing-data-platform/SKILL.md').read_text()


def test_use_case_intake_ships_a_complete_paired_pack():
    for relative in INTAKE_PACK:
        assert (ROOT / relative).is_file(), relative

    skill = (ROOT / "koine/skills/intaking-use-case/SKILL.md").read_text(encoding="utf-8")
    assert "../../prompts/generators/intake-use-case.md" in skill
    assert "paired reviewer" in skill

    for relative, pointer in INTAKE_ADAPTER_POINTERS.items():
        assert (ROOT / relative).read_text(encoding="utf-8").strip() == pointer, relative
