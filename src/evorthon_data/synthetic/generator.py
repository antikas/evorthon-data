"""Deterministic synthetic datasets from a declared schema, grain and summaries.

This module generates a labelled frozen dataset from declarations alone. It
reads no source system, no file, no clock and no environment variable, and the
only randomness it draws comes from the caller's seed through one explicitly
seeded generator. Two callers holding the same declarations and the same seed
obtain the same CSV bytes and the same content digest.

A caller supplies four things.

1. A schema declaration and a grain declaration from the verification domain.
2. Key lists: the permitted values of a foreign key, each with the identity of
   the real dataset those keys came from.
3. A constraint declaration carrying declared summaries only. A summary states
   one rule per field, which is a sequence, an inclusive range, a weighted set
   of categories, or a foreign key with its cardinality, plus a null rate and
   the tolerance that rate must be met within. A raw row never appears in a
   constraint and no statistical model is fitted to anything.
4. A seed and the generator version, both recorded on the result so the same
   dataset can be produced again.

The result carries canonical CSV bytes with a header of the logical field
names, LF line endings and RFC 4180 quoting, the typed rows behind those bytes,
and a frozen dataset whose provenance is synthetic, whose synthetic provenance
names the generator, its version, the seed, the digest of the constraints and
the identities that constrained the generation, and whose content digest comes
from the one canonical identity in the verification core.

The content digest is taken with no ordering declaration, which is the core's
declared multiset rule. A frozen dataset carries no ordering declaration, so
the multiset rule is the only rule a later reader can reproduce from the frozen
dataset itself. The CSV carries the rows in generation order.

The CSV writes a null as an empty field. Every generated text value is
non-empty by declaration, so an empty field always reads back as a null.

Every refusal is an integrity refusal raised before any value is generated. The
module refuses a constraint object that carries a row payload, a schema field
whose value type it cannot produce, a rule the field's type cannot take, a
constraint or object it does not implement, a declared cardinality that cannot
be satisfied at the declared row count, a null rate or tolerance that is not
declarable, and a structurally invalid declaration. It never substitutes a
default for a declaration it does not understand.
"""
# evorthon-implements: EVD-README-048
from __future__ import annotations

# evorthon-component: synthetic

import csv
import io
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields as dataclass_fields
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from types import MappingProxyType

from evorthon_data.verification.core import canonical_digest, dataset_digest
from evorthon_data.verification.domain.contracts import (
    CanonicalisationDeclaration,
    DatasetProvenance,
    DatasetRole,
    FrozenDataset,
    GrainDeclaration,
    Identity,
    SchemaDeclaration,
    SchemaField,
    SchemaValueType,
    SyntheticProvenance,
)

GENERATOR_ID = "evorthon_data.synthetic.generator"
CONSTRAINTS_FORM = "evorthon.synthetic.constraints.v1"

# The generator writes new data, so it declares the canonical representation it
# wrote. The identity names that policy. The decimal scale is the one scale the
# schema's own decimal fields declare, so the written form never exceeds what
# the schema states.
CANONICALISATION_ID = "evorthon.synthetic.canonicalisation"
CANONICALISATION_VERSION = "v1"
UNICODE_NORMALISATION = "NFC"
NULL_REPRESENTATION = "json-null"
SIGNED_ZERO_REPRESENTATION = "positive-zero"
NON_FINITE_NUMBER_POLICY = "reject"
TIMESTAMP_PRECISION = "seconds"
TIMESTAMP_TIMEZONE = "UTC"

CSV_NULL = ""
CSV_LINE_TERMINATOR = "\n"
CSV_ENCODING = "utf-8"
SEQUENCE_TEXT_WIDTH = 6
LOWEST_PRINTABLE = 0x20
HIGHEST_PRINTABLE = 0x7E


class ValueRule(str, Enum):
    """The closed set of declared shaping rules for one field."""

    SEQUENCE = "sequence"
    RANGE = "range"
    CATEGORIES = "categories"
    FOREIGN_KEY = "foreign-key"


class KeyCardinality(str, Enum):
    """How often one supplied key value may appear in the generated rows."""

    ONE_TO_ONE = "one-to-one"
    MANY_TO_ONE = "many-to-one"


class GenerationRefusalReason(str, Enum):
    """The closed set of integrity reasons for refusing to generate."""

    RAW_ROW_PAYLOAD = "raw-row-payload"
    UNSUPPORTED_FIELD_TYPE = "unsupported-field-type"
    UNDECLARED_CONSTRAINT = "undeclared-constraint"
    UNSATISFIABLE_CARDINALITY = "unsatisfiable-cardinality"
    NULL_RATE_NOT_DECLARABLE = "null-rate-not-declarable"
    INVALID_DECLARATION = "invalid-declaration"


