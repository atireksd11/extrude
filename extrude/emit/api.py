"""Deck-writer entry. The body stays refused until Phase 4."""

from extrude.ir.models import CircuitIR
from extrude.physics.models import PhysicsValues


def emit_cir(ir: CircuitIR, physics: PhysicsValues) -> str:
    raise NotImplementedError("not built")
