"""Obvious wiring mistakes. This does not run a simulator and does not judge ripple."""

from collections import defaultdict

from extrude.checks.models import PreflightReport
from extrude.ir.models import CircuitIR, Pin

_DC_KINDS = {"resistor", "inductor", "ferrite", "ideal_voltage_source"}
_GROUND_NAMES = {"GND", "AGND", "PGND", "DGND"}
_DRIVER_NAMES = {
    "TX": "uart_tx",
    "TXD": "uart_tx",
    "MOSI": "spi_mosi",
    "SCK": "spi_sck",
    "SCLK": "spi_sck",
}


def inspect_design(ir: CircuitIR) -> PreflightReport:
    canon = _canon_of(ir.tied_nets)
    kind_of = {part.refdes: part.kind for part in ir.parts}
    blocking: list[str] = []
    warnings: list[str] = []

    for pin in ir.pins:
        if pin.state == "nc":
            continue
        if pin.state == "open" or not pin.net:
            blocking.append(f"hanging_pin:{pin.refdes}.{pin.name}")

    blocking.extend(_source_conflicts(ir, kind_of, canon))
    blocking.extend(_driver_conflicts(ir, canon))

    graph, capacitors = _dc_graph(ir, kind_of, canon)
    grounds = _grounds(ir, canon)
    reachable = {ground: _reachable(graph, ground) for ground in grounds}
    ground_reach = set().union(*reachable.values()) if reachable else set()

    for pin in ir.pins:
        if pin.role != "power" or pin.state != "connected" or not pin.net:
            continue
        node = canon(pin.net)
        if node not in ground_reach:
            blocking.append(f"power_pin_no_dc_path:{pin.refdes}.{pin.name}")
        caps_on_rail = _capacitors_on(node, graph, capacitors)
        if not caps_on_rail:
            blocking.append(f"power_rail_has_no_capacitor:{pin.refdes}.{pin.name}")
        elif not any(side == node for _part, side, _other in caps_on_rail):
            warnings.append(f"capacitor_not_on_power_pin_net:{pin.refdes}.{pin.name}")

    blocking.extend(_ac_bias(capacitors, graph, grounds))
    return PreflightReport(blocking=sorted(set(blocking)), warnings=sorted(set(warnings)))


def _canon_of(groups: list[list[str]]):
    parent: dict[str, str] = {}

    def find(name: str) -> str:
        key = name.strip().upper()
        parent.setdefault(key, key)
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def union(left: str, right: str) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[b] = a

    for group in groups:
        names = [name for name in group if name.strip()]
        for name in names[1:]:
            union(names[0], name)
    return find


def _source_conflicts(ir: CircuitIR, kind_of: dict[str, str], canon) -> list[str]:
    positives: dict[str, list[str]] = defaultdict(list)
    for pin in ir.pins:
        if kind_of.get(pin.refdes) != "ideal_voltage_source":
            continue
        if not pin.net or pin.state != "connected":
            continue
        if pin.role == "positive" or pin.name.upper() in {"+", "POS", "P"}:
            positives[canon(pin.net)].append(pin.refdes)
    found = []
    for net, parts in positives.items():
        unique = sorted(set(parts))
        if len(unique) > 1:
            found.append(f"voltage_sources_on_one_node:{'+'.join(unique)}:{net}")
    return found


def _driver_conflicts(ir: CircuitIR, canon) -> list[str]:
    seen: dict[tuple[str, str], list[str]] = defaultdict(list)
    for pin in ir.pins:
        token = _driver_token(pin)
        if token is None or not pin.net or pin.state != "connected":
            continue
        seen[(token, canon(pin.net))].append(f"{pin.refdes}.{pin.name}")
    found = []
    for (token, net), pins in seen.items():
        if len(pins) > 1:
            found.append(f"drivers_on_one_net:{token}:{net}:{','.join(pins)}")
    return found


def _driver_token(pin: Pin) -> str | None:
    if pin.driver:
        return pin.driver.strip().lower()
    return _DRIVER_NAMES.get(pin.name.upper())


def _dc_graph(ir: CircuitIR, kind_of: dict[str, str], canon):
    graph: dict[str, set[str]] = defaultdict(set)
    capacitors: list[tuple[str, str, str]] = []
    by_part: dict[str, list[Pin]] = defaultdict(list)
    for pin in ir.pins:
        if pin.state == "connected" and pin.net:
            by_part[pin.refdes].append(pin)
    for refdes, pins in by_part.items():
        kind = kind_of.get(refdes, "ic")
        nets = [canon(pin.net) for pin in pins if pin.net]
        if kind == "capacitor" and len(nets) >= 2:
            capacitors.append((refdes, nets[0], nets[1]))
            continue
        if kind not in _DC_KINDS:
            continue
        for left in nets:
            for right in nets:
                if left != right:
                    graph[left].add(right)
                    graph[right].add(left)
    return graph, capacitors


def _grounds(ir: CircuitIR, canon) -> set[str]:
    found = set()
    for pin in ir.pins:
        if pin.role == "ground" and pin.net and pin.state == "connected":
            found.add(canon(pin.net))
        elif pin.net and canon(pin.net) in _GROUND_NAMES:
            found.add(canon(pin.net))
    return found


def _reachable(graph: dict[str, set[str]], start: str) -> set[str]:
    seen = {start}
    stack = [start]
    while stack:
        node = stack.pop()
        for nxt in graph.get(node, ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def _capacitors_on(node: str, graph: dict[str, set[str]], capacitors: list[tuple[str, str, str]]):
    rail = _reachable(graph, node) | {node}
    return [item for item in capacitors if item[1] in rail or item[2] in rail]


def _ac_bias(capacitors, graph, grounds: set[str]) -> list[str]:
    ground_reach: set[str] = set()
    for ground in grounds:
        ground_reach |= _reachable(graph, ground)
    found = []
    for refdes, left, right in capacitors:
        for side in (left, right):
            if side not in ground_reach and side not in grounds:
                found.append(f"ac_side_missing_bias:{refdes}:{side}")
    return found
