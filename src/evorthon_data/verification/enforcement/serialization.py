"""Closed serialization for the generated verification-domain wire contract."""
from __future__ import annotations

# evorthon-component: verification_enforcement

import dataclasses
import json
import types
from collections.abc import Mapping
from enum import Enum
from typing import Any, Union, get_args, get_origin, get_type_hints

from evorthon_data.verification.domain.contracts import (
    DOMAIN_RECORD_TYPES,
    VERIFICATION_DOMAIN_VERSION,
)
from evorthon_data.verification.enforcement.schema import (
    UNKNOWN_FIELD_POLICY,
    UNKNOWN_VERSION_POLICY,
)
from evorthon_data.verification.enforcement.validation import validate_verification_record


class SerializationError(ValueError):
    """Base refusal for malformed external verification records."""


class UnknownSchemaVersionError(SerializationError):
    """Raised when a wire record uses a schema version this product does not know."""


class UnknownRecordTypeError(SerializationError):
    """Raised when a wire record declares a type outside the domain inventory."""


class UnknownFieldError(SerializationError):
    """Raised when an external record attempts an undeclared field."""


_RECORD_TYPE_BY_NAME = {record_type.__name__: record_type for record_type in DOMAIN_RECORD_TYPES}


def _primitive(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: _primitive(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, tuple):
        return [_primitive(item) for item in value]
    return value


def serialize_record(record: object) -> dict[str, object]:
    """Serialize one known domain record into its closed envelope.

    The envelope version is the version policy boundary.  Individual ``version``
    fields remain immutable identities supplied by an adopting engagement, so
    they are not mistaken for an extensibility mechanism for this wire schema.
    """
    record_type = type(record)
    if record_type not in DOMAIN_RECORD_TYPES:
        raise UnknownRecordTypeError(
            f"record type is not in the verification-domain inventory: {record_type.__name__}"
        )
    validate_verification_record(record)
    envelope: dict[str, object] = {
        "schema_version": VERIFICATION_DOMAIN_VERSION,
        "record_type": record_type.__name__,
        "record": _primitive(record),
    }
    # Rehydrate once so callers cannot serialize malformed values by bypassing
    # Python's otherwise non-enforcing dataclass annotations.
    deserialize_record(envelope)
    return envelope


def serialize_json(record: object) -> str:
    """Return the deterministic JSON text for one domain record."""
    return json.dumps(serialize_record(record), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _decode(annotation: Any, value: object, path: str) -> object:
    origin = get_origin(annotation)
    if annotation is Any:
        return value
    if annotation is str:
        if not isinstance(value, str):
            raise SerializationError(f"{path} must be a string")
        return value
    if annotation is int:
        if type(value) is not int:
            raise SerializationError(f"{path} must be an integer")
        return value
    if annotation is bool:
        if type(value) is not bool:
            raise SerializationError(f"{path} must be a boolean")
        return value
    if annotation is float:
        if type(value) not in (int, float):
            raise SerializationError(f"{path} must be a number")
        return float(value)
    if annotation is type(None):
        if value is not None:
            raise SerializationError(f"{path} must be null")
        return None
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        if not isinstance(value, str):
            raise SerializationError(f"{path} must be an enum string")
        try:
            return annotation(value)
        except ValueError as exc:
            raise SerializationError(f"{path} has an unknown {annotation.__name__} value: {value!r}") from exc
    if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
        if not isinstance(value, Mapping):
            raise SerializationError(f"{path} must be an object")
        if not all(isinstance(field, str) for field in value):
            raise SerializationError(f"{path} field names must be strings")
        hints = get_type_hints(annotation)
        expected = tuple(field.name for field in dataclasses.fields(annotation))
        observed = tuple(value.keys())
        unknown = sorted(set(observed) - set(expected))
        missing = [field for field in expected if field not in value]
        if unknown:
            raise UnknownFieldError(f"{path} contains unknown fields under {UNKNOWN_FIELD_POLICY} policy: {', '.join(unknown)}")
        if missing:
            raise SerializationError(f"{path} is missing required fields: {', '.join(missing)}")
        return annotation(**{field: _decode(hints[field], value[field], f"{path}.{field}") for field in expected})
    if origin is tuple:
        if not isinstance(value, list):
            raise SerializationError(f"{path} must be an array")
        arguments = get_args(annotation)
        if len(arguments) > 1 and arguments[1] is not Ellipsis:
            if len(value) != len(arguments):
                raise SerializationError(f"{path} must contain exactly {len(arguments)} values")
            return tuple(_decode(item_type, item, f"{path}[{index}]") for index, (item_type, item) in enumerate(zip(arguments, value)))
        item_type = arguments[0] if arguments else Any
        return tuple(_decode(item_type, item, f"{path}[{index}]") for index, item in enumerate(value))
    if origin in (Union, types.UnionType):
        errors: list[str] = []
        for candidate in get_args(annotation):
            try:
                return _decode(candidate, value, path)
            except SerializationError as exc:
                errors.append(str(exc))
        raise SerializationError(f"{path} does not match any permitted contract shape: {'; '.join(errors)}")
    raise SerializationError(f"{path} has unsupported contract annotation {annotation!r}")


def deserialize_record(envelope: Mapping[str, object]) -> object:
    """Rehydrate a record and reject unknown versions, types, and fields."""
    if not isinstance(envelope, Mapping):
        raise SerializationError("record envelope must be an object")
    if not all(isinstance(field, str) for field in envelope):
        raise SerializationError("record envelope field names must be strings")
    expected = {"schema_version", "record_type", "record"}
    unknown = sorted(set(envelope) - expected)
    missing = sorted(expected - set(envelope))
    if unknown:
        raise UnknownFieldError(f"record envelope contains unknown fields under {UNKNOWN_FIELD_POLICY} policy: {', '.join(unknown)}")
    if missing:
        raise SerializationError(f"record envelope is missing required fields: {', '.join(missing)}")
    if envelope["schema_version"] != VERIFICATION_DOMAIN_VERSION:
        raise UnknownSchemaVersionError(
            f"schema version {envelope['schema_version']!r} is unsupported under {UNKNOWN_VERSION_POLICY} policy"
        )
    record_name = envelope["record_type"]
    if not isinstance(record_name, str) or record_name not in _RECORD_TYPE_BY_NAME:
        raise UnknownRecordTypeError(f"record type {record_name!r} is not in the verification-domain inventory")
    record = _decode(_RECORD_TYPE_BY_NAME[record_name], envelope["record"], "record")
    validate_verification_record(record)
    return record


def deserialize_json(serialized: str | bytes) -> object:
    """Parse and fail closed on non-object JSON or a malformed record envelope."""
    try:
        envelope = json.loads(serialized)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SerializationError("record is not valid JSON") from exc
    if not isinstance(envelope, Mapping):
        raise SerializationError("record envelope must be a JSON object")
    return deserialize_record(envelope)


# British spellings make the portable public contract easier to discover while
# retaining the standard-library spelling as the canonical implementation API.
serialise_record = serialize_record
serialise_json = serialize_json
deserialise_record = deserialize_record
deserialise_json = deserialize_json


__all__ = [
    "SerializationError",
    "UnknownFieldError",
    "UnknownRecordTypeError",
    "UnknownSchemaVersionError",
    "deserialize_json",
    "deserialize_record",
    "deserialise_json",
    "deserialise_record",
    "serialise_json",
    "serialise_record",
    "serialize_json",
    "serialize_record",
]
