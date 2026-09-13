"""Determinism, declared refusals and labelled provenance for generated data."""
# evorthon-verifies: EVD-README-048
from __future__ import annotations

import ast
import csv
import importlib.util
import io
import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from evorthon_data.synthetic import generator as module
from evorthon_data.synthetic import (
    CategoryWeight,
    FieldConstraint,
    GenerationRefusal,
    GenerationRefusalReason,
    GenerationRequest as Request,
    KeyList,
    SyntheticDatasetConstraints,
    ValueRule,
    constraints_bytes,
    generate,
    read_request as read_request_document,
    written_value,
)
from evorthon_data.verification.core import canonical_digest, dataset_digest
from evorthon_data.verification.domain.contracts import (
    DatasetProvenance,
    DatasetRole,
    GrainDeclaration,
    Identity,
    SchemaDeclaration,
    SchemaField,
    SchemaValueType,
)

ROOT = Path(__file__).parents[2]
GENERATOR_SOURCE = ROOT / "src" / "evorthon_data" / "synthetic" / "generator.py"
REQUEST_SOURCE = ROOT / "src" / "evorthon_data" / "synthetic" / "request.py"
FIXTURES = ROOT / "tests" / "fixtures" / "synthetic"
CONSTRAINT_DIRECTORY = FIXTURES / "constraints"
PROVENANCE = FIXTURES / "provenance.json"
FIXTURE_NAMES = ["customer-orders", "region-reference"]
SEED = "campaign-seed-one"
OTHER_SEED = "campaign-seed-two"
GENERATOR_VERSION = "1.0.0"

ALLOWED_IMPORTS = {
    "__future__",
    "collections.abc",
    "csv",
    "dataclasses",
    "datetime",
    "decimal",
    "enum",
    "evorthon_data.verification.core",
    "evorthon_data.verification.domain.contracts",
    "io",
    "random",
    "types",
}
FORBIDDEN_SOURCE_TEXT = (".now(", ".today(", ".utcnow(", "urandom", "getenv", "os.environ", "open(")
# The reader of the request document owns that document's form, so it is the
# one module of this component allowed to read the written form. It reaches no
# file and no environment either: it is given the document as text.
REQUEST_ALLOWED_IMPORTS = {
    "__future__",
    "collections.abc",
    "dataclasses",
    "datetime",
    "decimal",
    "evorthon_data.synthetic.generator",
    "evorthon_data.verification.domain.contracts",
    "json",
}


def read_request(name: str) -> Request:
    """Read one committed request document through the product's own reader."""
    return read_request_document((CONSTRAINT_DIRECTORY / f"{name}.json").read_text(encoding="ascii"))


def run(request: Request, seed: str = SEED, version: str = GENERATOR_VERSION):
    return generate(request.schema, request.grain, request.keys, request.constraints, seed, version)


def refuse(request: Request, seed: str = SEED, version: str = GENERATOR_VERSION) -> GenerationRefusalReason:
    with pytest.raises(GenerationRefusal) as caught:
        run(request, seed, version)
    return caught.value.reason


def field_index(request: Request) -> dict:
    return {field.field_id: field for field in request.schema.fields}


def constraint_index(request: Request) -> dict:
    return {constraint.field_id: constraint for constraint in request.constraints.fields}


def with_field(request: Request, target: str, **changes) -> Request:
    fields = tuple(
        replace(constraint, **changes) if constraint.field_id == target else constraint
        for constraint in request.constraints.fields
    )
    return replace(request, constraints=replace(request.constraints, fields=fields))