class GenerationRefusal(ValueError):
    """Raised when a dataset cannot be generated with declared meaning."""

    def __init__(self, reason: GenerationRefusalReason, detail: str) -> None:
        super().__init__(f"{reason.value}: {detail}")
        self.reason = reason


@dataclass(frozen=True)
class CategoryWeight:
    """One declared category value and its relative weight in a distribution."""

    value: object
    weight: int


@dataclass(frozen=True)
class FieldConstraint:
    """The declared summary for one field.

    ``rule`` selects which of the remaining slots carry a declaration. A slot
    the rule does not use must be empty, so a declaration never carries a value
    that nothing reads.
    """

    field_id: str
    rule: ValueRule
    lower: object
    upper: object
    categories: tuple[CategoryWeight, ...]
    key_list_id: str | None
    cardinality: KeyCardinality | None
    null_rate: float
    null_rate_tolerance: float


@dataclass(frozen=True)
class SyntheticDatasetConstraints:
    """The declared summaries that shape one generated dataset.

    The declaration also names the dataset it describes, because the generator
    creates that dataset and must label it. It carries summaries only. A row,
    a sample of rows or a fitted model is never part of it.
    """

    constraints_id: str
    version: str
    dataset_id: str
    role: DatasetRole
    row_count: int
    approved_summary: str
    fields: tuple[FieldConstraint, ...]


@dataclass(frozen=True)
class KeyList:
    """Permitted values of one foreign key and the identity they came from."""

    key_list_id: str
    source: Identity
    values: tuple[object, ...]


@dataclass(frozen=True)
class GeneratedDataset:
    """Canonical CSV bytes, the typed rows behind them and the frozen dataset."""

    csv_bytes: bytes
    dataset: FrozenDataset
    rows: tuple[Mapping[str, object], ...]


DECLARED_CONSTRAINT_TYPES = (SyntheticDatasetConstraints, FieldConstraint, CategoryWeight)
DECLARED_SCALAR_TYPES = (bool, int, float, str, Decimal, date, datetime)
SUPPORTED_VALUE_TYPES = (
    SchemaValueType.STRING,
    SchemaValueType.INTEGER,
    SchemaValueType.DECIMAL,
    SchemaValueType.BOOLEAN,
    SchemaValueType.DATE,
    SchemaValueType.TIMESTAMP,
)
SEQUENCE_VALUE_TYPES = frozenset(
    {SchemaValueType.STRING, SchemaValueType.INTEGER, SchemaValueType.DATE}
)
RANGE_VALUE_TYPES = frozenset(
    {
        SchemaValueType.INTEGER,
        SchemaValueType.DECIMAL,
        SchemaValueType.DATE,
        SchemaValueType.TIMESTAMP,
    }
)
# A rule that gives every row a value no other row holds. The grain reads this
# set when it forbids duplicate keys.
DISTINCT_RULES = frozenset({ValueRule.SEQUENCE})


def _refuse(reason: GenerationRefusalReason, detail: str) -> GenerationRefusal:
    return GenerationRefusal(reason, detail)


def _is_printable(text: str) -> bool:
    return all(LOWEST_PRINTABLE <= ord(character) <= HIGHEST_PRINTABLE for character in text)


