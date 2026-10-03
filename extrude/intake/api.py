"""Requirement-card entry. The body stays refused until Phase 1."""

from extrude.intake.models import FrozenSpec, NeedsInfo


def resolve(raw_text: str) -> FrozenSpec | NeedsInfo:
    raise NotImplementedError("not built")
