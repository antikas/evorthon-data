"""The customer service reporting example, executed end to end on frozen fixtures.

One command runs this whole proof:

    python scripts/run_tests.py --lane fast tests/product/test_proof_customer_service.py

The modernisation example is in
``examples/modernisation/customer-service-reporting``.
Its frozen material is in
``tests/fixtures/proofs/customer-service-reporting``: the declared inputs, the
reference and lookup datasets, the two approved daily publications, the
declared lineage, and the outputs of a candidate that carries one deliberate
defect at a time. This module drives the one supported application route over
that material, on the injected fakes, and reads back what each stage decided.

Five defects are injected, one at a time, each in its own scratch repository: a
repeated grain key, a dropped population, a daily total that moves while every
row stays inside its declared tolerance, a carried-back effective date and a
resolution rate rounded at a place the declared scale does not carry. For each
one the proof asserts the fault class the product deterministically reports,
the disclosure decision the policy made, and the diagnostic strength the packet
supports. The aggregate-only divergence decides no class: it reports unknown
and its packet is withheld. The fault stays open and acceptance is recorded
as not reached.

The use case runs as two versions on one record. The first cuts one segment on
wholly synthetic evidence and is accepted with the synthetic label on its
acceptance record; the second cuts every segment on the captured publications
and is accepted beside the first on the higher provenance, with the record's
lifecycle moved once and the first version and its acceptance left exactly as
they were taken. Both coverage statements and both evidence provenances are
read back off that one record. Every byte of every fixture is invented: the
provenance a case declares is the engagement's own declaration about the class
of its evidence, and never a claim that any of this material came from a live
system.

The proof uses the product's stages, fakes, scripted transport and seeded
generator. The segment generation stage is drafted from the shape the
declaration-draft proof owns and emitted onto the estate the generation proof
owns. Every identity inside both is
this example's, so the records that stage writes describe the daily service
report and no other product.

The public boundary. The fixture root declares every file it holds. Material
declared for projection carries a deterministic seed or a named hand author,
its licence and its source; the one confidential-class sample whose provenance
cannot be resolved is declared as withheld, is never read as data, and is kept
out of the projection by its own manifest disposition. The export gates a
candidate on the declaration before it writes anything, and the exclusion is
proved here as well over a scratch copy taken by the rule and through the
disposition the projection gives that path.
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from evorthon_data import composition, lifecycle
from evorthon_data.delivery import FixtureSeed
from evorthon_data.verification.core.canonical import (
    CanonicalisationRefusal,
    RefusalReason as CanonicalisationRefusalReason,
    dataset_digest,
    record_digest,
)
from evorthon_data.verification.core.reconciliation import (
    EFFECTIVE_TIME_ROLE,
    CandidateObservation,
    ExpectedMaterial,
)
from evorthon_data.verification.domain.contracts import (
    ActualOutput,
    AdviserConfidence,
    AggregateControl,
    AssuranceDeclaration,
    AssuranceLevel,
    CanonicalisationDeclaration,
    Checkpoint,
    ComparisonDeclaration,
    ComparisonDimension,
    ComparisonPolicy,
    ContextIdentity,
    DatasetProvenance,
    DatasetRole,
    DiagnosticStrength,
    EvidenceReference,
    ExpectedOutput,
    ExpectedOutputOrigin,
    GrainDeclaration,
    Identity,
    LineageDefinition,
    NullPlacement,
    OrderingDeclaration,
    OrderingField,
    OutputLineageBinding,
    ParityClause,
    SchemaDeclaration,
    SchemaField,
    SchemaValueType,
    SortDirection,
    ToleranceDeclaration,
    VerificationCase,
    VerificationMode,
    WarningBandDeclaration,
)
from evorthon_data.verification.enforcement.validation import inspect_verification_case

import declaration_draft_support as draft_support  # noqa: E402
import proof_lifecycle as harness  # noqa: E402
import test_autobuild_route as campaign_fixture  # noqa: E402
import test_ergasterion_route as generation_fixture  # noqa: E402
import test_koine_session as koine_fixture  # noqa: E402
import test_pinax_projection as tracker_fixture  # noqa: E402

ROOT = Path(__file__).parents[2]
CONTRACT_SOURCES = str(ROOT / "tests/verification")
if CONTRACT_SOURCES not in sys.path:
    sys.path.insert(0, CONTRACT_SOURCES)

import test_intake_workflow as intake_fixture  # noqa: E402

PROOF = "customer-service-reporting"

# --- what the engagement is called --------------------------------------------

ENGAGEMENT = "eng-customer-service-reporting"
USE_CASE = "uc-daily-service-report"
SESSION = "session-customer-service-proof"
CASE = "case-normal-business-day"
CASE_IDENTITY = f"{CASE}:v1:digest-{CASE}"
RESULT_IDENTITY = f"result-{CASE}:v1:digest-result-{CASE}"
DAY_ONE = "service-report-2026-09-01"
DAY_TWO = "service-report-2026-09-02"
PUBLICATIONS = (DAY_ONE, DAY_TWO)
STEP = "reconciled-service-cases"
INPUT_DATASET = "service-case-extract"
REFERENCE_DATASET = "service-channel-reference"
LOOKUP_DATASET = "service-team-lookup"
ARTEFACT = "service-case-dictionary"
POSITION = "section=target output;line=4"
PROVENANCE = f"{ARTEFACT}:v1:digest-{ARTEFACT}:intake-coworker:model:extracted:{POSITION}"
AUTHORITY = "service-acceptance-authority"
AUTHORITY_IDENTITY = f"{AUTHORITY}:v1:digest-{AUTHORITY}"
HUMAN = f"{AUTHORITY}:human"
DECIDED_BY = f"{AUTHORITY_IDENTITY}:human"
EVIDENCE_ADAPTER = "held-service-evidence"
EVIDENCE_DIRECTORY = "environment-owned-service-material"
CASE_DOCUMENT = harness.case_document(ENGAGEMENT)
RATIONALE_DOCUMENT = harness.rationale_document(ENGAGEMENT)
ADVICE_DOCUMENT = harness.advice_document(ENGAGEMENT)

# --- the declared shape of a daily publication ---------------------------------

BUSINESS_DATE = "business-date"
CASE_REFERENCE = "case-reference"
EFFECTIVE_FROM = "effective-from"
HANDLED_MINUTES = "handled-minutes"
RESOLUTION_RATE = "resolution-rate"
RECORD_STATE = "record-state"
MINUTES_SCALE = 2
RATE_SCALE = 4
CANONICAL_SCALE = 4

CONTEXT = ContextIdentity(
    "service-report-context",
    "v1",
    "sha256:service-report-context",
    "2026-09-02T09:00:00Z",
    "09:00",
    "UTC",
)
CANONICALISATION = CanonicalisationDeclaration(
    "service-report-canonicalisation",
    "v1",
    "NFC",
    "json-null",
    CANONICAL_SCALE,
    "milliseconds",
    "UTC",
    "positive-zero",
    "reject",
)
# Every comparison class the shipped engine implements for a published table,
# except the replay metadata a case with no declared replay never carries.
DIMENSIONS = tuple(
    dimension
    for dimension in ComparisonDimension
    if dimension is not ComparisonDimension.REPLAY_METADATA
)
# The classes the five deliberate defects are expected to be read as, the
# decision the disclosure policy is expected to make about each packet, and the
# diagnostic strength the declared lineage supports.
DISCLOSED = "disclose"
EXPECTED_FAULTS = {
    "key": ("duplicate-join-cardinality", DISCLOSED, "low"),
    "population": ("missing-population", DISCLOSED, "low"),
    "effective-date": ("temporal-effective-date", DISCLOSED, "low"),
    "calculation": ("calculation-precision-rounding", DISCLOSED, "low"),
    "aggregate": ("unknown", "withhold-unknown", None),
}
DISCLOSED_DEFECTS = tuple(
    name for name, (_, decision, _) in EXPECTED_FAULTS.items() if decision == DISCLOSED
)
WITHHELD_DEFECT = "aggregate"
CORRECTED = "corrected"


def schema() -> SchemaDeclaration:
    return SchemaDeclaration(
        schema_id="service-report-schema",
        version="v1",
        fields=(
            SchemaField(BUSINESS_DATE, SchemaValueType.DATE, False, "partition-date", None, None),
            SchemaField(CASE_REFERENCE, SchemaValueType.STRING, False, "business-key", None, None),
            SchemaField(EFFECTIVE_FROM, SchemaValueType.DATE, False, EFFECTIVE_TIME_ROLE, None, None),
            SchemaField(HANDLED_MINUTES, SchemaValueType.DECIMAL, False, "measure", 18, MINUTES_SCALE),
            SchemaField(RESOLUTION_RATE, SchemaValueType.DECIMAL, False, "measure", 9, RATE_SCALE),
            SchemaField(RECORD_STATE, SchemaValueType.STRING, False, "publication-state", None, None),
        ),
        format_name="csv-rfc4180",
    )


FORMAT_DIGEST = record_digest(schema())


def grain() -> GrainDeclaration:
    return GrainDeclaration(
        grain_id="one-row-per-case-day",
        version="v1",
        key_fields=(BUSINESS_DATE, CASE_REFERENCE),
        population_description="one row per settled service case on the published business day",
        duplicate_keys_permitted=False,
    )


def ordering() -> OrderingDeclaration:
    return OrderingDeclaration(
        "service-report-order",
        "v1",
        (
            OrderingField(BUSINESS_DATE, SortDirection.ASCENDING, NullPlacement.LAST),
            OrderingField(CASE_REFERENCE, SortDirection.ASCENDING, NullPlacement.LAST),
        ),
        (),
    )


def aggregate_control(output_id: str) -> AggregateControl:
    return AggregateControl(
        f"handled-minutes-total-{output_id}",
        "v1",
        "sum",
        HANDLED_MINUTES,
        "handled-minutes-total",
        (BUSINESS_DATE,),
        "exclude-null",
        "half-even",
    )


def clause_id(output_id: str) -> str:
    return f"parity-{output_id}"


def tolerances() -> tuple[ToleranceDeclaration, ...]:
    """What the case permits: a handling time may move a little, a rate may not."""
    clauses = tuple(clause_id(output_id) for output_id in PUBLICATIONS)
    return (
        ToleranceDeclaration(
            "handled-minutes-tolerance",
            "v1",
            clauses,
            (ComparisonDimension.VALUE, ComparisonDimension.CALCULATION),
            (HANDLED_MINUTES,),
            "absolute-difference",
            "0.0000",
            "0.0500",
            "minutes",
            "half-even",
        ),
        ToleranceDeclaration(
            "resolution-rate-tolerance",
            "v1",
            clauses,
            (ComparisonDimension.VALUE, ComparisonDimension.CALCULATION),
            (RESOLUTION_RATE,),
            "absolute-difference",
            "0.0000",
            "0.0000",
            "rate",
            "half-even",
        ),
        ToleranceDeclaration(
            "handled-minutes-total-tolerance",
            "v1",
            clauses,
            (ComparisonDimension.AGGREGATE,),
            ("handled-minutes-total",),
            "absolute-difference",
            "0.0000",
            "0.0500",
            "minutes",
            "half-even",
        ),
    )


def warning_bands() -> tuple[WarningBandDeclaration, ...]:
    return (
        WarningBandDeclaration(
            "handled-minutes-warning",
            "v1",
            tuple(clause_id(output_id) for output_id in PUBLICATIONS),
            (ComparisonDimension.VALUE,),
            (HANDLED_MINUTES,),
            "absolute-difference",
            "0.0100",
            "0.0500",
            "minutes",
        ),
    )


def evidence(name: str) -> EvidenceReference:
    return EvidenceReference(name, "v1", f"sha256:{name}", f"approved {name}")


def identity(name: str) -> Identity:
    return Identity(identifier=name, version="v1", digest=f"sha256:{name}")


# --- the frozen material, read from the fixture root ---------------------------


def fixtures() -> harness.ProofFixtures:
    return harness.ProofFixtures(PROOF)


def typed_row(row) -> dict:
    """Read one written publication row into the value types the schema declares."""
    return {
        BUSINESS_DATE: date.fromisoformat(row[BUSINESS_DATE]),
        CASE_REFERENCE: row[CASE_REFERENCE],
        EFFECTIVE_FROM: date.fromisoformat(row[EFFECTIVE_FROM]),
        HANDLED_MINUTES: Decimal(row[HANDLED_MINUTES]),
        RESOLUTION_RATE: Decimal(row[RESOLUTION_RATE]),
        RECORD_STATE: row[RECORD_STATE],
    }


def publications(held: harness.ProofFixtures) -> dict[str, tuple]:
    """The two approved daily publications, by the output each one answers for."""
    return {
        document["output"]: tuple(typed_row(row) for row in document["rows"])
        for document in (
            held.read("declared/expected/publication-day-one.json"),
            held.read("declared/expected/publication-day-two.json"),
        )
    }


def candidate_rows(held: harness.ProofFixtures, name: str) -> dict[str, tuple]:
    """One candidate's declared outputs, by the output each one answers for."""
    document = held.read(f"declared/candidate/{name}.json")
    return {
        entry["output"]: tuple(typed_row(row) for row in entry["rows"])
        for entry in document["outputs"]
    }


