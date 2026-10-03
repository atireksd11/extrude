"""Shared-numbers entry. The body stays refused until Phase 3."""

from extrude.intake.models import FrozenSpec
from extrude.ir.models import CircuitIR
from extrude.physics.models import PhysicsValues


def derive(ir: CircuitIR, spec: FrozenSpec) -> PhysicsValues:
    raise NotImplementedError("not built")
