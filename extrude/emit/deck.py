"""Write a hold-up fade. The capacitor value is the shared use-value."""

import re

from extrude.ir.models import CircuitIR
from extrude.physics.models import CapValue, PhysicsValues


def holdup_deck(ir: CircuitIR, physics: PhysicsValues) -> str:
    del ir
    lines = ["* extrude hold-up fade"]
    if not physics.caps:
        lines.append("* no capacitor")
        lines.append(".end")
        return "\n".join(lines) + "\n"
    start = next((cap.v_dc for cap in physics.caps if cap.v_dc > 0), 5.0)
    lines.append(f"V1 nsrc 0 PULSE({_num(start)} 0 1m 1u 1u 5m 10m)")
    lines.append("Rsrc nsrc rail 2")
    for index, cap in enumerate(physics.caps, start=1):
        lines.append(
            "* "
            f"{cap.refdes} nominal={_num(cap.c_nominal)} "
            f"C_use={_num(cap.c_use)} source={cap.curve_source.value} vdc={_num(cap.v_dc)}"
        )
        lines.append(f"{_spice_cap_name(cap, index)} rail 0 {_num(cap.c_use)}")
    lines.append("Rload rail 0 100")
    lines.append(".tran 10u 4m")
    lines.append(".meas tran v_hold MIN v(rail) FROM=1.5m TO=3.5m")
    lines.append(".end")
    return "\n".join(lines) + "\n"


def _num(value: float) -> str:
    return format(value, ".12g")


def _spice_cap_name(cap: CapValue, index: int) -> str:
    if re.fullmatch(r"C[A-Za-z0-9_]+", cap.refdes):
        return cap.refdes
    return f"C{index}"