def with_schema_field(request: Request, target: str, **changes) -> Request:
    fields = tuple(
        replace(field, **changes) if field.field_id == target else field
        for field in request.schema.fields
    )
    return replace(request, schema=replace(request.schema, fields=fields))


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_the_result_is_a_labelled_synthetic_frozen_dataset(name):
    request = read_request(name)

    result = run(request)

    dataset = result.dataset
    assert dataset.provenance is DatasetProvenance.SYNTHETIC
    assert dataset.dataset_id == request.constraints.dataset_id
    assert dataset.version == request.constraints.version
    assert dataset.role is request.constraints.role
    assert dataset.approved_summary == request.constraints.approved_summary
    assert dataset.schema == request.schema
    assert dataset.grain == request.grain
    assert dataset.row_count == request.constraints.row_count == len(result.rows)
    provenance = dataset.synthetic_provenance
    assert provenance.generator_id == module.GENERATOR_ID
    assert provenance.generator_version == GENERATOR_VERSION
    assert provenance.seed == SEED
    assert provenance.constraints_digest == canonical_digest(
        constraints_bytes(request.constraints, field_index(request))
    )
    assert provenance.constrained_by == tuple(key_list.source for key_list in request.keys)


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_the_content_digest_is_the_core_dataset_digest_under_the_multiset_rule(name):
    request = read_request(name)

    result = run(request)

    assert result.dataset.content_digest == dataset_digest(
        result.rows,
        schema=request.schema,
        grain=request.grain,
        canonicalisation=result.dataset.canonicalisation,
        ordering=None,
    )


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_the_same_declarations_and_seed_produce_identical_bytes_and_digest(name):
    request = read_request(name)

    first = run(request)
    second = run(read_request(name))

    assert first.csv_bytes == second.csv_bytes
    assert first.dataset == second.dataset
    assert first.rows == second.rows


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_a_different_seed_changes_the_rows_and_keeps_the_schema_grain_and_header(name):
    request = read_request(name)

    first = run(request)
    other = run(request, seed=OTHER_SEED)

    assert other.csv_bytes != first.csv_bytes
    assert other.dataset.content_digest != first.dataset.content_digest
    assert other.csv_bytes.split(b"\n")[0] == first.csv_bytes.split(b"\n")[0]
    assert other.dataset.schema == first.dataset.schema
    assert other.dataset.grain == first.dataset.grain
    assert other.dataset.row_count == first.dataset.row_count
    assert other.dataset.synthetic_provenance.seed == OTHER_SEED


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_every_foreign_key_value_is_present_in_the_supplied_key_list(name):
    request = read_request(name)
    supplied = {key_list.key_list_id: set(key_list.values) for key_list in request.keys}
    foreign_keys = [
        constraint for constraint in request.constraints.fields if constraint.rule is ValueRule.FOREIGN_KEY
    ]
    assert foreign_keys

    result = run(request)

    for constraint in foreign_keys:
        permitted = supplied[constraint.key_list_id]
        assert all(row[constraint.field_id] in permitted for row in result.rows)


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_the_declared_grain_key_is_unique_across_the_generated_rows(name):
    request = read_request(name)
    assert not request.grain.duplicate_keys_permitted

    result = run(request)

    keys = [tuple(row[field_id] for field_id in request.grain.key_fields) for row in result.rows]
    assert len(set(keys)) == len(keys) == request.constraints.row_count


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_measured_null_rates_fall_within_the_declared_tolerance(name):
    request = read_request(name)
    declared = constraint_index(request)

    result = run(request)

    measured_any_null = False
    for field in request.schema.fields:
        constraint = declared[field.field_id]
        nulls = sum(1 for row in result.rows if row[field.field_id] is None)
        measured = nulls / len(result.rows)
        assert abs(measured - constraint.null_rate) <= constraint.null_rate_tolerance
        if constraint.null_rate == 0.0:
            assert nulls == 0
        else:
            measured_any_null = True
            assert nulls > 0
    assert measured_any_null


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_the_csv_loads_with_the_standard_module_and_carries_the_written_rows(name):
    request = read_request(name)

    result = run(request)

    text = result.csv_bytes.decode("ascii")
    read = list(csv.reader(io.StringIO(text, newline="")))
    assert read[0] == [field.field_id for field in request.schema.fields]
    assert len(read) == 1 + request.constraints.row_count
    for line, row in zip(read[1:], result.rows):
        assert line == [
            "" if row[field.field_id] is None else written_value(row[field.field_id], field)
            for field in request.schema.fields
        ]


def test_the_csv_carries_lf_endings_and_quotes_a_separator_or_a_quote_in_a_value():
    request = read_request("customer-orders")

    result = run(request)

    text = result.csv_bytes.decode("ascii")
    assert "\r" not in text
    assert text.endswith("\n")
    assert text.split("\n")[0] == ",".join(field.field_id for field in request.schema.fields)
    assert '"east, west"' in text
    assert '"the ""central"" belt"' in text