def frozen_datasets(held: harness.ProofFixtures, *, captured: bool):
    """The datasets the case freezes, declared as the run they were taken from.

    A synthetic run freezes what the shipped seeded generator produced and says
    so. A captured run declares the same shape as the modernisation capture of
    the estate it replaces. Every row behind both is invented.
    """
    declared = (
        ("declared/inputs/service-case-extract.json", DatasetRole.INPUT),
        ("declared/reference/service-channel-reference.json", DatasetRole.REFERENCE),
        ("declared/reference/service-team-lookup.json", DatasetRole.ENRICHMENT),
    )
    datasets = []
    for name, role in declared:
        generated = held.dataset(name)
        dataset = generated.dataset
        datasets.append(
            replace(
                dataset,
                role=role,
                provenance=DatasetProvenance.REAL if captured else DatasetProvenance.SYNTHETIC,
                synthetic_provenance=None if captured else dataset.synthetic_provenance,
            )
        )
    return tuple(datasets)


def expected_output(output_id: str, rows, *, captured: bool) -> ExpectedOutput:
    return ExpectedOutput(
        output_id=output_id,
        version="v1",
        origin=(
            ExpectedOutputOrigin.MODERNISATION_CAPTURE
            if captured
            else ExpectedOutputOrigin.SYNTHETIC_DERIVATION
        ),
        provenance=DatasetProvenance.REAL if captured else DatasetProvenance.SYNTHETIC,
        content_digest=dataset_digest(
            rows,
            schema=schema(),
            grain=grain(),
            canonicalisation=CANONICALISATION,
            ordering=ordering(),
        ),
        schema=schema(),
        grain=grain(),
        canonicalisation=CANONICALISATION,
        row_count=len(rows),
        format_digest=FORMAT_DIGEST,
        approved_summary=f"approved daily service report {output_id}",
    )


