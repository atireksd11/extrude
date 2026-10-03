"""Wiring-check entry. It names the broken rule and does not start a simulator."""

from extrude.checks.models import PreflightReport
from extrude.checks.walk import inspect_design
from extrude.ir.models import CircuitIR


def preflight(ir: CircuitIR) -> PreflightReport:
    return inspect_design(ir)