def test_an_empty_csv_field_reads_back_as_the_declared_null():
    request = read_request("customer-orders")

    result = run(request)

    text = result.csv_bytes.decode("ascii")
    read = list(csv.reader(io.StringIO(text, newline="")))
    position = [field.field_id for field in request.schema.fields].index("region")
    empty_lines = [index for index, line in enumerate(read[1:]) if line[position] == ""]
    assert empty_lines
    assert all(result.rows[index]["region"] is None for index in empty_lines)
    assert all(row["region"] != "" for row in result.rows if row["region"] is not None)


def test_the_generator_declares_the_representation_it_wrote():
    orders = run(read_request("customer-orders")).dataset.canonicalisation
    regions = run(read_request("region-reference")).dataset.canonicalisation

    assert orders.canonicalisation_id == regions.canonicalisation_id == module.CANONICALISATION_ID
    assert orders.decimal_scale == 2
    assert orders.timestamp_precision == "seconds"
    assert orders.timezone == "UTC"
    assert regions.decimal_scale is None
    assert regions.timestamp_precision is None
    assert regions.timezone is None


def test_the_constraints_digest_follows_the_declared_summaries():
    request = read_request("customer-orders")

    base = run(request).dataset.synthetic_provenance.constraints_digest
    changed = run(with_field(request, "region", null_rate=0.2, null_rate_tolerance=0.05))

    assert changed.dataset.synthetic_provenance.constraints_digest != base
    assert constraints_bytes(request.constraints, field_index(request)).decode("ascii").startswith(
        module.CONSTRAINTS_FORM
    )


def test_a_dataset_with_no_key_list_is_generated_from_declared_summaries_alone():
    schema = SchemaDeclaration(
        "counter",
        "v1",
        (
            SchemaField("row_id", SchemaValueType.INTEGER, False, "key", None, None),
            SchemaField("label", SchemaValueType.STRING, False, "label", None, None),
        ),
        "csv-rfc4180",
    )
    grain = GrainDeclaration("one-row-per-counter", "v1", ("row_id",), "one row per counter", False)
    constraints = SyntheticDatasetConstraints(
        constraints_id="counter-summaries",
        version="v1",
        dataset_id="counter-synthetic",
        role=DatasetRole.INPUT,
        row_count=6,
        approved_summary="Six synthetic counter rows with two labels.",
        fields=(
            FieldConstraint("row_id", ValueRule.SEQUENCE, 100, None, (), None, None, 0.0, 0.0),
            FieldConstraint(
                "label",
                ValueRule.CATEGORIES,
                None,
                None,
                (CategoryWeight("alpha", 1), CategoryWeight("beta", 1)),
                None,
                None,
                0.0,
                0.0,
            ),
        ),
    )

    result = generate(schema, grain, (), constraints, SEED, GENERATOR_VERSION)

    assert result.dataset.synthetic_provenance.constrained_by == ()
    assert [row["row_id"] for row in result.rows] == [100, 101, 102, 103, 104, 105]
    assert set(row["label"] for row in result.rows) <= {"alpha", "beta"}


def test_the_generator_draws_randomness_only_from_the_supplied_seed():
    source = GENERATOR_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    random_uses = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "random"
    }

    assert imported <= ALLOWED_IMPORTS
    assert random_uses == {"Random"}
    assert not [text for text in FORBIDDEN_SOURCE_TEXT if text in source]


def test_the_request_reader_reaches_no_file_clock_or_environment():
    source = REQUEST_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            written = "." * node.level + (node.module or "")
            imported.add(
                importlib.util.resolve_name(written, "evorthon_data.synthetic")
                if node.level
                else written
            )

    assert imported <= REQUEST_ALLOWED_IMPORTS
    assert "json" in imported
    assert "json" not in ALLOWED_IMPORTS
    assert not [text for text in FORBIDDEN_SOURCE_TEXT if text in source]


def test_the_provenance_declaration_sits_beside_the_constraint_fixtures():
    provenance = json.loads(PROVENANCE.read_text(encoding="ascii"))

    assert provenance["produced_by"] == "hand authored"
    assert provenance["constraint_definitions"] == "tests/product/test_synthetic_generator.py"
    assert provenance["encoding"] == "ascii"
    assert provenance["line_endings"] == "lf"
    assert provenance["re_emitted_material"] == "none"
    assert "No real, personal or confidential data" in provenance["content"]