def actual_output(output_id: str, rows) -> ActualOutput:
    """The output one candidate declared for one publication.

    A candidate that repeats a key its own grain forbids produces no canonical
    bytes, so the digest it declares is the one its rows would produce if
    repetition were permitted. That is what such a run declares, and the
    comparison reports the repetition itself.
    """
    try:
        content_digest = dataset_digest(
            rows,
            schema=schema(),
            grain=grain(),
            canonicalisation=CANONICALISATION,
            ordering=ordering(),
        )
    except CanonicalisationRefusal as refusal:
        assert refusal.reason is CanonicalisationRefusalReason.DUPLICATE_KEY_NOT_PERMITTED
        content_digest = dataset_digest(
            rows,
            schema=schema(),
            grain=replace(grain(), duplicate_keys_permitted=True),
            canonicalisation=CANONICALISATION,
            ordering=ordering(),
        )
    return ActualOutput(
        output_id=output_id,
        version="v1",
        content_digest=content_digest,
        schema=schema(),
        grain=grain(),
        canonicalisation=CANONICALISATION,
        row_count=len(rows),
        format_digest=FORMAT_DIGEST,
        approved_summary=f"observed daily service report {output_id}",
    )


def lineage(held: harness.ProofFixtures) -> LineageDefinition:
    """The declared lineage of the report, read from the fixture that owns it."""
    document = held.read("declared/lineage/service-report-lineage.json")
    checkpoints = tuple(
        Checkpoint(
            checkpoint_id=entry["checkpoint_id"],
            version="v1",
            parent_ids=tuple(entry["parents"]),
            expected_state=identity(entry["expected_state"]),
            schema=schema(),
            grain=grain(),
            canonicalisation=CANONICALISATION,
            transformation=identity(entry["transformation"]),
            provenance=identity(entry["provenance"]),
            diagnostic_evidence=(evidence(entry["evidence"]),),
            replay=None,
        )
        for entry in document["checkpoints"]
    )
    bindings = tuple(
        OutputLineageBinding(entry["output"], entry["checkpoint"])
        for entry in document["bindings"]
    )
    return LineageDefinition(document["lineage_id"], document["version"], checkpoints, bindings)


def verification_case(held: harness.ProofFixtures, *, captured: bool) -> VerificationCase:
    """The approved case both versions of this use case are verified against."""
    approved = publications(held)
    outputs = tuple(
        expected_output(output_id, approved[output_id], captured=captured)
        for output_id in PUBLICATIONS
    )
    clauses = tuple(
        ParityClause(
            clause_id(output.output_id),
            "v1",
            output.output_id,
            ComparisonDeclaration(
                comparison_id=f"comparison-{output.output_id}",
                version="v1",
                dimensions=DIMENSIONS,
                schema=schema(),
                grain=grain(),
                canonicalisation=CANONICALISATION,
                aggregates=(aggregate_control(output.output_id),),
                ordering=ordering(),
                replay=None,
            ),
            (evidence(f"parity-evidence-{output.output_id}"),),
        )
        for output in outputs
    )
    case = VerificationCase(
        case_id=CASE,
        version="v1",
        mode=VerificationMode.MODERNISATION,
        frozen_datasets=frozen_datasets(held, captured=captured),
        expected_outputs=outputs,
        context=CONTEXT,
        comparison_policy=ComparisonPolicy(
            "service-report-comparison-policy",
            "v1",
            "sha256:service-report-comparison-policy",
            clauses,
            tolerances(),
            (),
            warning_bands(),
        ),
        lineage=lineage(held),
        assurance=AssuranceDeclaration(
            "service-report-assurance", "v1", AssuranceLevel.DECLARED, (), ()
        ),
        diagnostic_strength=DiagnosticStrength.CHECKPOINTED,
    )
    return intake_fixture.with_stored_evidence_digests(case)


# --- one whole run over one scratch repository ---------------------------------


def adapter_name(candidate: str) -> str:
    return f"service-report-candidate-{candidate}"


def material_document(candidate: str) -> str:
    return f"{ENGAGEMENT}/material-{candidate}.json"


