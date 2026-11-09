"""KiCad netlist text back into a circuit file."""

import re

from extrude.ir.models import CircuitIR, Part, Pin

_FARAD = re.compile(r"([0-9]*\.?[0-9]+)\s*(p|n|u|µ|μ|m)?\s*f\b", re.IGNORECASE)
_VOLT = re.compile(r"([0-9]*\.?[0-9]+)\s*v?\b", re.IGNORECASE)
_FARAD_SCALE = {"": 1.0, "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6, "m": 1e-3}

_KINDS = {
    "R": "resistor",
    "RESISTOR": "resistor",
    "C": "capacitor",
    "CAPACITOR": "capacitor",
    "L": "inductor",
    "INDUCTOR": "inductor",
    "LED": "led",
    "FERRITE_BEAD": "ferrite",
    "FERRITE": "ferrite",
}
_REFDES = (
    (re.compile(r"^R\d+$", re.IGNORECASE), "resistor"),
    (re.compile(r"^C\d+$", re.IGNORECASE), "capacitor"),
    (re.compile(r"^L\d+$", re.IGNORECASE), "inductor"),
    (re.compile(r"^(LED|D)\d+$", re.IGNORECASE), "led"),
    (re.compile(r"^FB\d+$", re.IGNORECASE), "ferrite"),
)


def parse_kicad_netlist(text: str) -> CircuitIR:
    tree = _parse(_tokens(text))[0]
    export = _child(tree, "export") or tree
    parts: list[Part] = []
    c_min = None
    for comp in _children(_child(export, "components"), "comp"):
        refdes = (_field(comp, "ref") or "").strip()
        if not refdes:
            continue
        symbol = ""
        source = _child(comp, "libsource")
        if source is not None:
            symbol = (_field(source, "part") or "").upper().split(":")[-1]
        kind = _kind(symbol, refdes)
        fields = _named_fields(comp)
        part = Part(refdes=refdes, kind=kind)
        if kind == "capacitor":
            part.capacitance = _farads(_field(comp, "value") or "")
            part.dielectric = fields.get("dielectric")
            part.manufacturer = fields.get("manufacturer")
            part.series = fields.get("series")
            part.case = fields.get("case")
            part.voltage_rating = _volts(fields.get("voltagerating") or fields.get("voltage") or "")
            part.bias_v = _volts(fields.get("biasv") or fields.get("bias") or "")
            required = _farads(fields.get("cmin") or "")
            if required is not None:
                c_min = required
        parts.append(part)
    pins: list[Pin] = []
    nets: list[str] = []
    for net in _children(_child(export, "nets"), "net"):
        name = _field(net, "name") or ""
        if name:
            nets.append(name)
        for node in _children(net, "node"):
            number = _field(node, "pin") or ""
            function = (_field(node, "pinfunction") or "").strip()
            pins.append(
                Pin(
                    refdes=_field(node, "ref") or "",
                    name=function or number,
                    net=name,
                    state="connected",
                )
            )
    if not parts or not pins or not nets:
        raise ValueError("Empty netlist is unverified; no electrical connectivity was checked.")
    return CircuitIR(
        parts=parts,
        pins=pins,
        nets=nets,
        components=[part.refdes for part in parts],
        c_min=c_min,
    )


def _named_fields(comp: list) -> dict[str, str]:
    box = _child(comp, "fields") or comp
    found: dict[str, str] = {}
    for field in _children(box, "field"):
        name = (_field(field, "name") or "").strip().lower()
        value = next((item for item in field[1:] if isinstance(item, str)), None)
        if name and value is not None:
            found[name] = value
    return found


def _farads(text: str) -> float | None:
    match = _FARAD.search(text or "")
    if match is None:
        return None
    scale = _FARAD_SCALE[(match.group(2) or "").lower()]
    return float(match.group(1)) * scale


def _volts(text: str) -> float | None:
    match = _VOLT.search(text or "")
    if match is None:
        return None
    return float(match.group(1))


def _kind(symbol: str, refdes: str) -> str:
    if symbol in _KINDS:
        return _KINDS[symbol]
    if symbol.startswith("R_"):
        return "resistor"
    if symbol.startswith("C_"):
        return "capacitor"
    if symbol.startswith("L_") and not symbol.startswith("LED"):
        return "inductor"
    for pattern, kind in _REFDES:
        if pattern.match(refdes):
            return kind
    return "ic"


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char in "()":
            tokens.append(char)
            index += 1
            continue
        if char == '"':
            index += 1
            chunk = []
            while index < len(text) and text[index] != '"':
                chunk.append(text[index])
                index += 1
            index += 1
            tokens.append("".join(chunk))
            continue
        start = index
        while index < len(text) and not text[index].isspace() and text[index] not in "()":
            index += 1
        tokens.append(text[start:index])
    return tokens


def _parse(tokens: list[str]) -> tuple[list, int]:
    items: list = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == ")":
            return items, index + 1
        if token == "(":
            child, consumed = _parse(tokens[index + 1 :])
            items.append(child)
            index += consumed + 1
            continue
        items.append(token)
        index += 1
    return items, index


def _child(node: list | None, name: str) -> list | None:
    if not node:
        return None
    for item in node:
        if isinstance(item, list) and item and item[0] == name:
            return item
    return None


def _children(node: list | None, name: str) -> list[list]:
    if not node:
        return []
    return [item for item in node if isinstance(item, list) and item and item[0] == name]


def _field(node: list, name: str) -> str | None:
    child = _child(node, name)
    if child is None or len(child) < 2:
        return None
    return str(child[1])
