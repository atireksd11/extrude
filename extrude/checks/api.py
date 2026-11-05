"""Wiring-check entry. It names the broken rule and does not start a simulator."""

from extrude.checks.models import PreflightReport
from extrude.checks.pins import lint_control_pins
from extrude.checks.walk import inspect_design
from extrude.ir.models import CircuitIR


def preflight(ir: CircuitIR) -> PreflightReport:
    return inspect_design(ir)


def inspect_electrical(ir: CircuitIR) -> PreflightReport:
    base = preflight(ir)
    pins = lint_control_pins(ir)
    return PreflightReport(
        blocking=sorted(set(base.blocking + pins.blocking)),
        warnings=sorted(set(base.warnings + pins.warnings)),
    )
