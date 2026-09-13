"""Committed canonical vectors, mutation cases and integrity refusals."""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from evorthon_data.verification.core import canonical as core
from evorthon_data.verification.core import (
    CanonicalisationRefusal,
    DIGEST_PREFIX,
    HASH_ALGORITHM,
    HASH_DIGEST_SIZE_BYTES,
    RefusalReason,
    canonical_digest,
    canonical_record_bytes,
    canonical_row_stream,
    case_digest,
    dataset_digest,
    frozen_dataset_digest,
    record_digest,
    result_digest,
)
from evorthon_data.verification.domain.contracts import (
    ActualOutput,
    AssuranceDeclaration,
    AssuranceLevel,
    CandidateIdentity,
    CanonicalisationDeclaration,
    ClauseFamily,
    ClauseOutcome,
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
    FrozenDataset,
    GrainDeclaration,
    Identity,
    IndependentlyDerivedReceipt,
    LineageDefinition,
    NullPlacement,
    OrderingDeclaration,
    OrderingField,
    OutputLineageBinding,
    ParityClause,
    ReceiptSubject,
    RepeatRunIdentity,
    SchemaDeclaration,
    SchemaField,
    SchemaValueType,
    SortDirection,
    VerificationCase,
    VerificationMode,
    VerificationResult,
    VerificationStatus,
)

ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "canonical"
VECTOR_DIRECTORY = FIXTURES / "vectors"
DIGEST_INDEX = FIXTURES / "digests.json"
PROVENANCE = FIXTURES / "provenance.json"

ALLOWED_CORE_IMPORTS = {
    "__future__",
    "collections.abc",
    "dataclasses",
    "datetime",
    "decimal",
    "enum",
    "evorthon_data.verification.core.canonical",
    "evorthon_data.verification.core.localisation",
    "evorthon_data.verification.core.reconciliation",
    "evorthon_data.verification.domain.contracts",
    "hashlib",
    "json",
    "types",
    "unicodedata",
}
FORBIDDEN_CORE_TEXT = (".now(", ".today(", ".utcnow(", "open(", "getenv", "os.environ", "random.", "locale.")


def field(
    field_id: str,
    value_type: SchemaValueType,
    *,
    nullable: bool = False,
    precision: int | None = None,
    scale: int | None = None,
    role: str = "measure",
) -> SchemaField:
    return SchemaField(field_id, value_type, nullable, role, precision, scale)


def schema(schema_id: str, fields: tuple[SchemaField, ...]) -> SchemaDeclaration:
    return SchemaDeclaration(schema_id, "v1", fields, "csv-rfc4180")


def grain(grain_id: str, key_fields: tuple[str, ...], *, duplicates: bool = False) -> GrainDeclaration:
    return GrainDeclaration(grain_id, "v1", key_fields, "one approved population", duplicates)


def canonicalisation(
    canonicalisation_id: str,
    *,
    normalisation: str = "NFC",
    scale: int | None = 2,
    precision: str | None = "milliseconds",
    zone: str | None = "UTC",
    signed_zero: str = "positive-zero",
    non_finite: str = "reject",
) -> CanonicalisationDeclaration:
    return CanonicalisationDeclaration(
        canonicalisation_id,
        "v1",
        normalisation,
        "json-null",
        scale,
        precision,
        zone,
        signed_zero,
        non_finite,
    )


def ordering(
    ordering_id: str,
    fields: tuple[OrderingField, ...],
    tie_breakers: tuple[str, ...] = (),
) -> OrderingDeclaration:
    return OrderingDeclaration(ordering_id, "v1", fields, tie_breakers)


def ascending(field_id: str, placement: NullPlacement = NullPlacement.LAST) -> OrderingField:
    return OrderingField(field_id, SortDirection.ASCENDING, placement)


def descending(field_id: str, placement: NullPlacement = NullPlacement.FIRST) -> OrderingField:
    return OrderingField(field_id, SortDirection.DESCENDING, placement)


def stamp(year: int, month: int, day: int, hour: int, minute: int, second: int, microsecond: int) -> datetime:
    return datetime(year, month, day, hour, minute, second, microsecond, tzinfo=timezone.utc)


@dataclass(frozen=True)
class RowVector:
    """One committed row-stream vector and the single value change that reddens it."""

    schema: SchemaDeclaration
    grain: GrainDeclaration
    canonicalisation: CanonicalisationDeclaration
    ordering: OrderingDeclaration | None
    rows: tuple[dict, ...]
    mutation: tuple[int, str, object]

    def stream(self, rows: tuple[dict, ...] | list[dict] | None = None) -> bytes:
        return canonical_row_stream(
            self.rows if rows is None else rows,
            schema=self.schema,
            grain=self.grain,
            canonicalisation=self.canonicalisation,
            ordering=self.ordering,
        )

    def digest(self) -> str:
        return canonical_digest(self.stream())

    def mutated_rows(self) -> list[dict]:
        position, field_id, value = self.mutation
        rows = [dict(row) for row in self.rows]
        rows[position][field_id] = value
        return rows


@dataclass(frozen=True)
class RecordVector:
    """One committed record vector and the single value change that reddens it."""

    record: object
    mutation: dict

    def stream(self) -> bytes:
        return canonical_record_bytes(self.record)

    def digest(self) -> str:
        return canonical_digest(self.stream())

    def mutated_record(self) -> object:
        return replace(self.record, **self.mutation)


BASE_SCHEMA = schema(
    "daily-output-schema",
    (
        field("business-date", SchemaValueType.DATE, role="effective-date"),
        field("customer-id", SchemaValueType.STRING, role="business-key"),
        field("daily-amount", SchemaValueType.DECIMAL, precision=18, scale=2),
        field("is-active", SchemaValueType.BOOLEAN, role="publication-state"),
        field("payload", SchemaValueType.BINARY, role="opaque-payload"),
        field("record-count", SchemaValueType.INTEGER, role="control-total"),
        field("recorded-at", SchemaValueType.TIMESTAMP, role="observation-time"),
    ),
)
BASE_GRAIN = grain("customer-day", ("business-date", "customer-id"))
BASE_ORDERING = ordering("customer-day-order", (ascending("business-date"), ascending("customer-id")))
BASE_ROWS = (
    {
        "business-date": date(2026, 1, 6),
        "customer-id": "customer-002",
        "daily-amount": Decimal("18.40"),
        "is-active": False,
        "payload": b"\x00\x01\xfe\xff",
        "record-count": 7,
        "recorded-at": stamp(2026, 1, 6, 23, 59, 59, 999000),
    },
    {
        "business-date": date(2026, 1, 5),
        "customer-id": "customer-001",
        "daily-amount": Decimal("1234.50"),
        "is-active": True,
        "payload": b"",
        "record-count": 12,
        "recorded-at": stamp(2026, 1, 5, 9, 30, 0, 0),
    },
    {
        "business-date": date(2026, 1, 5),
        "customer-id": "customer-002",
        "daily-amount": Decimal("-0.75"),
        "is-active": True,
        "payload": b"\x7f",
        "record-count": 0,
        "recorded-at": stamp(2026, 1, 5, 12, 0, 0, 250000),
    },
)

