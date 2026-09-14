#!/usr/bin/env python3
"""Render the architecture owner and its deny-by-default dependency policy."""
from __future__ import annotations

import argparse
import html
import pathlib
import re
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parents[1]
NODE = re.compile(r'([a-z][a-z0-9_-]*):\s*"([^"]+)"$')
EDGE = re.compile(r"[a-z][a-z0-9_-]*(?:\s*->\s*[a-z][a-z0-9_-]*)+$")
DEPENDENCY_RULE = re.compile(r"(allow|forbid):\s*([a-z][a-z0-9_-]*)\s*->\s*([a-z][a-z0-9_-]*)$")


@dataclass(frozen=True)
class Architecture:
    """The parsed D2 model, including its complete direct-import boundary."""

    direction: str
    nodes: dict[str, str]
    routes: tuple[tuple[str, str], ...]
    allowed_dependencies: frozenset[tuple[str, str]]
    explicit_forbidden_dependencies: frozenset[tuple[str, str]]

    @property
    def forbidden_dependencies(self) -> frozenset[tuple[str, str]]:
        """All cross-component imports not explicitly allowed are forbidden."""
        pairs = {
            (left, right)
            for left in self.nodes
            for right in self.nodes
            if left != right
        }
        return frozenset(pairs - self.allowed_dependencies)


def _validate_dependency_edges(
    nodes: dict[str, str],
    edges: set[tuple[str, str]],
    label: str,
) -> None:
    unknown = {identity for edge in edges for identity in edge if identity not in nodes}
    if unknown:
        raise ValueError(f"{label} references undeclared node: " + ", ".join(sorted(unknown)))
    if any(left == right for left, right in edges):
        raise ValueError(f"{label} cannot contain a self dependency")


def parse(source: pathlib.Path) -> Architecture:
    direction: str | None = None
    dependency_policy: str | None = None
    nodes: dict[str, str] = {}
    routes: list[tuple[str, str]] = []
    allowed: set[tuple[str, str]] = set()
    explicit_forbidden: set[tuple[str, str]] = set()
    seen_rules: set[tuple[str, str, str]] = set()

    for number, raw in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("direction:"):
            if direction is not None:
                raise ValueError(f"line {number}: duplicate direction")
            direction = line.partition(":")[2].strip()
            if direction not in {"down", "right"}:
                raise ValueError(f"line {number}: unsupported direction")
            continue
        if line.startswith("dependency-policy:"):
            if dependency_policy is not None:
                raise ValueError(f"line {number}: duplicate dependency policy")
            dependency_policy = line.partition(":")[2].strip()
            if dependency_policy != "deny-by-default":
                raise ValueError(f"line {number}: unsupported dependency policy")
            continue
        rule = DEPENDENCY_RULE.fullmatch(line)
        if rule:
            kind, left, right = rule.groups()
            edge = (left, right)
            key = (kind, *edge)
            if key in seen_rules:
                raise ValueError(f"line {number}: duplicate {kind} dependency")
            seen_rules.add(key)
            (allowed if kind == "allow" else explicit_forbidden).add(edge)
            continue
        node = NODE.fullmatch(line)
        if node:
            identity, label = node.groups()
            if identity in nodes:
                raise ValueError(f"line {number}: duplicate node")
            nodes[identity] = label
            continue
        if EDGE.fullmatch(line):
            chain = [part.strip() for part in line.split("->")]
            routes.extend(zip(chain, chain[1:]))
            continue
        raise ValueError(f"line {number}: unsupported D2 syntax")

    if direction is None or dependency_policy is None or not nodes or not routes:
        raise ValueError("D2 model requires direction, dependency policy, nodes and routes")
    if len(set(routes)) != len(routes):
        raise ValueError("duplicate route")
    _validate_dependency_edges(nodes, set(routes), "route")
    _validate_dependency_edges(nodes, allowed, "allowed dependency")
    _validate_dependency_edges(nodes, explicit_forbidden, "forbidden dependency")
    if not allowed:
        raise ValueError("D2 model requires at least one allowed dependency")
    if not explicit_forbidden:
        raise ValueError("D2 model requires an explicit protected boundary")
    overlap = allowed & explicit_forbidden
    if overlap:
        pairs = ", ".join(f"{left}->{right}" for left, right in sorted(overlap))
        raise ValueError("dependency cannot be both allowed and forbidden: " + pairs)
    return Architecture(
        direction=direction,
        nodes=nodes,
        routes=tuple(routes),
        allowed_dependencies=frozenset(allowed),
        explicit_forbidden_dependencies=frozenset(explicit_forbidden),
    )


def rendered(source: pathlib.Path) -> tuple[str, str]:
    architecture = parse(source)
    lines = ["# Evorthon Data Harness architecture", "", f"Direction: `{architecture.direction}`.", "", "## Components", ""]
    lines.extend(f"- `{identity}` - {label}" for identity, label in architecture.nodes.items())
    lines.extend(["", "## Routes", ""])
    lines.extend(f"- `{left} -> {right}`" for left, right in architecture.routes)
    lines.extend([
        "",
        "## Direct dependency policy",
        "",
        "Direct imports between product components are deny-by-default: every cross-component import not listed as allowed is forbidden.",
        "",
        "### Allowed direct dependencies",
        "",
    ])
    lines.extend(f"- `{left} -> {right}`" for left, right in sorted(architecture.allowed_dependencies))
    lines.extend(["", "### Explicitly protected boundaries", ""])
    lines.extend(f"- `{left} -> {right}`" for left, right in sorted(architecture.explicit_forbidden_dependencies))
    mirror = "\n".join(lines) + "\n"

    order = list(architecture.nodes)
    positions = {
        identity: ((100 + index * 190, 90) if architecture.direction == "right" else (250, 70 + index * 105))
        for index, identity in enumerate(order)
    }
    width, height = ((190 * len(order) + 80, 210) if architecture.direction == "right" else (500, 105 * len(order) + 70))
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z"/></marker></defs>',
    ]
    for left, right in architecture.routes:
        x1, y1 = positions[left]
        x2, y2 = positions[right]
        svg.append(f'<line data-edge="{left}->{right}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#334155" marker-end="url(#arrow)"/>')
    for identity, label in architecture.nodes.items():
        x, y = positions[identity]
        svg.append(f'<g data-node="{identity}"><rect x="{x - 75}" y="{y - 24}" width="150" height="48" rx="8" fill="#eff6ff" stroke="#2563eb"/><text x="{x}" y="{y - 4}" text-anchor="middle">{html.escape(identity)}</text><text x="{x}" y="{y + 13}" text-anchor="middle">{html.escape(label)}</text></g>')
    svg.append("</svg>")
    return mirror, "\n".join(svg) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--source", type=pathlib.Path, default=ROOT / "docs/architecture/solution-architecture.d2")
    parser.add_argument("--mirror", type=pathlib.Path, default=ROOT / "docs/architecture/solution-architecture.md")
    parser.add_argument("--svg", type=pathlib.Path, default=ROOT / "docs/architecture/solution-architecture.svg")
    args = parser.parse_args()
    mirror, svg = rendered(args.source)
    if args.check:
        if not args.mirror.exists() or not args.svg.exists() or args.mirror.read_text(encoding="utf-8") != mirror or args.svg.read_text(encoding="utf-8") != svg:
            raise SystemExit("architecture render drift")
        print("architecture render matches D2")
        return 0
    args.mirror.write_text(mirror, encoding="utf-8", newline="\n")
    args.svg.write_text(svg, encoding="utf-8", newline="\n")
    print("rendered architecture from D2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
