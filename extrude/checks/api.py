"""Wiring-check entry. The body stays refused until Phase 2."""

from extrude.checks.models import PreflightReport
from extrude.ir.models import CircuitIR


def preflight(ir: CircuitIR) -> PreflightReport:
    raise NotImplementedError("not built")
