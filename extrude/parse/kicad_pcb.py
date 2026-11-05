"""Read the KiCad fields used by the Atlas PCB comparison."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from math import isfinite
from threading import Lock

from kicad_tools.sexp import ParseError, SExp, parse_string

MAX_BOARD_BYTES = 8 * 1024 * 1024
_PARSE_LOCK = Lock()


class BoardParseError(ValueError):
    """The input does not provide reliable PCB comparison evidence."""


@dataclass(frozen=True)
class Footprint:
    reference: str | None
    uuid: str | None
    library: str
    position: tuple[float, float]
    rotation: float
    layer: str
    pads: dict[str, tuple[str | None, ...]]


@dataclass(frozen=True)
class Board:
    version: int
    footprints: tuple[Footprint, ...]


def _rows(node: SExp, name: str):
    return (item for item in node.children if item.name == name)


def _field(node: SExp, name: str) -> list:
    row = next(_rows(node, name), None)
    return row.values if row is not None else []


def _atom(value: object) -> str:
    if isinstance(value, (str, int, float)):
        return str(value)
    raise BoardParseError("A PCB field is malformed.")


def _string_field(node: SExp, key: str) -> str | None:
    values = _field(node, key)
    return _atom(values[0]) if values else None


def _net(pad: SExp, nets: dict[int, str]) -> str | None:
    rows = list(_rows(pad, "net"))
    if not rows:
        return None
    values = rows[0].values
    if len(rows) != 1 or len(values) not in {1, 2}:
        raise BoardParseError("A pad's net is malformed.")
    token = values[0]
    if not isinstance(token, int):
        if len(values) != 1:
            raise BoardParseError("A pad's net is malformed.")
        return _atom(token) or None
    if token == 0:
        if len(values) == 2 and values[1] != "":
            raise BoardParseError("A pad refers to a missing or inconsistent net.")
        return None
    name = _atom(values[1]) if len(values) > 1 else nets.get(token)
    if not name or (token in nets and nets[token] != name):
        raise BoardParseError("A pad refers to a missing or inconsistent net.")
    return name


def _reference(node: SExp) -> str | None:
    for row in _rows(node, "property"):
        values = row.values
        if len(values) >= 2 and values[0] == "Reference":
            return _atom(values[1]) or None
    for row in _rows(node, "fp_text"):
        values = row.values
        if len(values) >= 2 and values[0] == "reference":
            return _atom(values[1]) or None
    return None


def _footprint(node: SExp, nets: dict[int, str]) -> Footprint:
    coords = _field(node, "at")
    layer = _string_field(node, "layer")
    library = node.get_first_atom()
    if len(coords) not in {2, 3} or not layer or library is None:
        raise BoardParseError("A footprint is missing its placement or layer.")
    try:
        x, y, rotation = (float(_atom(value)) for value in [*coords, 0][:3])
    except (ValueError, OverflowError) as exc:
        raise BoardParseError("A footprint has invalid placement coordinates.") from exc
    if not all(map(isfinite, (x, y, rotation))):
        raise BoardParseError("A footprint has invalid placement coordinates.")
    pads = defaultdict(list)
    for pad in _rows(node, "pad"):
        number = pad.get_value(0)
        if number is None:
            raise BoardParseError("A footprint contains a pad without a number field.")
        number = _atom(number)
        if number:
            pads[number].append(_net(pad, nets))
    return Footprint(
        _reference(node), _string_field(node, "uuid") or _string_field(node, "tstamp"),
        _atom(library), (x, y), rotation % 360, layer,
        {number: tuple(sorted(values, key=lambda value: (value is not None, value or "")))
         for number, values in pads.items()},
    )


def parse_board(data: bytes) -> Board:
    if len(data) > MAX_BOARD_BYTES:
        raise BoardParseError("Board exceeds the 8 MiB comparison limit.")
    try:
        # The upstream parser temporarily pauses process-wide garbage collection.
        with _PARSE_LOCK:
            root = parse_string(data.decode("utf-8-sig"))
    except (ParseError, ValueError, RecursionError) as exc:
        raise BoardParseError("Could not read the KiCad board syntax.") from exc
    if root.name != "kicad_pcb":
        raise BoardParseError("Expected a native KiCad PCB file.")
    version = _field(root, "version")
    if len(version) != 1 or not isinstance(version[0], int):
        raise BoardParseError("The board is missing its KiCad format version.")
    nets = {}
    for row in _rows(root, "net"):
        values = row.values
        if len(values) != 2 or not isinstance(values[0], int):
            raise BoardParseError("The board contains a malformed net definition.")
        code, value = values
        name = _atom(value)
        if code in nets and nets[code] != name:
            raise BoardParseError("The board contains conflicting net definitions.")
        nets[code] = name
    footprints = tuple(_footprint(row, nets) for row in root.children if row.name in {"footprint", "module"})
    return Board(version[0], footprints)


def _pairs(before: tuple[Footprint, ...], after: tuple[Footprint, ...]):
    left = dict(enumerate(before))
    right = dict(enumerate(after))
    for key in ("uuid", "reference"):
        left_counts = Counter(getattr(item, key) for item in left.values())
        right_counts = Counter(getattr(item, key) for item in right.values())
        by_key = {getattr(item, key): index for index, item in right.items()
                  if right_counts[getattr(item, key)] == 1}
        for index, item in list(left.items()):
            value = getattr(item, key)
            if value and left_counts[value] == 1 and value in by_key:
                yield left.pop(index), right.pop(by_key[value])
    yield from ((item, None) for item in left.values())
    yield from ((None, item) for item in right.values())


def _identity(item: Footprint) -> str:
    return item.reference or item.uuid or item.library


def _placement(item: Footprint) -> dict:
    return {"x_mm": item.position[0], "y_mm": item.position[1], "rotation_deg": item.rotation,
            "layer": item.layer, "library": item.library}


def compare_boards(before: Board | None, after: Board | None) -> list[dict]:
    rows = []
    for old, new in _pairs(before.footprints if before else (), after.footprints if after else ()):
        if old is None or new is None:
            item = new if new is not None else old
            rows.append({"kind": "footprint_added" if new else "footprint_removed", "reference": _identity(item),
                         "before": _placement(old) if old else None, "after": _placement(new) if new else None})
            continue
        reference = _identity(new)
        for field in ("reference", "position", "rotation", "layer", "library"):
            a, b = getattr(old, field), getattr(new, field)
            if a != b:
                rows.append({"kind": field + "_changed", "reference": reference, "before": a, "after": b})
        for pad in sorted(old.pads.keys() | new.pads.keys()):
            a, b = old.pads.get(pad), new.pads.get(pad)
            if a == b:
                continue
            if a is None or b is None:
                kind = "pad_added" if a is None else "pad_removed"
            else:
                kind = "pad_net_changed" if len(a) == len(b) == 1 else "pad_assignments_changed"
                if len(a) == len(b) == 1 and a[0] is not None and b[0] is None:
                    kind = "pad_disconnected"
            rows.append({"kind": kind, "reference": reference, "pad": pad, "before": a, "after": b})
    return rows
