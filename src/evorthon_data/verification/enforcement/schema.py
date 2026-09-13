"""Mechanical JSON Schema and serialization projections for verification records.

The domain dataclasses are the semantic source.  This module deliberately
reads their ordered record and enum inventories rather than maintaining a
second field list.  Generated files are committed projections so adopters can inspect
the portable wire contract without importing Python.
"""
from __future__ import annotations

# evorthon-component: verification_enforcement

import dataclasses
import json
import types
from pathlib import Path
from typing import Any, Union, get_args, get_origin, get_type_hints

from evorthon_data.verification.domain.contracts import (
    DOMAIN_ENUM_TYPES,
    DOMAIN_FIELD_INVENTORY,
    DOMAIN_RECORD_TYPES,
    DOMAIN_TYPE_VERSIONS,
    VERIFICATION_DOMAIN_VERSION,
)


JSON_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"
# The published schema identity follows the domain version rather than
# repeating it, so one bump moves the contract and its identity together.
SCHEMA_IDENTITY = (
    "https://evorthon-data.dev/schemas/verification/domain/"
    f"{VERIFICATION_DOMAIN_VERSION.rsplit('.', 1)[-1]}.json"
)
SCHEMA_FILE_NAME = "verification-domain.schema.json"
SERIALIZATION_FILE_NAME = "verification-serialization.json"
UNKNOWN_FIELD_POLICY = "reject"
UNKNOWN_VERSION_POLICY = "reject"


def _definition_name(contract_type: type) -> str:
    return contract_type.__name__


def _annotation_schema(annotation: Any) -> dict[str, Any]:
    """Project a closed Python contract annotation into JSON Schema."""
    origin = get_origin(annotation)
    if annotation is str:
        return {"type": "string"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is float:
        return {"type": "number"}
    if annotation is type(None):
        return {"type": "null"}
    if isinstance(annotation, type) and issubclass(annotation, str) and hasattr(annotation, "__members__"):
        return {"type": "string", "enum": [member.value for member in annotation]}
    if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
        return {"$ref": f"#/$defs/{_definition_name(annotation)}"}
    if origin is tuple:
        arguments = get_args(annotation)
        item_annotation = arguments[0] if arguments else Any
        schema: dict[str, Any] = {"type": "array", "items": _annotation_schema(item_annotation)}
        if len(arguments) > 1 and arguments[1] is not Ellipsis:
            schema["prefixItems"] = [_annotation_schema(argument) for argument in arguments]
            schema.pop("items")
            schema["minItems"] = len(arguments)
            schema["maxItems"] = len(arguments)
        return schema
    if origin in (Union, types.UnionType):
        return {"anyOf": [_annotation_schema(argument) for argument in get_args(annotation)]}
    if annotation is Any:
        return {}
    raise TypeError(f"unsupported verification contract annotation: {annotation!r}")


def _record_schema(record_type: type) -> dict[str, Any]:
    hints = get_type_hints(record_type)
    fields = [field.name for field in dataclasses.fields(record_type)]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": fields,
        "properties": {field: _annotation_schema(hints[field]) for field in fields},
    }


def generate_json_schema() -> dict[str, Any]:
    """Return the byte-stable JSON Schema projection for every domain record."""
    definitions = {_definition_name(record_type): _record_schema(record_type) for record_type in DOMAIN_RECORD_TYPES}
    envelope_variants = []
    for record_type in DOMAIN_RECORD_TYPES:
        envelope_variants.append(
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["schema_version", "record_type", "record"],
                "properties": {
                    "schema_version": {"const": VERIFICATION_DOMAIN_VERSION},
                    "record_type": {"const": record_type.__name__},
                    "record": {"$ref": f"#/$defs/{record_type.__name__}"},
                },
            }
        )
    return {
        "$schema": JSON_SCHEMA_DRAFT,
        "$id": SCHEMA_IDENTITY,
        "title": "Evorthon Data verification-domain record envelope",
        "description": "Generated from evorthon_data.verification.domain.contracts; unknown fields and schema versions are rejected.",
        "oneOf": envelope_variants,
        "$defs": definitions,
    }


def generate_serialization_projection() -> dict[str, Any]:
    """Return the inspectable wire-contract inventory derived from the domain."""
    return {
        "schema": "evorthon.verification.serialization-projection.v1",
        "semantic_source": "evorthon_data.verification.domain.contracts",
        "domain_schema_version": VERIFICATION_DOMAIN_VERSION,
        "unknown_field_policy": UNKNOWN_FIELD_POLICY,
        "unknown_version_policy": UNKNOWN_VERSION_POLICY,
        "record_types": [
            {
                "name": record_type.__name__,
                "schema_version": DOMAIN_TYPE_VERSIONS[record_type.__name__],
                "fields": list(DOMAIN_FIELD_INVENTORY[record_type.__name__]),
            }
            for record_type in DOMAIN_RECORD_TYPES
        ],
        "enum_types": [
            {
                "name": enum_type.__name__,
                "schema_version": DOMAIN_TYPE_VERSIONS[enum_type.__name__],
                "values": [member.value for member in enum_type],
            }
            for enum_type in DOMAIN_ENUM_TYPES
        ],
    }


def canonical_json_bytes(value: object) -> bytes:
    """Encode a projection with one deterministic JSON representation."""
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def generated_projection_bytes() -> dict[str, bytes]:
    """Return every committed generated projection keyed by its file name."""
    return {
        SCHEMA_FILE_NAME: canonical_json_bytes(generate_json_schema()),
        SERIALIZATION_FILE_NAME: canonical_json_bytes(generate_serialization_projection()),
    }


def write_schema_projections(directory: Path) -> None:
    """Regenerate the committed projections.  Used only by the checked-in tool."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in generated_projection_bytes().items():
        (directory / name).write_bytes(content)


def schema_projection_drift(directory: Path) -> dict[str, str]:
    """Report every missing or stale generated projection without changing files."""
    drift: dict[str, str] = {}
    for name, expected in generated_projection_bytes().items():
        path = directory / name
        if not path.exists():
            drift[name] = "projection is missing"
        elif path.read_bytes() != expected:
            drift[name] = "projection differs from the versioned domain source"
    return drift


__all__ = [
    "JSON_SCHEMA_DRAFT",
    "SCHEMA_IDENTITY",
    "SCHEMA_FILE_NAME",
    "SERIALIZATION_FILE_NAME",
    "UNKNOWN_FIELD_POLICY",
    "UNKNOWN_VERSION_POLICY",
    "canonical_json_bytes",
    "generate_json_schema",
    "generate_serialization_projection",
    "generated_projection_bytes",
    "schema_projection_drift",
    "write_schema_projections",
]
