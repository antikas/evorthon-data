"""Canonical typed values, canonical JSON and committed digests for frozen data.

This module is the single owner of value-level canonical identity. It turns
declared, typed row values into canonical bytes and hashes those bytes, so two
machines holding the same declared data produce the same identity.

The canonical form has four parts.

1. Canonical typed values. Every supported logical type has exactly one written
   form, selected by the declared canonicalisation. Text is normalised with the
   declared unicode form. Integers are written as plain digits. Decimals are
   written at exactly the declared scale. Booleans are written as true or
   false. Dates and timestamps are written at the declared precision in the
   declared zone. Binary values are written as lower-case hexadecimal. A null
   is written with the declared null representation.
2. Canonical JSON. Object keys are written in code-point order, separators
   carry no spaces, and every character outside printable ASCII is escaped, so
   the bytes are always plain ASCII.
3. A length-prefixed row stream. The stream opens with one frame that binds the
   declarations and carries one frame per row. A frame is the payload length in
   ASCII digits, a colon, the payload bytes, and a newline terminator that the
   length does not count.
4. One digest routine over those bytes.

Ordering is explicit. Rows are first placed in canonical row-byte order and
then sorted by the declared ordering fields followed by the declared
tie-breaker fields, which sort ascending with nulls last. Text keys are
compared in the declared unicode form, so two encodings of the same declared
text order alike and produce the same bytes. Rows that the
declaration does not separate therefore keep a stable place, and a caller's
input order never reaches the bytes. Passing no ordering declaration is the
declared multiset rule: the rows are identified as a bag in canonical row-byte
order. The choice is bound into the opening frame, so the two forms never
produce the same bytes.

The opening frame binds identity and the declared facts that change the written
form: the schema fields with their types, nullability, precision and scale; the
grain key and duplicate policy; every canonicalisation field; the ordering; and
the row count. Free text such as a semantic role, a population description or
an external format name does not change the written form and is not bound.

Refusals are integrity refusals. The module refuses an unsupported type, a
value outside the declared representation such as a decimal beyond the declared
precision or scale, a non-finite number the declaration forbids, a repeated key
where the declared grain forbids duplicates, a representation token the core
does not implement, an undeclared or missing field, and an ordering that cannot
be applied. It never substitutes a default when a declaration is silent.

The module reads no file, no clock, no environment and no locale, and it draws
no random value.
"""
from __future__ import annotations

# evorthon-component: verification_core

import dataclasses
import hashlib
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from types import MappingProxyType

from evorthon_data.verification.domain.contracts import (
    DOMAIN_RECORD_TYPES,
    CanonicalisationDeclaration,
    FrozenDataset,
    GrainDeclaration,
    NullPlacement,
    OrderingDeclaration,
    OrderingField,
    SchemaDeclaration,
    SchemaField,
    SchemaValueType,
    SortDirection,
    VerificationCase,
    VerificationResult,
)

CANONICAL_ROW_STREAM_FORM = "evorthon.canonical.row-stream.v1"
CANONICAL_RECORD_FORM = "evorthon.canonical.record.v1"

# The one hash declaration. Every digest in this component comes from here.
HASH_ALGORITHM = "blake2b"
HASH_DIGEST_SIZE_BYTES = 32
DIGEST_PREFIX = "blake2b-256"

RECORD_TEXT_NORMALISATION = "NFC"
FRAME_SEPARATOR = b":"
FRAME_TERMINATOR = b"\n"

SUPPORTED_UNICODE_NORMALISATIONS = ("NFC", "NFD")
SUPPORTED_NULL_REPRESENTATIONS = ("json-null",)
SUPPORTED_TIMEZONES = ("UTC",)
SUPPORTED_SIGNED_ZERO_REPRESENTATIONS = ("positive-zero", "preserve-sign")
SUPPORTED_NON_FINITE_NUMBER_POLICIES = ("reject", "canonical-token")
TIMESTAMP_PRECISION_DIGITS = MappingProxyType({"seconds": 0, "milliseconds": 3, "microseconds": 6})
NAN_TOKEN = "NaN"
POSITIVE_INFINITY_TOKEN = "Infinity"
NEGATIVE_INFINITY_TOKEN = "-Infinity"