def candidates(held: harness.ProofFixtures, names) -> tuple[harness.DeclaredCandidate, ...]:
    declared = []
    for name in names:
        rows = candidate_rows(held, name)
        declared.append(
            harness.DeclaredCandidate(
                adapter=adapter_name(name),
                directory=f"environment-owned-candidate-{name}",
                document=material_document(name),
                observations=tuple(
                    CandidateObservation(
                        output=actual_output(output_id, rows[output_id]),
                        rows=rows[output_id],
                        context=CONTEXT,
                        observed_inputs=(),
                    )
                    for output_id in PUBLICATIONS
                ),
            )
        )
    return tuple(declared)


def seeded(base: Path, held: harness.ProofFixtures, names, *, captured: bool) -> VerificationCase:
    """Lay the whole engagement out: the case, the adapters, the material, the documents."""
    case = verification_case(held, captured=captured)
    approved = publications(held)
    harness.seed_engagement(
        base,
        engagement=ENGAGEMENT,
        case=case,
        evidence=tuple(
            intake_fixture.stored(reference)
            for reference in intake_fixture.declared_evidence(case)
        ),
        evidence_adapter=EVIDENCE_ADAPTER,
        evidence_directory=EVIDENCE_DIRECTORY,
        expected=tuple(
            ExpectedMaterial(output, approved[output.output_id])
            for output in case.expected_outputs
        ),
        candidates=candidates(held, names),
        written=harness.written_value,
    )
    selection = held.read(harness.HUMAN_SELECTION)
    harness.serialized_document(
        base / harness.RECORDS_ROOT / RATIONALE_DOCUMENT,
        EvidenceReference(
            selection["rationale"]["identifier"],
            "v1",
            f"sha256:{selection['rationale']['identifier']}",
            selection["rationale"]["summary"],
        ),
    )
    return case


def declarations(status: str = "pass") -> tuple[tuple[str, dict], ...]:
    """Everything the record holds about this use case, as the record takes it."""
    declared: list[tuple[str, dict]] = [
        (
            "authority",
            {"authority role": "accepting", "authority actor": HUMAN, "provenance": PROVENANCE},
        ),
        (
            "dataset",
            {
                "dataset identity": INPUT_DATASET,
                "dataset role": "input",
                "source system": "service-case-management",
                "delivery mode": "nightly file drop",
                "dataset cadence": "daily",
                "access owner": "service-data-owner:human",
                "classification": "confidential",
                "availability state": "obtained",
                "availability subject": f"{INPUT_DATASET}-2026-09:v1:digest-{INPUT_DATASET}-2026-09",
                "provenance": PROVENANCE,
            },
        ),
        (
            "dataset",
            {
                "dataset identity": REFERENCE_DATASET,
                "dataset role": "reference",
                "source system": "service-channel-catalogue",
                "delivery mode": "weekly export",
                "dataset cadence": "weekly",
                "access owner": "service-data-owner:human",
                "classification": "internal",
                "availability state": "obtained",
                "availability subject": f"{REFERENCE_DATASET}-2026-09:v1:digest-{REFERENCE_DATASET}-2026-09",
                "provenance": PROVENANCE,
            },
        ),
        (
            "dataset",
            {
                "dataset identity": LOOKUP_DATASET,
                "dataset role": "enrichment",
                "source system": "service-rota-register",
                "delivery mode": "weekly export",
                "dataset cadence": "weekly",
                "access owner": "service-data-owner:human",
                "classification": "internal",
                "availability state": "obtained",
                "availability subject": f"{LOOKUP_DATASET}-2026-09:v1:digest-{LOOKUP_DATASET}-2026-09",
                "provenance": PROVENANCE,
            },
        ),
    ]
    for output_id in PUBLICATIONS:
        declared.append(
            (
                "target-output",
                {
                    "output identity": output_id,
                    "output kind": "table",
                    "schema declaration": "service-report-schema:v1:tabular",
                    "schema fields": (
                        f"{CASE_REFERENCE}:string:not-null:::service case key"
                        f";{HANDLED_MINUTES}:decimal:not-null:18:2:handled minutes"
                    ),
                    "grain declaration": (
                        "one-row-per-case-day:v1:unique-keys:settled service cases on the business day"
                    ),
                    "grain keys": CASE_REFERENCE,
                    "output cadence": "daily",
                    "cutoff semantics": "cases settled before the evening cutoff",
                    "effective-time semantics": "effective-dated on the settlement date",
                    "stored name": "DAILY_SERVICE_REPORT",
                    "stored column names": f"{CASE_REFERENCE}:CASE_REFERENCE",
                    "defining specification": "service-report-specification:v1:digest-service-report-specification",
                    "provenance": PROVENANCE,
                },
            )
        )
    declared.append(
        (
            "intermediate-result",
            {
                "step identity": STEP,
                "step description": "service cases reconciled before publication, one row per case",
                "evidence owner": HUMAN,
                "checkpoint candidate": "checkpoint",
                "continuity": "continuity",
                "provenance": PROVENANCE,
            },
        )
    )
    for output_id in PUBLICATIONS:
        declared.append(
            (
                "build-route",
                {
                    "segment identity": output_id,
                    "build route": "engineered",
                    "target shape": "table",
                    "layer": "reporting",
                    "provenance": PROVENANCE,
                },
            )
        )
    declared.extend(
        [
            ("scenario", {"scenario case": CASE_IDENTITY, "provenance": PROVENANCE}),
            (
                "condition",
                {
                    "condition key": "freshness_deadline",
                    "condition state": "declared",
                    "condition value": "before the morning shift",
                    "provenance": PROVENANCE,
                },
            ),
            (
                "intake-artefact",
                {
                    "intake artefact": f"{ARTEFACT}:v1:digest-{ARTEFACT}",
                    "artefact classification": "confidential",
                    "artefact locator": "intake/service-case-dictionary",
                    "provenance": PROVENANCE,
                },
            ),
            (
                "scenario-result",
                {
                    "scenario case": CASE_IDENTITY,
                    "verification result": RESULT_IDENTITY,
                    "verification status": status,
                },
            ),
        ]
    )
    return tuple(declared)


CONFIRMED = (
    (
        "authority",
        {
            "authority role": "evidence_owner",
            "authority actor": "service-evidence-owner:human",
            "authority subject": STEP,
            "provenance": PROVENANCE,
        },
    ),
)


