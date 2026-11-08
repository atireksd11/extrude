"""Shared numbers. Ripple and a later deck must read c_use from this result."""

import math

from extrude.intake.models import FrozenSpec
from extrude.ir.models import CircuitIR
from extrude.physics.derate import derate_capacitor, load_curves, minimum_capacitance
from extrude.physics.models import PhysicsFinding, PhysicsValues
from extrude.physics.ripple import buck_ripple

_STILL_AIR = "estimate_still_air_datasheet"
_AMBIENT_C = 25.0


def derive(ir: CircuitIR, spec: FrozenSpec) -> PhysicsValues:
    curves = load_curves()
    capacitors = [part for part in ir.parts if part.kind == "capacitor" and part.capacitance is not None]
    borrowed = _bias_from_spec(spec) if len(capacitors) == 1 else None
    caps = []
    findings: list[PhysicsFinding] = []
    for part in capacitors:
        bias = part.bias_v if part.bias_v is not None else borrowed
        cap, notes = derate_capacitor(part, bias, curves)
        caps.append(cap)
        findings.extend(notes)
    findings_or_none = minimum_capacitance(caps, spec.values_si.get("c_min"))
    if findings_or_none is not None:
        findings.append(findings_or_none)
    inductance = _first(ir, "inductor", "inductance")
    ripple_caps = _output_caps(caps, spec)
    ripple_ids = {cap.refdes for cap in ripple_caps}
    missing_esr = [part.refdes for part in ir.parts if part.refdes in ripple_ids and part.esr is None]
    esr = sum(part.esr or 0.0 for part in ir.parts if part.refdes in ripple_ids)
    c_use = sum(cap.c_use for cap in ripple_caps) if ripple_caps else None
    ripple, mode = buck_ripple(
        spec.values_si.get("vin"),
        spec.values_si.get("vout"),
        spec.values_si.get("i_load"),
        ir.f_sw,
        inductance,
        c_use,
        esr,
    )
    switching = ir.f_sw is not None or inductance is not None
    if switching and missing_esr and c_use:
        findings.append(
            PhysicsFinding(
                code="esr_unknown",
                severity="warn",
                detail=(
                    "ESR was not given for "
                    + ", ".join(missing_esr)
                    + ", so ripple ignores series resistance and can look smaller than the part"
                ),
            )
        )
    if switching and mode == "dcm":
        findings.append(
            PhysicsFinding(
                code="ripple_not_covered",
                severity="warn",
                detail="inductor current reaches zero, so continuous-conduction ripple is not used",
            )
        )
    if spec.task_class == "buck":
        topology = _buck_topology(ir, ripple_ids)
        limit = spec.values_si.get("ripple_pp")
        if not topology:
            findings.append(PhysicsFinding(code="buck_topology", severity="fail",
                detail="Buck topology incomplete: require a connected regulator, switch-to-output inductor and output-to-ground capacitor."))
        if ripple is None or not math.isfinite(ripple) or mode != "ccm":
            findings.append(PhysicsFinding(code="ripple_unverified", severity="fail",
                detail=f"Buck ripple not checked: {mode}; require frequency, inductance and output capacitance in CCM."))
        elif limit is None or not math.isfinite(limit) or limit <= 0 or ripple > limit:
            findings.append(PhysicsFinding(code="ripple_limit", severity="fail",
                detail=f"Buck ripple {ripple:g} V exceeds or lacks the frozen limit {limit} V."))
    power, tj, note = _heat(ir, spec)
    return PhysicsValues(
        caps=caps,
        vout_dc=spec.values_si.get("vout"),
        ripple_pp=ripple if switching else None,
        conduction=mode if switching else None,
        p_diss_w=power,
        tj_estimate_c=tj,
        heat_note=note,
        findings=findings,
    )


def _output_caps(caps, spec: FrozenSpec):
    vout = spec.values_si.get("vout")
    if vout is None or len(caps) <= 1:
        return caps
    window = max(0.05, 0.02 * abs(vout))
    return [cap for cap in caps if abs(cap.v_dc - vout) <= window]


def _bias_from_spec(spec: FrozenSpec) -> float | None:
    if "v_rail" in spec.values_si:
        return spec.values_si["v_rail"]
    return spec.values_si.get("vout")


def _first(ir: CircuitIR, kind: str, field: str) -> float | None:
    for part in ir.parts:
        if part.kind == kind:
            value = getattr(part, field)
            if value is not None:
                return value
    return None


def _heat(ir: CircuitIR, spec: FrozenSpec) -> tuple[float | None, float | None, str | None]:
    if spec.task_class != "ldo":
        return None, None, None
    vin = spec.values_si.get("vin")
    vout = spec.values_si.get("vout")
    i_load = spec.values_si.get("i_load")
    theta = _first(ir, "ic", "theta_ja")
    if vin is None or vout is None or i_load is None or theta is None or vin <= vout:
        return None, None, None
    power = (vin - vout) * i_load
    return power, _AMBIENT_C + power * theta, _STILL_AIR


def _buck_topology(ir: CircuitIR, output_caps: set[str]) -> bool:
    from extrude.checks.walk import _canon_of
    canon = _canon_of(ir.tied_nets)
    grounds = {canon(name) for name in ("GND", "AGND", "PGND", "DGND", "0")}
    nets = {}
    for part in ir.parts:
        pins = [p for p in ir.pins if p.refdes == part.refdes]
        if not pins or any(p.state != "connected" or not p.net or not p.net.strip() for p in pins):
            return False
        nets[part.refdes] = {canon(p.net) for p in pins}
    if any(p.refdes not in nets for p in ir.pins):
        return False
    for cap in ir.parts:
        cn = nets.get(cap.refdes, set())
        if cap.refdes not in output_caps or len(cn) != 2 or not cn & grounds:
            continue
        output = cn - grounds
        for coil in ir.parts:
            ln = nets.get(coil.refdes, set())
            if coil.kind != "inductor" or len(ln) != 2 or not ln & output or ln & grounds:
                continue
            switch = ln - output
            for ic in ir.parts:
                un = nets.get(ic.refdes, set())
                if ic.kind == "ic" and un & switch and un & grounds and len(un - switch - grounds - output) >= 1:
                    return True
    return False
