# evorthon-verifies: EVD-README-012
# evorthon-verifies: EVD-README-011
# evorthon-verifies: EVD-README-005
import shutil
from pathlib import Path

from evorthon_data.engagement.stages import validate_examples, validate_stage
from evorthon_data.engagement.use_case import (
    CONDITION_KEYS,
    USE_CASE_INTAKE_SECTIONS,
    USE_CASE_INTAKE_TEMPLATE_FIELDS,
)
from evorthon_data.koine_projection import validate_koine_projections

ROOT = Path(__file__).parents[2] / "examples"
KOINE = Path(__file__).parents[2] / "koine"
INTAKE_SECTIONS = (
    "1. Outcome and consumer",
    "2. Target outputs",
    "3. Inputs",
    "4. Reference and enrichment data",
    "5. Intermediate steps",
    "6. Scenarios",
    "7. Comparison policy",
    "8. Authorities",
    "9. Build route",
    "10. Classification and handling",
    "11. History and time",
    "12. Freshness and operations",
    "13. Volume and performance",
    "14. Access and consumption",
    "15. Quality tolerances",
    "16. Change, audit and transition",
)
INTAKE_GENERATOR_STATEMENTS = (
    "artefact-first",
    "base tools",
    "artefact identity",
    "the position inside the artefact",
    "who or what extracted it",
    "extracted, inferred or confirmed",
    "confirm inferred facts in bulk",
    "residual questions",
    "i do not know yet",
    "creates a gap",
    "the existing output it replaces",
    "continuity worth keeping or an accident of the old run",
    "greenfield use case never asks a parity question",
    "never propose a parser",
)
INTAKE_ARTEFACT_CLASSES = (
    "delimited extracts",
    "spreadsheets",
    "data dictionaries",
    "table definitions",
    "query and transformation code",
    "project definitions",
    "exported job definitions",
    "reports",
    "schedules",
    "catalogue exports",
)
READINESS_LOOP_STEPS = (
    "read the artefacts",
    "record the facts",
    "recompute readiness per segment",
    "ask the residual questions",
    "repeat",
    "buildable now",
    "gaps",
    "open questions",
)
SUCCESS_CRITERIA = '[{"acceptance_rule":"named acceptance","check_family":"conformance","evidence":[{"digest":"digest-evidence","identifier":"evidence-one","version":"v1"}],"required_result":"pass","signal":"measurable result","validator":{"digest":"digest-validator","identifier":"result-validator","kind":"validator_specification","version":"v1"}}]'


# evorthon-verifies: EVD-README-032
def test_examples_prove_distinct_modes_with_the_production_validator():
    assert validate_examples(ROOT) == {}
    green = ROOT / "greenfield/renewable-asset-observability"
    assert not (green / "current-estate-map.md").exists()
    green_text = "\n".join(path.read_text(encoding="utf-8") for path in green.glob("*.md"))
    assert "no current estate" in green_text.lower()
    assert "legacy baseline" not in green_text.lower()


def test_missing_stage_field_is_rejected_by_the_production_validator(tmp_path):
    fixture = tmp_path / "outcome-brief.md"
    fixture.write_text(f"Consumer outcome: value\nSuccess signals: measurable result\nSuccess criteria: {SUCCESS_CRITERIA}\nScope: boundary\nAuthorities: owner\nEvidence: evidence-one@v1#digest-evidence; result-validator@v1#digest-validator\nConstraints: none\nVerification case intent: contract conformance\nCheck families: conformance\nLineage/checkpoint expectations: view — owner\nAcceptance rules: named acceptance\nPaired review: yes\nReviewer: review\nFinding: none\nDisposition: accepted\n", encoding="utf-8")
    assert validate_stage(fixture, "outcome") == ["open questions"]


def test_missing_paired_review_disposition_is_rejected_by_the_production_validator(tmp_path):
    fixture = tmp_path / "outcome-brief.md"
    fixture.write_text(f"Consumer outcome: value\nSuccess signals: measurable result\nSuccess criteria: {SUCCESS_CRITERIA}\nScope: boundary\nAuthorities: owner\nEvidence: evidence-one@v1#digest-evidence; result-validator@v1#digest-validator\nConstraints: none\nOpen questions: none\nVerification case intent: contract conformance\nCheck families: conformance\nLineage/checkpoint expectations: view — owner\nAcceptance rules: named acceptance\nPaired review: yes\nReviewer: review\nFinding: none\n", encoding="utf-8")
    assert validate_stage(fixture, "outcome") == ["disposition"]


