"""One capacitance number from a checked-in curve, a series match, or a generic screen."""

import json
from pathlib import Path

from extrude.ir.models import Part
from extrude.physics.models import CapValue, CurveSource, PhysicsFinding

_CLASS_II = {"X5R", "X7R", "X6S", "Y5V", "Z5U"}
_CURVES = Path(__file__).parent / "curves"
_STILL_AIR = "estimate_still_air_datasheet"


def load_curves() -> list[dict]:
    found = []
    for path in sorted(_CURVES.glob("*.json")):
        found.append(json.loads(path.read_text(encoding="utf-8")))
    return found


def derate_capacitor(part: Part, bias_v: float | None, curves: list[dict]) -> tuple[CapValue, list[PhysicsFinding]]:
    nominal = part.capacitance or 0.0
    tolerance = part.tolerance or 0.0
    dielectric = (part.dielectric or "").upper()
    findings: list[PhysicsFinding] = []
    if not _is_class_ii(dielectric):
        c_eff = nominal
        return (
            _cap(part, bias_v or 0.0, c_eff, tolerance, CurveSource.not_class_ii, None),
            findings,
        )
    if bias_v is None:
        findings.append(
            PhysicsFinding(
                code="bias_unknown",
                severity="warn",
                detail=f"{part.refdes} has no DC bias, so the ceramic loss is not applied",
            )
        )
        return _cap(part, 0.0, nominal, tolerance, CurveSource.generic_screen, None), findings
    curve = _match_curve(part, curves)
    if curve is None:
        c_eff = nominal * 0.5
        return (
            _cap(part, bias_v, c_eff, tolerance, CurveSource.generic_screen, None),
            findings,
        )
    ratio, clamped = _ratio_at(curve["points"], abs(bias_v))
    if clamped:
        findings.append(
            PhysicsFinding(
                code="bias_above_curve",
                severity="warn",
                detail=f"{part.refdes} bias is above the last point of {curve['id']}",
            )
        )
    source = CurveSource.vendor_table if part.curve_id else CurveSource.same_mfr_series
    return _cap(part, abs(bias_v), nominal * ratio, tolerance, source, curve["id"]), findings


def minimum_capacitance(
    caps: list[CapValue], required: float | None
) -> PhysicsFinding | None:
    if required is None or not caps:
        return None
    total = sum(cap.c_use for cap in caps)
    if total + 1e-18 >= required:
        return None
    hard = any(cap.curve_source is not CurveSource.generic_screen for cap in caps)
    detail = f"use-value {total:.6g} F is under the required {required:.6g} F"
    if hard:
        return PhysicsFinding(code="capacitance_below_minimum", severity="fail", detail=detail)
    return PhysicsFinding(code="capacitance_below_minimum", severity="warn", detail=detail)


def _is_class_ii(dielectric: str) -> bool:
    return dielectric in _CLASS_II


def _match_curve(part: Part, curves: list[dict]) -> dict | None:
    if part.curve_id:
        for curve in curves:
            if curve["id"] == part.curve_id:
                return curve
        return None
    for curve in curves:
        if (
            _same(curve.get("manufacturer"), part.manufacturer)
            and _same(curve.get("series"), part.series)
            and _same(curve.get("case"), part.case)
            and _same(curve.get("dielectric"), part.dielectric)
            and curve.get("voltage_rating") == part.voltage_rating
            and curve.get("capacitance") == part.capacitance
        ):
            return curve
    return None


def _same(left: object, right: object) -> bool:
    if left is None or right is None:
        return False
    return str(left).upper() == str(right).upper()


def _ratio_at(points: list[dict], bias: float) -> tuple[float, bool]:
    ordered = sorted(points, key=lambda point: point["v"])
    if bias <= ordered[0]["v"]:
        return float(ordered[0]["ratio"]), False
    if bias >= ordered[-1]["v"]:
        return float(ordered[-1]["ratio"]), bias > ordered[-1]["v"]
    for left, right in zip(ordered, ordered[1:]):
        if left["v"] <= bias <= right["v"]:
            span = right["v"] - left["v"]
            weight = (bias - left["v"]) / span if span else 0.0
            ratio = left["ratio"] + weight * (right["ratio"] - left["ratio"])
            return float(ratio), False
    return float(ordered[-1]["ratio"]), True


def _cap(
    part: Part,
    bias: float,
    c_eff: float,
    tolerance: float,
    source: CurveSource,
    curve_id: str | None,
) -> CapValue:
    return CapValue(
        refdes=part.refdes,
        c_nominal=part.capacitance or 0.0,
        c_eff=c_eff,
        c_use=c_eff * (1.0 - tolerance),
        curve_source=source,
        v_dc=bias,
        curve_id=curve_id,
    )
