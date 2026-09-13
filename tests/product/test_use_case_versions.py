"""Cutting a version over chosen spans, and the record of the person who takes it."""
# evorthon-verifies: EVD-README-048
# evorthon-verifies: EVD-README-047
# evorthon-verifies: EVD-README-038
# evorthon-verifies: EVD-README-010
import ast
from pathlib import Path

import pytest

from evorthon_data.engagement import (
    AcceptanceRecord,
    CaseEvidence,
    DecisionKind,
    DecisionOutcome,
    EngagementError,
    ReferenceKind,
    ScenarioResult,
    UseCase,
    UseCaseError,
    VersionError,
    cut_version,
    evidence_provenance_summary,
    record_acceptance,
)
from evorthon_data.engagement import versions as module
from evorthon_data.engagement.use_case import Version
from evorthon_data.engagement.versions import EVIDENCE_REFERENCE_KINDS, RefusalReason
from evorthon_data.verification.domain.contracts import (
    AssuranceDeclaration,
    AssuranceLevel,
    CanonicalisationDeclaration,
    ComparisonPolicy,
    ContextIdentity,
    DatasetProvenance,
    DatasetRole,
    DiagnosticStrength,
    EvidenceProvenance,
    ExpectedOutput,
    ExpectedOutputOrigin,
    FrozenDataset,
    Identity,
    LineageDefinition,
    OutputLineageBinding,
    SyntheticProvenance,
    VerificationCase,
    VerificationMode,
    VerificationStatus,
)

from test_use_case_aggregate import (
    answered,
    chained_use_case,
    grain,
    human,
    model,
    package,
    projection,
    reference,
    scenario,
    schema,
)


MODULE_SOURCE = Path(module.__file__).read_text(encoding="utf-8")
# One scenario case at two versions: the first judged on generated evidence, the
# second on evidence obtained from the estate.
GENERATED_CASE = Identity(identifier="case-normal-day", version="v1", digest="digest-case-day-v1")
REAL_CASE = Identity(identifier="case-normal-day", version="v2", digest="digest-case-day-v2")
DISPOSITION = "1 of 2 segments buildable; 1 built on labelled fallbacks"
# How the three readings rank, weakest first. The order is this file's own, so a
# claim that one record reads higher than another is checked here and not by the
# module under test.
READING_ORDER = (EvidenceProvenance.SYNTHETIC, EvidenceProvenance.MIXED, EvidenceProvenance.REAL)
# The words the lifecycle and the availability of a dataset are recorded in. A
# refusal explains an integrity fault and names none of them.
STATE_WORDS = frozenset(
    {
        "opened",
        "verified",
        "accepted",
        "in_service",
        "superseded",
        "obtained",
        "obtainable_by",
        "unobtainable",
        "synthetic_filled",
    }
)


# --- fixtures ----------------------------------------------------------------


def result_reference(case: Identity):
    return reference(ReferenceKind.VERIFICATION_RESULT, f"result-{case.identifier}-{case.version}")


def rationale(identifier: str = "rationale-take-1"):
    return reference(ReferenceKind.DECISION_RATIONALE, identifier)


def version_identity(identifier: str = "uc-order-volume-v1"):
    return reference(ReferenceKind.USE_CASE_VERSION, identifier)


def judged_use_case() -> UseCase:
    """Two spans, one case at two versions with a passing result each, one condition."""
    subject = chained_use_case()
    for case in (GENERATED_CASE, REAL_CASE):
        subject = subject.record_scenario(scenario(case=case))
        subject = subject.record_scenario_result(
            ScenarioResult(case=case, result=result_reference(case), status=VerificationStatus.PASS)
        )
    return subject.record_condition(answered())


def canonicalisation() -> CanonicalisationDeclaration:
    return CanonicalisationDeclaration(
        canonicalisation_id="daily-orders",
        version="v1",
        unicode_normalisation="NFC",
        null_representation="empty",
        decimal_scale=2,
        timestamp_precision="second",
        timezone="UTC",
        signed_zero_representation="unsigned",
        non_finite_number_policy="refused",
    )


def frozen_dataset(declared: DatasetProvenance) -> FrozenDataset:
    return FrozenDataset(
        dataset_id="order-extract",
        version="v1",
        role=DatasetRole.INPUT,
        provenance=declared,
        synthetic_provenance=(
            SyntheticProvenance(
                generator_id="order-generator",
                generator_version="v1",
                seed="17",
                constraints_digest="digest-constraints",
                constrained_by=(),
            )
            if declared is DatasetProvenance.SYNTHETIC
            else None
        ),
        content_digest="digest-order-extract",
        schema=schema(),
        grain=grain(),
        canonicalisation=canonicalisation(),
        row_count=12,
        approved_summary="settled orders for one day",
    )