# A declared tie-breaker field carries no direction or null placement, so the
# canonical form states one: ascending, nulls last.
TIE_BREAKER_DIRECTION = SortDirection.ASCENDING
TIE_BREAKER_NULL_PLACEMENT = NullPlacement.LAST

# The escape and quote characters are named rather than written, so the shipped
# text carries no doubled escape run for a path scanner to read as a location.
ESCAPE = chr(92)
QUOTE = chr(34)
_SHORT_ESCAPES = MappingProxyType(
    {
        ESCAPE: ESCAPE + ESCAPE,
        QUOTE: ESCAPE + QUOTE,
        "\b": ESCAPE + "b",
        "\f": ESCAPE + "f",
        "\n": ESCAPE + "n",
        "\r": ESCAPE + "r",
        "\t": ESCAPE + "t",
    }
)
_RECORD_TYPES = frozenset(DOMAIN_RECORD_TYPES)


class RefusalReason(str, Enum):
    """The closed set of integrity reasons for refusing to produce bytes."""

    UNSUPPORTED_TYPE = "unsupported-type"
    UNDECLARED_REPRESENTATION = "undeclared-representation"
    VALUE_OUTSIDE_DECLARED_REPRESENTATION = "value-outside-declared-representation"
    NON_FINITE_NOT_PERMITTED = "non-finite-not-permitted"
    DUPLICATE_KEY_NOT_PERMITTED = "duplicate-key-not-permitted"
    ORDERING_NOT_APPLICABLE = "ordering-not-applicable"
    UNDECLARED_FIELD = "undeclared-field"
    INVALID_DECLARATION = "invalid-declaration"


class CanonicalisationRefusal(ValueError):
    """Raised when canonical bytes cannot be produced with declared meaning."""

    def __init__(self, reason: RefusalReason, detail: str) -> None:
        super().__init__(f"{reason.value}: {detail}")
        self.reason = reason


class _Number:
    """A pre-rendered numeric token written into canonical JSON verbatim."""

    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        self.text = text


def _refuse(reason: RefusalReason, detail: str) -> CanonicalisationRefusal:
    return CanonicalisationRefusal(reason, detail)


def _quote(text: str) -> str:
    parts = [QUOTE]
    for character in text:
        escape = _SHORT_ESCAPES.get(character)
        if escape is not None:
            parts.append(escape)
            continue
        codepoint = ord(character)
        if 0x20 <= codepoint <= 0x7E:
            parts.append(character)
        elif codepoint > 0xFFFF:
            offset = codepoint - 0x10000
            high = 0xD800 + (offset >> 10)
            low = 0xDC00 + (offset & 0x3FF)
            parts.append(f"{ESCAPE}u{high:04x}{ESCAPE}u{low:04x}")
        else:
            parts.append(f"{ESCAPE}u{codepoint:04x}")
    parts.append(QUOTE)
    return "".join(parts)


def _encode(node: object) -> str:
    """Write one canonical JSON node: sorted keys, no spaces, ASCII only."""
    if node is None:
        return "null"
    if isinstance(node, _Number):
        return node.text
    if isinstance(node, bool):
        return "true" if node else "false"
    if isinstance(node, int):
        return str(node)
    if isinstance(node, str):
        return _quote(node)
    if isinstance(node, list):
        return "[" + ",".join(_encode(item) for item in node) + "]"
    if isinstance(node, dict):
        members = (f"{_quote(key)}:{_encode(value)}" for key, value in sorted(node.items()))
        return "{" + ",".join(members) + "}"
    raise _refuse(RefusalReason.UNSUPPORTED_TYPE, f"canonical JSON has no rule for {type(node).__name__}")


def _normalise(value: str, form: str) -> str:
    """The one normalisation call, so no caller can normalise differently."""
    return unicodedata.normalize(form, value)


def _declared_text(value: str, declaration: CanonicalisationDeclaration) -> str:
    """Return declared text in the declared unicode form.

    The written value and the sort key both read this, so the bytes and the
    ordering cannot drift apart.
    """
    return _normalise(value, declaration.unicode_normalisation)


def _text(value: str) -> str:
    return _normalise(value, RECORD_TEXT_NORMALISATION)


