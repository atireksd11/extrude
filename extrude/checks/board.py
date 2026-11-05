"""A board either matches the schematic or it does not. No simulator."""

import json
import math

BOARD_MM = 20.0
TOUCH_MM = 0.5
PADS = (
    ("C1", "1", "RAIL"),
    ("C1", "2", "GND"),
    ("R1", "1", "SRC"),
    ("R1", "2", "RAIL"),
)


class BoardFault(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def board_prompt(last_fault: str = "") -> str:
    lines = [
        "Place the hold-up on a board. The schematic is frozen.",
        "C1 pin 1 is RAIL. C1 pin 2 is GND. R1 pin 1 is SRC. R1 pin 2 is RAIL.",
        "The board is 20 mm by 20 mm. Every pad must sit inside it, origin at 0,0.",
        "Pads that share a schematic net must be joined by a trace.",
        "A trace must not touch pads of two different nets.",
        "EMIT one JSON object with parts and traces.",
        "Each part has refdes and pads. Each pad has name, net, x_mm, and y_mm.",
        "Each trace has x1_mm, y1_mm, x2_mm, and y2_mm.",
    ]
    if last_fault.strip():
        lines.append("LAST_REJECTED: " + " ".join(last_fault.split()))
    return "\n".join(lines)


def check_board(text: str) -> str | None:
    try:
        raw = _json_object(text)
        pads, traces = _read(raw)
    except BoardFault as exc:
        return exc.detail
    faults = _faults(pads, traces)
    return faults[0] if faults else None


def _faults(pads: list[dict], traces: list[dict]) -> list[str]:
    faults = []
    by_key = {(pad["refdes"], pad["name"]): pad for pad in pads}
    for refdes, name, net in PADS:
        pad = by_key.get((refdes, name))
        if pad is None:
            faults.append(f"{refdes} pin {name} has no pad")
            continue
        if pad["net"] != net:
            faults.append(f"{refdes} pin {name} is on {pad['net']}, the schematic says {net}")
        if not _inside(pad["x"], pad["y"]):
            faults.append(f"{refdes} pin {name} is outside the board")
    groups = _copper(pads, traces)
    schematic = {(refdes, name): net for refdes, name, net in PADS}
    for group in groups:
        nets = []
        for pad in group:
            net = schematic.get((pad["refdes"], pad["name"]), pad["net"])
            if net not in nets:
                nets.append(net)
        if len(nets) > 1:
            faults.append(f"a trace shorts {nets[0]} and {nets[1]}")
    for net in ("RAIL", "GND", "SRC"):
        members = [pad for pad in pads if schematic.get((pad["refdes"], pad["name"])) == net]
        if len(members) < 2:
            continue
        homes = []
        for pad in members:
            home = next((index for index, group in enumerate(groups) if pad in group), None)
            if home not in homes:
                homes.append(home)
        if len(homes) > 1:
            faults.append(f"{net} is not joined on the board")
    return faults


def _copper(pads: list[dict], traces: list[dict]) -> list[list[dict]]:
    parent = list(range(len(pads)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[b] = a

    for i, pad in enumerate(pads):
        for j in range(i + 1, len(pads)):
            other = pads[j]
            if _near(pad["x"], pad["y"], other["x"], other["y"]):
                union(i, j)
    for trace in traces:
        touched = [
            index
            for index, pad in enumerate(pads)
            if _segment_near(pad["x"], pad["y"], trace["x1"], trace["y1"], trace["x2"], trace["y2"])
        ]
        for index in touched[1:]:
            union(touched[0], index)
    buckets: dict[int, list[dict]] = {}
    for index, pad in enumerate(pads):
        buckets.setdefault(find(index), []).append(pad)
    return list(buckets.values())


def _read(raw: object) -> tuple[list[dict], list[dict]]:
    if not isinstance(raw, dict):
        raise BoardFault("the board was not a JSON object")
    parts = raw.get("parts", raw.get("footprints", []))
    if not isinstance(parts, list):
        raise BoardFault("the board has no parts")
    pads = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        refdes = str(part.get("refdes") or part.get("ref") or "").strip().upper()
        pins = part.get("pads", part.get("pins", []))
        if not isinstance(pins, list):
            continue
        for pin in pins:
            if not isinstance(pin, dict):
                continue
            name = str(pin.get("name") or pin.get("pin") or "").strip()
            net = str(pin.get("net") or "").strip().upper()
            x = _mm(pin.get("x_mm", pin.get("x")))
            y = _mm(pin.get("y_mm", pin.get("y")))
            if refdes and name and x is not None and y is not None:
                pads.append({"refdes": refdes, "name": name, "net": net, "x": x, "y": y})
    traces = []
    drawn = raw.get("traces", raw.get("tracks", raw.get("wires", [])))
    if isinstance(drawn, list):
        for item in drawn:
            if not isinstance(item, dict):
                continue
            x1 = _mm(item.get("x1_mm", item.get("x1")))
            y1 = _mm(item.get("y1_mm", item.get("y1")))
            x2 = _mm(item.get("x2_mm", item.get("x2")))
            y2 = _mm(item.get("y2_mm", item.get("y2")))
            if None not in (x1, y1, x2, y2):
                traces.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2})
    return pads, traces


def _inside(x: float, y: float) -> bool:
    return 0 <= x <= BOARD_MM and 0 <= y <= BOARD_MM


def _near(x1: float, y1: float, x2: float, y2: float) -> bool:
    return math.hypot(x2 - x1, y2 - y1) <= TOUCH_MM


def _segment_near(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> bool:
    dx, dy = x2 - x1, y2 - y1
    length = dx * dx + dy * dy
    if length == 0:
        return _near(px, py, x1, y1)
    tee = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length))
    return _near(px, py, x1 + tee * dx, y1 + tee * dy)


def _mm(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = value.strip().lower().replace("mm", "")
    try:
        return float(text)
    except ValueError:
        return None


def _json_object(text: str) -> object:
    body = text.strip()
    if body.startswith("```"):
        lines = [line for line in body.splitlines() if not line.strip().startswith("```")]
        body = "\n".join(lines)
    start = body.find("{")
    end = body.rfind("}")
    if start < 0 or end < start:
        raise BoardFault("the board was not JSON")
    try:
        return json.loads(body[start : end + 1])
    except json.JSONDecodeError as exc:
        raise BoardFault("the board was not JSON") from exc
