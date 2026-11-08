"""Compile-first solid verification. Shared by eval and product."""

import hashlib
import json
import re
import struct
import tempfile
from pathlib import Path

from eval.arm_benchmark.csg_read import read_csg
from extrude.render.openscad import render_source, studio_render_enabled
from extrude.verify.models import SolidVerifySpec


def spec_from_labels(
    sentence: str,
    *,
    material: str | None = None,
    insert: str | None = None,
    insert_count: int = 0,
    insert_min_mm: float | None = None,
    insert_max_mm: float | None = None,
    min_wall_mm: float | None = None,
    bbox_max_mm: float | None = None,
) -> SolidVerifySpec:
    return SolidVerifySpec(
        sentence=sentence,
        material=material,
        insert=insert,
        insert_count=insert_count,
        insert_min_mm=insert_min_mm,
        insert_max_mm=insert_max_mm,
        min_wall_mm=min_wall_mm,
        bbox_max_mm=bbox_max_mm,
    )


def checks_for_card(spec) -> list[str]:  # noqa: ANN001
    checks = ["compiles", "desktop_scale"]
    sentence = spec.evidence.get("sentence", "").lower()
    if any(token in sentence for token in ("link", "links", "arm", "gripper", "joint", "finger")):
        checks.extend(["three_links", "two_fingers", "more_than_one_bend"])
    if spec.labels.get("insert") or spec.values_si.get("insert_count"):
        checks.extend(["base_mounting_holes", "insert_diameter"])
    if spec.values_si.get("min_wall_mm"):
        checks.append("joint_wall")
    if spec.values_si.get("bbox_max_mm"):
        checks.append("bbox_max")
    return list(dict.fromkeys(checks))


def spec_from_frozen(spec, filament: str) -> SolidVerifySpec:  # noqa: ANN001
    material = spec.labels.get("material") or filament.upper()
    insert = spec.labels.get("insert")
    insert_count = int(spec.values_si.get("insert_count", 0))
    min_wall = spec.values_si.get("min_wall_mm")
    return SolidVerifySpec(
        sentence=spec.evidence.get("sentence", ""),
        material=material,
        insert=insert,
        insert_count=insert_count,
        insert_min_mm=spec.values_si.get("insert_min_mm"),
        insert_max_mm=spec.values_si.get("insert_max_mm"),
        min_wall_mm=min_wall,
        bbox_max_mm=spec.values_si.get("bbox_max_mm"),
        checks=checks_for_card(spec),
        min_wall_mm_threshold=float(min_wall or 2.0),
    )


def geometric_facts(code: str, out_dir: Path | None = None) -> dict | None:
    folder = out_dir or Path(tempfile.mkdtemp(prefix="extrude-facts-"))
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / "probe.scad"
    source.write_text(code, encoding="utf-8")
    rendered = render_source(source, folder, "probe")
    if rendered.status != "checked" or not rendered.csg:
        return None
    facts = read_csg(Path(rendered.csg).read_text(encoding="utf-8"))
    facts["color_count"] = len(facts.get("colors", []))
    facts["min_thickness"] = facts.get("min_thickness")
    return facts


