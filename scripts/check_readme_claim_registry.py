#!/usr/bin/env python3
"""Fail closed when README claim status stops matching the relational registry."""
# evorthon-implements: EVD-README-039
from __future__ import annotations

import pathlib
import re
import tomllib


ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "docs" / "product" / "readme-claim-registry.toml"
CLAIM_MARKER_LINE = re.compile(r"\s*<!--\s*evorthon-claim:\s*([A-Z0-9-]+)\s*-->\s*")
LIST_ITEM = re.compile(r"\s*(?:[-*+]\s+|\d+[.)]\s+)")
REGISTRY_FIELDS = {"schema", "claim_source", "status_guide", "relation"}
RELATION_FIELDS = {
    "claim_id",
    "status",
    "implementation_state",
    "evidence_state",
    "implementation_refs",
    "evidence_refs",
}
STATUS_STATES = {
    "available": ("available", "verified"),
    "in-development": ("in-development", "not-yet-verified"),
    "environment-owned": ("not-provided", "adopter-owned"),
}


class RegistryValidationError(ValueError):
    """The registry cannot support the README's capability status statement."""


def load_registry(path: pathlib.Path = REGISTRY_PATH) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def readme_claim_ids(readme: pathlib.Path) -> list[str]:
    return readme_claim_ids_from_text(readme.read_text(encoding="utf-8"))


def readme_claim_ids_from_text(text: str) -> list[str]:
    """Require each material README block to end with one stable claim marker."""
    claim_ids: list[str] = []
    pending_claim_line: int | None = None
    in_fenced_block = False

    def require_marker() -> None:
        if pending_claim_line is not None:
            raise RegistryValidationError(f"unmarked README claim text at line {pending_claim_line}")

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_fenced_block:
                require_marker()
            in_fenced_block = not in_fenced_block
            continue
        if in_fenced_block:
            continue
        if not stripped:
            require_marker()
            continue
        marker = CLAIM_MARKER_LINE.fullmatch(line)
        if marker:
            if pending_claim_line is None:
                raise RegistryValidationError(f"README claim marker at line {line_number} has no material claim text")
            claim_ids.append(marker.group(1))
            pending_claim_line = None
            continue
        if stripped.startswith("#"):
            require_marker()
            continue
        if LIST_ITEM.match(line):
            require_marker()
            pending_claim_line = line_number
            continue
        if pending_claim_line is None:
            pending_claim_line = line_number
    require_marker()
    return claim_ids


