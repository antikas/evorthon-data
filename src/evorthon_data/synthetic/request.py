"""The constraint request document and the declared values it is read into.

A request document is one JSON object with four members: the schema
declaration, the grain declaration, the key lists a foreign key draws from, and
the constraint declaration itself. This module is the only reader of that form,
so the wire form and the values behind it have one owner.

The reader takes the document as text. Whoever holds the document opens it;
nothing here reaches a file, a clock or an environment. Every scalar is read
into the value type its own schema field declares, so a caller never decides
what a written value means.

A document that does not carry the members the form declares, or that carries a
value the declared type cannot take, is refused as an invalid declaration. The
refusal is the one the generator already raises, so the component speaks one
refusal vocabulary.
"""
from __future__ import annotations

# evorthon-component: synthetic

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from ..verification.domain.contracts import (
    DatasetRole,
    GrainDeclaration,
    Identity,
    SchemaDeclaration,
    SchemaField,
    SchemaValueType,
)
from .generator import (
    CategoryWeight,
    FieldConstraint,
    GenerationRefusal,
    GenerationRefusalReason,
    KeyCardinality,
    KeyList,
    SyntheticDatasetConstraints,
    ValueRule,
)


# The stable name of the document form this module reads.
REQUEST_FORM = "evorthon.synthetic.request.v1"
# The trailing zone marker a written timestamp may carry, and the offset it
# stands for. The reader accepts the marker and stores the offset.
ZONE_MARKER = "Z"
ZONE_OFFSET = "+00:00"


@dataclass(frozen=True)
class GenerationRequest:
    """One complete generation request: schema, grain, key lists and constraints."""

    schema: SchemaDeclaration
    grain: GrainDeclaration
    keys: tuple[KeyList, ...]
    constraints: SyntheticDatasetConstraints


def typed_value(value: object, field: SchemaField) -> object:
    """Read one written value into the value type its schema field declares."""
    if value is None:
        return None
    if field.value_type is SchemaValueType.DECIMAL:
        return Decimal(value)
    if field.value_type is SchemaValueType.DATE:
        return date.fromisoformat(value)
    if field.value_type is SchemaValueType.TIMESTAMP:
        return datetime.fromisoformat(value.replace(ZONE_MARKER, ZONE_OFFSET))
    return value


def read_constraint(entry: Mapping[str, object], field: SchemaField) -> FieldConstraint:
    """Read one written field summary into the declared constraint it states."""
    return FieldConstraint(
        field_id=entry["field_id"],
        rule=ValueRule(entry["rule"]),
        lower=typed_value(entry["lower"], field),
        upper=typed_value(entry["upper"], field),
        categories=tuple(
            CategoryWeight(typed_value(category["value"], field), category["weight"])
            for category in entry["categories"]
        ),
        key_list_id=entry["key_list_id"],
        cardinality=None if entry["cardinality"] is None else KeyCardinality(entry["cardinality"]),
        null_rate=float(entry["null_rate"]),
        null_rate_tolerance=float(entry["null_rate_tolerance"]),
    )


def read_request(document: str) -> GenerationRequest:
    """Read one constraint request document into the values the generator takes."""
    try:
        return _read(json.loads(document))
    except GenerationRefusal:
        raise
    except (ArithmeticError, AttributeError, KeyError, TypeError, ValueError) as error:
        raise GenerationRefusal(
            GenerationRefusalReason.INVALID_DECLARATION,
            f"the request document is not the declared form: {error}",
        ) from error


def _read(document: Mapping[str, object]) -> GenerationRequest:
    """Read one parsed document, member by member, in the order the form states."""
    schema = _read_schema(document["schema"])
    index = {field.field_id: field for field in schema.fields}
    grain = _read_grain(document["grain"])
    constraints = _read_constraints(document["constraints"], index)
    owner = {
        constraint.key_list_id: index[constraint.field_id]
        for constraint in constraints.fields
        if constraint.rule is ValueRule.FOREIGN_KEY
    }
    keys = tuple(_read_key_list(entry, owner) for entry in document["keys"])
    return GenerationRequest(schema=schema, grain=grain, keys=keys, constraints=constraints)


def _read_schema(written: Mapping[str, object]) -> SchemaDeclaration:
    return SchemaDeclaration(
        written["schema_id"],
        written["version"],
        tuple(
            SchemaField(
                entry["field_id"],
                SchemaValueType(entry["value_type"]),
                entry["nullable"],
                entry["semantic_role"],
                entry["precision"],
                entry["scale"],
            )
            for entry in written["fields"]
        ),
        written["format_name"],
    )


def _read_grain(written: Mapping[str, object]) -> GrainDeclaration:
    return GrainDeclaration(
        written["grain_id"],
        written["version"],
        tuple(written["key_fields"]),
        written["population_description"],
        written["duplicate_keys_permitted"],
    )


def _read_constraints(
    written: Mapping[str, object], index: Mapping[str, SchemaField]
) -> SyntheticDatasetConstraints:
    return SyntheticDatasetConstraints(
        constraints_id=written["constraints_id"],
        version=written["version"],
        dataset_id=written["dataset_id"],
        role=DatasetRole(written["role"]),
        row_count=written["row_count"],
        approved_summary=written["approved_summary"],
        fields=tuple(
            read_constraint(entry, index[entry["field_id"]]) for entry in written["fields"]
        ),
    )


def _read_key_list(
    written: Mapping[str, object], owner: Mapping[str, SchemaField]
) -> KeyList:
    field = owner[written["key_list_id"]]
    source = written["source"]
    return KeyList(
        written["key_list_id"],
        Identity(source["identifier"], source["version"], source["digest"]),
        tuple(typed_value(value, field) for value in written["values"]),
    )
