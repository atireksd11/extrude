"""Parse mechanical numbers from a sentence. No model."""

import json
import re
from pathlib import Path

_TABLE = json.loads(
    (Path(__file__).resolve().parents[1] / "checks" / "data" / "heat_set_inserts.json").read_text(encoding="utf-8")
)


def parse_mechanical(text: str) -> dict[str, str | int | float]:
    lowered = text.lower()
    out: dict[str, str | int | float] = {"sentence": text.strip()}
    for name in ("petg", "pla", "abs"):
        if name in lowered:
            out["material"] = name.upper()
            break
    for insert in ("M4", "M3", "M2"):
        if insert.lower() in lowered or insert in text:
            out["insert"] = insert
            break
    count = re.search(r"(\d+)\s*(?:x\s*)?(?:m[234]|heat[- ]?set)", lowered)
    if count:
        out["insert_count"] = int(count.group(1))
    elif out.get("insert"):
        out["insert_count"] = 4
    wall = re.search(r"(\d+(?:\.\d+)?)\s*mm\s+(?:joint\s+)?walls?", lowered)
    if wall:
        out["min_wall_mm"] = float(wall.group(1))
    bbox = re.search(r"(\d+(?:\.\d+)?)\s*mm\s+(?:max|bbox|bounding)", lowered)
    if bbox:
        out["bbox_max_mm"] = float(bbox.group(1))
    material = str(out.get("material") or "PETG").upper()
    insert = str(out.get("insert") or "")
    if insert and material:
        row = _TABLE["inserts"].get(insert, {})
        target = row.get(material)
        band = float(_TABLE["band_mm"])
        if target is not None:
            out["insert_min_mm"] = round(float(target) - band, 4)
            out["insert_max_mm"] = round(float(target) + band, 4)
    return out
