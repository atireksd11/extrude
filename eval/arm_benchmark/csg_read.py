"""Read an evaluated OpenSCAD CSG tree. Variables are already numbers."""

import re

_COLOR = re.compile(r"color\(\[([^\]]+)\]")
_CUBE = re.compile(r"cube\(\s*size\s*=\s*\[([^\]]+)\]", re.IGNORECASE)
_CYL = re.compile(
    r"cylinder\([^)]*?h\s*=\s*([0-9.eE+-]+)[^)]*?r1\s*=\s*([0-9.eE+-]+)[^)]*?r2\s*=\s*([0-9.eE+-]+)",
    re.IGNORECASE,
)
_MATRIX = re.compile(r"multmatrix\(\[\[([^\]]+)\]\s*,\s*\[([^\]]+)\]\s*,\s*\[([^\]]+)\]")


def read_csg(
    text: str,
    *,
    link_span_mm: float = 40.0,
    hull_link_span_mm: float = 50.0,
    finger_length_min_mm: float = 12.0,
    finger_length_max_mm: float = 40.0,
    min_wall_mm: float = 2.0,
) -> dict:
    colors = []
    for match in _COLOR.finditer(text):
        parts = [float(item) for item in match.group(1).split(",")[:3]]
        colors.append(tuple(round(item, 3) for item in parts))
    cubes = []
    for match in _CUBE.finditer(text):
        size = [float(item) for item in match.group(1).split(",")]
        if len(size) == 3:
            cubes.append(sorted(size))
    holes = _subtracted_holes(text)
    return {
        "colors": sorted(set(colors)),
        "cubes": cubes,
        "links": _links(cubes, text, link_span_mm, hull_link_span_mm),
        "fingers": _fingers(cubes, text, finger_length_min_mm, finger_length_max_mm),
        "bends": _bends(text),
        "holes": holes,
        "min_thickness": _link_thickness(cubes, text, hull_link_span_mm, min_wall_mm),
    }


def _links(cubes: list[list[float]], text: str, link_span_mm: float, hull_link_span_mm: float) -> int:
    from_cubes = sum(
        1
        for size in cubes
        if size[2] >= link_span_mm and size[2] >= 2.5 * size[0] and size[0] <= 15
    )
    return from_cubes + _hull_spans(text, hull_link_span_mm)


def _fingers(
    cubes: list[list[float]],
    text: str,
    finger_length_min_mm: float,
    finger_length_max_mm: float,
) -> int:
    from_cubes = sum(
        1 for size in cubes if finger_length_min_mm <= size[2] <= finger_length_max_mm and size[0] <= 8
    )
    return from_cubes + _hull_spans(text, finger_length_min_mm, finger_length_max_mm)


def _hull_spans(text: str, low: float, high: float | None = None) -> int:
    count = 0
    for block in _brace_blocks(text, "hull"):
        xs = []
        for match in _MATRIX.finditer(block):
            row = [float(item) for item in match.group(1).split(",")]
            if len(row) >= 4:
                xs.append(row[3])
        if len(xs) < 2:
            continue
        span = max(xs) - min(xs)
        if high is None and span >= low:
            count += 1
        elif high is not None and low <= span <= high:
            count += 1
    return count


def _bends(text: str) -> int:
    count = 0
    for match in _MATRIX.finditer(text):
        rows = [[float(item) for item in match.group(index).split(",")] for index in (1, 2, 3)]
        if any(len(row) < 3 for row in rows):
            continue
        off = (
            abs(rows[0][1]) + abs(rows[0][2]) + abs(rows[1][0]) + abs(rows[1][2]) + abs(rows[2][0]) + abs(rows[2][1])
        )
        if off > 0.05:
            count += 1
    return count


def _subtracted_holes(text: str) -> list[float]:
    diameters = []
    for block in _brace_blocks(text, "difference"):
        subtracted = _difference_subtracted(block)
        for match in _CYL.finditer(subtracted):
            radius = float(match.group(2))
            if radius <= 8:
                diameters.append(round(radius * 2, 4))
    return diameters


def _difference_subtracted(block: str) -> str:
    parts = block.split("group()", 2)
    if len(parts) > 1:
        return parts[-1]
    body = block.strip()
    if not body.startswith("{") or not body.endswith("}"):
        return ""
    inner = body[1:-1].strip()
    depth = 0
    for index, char in enumerate(inner):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return inner[index + 1 :]
    return ""


def _link_thickness(
    cubes: list[list[float]],
    text: str,
    hull_link_span_mm: float,
    min_wall_mm: float,
) -> float | None:
    found: list[float] = []
    for size in cubes:
        if size[2] >= hull_link_span_mm - 10 and size[2] >= 2.5 * size[0] and size[0] <= 15:
            found.append(size[0])
    for block in _brace_blocks(text, "hull"):
        xs = []
        for match in _MATRIX.finditer(block):
            row = [float(item) for item in match.group(1).split(",")]
            if len(row) >= 4:
                xs.append(row[3])
        if len(xs) >= 2 and max(xs) - min(xs) >= hull_link_span_mm:
            heights = [float(item) for item in re.findall(r"\bh\s*=\s*([0-9.]+)", block)]
            if heights:
                thick = max(heights)
                if thick >= min_wall_mm:
                    found.append(thick)
    if not found:
        return None
    return min(found)


def _brace_blocks(text: str, keyword: str) -> list[str]:
    blocks = []
    token = keyword + "("
    start = 0
    while True:
        found = text.find(token, start)
        if found < 0:
            return blocks
        brace = text.find("{", found)
        if brace < 0:
            return blocks
        depth = 0
        for index in range(brace, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    blocks.append(text[brace : index + 1])
                    start = index + 1
                    break
        else:
            return blocks