ORDERED_SCHEMA = schema(
    "ranked-output-schema",
    (
        field("label", SchemaValueType.STRING, role="business-key"),
        field("rank", SchemaValueType.INTEGER, nullable=True, role="ranking"),
    ),
)
ORDERED_GRAIN = grain("label-grain", ("label",))
ORDERED_ROWS = (
    {"label": "second", "rank": 2},
    {"label": "unranked", "rank": None},
    {"label": "first", "rank": 1},
    {"label": "third", "rank": 3},
)

TIMESTAMP_SCHEMA = schema(
    "observation-schema",
    (
        field("label", SchemaValueType.STRING, role="business-key"),
        field("observed-at", SchemaValueType.TIMESTAMP, role="observation-time"),
    ),
)
TIMESTAMP_GRAIN = grain("observation-grain", ("label",))
TIMESTAMP_ORDERING = ordering("observation-order", (ascending("label"),))
TIMESTAMP_ROWS = (
    {"label": "midnight", "observed-at": stamp(2026, 1, 5, 0, 0, 0, 0)},
    {"label": "sub-second", "observed-at": stamp(2026, 1, 5, 6, 15, 30, 123000)},
    {"label": "end-of-day", "observed-at": stamp(2026, 1, 5, 23, 59, 59, 456000)},
)

SIGNED_ZERO_SCHEMA = schema(
    "signed-zero-schema",
    (
        field("label", SchemaValueType.STRING, role="business-key"),
        field("amount", SchemaValueType.DECIMAL, precision=9, scale=2),
    ),
)
SIGNED_ZERO_GRAIN = grain("signed-zero-grain", ("label",))
SIGNED_ZERO_ORDERING = ordering("signed-zero-order", (ascending("label"),))
SIGNED_ZERO_ROWS = (
    {"label": "negative-value", "amount": Decimal("-1.25")},
    {"label": "negative-zero", "amount": Decimal("-0.00")},
    {"label": "positive-zero", "amount": Decimal("0.00")},
)

UNICODE_SCHEMA = schema(
    "unicode-schema",
    (
        field("label", SchemaValueType.STRING, role="business-key"),
        field("note", SchemaValueType.STRING, role="approved-note"),
    ),
)
UNICODE_GRAIN = grain("unicode-grain", ("label",))
UNICODE_ORDERING = ordering("unicode-order", (ascending("label"),))
# The two notes carry the same text in precomposed and decomposed form.
UNICODE_PRECOMPOSED = "caf\u00e9 \u00e5"
UNICODE_DECOMPOSED = "cafe\u0301 a\u030a"
UNICODE_ROWS = (
    {"label": "precomposed", "note": UNICODE_PRECOMPOSED},
    {"label": "decomposed", "note": UNICODE_DECOMPOSED},
)

