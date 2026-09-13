"""Product presentation: the one output convention every command route reports through."""

# evorthon-component: presentation
from .use_case import (
    ENVELOPE_FORM,
    EXIT_OK,
    EXIT_REFUSED,
    EXIT_USAGE,
    NOTHING,
    STATUS_OK,
    STATUS_REFUSED,
    envelope,
    projection_lines,
    refusal_envelope,
    refusal_line,
    result_lines,
    written,
)

__all__ = [
    "ENVELOPE_FORM",
    "EXIT_OK",
    "EXIT_REFUSED",
    "EXIT_USAGE",
    "NOTHING",
    "STATUS_OK",
    "STATUS_REFUSED",
    "envelope",
    "projection_lines",
    "refusal_envelope",
    "refusal_line",
    "result_lines",
    "written",
]
