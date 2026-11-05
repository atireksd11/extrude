"""Checker order. New checks are added here, not in the HTTP shape."""

from extrude.checks.api import inspect_electrical
from extrude.checks.models import PreflightReport, ToleranceReport
from extrude.checks.tolerance import HoleCheck, WallCheck, check_tolerance
from extrude.ir.mechanical import MechanicalIR
from extrude.ir.models import CircuitIR
from extrude.physics.derate import derate_capacitor, load_curves, minimum_capacitance


def run_mechanical(design: MechanicalIR, filament: str) -> ToleranceReport:
    holes = [
        HoleCheck(name=hole.name, diameter_mm=hole.diameter_mm, intended_insert=hole.intended_insert)
        for hole in design.holes
        if hole.intended_insert and hole.intended_insert != "none"
    ]
    walls = [
        WallCheck(name=wall.name, thickness_mm=wall.thickness_mm, normal_z=wall.normal_z)
        for wall in design.walls
    ]
    return check_tolerance(holes=holes, walls=walls, filament=filament)


def run_electrical(design: CircuitIR) -> PreflightReport:
    base = inspect_electrical(design)
    capacitance = _capacitance(design)
    return PreflightReport(
        blocking=sorted(set(base.blocking + capacitance.blocking)),
        warnings=sorted(set(base.warnings + capacitance.warnings)),
    )


def _capacitance(design: CircuitIR) -> PreflightReport:
    curves = load_curves()
    caps = []
    blocking: list[str] = []
    warnings: list[str] = []
    for part in design.parts:
        if part.kind != "capacitor" or part.capacitance is None:
            continue
        cap, notes = derate_capacitor(part, part.bias_v, curves)
        caps.append(cap)
        for note in notes:
            text = f"{note.code}:{note.detail}"
            if note.severity == "fail":
                blocking.append(text)
            else:
                warnings.append(text)
    short = minimum_capacitance(caps, design.c_min)
    if short is not None:
        text = f"{short.code}:{short.detail}"
        if short.severity == "fail":
            blocking.append(text)
        else:
            warnings.append(text)
    return PreflightReport(blocking=blocking, warnings=warnings)