ROW_VECTORS: dict[str, RowVector] = {
    "base-row-stream": RowVector(
        schema=BASE_SCHEMA,
        grain=BASE_GRAIN,
        canonicalisation=canonicalisation("canonical-json-v1"),
        ordering=BASE_ORDERING,
        rows=BASE_ROWS,
        mutation=(0, "record-count", 8),
    ),
    "duplicate-rows": RowVector(
        schema=schema(
            "duplicate-schema",
            (
                field("customer-id", SchemaValueType.STRING, role="business-key"),
                field("record-count", SchemaValueType.INTEGER, role="control-total"),
            ),
        ),
        grain=grain("duplicate-grain", ("customer-id",), duplicates=True),
        canonicalisation=canonicalisation("canonical-json-v1", scale=None, precision=None, zone=None),
        ordering=ordering("duplicate-order", (ascending("customer-id"),)),
        rows=(
            {"customer-id": "customer-001", "record-count": 4},
            {"customer-id": "customer-002", "record-count": 9},
            {"customer-id": "customer-001", "record-count": 4},
        ),
        mutation=(2, "record-count", 5),
    ),
    "null-values": RowVector(
        schema=schema(
            "nullable-schema",
            (
                field("customer-id", SchemaValueType.STRING, role="business-key"),
                field("note", SchemaValueType.STRING, nullable=True, role="approved-note"),
                field("quantity", SchemaValueType.INTEGER, nullable=True, role="control-total"),
                field("settled-on", SchemaValueType.DATE, nullable=True, role="effective-date"),
            ),
        ),
        grain=grain("nullable-grain", ("customer-id",)),
        canonicalisation=canonicalisation("canonical-json-v1", scale=None, precision=None, zone=None),
        ordering=ordering("nullable-order", (ascending("customer-id"),)),
        rows=(
            {"customer-id": "customer-001", "note": None, "quantity": None, "settled-on": None},
            {"customer-id": "customer-002", "note": "settled", "quantity": 3, "settled-on": date(2026, 1, 5)},
        ),
        mutation=(0, "note", ""),
    ),
    "empty-zero-and-false": RowVector(
        schema=schema(
            "empty-value-schema",
            (
                field("amount", SchemaValueType.DECIMAL, precision=9, scale=2),
                field("is-active", SchemaValueType.BOOLEAN, role="publication-state"),
                field("label", SchemaValueType.STRING, role="business-key"),
                field("note", SchemaValueType.STRING, role="approved-note"),
                field("payload", SchemaValueType.BINARY, role="opaque-payload"),
                field("quantity", SchemaValueType.INTEGER, role="control-total"),
            ),
        ),
        grain=grain("empty-value-grain", ("label",)),
        canonicalisation=canonicalisation("canonical-json-v1", precision=None, zone=None),
        ordering=ordering("empty-value-order", (ascending("label"),)),
        rows=(
            {
                "amount": Decimal("0.00"),
                "is-active": False,
                "label": "empty",
                "note": "",
                "payload": b"",
                "quantity": 0,
            },
            {
                "amount": Decimal("1.00"),
                "is-active": True,
                "label": "populated",
                "note": "present",
                "payload": b"\x01",
                "quantity": 1,
            },
        ),
        mutation=(0, "is-active", True),
    ),
    "decimal-scale-four": RowVector(
        schema=schema(
            "decimal-scale-schema",
            (
                field("amount", SchemaValueType.DECIMAL, precision=18, scale=4),
                field("label", SchemaValueType.STRING, role="business-key"),
            ),
        ),
        grain=grain("decimal-scale-grain", ("label",)),
        canonicalisation=canonicalisation("canonical-json-v4", scale=4, precision=None, zone=None),
        ordering=ordering("decimal-scale-order", (ascending("label"),)),
        rows=(
            {"amount": Decimal("1.5"), "label": "short-scale"},
            {"amount": Decimal("-2.2500"), "label": "exact-scale"},
            {"amount": Decimal("0"), "label": "integral"},
        ),
        mutation=(0, "amount", Decimal("1.5001")),
    ),
    "timestamp-milliseconds": RowVector(
        schema=TIMESTAMP_SCHEMA,
        grain=TIMESTAMP_GRAIN,
        canonicalisation=canonicalisation("canonical-json-milliseconds", scale=None, precision="milliseconds"),
        ordering=TIMESTAMP_ORDERING,
        rows=TIMESTAMP_ROWS,
        mutation=(0, "observed-at", stamp(2026, 1, 5, 0, 0, 0, 1000)),
    ),
    "timestamp-microseconds": RowVector(
        schema=TIMESTAMP_SCHEMA,
        grain=TIMESTAMP_GRAIN,
        canonicalisation=canonicalisation("canonical-json-microseconds", scale=None, precision="microseconds"),
        ordering=TIMESTAMP_ORDERING,
        rows=TIMESTAMP_ROWS,
        mutation=(0, "observed-at", stamp(2026, 1, 5, 0, 0, 0, 1)),
    ),
    "timestamp-seconds": RowVector(
        schema=TIMESTAMP_SCHEMA,
        grain=TIMESTAMP_GRAIN,
        canonicalisation=canonicalisation("canonical-json-seconds", scale=None, precision="seconds"),
        ordering=TIMESTAMP_ORDERING,
        rows=(
            {"label": "midnight", "observed-at": stamp(2026, 1, 5, 0, 0, 0, 0)},
            {"label": "noon", "observed-at": stamp(2026, 1, 5, 12, 0, 0, 0)},
        ),
        mutation=(1, "observed-at", stamp(2026, 1, 5, 12, 0, 1, 0)),
    ),
    "signed-zero-positive": RowVector(
        schema=SIGNED_ZERO_SCHEMA,
        grain=SIGNED_ZERO_GRAIN,
        canonicalisation=canonicalisation(
            "canonical-json-positive-zero",
            precision=None,
            zone=None,
            signed_zero="positive-zero",
        ),
        ordering=SIGNED_ZERO_ORDERING,
        rows=SIGNED_ZERO_ROWS,
        mutation=(1, "amount", Decimal("0.01")),
    ),
    "signed-zero-preserved": RowVector(
        schema=SIGNED_ZERO_SCHEMA,
        grain=SIGNED_ZERO_GRAIN,
        canonicalisation=canonicalisation(
            "canonical-json-preserve-sign",
            precision=None,
            zone=None,
            signed_zero="preserve-sign",
        ),
        ordering=SIGNED_ZERO_ORDERING,
        rows=SIGNED_ZERO_ROWS,
        mutation=(1, "amount", Decimal("0.00")),
    ),
    "non-finite-tokens": RowVector(
        schema=schema(
            "non-finite-schema",
            (
                field("label", SchemaValueType.STRING, role="business-key"),
                field("measure", SchemaValueType.DECIMAL, precision=18, scale=2),
            ),
        ),
        grain=grain("non-finite-grain", ("label",)),
        canonicalisation=canonicalisation(
            "canonical-json-non-finite",
            precision=None,
            zone=None,
            non_finite="canonical-token",
        ),
        ordering=ordering("non-finite-order", (ascending("label"),)),
        rows=(
            {"label": "finite", "measure": Decimal("42.00")},
            {"label": "negative-infinity", "measure": Decimal("-Infinity")},
            {"label": "not-a-number", "measure": Decimal("NaN")},
            {"label": "positive-infinity", "measure": Decimal("Infinity")},
        ),
        mutation=(2, "measure", Decimal("Infinity")),
    ),
    "ordering-ascending-nulls-last": RowVector(
        schema=ORDERED_SCHEMA,
        grain=ORDERED_GRAIN,
        canonicalisation=canonicalisation("canonical-json-v1", scale=None, precision=None, zone=None),
        ordering=ordering("ascending-nulls-last", (ascending("rank", NullPlacement.LAST),)),
        rows=ORDERED_ROWS,
        mutation=(0, "rank", 5),
    ),
    "ordering-descending-nulls-first": RowVector(
        schema=ORDERED_SCHEMA,
        grain=ORDERED_GRAIN,
        canonicalisation=canonicalisation("canonical-json-v1", scale=None, precision=None, zone=None),
        ordering=ordering("descending-nulls-first", (descending("rank", NullPlacement.FIRST),)),
        rows=ORDERED_ROWS,
        mutation=(0, "rank", 5),
    ),
    "unicode-nfc": RowVector(
        schema=UNICODE_SCHEMA,
        grain=UNICODE_GRAIN,
        canonicalisation=canonicalisation(
            "canonical-json-nfc",
            normalisation="NFC",
            scale=None,
            precision=None,
            zone=None,
        ),
        ordering=UNICODE_ORDERING,
        rows=UNICODE_ROWS,
        mutation=(0, "note", "cafe a"),
    ),
    "unicode-nfd": RowVector(
        schema=UNICODE_SCHEMA,
        grain=UNICODE_GRAIN,
        canonicalisation=canonicalisation(
            "canonical-json-nfd",
            normalisation="NFD",
            scale=None,
            precision=None,
            zone=None,
        ),
        ordering=UNICODE_ORDERING,
        rows=UNICODE_ROWS,
        mutation=(0, "note", "cafe a"),
    ),
    "multiset-order": RowVector(
        schema=schema(
            "multiset-schema",
            (
                field("label", SchemaValueType.STRING, role="business-key"),
                field("quantity", SchemaValueType.INTEGER, role="control-total"),
            ),
        ),
        grain=grain("multiset-grain", ("label",), duplicates=True),
        canonicalisation=canonicalisation("canonical-json-v1", scale=None, precision=None, zone=None),
        ordering=None,
        rows=(
            {"label": "beta", "quantity": 2},
            {"label": "alpha", "quantity": 1},
            {"label": "beta", "quantity": 2},
        ),
        mutation=(1, "quantity", 4),
    ),
}


