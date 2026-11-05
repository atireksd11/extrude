"""Control-pin rules. This does not run a simulator."""

import re
from collections import defaultdict

from extrude.checks.models import PreflightReport
from extrude.ir.models import CircuitIR, Pin

_CONTROL = {"EN", "ENABLE", "RESET", "NRST", "NRESET"}
_RAIL_PREFIX = ("GND", "VCC", "VDD", "VSS", "VIN", "VOUT")


def lint_control_pins(ir: CircuitIR) -> PreflightReport:
    blocking: list[str] = []
    seen: set[str] = set()
    for part in ir.parts:
        if not part.refdes:
            continue
        if part.refdes in seen:
            blocking.append(f"duplicate_refdes:{part.refdes}")
        seen.add(part.refdes)
    kind_of = {part.refdes: part.kind for part in ir.parts}
    for pin in ir.pins:
        if _is_nc(pin.name) and pin.state == "connected" and (pin.net or "").strip():
            blocking.append(f"nc_tied:{pin.refdes}.{pin.name}")
        if kind_of.get(pin.refdes) != "ic" or not _is_control(pin.name):
            continue
        if pin.state != "connected" or not (pin.net and pin.net.strip()):
            blocking.append(f"control_pin_floating:{pin.refdes}.{pin.name}")
            continue
        if not _pulled(ir, pin.net, pin.refdes, kind_of):
            blocking.append(f"control_pin_floating:{pin.refdes}.{pin.name}")
    return PreflightReport(blocking=sorted(set(blocking)))


def _is_control(name: str) -> bool:
    token = _token(name)
    if token in _CONTROL:
        return True
    base = token.rstrip("0123456789")
    return base in _CONTROL and base != token


def _is_nc(name: str) -> bool:
    token = _token(name)
    return token == "NC" or (token.startswith("NC") and token[2:].isdigit())


def _token(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", name.strip().upper())


def _is_rail(name: str) -> bool:
    key = name.strip().upper().lstrip("+")
    if key.startswith(_RAIL_PREFIX):
        return True
    return re.fullmatch(r"\d+V\d*", key) is not None


def _pulled(ir: CircuitIR, net: str, owner: str, kind_of: dict[str, str]) -> bool:
    key = net.strip().upper()
    if _is_rail(key):
        return True
    pins_of: dict[str, list[Pin]] = defaultdict(list)
    for pin in ir.pins:
        if pin.state == "connected" and (pin.net or "").strip():
            pins_of[pin.refdes].append(pin)
    for pin in ir.pins:
        if pin.refdes == owner or pin.state != "connected":
            continue
        if (pin.net or "").strip().upper() != key:
            continue
        kind = kind_of.get(pin.refdes)
        if kind == "ideal_voltage_source":
            return True
        if kind != "resistor":
            continue
        for other in pins_of.get(pin.refdes, []):
            other_net = (other.net or "").strip().upper()
            if other_net and other_net != key and _is_rail(other_net):
                return True
    return False