def test_unstructured_success_criterion_is_rejected_by_the_production_validator(tmp_path):
    fixture = tmp_path / "outcome-brief.md"
    fixture.write_text("Consumer outcome: value\nSuccess signals: feels trustworthy\nSuccess criteria: stakeholders feel it is good\nScope: boundary\nAuthorities: owner\nEvidence: EVD-X\nConstraints: none\nOpen questions: none\nVerification case intent: contract conformance\nCheck families: conformance\nLineage/checkpoint expectations: view — owner\nAcceptance rules: named acceptance\nPaired review: yes\nReviewer: review\nFinding: none\nDisposition: accepted\n", encoding="utf-8")

    assert validate_stage(fixture, "outcome") == ["success criteria must be canonical JSON"]


def test_readable_outcome_rejects_placeholder_authority_and_checkpoint_owner(tmp_path):
    fixture = tmp_path / "outcome-brief.md"
    fixture.write_text(
        f"Consumer outcome: value\nSuccess signals: measurable result\nSuccess criteria: {SUCCESS_CRITERIA}\nScope: boundary\nAuthorities: tbd\nEvidence: evidence-one@v1#digest-evidence; result-validator@v1#digest-validator\nConstraints: none\nOpen questions: none\nVerification case intent: contract conformance\nCheck families: conformance\nLineage/checkpoint expectations: view — unassigned\nAcceptance rules: named acceptance\nPaired review: yes\nReviewer: review\nFinding: none\nDisposition: accepted\n",
        encoding="utf-8",
    )

    failures = validate_stage(fixture, "outcome")
    assert "authorities must name accountable identities, not placeholders" in failures
    assert "lineage/checkpoint expectations must name accountable identities, not placeholders" in failures


def test_readable_outcome_rejects_a_checkpoint_without_an_owner(tmp_path):
    fixture = tmp_path / "outcome-brief.md"
    fixture.write_text(
        f"Consumer outcome: value\nSuccess signals: measurable result\nSuccess criteria: {SUCCESS_CRITERIA}\nScope: boundary\nAuthorities: sponsor\nEvidence: evidence-one@v1#digest-evidence; result-validator@v1#digest-validator\nConstraints: none\nOpen questions: none\nVerification case intent: contract conformance\nCheck families: conformance\nLineage/checkpoint expectations: published-report\nAcceptance rules: named acceptance\nPaired review: yes\nReviewer: review\nFinding: none\nDisposition: accepted\n",
        encoding="utf-8",
    )

    assert "lineage/checkpoint expectations must name an owner for every checkpoint" in validate_stage(
        fixture, "outcome"
    )


def test_readable_delivery_contract_rejects_placeholder_inventories(tmp_path):
    fixture = tmp_path / "implementation-plan.md"
    fixture.write_text(
        "Package inventory: to-be-determined\nDependency inventory: to-be-determined\nGate inventory: to-be-determined\nExclusions: none\nAcceptance: accepted\nEvidence: evidence\nVerification case intent: contract conformance\nCheck families: conformance\nLineage/checkpoint expectations: view — data-owner\nAcceptance rules: named acceptance\nPaired review: yes\nReviewer: review\nFinding: none\nDisposition: accepted\n",
        encoding="utf-8",
    )

    failures = validate_stage(fixture, "implementation_plan")
    assert "package inventory must not contain placeholders" in failures
    assert "dependency inventory must not contain placeholders" in failures
    assert "gate inventory must not contain placeholders" in failures
    assert "package inventory must contain at least one complete package row" in failures