def identity(name: str) -> Identity:
    return Identity(identifier=name, version="v1", digest=f"{DIGEST_PREFIX}:{name}")


def evidence(name: str) -> EvidenceReference:
    return EvidenceReference(
        evidence_id=name,
        version="v1",
        digest=f"{DIGEST_PREFIX}:{name}",
        summary=f"approved {name}",
    )


BASE_VECTOR = ROW_VECTORS["base-row-stream"]
BASE_CONTENT_DIGEST = BASE_VECTOR.digest()
CASE_CONTEXT = ContextIdentity(
    context_id="daily-context",
    version="v1",
    digest=f"{DIGEST_PREFIX}:daily-context",
    logical_run_time="2026-01-06T00:00:00Z",
    cutoff_time="2026-01-05T23:59:59Z",
    timezone="UTC",
)
CASE_DATASET = FrozenDataset(
    dataset_id="input-dataset",
    version="v1",
    role=DatasetRole.INPUT,
    provenance=DatasetProvenance.SYNTHETIC,
    synthetic_provenance=None,
    content_digest=BASE_CONTENT_DIGEST,
    schema=BASE_SCHEMA,
    grain=BASE_GRAIN,
    canonicalisation=BASE_VECTOR.canonicalisation,
    row_count=len(BASE_ROWS),
    approved_summary="approved synthetic input",
)
CASE_OUTPUT = ExpectedOutput(
    output_id="daily-output",
    version="v1",
    origin=ExpectedOutputOrigin.SYNTHETIC_DERIVATION,
    provenance=DatasetProvenance.SYNTHETIC,
    content_digest=BASE_CONTENT_DIGEST,
    schema=BASE_SCHEMA,
    grain=BASE_GRAIN,
    canonicalisation=BASE_VECTOR.canonicalisation,
    row_count=len(BASE_ROWS),
    format_digest=f"{DIGEST_PREFIX}:daily-output-format",
    approved_summary="approved synthetic expected output",
)
CASE_COMPARISON = ComparisonDeclaration(
    comparison_id="daily-output-comparison",
    version="v1",
    dimensions=(ComparisonDimension.SCHEMA, ComparisonDimension.VALUE, ComparisonDimension.ORDERING),
    schema=BASE_SCHEMA,
    grain=BASE_GRAIN,
    canonicalisation=BASE_VECTOR.canonicalisation,
    aggregates=(),
    ordering=BASE_ORDERING,
    replay=None,
)
VERIFICATION_CASE = VerificationCase(
    case_id="daily-output-case",
    version="v1",
    mode=VerificationMode.GREENFIELD,
    frozen_datasets=(CASE_DATASET,),
    expected_outputs=(CASE_OUTPUT,),
    context=CASE_CONTEXT,
    comparison_policy=ComparisonPolicy(
        policy_id="daily-output-policy",
        version="v1",
        digest=f"{DIGEST_PREFIX}:daily-output-policy",
        clauses=(
            ParityClause(
                clause_id="daily-output-parity",
                version="v1",
                expected_output_id="daily-output",
                comparison=CASE_COMPARISON,
                required_evidence=(evidence("expected-output-approval"),),
            ),
        ),
        tolerances=(),
        exclusions=(),
        warning_bands=(),
    ),
    lineage=LineageDefinition(
        lineage_id="daily-output-lineage",
        version="v1",
        checkpoints=(),
        output_bindings=(OutputLineageBinding("daily-output", None),),
    ),
    assurance=AssuranceDeclaration(
        assurance_id="daily-output-assurance",
        version="v1",
        declared_level=AssuranceLevel.DECLARED,
        owner_presented_evidence=(),
        environment_certificate_claims=(),
    ),
    diagnostic_strength=DiagnosticStrength.OUTPUT_ONLY,
)
VERIFICATION_RESULT = VerificationResult(
    result_id="daily-output-result",
    version="v1",
    case=identity("daily-output-case"),
    candidate=CandidateIdentity(
        candidate_id="daily-output-candidate",
        version="v1",
        artifact_digest=f"{DIGEST_PREFIX}:daily-output-candidate",
    ),
    context=CASE_CONTEXT,
    independent_receipts=(
        IndependentlyDerivedReceipt(
            receipt_id="input-receipt",
            version="v1",
            subject=ReceiptSubject.INPUT,
            subject_identity=identity("input-dataset"),
            observed_digest=BASE_CONTENT_DIGEST,
            derived_by=identity("evidence-repository"),
            evidence=(evidence("input-receipt-evidence"),),
        ),
    ),
    actual_outputs=(
        ActualOutput(
            output_id="daily-output",
            version="v1",
            content_digest=BASE_CONTENT_DIGEST,
            schema=BASE_SCHEMA,
            grain=BASE_GRAIN,
            canonicalisation=BASE_VECTOR.canonicalisation,
            row_count=len(BASE_ROWS),
            format_digest=f"{DIGEST_PREFIX}:daily-output-format",
            approved_summary="observed candidate output",
        ),
    ),
    clause_outcomes=(
        ClauseOutcome(
            outcome_id="daily-output-parity-outcome",
            version="v1",
            clause=identity("daily-output-parity"),
            family=ClauseFamily.PARITY,
            status=VerificationStatus.PASS,
            compared_dimensions=(ComparisonDimension.SCHEMA, ComparisonDimension.VALUE),
            expected_evidence=(evidence("expected-output-approval"),),
            observed_evidence=(evidence("candidate-output-observation"),),
        ),
    ),
    status=VerificationStatus.PASS,
    evidence=(evidence("candidate-run-evidence"),),
    diagnostic_strength=DiagnosticStrength.OUTPUT_ONLY,
    repeat_run_identity=RepeatRunIdentity(
        repeat_run_id="daily-output-repeat",
        version="v1",
        digest=f"{DIGEST_PREFIX}:daily-output-repeat",
    ),
)

RECORD_VECTORS: dict[str, RecordVector] = {
    "case-record": RecordVector(
        record=VERIFICATION_CASE,
        mutation={"diagnostic_strength": DiagnosticStrength.CHECKPOINTED},
    ),
    "result-record": RecordVector(
        record=VERIFICATION_RESULT,
        mutation={"status": VerificationStatus.FAIL},
    ),
}

