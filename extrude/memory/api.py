"""Notebook entry. One miss, one notebook."""

from extrude.memory.models import AttributionEvent, ElectricalIdentity, NegativeConstraint
from extrude.memory.store import (
    design_rows,
    design_tries_used,
    from_simulator_log,
    identity_for,
    matching_blocks,
    record as write_row,
    remember_alias,
    request_rows,
    reset,
    tool_rows,
)


def record(event: AttributionEvent) -> None:
    write_row(event)


__all__ = [
    "design_rows",
    "design_tries_used",
    "from_simulator_log",
    "identity_for",
    "matching_blocks",
    "record",
    "remember_alias",
    "request_rows",
    "reset",
    "tool_rows",
]