def test_readable_delivery_contract_allows_an_explicit_edge_free_inventory(tmp_path):
    fixture = tmp_path / "implementation-plan.md"
    fixture.write_text(
        "Package inventory: one bounded package below\nDependency inventory: none\nGate inventory: one declared gate below\nExclusions: production connections\nAcceptance: named acceptance\nEvidence: contract@v1#digest-contract\nVerification case intent: contract conformance\nCheck families: conformance\nLineage/checkpoint expectations: consumer-view@data-owner\nAcceptance rules: named acceptance\nPaired review: yes\nReviewer: reviewer\nFinding: none\nDisposition: accepted\n| Package ID | Summary | Owner | Validator | Depends on | Gate ID | Gate requirement |\n| --- | --- | --- | --- | --- | --- | --- |\n| consumer-view | Deliver the view | data-owner | view-validator | none | view-reviewed | Deterministic checks pass |\n",
        encoding="utf-8",
    )

    assert validate_stage(fixture, "implementation_plan") == []


def test_framing_prompt_pair_carries_verification_planning_from_the_first_record():
    required = (
        "verification case intent",
        "check families",
        "lineage/checkpoint expectations",
        "structured executable criterion",
        "validator-specification",
        "required result",
        "acceptance rule",
    )
    for relative in (
        "prompts/generators/frame-platform-outcome.md",
        "prompts/reviewers/frame-platform-outcome-reviewer.md",
        "skills/framing-platform-outcome/SKILL.md",
    ):
        text = (KOINE / relative).read_text(encoding="utf-8").lower()
        assert all(term in text for term in required), relative


def test_intake_template_carries_the_sixteen_intake_sections():
    assert USE_CASE_INTAKE_SECTIONS == INTAKE_SECTIONS

    text = (KOINE / "templates/use-case-intake.md").read_text(encoding="utf-8")
    headings = [line.removeprefix("## ").strip() for line in text.splitlines() if line.startswith("## ")]

    assert headings == list(INTAKE_SECTIONS)


def test_intake_sections_ten_to_sixteen_name_every_standing_condition_once():
    conditions = [key.value.replace("_", " ") for key in CONDITION_KEYS]
    declared = [field for block in INTAKE_SECTIONS[9:] for field in USE_CASE_INTAKE_TEMPLATE_FIELDS[block]]

    assert len(conditions) == 43
    assert [declared.count(name) for name in conditions] == [1] * 43


def test_an_invented_intake_field_reddens_the_projection_validator(tmp_path):
    projection = tmp_path / "koine"
    shutil.copytree(KOINE, projection)
    template = projection / "templates" / "use-case-intake.md"
    template.write_text(
        template.read_text(encoding="utf-8").replace(
            "- **Consumer:**", "- **Consumer:**\n- **Invented field:**", 1
        ),
        encoding="utf-8",
    )

    assert validate_koine_projections(projection) == {
        "templates/use-case-intake.md": [
            "1. Outcome and consumer: unexpected use-case fields: invented field"
        ]
    }


def test_intake_generator_prompt_states_every_required_intake_rule():
    text = (KOINE / "prompts/generators/intake-use-case.md").read_text(encoding="utf-8").lower()

    for statement in INTAKE_GENERATOR_STATEMENTS:
        assert statement in text, statement


def test_intake_reviewer_prompt_lists_its_checks_and_stays_advisory():
    text = (KOINE / "prompts/reviewers/intake-use-case-reviewer.md").read_text(encoding="utf-8").lower()

    assert "your findings are advice, never a gate" in text
    assert "no parser" in text
    for check in ("provenance", "coverage", "gaps", "conditions", "mode", "synthetic"):
        assert check in text, check


def test_intake_method_files_carry_the_artefact_classes_and_the_readiness_loop():
    artefact_first = (KOINE / "method/artefact-first-intake.md").read_text(encoding="utf-8").lower()
    readiness = (KOINE / "method/intent-readiness.md").read_text(encoding="utf-8").lower()

    for artefact_class in INTAKE_ARTEFACT_CLASSES:
        assert artefact_class in artefact_first, artefact_class
    assert "no parser" in artefact_first
    for step in READINESS_LOOP_STEPS:
        assert step in readiness, step
    assert "never blocks a use case as a whole" in readiness


def test_greenfield_discovery_is_a_first_class_adoption_route():
    repository = Path(__file__).parents[2]
    catalogue = (repository / "SKILL-CATALOGUE.md").read_text(encoding="utf-8")
    adoption = (repository / "ADOPTION-GUIDE.md").read_text(encoding="utf-8").lower()

    assert "discovering-greenfield-capabilities" in catalogue
    assert "capability-discovery" in adoption
    assert "do not simply skip discovery" in adoption
