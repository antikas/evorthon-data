"""One machine envelope, one exit-code table, one error shape, and concise human lines.

Every route reports through this module, so a caller reads one convention
whatever route it drove. Nothing here decides anything: it receives what a
route did and writes it down.

The machine form is one JSON object on one line, with keys in code-point order,
no spaces between members, every character in printable ASCII, and a closing
line feed. It always carries the form name, the command, the status, and the
exit code the process returns. A completed route also carries its result; a
refused route carries the error instead.

The readiness projection is rendered here rather than flattened by the route
that read it, because the projection is the one value the presentation surface
shares with a domain component.
"""
from __future__ import annotations

# evorthon-component: presentation
import json

from ..composition import RouteResult
from ..readiness import ReadinessProjection


# The stable name of the output convention this module writes.
ENVELOPE_FORM = "evorthon.cli.v1"
# The one exit-code table. A route returns exactly one of these.
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_REFUSED = 3
STATUS_OK = "ok"
STATUS_REFUSED = "refused"
# What a human line writes for a list that holds nothing.
NOTHING = "none"


def envelope(result: RouteResult) -> dict[str, object]:
    """Build the envelope of one completed route."""
    reported: dict[str, object] = {name: value for name, value in result.values}
    if result.projection is not None:
        reported["segments"] = [_segment_node(segment) for segment in result.projection.segments]
        reported["gaps"] = [_gap_node(gap) for gap in result.projection.gaps]
        reported["open conditions"] = [
            {"key": condition.key.value, "default": condition.default_value, "value": condition.value}
            for condition in result.projection.open_conditions
        ]
    return {
        "form": ENVELOPE_FORM,
        "command": result.command,
        "status": STATUS_OK,
        "exit code": EXIT_OK,
        "result": reported,
    }


def refusal_envelope(command: str, reason: str, detail: str) -> dict[str, object]:
    """Build the envelope of one refused route."""
    return {
        "form": ENVELOPE_FORM,
        "command": command,
        "status": STATUS_REFUSED,
        "exit code": EXIT_REFUSED,
        "error": {"reason": reason, "detail": detail},
    }


def written(payload: dict[str, object]) -> str:
    """Write one envelope in the canonical machine form."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def result_lines(result: RouteResult) -> tuple[str, ...]:
    """Write one completed route as concise human lines."""
    lines = [f"{name}: {_readable(value)}" for name, value in result.values]
    if result.projection is not None:
        lines.extend(projection_lines(result.projection))
    return tuple(lines)


def refusal_line(reason: str, detail: str) -> str:
    """Write one refusal as the single line a person reads."""
    return f"refused: {reason}: {detail}"


def projection_lines(projection: ReadinessProjection) -> tuple[str, ...]:
    """Write one readiness projection as concise human lines."""
    lines = []
    for segment in projection.segments:
        lines.append(
            f"segment {segment.segment_id}: {segment.state.value}, "
            f"{segment.diagnostic_strength.value}, {len(segment.gaps)} gaps"
        )
    for gap in projection.gaps:
        fillable = "synthetic fill available" if gap.synthetic_fillable else "no synthetic fill"
        owner = gap.suggested_owner.identity if gap.suggested_owner is not None else NOTHING
        lines.append(
            f"gap {gap.kind.value} on {gap.subject}: owner {owner}, {fillable}, "
            f"suggested title {gap.suggested_title}"
        )
    for condition in projection.open_conditions:
        lines.append(f"open condition {condition.key.value}: {condition.value}")
    return tuple(lines)


def _segment_node(segment: object) -> dict[str, object]:
    return {
        "segment": segment.segment_id,
        "reaches": segment.reaches.value,
        "route": None if segment.route is None else segment.route.value,
        "state": segment.state.value,
        "diagnostic strength": segment.diagnostic_strength.value,
        "acceptable now": segment.acceptable_now,
        "facts": [
            {"kind": fact.kind.value, "subject": fact.subject, "evidence": fact.evidence.value}
            for fact in segment.facts
        ],
        "gaps": [_gap_node(gap) for gap in segment.gaps],
    }


def _gap_node(gap: object) -> dict[str, object]:
    return {
        "kind": gap.kind.value,
        "subject": gap.subject,
        "segment": gap.segment_id,
        "suggested owner": None if gap.suggested_owner is None else gap.suggested_owner.identity,
        "synthetic fillable": gap.synthetic_fillable,
        "suggested title": gap.suggested_title,
    }


def _readable(value: object) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(entry) for entry in value) or NOTHING
    return str(value)
