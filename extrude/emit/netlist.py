"""KiCad netlist. A board editor can import this file."""

from extrude.ir.models import CircuitIR

_PARTS = {
    "resistor": ("Device", "R", "Resistor_SMD:R_0805_2012Metric"),
    "capacitor": ("Device", "C", "Capacitor_SMD:C_0805_2012Metric"),
    "inductor": ("Device", "L", "Inductor_SMD:L_0805_2012Metric"),
    "led": ("Device", "LED", "LED_SMD:LED_0805_2012Metric"),
    "ic": ("Connector_Generic", "Conn_01x04", "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical"),
    "ferrite": ("Device", "Ferrite_Bead", "Ferrite_SMD:L_0805_2012Metric"),
}


def emit_netlist(ir: CircuitIR) -> str:
    parts = [part for part in ir.parts if part.kind != "ideal_voltage_source"]
    kept = {part.refdes for part in parts}
    lines = [
        '(export (version "E")',
        "  (design",
        '    (source "extrude")',
        '    (date "2026-10-04")',
        '    (tool "Extrude")',
        "  )",
        "  (components",
    ]
    for part in parts:
        lib, symbol, footprint = _PARTS.get(part.kind, _PARTS["ic"])
        lines.append(f'    (comp (ref "{_esc(part.refdes)}")')
        lines.append(f'      (value "{_esc(_value(part))}")')
        lines.append(f'      (footprint "{footprint}")')
        lines.append(f'      (libsource (lib "{lib}") (part "{symbol}") (description ""))')
        lines.append("    )")
    lines.append("  )")
    lines.append("  (nets")
    grouped: dict[str, list[tuple[str, str, str]]] = {}
    counts: dict[str, int] = {}
    for pin in ir.pins:
        if pin.refdes not in kept or pin.state != "connected" or not pin.net:
            continue
        counts[pin.refdes] = counts.get(pin.refdes, 0) + 1
        number = pin.name if pin.name.isdigit() else _number(pin.name, counts[pin.refdes])
        function = "" if pin.name.strip() == number else pin.name.strip()
        grouped.setdefault(pin.net.strip(), []).append((pin.refdes, number, function))
    for code, (name, nodes) in enumerate(sorted(grouped.items()), start=1):
        lines.append(f'    (net (code "{code}") (name "{_esc(name)}")')
        for refdes, number, function in nodes:
            extra = f' (pinfunction "{_esc(function)}")' if function else ""
            lines.append(f'      (node (ref "{_esc(refdes)}") (pin "{number}"){extra})')
        lines.append("    )")
    lines.append("  )")
    lines.append(")")
    return "\n".join(lines) + "\n"


def _value(part) -> str:
    if part.kind == "resistor" and part.resistance:
        ohms = part.resistance
        if ohms >= 1_000_000:
            return f"{ohms / 1_000_000:.4g}M"
        if ohms >= 1000:
            return f"{ohms / 1000:.4g}k"
        return f"{ohms:.4g}"
    if part.kind == "capacitor" and part.capacitance:
        return f"{part.capacitance * 1e6:.4g}uF"
    if part.kind == "inductor" and part.inductance:
        return f"{part.inductance * 1e6:.4g}uH"
    return part.kind


def _number(name: str, index: int) -> str:
    token = name.strip().upper()
    if token in {"A", "+", "1"}:
        return "1"
    if token in {"B", "K", "-", "2"}:
        return "2"
    return str(index)


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')