def expected_output(declared: DatasetProvenance) -> ExpectedOutput:
    return ExpectedOutput(
        output_id="daily-order-report",
        version="v1",
        origin=(
            ExpectedOutputOrigin.SYNTHETIC_DERIVATION
            if declared is DatasetProvenance.SYNTHETIC
            else ExpectedOutputOrigin.MODERNISATION_CAPTURE
        ),
        provenance=declared,
        content_digest="digest-expected",
        schema=schema(),
        grain=grain(),
        canonicalisation=canonicalisation(),
        row_count=12,
        format_digest="digest-format",
        approved_summary="the expected daily report",
    )


def verification_case(case: Identity, declared: DatasetProvenance) -> VerificationCase:
    """One case whose frozen parts all carry the declared provenance."""
    return VerificationCase(
        case_id=case.identifier,
        version=case.version,
        mode=VerificationMode.MODERNISATION,
        frozen_datasets=(frozen_dataset(declared),),
        expected_outputs=(expected_output(declared),),
        context=ContextIdentity(
            "context", "v1", "digest-context", "2026-09-08T09:00:00Z", "22:00", "UTC"
        ),
        comparison_policy=ComparisonPolicy("policy", "v1", "digest-policy", (), (), (), ()),
        lineage=LineageDefinition(
            "lineage", "v1", (), (OutputLineageBinding("daily-order-report", None),)
        ),
        assurance=AssuranceDeclaration("assurance", "v1", AssuranceLevel.DECLARED, (), ()),
        diagnostic_strength=DiagnosticStrength.OUTPUT_ONLY,
    )


def case_reading(case: Identity, declared: DatasetProvenance) -> CaseEvidence:
    """Read one case exactly as the verification domain reads it."""
    return CaseEvidence(
        case=case, evidence_provenance=verification_case(case, declared).evidence_provenance
    )


GENERATED_READING = case_reading(GENERATED_CASE, DatasetProvenance.SYNTHETIC)
REAL_READING = case_reading(REAL_CASE, DatasetProvenance.REAL)


def first_cut(subject: UseCase | None = None) -> tuple[UseCase, Version]:
    """One span of two, judged on the generated case, cut on the first projection."""
    return cut_version(
        subject if subject is not None else judged_use_case(),
        version_identity(),
        ("settled-orders",),
        projection("projection-cut-1"),
        scenario_case_versions=(GENERATED_CASE,),
        packages=(package(),),
        evidence=(result_reference(GENERATED_CASE),),
        suggested_disposition=DISPOSITION,
    )


def second_cut(subject: UseCase) -> tuple[UseCase, Version]:
    """Both spans, judged on the case at the version the estate data reached."""
    return cut_version(
        subject,
        version_identity("uc-order-volume-v2"),
        ("settled-orders", "daily-order-report"),
        projection("projection-cut-2"),
        scenario_case_versions=(REAL_CASE,),
        packages=(package(),),
        evidence=(result_reference(REAL_CASE),),
        suggested_disposition="2 of 2 segments buildable; 0 built on labelled fallbacks",
    )


def taken(
    subject: UseCase,
    version: Version,
    readings: tuple[CaseEvidence, ...],
    decision_id: str = "take-1",
    decided_by=None,
) -> AcceptanceRecord:
    return record_acceptance(
        subject,
        version,
        decision_id=decision_id,
        decided_by=decided_by if decided_by is not None else human(),
        rationale=rationale(),
        cases=readings,
    )


# --- the cut -----------------------------------------------------------------


def test_a_cut_stores_the_projection_digest_and_the_disposition_exactly_as_given():
    subject, version = first_cut()

    assert isinstance(version, Version)
    assert version.readiness_projection == projection("projection-cut-1")
    assert version.readiness_digest == "digest-projection-cut-1"
    assert version.readiness_projection.kind is ReferenceKind.READINESS_PROJECTION
    assert version.suggested_disposition == DISPOSITION
    assert version.suggested_disposition.isascii()
    assert version.scenario_case_versions == (GENERATED_CASE,)
    assert version.packages == (package(),)


def test_a_cut_version_is_recorded_on_the_use_case_and_the_record_keeps_it():
    before = judged_use_case()

    subject, version = first_cut(before)

    assert subject.versions == (version,)
    assert subject.current_version is version
    assert subject.revision == before.revision + 1
    assert before.versions == ()