def _frame(payload: bytes) -> bytes:
    return str(len(payload)).encode("ascii") + FRAME_SEPARATOR + payload + FRAME_TERMINATOR


def _to_ascii(text: str) -> bytes:
    return text.encode("ascii")


def canonical_digest(payload: bytes) -> str:
    """Return the one canonical digest of already-canonical bytes."""
    fingerprint = hashlib.blake2b(payload, digest_size=HASH_DIGEST_SIZE_BYTES)
    return f"{DIGEST_PREFIX}:{fingerprint.hexdigest()}"


def _field_index(schema: SchemaDeclaration) -> dict[str, SchemaField]:
    if not isinstance(schema, SchemaDeclaration):
        raise _refuse(RefusalReason.UNSUPPORTED_TYPE, "a schema declaration is required")
    if not schema.fields:
        raise _refuse(RefusalReason.INVALID_DECLARATION, "the schema declares no field")
    index: dict[str, SchemaField] = {}
    for field in schema.fields:
        if not isinstance(field.value_type, SchemaValueType):
            raise _refuse(RefusalReason.INVALID_DECLARATION, f"field {field.field_id} declares no known value type")
        if field.field_id in index:
            raise _refuse(RefusalReason.INVALID_DECLARATION, f"the schema declares field {field.field_id} twice")
        index[field.field_id] = field
    return index


def _validate_declaration(schema: SchemaDeclaration, declaration: CanonicalisationDeclaration) -> None:
    if not isinstance(declaration, CanonicalisationDeclaration):
        raise _refuse(RefusalReason.UNSUPPORTED_TYPE, "a canonicalisation declaration is required")
    if declaration.unicode_normalisation not in SUPPORTED_UNICODE_NORMALISATIONS:
        raise _refuse(
            RefusalReason.UNDECLARED_REPRESENTATION,
            f"no unicode normalisation is implemented for {declaration.unicode_normalisation}",
        )
    if declaration.null_representation not in SUPPORTED_NULL_REPRESENTATIONS:
        raise _refuse(
            RefusalReason.UNDECLARED_REPRESENTATION,
            f"no null representation is implemented for {declaration.null_representation}",
        )
    if declaration.signed_zero_representation not in SUPPORTED_SIGNED_ZERO_REPRESENTATIONS:
        raise _refuse(
            RefusalReason.UNDECLARED_REPRESENTATION,
            f"no signed zero representation is implemented for {declaration.signed_zero_representation}",
        )
    if declaration.non_finite_number_policy not in SUPPORTED_NON_FINITE_NUMBER_POLICIES:
        raise _refuse(
            RefusalReason.UNDECLARED_REPRESENTATION,
            f"no non-finite number policy is implemented for {declaration.non_finite_number_policy}",
        )
    declared_types = {field.value_type for field in schema.fields}
    if SchemaValueType.DECIMAL in declared_types:
        scale = declaration.decimal_scale
        if scale is None:
            raise _refuse(
                RefusalReason.UNDECLARED_REPRESENTATION,
                "the schema declares a decimal and the declaration states no scale",
            )
        if type(scale) is not int or scale < 0:
            raise _refuse(
                RefusalReason.INVALID_DECLARATION,
                "the declared decimal scale must be a non-negative integer",
            )
    if SchemaValueType.TIMESTAMP in declared_types:
        if declaration.timestamp_precision is None:
            raise _refuse(
                RefusalReason.UNDECLARED_REPRESENTATION,
                "the schema declares a timestamp and the declaration states no precision",
            )
        if declaration.timestamp_precision not in TIMESTAMP_PRECISION_DIGITS:
            raise _refuse(
                RefusalReason.UNDECLARED_REPRESENTATION,
                f"no timestamp precision is implemented for {declaration.timestamp_precision}",
            )
        if declaration.timezone is None:
            raise _refuse(
                RefusalReason.UNDECLARED_REPRESENTATION,
                "the schema declares a timestamp and the declaration states no zone",
            )
        if declaration.timezone not in SUPPORTED_TIMEZONES:
            raise _refuse(
                RefusalReason.UNDECLARED_REPRESENTATION,
                f"no time zone is implemented for {declaration.timezone}",
            )


