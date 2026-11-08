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


def wiring_evidence(ir: CircuitIR) -> bool:
    """A clean wiring verdict needs parts and actual, attributable connections."""
    refs = {part.refdes for part in ir.parts}
    return bool(refs and ir.pins and all(
        pin.refdes in refs and pin.name.strip() and
        (pin.state == "nc" or (pin.state == "connected" and pin.net and pin.net.strip()))
        for pin in ir.pins
    ) and any(pin.state == "connected" for pin in ir.pins)
        and refs.issubset({pin.refdes for pin in ir.pins}))
