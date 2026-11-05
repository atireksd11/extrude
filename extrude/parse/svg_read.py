"""Read hole and outline geometry from an SVG export. No layer-name rules."""

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class HoleFact:
    cx: float
    cy: float
    diameter: float


@dataclass
class SvgFacts:
    width_mm: float
    height_mm: float
    holes: list[HoleFact] = field(default_factory=list)
    closed_outline: bool = False


def read_svg(text: str) -> SvgFacts:
    root = ET.fromstring(text)
    view = _viewbox(root)
    width = _length_mm(root.get("width"), view[2] if view else None)
    height = _length_mm(root.get("height"), view[3] if view else None)
    if view:
        width = width or view[2]
        height = height or view[3]
    contours: list[list[tuple[float, float]]] = []
    for element in root.iter():
        tag = element.tag.split("}")[-1]
        if tag == "circle":
            cx = float(element.get("cx", 0))
            cy = float(element.get("cy", 0))
            r = float(element.get("r", 0))
            contours.append(_circle_points(cx, cy, r))
        elif tag == "rect":
            contours.append(_rect_points(element))
        elif tag == "path" and element.get("d"):
            contours.extend(_path_contours(element.get("d", "")))

    if not width or not height:
        width, height = _bounds_size(contours)

    plate_h = height or 1.0
    scaled = []
    for contour in contours:
        scaled.append([(x, plate_h + y) for x, y in contour])

    outline, holes = _classify(scaled, width or 1.0, plate_h)
    return SvgFacts(
        width_mm=width or 0.0,
        height_mm=plate_h,
        holes=holes,
        closed_outline=outline is not None and len(outline) >= 4,
    )


def read_svg_file(path: Path) -> SvgFacts:
    return read_svg(path.read_text(encoding="utf-8"))


def _viewbox(root: ET.Element) -> tuple[float, float, float, float] | None:
    raw = root.get("viewBox")
    if not raw:
        return None
    parts = [float(item) for item in raw.replace(",", " ").split()]
    if len(parts) != 4:
        return None
    return parts[0], parts[1], parts[2], parts[3]


def _length_mm(value: str | None, fallback: float | None) -> float | None:
    if not value:
        return fallback
    match = re.match(r"([0-9.]+)\s*mm", value.strip())
    if match:
        return float(match.group(1))
    try:
        return float(value)
    except ValueError:
        return fallback


def _circle_points(cx: float, cy: float, r: float, segments: int = 24) -> list[tuple[float, float]]:
    return [
        (cx + r * math.cos(2 * math.pi * index / segments), cy + r * math.sin(2 * math.pi * index / segments))
        for index in range(segments)
    ]


def _rect_points(element: ET.Element) -> list[tuple[float, float]]:
    x = float(element.get("x", 0))
    y = float(element.get("y", 0))
    w = float(element.get("width", 0))
    h = float(element.get("height", 0))
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def _path_contours(d: str) -> list[list[tuple[float, float]]]:
    tokens = re.findall(r"[A-Za-z]|-?[0-9]*\.?[0-9]+(?:e[-+]?[0-9]+)?", d)
    contours: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    index = 0
    cmd = ""
    cursor = (0.0, 0.0)

    def number() -> float:
        nonlocal index
        value = float(tokens[index])
        index += 1
        return value

    while index < len(tokens):
        token = tokens[index]
        if token.isalpha():
            if token.lower() == "z" and current:
                contours.append(current)
                current = []
            cmd = token
            index += 1
            continue
        if cmd in {"M", "L"}:
            x, y = number(), number()
            cursor = (x, y)
            current.append(cursor)
        elif cmd == "m":
            dx, dy = number(), number()
            cursor = (cursor[0] + dx, cursor[1] + dy)
            current.append(cursor)
        elif cmd == "l":
            dx, dy = number(), number()
            cursor = (cursor[0] + dx, cursor[1] + dy)
            current.append(cursor)
        else:
            index += 1
    if len(current) >= 3:
        contours.append(current)
    return contours


def _bounds_size(contours: list[list[tuple[float, float]]]) -> tuple[float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for contour in contours:
        for x, y in contour:
            xs.append(x)
            ys.append(y)
    if not xs:
        return 0.0, 0.0
    return max(xs) - min(xs), max(ys) - min(ys)


def _bbox(contour: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in contour]
    ys = [point[1] for point in contour]
    return min(xs), min(ys), max(xs), max(ys)


def _area(contour: list[tuple[float, float]]) -> float:
    if len(contour) < 3:
        return 0.0
    total = 0.0
    for index, (x1, y1) in enumerate(contour):
        x2, y2 = contour[(index + 1) % len(contour)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def _classify(
    contours: list[list[tuple[float, float]]],
    width: float,
    height: float,
) -> tuple[list[tuple[float, float]] | None, list[HoleFact]]:
    if not contours:
        return None, []
    plate_area = width * height
    ranked = sorted(contours, key=_area, reverse=True)
    outline = ranked[0]
    holes: list[HoleFact] = []
    for contour in ranked[1:]:
        min_x, min_y, max_x, max_y = _bbox(contour)
        w = max_x - min_x
        h = max_y - min_y
        area = _area(contour)
        if area <= 0:
            continue
        if area > plate_area * 0.5:
            continue
        if max(w, h) < 0.4:
            continue
        roundness = min(w, h) / max(w, h) if max(w, h) else 0.0
        if roundness < 0.55 and len(contour) < 12:
            continue
        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0
        diameter = (w + h) / 2.0
        holes.append(HoleFact(cx=cx, cy=cy, diameter=diameter))
    return outline, holes