def _ordering_specs(ordering: OrderingDeclaration, index: Mapping[str, SchemaField]) -> list[OrderingField]:
    if not isinstance(ordering, OrderingDeclaration):
        raise _refuse(RefusalReason.UNSUPPORTED_TYPE, "an ordering declaration or None is required")
    specs = list(ordering.fields)
    specs.extend(
        OrderingField(field_id, TIE_BREAKER_DIRECTION, TIE_BREAKER_NULL_PLACEMENT)
        for field_id in ordering.tie_breaker_fields
    )
    if not specs:
        raise _refuse(RefusalReason.ORDERING_NOT_APPLICABLE, "the ordering declares no field")
    for spec in specs:
        if spec.field_id not in index:
            raise _refuse(
                RefusalReason.ORDERING_NOT_APPLICABLE,
                f"the ordering names undeclared field {spec.field_id}",
            )
        if not isinstance(spec.direction, SortDirection):
            raise _refuse(
                RefusalReason.ORDERING_NOT_APPLICABLE,
                f"field {spec.field_id} declares no known direction",
            )
        if not isinstance(spec.null_placement, NullPlacement):
            raise _refuse(
                RefusalReason.ORDERING_NOT_APPLICABLE,
                f"field {spec.field_id} declares no known null placement",
            )
    return specs


def _decimal_node(value: Decimal, field: SchemaField, declaration: CanonicalisationDeclaration) -> object:
    if value.is_nan() or value.is_infinite():
        if declaration.non_finite_number_policy == "reject":
            raise _refuse(
                RefusalReason.NON_FINITE_NOT_PERMITTED,
                f"field {field.field_id} carries a non-finite number and the declaration rejects one",
            )
        if value.is_nan():
            return NAN_TOKEN
        return NEGATIVE_INFINITY_TOKEN if value.is_signed() else POSITIVE_INFINITY_TOKEN
    scale = declaration.decimal_scale
    sign, digits, exponent = value.as_tuple()
    if -exponent > scale:
        raise _refuse(
            RefusalReason.VALUE_OUTSIDE_DECLARED_REPRESENTATION,
            f"field {field.field_id} carries more decimal scale than the declared {scale}",
        )
    if field.scale is not None and -exponent > field.scale:
        raise _refuse(
            RefusalReason.VALUE_OUTSIDE_DECLARED_REPRESENTATION,
            f"field {field.field_id} carries more decimal scale than its declared field scale",
        )
    coefficient = int("".join(str(digit) for digit in digits))
    # A field that declares no precision constrains no digit count. Precision is
    # counted at the field's own scale when it declares one, so a wider written
    # form does not spend the field's digits. The written form stays at the
    # declared canonicalisation scale.
    if field.precision is not None:
        counted = coefficient * 10 ** (exponent + (scale if field.scale is None else field.scale))
        if len(str(counted)) > field.precision:
            raise _refuse(
                RefusalReason.VALUE_OUTSIDE_DECLARED_REPRESENTATION,
                f"field {field.field_id} carries more digits than its declared precision {field.precision}",
            )
    unscaled = coefficient * 10 ** (exponent + scale)
    body = str(unscaled).rjust(scale + 1, "0")
    if scale:
        body = f"{body[:-scale]}.{body[-scale:]}"
    positive_zero = unscaled == 0 and declaration.signed_zero_representation == "positive-zero"
    if sign == 1 and not positive_zero:
        return _Number(f"-{body}")
    return _Number(body)


def _timestamp_node(value: datetime, field: SchemaField, declaration: CanonicalisationDeclaration) -> str:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise _refuse(
            RefusalReason.VALUE_OUTSIDE_DECLARED_REPRESENTATION,
            f"field {field.field_id} carries a timestamp outside the declared zone {declaration.timezone}",
        )
    digits = TIMESTAMP_PRECISION_DIGITS[declaration.timestamp_precision]
    fraction = f"{value.microsecond:06d}"
    if fraction[digits:].strip("0"):
        raise _refuse(
            RefusalReason.VALUE_OUTSIDE_DECLARED_REPRESENTATION,
            f"field {field.field_id} carries a timestamp finer than the declared {declaration.timestamp_precision}",
        )
    stamp = (
        f"{value.year:04d}-{value.month:02d}-{value.day:02d}"
        f"T{value.hour:02d}:{value.minute:02d}:{value.second:02d}"
    )
    if digits:
        stamp = f"{stamp}.{fraction[:digits]}"
    return f"{stamp}Z"


