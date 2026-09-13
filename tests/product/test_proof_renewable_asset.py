"""The renewable asset observability example, executed end to end on frozen fixtures.

One command runs this whole proof:

    python scripts/run_tests.py --lane fast tests/product/test_proof_renewable_asset.py

What it proves. The shipped greenfield example under
``examples/greenfield/renewable-asset-observability`` is no longer prose only.
The frozen material of that engagement sits under
``tests/fixtures/proofs/renewable-asset-observability``: the declared input,
reference and enrichment constraints, the two approved golden views, the
declared requirements of the interface, invariant, operational and
delivery-integrity families, the declared lineage, and the outputs of
candidates that carry one deliberate defect at a time. This module drives the
one supported application route over that material, on the injected fakes, and
reads back what each stage decided.

The delivery is answered by five clause families, and one deliberate defect is
injected into each: a published interface version the approved contract does
not name, four observations outside the declared measurement range, a feed run
that did not complete before the declared cutoff, an earlier register snapshot
that left asset codes unmatched, and six capacity factors that move by one unit
in the last declared decimal place. Each one is read back by the family that
owns it and by the status that family decided, and no other family moves.

Only the last of the five is a difference between published rows. That one is
carried through the whole route: the comparison reports the failing view, the
packet is disclosed with the class the product deterministically reports, the
scripted adviser answers, a named human disposes of the advice and the
corrected candidate is rerun green. The other four are answered by the
verification stage and go no further, because a diagnosis answers for an output
a comparison reported as failing and a contract-family failure that is not a
row difference names no such output. That boundary is the honest frontier of
this route rather than a defect, and it is asserted here as the route's own
refusal.

The use case runs as two versions on one record. The first covers one published
view and is accepted; the second covers every segment and is accepted beside
it, with the record's lifecycle moved once and the first version and its
acceptance left exactly as they were taken.

The greenfield boundary. Every approved golden view is authored from the
approved specification and carries the greenfield-specification origin, so no
expected value is taken from a run of any earlier system. The engagement
refuses a parity question at intake, the case refuses an expected value whose
origin is a capture of an old run, and no fixture invents a legacy baseline, a
comparison artefact of an old estate or a capture of any kind.

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
from evorthon_data.engagement import EngagementMode
from evorthon_data.koine_session import KoineSessionError
from evorthon_data.verification.core.canonical import dataset_digest, record_digest
from evorthon_data.verification.core.reconciliation import (
    EFFECTIVE_TIME_ROLE,
    CandidateObservation,
    ExpectedMaterial,
)
from evorthon_data.verification.domain.contracts import (
    CLAUSE_TYPE_BY_FAMILY,
    ActualOutput,
    AdviserConfidence,
    AggregateControl,
    AssuranceDeclaration,
    AssuranceLevel,
    CanonicalisationDeclaration,
    Checkpoint,
    ClauseFamily,
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
    RuleConstraint,
    RuleDeclaration,
    RuleOperator,
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
from evorthon_data.verification.presentation import (
    CLAUSE_FIELDS,
    DECISION_LABEL,
    FAILING_FAMILY_FIELD,
    NO_FAILING_OUTPUT,
    PACKET_LABELS,
    clause_fields,
)

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

PROOF = "renewable-asset-observability"

# --- what the engagement is called --------------------------------------------

ENGAGEMENT = "eng-renewable-asset-observability"
USE_CASE = "uc-asset-performance-view"
SESSION = "session-renewable-asset-proof"
CASE = "case-normal-reporting-day"
CASE_IDENTITY = f"{CASE}:v1:digest-{CASE}"
RESULT_IDENTITY = f"result-{CASE}:v1:digest-result-{CASE}"
DAY_ONE = "asset-performance-view-2026-09-01"
DAY_TWO = "asset-performance-view-2026-09-02"
VIEWS = (DAY_ONE, DAY_TWO)
STEP = "validated-asset-observations"
INPUT_DATASET = "asset-telemetry-extract"
REFERENCE_DATASET = "asset-register-reference"
LOOKUP_DATASET = "turbine-technology-lookup"
ARTEFACT = "asset-event-glossary"
POSITION = "section=target output;line=4"
PROVENANCE = f"{ARTEFACT}:v1:digest-{ARTEFACT}:intake-coworker:model:extracted:{POSITION}"
AUTHORITY = "asset-view-acceptance-authority"
AUTHORITY_IDENTITY = f"{AUTHORITY}:v1:digest-{AUTHORITY}"
HUMAN = f"{AUTHORITY}:human"
DECIDED_BY = f"{AUTHORITY_IDENTITY}:human"
EVIDENCE_ADAPTER = "held-asset-view-evidence"
EVIDENCE_DIRECTORY = "environment-owned-asset-view-material"
CASE_DOCUMENT = harness.case_document(ENGAGEMENT)
RATIONALE_DOCUMENT = harness.rationale_document(ENGAGEMENT)
ADVICE_DOCUMENT = harness.advice_document(ENGAGEMENT)

# --- the declared shape of a published view ------------------------------------

REPORTING_DATE = "reporting-date"
ASSET_CODE = "asset-code"
OBSERVED_FROM = "observed-from"
GENERATED_MWH = "generated-mwh"
CAPACITY_FACTOR = "capacity-factor"
VIEW_STATE = "view-state"
ENERGY_SCALE = 3
FACTOR_SCALE = 4
CANONICAL_SCALE = 4

CONTEXT = ContextIdentity(
    "asset-performance-context",
    "v1",
    "sha256:asset-performance-context",
    "2026-09-02T07:00:00Z",
    "07:00",
    "UTC",
)
CANONICALISATION = CanonicalisationDeclaration(
    "asset-performance-canonicalisation",
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
# The clause family each deliberate defect is expected to be answered by, and
# the status that family is expected to decide. Only the row difference is a
# parity clause; the other four are answered over the facts a run declared.
FAILED = "fail"
PASSED = composition.PASSED
EXPECTED_FAMILIES = {
    "interface": ClauseFamily.CONFORMANCE,
    "invariant": ClauseFamily.INVARIANT,
    "operational": ClauseFamily.OPERATIONAL_EVIDENCE,
    "reference": ClauseFamily.DELIVERY_INTEGRITY,
    "transformation": ClauseFamily.PARITY,
}
DEFECTS = tuple(sorted(EXPECTED_FAMILIES))
# The defect the whole route is driven over, the class the product decides for
# it and the decision its disclosure policy makes about the packet.
ROW_DEFECT = "transformation"
CORRECTED = "corrected"
EXPECTED_FAULT = ("calculation-precision-rounding", "disclose", "low")
# The families whose defect is not a difference between published rows, and the
# one of them the whole route is driven over. Such a run fails with no failing
# output, so no packet is built and none of the labels a packet carries reaches
# the diagnosis it reports.
CONTRACT_DEFECTS = tuple(name for name in DEFECTS if name != ROW_DEFECT)
CONTRACT_DEFECT = "interface"


def schema() -> SchemaDeclaration:
    return SchemaDeclaration(
        schema_id="asset-performance-schema",
        version="v1",
        fields=(
            SchemaField(REPORTING_DATE, SchemaValueType.DATE, False, "partition-date", None, None),
            SchemaField(ASSET_CODE, SchemaValueType.STRING, False, "business-key", None, None),
            SchemaField(OBSERVED_FROM, SchemaValueType.DATE, False, EFFECTIVE_TIME_ROLE, None, None),
            SchemaField(GENERATED_MWH, SchemaValueType.DECIMAL, False, "measure", 18, ENERGY_SCALE),
            SchemaField(CAPACITY_FACTOR, SchemaValueType.DECIMAL, False, "measure", 9, FACTOR_SCALE),
            SchemaField(VIEW_STATE, SchemaValueType.STRING, False, "publication-state", None, None),
        ),
        format_name="csv-rfc4180",
    )


FORMAT_DIGEST = record_digest(schema())


def grain() -> GrainDeclaration:
    return GrainDeclaration(
        grain_id="one-row-per-asset-day",
        version="v1",
        key_fields=(REPORTING_DATE, ASSET_CODE),
        population_description="one row per registered asset on the published reporting day",
        duplicate_keys_permitted=False,
    )


def ordering() -> OrderingDeclaration:
    return OrderingDeclaration(
        "asset-performance-order",
        "v1",
        (
            OrderingField(REPORTING_DATE, SortDirection.ASCENDING, NullPlacement.LAST),
            OrderingField(ASSET_CODE, SortDirection.ASCENDING, NullPlacement.LAST),
        ),
        (),
    )


def aggregate_control(output_id: str) -> AggregateControl:
    return AggregateControl(
        f"generated-mwh-total-{output_id}",
        "v1",
        "sum",
        GENERATED_MWH,
        "generated-mwh-total",
        (REPORTING_DATE,),
        "exclude-null",
        "half-even",
    )


def clause_id(output_id: str) -> str:
    return f"golden-view-{output_id}"


def tolerances() -> tuple[ToleranceDeclaration, ...]:
    """What the case permits: an energy total may move a little, a factor may not."""
    clauses = tuple(clause_id(output_id) for output_id in VIEWS)
    return (
        ToleranceDeclaration(
            "generated-mwh-tolerance",
            "v1",
            clauses,
            (ComparisonDimension.VALUE, ComparisonDimension.CALCULATION),
            (GENERATED_MWH,),
            "absolute-difference",
            "0.0000",
            "0.0500",
            "megawatt-hours",
            "half-even",
        ),
        ToleranceDeclaration(
            "capacity-factor-tolerance",
            "v1",
            clauses,
            (ComparisonDimension.VALUE, ComparisonDimension.CALCULATION),
            (CAPACITY_FACTOR,),
            "absolute-difference",
            "0.0000",
            "0.0000",
            "factor",
            "half-even",
        ),
        ToleranceDeclaration(
            "generated-mwh-total-tolerance",
            "v1",
            clauses,
            (ComparisonDimension.AGGREGATE,),
            ("generated-mwh-total",),
            "absolute-difference",
            "0.0000",
            "0.0500",
            "megawatt-hours",
            "half-even",
        ),
    )


def warning_bands() -> tuple[WarningBandDeclaration, ...]:
    return (
        WarningBandDeclaration(
            "generated-mwh-warning",
            "v1",
            tuple(clause_id(output_id) for output_id in VIEWS),
            (ComparisonDimension.VALUE,),
            (GENERATED_MWH,),
            "absolute-difference",
            "0.0100",
            "0.0500",
            "megawatt-hours",
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
    """Read one written view row into the value types the schema declares."""
    return {
        REPORTING_DATE: date.fromisoformat(row[REPORTING_DATE]),
        ASSET_CODE: row[ASSET_CODE],
        OBSERVED_FROM: date.fromisoformat(row[OBSERVED_FROM]),
        GENERATED_MWH: Decimal(row[GENERATED_MWH]),
        CAPACITY_FACTOR: Decimal(row[CAPACITY_FACTOR]),
        VIEW_STATE: row[VIEW_STATE],
    }


def views(held: harness.ProofFixtures) -> dict[str, tuple]:
    """The two approved golden views, by the output each one answers for."""
    return {
        document["output"]: tuple(typed_row(row) for row in document["rows"])
        for document in (
            held.read("declared/expected/performance-view-day-one.json"),
            held.read("declared/expected/performance-view-day-two.json"),
        )
    }


def candidate_document(held: harness.ProofFixtures, name: str) -> dict:
    return held.read(f"declared/candidate/{name}.json")


def candidate_rows(held: harness.ProofFixtures, name: str) -> dict[str, tuple]:
    """One candidate's declared outputs, by the output each one answers for."""
    return {
        entry["output"]: tuple(typed_row(row) for row in entry["rows"])
        for entry in candidate_document(held, name)["outputs"]
    }