def _require_string_list(value: object, field: str, claim_id: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise RegistryValidationError(f"{claim_id}: {field} must be a list of nonempty strings")
    return value


def _repository_relative_target(root: pathlib.Path, path_text: str, error: str) -> pathlib.Path:
    path = pathlib.PurePosixPath(path_text)
    windows_path = pathlib.PureWindowsPath(path_text)
    if (
        not path_text
        or path.is_absolute()
        or windows_path.drive
        or windows_path.root
        or ".." in path.parts
        or chr(92) in path_text
    ):
        raise RegistryValidationError(error)
    target = root.joinpath(*path.parts)
    try:
        target.resolve().relative_to(root.resolve())
    except (OSError, ValueError) as exc:
        raise RegistryValidationError(error) from exc
    return target


def _validate_reference(root: pathlib.Path, reference: str, claim_id: str, role: str) -> None:
    path_text, separator, node_id = reference.partition("::")
    if not separator or node_id != claim_id:
        raise RegistryValidationError(f"{claim_id}: {role} must use a claim-bound reference: {reference}")
    target = _repository_relative_target(
        root,
        path_text,
        f"{claim_id}: invalid relative reference {reference}",
    )
    if not target.is_file():
        raise RegistryValidationError(f"{claim_id}: referenced path is missing: {reference}")
    markers = {
        f"# evorthon-{role}: {claim_id}",
        f"<!-- evorthon-{role}: {claim_id} -->",
    }
    lines = {line.strip() for line in target.read_text(encoding="utf-8").splitlines()}
    if markers.isdisjoint(lines):
        raise RegistryValidationError(f"{claim_id}: {role} claim binding is missing: {reference}")


def validate_registry_data(root: pathlib.Path, registry: dict) -> dict[str, int]:
    if not isinstance(registry, dict) or set(registry) != REGISTRY_FIELDS:
        raise RegistryValidationError("registry may contain only schema, claim source, status guide and relations")
    if registry.get("schema") != "evorthon-data.readme-claim-registry.v1":
        raise RegistryValidationError("unsupported registry schema")
    claim_source = registry.get("claim_source")
    if not isinstance(claim_source, str) or not claim_source:
        raise RegistryValidationError("claim_source is required")
    readme = _repository_relative_target(root, claim_source, f"invalid claim source: {claim_source}")
    if not readme.is_file():
        raise RegistryValidationError(f"claim source is missing: {claim_source}")
    status_guide = registry.get("status_guide")
    if not isinstance(status_guide, str) or not status_guide:
        raise RegistryValidationError("status_guide is required")
    status_guide_path = _repository_relative_target(root, status_guide, f"invalid status guide: {status_guide}")
    if not status_guide_path.is_file():
        raise RegistryValidationError(f"status guide is missing: {status_guide}")
    marker_ids = readme_claim_ids(readme)
    duplicate_markers = sorted({claim_id for claim_id in marker_ids if marker_ids.count(claim_id) > 1})
    if duplicate_markers:
        raise RegistryValidationError("duplicate README claim identifier: " + ", ".join(duplicate_markers))
    relations = registry.get("relation")
    if not isinstance(relations, list) or not relations:
        raise RegistryValidationError("at least one registry relation is required")

    relation_ids: list[str] = []
    for relation in relations:
        if not isinstance(relation, dict) or set(relation) != RELATION_FIELDS:
            raise RegistryValidationError("registry relations may contain only identifiers, states and references")
        claim_id = relation["claim_id"]
        if not isinstance(claim_id, str) or not claim_id:
            raise RegistryValidationError("registry relation has an invalid claim identifier")
        relation_ids.append(claim_id)
        status = relation["status"]
        if status not in STATUS_STATES:
            raise RegistryValidationError(f"{claim_id}: unsupported status {status}")
        expected_implementation, expected_evidence = STATUS_STATES[status]
        if (relation["implementation_state"], relation["evidence_state"]) != (expected_implementation, expected_evidence):
            raise RegistryValidationError(f"{claim_id}: status and implementation/evidence states disagree")
        implementation_refs = _require_string_list(relation["implementation_refs"], "implementation_refs", claim_id)
        evidence_refs = _require_string_list(relation["evidence_refs"], "evidence_refs", claim_id)
        if status == "available" and (not implementation_refs or not evidence_refs):
            raise RegistryValidationError(f"{claim_id}: falsely implemented relation has no implementation and evidence references")
        if status != "available" and (implementation_refs or evidence_refs):
            raise RegistryValidationError(f"{claim_id}: non-available relation must not imply shipped evidence")
        for reference in implementation_refs:
            _validate_reference(root, reference, claim_id, "implements")
        for reference in evidence_refs:
            _validate_reference(root, reference, claim_id, "verifies")

    duplicate_relations = sorted({claim_id for claim_id in relation_ids if relation_ids.count(claim_id) > 1})
    if duplicate_relations:
        raise RegistryValidationError("duplicate registry relation: " + ", ".join(duplicate_relations))
    marker_set, relation_set = set(marker_ids), set(relation_ids)
    missing = sorted(marker_set - relation_set)
    if missing:
        raise RegistryValidationError("README claims without registry relation: " + ", ".join(missing))
    orphaned = sorted(relation_set - marker_set)
    if orphaned:
        raise RegistryValidationError("orphan registry relation: " + ", ".join(orphaned))
    return {"claims": len(marker_ids), "relations": len(relations)}


def main() -> int:
    try:
        result = validate_registry_data(ROOT, load_registry())
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        raise SystemExit(f"README claim registry validation failed: {exc}") from exc
    print(f"README claim registry validation passed: {result['claims']} claims")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