ROW_VECTOR_NAMES = sorted(ROW_VECTORS)
RECORD_VECTOR_NAMES = sorted(RECORD_VECTORS)
ALL_VECTOR_NAMES = sorted([*ROW_VECTOR_NAMES, *RECORD_VECTOR_NAMES])


def vector(name: str) -> RowVector | RecordVector:
    return ROW_VECTORS[name] if name in ROW_VECTORS else RECORD_VECTORS[name]


def committed_index() -> dict:
    return json.loads(DIGEST_INDEX.read_text(encoding="utf-8"))


def committed_bytes(name: str) -> bytes:
    return (FIXTURES / committed_index()["vectors"][name]["file"]).read_bytes()


def frames(stream: bytes) -> list[bytes]:
    """Read a length-prefixed stream back, proving the framing is unambiguous."""
    payloads: list[bytes] = []
    position = 0
    while position < len(stream):
        separator = stream.index(b":", position)
        length = int(stream[position:separator].decode("ascii"))
        start = separator + 1
        payloads.append(stream[start : start + length])
        assert stream[start + length : start + length + 1] == b"\n"
        position = start + length + 1
    return payloads


@pytest.mark.parametrize("name", ALL_VECTOR_NAMES)
def test_committed_vector_bytes_and_digest_match_the_module(name):
    index = committed_index()["vectors"][name]
    produced = vector(name).stream()

    assert produced == committed_bytes(name)
    assert canonical_digest(produced) == index["digest"]


def test_every_committed_file_is_named_by_the_index_and_nothing_else():
    index = committed_index()["vectors"]
    files = sorted(path.name for path in VECTOR_DIRECTORY.iterdir())

    assert sorted(index) == ALL_VECTOR_NAMES
    assert files == sorted(f"{name}.canonical" for name in ALL_VECTOR_NAMES)


@pytest.mark.parametrize("name", ALL_VECTOR_NAMES)
def test_committed_vectors_are_plain_ascii_lines(name):
    payload = committed_bytes(name)

    payload.decode("ascii")
    assert b"\r" not in payload
    assert payload.endswith(b"\n")


@pytest.mark.parametrize("name", ROW_VECTOR_NAMES)
def test_committed_row_streams_read_back_frame_by_frame(name):
    payloads = frames(committed_bytes(name))

    assert len(payloads) == len(ROW_VECTORS[name].rows) + 1
    assert core.CANONICAL_ROW_STREAM_FORM.encode("ascii") in payloads[0]


@pytest.mark.parametrize("name", ALL_VECTOR_NAMES)
def test_a_second_emission_is_byte_identical(name):
    subject = vector(name)

    assert subject.stream() == subject.stream()