def header_parts() -> tuple[str, ...]:
    return (
        f"{USE_CASE}:v1:digest-{USE_CASE}",
        ENGAGEMENT,
        "modernisation",
        "the customer service operations manager",
        "decide the next day rota from the settled service demand",
        "the manager can staff the rota without the old report",
        "every working day before the morning shift",
        "2026-12-01",
        PROVENANCE,
    )


def intake(status: str = "pass") -> lifecycle.UseCaseIntake:
    return lifecycle.UseCaseIntake(
        header_parts=header_parts(),
        readings=koine_fixture.intake_readings(),
        answers=koine_fixture.bulk_confirmation(),
        authorization=harness.intake_authorization(ENGAGEMENT, SESSION),
        declarations=declarations(status),
        confirmed=CONFIRMED,
    )


# What the generation stage is asked to declare for this engagement. The shape
# of the request is the declaration-draft proof's own, because this proof adds
# nothing to that stage; every identity inside it is this example's, so the
# record the stage writes describes the daily service report and nothing else.
GENERATED_SEGMENT = "daily_service_report"
GENERATED_SOURCE = "service_case_extract"
GENERATED_STEP = "service_case_reconciliation"
GENERATED_DOMAIN = "service"
GENERATED_PRODUCT = "case_extract"
SEED_DOCUMENT = "declared/generation/service-case-extract-seed.csv"
GENERATED_FIELDS = (
    draft_support.schema_field("case_reference"),
    draft_support.schema_field("opened_at", SchemaValueType.TIMESTAMP, nullable=True),
)


# The names the emitted estate carries for this engagement. The estate itself
# is the generation proof's own recorded one, renamed onto this example, so the
# record of a customer service run names a customer service product and the
# shape of an emitted estate keeps its one owner.
GENERATED_NAMES = {
    "settled_positions": GENERATED_SEGMENT,
    "exposure_summary": "service_demand_summary",
    "position_id": "case_reference",
    "booked_at": "opened_at",
    "booked_on": "opened_on",
    "exposure_amount": "handled_minutes",
    "exposure_label": "demand_label",
    "risk": GENERATED_DOMAIN,
}


def generated_estate() -> dict[str, str]:
    """The estate the fake released tool emits, in this engagement's own names."""

    def renamed(value: str) -> str:
        for drafted, named in GENERATED_NAMES.items():
            value = value.replace(drafted, named)
        return value

    return {
        renamed(name): renamed(text)
        for name, text in generation_fixture.recorded_estate().items()
    }


def generated_grain() -> GrainDeclaration:
    return GrainDeclaration(
        grain_id="one-row-per-service-case",
        version="v1",
        key_fields=("case_reference",),
        population_description="settled service cases",
        duplicate_keys_permitted=False,
    )


def declaration_request():
    """The segment declaration this engagement's generation stage is drafted from."""
    read = harness.drafted_provenance(ARTEFACT, POSITION)
    return draft_support.request(
        segment=draft_support.segment(
            segment_id=GENERATED_SEGMENT,
            sources=(GENERATED_SOURCE,),
            passes_through=(GENERATED_STEP,),
            route=draft_support.build_route(
                segment_id=GENERATED_SEGMENT,
                product_domain=GENERATED_DOMAIN,
                provenance=read,
            ),
        ),
        authorities=(
            draft_support.authority(actor=draft_support.human(AUTHORITY), provenance=read),
        ),
        fixture_inputs={
            GENERATED_SOURCE: draft_support.fixture_input(
                relation=GENERATED_SOURCE,
                dataset=replace(
                    draft_support.frozen_dataset(GENERATED_FIELDS, dataset_id=GENERATED_SOURCE),
                    grain=generated_grain(),
                    canonicalisation=replace(
                        draft_support.canonicalisation(),
                        canonicalisation_id="service-report-generation-canonicalisation",
                    ),
                    approved_summary="two invented service cases",
                ),
                pin=draft_support.ProductPin(
                    domain=GENERATED_DOMAIN, product=GENERATED_PRODUCT, major_version=1
                ),
            )
        },
        target_output=draft_support.target_output(
            output_id=GENERATED_SEGMENT,
            schema=draft_support.schema(GENERATED_FIELDS, schema_id=GENERATED_SEGMENT),
            grain=generated_grain(),
            cutoff_semantics="cases settled before the evening cutoff",
            effective_time_semantics="effective-dated on the settlement date",
            provenance=read,
        ),
        intermediate_calculations={
            GENERATED_STEP: (
                draft_support.ProposedCalculatedField(
                    field_id="opened_on",
                    value_type=SchemaValueType.DATE,
                    expression="CAST(opened_at AS DATE)",
                ),
            )
        },
    )


def delivery(repository: Path, held: harness.ProofFixtures) -> lifecycle.SegmentDelivery:
    return lifecycle.SegmentDelivery(
        declaration_request=declaration_request(),
        proposal_reference="service-report-declaration:v1",
        drafted_by="declaration-drafter",
        reviewer="declaration-reviewer:v1:digest-declaration-reviewer",
        disposition="accepted",
        generation_reference="service-report-generation:v1:digest-service-report-generation",
        generation_actor="generation-actor",
        estate_name="daily-service-report",
        profile="use-case-build",
        harness="coding-assistant",
        target_repository=repository,
        seeds=(FixtureSeed(f"{GENERATED_SOURCE}.csv", held.text(SEED_DOCUMENT)),),
        canonicalisation=generation_fixture.CANONICALISATION,
        selections=tuple(
            f"{item['item_id']}:ready:approved"
            for item in campaign_fixture.run_result_payload()["items"]
        ),
    )


def verification(
    held: harness.ProofFixtures,
    candidate: str,
    output_id: str = DAY_TWO,
    corrected: str = CORRECTED,
) -> lifecycle.CaseVerification:
    return harness.case_verification(
        held,
        engagement_id=ENGAGEMENT,
        evidence_adapter=EVIDENCE_ADAPTER,
        adapter_name=adapter_name,
        material_document=material_document,
        candidate=candidate,
        corrected=corrected,
        output_id=output_id,
        adviser_authority=AUTHORITY_IDENTITY,
        decided_by=DECIDED_BY,
    )


def acceptance(covered: tuple[str, ...], reading: str) -> lifecycle.VersionAcceptance:
    version = f"{USE_CASE}-{reading}"
    return lifecycle.VersionAcceptance(
        version_reference=f"{version}:v1:digest-{version}",
        version_identity=version,
        covered_segments=";".join(covered),
        projection_reference=f"readiness-{USE_CASE}:v1",
        decision_identity=f"accept-{reading}",
        decided_by=HUMAN,
        rationale=f"rationale-accept-{reading}:v1:digest-rationale-accept-{reading}",
        scenario_case_versions=CASE_IDENTITY,
        evidence=RESULT_IDENTITY,
        case_readings=f"{CASE_IDENTITY}:{reading}",
    )