def _value_node(value: object, field: SchemaField, declaration: CanonicalisationDeclaration) -> object:
    if value is None:
        if not field.nullable:
            raise _refuse(
                RefusalReason.VALUE_OUTSIDE_DECLARED_REPRESENTATION,
                f"field {field.field_id} is not nullable and carries a null",
            )
        return None
    value_type = field.value_type
    if value_type is SchemaValueType.STRING:
        if type(value) is not str:
            raise _refuse(RefusalReason.UNSUPPORTED_TYPE, f"field {field.field_id} needs a string value")
        return _declared_text(value, declaration)
    if value_type is SchemaValueType.INTEGER:
        if type(value) is not int:
            raise _refuse(RefusalReason.UNSUPPORTED_TYPE, f"field {field.field_id} needs an integer value")
        return value
    if value_type is SchemaValueType.BOOLEAN:
        if type(value) is not bool:
            raise _refuse(RefusalReason.UNSUPPORTED_TYPE, f"field {field.field_id} needs a boolean value")
        return value
    if value_type is SchemaValueType.DECIMAL:
        if type(value) is not Decimal:
            raise _refuse(RefusalReason.UNSUPPORTED_TYPE, f"field {field.field_id} needs a decimal value")
        return _decimal_node(value, field, declaration)
    if value_type is SchemaValueType.DATE:
        if type(value) is not date:
            raise _refuse(RefusalReason.UNSUPPORTED_TYPE, f"field {field.field_id} needs a date value")
        return f"{value.year:04d}-{value.month:02d}-{value.day:02d}"
    if value_type is SchemaValueType.TIMESTAMP:
        if type(value) is not datetime:
            raise _refuse(RefusalReason.UNSUPPORTED_TYPE, f"field {field.field_id} needs a timestamp value")
        return _timestamp_node(value, field, declaration)
    if type(value) is not bytes:
        raise _refuse(RefusalReason.UNSUPPORTED_TYPE, f"field {field.field_id} needs a binary value")
    return value.hex()


def _row_node(
    row: Mapping[str, object],
    index: Mapping[str, SchemaField],
    declaration: CanonicalisationDeclaration,
) -> dict[str, object]:
    if not isinstance(row, Mapping):
        raise _refuse(RefusalReason.UNSUPPORTED_TYPE, "each row must be a mapping of declared field to value")
    extra = sorted(set(row) - set(index))
    if extra:
        raise _refuse(RefusalReason.UNDECLARED_FIELD, f"the row carries undeclared fields: {', '.join(extra)}")
    missing = sorted(set(index) - set(row))
    if missing:
        raise _refuse(RefusalReason.UNDECLARED_FIELD, f"the row omits declared fields: {', '.join(missing)}")
    return {field_id: _value_node(row[field_id], field, declaration) for field_id, field in index.items()}


def _comparable(value: object, field: SchemaField, declaration: CanonicalisationDeclaration) -> object:
    """Return the canonical sort value, so ordering reads the declared data.

    Text is compared in the declared unicode form. Comparing the caller's raw
    text would let two encodings of the same declared value order differently
    and change the bytes.
    """
    if field.value_type is SchemaValueType.STRING:
        return _declared_text(value, declaration)
    if type(value) is Decimal and value.is_nan():
        raise _refuse(
            RefusalReason.ORDERING_NOT_APPLICABLE,
            f"ordering field {field.field_id} carries a value that does not compare",
        )
    return value


def _sort_key(
    row: Mapping[str, object],
    spec: OrderingField,
    index: Mapping[str, SchemaField],
    declaration: CanonicalisationDeclaration,
) -> tuple[int, object]:
    if spec.direction is SortDirection.ASCENDING:
        null_rank, value_rank = (0, 1) if spec.null_placement is NullPlacement.FIRST else (1, 0)
    else:
        null_rank, value_rank = (1, 0) if spec.null_placement is NullPlacement.FIRST else (0, 1)
    value = row[spec.field_id]
    if value is None:
        return (null_rank, 0)
    return (value_rank, _comparable(value, index[spec.field_id], declaration))


