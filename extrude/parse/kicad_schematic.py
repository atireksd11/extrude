"""Placed-symbol facts, not an electrical connectivity solver."""

from dataclasses import dataclass

from kicad_tools.sexp import ParseError, parse_string

from extrude.parse.kicad_pcb import _PARSE_LOCK, _field, _pairs, _rows, _string_field

MAX_SCHEMATIC_BYTES = 8 * 1024 * 1024


class SchematicParseError(ValueError):
    pass


@dataclass(frozen=True)
class Symbol:
    uuid: str
    reference: str
    value: str
    footprint: str
    unit: int


@dataclass(frozen=True)
class Schematic:
    version: int
    symbols: tuple[Symbol, ...]
    sheets: tuple[tuple[str, str], ...]  # child sheet UUID, relative filename


def parse_schematic(data: bytes) -> Schematic:
    if len(data) > MAX_SCHEMATIC_BYTES:
        raise SchematicParseError("Schematic exceeds the 8 MiB analysis limit.")
    try:
        with _PARSE_LOCK:
            root = parse_string(data.decode("utf-8-sig"))
        if root.name != "kicad_sch":
            raise ValueError()
        fmt = _field(root, "version")
        if len(fmt) != 1 or not isinstance(fmt[0], int):
            raise ValueError()
        symbols, sheets = [], []
        # Only top-level placed symbols: never the definitions in lib_symbols.
        for node in _rows(root, "symbol"):
            props = {row.values[0]: row.values[1] for row in _rows(node, "property")
                     if len(row.values) >= 2}
            uid = _string_field(node, "uuid")
            if not uid or not isinstance(props.get("Reference"), str):
                raise ValueError()
            unit = _field(node, "unit")
            symbols.append(Symbol(uid, props["Reference"], str(props.get("Value", "")),
                                  str(props.get("Footprint", "")), int(unit[0]) if unit else 1))
        for node in _rows(root, "sheet"):
            props = {row.values[0]: row.values[1] for row in _rows(node, "property")
                     if len(row.values) >= 2}
            filename = props.get("Sheetfile", props.get("Sheet file"))
            uid = _string_field(node, "uuid")
            if not uid or not isinstance(filename, str) or not filename:
                raise ValueError()
            sheets.append((uid, filename))
        return Schematic(fmt[0], tuple(symbols), tuple(sheets))
    except (ParseError, ValueError, TypeError, IndexError, RecursionError) as exc:
        raise SchematicParseError("Could not read native KiCad schematic fields.") from exc


def compare_schematics(before: Schematic | None, after: Schematic | None) -> list[dict]:
    result = []
    # A multi-unit part has multiple symbols; UUID is the primary identity. The
    # fallback only pairs references unique within the individual sheet.
    for old, new in _pairs(before.symbols if before else (), after.symbols if after else ()):
        item = new or old
        common = {"reference": item.reference, "uuid": item.uuid, "unit": item.unit}
        if old is None or new is None:
            value = lambda symbol: ({"reference": symbol.reference, "value": symbol.value,
                                      "footprint": symbol.footprint, "unit": symbol.unit} if symbol else None)
            result.append({**common, "kind": "symbol_added" if new else "symbol_removed",
                           "before": value(old), "after": value(new)})
        else:
            for field in ("reference", "value", "footprint", "unit"):
                if getattr(old, field) != getattr(new, field):
                    result.append({**common, "kind": field + "_changed",
                                   "before": getattr(old, field), "after": getattr(new, field)})
    return result