SEGMENTS = (STEP, DAY_ONE, DAY_TWO)


def traversed(
    base: Path,
    candidate: str,
    *,
    captured: bool = True,
    covered: tuple[str, ...] = SEGMENTS,
    reading: str = "real",
    declared_status: str = "pass",
    corrected: str = CORRECTED,
):
    """Drive one whole traversal of the route over one scratch repository."""
    base.mkdir(parents=True, exist_ok=True)
    held = fixtures()
    seeded(base, held, (candidate, corrected), captured=captured)
    scripted = held.read(harness.ADVISER_REPLIES)
    hypothesis = scripted["replies"].get(candidate) or next(iter(scripted["replies"].values()))
    fakes = harness.ProofFakes(
        ENGAGEMENT,
        SESSION,
        harness.scripted_reply(
            hypothesis, scripted["assumptions"], AdviserConfidence(scripted["confidence"])
        ),
        generator=generation_fixture.FakeErgasterionRunner(files=generated_estate()),
    )
    record = lifecycle.run_lifecycle(
        repository=base,
        root=harness.RECORDS_ROOT,
        mechanisms=fakes.mechanisms(),
        intake=intake(declared_status),
        tracker=lifecycle.TrackerRoute(
            actor_handle=tracker_fixture.ACTOR, prefix="evd", repository=base
        ),
        delivery=delivery(base, held),
        verification=verification(held, candidate, corrected=corrected),
        acceptance=acceptance(covered, reading),
    )
    return harness.ProofRun(base=base, record=record, fakes=fakes, held=held)


@pytest.fixture(scope="session")
def defect_runs(tmp_path_factory):
    """One traversal per injected defect, driven once and read by every check.

    Each run is a whole traversal of the route over its own scratch
    repository. The same inputs always give the same run, so the checks that
    read one read the same record.
    """
    base = tmp_path_factory.mktemp("defects")
    return {
        name: traversed(
            base / name,
            name,
            declared_status="fail" if name == WITHHELD_DEFECT else "pass",
        )
        for name in sorted(EXPECTED_FAULTS)
    }


# --- the case the whole proof rests on ----------------------------------------


def test_the_approved_case_is_one_the_central_validator_accepts():
    held = fixtures()

    for captured in (True, False):
        assert inspect_verification_case(verification_case(held, captured=captured)).issues == ()


def test_the_frozen_input_is_the_dataset_the_declared_seed_produces():
    harness.confirm_seeded_dataset(fixtures(), "declared/inputs/service-case-extract.json")


# --- every stage, over the whole example --------------------------------------


def test_one_run_drives_every_stage_of_the_route_over_the_example(defect_runs):
    run = defect_runs["population"]

    assert [stage.name for stage in run.record.stages] == list(lifecycle.STAGES)
    assert (run.record.engagement_id, run.record.use_case_id) == (ENGAGEMENT, USE_CASE)
    assert run.stage(lifecycle.CASE_INTAKE)["case"] == CASE
    verified = run.stage(lifecycle.VERIFICATION)
    assert verified["status"] == "fail"
    assert verified["failed outputs"] == DAY_TWO
    # The adviser was asked exactly once, after the two intake rounds and their
    # reviews, and nothing else crossed the egress port.
    assert run.fakes.transport.routes.count(harness.ADVISER_ROUTE) == 1
    decided = run.stage(lifecycle.REMEDIATION)
    assert decided["disposition"] == "accepted"
    assert decided["remedy item"].startswith("evd-")
    assert run.stage(lifecycle.CORRECTED_RERUN)["status"] == "pass"
    assert run.stage(lifecycle.ACCEPTANCE)["version"] == f"{USE_CASE}-real"


def test_every_record_this_run_writes_describes_this_example(defect_runs):
    """The generation stage declares and emits this engagement's own product.

    The declaration request and the estate the fake released tool emits are the
    declaration-draft and generation proofs' own shapes, carrying this
    example's identities, so no record of a customer service run describes
    another engagement's product.
    """
    run = defect_runs["population"]
    generated = run.stage(lifecycle.SEGMENT_GENERATION)
    written = "\n".join(harness.written_records(run.base).values())

    assert generated["generation"] == "service-report-generation"
    assert generated["checkpoints"] == f"{GENERATED_DOMAIN}.{GENERATED_SEGMENT}"
    for drafted in GENERATED_NAMES:
        assert drafted not in written, drafted


@pytest.mark.parametrize("defect", sorted(EXPECTED_FAULTS), ids=sorted(EXPECTED_FAULTS))
def test_every_injected_defect_reports_the_class_and_strength_the_product_decides(
    defect_runs, defect
):
    """Each defect is read as one declared class, with the strength its evidence supports.

    The aggregate-only divergence decides no class of its own: the daily total
    moves while every row stays inside its declared tolerance, so the class is
    unknown, the packet is withheld and nothing the packet observed is
    reported. The fault remains open.
    """
    declared_class, decision, strength = EXPECTED_FAULTS[defect]

    diagnosed = defect_runs[defect].stage(lifecycle.DIAGNOSIS)
    assert diagnosed["fault class"] == declared_class
    assert diagnosed[composition.DISCLOSURE_LABEL] == decision
    if strength is None:
        assert {"confidence", "localisation status", "diagnostic scope"}.isdisjoint(diagnosed)
    else:
        assert diagnosed["confidence"] == strength
        assert diagnosed["localisation status"] == "inferred"
        assert f"output {DAY_TWO}" in diagnosed["diagnostic scope"]


@pytest.mark.parametrize("defect", sorted(DISCLOSED_DEFECTS), ids=sorted(DISCLOSED_DEFECTS))
def test_a_swapped_defect_reddens_the_class_this_proof_asserts(defect_runs, defect):
    """Read one defect's run against every other defect's expected class."""
    others = [name for name in sorted(EXPECTED_FAULTS) if name != defect]

    reported = defect_runs[defect].stage(lifecycle.DIAGNOSIS)["fault class"]

    assert reported == EXPECTED_FAULTS[defect][0]
    assert all(reported != EXPECTED_FAULTS[other][0] for other in others)