def frozen_datasets(held: harness.ProofFixtures):
    """The datasets the case freezes, each one the shipped generator produced.

    Every row behind them is invented. Nothing here is taken from a run of any
    system, and the generated label each dataset carries says so.
    """
    declared = (
        ("declared/inputs/asset-telemetry-extract.json", DatasetRole.INPUT),
        ("declared/reference/asset-register-reference.json", DatasetRole.REFERENCE),
        ("declared/reference/turbine-technology-lookup.json", DatasetRole.ENRICHMENT),
    )
    return tuple(replace(held.dataset(name).dataset, role=role) for name, role in declared)


def expected_output(output_id: str, rows) -> ExpectedOutput:
    """One approved golden view, authored from the specification this example approved."""
    return ExpectedOutput(
        output_id=output_id,
        version="v1",
        origin=ExpectedOutputOrigin.GREENFIELD_SPECIFICATION,
        provenance=DatasetProvenance.DERIVED,
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
        approved_summary=f"approved golden asset performance view {output_id}",
    )


def actual_output(output_id: str, rows) -> ActualOutput:
    """The output one candidate declared for one published view."""
    return ActualOutput(
        output_id=output_id,
        version="v1",
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
        approved_summary=f"observed asset performance view {output_id}",
    )


def lineage(held: harness.ProofFixtures) -> LineageDefinition:
    """The declared lineage of the view, read from the fixture that owns it."""
    document = held.read("declared/lineage/asset-performance-lineage.json")
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