def score_openscad(source: Path, verify: SolidVerifySpec, out_dir: Path | None = None) -> dict:
    folder = out_dir or source.parent / "solid"
    cache_key = hashlib.sha256(
        source.read_bytes() + verify.model_dump_json().encode("utf-8")
    ).hexdigest()
    cache_file = folder / ".cache" / f"{cache_key}.json"
    if cache_file.is_file():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    rendered = render_source(source, folder, source.stem + "-solid")
    studio = studio_render_enabled()
    if rendered.status != "checked" or not rendered.csg or (not rendered.stl and not studio):
        return {
            "percent": 0.0,
            "passed": 0,
            "out_of": 1,
            "checks": {"compiles": False},
            "cause": "tooling",
            "detail": rendered.detail,
            "render": rendered.model_dump(),
        }
    source_text = source.read_text(encoding="utf-8")
    facts = read_csg(
        Path(rendered.csg).read_text(encoding="utf-8"),
        link_span_mm=verify.link_span_mm,
        hull_link_span_mm=verify.hull_link_span_mm,
        finger_length_min_mm=verify.finger_length_min_mm,
        finger_length_max_mm=verify.finger_length_max_mm,
        min_wall_mm=verify.min_wall_mm_threshold,
    )
    assigned_wall = _assigned_wall(source_text)
    if assigned_wall is not None and (
        facts.get("min_thickness") is None or verify.enabled("bbox_in_range")
    ):
        facts["min_thickness"] = assigned_wall
    longest = _longest(Path(rendered.stl)) if rendered.stl else _longest_from_facts(facts)
    checks: dict[str, bool] = {}
    if verify.enabled("compiles"):
        checks["compiles"] = True
    if verify.enabled("desktop_scale") and longest is not None:
        checks["desktop_scale"] = 20 <= longest <= 400
    if verify.enabled("three_links"):
        checks["three_links"] = facts["links"] >= 3
    if verify.enabled("two_fingers"):
        checks["two_fingers"] = facts["fingers"] >= 2
    if verify.enabled("more_than_one_bend"):
        checks["more_than_one_bend"] = facts["bends"] >= 2
    if verify.enabled("min_bends"):
        checks["min_bends"] = facts["bends"] >= verify.min_bends
    if verify.require_colors:
        checks["separate_colors"] = len(facts["colors"]) >= 2
    if verify.enabled("base_mounting_holes"):
        required_holes = verify.insert_count if verify.insert_count else 4
        checks["base_mounting_holes"] = len(facts["holes"]) >= required_holes
    misses = []
    if (
        verify.enabled("insert_diameter")
        and verify.insert
        and verify.insert_count
        and verify.insert_min_mm is not None
        and verify.insert_max_mm is not None
    ):
        ok, measured = _inserts(facts["holes"], verify)
        checks["insert_diameter"] = ok
        if not ok:
            misses.append(
                {
                    "cause": "model_design",
                    "feature": "base_insert",
                    "check_id": "insert_diameter",
                    "measured_mm": measured,
                    "limit_mm": verify.insert_min_mm,
                    "detail": (
                        f"base hole diameter is {measured:g} mm. "
                        f"{verify.material} {verify.insert} inserts must be between "
                        f"{verify.insert_min_mm:g} and {verify.insert_max_mm:g} mm."
                    ),
                }
            )
    if verify.enabled("joint_wall") and verify.min_wall_mm is not None:
        thick = facts["min_thickness"]
        checks["joint_wall"] = thick is not None and thick + 1e-6 >= verify.min_wall_mm
        if not checks["joint_wall"]:
            misses.append(
                {
                    "cause": "model_design",
                    "feature": "joint_wall",
                    "check_id": "joint_wall",
                    "measured_mm": thick or 0,
                    "limit_mm": verify.min_wall_mm,
                    "detail": f"joint wall is {thick} mm and the card requires {verify.min_wall_mm:g} mm.",
                }
            )
    if verify.enabled("bbox_in_range") and longest is not None:
        low = verify.bbox_min_mm if verify.bbox_min_mm is not None else 0.0
        high = verify.bbox_max_mm if verify.bbox_max_mm is not None else longest
        checks["bbox_in_range"] = low - 1e-6 <= longest <= high + 1e-6
        if not checks["bbox_in_range"]:
            misses.append(
                {
                    "cause": "model_design",
                    "feature": "bbox",
                    "check_id": "bbox_in_range",
                    "measured_mm": longest,
                    "limit_mm": high,
                    "detail": f"longest side is {longest:g} mm and the card expects {low:g}–{high:g} mm.",
                }
            )
    elif verify.enabled("bbox_max") and verify.bbox_max_mm is not None and longest is not None:
        checks["bbox_max"] = longest <= verify.bbox_max_mm + 1e-6
        if not checks["bbox_max"]:
            misses.append(
                {
                    "cause": "model_design",
                    "feature": "bbox",
                    "check_id": "bbox_max",
                    "measured_mm": longest,
                    "limit_mm": verify.bbox_max_mm,
                    "detail": f"longest side is {longest:g} mm and the card caps it at {verify.bbox_max_mm:g} mm.",
                }
            )
    passed = sum(1 for item in checks.values() if item)
    result = {
        "percent": round(100 * passed / len(checks), 1) if checks else 0.0,
        "passed": passed,
        "out_of": len(checks),
        "checks": checks,
        "cause": "model_design" if misses else "",
        "misses": misses,
        "facts": {key: value for key, value in facts.items() if key != "cubes"},
        "render": {"png": rendered.png, "stl": rendered.stl, "csg": rendered.csg},
    }
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(result), encoding="utf-8")
    return result


def score_openscad_text(code: str, verify: SolidVerifySpec, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    source = out_dir / "candidate.scad"
    source.write_text(code, encoding="utf-8")
    return score_openscad(source, verify, out_dir)


def _inserts(holes: list[float], verify: SolidVerifySpec) -> tuple[bool, float]:
    band = [item for item in holes if verify.insert_min_mm <= item <= verify.insert_max_mm]
    if len(band) >= verify.insert_count:
        return True, band[0]
    if holes:
        return False, holes[0]
    return False, 0.0


def _assigned_wall(text: str) -> float | None:
    match = re.search(r"\bwall\s*=\s*([0-9.]+)", text, re.IGNORECASE)
    if match is None:
        match = re.search(r"\bthickness\s*=\s*([0-9.]+)", text, re.IGNORECASE)
    return float(match.group(1)) if match else None


def _longest_from_facts(facts: dict) -> float | None:
    cubes = facts.get("cubes") or []
    if not cubes:
        return None
    return max(max(size) for size in cubes)


def _longest(path: Path) -> float | None:
    data = path.read_bytes()
    if b"vertex" in data:
        xs, ys, zs = [], [], []
        for line in data.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0] == b"vertex":
                xs.append(float(parts[1]))
                ys.append(float(parts[2]))
                zs.append(float(parts[3]))
        if not xs:
            return None
    else:
        if len(data) < 84:
            return None
        count = struct.unpack_from("<I", data, 80)[0]
        xs, ys, zs = [], [], []
        offset = 84
        for _ in range(count):
            if offset + 50 > len(data):
                break
            vals = struct.unpack_from("<12f", data, offset)
            xs.extend(vals[3::3])
            ys.extend(vals[4::3])
            zs.extend(vals[5::3])
            offset += 50
        if not xs:
            return None
    return max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