def test_a_cut_names_the_outputs_its_spans_reach_and_the_spans_left_outside():
    _, narrow = first_cut()
    _, wide = second_cut(judged_use_case())

    assert narrow.covered_segments == ("settled-orders",)
    assert narrow.covered_outputs == ()
    assert narrow.segments_outside == ("daily-order-report",)
    assert wide.covered_segments == ("settled-orders", "daily-order-report")
    assert wide.covered_outputs == ("daily-order-report",)
    assert wide.segments_outside == ()


def test_a_cut_snapshots_the_standing_conditions_as_they_stand():
    subject = judged_use_case()

    _, version = first_cut(subject)

    assert version.conditions == subject.conditions
    assert version.conditions[0].effective_value == "seven years of settled orders"


def test_a_narrowing_version_is_legal_and_leaves_the_wider_one_as_cut():
    wide_use_case, wide = second_cut(judged_use_case())

    narrowed, narrow = cut_version(
        wide_use_case,
        version_identity("uc-order-volume-v3"),
        ("settled-orders",),
        projection("projection-cut-3"),
        scenario_case_versions=(REAL_CASE,),
    )

    assert narrow.covered_segments == ("settled-orders",)
    assert narrow.segments_outside == ("daily-order-report",)
    assert narrowed.versions == (wide, narrow)
    assert narrowed.versions[0].covered_segments == ("settled-orders", "daily-order-report")
    assert narrowed.versions[0].segments_outside == ()


def test_a_span_the_record_does_not_derive_is_refused_by_the_use_case_type():
    with pytest.raises(UseCaseError, match="covers a span the use case does not have"):
        cut_version(
            judged_use_case(), version_identity(), ("no-such-span",), projection("projection-cut-1")
        )


# --- the record --------------------------------------------------------------


def test_a_one_span_version_taken_on_wholly_generated_evidence_carries_that_label():
    subject, version = first_cut()

    record = taken(subject, version, (GENERATED_READING,))

    assert record.evidence_provenance is EvidenceProvenance.SYNTHETIC
    assert record.evidence_provenance.value == "synthetic"
    assert record.cases_read == (GENERATED_CASE,)
    assert record.version == version.identity
    assert version.covered_segments == ("settled-orders",)
    assert record.decision.kind is DecisionKind.VERSION_ACCEPTANCE
    assert record.decision.outcome is DecisionOutcome.ACCEPTED
    assert record.decision.subject is version.identity
    assert record.decision.decided_by == human()


def test_the_record_repeats_the_suggested_disposition_as_advice():
    subject, version = first_cut()

    record = taken(subject, version, (GENERATED_READING,))

    assert record.suggested_disposition == DISPOSITION
    assert record.suggested_disposition == version.suggested_disposition


def test_the_decision_on_the_record_is_the_one_the_use_case_records():
    subject, version = first_cut()
    record = taken(subject, version, (GENERATED_READING,))

    signed = subject.verify(human()).accept(record.decision)

    assert signed.acceptance is record.decision
    assert signed.decisions == (record.decision,)


def test_a_second_version_on_real_evidence_reads_higher_and_the_first_stays_as_taken():
    subject, first = first_cut()
    first_record = taken(subject, first, (GENERATED_READING,))

    later, second = second_cut(subject)
    second_record = taken(later, second, (REAL_READING,), decision_id="take-2")

    assert second_record.evidence_provenance is EvidenceProvenance.REAL
    assert READING_ORDER.index(second_record.evidence_provenance) > READING_ORDER.index(
        first_record.evidence_provenance
    )
    assert first_record.evidence_provenance is EvidenceProvenance.SYNTHETIC
    assert first_record.cases_read == (GENERATED_CASE,)
    assert first_record.suggested_disposition == DISPOSITION
    assert later.versions[0] is first
    assert later.versions[0].covered_segments == ("settled-orders",)