@pytest.mark.parametrize("seed", ["0", "1"])
def test_a_fresh_interpreter_emits_the_committed_bytes(seed):
    script = (
        "import json, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "import test_canonical_identity as vectors\n"
        "emitted = {name: vectors.vector(name).stream().hex() for name in vectors.ALL_VECTOR_NAMES}\n"
        "sys.stdout.write(json.dumps(emitted, sort_keys=True))\n"
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    environment["PYTHONHASHSEED"] = seed
    completed = subprocess.run(
        [sys.executable, "-c", script, str(Path(__file__).parent)],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {name: committed_bytes(name).hex() for name in ALL_VECTOR_NAMES}


@pytest.mark.parametrize("name", ROW_VECTOR_NAMES)
def test_one_value_change_reddens_the_row_vector(name):
    subject = ROW_VECTORS[name]
    mutated = subject.stream(subject.mutated_rows())

    assert mutated != committed_bytes(name)
    assert canonical_digest(mutated) != committed_index()["vectors"][name]["digest"]


@pytest.mark.parametrize("name", RECORD_VECTOR_NAMES)
def test_one_value_change_reddens_the_record_vector(name):
    subject = RECORD_VECTORS[name]
    mutated = canonical_record_bytes(subject.mutated_record())

    assert mutated != committed_bytes(name)
    assert canonical_digest(mutated) != committed_index()["vectors"][name]["digest"]


def test_one_byte_change_in_a_copied_vector_reddens_the_comparison(tmp_path):
    name = "base-row-stream"
    copy = tmp_path / "base-row-stream.canonical"
    original = committed_bytes(name)
    position = original.index(b"customer-001")
    copy.write_bytes(original[:position] + b"C" + original[position + 1 :])

    assert len(copy.read_bytes()) == len(original)
    assert copy.read_bytes() != ROW_VECTORS[name].stream()
    assert canonical_digest(copy.read_bytes()) != committed_index()["vectors"][name]["digest"]


@pytest.mark.parametrize("name", ROW_VECTOR_NAMES)
def test_input_row_order_never_reaches_the_bytes(name):
    subject = ROW_VECTORS[name]
    reversed_rows = list(reversed(subject.rows))

    assert subject.stream(reversed_rows) == committed_bytes(name)


def test_a_different_ordering_declaration_changes_the_bytes():
    ascending_stream = ROW_VECTORS["ordering-ascending-nulls-last"].stream()
    descending_stream = ROW_VECTORS["ordering-descending-nulls-first"].stream()

    assert ascending_stream != descending_stream
    assert sorted(frames(ascending_stream)[1:]) == sorted(frames(descending_stream)[1:])
    assert frames(ascending_stream)[1:] == list(reversed(frames(descending_stream)[1:]))


def test_the_declared_null_placement_moves_the_null_row():
    subject = ROW_VECTORS["ordering-ascending-nulls-last"]
    nulls_first = replace(
        subject,
        ordering=ordering("ascending-nulls-first", (ascending("rank", NullPlacement.FIRST),)),
    )

    assert b"null" in frames(subject.stream())[-1]
    assert b"null" in frames(nulls_first.stream())[1]


def test_duplicate_rows_are_retained_and_adjacent():
    payloads = frames(ROW_VECTORS["duplicate-rows"].stream())[1:]

    assert len(payloads) == 3
    assert payloads[0] == payloads[1]


def test_a_repeated_key_is_refused_when_the_grain_forbids_duplicates():
    permitted = ROW_VECTORS["duplicate-rows"]
    forbidding = replace(permitted, grain=grain("unique-customer-grain", ("customer-id",)))
    distinct = [
        {"customer-id": "customer-001", "record-count": 4},
        {"customer-id": "customer-002", "record-count": 9},
    ]

    assert len(frames(permitted.stream())) == len(permitted.rows) + 1
    assert len(frames(forbidding.stream(distinct))) == len(distinct) + 1
    with pytest.raises(CanonicalisationRefusal) as refusal:
        forbidding.stream()
    assert refusal.value.reason is RefusalReason.DUPLICATE_KEY_NOT_PERMITTED


def test_a_repeated_key_is_read_in_the_declared_canonical_form():
    forbidding = replace(
        ROW_VECTORS["unicode-nfc"],
        grain=grain("unique-note-grain", ("note",)),
        ordering=NOTE_ORDERING,
    )

    assert forbidding.stream([{"label": "one", "note": ACUTE_COMPOSED}])
    with pytest.raises(CanonicalisationRefusal) as refusal:
        forbidding.stream(
            [
                {"label": "one", "note": ACUTE_COMPOSED},
                {"label": "two", "note": ACUTE_DECOMPOSED},
            ]
        )
    assert refusal.value.reason is RefusalReason.DUPLICATE_KEY_NOT_PERMITTED


@pytest.mark.parametrize(
    "declared",
    [
        grain("undeclared-key-grain", ("undeclared-field",)),
        grain("keyless-unique-grain", ()),
    ],
)
def test_a_grain_that_cannot_be_applied_is_refused(declared):
    subject = ROW_VECTORS["signed-zero-positive"]

    assert subject.stream()
    with pytest.raises(CanonicalisationRefusal) as refusal:
        replace(subject, grain=declared).stream()
    assert refusal.value.reason is RefusalReason.INVALID_DECLARATION


def test_the_multiset_rule_and_a_declared_ordering_never_share_bytes():
    subject = ROW_VECTORS["multiset-order"]
    declared = replace(subject, ordering=ordering("multiset-order-declared", (ascending("label"),)))

    assert subject.stream() != declared.stream()
    assert sorted(frames(subject.stream())[1:]) == sorted(frames(declared.stream())[1:])


def test_the_declared_unicode_normalisation_changes_the_bytes():
    composed = ROW_VECTORS["unicode-nfc"].stream()
    decomposed = ROW_VECTORS["unicode-nfd"].stream()

    escape = core.ESCAPE
    composed_note = f'"note":"caf{escape}u00e9 {escape}u00e5"'.encode("ascii")
    decomposed_note = f'"note":"cafe{escape}u0301 a{escape}u030a"'.encode("ascii")

    assert composed != decomposed
    assert composed.count(composed_note) == 2
    assert decomposed.count(decomposed_note) == 2


ACUTE_COMPOSED = "caf\u00e9"
ACUTE_DECOMPOSED = "cafe\u0301"
RING_COMPOSED = "\u00e5ngstrom"
RING_DECOMPOSED = "a\u030angstrom"
PLAIN_NOTE = "cafz"
NOTE_ORDERING = ordering("note-order", (ascending("note"),), ("label",))
# The declared form decides which row leads, so a normalisation that never
# reached the ordering would show here.
LEADING_LABEL = {"NFC": b'"label":"plain"', "NFD": b'"label":"ring"'}


def normalisation_rows(acute: str, ring: str) -> tuple[dict, ...]:
    return (
        {"label": "acute", "note": acute},
        {"label": "plain", "note": PLAIN_NOTE},
        {"label": "ring", "note": ring},
    )


@pytest.mark.parametrize("declared", ["NFC", "NFD"])
def test_the_declared_normalisation_reaches_the_declared_ordering(declared):
    composed = replace(
        ROW_VECTORS["unicode-nfc"],
        canonicalisation=canonicalisation(
            "canonical-json-ordered-notes",
            normalisation=declared,
            scale=None,
            precision=None,
            zone=None,
        ),
        ordering=NOTE_ORDERING,
        rows=normalisation_rows(ACUTE_COMPOSED, RING_COMPOSED),
    )
    decomposed = replace(composed, rows=normalisation_rows(ACUTE_DECOMPOSED, RING_DECOMPOSED))
    mixed = replace(composed, rows=normalisation_rows(ACUTE_COMPOSED, RING_DECOMPOSED))

    assert composed.stream() == decomposed.stream() == mixed.stream()
    assert composed.digest() == decomposed.digest() == mixed.digest()
    assert LEADING_LABEL[declared] in frames(composed.stream())[1]


def test_the_declared_signed_zero_representation_changes_the_bytes():
    positive = ROW_VECTORS["signed-zero-positive"].stream()
    preserved = ROW_VECTORS["signed-zero-preserved"].stream()

    assert positive != preserved
    assert b'"amount":-0.00' in preserved
    assert b'"amount":-0.00' not in positive


def test_the_declared_timestamp_precision_changes_the_bytes():
    assert ROW_VECTORS["timestamp-milliseconds"].stream() != ROW_VECTORS["timestamp-microseconds"].stream()
    assert b"T00:00:00.000Z" in ROW_VECTORS["timestamp-milliseconds"].stream()
    assert b"T00:00:00.000000Z" in ROW_VECTORS["timestamp-microseconds"].stream()
    assert b"T00:00:00Z" in ROW_VECTORS["timestamp-seconds"].stream()


def test_the_declared_non_finite_tokens_are_written():
    stream = ROW_VECTORS["non-finite-tokens"].stream()

    assert b'"measure":"Infinity"' in stream
    assert b'"measure":"-Infinity"' in stream
    assert b'"measure":"NaN"' in stream


def test_the_digest_index_states_the_one_hash_declaration():
    index = committed_index()

    assert index["hash_algorithm"] == HASH_ALGORITHM == "blake2b"
    assert index["hash_digest_size_bytes"] == HASH_DIGEST_SIZE_BYTES == 32
    assert index["digest_prefix"] == DIGEST_PREFIX
    assert index["canonical_row_stream_form"] == core.CANONICAL_ROW_STREAM_FORM
    assert index["canonical_record_form"] == core.CANONICAL_RECORD_FORM
    assert all(entry["digest"].startswith(f"{DIGEST_PREFIX}:") for entry in index["vectors"].values())
    assert all(len(entry["digest"].split(":")[1]) == HASH_DIGEST_SIZE_BYTES * 2 for entry in index["vectors"].values())


def test_the_provenance_declaration_sits_beside_the_vectors():
    provenance = json.loads(PROVENANCE.read_text(encoding="utf-8"))

    assert provenance["produced_by"] == "evorthon_data.verification.core.canonical"
    assert provenance["vector_definitions"] == "tests/verification/test_canonical_identity.py"
    assert provenance["hash_algorithm"] == HASH_ALGORITHM
    assert provenance["hash_digest_size_bytes"] == HASH_DIGEST_SIZE_BYTES
    assert provenance["encoding"] == "ascii"
    assert provenance["line_endings"] == "lf"


def test_dataset_digest_is_the_digest_of_the_canonical_stream():
    subject = ROW_VECTORS["base-row-stream"]
    produced = dataset_digest(
        subject.rows,
        schema=subject.schema,
        grain=subject.grain,
        canonicalisation=subject.canonicalisation,
        ordering=subject.ordering,
    )

    assert produced == canonical_digest(subject.stream())
    assert produced == committed_index()["vectors"]["base-row-stream"]["digest"]


def test_a_frozen_dataset_digest_matches_its_recorded_content_digest():
    subject = ROW_VECTORS["base-row-stream"]

    assert frozen_dataset_digest(CASE_DATASET, subject.rows, ordering=subject.ordering) == CASE_DATASET.content_digest
    assert frozen_dataset_digest(CASE_DATASET, subject.mutated_rows(), ordering=subject.ordering) != CASE_DATASET.content_digest


def test_case_and_result_digests_come_from_the_one_record_routine():
    assert case_digest(VERIFICATION_CASE) == record_digest(VERIFICATION_CASE)
    assert result_digest(VERIFICATION_RESULT) == record_digest(VERIFICATION_RESULT)
    assert case_digest(VERIFICATION_CASE) != result_digest(VERIFICATION_RESULT)
    with pytest.raises(CanonicalisationRefusal) as refusal:
        case_digest(VERIFICATION_RESULT)
    assert refusal.value.reason is RefusalReason.UNSUPPORTED_TYPE


def stream_of(subject: RowVector, rows) -> bytes:
    return subject.stream(rows)


def test_an_unsupported_value_type_is_refused_and_a_declared_one_is_not():
    subject = ROW_VECTORS["signed-zero-positive"]
    accepted = [{"label": "positive-zero", "amount": Decimal("0.00")}]
    offending = [{"label": "positive-zero", "amount": 0.0}]

    assert stream_of(subject, accepted)
    with pytest.raises(CanonicalisationRefusal) as refusal:
        stream_of(subject, offending)
    assert refusal.value.reason is RefusalReason.UNSUPPORTED_TYPE


def test_a_record_outside_the_domain_inventory_is_refused():
    assert canonical_record_bytes(CASE_DATASET)
    with pytest.raises(CanonicalisationRefusal) as refusal:
        canonical_record_bytes({"case_id": "daily-output-case"})
    assert refusal.value.reason is RefusalReason.UNSUPPORTED_TYPE


def test_a_decimal_beyond_the_declared_scale_is_refused():
    subject = ROW_VECTORS["signed-zero-positive"]
    accepted = [{"label": "exact", "amount": Decimal("1.25")}]
    offending = [{"label": "too-fine", "amount": Decimal("1.253")}]

    assert stream_of(subject, accepted)
    with pytest.raises(CanonicalisationRefusal) as refusal:
        stream_of(subject, offending)
    assert refusal.value.reason is RefusalReason.VALUE_OUTSIDE_DECLARED_REPRESENTATION


def test_a_decimal_beyond_the_declared_field_precision_is_refused():
    subject = ROW_VECTORS["signed-zero-positive"]
    accepted = [{"label": "at-the-limit", "amount": Decimal("1234567.89")}]
    offending = [{"label": "one-digit-too-many", "amount": Decimal("12345678.90")}]

    assert stream_of(subject, accepted)
    with pytest.raises(CanonicalisationRefusal) as refusal:
        stream_of(subject, offending)
    assert refusal.value.reason is RefusalReason.VALUE_OUTSIDE_DECLARED_REPRESENTATION


def test_the_declared_field_scale_governs_the_precision_count():
    subject = replace(
        ROW_VECTORS["signed-zero-positive"],
        schema=schema(
            "narrow-decimal-schema",
            (
                field("label", SchemaValueType.STRING, role="business-key"),
                field("amount", SchemaValueType.DECIMAL, precision=4, scale=2),
            ),
        ),
        canonicalisation=canonicalisation("canonical-json-wider-scale", scale=4, precision=None, zone=None),
    )
    accepted = [{"label": "at-the-limit", "amount": Decimal("99.99")}]
    offending = [{"label": "one-digit-too-many", "amount": Decimal("100.00")}]

    assert b'"amount":99.9900' in stream_of(subject, accepted)
    with pytest.raises(CanonicalisationRefusal) as refusal:
        stream_of(subject, offending)
    assert refusal.value.reason is RefusalReason.VALUE_OUTSIDE_DECLARED_REPRESENTATION


def test_a_timestamp_finer_than_the_declared_precision_is_refused():
    subject = ROW_VECTORS["timestamp-milliseconds"]
    accepted = [{"label": "exact", "observed-at": stamp(2026, 1, 5, 0, 0, 0, 123000)}]
    offending = [{"label": "too-fine", "observed-at": stamp(2026, 1, 5, 0, 0, 0, 123456)}]

    assert stream_of(subject, accepted)
    with pytest.raises(CanonicalisationRefusal) as refusal:
        stream_of(subject, offending)
    assert refusal.value.reason is RefusalReason.VALUE_OUTSIDE_DECLARED_REPRESENTATION


@pytest.mark.parametrize(
    "offending",
    [
        datetime(2026, 1, 5, 0, 0, 0),
        datetime(2026, 1, 5, 0, 0, 0, tzinfo=timezone(timedelta(hours=1))),
    ],
)
def test_a_timestamp_outside_the_declared_zone_is_refused(offending):
    subject = ROW_VECTORS["timestamp-milliseconds"]

    assert stream_of(subject, [{"label": "declared", "observed-at": stamp(2026, 1, 5, 0, 0, 0, 0)}])
    with pytest.raises(CanonicalisationRefusal) as refusal:
        stream_of(subject, [{"label": "undeclared-zone", "observed-at": offending}])
    assert refusal.value.reason is RefusalReason.VALUE_OUTSIDE_DECLARED_REPRESENTATION


@pytest.mark.parametrize("offending", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_a_non_finite_number_is_refused_when_the_declaration_rejects_one(offending):
    subject = ROW_VECTORS["signed-zero-positive"]

    assert stream_of(subject, [{"label": "finite", "amount": Decimal("1.00")}])
    with pytest.raises(CanonicalisationRefusal) as refusal:
        stream_of(subject, [{"label": "non-finite", "amount": offending}])
    assert refusal.value.reason is RefusalReason.NON_FINITE_NOT_PERMITTED


def test_a_value_that_does_not_compare_is_refused_by_the_declared_ordering():
    subject = ROW_VECTORS["non-finite-tokens"]
    ordered_by_measure = replace(
        subject,
        ordering=ordering("measure-order", (ascending("measure"),)),
    )
    finite_rows = [{"label": "finite", "measure": Decimal("1.00")}]

    assert stream_of(ordered_by_measure, finite_rows)
    with pytest.raises(CanonicalisationRefusal) as refusal:
        ordered_by_measure.stream()
    assert refusal.value.reason is RefusalReason.ORDERING_NOT_APPLICABLE


@pytest.mark.parametrize(
    "declared",
    [
        ordering("undeclared-field-order", (ascending("undeclared-field"),)),
        ordering("empty-order", ()),
        ordering("undeclared-tie-breaker", (ascending("label"),), ("undeclared-field",)),
    ],
)
def test_an_ordering_that_cannot_be_applied_is_refused(declared):
    subject = ROW_VECTORS["signed-zero-positive"]

    assert subject.stream()
    with pytest.raises(CanonicalisationRefusal) as refusal:
        replace(subject, ordering=declared).stream()
    assert refusal.value.reason is RefusalReason.ORDERING_NOT_APPLICABLE


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"normalisation": "NFKC"}, RefusalReason.UNDECLARED_REPRESENTATION),
        ({"signed_zero": "negative-zero"}, RefusalReason.UNDECLARED_REPRESENTATION),
        ({"non_finite": "permit"}, RefusalReason.UNDECLARED_REPRESENTATION),
        ({"scale": None}, RefusalReason.UNDECLARED_REPRESENTATION),
        ({"scale": -1}, RefusalReason.INVALID_DECLARATION),
    ],
)
def test_a_declaration_the_core_cannot_honour_is_refused_rather_than_defaulted(changes, reason):
    subject = ROW_VECTORS["signed-zero-positive"]
    settings = {"precision": None, "zone": None, **changes}

    assert subject.stream()
    with pytest.raises(CanonicalisationRefusal) as refusal:
        replace(subject, canonicalisation=canonicalisation("undeclared", **settings)).stream()
    assert refusal.value.reason is reason


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"precision": None}, RefusalReason.UNDECLARED_REPRESENTATION),
        ({"precision": "nanoseconds"}, RefusalReason.UNDECLARED_REPRESENTATION),
        ({"zone": None}, RefusalReason.UNDECLARED_REPRESENTATION),
        ({"zone": "Europe/London"}, RefusalReason.UNDECLARED_REPRESENTATION),
    ],
)
def test_a_silent_timestamp_declaration_is_refused_rather_than_defaulted(changes, reason):
    subject = ROW_VECTORS["timestamp-milliseconds"]
    settings = {"scale": None, **changes}

    assert subject.stream()
    with pytest.raises(CanonicalisationRefusal) as refusal:
        replace(subject, canonicalisation=canonicalisation("undeclared", **settings)).stream()
    assert refusal.value.reason is reason


