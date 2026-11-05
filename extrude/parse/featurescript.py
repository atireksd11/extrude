"""A FeatureScript subset: circles, holes, and wall notes."""

import re

from extrude.ir.mechanical import HoleFeature, MechanicalIR, WallFeature

_MM = re.compile(r"([0-9.]+)\s*\*\s*millimeter", re.IGNORECASE)
_HOLE = re.compile(r"\bhole\s*\(\s*([^)]*)\)", re.IGNORECASE)
_CIRCLE = re.compile(r"skCircle\s*\(\s*([^)]*)\)", re.IGNORECASE)
_INSERT = re.compile(r"\b(M2|M3|M4)\b")
_WALL = re.compile(
    r"//\s*extrude-wall\s+(\S+)\s+([0-9.]+)(?:\s+([0-9.+-]+))?",
    re.IGNORECASE,
)
_UNKNOWN = re.compile(r"\b(opFillet|opShell|opDraft)\s*\(")


_ASSIGN = re.compile(
    r"(?:const|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([0-9.]+)\s*\*\s*millimeter",
    re.IGNORECASE,
)


def parse_featurescript(text: str) -> MechanicalIR:
    warnings = [f"unsupported:{name}" for name in sorted(set(_UNKNOWN.findall(text)))]
    names = {match.group(1): float(match.group(2)) for match in _ASSIGN.finditer(text)}
    holes: list[HoleFeature] = []
    walls: list[WallFeature] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        wall = _WALL.search(line)
        if wall:
            normal = float(wall.group(3)) if wall.group(3) else None
            walls.append(WallFeature(name=wall.group(1), thickness_mm=float(wall.group(2)), normal_z=normal))
        for pattern, radius_literal in ((_HOLE, False), (_CIRCLE, True)):
            match = pattern.search(line)
            if match is None:
                continue
            diameter = _diameter(match.group(1), names, radius_literal=radius_literal)
            if diameter is None:
                warnings.append(f"unparsed_feature:{index + 1}")
                continue
            own = _INSERT.findall(line)
            previous = lines[index - 1] if index else ""
            found = own or ([] if "skCircle" in previous or "hole(" in previous.lower() else _INSERT.findall(previous))
            holes.append(
                HoleFeature(
                    name=f"hole_{len(holes) + 1}",
                    diameter_mm=diameter,
                    intended_insert=found[-1].upper() if found else None,
                )
            )
    return MechanicalIR(holes=holes, walls=walls, source="featurescript", warnings=warnings)


def _diameter(args: str, names: dict[str, float], *, radius_literal: bool) -> float | None:
    chosen = None
    for ident in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", args):
        if ident in names and _size_name(ident):
            chosen = ident
    if chosen is not None:
        value = names[chosen]
        if _radius_name(chosen):
            return value * 2
        return value
    labeled = re.search(r"(?:diameter|d)\s*[,:=]\s*([0-9.]+)", args, re.IGNORECASE)
    if labeled:
        return float(labeled.group(1))
    millimeters = _MM.findall(args)
    if millimeters:
        value = float(millimeters[-1])
        return value * 2 if radius_literal else value
    bare = re.findall(r"([0-9.]+)", args)
    if bare:
        value = float(bare[-1])
        return value * 2 if radius_literal else value
    return None


def _radius_name(name: str) -> bool:
    token = name.lower()
    return token in {"r", "radius"} or "radius" in token


def _size_name(name: str) -> bool:
    token = name.lower()
    return _radius_name(name) or "dia" in token or token in {"d", "diameter"}
