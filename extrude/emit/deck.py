"""Write a hold-up fade. The capacitor value is the shared use-value."""

import re

from extrude.ir.models import CircuitIR
from extrude.physics.models import CapValue, PhysicsValues

_GROUND_NAMES = {"GND", "AGND", "PGND", "DGND"}


def holdup_deck(ir: CircuitIR, physics: PhysicsValues) -> str:
    lines = ["* extrude hold-up fade"]
    if not physics.caps:
        lines.append("* no capacitor")
        lines.append(".end")
        return "\n".join(lines) + "\n"
    placed = _placed_caps(ir, physics)
    if not placed:
        return _canned(physics)
    sense = next((nodes[0] for _cap, nodes in placed if nodes[0] != "0"), None)
    if sense is None:
        sense = next((nodes[1] for _cap, nodes in placed if nodes[1] != "0"), "0")
    start = next((cap.v_dc for cap, _nodes in placed if cap.v_dc > 0), 5.0)
    lines.append(f"V1 nsrc 0 PULSE({_num(start)} 0 1m 1u 1u 5m 10m)")
    lines.append(f"Rsrc nsrc {sense} 2")
    for index, (cap, nodes) in enumerate(placed, start=1):
        lines.append(_cap_comment(cap))
        lines.append(f"{_spice_cap_name(cap, index)} {nodes[0]} {nodes[1]} {_num(cap.c_use)}")
    lines.append(f"Rload {sense} 0 100")
    lines.append(".tran 10u 4m")
    lines.append(f".meas tran v_hold MIN v({sense}) FROM=1.5m TO=3.5m")
    lines.append(".end")
    return "\n".join(lines) + "\n"


def _canned(physics: PhysicsValues) -> str:
    lines = ["* extrude hold-up fade"]
    start = next((cap.v_dc for cap in physics.caps if cap.v_dc > 0), 5.0)
    lines.append(f"V1 nsrc 0 PULSE({_num(start)} 0 1m 1u 1u 5m 10m)")
    lines.append("Rsrc nsrc rail 2")
    for index, cap in enumerate(physics.caps, start=1):
        lines.append(_cap_comment(cap))
        lines.append(f"{_spice_cap_name(cap, index)} rail 0 {_num(cap.c_use)}")
    lines.append("Rload rail 0 100")
    lines.append(".tran 10u 4m")
    lines.append(".meas tran v_hold MIN v(rail) FROM=1.5m TO=3.5m")
    lines.append(".end")
    return "\n".join(lines) + "\n"


def _placed_caps(ir: CircuitIR, physics: PhysicsValues) -> list[tuple[CapValue, tuple[str, str]]]:
    grounds = _ground_nets(ir)
    placed = []
    for cap in physics.caps:
        nets = [
            pin.net.strip()
            for pin in ir.pins
            if pin.refdes == cap.refdes and pin.state == "connected" and pin.net and pin.net.strip()
        ]
        if len(nets) < 2:
            continue
        placed.append((cap, (_node(nets[0], grounds), _node(nets[1], grounds))))
    return placed


def _ground_nets(ir: CircuitIR) -> set[str]:
    found = set()
    for group in ir.tied_nets:
        if any(name.strip().upper() in _GROUND_NAMES for name in group):
            found.update(name.strip() for name in group if name.strip())
    return found


def _node(net: str, grounds: set[str]) -> str:
    if net.strip().upper() in _GROUND_NAMES or net.strip() in grounds:
        return "0"
    token = re.sub(r"[^A-Za-z0-9_]", "_", net.strip())
    if not token or token[0].isdigit():
        token = f"N_{token}"
    return token


def _cap_comment(cap: CapValue) -> str:
    return (
        "* "
        f"{cap.refdes} nominal={_num(cap.c_nominal)} "
        f"C_use={_num(cap.c_use)} source={cap.curve_source.value} vdc={_num(cap.v_dc)}"
    )


def _num(value: float) -> str:
    return format(value, ".12g")


def _spice_cap_name(cap: CapValue, index: int) -> str:
    if re.fullmatch(r"C[A-Za-z0-9_]+", cap.refdes):
        return cap.refdes
    return f"C{index}"