def contract_clauses(held: harness.ProofFixtures) -> tuple:
    """The four clauses answered over declared facts, as the fixture declares them."""
    document = held.read("declared/contract/clause-requirements.json")
    built = []
    for entry in document["clauses"]:
        requirement = RuleDeclaration(
            entry["requirement"],
            "v1",
            tuple(
                RuleConstraint(
                    constraint["field"],
                    RuleOperator(constraint["operator"]),
                    constraint["value"],
                )
                for constraint in entry["constraints"]
            ),
        )
        family = ClauseFamily(entry["family"])
        built.append(
            CLAUSE_TYPE_BY_FAMILY[family](
                entry["clause_id"],
                "v1",
                identity(entry["subject"]),
                requirement,
                (evidence(entry["evidence"]),),
            )
        )
    return tuple(built)


def declared_families(held: harness.ProofFixtures) -> dict[str, ClauseFamily]:
    """The family each declared clause belongs to, by the clause it answers for."""
    families = {clause_id(output_id): ClauseFamily.PARITY for output_id in VIEWS}
    for entry in held.read("declared/contract/clause-requirements.json")["clauses"]:
        families[entry["clause_id"]] = ClauseFamily(entry["family"])
    return families


def verification_case(held: harness.ProofFixtures) -> VerificationCase:
    """The approved case both versions of this use case are verified against."""
    approved = views(held)
    outputs = tuple(expected_output(output_id, approved[output_id]) for output_id in VIEWS)
    parity = tuple(
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
            (evidence(f"approved-golden-{output.output_id}"),),
        )
        for output in outputs
    )
    case = VerificationCase(
        case_id=CASE,
        version="v1",
        mode=VerificationMode.GREENFIELD,
        frozen_datasets=frozen_datasets(held),
        expected_outputs=outputs,
        context=CONTEXT,
        comparison_policy=ComparisonPolicy(
            "asset-performance-comparison-policy",
            "v1",
            "sha256:asset-performance-comparison-policy",
            parity + contract_clauses(held),
            tolerances(),
            (),
            warning_bands(),
        ),
        lineage=lineage(held),
        assurance=AssuranceDeclaration(
            "asset-performance-assurance", "v1", AssuranceLevel.DECLARED, (), ()
        ),
        diagnostic_strength=DiagnosticStrength.CHECKPOINTED,
    )
    return intake_fixture.with_stored_evidence_digests(case)


# --- one whole run over one scratch repository ---------------------------------


def adapter_name(candidate: str) -> str:
    return f"asset-performance-candidate-{candidate}"


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
                    for output_id in VIEWS
                ),
                clauses=tuple(candidate_document(held, name)["clauses"]),
            )
        )
    return tuple(declared)


def seeded(base: Path, held: harness.ProofFixtures, names) -> VerificationCase:
    """Lay the whole engagement out: the case, the adapters, the material, the documents."""
    case = verification_case(held)
    approved = views(held)
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


def declarations(status: str = PASSED) -> tuple[tuple[str, dict], ...]:
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
                "source system": "asset-telemetry-platform",
                "delivery mode": "nightly file drop",
                "dataset cadence": "daily",
                "access owner": "asset-evidence-owner:human",
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
                "source system": "asset-register",
                "delivery mode": "weekly export",
                "dataset cadence": "weekly",
                "access owner": "asset-evidence-owner:human",
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
                "source system": "turbine-technology-catalogue",
                "delivery mode": "weekly export",
                "dataset cadence": "weekly",
                "access owner": "asset-evidence-owner:human",
                "classification": "internal",
                "availability state": "obtained",
                "availability subject": f"{LOOKUP_DATASET}-2026-09:v1:digest-{LOOKUP_DATASET}-2026-09",
                "provenance": PROVENANCE,
            },
        ),
    ]
    for output_id in VIEWS:
        declared.append(
            (
                "target-output",
                {
                    "output identity": output_id,
                    "output kind": "table",
                    "schema declaration": "asset-performance-schema:v1:tabular",
                    "schema fields": (
                        f"{ASSET_CODE}:string:not-null:::registered asset key"
                        f";{GENERATED_MWH}:decimal:not-null:18:3:generated energy"
                    ),
                    "grain declaration": (
                        "one-row-per-asset-day:v1:unique-keys:registered assets on the reporting day"
                    ),
                    "grain keys": ASSET_CODE,
                    "output cadence": "daily",
                    "cutoff semantics": "observations settled before the morning cutoff",
                    "effective-time semantics": "effective-dated on the observation date",
                    "stored name": "ASSET_PERFORMANCE_VIEW",
                    "stored column names": f"{ASSET_CODE}:ASSET_CODE",
                    "defining specification": (
                        "asset-performance-specification:v1:digest-asset-performance-specification"
                    ),
                    "provenance": PROVENANCE,
                },
            )
        )
    declared.append(
        (
            "intermediate-result",
            {
                "step identity": STEP,
                "step description": "asset observations validated before publication, one row per asset",
                "evidence owner": HUMAN,
                "checkpoint candidate": "checkpoint",
                "provenance": PROVENANCE,
            },
        )
    )
    for output_id in VIEWS:
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
                    "condition value": "before the morning operations review",
                    "provenance": PROVENANCE,
                },
            ),
            (
                "intake-artefact",
                {
                    "intake artefact": f"{ARTEFACT}:v1:digest-{ARTEFACT}",
                    "artefact classification": "confidential",
                    "artefact locator": "intake/asset-event-glossary",
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
            "authority actor": "asset-evidence-owner:human",
            "authority subject": STEP,
            "provenance": PROVENANCE,
        },
    ),
)


