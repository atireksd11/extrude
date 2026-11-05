"""Parse 2D plate numbers from a sentence. No model."""

import json
import math
import re
from pathlib import Path

_TABLE = json.loads(
    (Path(__file__).resolve().parents[1] / "checks" / "data" / "clearance_holes.json").read_text(encoding="utf-8")
)


def parse_mechanical_2d(text: str) -> dict[str, str | int | float]:
    lowered = text.lower()
    out: dict[str, str | int | float] = {"sentence": text.strip(), "min_edge_distance_mm": 2.0}
    for name in ("acrylic", "plywood", "aluminum", "aluminium"):
        if name in lowered:
            out["material"] = name.upper() if name != "aluminium" else "ALUMINUM"
            break
    for hole in ("M4", "M3", "M2"):
        if hole.lower() in lowered or hole in text:
            out["hole"] = hole
            break
    count = re.search(r"(\d+)\s*(?:x\s*)?(?:m[234]|holes?)", lowered)
    if count:
        out["hole_count"] = int(count.group(1))
    elif out.get("hole"):
        out["hole_count"] = 4

    rect = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:mm\s*)?[x×]\s*(\d+(?:\.\d+)?)\s*(?:mm)?",
        lowered,
    )
    if rect:
        out["plate_width_mm"] = float(rect.group(1))
        out["plate_height_mm"] = float(rect.group(2))

    diameter = re.search(r"(?:ø|diameter|dia\.?)\s*(\d+(?:\.\d+)?)\s*mm", lowered)
    if diameter:
        out["plate_diameter_mm"] = float(diameter.group(1))
    round_plate = re.search(r"(\d+(?:\.\d+)?)\s*mm\s+(?:diameter|dia\.?|round)", lowered)
    if round_plate and "plate_diameter_mm" not in out:
        out["plate_diameter_mm"] = float(round_plate.group(1))

    pcd = re.search(r"(?:pcd|pitch\s+circle)\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*mm", lowered)
    if pcd:
        out["pcd_mm"] = float(pcd.group(1))
        out["hole_count"] = int(out.get("hole_count") or 6)

    inset = re.search(r"(\d+(?:\.\d+)?)\s*mm\s+(?:inset|margin|from\s+(?:the\s+)?edge)", lowered)
    edge_inset = float(inset.group(1)) if inset else 10.0

    hole = str(out.get("hole") or "")
    if hole:
        target = _TABLE["holes"].get(hole)
        band = float(_TABLE["band_mm"])
        if target is not None:
            out["hole_min_mm"] = round(float(target) - band, 4)
            out["hole_max_mm"] = round(float(target) + band, 4)

    if "plate_width_mm" in out and "plate_height_mm" in out and out.get("hole_count"):
        out["hole_positions_json"] = json.dumps(
            _corner_positions(
                float(out["plate_width_mm"]),
                float(out["plate_height_mm"]),
                int(out["hole_count"]),
                edge_inset,
            )
        )
    elif "plate_diameter_mm" in out and out.get("pcd_mm") and out.get("hole_count"):
        out["hole_positions_json"] = json.dumps(
            _pcd_positions(float(out["plate_diameter_mm"]), float(out["pcd_mm"]), int(out["hole_count"]))
        )
    return out


def _corner_positions(width: float, height: float, count: int, inset: float) -> list[list[float]]:
    corners = [
        [inset, inset],
        [width - inset, inset],
        [inset, height - inset],
        [width - inset, height - inset],
    ]
    return corners[:count]


def _pcd_positions(diameter: float, pcd: float, count: int) -> list[list[float]]:
    cx = cy = diameter / 2.0
    radius = pcd / 2.0
    return [
        [round(cx + radius * math.cos(math.radians(angle)), 4), round(cy + radius * math.sin(math.radians(angle)), 4)]
        for angle in [360 * index / count for index in range(count)]
    ]
