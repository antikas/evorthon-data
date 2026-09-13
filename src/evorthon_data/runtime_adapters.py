"""Containment-checked discovery pointers for supported runtime adapters."""
from __future__ import annotations

# evorthon-component: composition

import re
from pathlib import Path

ADAPTER_GLOBS = ("CLAUDE.md", ".github/copilot-instructions.md", ".github/agents/*.md", ".github/prompts/*.md", ".github/skills/**/SKILL.md")
POINTER = re.compile(r"(?:Read|Use)\s+`([^`]+)`|@([A-Za-z0-9_./-]+\.md)")


def adapter_files(root: Path) -> list[Path]:
    return sorted({path for pattern in ADAPTER_GLOBS for path in root.glob(pattern) if path.is_file()})


def validate_runtime_adapters(root: Path) -> list[str]:
    root = root.resolve()
    failures: list[str] = []
    for adapter in adapter_files(root):
        text = adapter.read_text(encoding="utf-8")
        matches = list(POINTER.finditer(text))
        if not matches:
            failures.append(f"{adapter.relative_to(root)}: no declared local target")
            continue
        for match in matches:
            declared = next(value for value in match.groups() if value is not None)
            target = Path(declared)
            if target.is_absolute() or any(part in {"", "."} for part in target.parts) or any(token in declared for token in ("*", "?", "[", "]")):
                failures.append(f"{adapter.relative_to(root)}: ambiguous or absolute target {declared}")
                continue
            resolved = (adapter.parent / target).resolve()
            try:
                resolved.relative_to(root)
            except ValueError:
                failures.append(f"{adapter.relative_to(root)}: outside target {declared}")
                continue
            if not resolved.exists():
                failures.append(f"{adapter.relative_to(root)}: missing target {declared}")
    return failures
