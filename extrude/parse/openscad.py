"""A small OpenSCAD subset: cubes, cylinders, translates, and wall notes."""

import re

from extrude.ir.mechanical import HoleFeature, MechanicalIR, WallFeature

_CUBE = re.compile(
    r"cube\s*\(\s*(?:size\s*=\s*)?\[\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\]",
    re.IGNORECASE,
)
_TRANSLATE = re.compile(
    r"translate\s*\(\s*\[\s*([0-9.+-]+)\s*,\s*([0-9.+-]+)\s*,\s*([0-9.+-]+)\s*\]\s*\)",
    re.IGNORECASE,
)
_CYLINDER = re.compile(r"cylinder\s*\(\s*([^()]*)\)", re.IGNORECASE)
_INSERT = re.compile(r"\b(M2|M3|M4)\b", re.IGNORECASE)
_WALL = re.compile(
    r"//\s*extrude-wall\s+(\S+)\s+([0-9.]+)(?:\s+([0-9.+-]+))?",
    re.IGNORECASE,
)
_ASSIGN = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([0-9.]+)\s*;", re.MULTILINE)
_NAMED = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([A-Za-z0-9_.]+)")
_UNIT = re.compile(r"mm$", re.IGNORECASE)


def cylinder_spans(text: str) -> list[tuple[int, int, float]]:
    names = _bindings(text)
    spans: list[tuple[int, int, float]] = []
    for match in _CYLINDER.finditer(text):
        diameter, _depth = _cylinder_size(match.group(1), names)
        if diameter is None:
            continue
        spans.append((match.start(), match.end(), diameter))
    return spans


def parse_openscad(text: str) -> MechanicalIR:
    warnings: list[str] = []
    holes: list[HoleFeature] = []
    walls: list[WallFeature] = []
    bounds = (0.0, 0.0, 0.0)
    cube = _CUBE.search(text)
    if cube:
        bounds = (float(cube.group(1)), float(cube.group(2)), float(cube.group(3)))
    names = _bindings(text)
    if re.search(r"\$[A-Za-z_]", text):
        warnings.append("parameterized_openscad")

    lines = text.splitlines()
    for line in lines:
        wall = _WALL.search(line)
        if wall:
            normal = float(wall.group(3)) if wall.group(3) else None
            walls.append(WallFeature(name=wall.group(1), thickness_mm=float(wall.group(2)), normal_z=normal))

    for match in _CYLINDER.finditer(text):
        diameter, depth = _cylinder_size(match.group(1), names)
        if diameter is None:
            warnings.append(f"unparsed_cylinder:{_line_number(text, match.start())}")
            continue
        holes.append(
            HoleFeature(
                name=f"hole_{len(holes) + 1}",
                diameter_mm=diameter,
                depth_mm=depth,
                position_mm=_translate_for(text, match.start()),
                intended_insert=_insert_for(text, match.start()),
            )
        )
    return MechanicalIR(holes=holes, walls=walls, bounds_mm=bounds, source="openscad", warnings=warnings)


def _bindings(text: str) -> dict[str, float]:
    names: dict[str, float] = {}
    for match in re.finditer(r"^\s*([A-Za-z_]\w*)\s*=\s*([^;]+);", text, re.MULTILINE):
        value = _eval_expr(match.group(2).strip(), names)
        if value is not None:
            names[match.group(1)] = value
    return names


def _eval_expr(expr: str, names: dict[str, float]) -> float | None:
    tokens = re.findall(r"[A-Za-z_]\w*|\d+(?:\.\d+)?|[()+\-*/]", expr.replace(" ", ""))
    if not tokens:
        return None
    position = 0

    def parse_sum() -> float | None:
        nonlocal position
        left = parse_product()
        if left is None:
            return None
        while position < len(tokens) and tokens[position] in {"+", "-"}:
            op = tokens[position]
            position += 1
            right = parse_product()
            if right is None:
                return None
            left = left + right if op == "+" else left - right
        return left

    def parse_product() -> float | None:
        nonlocal position
        left = parse_unary()
        if left is None:
            return None
        while position < len(tokens) and tokens[position] in {"*", "/"}:
            op = tokens[position]
            position += 1
            right = parse_unary()
            if right is None or (op == "/" and right == 0):
                return None
            left = left * right if op == "*" else left / right
        return left

    def parse_unary() -> float | None:
        nonlocal position
        if position < len(tokens) and tokens[position] in {"+", "-"}:
            op = tokens[position]
            position += 1
            value = parse_unary()
            if value is None:
                return None
            return value if op == "+" else -value
        return parse_atom()

    def parse_atom() -> float | None:
        nonlocal position
        if position >= len(tokens):
            return None
        token = tokens[position]
        if token == "(":
            position += 1
            value = parse_sum()
            if position >= len(tokens) or tokens[position] != ")":
                return None
            position += 1
            return value
        position += 1
        if token in names:
            return names[token]
        try:
            return float(token)
        except ValueError:
            return None

    value = parse_sum()
    if value is None or position != len(tokens):
        return None
    return value


def _cylinder_size(args: str, names: dict[str, float]) -> tuple[float | None, float | None]:
    named: dict[str, float] = {}
    for key, raw in re.findall(r"([A-Za-z_]\w*)\s*=\s*([^,]+)", args):
        value = _eval_expr(_UNIT.sub("", raw.strip()), names)
        if value is not None:
            named[key.lower()] = value
    if not named:
        for key, raw in _NAMED.findall(args):
            value = _number(raw, names)
            if value is not None:
                named[key.lower()] = value
    depth = named.get("h")
    if "d" in named:
        return named["d"], depth
    if "r" in named:
        return named["r"] * 2, depth
    positional = [float(item) for item in re.findall(r"[0-9.]+", _NAMED.sub(" ", args))]
    if len(positional) >= 2:
        return positional[1] * 2, positional[0]
    return None, depth


def _number(raw: str, names: dict[str, float]) -> float | None:
    token = _UNIT.sub("", raw.strip())
    if token in names:
        return names[token]
    try:
        return float(token)
    except ValueError:
        return None


def _translate_for(text: str, start: int) -> tuple[float, float, float]:
    line_start = text.rfind("\n", 0, start) + 1
    own = text[line_start:start]
    found = list(_TRANSLATE.finditer(own))
    if found:
        return _point(found[-1])
    previous_end = text.rfind("\n", 0, line_start - 1)
    previous = text[previous_end + 1 : line_start - 1] if line_start else ""
    if "cylinder" in previous.lower():
        return (0.0, 0.0, 0.0)
    found = list(_TRANSLATE.finditer(previous))
    if found:
        return _point(found[-1])
    return (0.0, 0.0, 0.0)


def _insert_for(text: str, start: int) -> str | None:
    line_end = text.find("\n", start)
    if line_end < 0:
        line_end = len(text)
    line_start = text.rfind("\n", 0, start) + 1
    own = _INSERT.findall(text[line_start:line_end])
    if own:
        return own[-1].upper()
    previous_end = text.rfind("\n", 0, line_start - 1)
    previous = text[previous_end + 1 : line_start - 1] if line_start else ""
    if "cylinder" in previous.lower():
        return None
    found = _INSERT.findall(previous)
    if found:
        return found[-1].upper()
    return None


def _point(match: re.Match[str]) -> tuple[float, float, float]:
    return (float(match.group(1)), float(match.group(2)), float(match.group(3)))


def _line_number(text: str, start: int) -> int:
    return text[:start].count("\n") + 1