def test_a_null_representation_the_core_cannot_honour_is_refused():
    subject = ROW_VECTORS["null-values"]
    declared = subject.canonicalisation

    assert subject.stream()
    with pytest.raises(CanonicalisationRefusal) as refusal:
        replace(subject, canonicalisation=replace(declared, null_representation="empty-string")).stream()
    assert refusal.value.reason is RefusalReason.UNDECLARED_REPRESENTATION


@pytest.mark.parametrize(
    "offending",
    [
        {"label": "extra", "amount": Decimal("1.00"), "undeclared": "value"},
        {"label": "missing"},
    ],
)
def test_an_undeclared_or_missing_row_field_is_refused(offending):
    subject = ROW_VECTORS["signed-zero-positive"]

    assert stream_of(subject, [{"label": "complete", "amount": Decimal("1.00")}])
    with pytest.raises(CanonicalisationRefusal) as refusal:
        stream_of(subject, [offending])
    assert refusal.value.reason is RefusalReason.UNDECLARED_FIELD


def test_a_null_in_a_field_declared_not_nullable_is_refused():
    subject = ROW_VECTORS["null-values"]
    accepted = [{"customer-id": "customer-001", "note": None, "quantity": None, "settled-on": None}]
    offending = [{"customer-id": None, "note": None, "quantity": None, "settled-on": None}]

    assert stream_of(subject, accepted)
    with pytest.raises(CanonicalisationRefusal) as refusal:
        stream_of(subject, offending)
    assert refusal.value.reason is RefusalReason.VALUE_OUTSIDE_DECLARED_REPRESENTATION