def _validate_text(value: object, name: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str:
        raise _refuse(GenerationRefusalReason.INVALID_DECLARATION, f"{name} must be declared text")
    if not allow_empty and not value:
        raise _refuse(GenerationRefusalReason.INVALID_DECLARATION, f"{name} must not be empty")
    if not _is_printable(value):
        raise _refuse(
            GenerationRefusalReason.INVALID_DECLARATION,
            f"{name} carries a character outside printable ASCII, which the generator does not write",
        )
    return value


def _validate_constraint_content(constraints: object) -> None:
    """Refuse a row payload or an unimplemented object before generation.

    A declared summary is built from scalars and the generator's own constraint
    types. A row is a mapping of field to value, so a mapping anywhere in the
    declaration is a row payload whatever the surrounding shape claims.
    """
    if type(constraints) is not SyntheticDatasetConstraints:
        raise _refuse(
            GenerationRefusalReason.UNDECLARED_CONSTRAINT,
            f"constraints must be a declared constraint set, not {type(constraints).__name__}",
        )
    _walk_declaration(constraints, "constraints")


def _walk_declaration(node: object, path: str) -> None:
    if node is None or isinstance(node, Enum) or isinstance(node, DECLARED_SCALAR_TYPES):
        return
    if isinstance(node, Mapping):
        raise _refuse(
            GenerationRefusalReason.RAW_ROW_PAYLOAD,
            f"{path} carries a mapping of field to value, which is a row and never a summary",
        )
    if isinstance(node, (tuple, list)):
        for position, item in enumerate(node):
            _walk_declaration(item, f"{path}[{position}]")
        return
    if type(node) in DECLARED_CONSTRAINT_TYPES:
        for member in dataclass_fields(node):
            _walk_declaration(getattr(node, member.name), f"{path}.{member.name}")
        return
    raise _refuse(
        GenerationRefusalReason.UNDECLARED_CONSTRAINT,
        f"{path} carries {type(node).__name__}, which the generator does not implement",
    )


def _field_index(schema: object) -> Mapping[str, SchemaField]:
    if type(schema) is not SchemaDeclaration:
        raise _refuse(GenerationRefusalReason.INVALID_DECLARATION, "a schema declaration is required")
    if not schema.fields:
        raise _refuse(GenerationRefusalReason.INVALID_DECLARATION, "the schema declares no field")
    index: dict[str, SchemaField] = {}
    for field in schema.fields:
        if type(field) is not SchemaField:
            raise _refuse(GenerationRefusalReason.INVALID_DECLARATION, "the schema carries a value that is not a field")
        _validate_text(field.field_id, "a schema field name")
        if field.field_id in index:
            raise _refuse(
                GenerationRefusalReason.INVALID_DECLARATION,
                f"the schema declares field {field.field_id} twice",
            )
        if field.value_type not in SUPPORTED_VALUE_TYPES:
            raise _refuse(
                GenerationRefusalReason.UNSUPPORTED_FIELD_TYPE,
                f"field {field.field_id} declares value type {field.value_type} and the generator cannot produce it",
            )
        index[field.field_id] = field
    return MappingProxyType(index)


def _validate_grain(grain: object, index: Mapping[str, SchemaField]) -> None:
    if type(grain) is not GrainDeclaration:
        raise _refuse(GenerationRefusalReason.INVALID_DECLARATION, "a grain declaration is required")
    for field_id in grain.key_fields:
        if field_id not in index:
            raise _refuse(
                GenerationRefusalReason.INVALID_DECLARATION,
                f"the grain names key field {field_id}, which the schema does not declare",
            )


def _canonicalisation_for(schema: SchemaDeclaration) -> CanonicalisationDeclaration:
    """Return the representation the generator wrote for this schema."""
    decimal_scales = {
        field.scale for field in schema.fields if field.value_type is SchemaValueType.DECIMAL
    }
    if decimal_scales:
        if None in decimal_scales:
            raise _refuse(
                GenerationRefusalReason.INVALID_DECLARATION,
                "the schema declares a decimal field without a scale, so its written form is undeclared",
            )
        if len(decimal_scales) != 1:
            raise _refuse(
                GenerationRefusalReason.INVALID_DECLARATION,
                "the schema declares decimal fields at different scales, so one written scale cannot be chosen",
            )
    holds_timestamp = any(
        field.value_type is SchemaValueType.TIMESTAMP for field in schema.fields
    )
    return CanonicalisationDeclaration(
        canonicalisation_id=CANONICALISATION_ID,
        version=CANONICALISATION_VERSION,
        unicode_normalisation=UNICODE_NORMALISATION,
        null_representation=NULL_REPRESENTATION,
        decimal_scale=decimal_scales.pop() if decimal_scales else None,
        timestamp_precision=TIMESTAMP_PRECISION if holds_timestamp else None,
        timezone=TIMESTAMP_TIMEZONE if holds_timestamp else None,
        signed_zero_representation=SIGNED_ZERO_REPRESENTATION,
        non_finite_number_policy=NON_FINITE_NUMBER_POLICY,
    )


def _constraint_index(
    constraints: SyntheticDatasetConstraints,
    index: Mapping[str, SchemaField],
) -> Mapping[str, FieldConstraint]:
    _validate_text(constraints.constraints_id, "the constraints identifier")
    _validate_text(constraints.version, "the constraints version")
    _validate_text(constraints.dataset_id, "the dataset identifier")
    _validate_text(constraints.approved_summary, "the approved summary")
    if type(constraints.role) is not DatasetRole:
        raise _refuse(GenerationRefusalReason.INVALID_DECLARATION, "the constraints declare no known dataset role")
    if type(constraints.row_count) is not int or constraints.row_count < 1:
        raise _refuse(
            GenerationRefusalReason.INVALID_DECLARATION,
            "the constraints must declare a row count of at least one",
        )
    declared: dict[str, FieldConstraint] = {}
    for constraint in constraints.fields:
        _validate_text(constraint.field_id, "a constraint field name")
        if constraint.field_id in declared:
            raise _refuse(
                GenerationRefusalReason.INVALID_DECLARATION,
                f"the constraints declare field {constraint.field_id} twice",
            )
        if constraint.field_id not in index:
            raise _refuse(
                GenerationRefusalReason.INVALID_DECLARATION,
                f"the constraints name field {constraint.field_id}, which the schema does not declare",
            )
        declared[constraint.field_id] = constraint
    missing = sorted(set(index) - set(declared))
    if missing:
        raise _refuse(
            GenerationRefusalReason.INVALID_DECLARATION,
            f"the constraints declare no summary for fields: {', '.join(missing)}",
        )
    return MappingProxyType(declared)


def _key_list_index(
    keys: object,
    declared: Mapping[str, FieldConstraint],
    index: Mapping[str, SchemaField],
    scale: int | None,
) -> Mapping[str, KeyList]:
    if not isinstance(keys, (tuple, list)):
        raise _refuse(GenerationRefusalReason.INVALID_DECLARATION, "the key lists must be a sequence")
    referenced: dict[str, list[SchemaField]] = {}
    for constraint in declared.values():
        if constraint.rule is ValueRule.FOREIGN_KEY:
            referenced.setdefault(constraint.key_list_id, []).append(index[constraint.field_id])
    supplied: dict[str, KeyList] = {}
    for key_list in keys:
        if type(key_list) is not KeyList:
            raise _refuse(
                GenerationRefusalReason.INVALID_DECLARATION,
                f"a key list must be a declared key list, not {type(key_list).__name__}",
            )
        _validate_text(key_list.key_list_id, "a key list identifier")
        if key_list.key_list_id in supplied:
            raise _refuse(
                GenerationRefusalReason.INVALID_DECLARATION,
                f"key list {key_list.key_list_id} is supplied twice",
            )
        if type(key_list.source) is not Identity:
            raise _refuse(
                GenerationRefusalReason.INVALID_DECLARATION,
                f"key list {key_list.key_list_id} declares no source identity",
            )
        if not key_list.values:
            raise _refuse(
                GenerationRefusalReason.INVALID_DECLARATION,
                f"key list {key_list.key_list_id} declares no value",
            )
        if len(set(key_list.values)) != len(key_list.values):
            raise _refuse(
                GenerationRefusalReason.INVALID_DECLARATION,
                f"key list {key_list.key_list_id} repeats a key value",
            )
        if key_list.key_list_id not in referenced:
            raise _refuse(
                GenerationRefusalReason.INVALID_DECLARATION,
                f"key list {key_list.key_list_id} is supplied and no constraint references it",
            )
        for field in referenced[key_list.key_list_id]:
            for value in key_list.values:
                _validate_declared_value(value, field, f"key list {key_list.key_list_id}", scale)
        supplied[key_list.key_list_id] = key_list
    unknown = sorted(set(referenced) - set(supplied))
    if unknown:
        raise _refuse(
            GenerationRefusalReason.UNDECLARED_CONSTRAINT,
            f"a constraint names key lists that were not supplied: {', '.join(str(name) for name in unknown)}",
        )
    return MappingProxyType(supplied)


def _validate_declared_value(
    value: object,
    field: SchemaField,
    where: str,
    scale: int | None,
) -> None:
    """Refuse a declared value that the field's declared type cannot hold."""
    value_type = field.value_type
    detail = f"{where} declares a value for field {field.field_id} that is not"
    if value_type is SchemaValueType.STRING:
        if type(value) is not str:
            raise _refuse(GenerationRefusalReason.INVALID_DECLARATION, f"{detail} declared text")
        _validate_text(value, f"a declared value for field {field.field_id}")
        return
    if value_type is SchemaValueType.INTEGER:
        if type(value) is not int:
            raise _refuse(GenerationRefusalReason.INVALID_DECLARATION, f"{detail} a declared integer")
        return
    if value_type is SchemaValueType.BOOLEAN:
        if type(value) is not bool:
            raise _refuse(GenerationRefusalReason.INVALID_DECLARATION, f"{detail} a declared boolean")
        return
    if value_type is SchemaValueType.DECIMAL:
        if type(value) is not Decimal or not value.is_finite():
            raise _refuse(GenerationRefusalReason.INVALID_DECLARATION, f"{detail} a finite declared decimal")
        if -value.as_tuple().exponent > (scale or 0):
            raise _refuse(
                GenerationRefusalReason.INVALID_DECLARATION,
                f"{where} declares a decimal for field {field.field_id} beyond the written scale {scale}",
            )
        _validate_declared_precision(value, field, where, scale)
        return
    if value_type is SchemaValueType.DATE:
        if type(value) is not date:
            raise _refuse(GenerationRefusalReason.INVALID_DECLARATION, f"{detail} a declared date")
        return
    if type(value) is not datetime:
        raise _refuse(GenerationRefusalReason.INVALID_DECLARATION, f"{detail} a declared timestamp")
    if value.tzinfo is None or value.utcoffset() != timedelta(0) or value.microsecond:
        raise _refuse(
            GenerationRefusalReason.INVALID_DECLARATION,
            f"{where} declares a timestamp for field {field.field_id} outside whole seconds in {TIMESTAMP_TIMEZONE}",
        )


def _validate_declared_precision(
    value: Decimal,
    field: SchemaField,
    where: str,
    scale: int | None,
) -> None:
    """Refuse a declared decimal that the field's declared precision cannot hold.

    The digit count is taken the way the verification core counts it, at the
    field's own scale, so a value this function accepts is a value the core can
    write. Checking both bounds of a range covers every value drawn between
    them, because no drawn value has a larger magnitude than the wider bound.
    """
    if field.precision is None:
        return
    digits, exponent = value.as_tuple()[1:]
    coefficient = int("".join(str(digit) for digit in digits))
    counted = coefficient * 10 ** (exponent + (scale if field.scale is None else field.scale))
    if len(str(counted)) > field.precision:
        raise _refuse(
            GenerationRefusalReason.INVALID_DECLARATION,
            f"{where} declares a decimal for field {field.field_id} beyond its declared precision"
            f" {field.precision}",
        )


def _validate_slots(constraint: FieldConstraint, field: SchemaField) -> None:
    """Refuse a declaration that fills a slot its own rule does not read."""
    used = {
        ValueRule.SEQUENCE: {"lower"},
        ValueRule.RANGE: {"lower", "upper"},
        ValueRule.CATEGORIES: {"categories"},
        ValueRule.FOREIGN_KEY: {"key_list_id", "cardinality"},
    }[constraint.rule]
    filled = set()
    if constraint.lower is not None:
        filled.add("lower")
    if constraint.upper is not None:
        filled.add("upper")
    if constraint.categories:
        filled.add("categories")
    if constraint.key_list_id is not None:
        filled.add("key_list_id")
    if constraint.cardinality is not None:
        filled.add("cardinality")
    unused = sorted(filled - used)
    if unused:
        raise _refuse(
            GenerationRefusalReason.INVALID_DECLARATION,
            f"field {field.field_id} declares rule {constraint.rule.value} and fills unread slots: {', '.join(unused)}",
        )
    unfilled = sorted(used - filled)
    if unfilled:
        raise _refuse(
            GenerationRefusalReason.INVALID_DECLARATION,
            f"field {field.field_id} declares rule {constraint.rule.value} and fills no {', '.join(unfilled)}",
        )


def _null_count(constraint: FieldConstraint, row_count: int) -> int:
    return round(constraint.null_rate * row_count)


def _validate_null_rate(
    constraint: FieldConstraint,
    field: SchemaField,
    grain: GrainDeclaration,
    row_count: int,
) -> None:
    for value, name in ((constraint.null_rate, "null rate"), (constraint.null_rate_tolerance, "null rate tolerance")):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _refuse(
                GenerationRefusalReason.NULL_RATE_NOT_DECLARABLE,
                f"field {field.field_id} declares a {name} that is not a number",
            )
        if not 0.0 <= float(value) <= 1.0:
            raise _refuse(
                GenerationRefusalReason.NULL_RATE_NOT_DECLARABLE,
                f"field {field.field_id} declares a {name} of {value}, which is outside 0 to 1",
            )
    if constraint.null_rate == 0.0:
        return
    if not field.nullable:
        raise _refuse(
            GenerationRefusalReason.NULL_RATE_NOT_DECLARABLE,
            f"field {field.field_id} is not nullable and declares a null rate above zero",
        )
    if field.field_id in grain.key_fields:
        raise _refuse(
            GenerationRefusalReason.NULL_RATE_NOT_DECLARABLE,
            f"field {field.field_id} is a grain key field and declares a null rate above zero",
        )
    achieved = _null_count(constraint, row_count) / row_count
    if abs(achieved - float(constraint.null_rate)) > float(constraint.null_rate_tolerance):
        raise _refuse(
            GenerationRefusalReason.NULL_RATE_NOT_DECLARABLE,
            f"field {field.field_id} declares a null rate of {constraint.null_rate} and {row_count} rows"
            f" reach {achieved}, which is outside the declared tolerance",
        )


def _validate_field_constraint(
    constraint: object,
    field: SchemaField,
    grain: GrainDeclaration,
    row_count: int,
    scale: int | None,
) -> None:
    if type(constraint) is not FieldConstraint:
        raise _refuse(
            GenerationRefusalReason.UNDECLARED_CONSTRAINT,
            f"field {field.field_id} carries {type(constraint).__name__} rather than a field constraint",
        )
    if type(constraint.rule) is not ValueRule:
        raise _refuse(
            GenerationRefusalReason.UNDECLARED_CONSTRAINT,
            f"field {field.field_id} declares no known rule",
        )
    _validate_slots(constraint, field)
    _validate_null_rate(constraint, field, grain, row_count)
    rule = constraint.rule
    if rule is ValueRule.SEQUENCE:
        if field.value_type not in SEQUENCE_VALUE_TYPES:
            raise _refuse(
                GenerationRefusalReason.UNSUPPORTED_FIELD_TYPE,
                f"field {field.field_id} declares value type {field.value_type} and a sequence cannot be written for it",
            )
        if field.value_type is SchemaValueType.STRING:
            if type(constraint.lower) is not str:
                raise _refuse(
                    GenerationRefusalReason.INVALID_DECLARATION,
                    f"field {field.field_id} declares a sequence prefix that is not declared text",
                )
            _validate_text(constraint.lower, f"the sequence prefix for field {field.field_id}", allow_empty=True)
            return
        _validate_declared_value(constraint.lower, field, "the sequence start", scale)
        return
    if rule is ValueRule.RANGE:
        if field.value_type not in RANGE_VALUE_TYPES:
            raise _refuse(
                GenerationRefusalReason.UNSUPPORTED_FIELD_TYPE,
                f"field {field.field_id} declares value type {field.value_type} and a range cannot be drawn for it",
            )
        _validate_declared_value(constraint.lower, field, "the range lower bound", scale)
        _validate_declared_value(constraint.upper, field, "the range upper bound", scale)
        if constraint.upper < constraint.lower:
            raise _refuse(
                GenerationRefusalReason.INVALID_DECLARATION,
                f"field {field.field_id} declares a range whose upper bound is below its lower bound",
            )
        return
    if rule is ValueRule.CATEGORIES:
        for category in constraint.categories:
            if type(category) is not CategoryWeight:
                raise _refuse(
                    GenerationRefusalReason.UNDECLARED_CONSTRAINT,
                    f"field {field.field_id} declares a category that is not a declared category weight",
                )
            if type(category.weight) is not int or category.weight < 1:
                raise _refuse(
                    GenerationRefusalReason.INVALID_DECLARATION,
                    f"field {field.field_id} declares a category weight below one",
                )
            _validate_declared_value(category.value, field, "a declared category", scale)
        return
    if type(constraint.cardinality) is not KeyCardinality:
        raise _refuse(
            GenerationRefusalReason.UNDECLARED_CONSTRAINT,
            f"field {field.field_id} declares no known key cardinality",
        )
    _validate_text(constraint.key_list_id, f"the key list named by field {field.field_id}")


def _validate_cardinality(
    constraint: FieldConstraint,
    field: SchemaField,
    key_lists: Mapping[str, KeyList],
    row_count: int,
) -> None:
    """Refuse a key list that cannot meet the declared cardinality."""
    if constraint.rule is not ValueRule.FOREIGN_KEY:
        return
    key_list = key_lists[constraint.key_list_id]
    if constraint.cardinality is KeyCardinality.ONE_TO_ONE and len(key_list.values) < row_count:
        raise _refuse(
            GenerationRefusalReason.UNSATISFIABLE_CARDINALITY,
            f"field {field.field_id} declares one key value per row and key list {key_list.key_list_id}"
            f" holds {len(key_list.values)} values for {row_count} rows",
        )


def _validate_distinct_grain(
    grain: GrainDeclaration,
    declared: Mapping[str, FieldConstraint],
) -> None:
    """Refuse a grain that forbids duplicates without a distinct-value rule."""
    if grain.duplicate_keys_permitted:
        return
    for field_id in grain.key_fields:
        constraint = declared[field_id]
        if constraint.rule in DISTINCT_RULES:
            return
        if constraint.rule is ValueRule.FOREIGN_KEY and constraint.cardinality is KeyCardinality.ONE_TO_ONE:
            return
    raise _refuse(
        GenerationRefusalReason.UNSATISFIABLE_CARDINALITY,
        f"grain {grain.grain_id} forbids duplicate keys and no key field declares a rule that gives every row"
        " a value no other row holds",
    )


def written_value(value: object, field: SchemaField) -> str:
    """Return the one written form of a declared value for this generator.

    The CSV cells and the constraints rendering both read this function, so a
    value is written the same way wherever the generator writes it.
    """
    value_type = field.value_type
    if value_type is SchemaValueType.STRING:
        return value
    if value_type is SchemaValueType.INTEGER:
        return str(value)
    if value_type is SchemaValueType.BOOLEAN:
        return "true" if value else "false"
    if value_type is SchemaValueType.DECIMAL:
        return format(value, f".{field.scale or 0}f")
    if value_type is SchemaValueType.DATE:
        return f"{value.year:04d}-{value.month:02d}-{value.day:02d}"
    return (
        f"{value.year:04d}-{value.month:02d}-{value.day:02d}"
        f"T{value.hour:02d}:{value.minute:02d}:{value.second:02d}Z"
    )


def _slot(text: str | None) -> str:
    """Write one optional token so an absent slot and an empty one differ."""
    return "absent" if text is None else f"value:{len(text)}:{text}"


def constraints_bytes(
    constraints: SyntheticDatasetConstraints,
    index: Mapping[str, SchemaField],
) -> bytes:
    """Return the declared bytes of a constraint set, for its digest.

    The form is one ASCII line per declaration with length-prefixed variable
    tokens, so no declared value can be read as another. The digest itself
    comes from the verification core, which owns every digest in the product.
    """
    lines = [
        CONSTRAINTS_FORM,
        f"constraints-id={_slot(constraints.constraints_id)}",
        f"version={_slot(constraints.version)}",
        f"dataset-id={_slot(constraints.dataset_id)}",
        f"role={_slot(constraints.role.value)}",
        f"row-count={constraints.row_count}",
        f"approved-summary={_slot(constraints.approved_summary)}",
    ]
    for field_id, field in index.items():
        constraint = next(item for item in constraints.fields if item.field_id == field_id)
        lower = None if constraint.lower is None else written_value(constraint.lower, field)
        upper = None if constraint.upper is None else written_value(constraint.upper, field)
        cardinality = None if constraint.cardinality is None else constraint.cardinality.value
        lines.append(
            f"field={_slot(field_id)} type={_slot(field.value_type.value)} rule={_slot(constraint.rule.value)}"
            f" lower={_slot(lower)} upper={_slot(upper)} key-list={_slot(constraint.key_list_id)}"
            f" cardinality={_slot(cardinality)} null-rate={float(constraint.null_rate)!r}"
            f" null-rate-tolerance={float(constraint.null_rate_tolerance)!r}"
        )
        for position, category in enumerate(constraint.categories):
            lines.append(
                f"category={_slot(field_id)} position={position}"
                f" value={_slot(written_value(category.value, field))} weight={category.weight}"
            )
    return ("\n".join(lines) + "\n").encode("ascii")


def _sequence_value(field: SchemaField, start: object, position: int) -> object:
    if field.value_type is SchemaValueType.INTEGER:
        return start + position
    if field.value_type is SchemaValueType.DATE:
        return start + timedelta(days=position)
    return f"{start}{position:0{SEQUENCE_TEXT_WIDTH}d}"


def _range_value(
    field: SchemaField,
    constraint: FieldConstraint,
    draw: random.Random,
    scale: int | None,
) -> object:
    if field.value_type is SchemaValueType.INTEGER:
        return draw.randint(constraint.lower, constraint.upper)
    if field.value_type is SchemaValueType.DATE:
        span = (constraint.upper - constraint.lower).days
        return constraint.lower + timedelta(days=draw.randint(0, span))
    if field.value_type is SchemaValueType.TIMESTAMP:
        span = int((constraint.upper - constraint.lower).total_seconds())
        return constraint.lower + timedelta(seconds=draw.randint(0, span))
    lower = int(constraint.lower.scaleb(scale))
    upper = int(constraint.upper.scaleb(scale))
    return Decimal(draw.randint(lower, upper)).scaleb(-scale)


def _category_value(constraint: FieldConstraint, draw: random.Random) -> object:
    total = sum(category.weight for category in constraint.categories)
    target = draw.randrange(total)
    running = 0
    for category in constraint.categories:
        running += category.weight
        if target < running:
            return category.value
    return constraint.categories[-1].value


def _column(
    field: SchemaField,
    constraint: FieldConstraint,
    key_lists: Mapping[str, KeyList],
    row_count: int,
    draw: random.Random,
    scale: int | None,
) -> list[object]:
    rule = constraint.rule
    if rule is ValueRule.SEQUENCE:
        return [_sequence_value(field, constraint.lower, position) for position in range(row_count)]
    if rule is ValueRule.RANGE:
        return [_range_value(field, constraint, draw, scale) for _ in range(row_count)]
    if rule is ValueRule.CATEGORIES:
        return [_category_value(constraint, draw) for _ in range(row_count)]
    values = key_lists[constraint.key_list_id].values
    if constraint.cardinality is KeyCardinality.ONE_TO_ONE:
        return list(draw.sample(values, row_count))
    return [values[draw.randrange(len(values))] for _ in range(row_count)]


def _csv_bytes(schema: SchemaDeclaration, rows: Sequence[Mapping[str, object]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator=CSV_LINE_TERMINATOR, quoting=csv.QUOTE_MINIMAL)
    writer.writerow([field.field_id for field in schema.fields])
    for row in rows:
        writer.writerow(
            [
                CSV_NULL if row[field.field_id] is None else written_value(row[field.field_id], field)
                for field in schema.fields
            ]
        )
    return buffer.getvalue().encode(CSV_ENCODING)


def _constrained_by(key_lists: Mapping[str, KeyList]) -> tuple[Identity, ...]:
    ordered = sorted(
        (key_list.source for key_list in key_lists.values()),
        key=lambda source: (source.identifier, source.version, source.digest),
    )
    unique: list[Identity] = []
    for source in ordered:
        if source not in unique:
            unique.append(source)
    return tuple(unique)


def generate(
    schema: SchemaDeclaration,
    grain: GrainDeclaration,
    keys: Sequence[KeyList],
    constraints: SyntheticDatasetConstraints,
    seed: str,
    generator_version: str,
) -> GeneratedDataset:
    """Generate one labelled synthetic dataset from declarations and a seed.

    Every declaration is checked before a single value is drawn, so a refusal
    never leaves a partly generated dataset behind. Randomness comes only from
    ``seed`` through one explicitly seeded generator, consumed field by field in
    the schema's declared order and then row by row, so the same declarations
    and seed always produce the same bytes and the same digest.
    """
    _validate_text(seed, "the seed")
    _validate_text(generator_version, "the generator version")
    _validate_constraint_content(constraints)
    index = _field_index(schema)
    _validate_grain(grain, index)
    canonicalisation = _canonicalisation_for(schema)
    scale = canonicalisation.decimal_scale
    declared = _constraint_index(constraints, index)
    row_count = constraints.row_count
    for field_id, field in index.items():
        _validate_field_constraint(declared[field_id], field, grain, row_count, scale)
    key_lists = _key_list_index(keys, declared, index, scale)
    for field_id, field in index.items():
        _validate_cardinality(declared[field_id], field, key_lists, row_count)
    _validate_distinct_grain(grain, declared)

    draw = random.Random(seed)
    columns: dict[str, list[object]] = {}
    for field_id, field in index.items():
        constraint = declared[field_id]
        column = _column(field, constraint, key_lists, row_count, draw, scale)
        count = _null_count(constraint, row_count)
        if count:
            for position in draw.sample(range(row_count), count):
                column[position] = None
        columns[field_id] = column

    rows = tuple(
        MappingProxyType({field_id: columns[field_id][position] for field_id in index})
        for position in range(row_count)
    )
    content_digest = dataset_digest(
        rows,
        schema=schema,
        grain=grain,
        canonicalisation=canonicalisation,
        ordering=None,
    )
    dataset = FrozenDataset(
        dataset_id=constraints.dataset_id,
        version=constraints.version,
        role=constraints.role,
        provenance=DatasetProvenance.SYNTHETIC,
        synthetic_provenance=SyntheticProvenance(
            generator_id=GENERATOR_ID,
            generator_version=generator_version,
            seed=seed,
            constraints_digest=canonical_digest(constraints_bytes(constraints, index)),
            constrained_by=_constrained_by(key_lists),
        ),
        content_digest=content_digest,
        schema=schema,
        grain=grain,
        canonicalisation=canonicalisation,
        row_count=row_count,
        approved_summary=constraints.approved_summary,
    )
    return GeneratedDataset(csv_bytes=_csv_bytes(schema, rows), dataset=dataset, rows=rows)