def _declaration_node(declaration: CanonicalisationDeclaration) -> dict[str, object]:
    precision = declaration.timestamp_precision
    zone = declaration.timezone
    return {
        "canonicalisation_id": _text(declaration.canonicalisation_id),
        "version": _text(declaration.version),
        "unicode_normalisation": _text(declaration.unicode_normalisation),
        "null_representation": _text(declaration.null_representation),
        "decimal_scale": declaration.decimal_scale,
        "timestamp_precision": None if precision is None else _text(precision),
        "timezone": None if zone is None else _text(zone),
        "signed_zero_representation": _text(declaration.signed_zero_representation),
        "non_finite_number_policy": _text(declaration.non_finite_number_policy),
    }


def _schema_node(schema: SchemaDeclaration) -> dict[str, object]:
    return {
        "schema_id": _text(schema.schema_id),
        "version": _text(schema.version),
        "fields": [
            {
                "field_id": _text(field.field_id),
                "value_type": field.value_type.value,
                "nullable": bool(field.nullable),
                "precision": field.precision,
                "scale": field.scale,
            }
            for field in schema.fields
        ],
    }


def _validate_grain(grain: GrainDeclaration, index: Mapping[str, SchemaField]) -> None:
    if not isinstance(grain, GrainDeclaration):
        raise _refuse(RefusalReason.UNSUPPORTED_TYPE, "a grain declaration is required")
    for field_id in grain.key_fields:
        if field_id not in index:
            raise _refuse(
                RefusalReason.INVALID_DECLARATION,
                f"the grain names undeclared key field {field_id}",
            )
    if not grain.duplicate_keys_permitted and not grain.key_fields:
        raise _refuse(
            RefusalReason.INVALID_DECLARATION,
            "a grain that forbids duplicate keys must declare a key field",
        )


def _refuse_duplicate_keys(nodes: list[dict[str, object]], grain: GrainDeclaration) -> None:
    """Refuse a repeated key when the declared grain forbids duplicates."""
    seen: set[str] = set()
    for node in nodes:
        key = _encode([node[field_id] for field_id in grain.key_fields])
        if key in seen:
            raise _refuse(
                RefusalReason.DUPLICATE_KEY_NOT_PERMITTED,
                f"the grain forbids duplicate keys and the rows repeat key {key}",
            )
        seen.add(key)


def _grain_node(grain: GrainDeclaration) -> dict[str, object]:
    return {
        "grain_id": _text(grain.grain_id),
        "version": _text(grain.version),
        "key_fields": [_text(field_id) for field_id in grain.key_fields],
        "duplicate_keys_permitted": bool(grain.duplicate_keys_permitted),
    }


def _ordering_node(ordering: OrderingDeclaration | None) -> object:
    if ordering is None:
        return None
    return {
        "ordering_id": _text(ordering.ordering_id),
        "version": _text(ordering.version),
        "fields": [
            {
                "field_id": _text(spec.field_id),
                "direction": spec.direction.value,
                "null_placement": spec.null_placement.value,
            }
            for spec in ordering.fields
        ],
        "tie_breaker_fields": [_text(field_id) for field_id in ordering.tie_breaker_fields],
    }