def test_a_disclosed_packet_names_the_lineage_the_checkpoints_support(defect_runs):
    """The localisation is the interval the declared checkpoints support, and says so."""
    run = defect_runs["population"]

    diagnosed = run.stage(lifecycle.DIAGNOSIS)
    evidence_stage = run.stage(lifecycle.ACCEPTANCE_EVIDENCE)
    declared = run.held.read("declared/lineage/service-report-lineage.json")
    bound = next(
        entry["checkpoint"] for entry in declared["bindings"] if entry["output"] == DAY_TWO
    )

    assert diagnosed["localisation status"] == "inferred"
    assert "uncovered 1" in diagnosed["diagnostic scope"]
    assert diagnosed["fault id"] in evidence_stage["localisation"]
    assert bound in {checkpoint["checkpoint_id"] for checkpoint in declared["checkpoints"]}


def test_the_advice_the_human_disposes_of_is_the_scripted_reply_this_run_produced(defect_runs):
    """The adviser's hypothesis is recorded as inert text and selected by a named human."""
    run = defect_runs["population"]
    scripted = run.held.read(harness.ADVISER_REPLIES)
    selection = run.held.read(harness.HUMAN_SELECTION)

    advised = run.stage(lifecycle.ADVICE)
    decided = run.stage(lifecycle.REMEDIATION)
    written_advice = json.loads(
        (run.base / harness.RECORDS_ROOT / ADVICE_DOCUMENT).read_text(encoding="ascii")
    )

    assert advised["hypotheses"] == "1"
    assert advised["required authority"] == AUTHORITY
    assert written_advice["record"]["hypotheses"] == [scripted["replies"]["population"]["cause"]]
    assert written_advice["record"]["proposed_fixes"] == [
        scripted["replies"]["population"]["proposed_fix"]
    ]
    assert decided["disposition"] == selection["disposition"]
    assert decided["decided by"] == selection["decided_by"]["identity"] == AUTHORITY
    assert decided["fault"] == advised["fault"]
    # No prose a person or an adviser wrote reaches the record of the run.
    written_out = "\n".join(harness.written_records(run.base).values())
    for value in (
        scripted["replies"]["population"]["cause"],
        scripted["replies"]["population"]["proposed_fix"],
        selection["rationale"]["summary"],
    ):
        assert value not in written_out


def test_a_withheld_packet_leaves_the_fault_open_and_the_acceptance_not_reached(defect_runs):
    run = defect_runs[WITHHELD_DEFECT]

    for name in (lifecycle.ADVICE, lifecycle.REMEDIATION, lifecycle.CORRECTED_RERUN):
        assert run.record.stage(name).value(lifecycle.REACHED_LABEL) == lifecycle.NOT_REACHED
    assert harness.ADVISER_ROUTE not in run.fakes.transport.routes
    assert run.stage(lifecycle.VERIFICATION)["status"] == "fail"
    accepted = run.record.stage(lifecycle.ACCEPTANCE)
    assert accepted.value(lifecycle.REACHED_LABEL) == lifecycle.NOT_REACHED
    assert accepted.value(lifecycle.REASON_LABEL) == lifecycle.UNVERIFIED_SCENARIO.format(
        status="fail"
    )


# --- the corrected work and the regression set ---------------------------------


def test_both_corrected_publications_pass_on_the_corrected_rerun(defect_runs):
    """The corrected candidate reproduces both days, and the regression set says so."""
    run = defect_runs["population"]

    rerun = run.stage(lifecycle.CORRECTED_RERUN)
    assert rerun["status"] == "pass"
    assert rerun["rerun"] == "green"
    assert rerun["regression set"] == lifecycle.LIST_SEPARATOR.join(
        clause_id(output_id) for output_id in PUBLICATIONS
    )
    assert rerun["corrected"] == clause_id(DAY_TWO)
    assert rerun["restored defects"] == composition.NOTHING
    assert rerun["regressions"] == composition.NOTHING
    # The evidence a named human would accept on carries the rerun beside the
    # status of the run that found the fault, which is the one it answers for.
    evidence_stage = run.stage(lifecycle.ACCEPTANCE_EVIDENCE)
    assert evidence_stage["status"] == "fail"
    assert evidence_stage["reruns"].endswith("green")
    assert run.stage(lifecycle.ACCEPTANCE)["state"] == "accepted"


def test_a_restored_defect_reddens_the_corrected_rerun(tmp_path):
    """Rerun the uncorrected candidate and the rerun reports the defect still there.

    This is the same traversal with one thing changed: the candidate the rerun
    runs still carries the defect the decision approved a remedy for. The rerun
    goes red, names the restored defect, corrects nothing, and the acceptance
    is recorded as not reached.
    """
    run = traversed(
        tmp_path / "restored",
        "population",
        corrected="population",
        declared_status="fail",
    )

    rerun = run.stage(lifecycle.CORRECTED_RERUN)
    assert rerun["rerun"] == "red"
    assert rerun["status"] == "fail"
    assert rerun["restored defects"] == clause_id(DAY_TWO)
    assert rerun["corrected"] == composition.NOTHING
    accepted = run.record.stage(lifecycle.ACCEPTANCE)
    assert accepted.value(lifecycle.REACHED_LABEL) == lifecycle.NOT_REACHED


# --- the two versions on one record ----------------------------------------------


def taken_beside(run: harness.ProofRun, *, covered: tuple[str, ...], reading: str):
    """Cut one more version on the record this run holds, and accept it there."""
    return harness.taken_beside(
        run.base,
        engagement_id=ENGAGEMENT,
        use_case_id=USE_CASE,
        taken=acceptance(covered, reading),
        reached=lifecycle.case_facts(
            composition.records_root(run.base, harness.RECORDS_ROOT),
            verification(run.held, "population"),
            status=composition.PASSED,
        ),
    )


