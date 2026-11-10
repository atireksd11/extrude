"""Bounded, offline schematic connectivity; no KiCad executable or repo code.

Embedded symbol geometry is authoritative. Crossings connect only at endpoints,
placed pins/labels or explicit junctions. Each sheet has its own local namespace.
"""

from dataclasses import dataclass, field
from collections import defaultdict
from kicad_tools.schema import Schematic
from kicad_tools.sexp import parse_string
from kicad_tools.core.symbol_transform import symbol_to_sheet_offset
from extrude.parse.kicad_pcb import _PARSE_LOCK

MAX_BYTES = 8 * 1024 * 1024
MAX_POINTS = 12000


@dataclass
class Pin:
    reference: str
    number: str
    name: str
    kind: str
    path: str
    net: object


@dataclass
class Part:
    reference: str
    value: str
    symbol: str
    footprint: str
    path: str
    properties: dict
    fitted: bool
    in_bom: bool
    pins: list = field(default_factory=list)


@dataclass
class Graph:
    parts: list = field(default_factory=list)
    nets: dict = field(default_factory=dict)
    names: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)


def build(files: dict[str, bytes]) -> Graph:
    """Build one revision. Inputs must be regular blobs, never followed symlinks."""
    graph = Graph()
    parent, names, points, wires, ports = {}, defaultdict(set), defaultdict(set), [], []

    def point(path, pos):
        key = (path, round(pos[0], 5), round(pos[1], 5))
        parent.setdefault(key, key)
        points[path].add(key)
        return key

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def join(a, b):
        parent[find(a)] = find(b)

    labels = {}
    for path, data in sorted(files.items()):
        if not path.endswith(".kicad_sch"):
            continue
        if len(data) > MAX_BYTES:
            graph.issues.append((path, "Not checked: schematic exceeds 8 MiB."))
            continue
        try:
            with _PARSE_LOCK:
                root = parse_string(data.decode("utf-8-sig"))
                if root.name != "kicad_sch":
                    raise ValueError("Not a native schematic")
                sch = Schematic(root)
                symbols = list(sch.symbols)
                for sym in symbols:
                    lib = sch.get_lib_symbol_resolved(sym.lib_id)
                    if lib is None:
                        graph.issues.append(
                            (
                                path,
                                f"Not checked: {sym.reference} embedded symbol is missing.",
                            )
                        )
                        continue
                    part = Part(
                        sym.reference,
                        sym.value,
                        sym.lib_id,
                        sym.footprint,
                        path,
                        {
                            **{k: v.value for k, v in sym.properties.items()},
                            "_symbol_description": lib.properties.get(
                                "Description", lib.properties.get("ki_description", "")
                            ),
                        },
                        not sym.dnp
                        and sym.value.upper() not in {"DNP", "DNI", "DNF", "NF", "NC"},
                        sym.in_bom,
                    )
                    for pin in [p for p in lib.pins if p.unit in {0, sym.unit}]:
                        dx, dy = symbol_to_sheet_offset(
                            *pin.position, sym.rotation, sym.mirror
                        )
                        key = point(path, (sym.position[0] + dx, sym.position[1] + dy))
                        part.pins.append(
                            Pin(
                                sym.reference, pin.number, pin.name, pin.type, path, key
                            )
                        )
                        if sym.lib_id.startswith("power:") and sym.value != "PWR_FLAG":
                            tag = ("global", sym.value)
                            if tag in labels:
                                join(key, labels[tag])
                            else:
                                labels[tag] = key
                            names[key].add(sym.value)
                    graph.parts.append(part)
                for wire in sch.wires:
                    a, b = point(path, wire.start), point(path, wire.end)
                    join(a, b)
                    wires.append((path, a, b))
                for junction in sch.junctions:
                    point(path, junction.position)
                for group, scope in (
                    (sch.labels, path),
                    (sch.global_labels, "global"),
                    (sch.hierarchical_labels, path),
                ):
                    for label in group:
                        key = point(path, label.position)
                        name = label.text
                        names[key].add(name)
                        tag = (scope, name)
                        if tag in labels:
                            join(key, labels[tag])
                        else:
                            labels[tag] = key
                for sheet in sch.sheets:
                    # Hierarchical port geometry is stored on the sheet node.
                    node = next(
                        (
                            n
                            for n in root.find_children("sheet")
                            if n.find_child("uuid").get_string(0) == sheet.uuid
                        ),
                        None,
                    )
                    if node:
                        for pin in node.find_children("pin"):
                            at = pin.find_child("at")
                            ports.append(
                                (
                                    path,
                                    sheet.filename,
                                    pin.get_string(0),
                                    point(path, (at.get_float(0), at.get_float(1))),
                                )
                            )
        except (
            ValueError,
            TypeError,
            AttributeError,
            IndexError,
            RecursionError,
        ) as exc:
            raise ValueError(
                f"Not checked: unreadable schematic {path}: {type(exc).__name__}"
            ) from exc
    if len(graph.parts) > 4096:
        raise ValueError("Not checked: graph exceeds 4,096 placed symbols.")
    if len(parent) > MAX_POINTS:
        raise ValueError("Not checked: graph exceeds 12,000 connection points.")
    if sum(len(points[path]) for path, _, _ in wires) > 20_000_000:
        raise ValueError(
            "Not checked: connectivity geometry exceeds the bounded work limit."
        )
    # A crossing without a junction contributes no point and remains separate.
    for path, a, b in wires:
        ax, ay = a[1:]
        bx, by = b[1:]
        for p in points[path]:
            x, y = p[1:]
            if (
                min(ax, bx) - 1e-5 <= x <= max(ax, bx) + 1e-5
                and min(ay, by) - 1e-5 <= y <= max(ay, by) + 1e-5
                and abs((x - ax) * (by - ay) - (y - ay) * (bx - ax)) < 1e-5
            ):
                join(a, p)
    from extrude.kicad_snapshot import relative_dependency

    for owner, child, name, key in ports:
        target = relative_dependency(owner, child)
        if (target, name) in labels:
            join(key, labels[target, name])
        else:
            graph.issues.append(
                (owner, f"Not checked: unresolved sheet port {child}:{name}.")
            )
    for key, values in names.items():
        graph.names.setdefault(find(key), set()).update(values)
    for part in graph.parts:
        for pin in part.pins:
            pin.net = find(pin.net)
            graph.nets.setdefault(pin.net, []).append(pin)
    return graph
