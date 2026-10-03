"""Deck writer. The simulated capacitance is the Phase 3 use-value."""

from extrude.emit.deck import holdup_deck
from extrude.ir.models import CircuitIR
from extrude.physics.models import PhysicsValues


def emit_cir(ir: CircuitIR, physics: PhysicsValues) -> str:
    return holdup_deck(ir, physics)