def test_every_committed_fixture_is_plain_ascii_and_is_read_by_a_test():
    files = sorted(path for path in FIXTURES.rglob("*") if path.is_file())

    assert [path.relative_to(FIXTURES).as_posix() for path in files] == [
        "constraints/customer-orders.json",
        "constraints/region-reference.json",
        "provenance.json",
    ]
    for path in files:
        payload = path.read_bytes()
        payload.decode("ascii")
        assert b"\r" not in payload


def test_a_constraint_carrying_a_raw_row_payload_is_refused_before_generation():
    request = read_request("customer-orders")
    assert run(request).dataset.row_count == 40
    row = {"order_id": "ORD-000000", "customer_id": "CUST-0001", "region": "north"}

    inside_a_category = with_field(request, "region", categories=(CategoryWeight(row, 1),))
    inside_a_slot = with_field(request, "region", lower=(row,))

    assert refuse(inside_a_category) is GenerationRefusalReason.RAW_ROW_PAYLOAD
    assert refuse(inside_a_slot) is GenerationRefusalReason.RAW_ROW_PAYLOAD


def test_a_key_list_that_cannot_satisfy_the_declared_cardinality_is_refused():
    request = read_request("region-reference")
    assert run(request).dataset.row_count == 5
    supplied = request.keys[0]

    short = replace(request, keys=(replace(supplied, values=supplied.values[:3]),))

    assert refuse(short) is GenerationRefusalReason.UNSATISFIABLE_CARDINALITY


def test_a_grain_that_forbids_duplicates_without_a_distinct_rule_is_refused():
    request = read_request("customer-orders")
    assert not run(request).dataset.grain.duplicate_keys_permitted

    on_a_repeating_key = replace(request, grain=replace(request.grain, key_fields=("customer_id",)))

    assert refuse(on_a_repeating_key) is GenerationRefusalReason.UNSATISFIABLE_CARDINALITY


@pytest.mark.parametrize("rate", [1.5, -0.1])
def test_a_null_rate_or_tolerance_outside_zero_to_one_is_refused(rate):
    request = read_request("customer-orders")
    assert run(request).dataset.row_count == 40

    assert refuse(with_field(request, "region", null_rate_tolerance=rate)) is (
        GenerationRefusalReason.NULL_RATE_NOT_DECLARABLE
    )
    assert refuse(with_field(request, "region", null_rate=rate)) is (
        GenerationRefusalReason.NULL_RATE_NOT_DECLARABLE
    )


def test_a_null_rate_the_declared_row_count_cannot_reach_is_refused():
    request = read_request("region-reference")
    assert run(request).dataset.row_count == 5

    unreachable = with_field(request, "population_band", null_rate=0.5, null_rate_tolerance=0.01)

    assert refuse(unreachable) is GenerationRefusalReason.NULL_RATE_NOT_DECLARABLE


def test_a_null_rate_on_a_field_that_cannot_carry_one_is_refused():
    orders = read_request("customer-orders")
    regions = read_request("region-reference")

    on_a_key_field = replace(orders, grain=replace(orders.grain, key_fields=("order_id", "region")))
    on_a_non_nullable_field = with_field(regions, "region_name", null_rate=0.2, null_rate_tolerance=0.05)

    assert refuse(on_a_key_field) is GenerationRefusalReason.NULL_RATE_NOT_DECLARABLE
    assert refuse(on_a_non_nullable_field) is GenerationRefusalReason.NULL_RATE_NOT_DECLARABLE


def test_a_schema_field_the_generator_cannot_produce_is_refused():
    request = read_request("region-reference")
    assert run(request).dataset.row_count == 5
    binary = SchemaField("payload", SchemaValueType.BINARY, False, "attachment", None, None)

    unwritable = replace(request, schema=replace(request.schema, fields=request.schema.fields + (binary,)))

    assert refuse(unwritable) is GenerationRefusalReason.UNSUPPORTED_FIELD_TYPE