def test_the_two_versions_carry_their_coverage_and_their_evidence_provenance(tmp_path):
    """One segment on synthetic evidence first, every segment on captured outputs beside it.

    Both versions stand on one use-case record. The first is cut over one
    segment on wholly synthetic evidence and accepted with that label. The
    engagement then states its case as the captured publications, and the
    second is cut over every segment on the readiness that reading recomputes
    and accepted beside the first. The record's lifecycle moves once, the first
    version and the acceptance it was taken through stand exactly as they were
    taken, and both coverage statements and both evidence provenances are read
    back off that one record.
    """
    run = traversed(
        tmp_path / "one-record",
        "population",
        captured=False,
        covered=(DAY_ONE,),
        reading="synthetic",
    )
    first_cut = run.stage(lifecycle.VERSION_CUT)
    first_accepted = run.stage(lifecycle.ACCEPTANCE)
    first_evidence = run.stage(lifecycle.ACCEPTANCE_EVIDENCE)
    taken = composition.load_use_case(run.base, harness.RECORDS_ROOT, ENGAGEMENT, USE_CASE)[0]
    written = harness.record_text(run.base, ENGAGEMENT, USE_CASE)

    harness.state_case(run.base, ENGAGEMENT, verification_case(run.held, captured=True))
    second_evidence = dict(
        composition.read_acceptance_evidence(
            repository=run.base,
            root=harness.RECORDS_ROOT,
            engagement_id=ENGAGEMENT,
            case_document=CASE_DOCUMENT,
        ).values
    )
    second_cut, second_accepted = taken_beside(run, covered=SEGMENTS, reading="real")

    held = composition.load_use_case(run.base, harness.RECORDS_ROOT, ENGAGEMENT, USE_CASE)[0]
    # One record, two versions, each with the coverage statement its own cut
    # was taken on and the readiness digest that cut was taken over.
    assert [version.identity.identifier for version in held.versions] == [
        first_cut["version"],
        second_cut["version"],
    ]
    assert held.versions[0].covered_segments == (DAY_ONE,)
    assert held.versions[0].covered_outputs == (DAY_ONE,)
    assert sorted(held.versions[0].segments_outside) == sorted((STEP, DAY_TWO))
    assert held.versions[1].covered_segments == SEGMENTS
    assert held.versions[1].segments_outside == ()
    assert held.versions[0].readiness_digest == first_cut["readiness digest"]
    assert held.versions[1].readiness_digest == second_cut["readiness digest"]
    assert held.versions[0].readiness_digest != held.versions[1].readiness_digest
    # Both named acceptances stand on that record, and each says what the
    # evidence behind its own version reads as.
    assert first_accepted["evidence provenance"] == "synthetic"
    assert second_accepted["evidence provenance"] == "real"
    assert [
        entry["case readings"]
        for entry in harness.recorded_acceptances(run.base, ENGAGEMENT, USE_CASE)
    ] == [
        f"{CASE_IDENTITY}:synthetic",
        f"{CASE_IDENTITY}:real",
    ]
    assert [decision.decision_id for decision in held.decisions] == [
        first_accepted["decision"],
        second_accepted["decision"],
    ]
    # The lifecycle moved once, through the first acceptance and no other.
    assert [move.target.value for move in held.transitions] == ["verified", "accepted"]
    assert (held.state.value, second_accepted["state"]) == ("accepted", "accepted")
    # Each acceptance repeats the disposition its own cut was taken on.
    assert first_accepted["suggested disposition"] == first_cut["suggested disposition"]
    assert second_accepted["suggested disposition"] == second_cut["suggested disposition"]
    # The evidence each acceptance rests on says how much of it was generated.
    assert (first_evidence["evidence provenance"], first_evidence["synthetic datasets"]) == (
        "synthetic",
        "3",
    )
    assert (second_evidence["evidence provenance"], second_evidence["synthetic datasets"]) == (
        "real",
        "0",
    )
    # The first version and its acceptance are exactly as they were taken, in
    # the use case the record replays and in the bytes of the record itself.
    assert (held.versions[0], held.decisions[0]) == (taken.versions[0], taken.decisions[0])
    assert harness.record_text(run.base, ENGAGEMENT, USE_CASE).startswith(written)


def test_the_synthetic_version_is_taken_on_a_case_that_declares_every_part_synthetic():
    """Nothing about the first version's evidence is labelled as more than it is."""
    held = fixtures()
    case = verification_case(held, captured=False)

    assert {dataset.provenance for dataset in case.frozen_datasets} == {
        DatasetProvenance.SYNTHETIC
    }
    assert {output.provenance for output in case.expected_outputs} == {
        DatasetProvenance.SYNTHETIC
    }
    assert {output.origin for output in case.expected_outputs} == {
        ExpectedOutputOrigin.SYNTHETIC_DERIVATION
    }


# --- the provenance and privacy gates over this proof's fixtures ---------------


def test_every_fixture_is_declared_with_its_provenance_licence_and_source():
    harness.confirm_declared_material(fixtures())


# The one publication a gate proof takes apart and the negative sample it
# resolves. The four faults themselves, and the finding each one must produce,
# are the harness's, because both proofs are held to the same four.
GATED_FILE = "declared/expected/publication-day-one.json"
NEGATIVE_SAMPLE = "withheld/confidential-case-export.txt"
GATED = {"gated": GATED_FILE, "negative": NEGATIVE_SAMPLE}


@pytest.mark.parametrize("injected", harness.INJECTIONS, ids=harness.INJECTIONS)
def test_an_injected_fixture_reddens_the_provenance_gate(tmp_path, injected):
    """Each way a fixture root can fail its own record is driven red once."""
    findings = harness.injected_gate(fixtures(), tmp_path / "gate", injected, **GATED)

    assert harness.injected_finding(injected, **GATED) in findings


@pytest.mark.deep
@pytest.mark.timeout(300)
def test_the_withheld_sample_is_reported_by_the_boundary_scan_and_never_read(tmp_path):
    """The one confidential-class sample is the only thing a scan of this root reports."""
    harness.confirm_withheld_sample(fixtures(), tmp_path, negative=NEGATIVE_SAMPLE)


@pytest.mark.deep
@pytest.mark.timeout(300)
def test_the_withheld_fixture_reaches_no_public_projection():
    """The exclusion is the disposition the manifest gives that path."""
    harness.confirm_manifest_dispositions(fixtures())


def test_every_fixture_this_proof_ships_is_printable_ascii_with_one_line_ending():
    harness.confirm_printable_ascii(fixtures())


def test_this_proof_reads_every_fixture_the_run_needs_and_nothing_else(defect_runs):
    """What the run opened is exactly the material declared for projection."""
    held = defect_runs["population"].held

    assert set(held.reads) <= set(held.projected())
    assert set(held.reads) == set(held.projected()) - {
        f"declared/candidate/{name}.json"
        for name in EXPECTED_FAULTS
        if name != "population"
    }
# evorthon-verifies: EVD-README-002
# evorthon-verifies: EVD-README-003
# evorthon-verifies: EVD-README-009
# evorthon-verifies: EVD-README-037