@pytest.mark.parametrize(
    ("cases", "readings"),
    [
        ((GENERATED_CASE,), (GENERATED_READING,)),
        ((REAL_CASE,), (REAL_READING,)),
        ((GENERATED_CASE, REAL_CASE), (GENERATED_READING, REAL_READING)),
    ],
)
def test_the_stored_summary_equals_the_value_those_cases_read(cases, readings):
    subject, version = cut_version(
        judged_use_case(),
        version_identity(),
        ("settled-orders",),
        projection("projection-cut-1"),
        scenario_case_versions=cases,
    )
    declared = {reading.evidence_provenance for reading in readings}
    expected = EvidenceProvenance.MIXED
    if declared == {EvidenceProvenance.REAL}:
        expected = EvidenceProvenance.REAL
    elif declared == {EvidenceProvenance.SYNTHETIC}:
        expected = EvidenceProvenance.SYNTHETIC

    record = taken(subject, version, readings)

    assert record.evidence_provenance is expected
    assert {
        verification_case(GENERATED_CASE, DatasetProvenance.SYNTHETIC).evidence_provenance,
        verification_case(REAL_CASE, DatasetProvenance.REAL).evidence_provenance,
    } == {EvidenceProvenance.SYNTHETIC, EvidenceProvenance.REAL}


def test_a_record_that_cites_no_case_reads_as_mixed_and_is_not_refused():
    subject, version = cut_version(
        judged_use_case(), version_identity(), ("settled-orders",), projection("projection-cut-1")
    )

    record = taken(subject, version, ())

    assert record.cases_read == ()
    assert record.evidence_provenance is EvidenceProvenance.MIXED
    assert evidence_provenance_summary(()) is EvidenceProvenance.MIXED


def test_every_declared_reading_is_summarised_and_none_falls_through_silently():
    assert set(EvidenceProvenance) == {
        EvidenceProvenance.REAL,
        EvidenceProvenance.MIXED,
        EvidenceProvenance.SYNTHETIC,
    }
    assert set(READING_ORDER) == set(EvidenceProvenance)
    for reading in EvidenceProvenance:
        single = (CaseEvidence(case=GENERATED_CASE, evidence_provenance=reading),)
        assert evidence_provenance_summary(single) is reading


# --- only a named human takes a version --------------------------------------


def test_a_model_actor_cannot_take_a_version():
    subject, version = first_cut()

    with pytest.raises(EngagementError, match="only a named human"):
        taken(subject, version, (GENERATED_READING,), decided_by=model())

    assert taken(subject, version, (GENERATED_READING,)).decision.decided_by == human()


def test_the_human_actor_rule_is_the_one_the_engagement_record_owns():
    assert "ActorKind" not in MODULE_SOURCE
    assert "NamedHumanDecision" in MODULE_SOURCE


# --- the module reads no readiness projection --------------------------------


def imported_modules() -> set[str]:
    tree = ast.parse(MODULE_SOURCE)
    names: set[str] = set()
    for statement in ast.walk(tree):
        if isinstance(statement, ast.Import):
            names.update(alias.name for alias in statement.names)
        elif isinstance(statement, ast.ImportFrom):
            names.add("." * statement.level + (statement.module or ""))
    return names


def test_the_module_imports_no_readiness_module():
    assert imported_modules() == {
        "__future__",
        "dataclasses",
        "enum",
        "..verification.domain.contracts",
        ".aggregate",
        ".use_case",
    }
    assert not any("readiness" in name for name in imported_modules())


def test_the_shipped_text_is_plain_and_carries_no_work_narrative():
    assert MODULE_SOURCE.isascii()
    for narrative in ("TODO", "FIXME", "for now", "temporarily"):
        assert narrative not in MODULE_SOURCE


# --- every refusal is an integrity refusal -----------------------------------


def unheld_version() -> Version:
    return second_cut(judged_use_case())[1]


def wrong_summary() -> AcceptanceRecord:
    subject, version = first_cut()
    record = taken(subject, version, (GENERATED_READING,))
    return AcceptanceRecord(
        decision=record.decision,
        version=record.version,
        cases=record.cases,
        evidence_provenance=EvidenceProvenance.REAL,
    )


def another_version_on_the_record() -> AcceptanceRecord:
    subject, version = first_cut()
    record = taken(subject, version, (GENERATED_READING,))
    return AcceptanceRecord(
        decision=record.decision,
        version=version_identity("uc-order-volume-v9"),
        cases=record.cases,
        evidence_provenance=record.evidence_provenance,
    )


def repeated_case_on_the_record() -> AcceptanceRecord:
    subject, version = first_cut()
    record = taken(subject, version, (GENERATED_READING,))
    return AcceptanceRecord(
        decision=record.decision,
        version=record.version,
        cases=(GENERATED_READING, GENERATED_READING),
        evidence_provenance=record.evidence_provenance,
    )