def header_parts() -> tuple[str, ...]:
    return (
        f"{USE_CASE}:v1:digest-{USE_CASE}",
        ENGAGEMENT,
        "greenfield",
        "the renewable asset operations manager",
        "act on asset condition and production before the operations review",
        "the manager can act on the published asset view alone",
        "every reporting day before the operations review",
        "2026-12-01",
        PROVENANCE,
    )


def intake(status: str = PASSED) -> lifecycle.UseCaseIntake:
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
# record the stage writes describes the asset performance view and nothing else.
GENERATED_SEGMENT = "asset_performance_view"
GENERATED_SOURCE = "asset_telemetry_extract"
GENERATED_STEP = "asset_observation_validation"
GENERATED_DOMAIN = "asset"
GENERATED_PRODUCT = "telemetry_extract"
SEED_DOCUMENT = "declared/generation/asset-telemetry-seed.csv"
GENERATED_FIELDS = (
    draft_support.schema_field("asset_code"),
    draft_support.schema_field("observed_at", SchemaValueType.TIMESTAMP, nullable=True),
)


# The names the emitted estate carries for this engagement. The estate itself
# is the generation proof's own recorded one, renamed onto this example, so the
# record of an asset observability run names an asset observability product and
# the shape of an emitted estate keeps its one owner.
GENERATED_NAMES = {
    "settled_positions": GENERATED_SEGMENT,
    "exposure_summary": "asset_production_summary",
    "position_id": "asset_code",
    "booked_at": "observed_at",
    "booked_on": "observed_on",
    "exposure_amount": "generated_mwh",
    "exposure_label": "production_label",
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
        grain_id="one-row-per-asset-observation",
        version="v1",
        key_fields=("asset_code",),
        population_description="validated asset observations",
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
                        canonicalisation_id="asset-performance-generation-canonicalisation",
                    ),
                    approved_summary="two invented asset observations",
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
            cutoff_semantics="observations settled before the morning cutoff",
            effective_time_semantics="effective-dated on the observation date",
            provenance=read,
        ),
        intermediate_calculations={
            GENERATED_STEP: (
                draft_support.ProposedCalculatedField(
                    field_id="observed_on",
                    value_type=SchemaValueType.DATE,
                    expression="CAST(observed_at AS DATE)",
                ),
            )
        },
    )