@pytest.mark.parametrize(
    "declared",
    [
        schema("empty-schema", ()),
        schema(
            "repeated-field-schema",
            (
                field("label", SchemaValueType.STRING, role="business-key"),
                field("label", SchemaValueType.INTEGER, role="control-total"),
            ),
        ),
    ],
)
def test_a_schema_that_cannot_be_written_is_refused(declared):
    subject = ROW_VECTORS["signed-zero-positive"]

    assert subject.stream()
    with pytest.raises(CanonicalisationRefusal) as refusal:
        stream_of(replace(subject, schema=declared), [])
    assert refusal.value.reason is RefusalReason.INVALID_DECLARATION


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
    imports: set[str] = set()
    for statement in ast.walk(tree):
        if isinstance(statement, ast.Import):
            imports.update(alias.name for alias in statement.names)
        elif isinstance(statement, ast.ImportFrom):
            if statement.level:
                imports.add(f"evorthon_data.verification.core.{statement.module}")
            elif statement.module:
                imports.add(statement.module)
    return imports


@pytest.mark.parametrize("module", ["canonical.py", "reconciliation.py", "localisation.py", "fault.py", "__init__.py"])
def test_the_core_imports_only_the_domain_and_a_narrow_standard_library(module):
    path = ROOT / "src" / "evorthon_data" / "verification" / "core" / module

    assert imported_modules(path) <= ALLOWED_CORE_IMPORTS


@pytest.mark.parametrize("forbidden", FORBIDDEN_CORE_TEXT)
def test_the_core_reads_no_clock_environment_or_file(forbidden):
    source = (ROOT / "src" / "evorthon_data" / "verification" / "core" / "canonical.py").read_text(encoding="utf-8")

    assert forbidden not in source