REFUSALS = (
    (
        "a cut needs a use case",
        lambda: cut_version(
            "not a record", version_identity(), ("settled-orders",), projection("projection-cut-1")
        ),
        RefusalReason.INVALID_INPUT,
    ),
    (
        "a cut needs the spans in a tuple",
        lambda: cut_version(
            judged_use_case(), version_identity(), ["settled-orders"], projection("projection-cut-1")
        ),
        RefusalReason.INVALID_INPUT,
    ),
    (
        "evidence names a result or a build artefact",
        lambda: cut_version(
            judged_use_case(),
            version_identity(),
            ("settled-orders",),
            projection("projection-cut-1"),
            evidence=(package(),),
        ),
        RefusalReason.INVALID_INPUT,
    ),
    (
        "a record and its decision name one version",
        another_version_on_the_record,
        RefusalReason.INVALID_INPUT,
    ),
    (
        "a case reading outside the declared vocabulary",
        lambda: CaseEvidence(case=GENERATED_CASE, evidence_provenance=DatasetProvenance.DERIVED),
        RefusalReason.UNDECLARED_REPRESENTATION,
    ),
    (
        "a summary outside the declared vocabulary",
        lambda: AcceptanceRecord(
            decision=taken(*first_cut(), (GENERATED_READING,)).decision,
            version=version_identity(),
            cases=(GENERATED_READING,),
            evidence_provenance="synthetic",
        ),
        RefusalReason.UNDECLARED_REPRESENTATION,
    ),
    (
        "a version the use case does not hold",
        lambda: taken(judged_use_case(), unheld_version(), ()),
        RefusalReason.UNKNOWN_VERSION,
    ),
    (
        "a case the version does not name",
        lambda: taken(*first_cut(), (REAL_READING,)),
        RefusalReason.UNKNOWN_CASE_IDENTITY,
    ),
    (
        "a result the record does not hold",
        lambda: cut_version(
            judged_use_case(),
            version_identity(),
            ("settled-orders",),
            projection("projection-cut-1"),
            evidence=(reference(ReferenceKind.VERIFICATION_RESULT, "result-never-run"),),
        ),
        RefusalReason.CONTRADICTORY_EVIDENCE,
    ),
    (
        "one evidence identity named twice",
        lambda: cut_version(
            judged_use_case(),
            version_identity(),
            ("settled-orders",),
            projection("projection-cut-1"),
            evidence=(result_reference(GENERATED_CASE), result_reference(GENERATED_CASE)),
        ),
        RefusalReason.CONTRADICTORY_EVIDENCE,
    ),
    ("one case read twice", repeated_case_on_the_record, RefusalReason.CONTRADICTORY_EVIDENCE),
    ("a summary the cases do not read", wrong_summary, RefusalReason.CONTRADICTORY_SUMMARY),
    (
        "a case the version names and the record leaves unread",
        lambda: taken(*first_cut(), ()),
        RefusalReason.CONTRADICTORY_SUMMARY,
    ),
)


def test_every_refusal_reason_is_an_integrity_reason():
    assert {reason.value for reason in RefusalReason} == {
        "invalid-input",
        "undeclared-representation",
        "unknown-version",
        "unknown-case-identity",
        "contradictory-evidence",
        "contradictory-summary",
    }
    advisory = {"provenance", "assurance", "synthetic", "readiness", "policy", "gap", "quality"}
    for reason in RefusalReason:
        assert not set(reason.value.split("-")) & advisory


def test_every_refusal_reason_has_a_proof_that_fires():
    assert {reason for _, _, reason in REFUSALS} == set(RefusalReason)


@pytest.mark.parametrize(
    ("case", "build", "reason"), REFUSALS, ids=[case for case, _, _ in REFUSALS]
)
def test_each_refusal_fires_on_the_offending_input(case, build, reason):
    with pytest.raises(VersionError) as refusal:
        build()

    assert refusal.value.reason is reason
    assert isinstance(refusal.value, EngagementError)


def test_the_well_formed_cut_and_record_are_not_refused():
    subject, version = first_cut()

    record = taken(subject, version, (GENERATED_READING,))

    assert subject.current_version is version
    assert record.evidence_provenance is EvidenceProvenance.SYNTHETIC
    assert EVIDENCE_REFERENCE_KINDS == {
        ReferenceKind.VERIFICATION_RESULT,
        ReferenceKind.BUILD_EVIDENCE,
    }


def test_no_refusal_names_a_lifecycle_or_availability_state():
    for _, build, _ in REFUSALS:
        with pytest.raises(VersionError) as refusal:
            build()
        words = set(str(refusal.value).replace(",", " ").replace(":", " ").split())
        assert not words & STATE_WORDS