def delivery(repository: Path, held: harness.ProofFixtures) -> lifecycle.SegmentDelivery:
    return lifecycle.SegmentDelivery(
        declaration_request=declaration_request(),
        proposal_reference="asset-performance-declaration:v1",
        drafted_by="declaration-drafter",
        reviewer="declaration-reviewer:v1:digest-declaration-reviewer",
        disposition="accepted",
        generation_reference="asset-performance-generation:v1:digest-asset-performance-generation",
        generation_actor="generation-actor",
        estate_name="asset-performance-view",
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


def acceptance(covered: tuple[str, ...], version: str) -> lifecycle.VersionAcceptance:
    """The words one version of this use case is cut and accepted in.

    ``version`` names how much of the use case the cut covers. The reading of
    the evidence is the one the case derives, and is the same for both cuts
    because both stand on the same approved case.
    """
    named = f"{USE_CASE}-{version}"
    return lifecycle.VersionAcceptance(
        version_reference=f"{named}:v1:digest-{named}",
        version_identity=named,
        covered_segments=";".join(covered),
        projection_reference=f"readiness-{USE_CASE}:v1",
        decision_identity=f"accept-{version}",
        decided_by=HUMAN,
        rationale=f"rationale-accept-{version}:v1:digest-rationale-accept-{version}",
        scenario_case_versions=CASE_IDENTITY,
        evidence=RESULT_IDENTITY,
        case_readings=f"{CASE_IDENTITY}:{READING}",
    )


SEGMENTS = (STEP, DAY_ONE, DAY_TWO)
# How the evidence of this case reads as a whole: the frozen datasets are
# generated and the approved golden views are authored from the specification,
# so the reading of the two together is the mixed one the domain derives. The
# product refuses to call an authored specification output generated, and this
# proof records the reading it derives rather than one of its own.
READING = "mixed"
ONE_SLICE = "one-view"
WHOLE = "every-segment"


def traversed(
    base: Path,
    candidate: str = ROW_DEFECT,
    *,
    covered: tuple[str, ...] = SEGMENTS,
    version: str = WHOLE,
    declared_status: str = PASSED,
    corrected: str = CORRECTED,
):
    """Drive one whole traversal of the route over one scratch repository."""
    base.mkdir(parents=True, exist_ok=True)
    held = fixtures()
    seeded(base, held, (candidate, corrected))
    scripted = held.read(harness.ADVISER_REPLIES)
    hypothesis = scripted["replies"].get(candidate) or next(iter(scripted["replies"].values()))
    fakes = harness.ProofFakes(
        ENGAGEMENT,
        SESSION,
        harness.scripted_reply(
            hypothesis, scripted["assumptions"], AdviserConfidence(scripted["confidence"])
        ),
        generator=generation_fixture.FakeErgasterionRunner(files=generated_estate()),
        mode=EngagementMode.GREENFIELD,
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
        acceptance=acceptance(covered, version),
    )
    return harness.ProofRun(base=base, record=record, fakes=fakes, held=held)


def verified(base: Path, candidate: str) -> dict:
    """Drive the two stages of the route that answer one candidate's whole contract."""
    route = {
        "repository": base,
        "root": harness.RECORDS_ROOT,
        "engagement_id": ENGAGEMENT,
        "case_document": CASE_DOCUMENT,
        "evidence_identity": EVIDENCE_ADAPTER,
        "candidate_identity": adapter_name(candidate),
    }
    composition.intake_verification_case(**route)
    return dict(
        composition.verify_case(**route, material_document=material_document(candidate)).values
    )


def clause_statuses(reported: dict) -> dict[str, tuple[str, str]]:
    """Read the reported clause lines back as the family and status of each clause."""
    read = {}
    for written_line in reported["clauses"]:
        fields = clause_fields(written_line)
        assert fields is not None, written_line
        entry = dict(zip(CLAUSE_FIELDS, fields))
        read[entry["clause"]] = (entry["family"], entry["status"])
    return read


@pytest.fixture(scope="session")
def contract_runs(tmp_path_factory):
    """Every candidate answered against the whole contract, over one engagement.

    Each candidate is answered by the verification stage the route drives, over
    the same laid-out engagement and the same approved case, so the six answers
    differ only by the material the candidate declared.
    """
    base = tmp_path_factory.mktemp("contract")
    held = fixtures()
    seeded(base, held, (*DEFECTS, CORRECTED))
    return {name: verified(base, name) for name in (*DEFECTS, CORRECTED)}


@pytest.fixture(scope="session")
def run(tmp_path_factory):
    """One whole traversal of the route over the defect the comparison reports."""
    return traversed(tmp_path_factory.mktemp("route") / "whole")


# --- the case the whole proof rests on ----------------------------------------


def test_the_approved_case_is_one_the_central_validator_accepts():
    assert inspect_verification_case(verification_case(fixtures())).issues == ()


def test_the_frozen_input_is_the_dataset_the_declared_seed_produces():
    harness.confirm_seeded_dataset(fixtures(), "declared/inputs/asset-telemetry-extract.json")


# --- every stage, over the whole example --------------------------------------


def test_one_run_drives_every_stage_of_the_route_over_the_example(run):
    assert [stage.name for stage in run.record.stages] == list(lifecycle.STAGES)
    assert (run.record.engagement_id, run.record.use_case_id) == (ENGAGEMENT, USE_CASE)
    assert run.stage(lifecycle.CASE_INTAKE)["case"] == CASE
    verified_stage = run.stage(lifecycle.VERIFICATION)
    assert verified_stage["status"] == FAILED
    assert verified_stage["failed outputs"] == DAY_TWO
    # The adviser was asked exactly once, after the two intake rounds and their
    # reviews, and nothing else crossed the egress port.
    assert run.fakes.transport.routes.count(harness.ADVISER_ROUTE) == 1
    decided = run.stage(lifecycle.REMEDIATION)
    assert decided["disposition"] == "accepted"
    assert decided["remedy item"].startswith("evd-")
    assert run.stage(lifecycle.CORRECTED_RERUN)["status"] == PASSED
    assert run.stage(lifecycle.ACCEPTANCE)["version"] == f"{USE_CASE}-{WHOLE}"


def test_every_record_this_run_writes_describes_this_example(run):
    """The generation stage declares and emits this engagement's own product."""
    generated = run.stage(lifecycle.SEGMENT_GENERATION)
    recorded = "\n".join(harness.written_records(run.base).values())

    assert generated["generation"] == "asset-performance-generation"
    assert generated["checkpoints"] == f"{GENERATED_DOMAIN}.{GENERATED_SEGMENT}"
    for drafted in GENERATED_NAMES:
        assert drafted not in recorded, drafted


# --- the five families, each red on the defect it owns -------------------------


@pytest.mark.parametrize("defect", DEFECTS, ids=DEFECTS)
def test_every_injected_defect_reddens_the_family_that_owns_it(contract_runs, defect):
    """One family answers one defect, and the four beside it still pass."""
    held = fixtures()
    families = declared_families(held)
    owning = EXPECTED_FAMILIES[defect]

    answered = clause_statuses(contract_runs[defect])

    assert contract_runs[defect]["status"] == FAILED
    failing = {clause for clause, (_, status) in answered.items() if status == FAILED}
    assert {families[clause] for clause in failing} == {owning}
    assert answered == {
        clause: (families[clause].value, FAILED if clause in failing else PASSED)
        for clause in families
    }


@pytest.mark.parametrize("defect", DEFECTS, ids=DEFECTS)
def test_a_swapped_defect_reddens_the_family_this_proof_asserts(contract_runs, defect):
    """Read one defect's run against every other defect's expected family."""
    families = declared_families(fixtures())
    answered = clause_statuses(contract_runs[defect])
    reported = {
        ClauseFamily(family) for family, status in answered.values() if status == FAILED
    }

    assert reported == {EXPECTED_FAMILIES[defect]}
    assert all(
        reported != {EXPECTED_FAMILIES[other]} for other in DEFECTS if other != defect
    )
    assert set(families.values()) == set(EXPECTED_FAMILIES.values())


def test_the_corrected_candidate_answers_every_declared_clause(contract_runs):
    """Nothing is left unanswered: every family passes on the corrected candidate."""
    families = declared_families(fixtures())

    answered = clause_statuses(contract_runs[CORRECTED])

    assert contract_runs[CORRECTED]["status"] == PASSED
    assert contract_runs[CORRECTED]["failed clauses"] == []
    assert contract_runs[CORRECTED]["unresolved clauses"] == []
    assert answered == {clause: (family.value, PASSED) for clause, family in families.items()}


def test_a_contract_family_failure_names_no_failing_output_and_completes_the_route(
    contract_runs, tmp_path
):
    """A whole run whose only failure is answered over declared facts completes.

    The four families answered over declared facts report their failure without
    a difference between published rows, so no output is named as failing and
    there is no packet for a diagnosis to build. The diagnosis reports that
    decision with the family that failed and the clause it is; the three stages
    that would have needed a packet are recorded as not reached with it as the
    reason; and the run is carried on to the acceptance evidence, the version
    cut and an acceptance recorded as not reached on the failing status.
    """
    for defect in CONTRACT_DEFECTS:
        assert contract_runs[defect]["failed outputs"] == []
    assert contract_runs[ROW_DEFECT]["failed outputs"] == [DAY_TWO]

    taken = traversed(tmp_path / CONTRACT_DEFECT, CONTRACT_DEFECT, declared_status=FAILED)

    assert [stage.name for stage in taken.record.stages] == list(lifecycle.STAGES)
    verified_stage = taken.stage(lifecycle.VERIFICATION)
    assert (verified_stage["status"], verified_stage["failed outputs"]) == (
        FAILED,
        composition.NOTHING,
    )
    diagnosed = taken.stage(lifecycle.DIAGNOSIS)
    assert diagnosed[DECISION_LABEL] == NO_FAILING_OUTPUT
    assert diagnosed[FAILING_FAMILY_FIELD] == EXPECTED_FAMILIES[CONTRACT_DEFECT].value
    assert PACKET_LABELS.isdisjoint(diagnosed)
    for name in (lifecycle.ADVICE, lifecycle.REMEDIATION, lifecycle.CORRECTED_RERUN):
        stage = taken.stage(name)
        assert stage[lifecycle.REACHED_LABEL] == lifecycle.NOT_REACHED
        assert stage[lifecycle.REASON_LABEL] == NO_FAILING_OUTPUT
    # Nobody was asked about a packet that was never built.
    assert harness.ADVISER_ROUTE not in taken.fakes.transport.routes
    assert taken.stage(lifecycle.ACCEPTANCE_EVIDENCE)[lifecycle.STATUS_LABEL] == FAILED
    assert taken.stage(lifecycle.VERSION_CUT)["version"] == f"{USE_CASE}-{WHOLE}"
    accepted = taken.stage(lifecycle.ACCEPTANCE)
    assert accepted[lifecycle.REACHED_LABEL] == lifecycle.NOT_REACHED
    assert accepted[lifecycle.REASON_LABEL] == lifecycle.UNVERIFIED_SCENARIO.format(
        status=FAILED
    )


# --- the disclosed packet, the advice and the corrected work --------------------


def test_the_row_defect_reports_the_class_and_strength_the_product_decides(run):
    declared_class, decision, strength = EXPECTED_FAULT

    diagnosed = run.stage(lifecycle.DIAGNOSIS)

    assert diagnosed["fault class"] == declared_class
    assert diagnosed[composition.DISCLOSURE_LABEL] == decision
    assert diagnosed["confidence"] == strength
    assert diagnosed["localisation status"] == "inferred"
    assert f"output {DAY_TWO}" in diagnosed["diagnostic scope"]


def test_a_disclosed_packet_names_the_lineage_the_checkpoints_support(run):
    """The localisation is the interval the declared checkpoints support, and says so."""
    diagnosed = run.stage(lifecycle.DIAGNOSIS)
    evidence_stage = run.stage(lifecycle.ACCEPTANCE_EVIDENCE)
    declared = run.held.read("declared/lineage/asset-performance-lineage.json")
    bound = next(
        entry["checkpoint"] for entry in declared["bindings"] if entry["output"] == DAY_TWO
    )

    assert diagnosed["localisation status"] == "inferred"
    assert "uncovered 1" in diagnosed["diagnostic scope"]
    assert diagnosed["fault id"] in evidence_stage["localisation"]
    assert bound in {checkpoint["checkpoint_id"] for checkpoint in declared["checkpoints"]}


def test_the_advice_the_human_disposes_of_is_the_scripted_reply_this_run_produced(run):
    """The adviser's hypothesis is recorded as inert text and selected by a named human."""
    scripted = run.held.read(harness.ADVISER_REPLIES)
    selection = run.held.read(harness.HUMAN_SELECTION)

    advised = run.stage(lifecycle.ADVICE)
    decided = run.stage(lifecycle.REMEDIATION)
    written_advice = json.loads(
        (run.base / harness.RECORDS_ROOT / ADVICE_DOCUMENT).read_text(encoding="ascii")
    )

    assert advised["hypotheses"] == "1"
    assert advised["required authority"] == AUTHORITY
    assert written_advice["record"]["hypotheses"] == [scripted["replies"][ROW_DEFECT]["cause"]]
    assert written_advice["record"]["proposed_fixes"] == [
        scripted["replies"][ROW_DEFECT]["proposed_fix"]
    ]
    assert decided["disposition"] == selection["disposition"]
    assert decided["decided by"] == selection["decided_by"]["identity"] == AUTHORITY
    assert decided["fault"] == advised["fault"]
    # No prose a person or an adviser wrote reaches the record of the run.
    recorded = "\n".join(harness.written_records(run.base).values())
    for value in (
        scripted["replies"][ROW_DEFECT]["cause"],
        scripted["replies"][ROW_DEFECT]["proposed_fix"],
        selection["rationale"]["summary"],
    ):
        assert value not in recorded


def test_both_published_views_pass_on_the_corrected_rerun(run):
    """The corrected candidate reproduces both views, and the regression set says so."""
    rerun = run.stage(lifecycle.CORRECTED_RERUN)

    assert rerun["status"] == PASSED
    assert rerun["rerun"] == "green"
    assert rerun["regression set"] == lifecycle.LIST_SEPARATOR.join(
        declared_families(run.held)
    )
    assert rerun["corrected"] == clause_id(DAY_TWO)
    assert rerun["restored defects"] == composition.NOTHING
    assert rerun["regressions"] == composition.NOTHING
    evidence_stage = run.stage(lifecycle.ACCEPTANCE_EVIDENCE)
    assert evidence_stage["status"] == FAILED
    assert evidence_stage["reruns"].endswith("green")
    assert run.stage(lifecycle.ACCEPTANCE)["state"] == "accepted"


def test_a_restored_defect_reddens_the_corrected_rerun(tmp_path):
    """Rerun the uncorrected candidate and the rerun reports the defect still there."""
    restored = traversed(
        tmp_path / "restored", ROW_DEFECT, corrected=ROW_DEFECT, declared_status=FAILED
    )

    rerun = restored.stage(lifecycle.CORRECTED_RERUN)
    assert rerun["rerun"] == "red"
    assert rerun["status"] == FAILED
    assert rerun["restored defects"] == clause_id(DAY_TWO)
    assert rerun["corrected"] == composition.NOTHING
    accepted = restored.record.stage(lifecycle.ACCEPTANCE)
    assert accepted.value(lifecycle.REACHED_LABEL) == lifecycle.NOT_REACHED


# --- the named acceptance and the labels it rests on ---------------------------


def test_the_corrected_run_reaches_a_named_acceptance_on_labelled_evidence(run):
    """A named human accepts, and the record says what the evidence behind it is.

    The frozen datasets are generated and say so; the approved golden views are
    authored from the specification and carry that origin, so no expected value
    is taken from a run of any earlier system. The reading of the two together
    is the one the domain derives from them.
    """
    held = run.held
    case = verification_case(held)

    accepted = run.stage(lifecycle.ACCEPTANCE)
    evidence_stage = run.stage(lifecycle.ACCEPTANCE_EVIDENCE)

    assert accepted["decided by"] == AUTHORITY
    assert accepted["state"] == "accepted"
    assert accepted["evidence provenance"] == READING
    assert (evidence_stage["evidence provenance"], evidence_stage["synthetic datasets"]) == (
        READING,
        "3",
    )
    assert {dataset.provenance for dataset in case.frozen_datasets} == {
        DatasetProvenance.SYNTHETIC
    }
    assert {output.origin for output in case.expected_outputs} == {
        ExpectedOutputOrigin.GREENFIELD_SPECIFICATION
    }
    assert {output.provenance for output in case.expected_outputs} == {DatasetProvenance.DERIVED}
    # The facts the acceptance was recorded with carry the authored origin of
    # every expected output and no origin of any other kind.
    reached = lifecycle.case_facts(
        composition.records_root(run.base, harness.RECORDS_ROOT),
        verification(held, ROW_DEFECT),
        status=PASSED,
    )
    assert all(
        line.endswith(f"derived:{ExpectedOutputOrigin.GREENFIELD_SPECIFICATION.value}")
        for line in reached["case_expected_outputs"]
    )
    assert all(line.endswith("synthetic") for line in reached["case_datasets"])


def test_an_acceptance_that_claims_a_capture_origin_is_not_the_one_this_version_was_cut_on(run):
    """The authored origin is load-bearing rather than decorative.

    The acceptance route recomputes the readiness of the record from the case
    facts it is given and accepts only the version that reading reproduces. An
    acceptance that claimed its expected values came from a run of an earlier
    system would be reading the record differently from the way the version was
    cut, and the route refuses it.
    """
    route = {
        "repository": run.base,
        "root": harness.RECORDS_ROOT,
        "engagement_id": ENGAGEMENT,
        "use_case_id": USE_CASE,
    }
    reached = lifecycle.case_facts(
        composition.records_root(run.base, harness.RECORDS_ROOT),
        verification(run.held, ROW_DEFECT),
        status=PASSED,
    )
    claimed = dict(reached)
    claimed["case_expected_outputs"] = tuple(
        line.replace(
            f"{DatasetProvenance.DERIVED.value}:{ExpectedOutputOrigin.GREENFIELD_SPECIFICATION.value}",
            f"{DatasetProvenance.REAL.value}:{ExpectedOutputOrigin.MODERNISATION_CAPTURE.value}",
        )
        for line in reached["case_expected_outputs"]
    )
    taken = acceptance(SEGMENTS, WHOLE)

    with pytest.raises(composition.CompositionError):
        composition.record_use_case_acceptance(
            **route,
            version_identity=taken.version_identity,
            decision_identity="accept-claimed",
            decided_by=taken.decided_by,
            rationale=taken.rationale,
            case_readings=taken.case_readings,
            **claimed,
        )
    # Nothing was written: the record still holds the one acceptance it took.
    assert len(harness.recorded_acceptances(run.base, ENGAGEMENT, USE_CASE)) == 1


def test_the_approval_of_every_golden_view_names_its_author_and_its_evidence():
    """Each approved golden view is authored, approved and never taken from a run."""
    held = fixtures()

    for name in (
        "declared/expected/performance-view-day-one.json",
        "declared/expected/performance-view-day-two.json",
    ):
        declared = held.declarations[name].fields
        document = held.read(name)
        assert declared["author"] == document["author"]
        assert declared["approval"] == document["approval"]
        assert "seed" not in declared


# --- the two versions on one record --------------------------------------------


def taken_beside(taken_run: harness.ProofRun, *, covered: tuple[str, ...], version: str):
    """Cut one more version on the record this run holds, and accept it there."""
    return harness.taken_beside(
        taken_run.base,
        engagement_id=ENGAGEMENT,
        use_case_id=USE_CASE,
        taken=acceptance(covered, version),
        reached=lifecycle.case_facts(
            composition.records_root(taken_run.base, harness.RECORDS_ROOT),
            verification(taken_run.held, ROW_DEFECT),
            status=PASSED,
        ),
    )


def test_the_one_slice_version_is_accepted_before_the_whole_one_beside_it(tmp_path):
    """One published view first, every segment beside it, both on one record.

    The first version is cut over one published view and accepted. The second
    is cut over every segment on the readiness the record recomputes and
    accepted beside the first. The record's lifecycle moves once, the first
    version and the acceptance it was taken through stand exactly as they were
    taken, and both coverage statements are read back off that one record.
    """
    sliced = traversed(tmp_path / "one-record", covered=(DAY_ONE,), version=ONE_SLICE)
    first_cut = sliced.stage(lifecycle.VERSION_CUT)
    first_accepted = sliced.stage(lifecycle.ACCEPTANCE)
    taken = composition.load_use_case(sliced.base, harness.RECORDS_ROOT, ENGAGEMENT, USE_CASE)[0]
    recorded = harness.record_text(sliced.base, ENGAGEMENT, USE_CASE)

    second_cut, second_accepted = taken_beside(sliced, covered=SEGMENTS, version=WHOLE)

    held = composition.load_use_case(sliced.base, harness.RECORDS_ROOT, ENGAGEMENT, USE_CASE)[0]
    assert [version.identity.identifier for version in held.versions] == [
        first_cut["version"],
        second_cut["version"],
    ]
    assert held.versions[0].covered_segments == (DAY_ONE,)
    assert held.versions[0].covered_outputs == (DAY_ONE,)
    assert sorted(held.versions[0].segments_outside) == sorted((STEP, DAY_TWO))
    assert held.versions[1].covered_segments == SEGMENTS
    assert held.versions[1].segments_outside == ()
    # Both named acceptances stand on that record, each with the reading the
    # evidence behind its own version carries.
    assert first_accepted["evidence provenance"] == second_accepted["evidence provenance"] == READING
    assert [
        entry["case readings"]
        for entry in harness.recorded_acceptances(sliced.base, ENGAGEMENT, USE_CASE)
    ] == [
        f"{CASE_IDENTITY}:{READING}",
        f"{CASE_IDENTITY}:{READING}",
    ]
    assert [decision.decision_id for decision in held.decisions] == [
        first_accepted["decision"],
        second_accepted["decision"],
    ]
    # The lifecycle moved once, through the first acceptance and no other.
    assert [move.target.value for move in held.transitions] == ["verified", "accepted"]
    assert (held.state.value, second_accepted["state"]) == ("accepted", "accepted")
    assert first_accepted["suggested disposition"] == first_cut["suggested disposition"]
    assert second_accepted["suggested disposition"] == second_cut["suggested disposition"]
    # The first version and its acceptance are exactly as they were taken, in
    # the use case the record replays and in the bytes of the record itself.
    assert (held.versions[0], held.decisions[0]) == (taken.versions[0], taken.decisions[0])
    assert harness.record_text(sliced.base, ENGAGEMENT, USE_CASE).startswith(recorded)


# --- the greenfield boundary ---------------------------------------------------


def test_a_greenfield_intake_round_refuses_a_parity_question():
    """The engagement is never asked what an earlier output it replaces."""
    asked = []

    def comparison_round(call):
        asked.append(call)
        return koine_fixture.IntakeRoundProposal(
            facts=(
                koine_fixture.IntakeFact(
                    "2. Target outputs",
                    "replaced output",
                    "an output of an earlier estate",
                    koine_fixture.read_at(
                        call, koine_fixture.DICTIONARY_ARTEFACT, "target output;replaced output"
                    ),
                ),
            )
        )

    transport = harness.ScriptedTransport((comparison_round,), lambda call: None)
    gateway = harness.ModelEgressGateway(
        local_transport=transport, fake_transport=transport, clock=lambda: harness.NOW
    )
    session = harness.coworker_session(
        gateway, ENGAGEMENT, SESSION, EngagementMode.GREENFIELD
    )
    opened = composition.use_case_from_header(header_parts())

    with pytest.raises(KoineSessionError, match="never asked a parity question"):
        session.run_intake_round(
            opened,
            koine_fixture.intake_readings(),
            authorization=harness.intake_authorization(ENGAGEMENT, SESSION),
        )
    # The round was asked once and its proposal was refused, so nothing the
    # round read reaches the record and no answer to such a question is taken.
    assert len(asked) == len(transport.calls) == 1
    assert opened.target_outputs == ()


def test_a_greenfield_case_refuses_an_expected_value_taken_from_an_old_run():
    """No expected value of this case may declare a capture of an earlier system."""
    case = verification_case(fixtures())

    taken = replace(
        case,
        expected_outputs=tuple(
            replace(
                output,
                origin=ExpectedOutputOrigin.MODERNISATION_CAPTURE,
                provenance=DatasetProvenance.REAL,
            )
            for output in case.expected_outputs
        ),
    )

    assert inspect_verification_case(case).issues == ()
    assert {issue.code for issue in inspect_verification_case(taken).issues} == {
        "invalid-expected-origin"
    }


def test_the_record_refuses_a_step_whose_expected_value_comes_from_an_old_run(tmp_path):
    """The use-case record refuses the same claim the case refuses."""
    base = tmp_path / "old-run"
    base.mkdir(parents=True, exist_ok=True)
    composition.open_use_case(
        repository=base, root=harness.RECORDS_ROOT, header_parts=header_parts()
    )
    fields = {
        "step identity": STEP,
        "step description": "asset observations validated before publication",
        "evidence owner": HUMAN,
        "checkpoint candidate": "checkpoint",
        "expected value origin": ExpectedOutputOrigin.MODERNISATION_CAPTURE.value,
        "provenance": PROVENANCE,
    }

    with pytest.raises(composition.CompositionError, match="from an old run"):
        composition.record_fact(
            repository=base,
            root=harness.RECORDS_ROOT,
            engagement_id=ENGAGEMENT,
            use_case_id=USE_CASE,
            kind="intermediate-result",
            declared_fields=tuple(f"{name}={value}" for name, value in fields.items()),
        )


# The words that would name an estate this greenfield delivery does not have.
# A fixture that carried one would be inventing the thing the example refuses
# to invent.
ESTATE_WORDS = (
    "legacy",
    "baseline",
    "cutover",
    "continuity",
    "modernisation",
    "modernization",
    "capture",
    "captured",
    "parity",
    "replaced",
)
# The records a run writes carry the engine's own clause vocabulary, in which
# the family that compares a candidate against an approved expected output is
# named. That word is the engine's and not an artefact of an old estate, so it
# is read out of the words a record may not carry.
RECORD_WORDS = tuple(word for word in ESTATE_WORDS if word != "parity")


def test_no_fixture_of_this_proof_invents_an_estate_that_does_not_exist():
    held = fixtures()

    for name in (harness.PROVENANCE_RECORD, *held.held()):
        text = (held.root / name).read_text(encoding="ascii").lower()
        found = [word for word in ESTATE_WORDS if word in text]
        assert found == [], f"{name}: {found}"


def test_no_record_this_run_writes_invents_an_estate_that_does_not_exist(run):
    recorded = "\n".join(harness.written_records(run.base).values()).lower()

    found = [word for word in RECORD_WORDS if word in recorded]

    assert found == []
    # The one word a record does carry is the engine's own family name, read
    # off the clause lines the verification stage wrote.
    assert ClauseFamily.PARITY.value in run.stage(lifecycle.VERIFICATION)["clauses"]


# --- the provenance and privacy gates over this proof's fixtures ---------------


def test_every_fixture_is_declared_with_its_provenance_licence_and_source():
    harness.confirm_declared_material(fixtures())


# The one golden view a gate proof takes apart and the negative sample it
# resolves. The four faults themselves, and the finding each one must produce,
# are the harness's, because both proofs are held to the same four.
GATED_FILE = "declared/expected/performance-view-day-one.json"
NEGATIVE_SAMPLE = "withheld/confidential-asset-register-export.txt"
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


def test_this_proof_reads_every_fixture_the_run_needs_and_nothing_else(run):
    """What the run opened is exactly the material declared for projection."""
    held = run.held

    assert set(held.reads) <= set(held.projected())
    assert set(held.reads) == set(held.projected()) - {
        f"declared/candidate/{name}.json" for name in CONTRACT_DEFECTS
    }
# evorthon-verifies: EVD-README-012
# evorthon-verifies: EVD-README-037