def test_a_rule_the_declared_value_type_cannot_take_is_refused():
    request = read_request("customer-orders")

    sequence_on_a_decimal = with_field(
        request, "order_amount", rule=ValueRule.SEQUENCE, lower=Decimal("10.00"), upper=None
    )
    range_on_a_text_field = with_field(
        request, "region", rule=ValueRule.RANGE, lower="a", upper="z", categories=()
    )

    assert refuse(sequence_on_a_decimal) is GenerationRefusalReason.UNSUPPORTED_FIELD_TYPE
    assert refuse(range_on_a_text_field) is GenerationRefusalReason.UNSUPPORTED_FIELD_TYPE


def test_a_declared_decimal_beyond_the_field_precision_is_refused_before_any_draw():
    request = read_request("customer-orders")

    within_precision = with_schema_field(request, "order_amount", precision=6)
    beyond_precision = with_schema_field(request, "order_amount", precision=5)

    generated = run(within_precision)
    assert generated.dataset.row_count == 40
    assert all(len(format(row["order_amount"], "f").replace(".", "")) <= 6 for row in generated.rows)
    assert refuse(beyond_precision) is GenerationRefusalReason.INVALID_DECLARATION


def test_a_constraint_the_generator_does_not_implement_is_refused_and_never_ignored():
    request = read_request("region-reference")

    with pytest.raises(GenerationRefusal) as not_a_constraint_set:
        generate(request.schema, request.grain, request.keys, object(), SEED, GENERATOR_VERSION)
    nested_unknown = with_field(request, "region_name", categories=(CategoryWeight({"north"}, 1),))
    key_list_not_supplied = replace(request, keys=())

    assert not_a_constraint_set.value.reason is GenerationRefusalReason.UNDECLARED_CONSTRAINT
    assert refuse(nested_unknown) is GenerationRefusalReason.UNDECLARED_CONSTRAINT
    assert refuse(key_list_not_supplied) is GenerationRefusalReason.UNDECLARED_CONSTRAINT


@pytest.mark.parametrize(
    "case",
    [
        "unread slot filled",
        "required slot empty",
        "missing field summary",
        "repeated field summary",
        "undeclared field summary",
        "row count below one",
        "unreferenced key list",
        "repeated key value",
        "category weight below one",
        "empty category value",
        "category outside printable ascii",
        "range upper below lower",
        "decimal field without a scale",
        "seed that is not declared text",
    ],
)
def test_a_structurally_invalid_declaration_is_refused(case):
    request = read_request("region-reference")
    assert run(request).dataset.row_count == 5
    seed = SEED
    if case == "unread slot filled":
        request = with_field(request, "active_from", upper=date(2021, 1, 1))
    elif case == "required slot empty":
        request = with_field(request, "active_from", lower=None)
    elif case == "missing field summary":
        request = replace(
            request, constraints=replace(request.constraints, fields=request.constraints.fields[:-1])
        )
    elif case == "repeated field summary":
        fields = request.constraints.fields + (request.constraints.fields[0],)
        request = replace(request, constraints=replace(request.constraints, fields=fields))
    elif case == "undeclared field summary":
        request = with_field(request, "region_name", field_id="not_in_the_schema")
    elif case == "row count below one":
        request = replace(request, constraints=replace(request.constraints, row_count=0))
    elif case == "unreferenced key list":
        spare = KeyList("spare-keys", Identity("spare", "v1", "blake2b-256:" + "0" * 64), ("X-0001",))
        request = replace(request, keys=request.keys + (spare,))
    elif case == "repeated key value":
        supplied = request.keys[0]
        request = replace(request, keys=(replace(supplied, values=supplied.values[:4] + supplied.values[:1]),))
    elif case == "category weight below one":
        request = with_field(request, "region_name", categories=(CategoryWeight("Northern Region", 0),))
    elif case == "empty category value":
        request = with_field(request, "region_name", categories=(CategoryWeight("", 1),))
    elif case == "category outside printable ascii":
        request = with_field(request, "region_name", categories=(CategoryWeight("nor" + chr(240), 1),))
    elif case == "range upper below lower":
        request = with_field(request, "population_band", lower=5, upper=1)
    elif case == "decimal field without a scale":
        request = read_request("customer-orders")
        request = with_schema_field(request, "order_amount", scale=None)
    else:
        seed = ""

    assert refuse(request, seed=seed) is GenerationRefusalReason.INVALID_DECLARATION