def canonical_row_stream(
    rows: Sequence[Mapping[str, object]],
    *,
    schema: SchemaDeclaration,
    grain: GrainDeclaration,
    canonicalisation: CanonicalisationDeclaration,
    ordering: OrderingDeclaration | None,
) -> bytes:
    """Return the canonical length-prefixed row stream for declared rows.

    ``ordering`` is required and has no default. An ordering declaration sorts
    the rows by its declared fields and tie-breakers. ``None`` is the declared
    multiset rule and orders the rows by their canonical row bytes.
    """
    if isinstance(rows, (str, bytes, Mapping)):
        raise _refuse(RefusalReason.UNSUPPORTED_TYPE, "rows must be a sequence of mappings")
    material = list(rows)
    index = _field_index(schema)
    _validate_declaration(schema, canonicalisation)
    _validate_grain(grain, index)
    nodes = [_row_node(row, index, canonicalisation) for row in material]
    if not grain.duplicate_keys_permitted:
        _refuse_duplicate_keys(nodes, grain)
    payloads = [_to_ascii(_encode(node)) for node in nodes]
    positions = sorted(range(len(payloads)), key=lambda position: payloads[position])
    if ordering is not None:
        for spec in reversed(_ordering_specs(ordering, index)):
            positions.sort(
                key=lambda position: _sort_key(material[position], spec, index, canonicalisation),
                reverse=spec.direction is SortDirection.DESCENDING,
            )
    binding = {
        "stream": CANONICAL_ROW_STREAM_FORM,
        "schema": _schema_node(schema),
        "grain": _grain_node(grain),
        "canonicalisation": _declaration_node(canonicalisation),
        "ordering": _ordering_node(ordering),
        "row_count": len(material),
    }
    frames = [_frame(_to_ascii(_encode(binding)))]
    frames.extend(_frame(payloads[position]) for position in positions)
    return b"".join(frames)


def dataset_digest(
    rows: Sequence[Mapping[str, object]],
    *,
    schema: SchemaDeclaration,
    grain: GrainDeclaration,
    canonicalisation: CanonicalisationDeclaration,
    ordering: OrderingDeclaration | None,
) -> str:
    """Return the canonical digest of declared rows.

    This is the one entry point for a component that is building a frozen
    dataset and needs its content digest before the record exists.
    """
    stream = canonical_row_stream(
        rows,
        schema=schema,
        grain=grain,
        canonicalisation=canonicalisation,
        ordering=ordering,
    )
    return canonical_digest(stream)


def frozen_dataset_digest(
    dataset: FrozenDataset,
    rows: Sequence[Mapping[str, object]],
    *,
    ordering: OrderingDeclaration | None,
) -> str:
    """Return the digest of a frozen dataset's canonical bytes for its rows."""
    if not isinstance(dataset, FrozenDataset):
        raise _refuse(RefusalReason.UNSUPPORTED_TYPE, "a frozen dataset is required")
    return dataset_digest(
        rows,
        schema=dataset.schema,
        grain=dataset.grain,
        canonicalisation=dataset.canonicalisation,
        ordering=ordering,
    )


def _record_node(value: object) -> object:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, Enum):
        return _record_node(value.value)
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, tuple):
        return [_record_node(item) for item in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        if type(value) not in _RECORD_TYPES:
            raise _refuse(
                RefusalReason.UNSUPPORTED_TYPE,
                f"{type(value).__name__} is outside the verification-domain record inventory",
            )
        return {field.name: _record_node(getattr(value, field.name)) for field in dataclasses.fields(value)}
    raise _refuse(
        RefusalReason.UNSUPPORTED_TYPE,
        f"a record carries an unsupported value of type {type(value).__name__}",
    )


def canonical_record_bytes(record: object) -> bytes:
    """Return the canonical bytes of one verification-domain record."""
    if type(record) not in _RECORD_TYPES:
        raise _refuse(
            RefusalReason.UNSUPPORTED_TYPE,
            f"{type(record).__name__} is outside the verification-domain record inventory",
        )
    payload = {
        "record_form": CANONICAL_RECORD_FORM,
        "record_type": type(record).__name__,
        "record": _record_node(record),
    }
    return _to_ascii(_encode(payload)) + FRAME_TERMINATOR


def record_digest(record: object) -> str:
    """Return the canonical digest of one verification-domain record."""
    return canonical_digest(canonical_record_bytes(record))


def case_digest(case: VerificationCase) -> str:
    """Return the canonical digest of one verification case."""
    if type(case) is not VerificationCase:
        raise _refuse(RefusalReason.UNSUPPORTED_TYPE, "a verification case is required")
    return record_digest(case)


def result_digest(result: VerificationResult) -> str:
    """Return the canonical digest of one verification result."""
    if type(result) is not VerificationResult:
        raise _refuse(RefusalReason.UNSUPPORTED_TYPE, "a verification result is required")
    return record_digest(result)
