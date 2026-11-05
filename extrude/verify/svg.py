"""Compile-first 2D SVG verification. Shared by eval and product."""

import hashlib
import json
import re
from pathlib import Path

from extrude.parse.svg_read import SvgFacts, read_svg, read_svg_file
from extrude.render.openscad import render_2d
from extrude.verify.models import SvgVerifySpec


def checks_for_card_2d(spec) -> list[str]:  # noqa: ANN001
    checks = ["compiles", "closed_outline"]
    if spec.values_si.get("plate_width_mm") or spec.values_si.get("plate_diameter_mm"):
        checks.append("outline_size")
    if spec.labels.get("hole") or spec.values_si.get("hole_count"):
        checks.extend(["hole_count", "hole_diameter"])
    if spec.labels.get("hole_positions_json"):
        checks.append("hole_positions")
    if spec.values_si.get("min_edge_distance_mm"):
        checks.append("min_edge_distance")
    return list(dict.fromkeys(checks))


def checks_for_task(task) -> list[str]:  # noqa: ANN001
    return list(task.checks)


def spec_from_frozen_2d(spec) -> SvgVerifySpec:  # noqa: ANN001
    positions = []
    raw = spec.labels.get("hole_positions_json")
    if raw:
        positions = [tuple(item) for item in json.loads(str(raw))]
    return SvgVerifySpec(
        sentence=spec.evidence.get("sentence", ""),
        plate_width_mm=spec.values_si.get("plate_width_mm"),
        plate_height_mm=spec.values_si.get("plate_height_mm"),
        plate_diameter_mm=spec.values_si.get("plate_diameter_mm"),
        hole=spec.labels.get("hole"),
        hole_count=int(spec.values_si.get("hole_count", 0)),
        hole_min_mm=spec.values_si.get("hole_min_mm"),
        hole_max_mm=spec.values_si.get("hole_max_mm"),
        hole_positions=positions,
        position_tolerance_mm=float(spec.values_si.get("position_tolerance_mm", 0.5)),
        min_edge_distance_mm=float(spec.values_si.get("min_edge_distance_mm", 2.0)),
        checks=checks_for_card_2d(spec),
    )


def score_svg(path: Path, verify: SvgVerifySpec, out_dir: Path | None = None) -> dict:
    folder = out_dir or path.parent
    cache_key = hashlib.sha256(path.read_bytes() + verify.model_dump_json().encode("utf-8")).hexdigest()
    cache_file = folder / ".cache" / f"{cache_key}.json"
    if cache_file.is_file():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    if not path.is_file():
        return _fail("svg file missing", render={})
    try:
        facts = read_svg_file(path)
    except Exception as exc:  # noqa: BLE001
        return _fail(f"svg parse failed: {exc}", render={"svg": str(path)})
    return _score_facts(facts, verify, {"svg": str(path)}, cache_file)


def score_openscad_2d(source: Path, verify: SvgVerifySpec, out_dir: Path | None = None) -> dict:
    folder = out_dir or source.parent / "svg"
    cache_key = hashlib.sha256(source.read_bytes() + verify.model_dump_json().encode("utf-8")).hexdigest()
    cache_file = folder / ".cache" / f"{cache_key}.json"
    if cache_file.is_file():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    rendered = render_2d(source, folder, source.stem)
    if rendered.status != "checked" or not rendered.svg:
        return _fail(rendered.detail or "openscad 2d export failed", render=rendered.model_dump())
    try:
        facts = read_svg_file(Path(rendered.svg))
    except Exception as exc:  # noqa: BLE001
        return _fail(f"svg parse failed: {exc}", render=rendered.model_dump())
    return _score_facts(facts, verify, rendered.model_dump(), cache_file)


def score_openscad_2d_text(code: str, verify: SvgVerifySpec, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    source = out_dir / "candidate.scad"
    source.write_text(code, encoding="utf-8")
    return score_openscad_2d(source, verify, out_dir)


def svg_facts_from_code(code: str, out_dir: Path) -> SvgFacts | None:
    out_dir.mkdir(parents=True, exist_ok=True)
    source = out_dir / "probe.scad"
    source.write_text(code, encoding="utf-8")
    rendered = render_2d(source, out_dir, "probe")
    if rendered.status != "checked" or not rendered.svg:
        return None
    return read_svg_file(Path(rendered.svg))


def _score_facts(facts: SvgFacts, verify: SvgVerifySpec, render: dict, cache_file: Path) -> dict:
    checks: dict[str, bool] = {}
    misses: list[dict] = []
    if verify.enabled("compiles"):
        checks["compiles"] = facts.width_mm > 0 and facts.height_mm > 0
    if verify.enabled("closed_outline"):
        checks["closed_outline"] = facts.closed_outline
        if not facts.closed_outline:
            misses.append(
                {
                    "cause": "model_design",
                    "feature": "outline",
                    "check_id": "closed_outline",
                    "detail": "the exported outline is not a closed contour.",
                }
            )
    if verify.enabled("outline_size"):
        ok, detail = _outline_size(facts, verify)
        checks["outline_size"] = ok
        if not ok and detail:
            misses.append(detail)
    if verify.enabled("hole_count"):
        required = verify.hole_count or 0
        checks["hole_count"] = len(facts.holes) >= required
        if not checks["hole_count"]:
            misses.append(
                {
                    "cause": "model_design",
                    "feature": "holes",
                    "check_id": "hole_count",
                    "measured": len(facts.holes),
                    "limit": required,
                    "detail": f"found {len(facts.holes)} holes; the card requires at least {required}.",
                }
            )
    if verify.enabled("hole_diameter") and verify.hole_min_mm is not None and verify.hole_max_mm is not None:
        ok, measured = _hole_diameters(facts, verify)
        checks["hole_diameter"] = ok
        if not ok:
            misses.append(
                {
                    "cause": "model_design",
                    "feature": "hole_diameter",
                    "check_id": "hole_diameter",
                    "measured_mm": measured,
                    "limit_mm": verify.hole_min_mm,
                    "detail": (
                        f"hole diameter is {measured:g} mm. "
                        f"{verify.hole or 'clearance'} holes must be between "
                        f"{verify.hole_min_mm:g} and {verify.hole_max_mm:g} mm."
                    ),
                }
            )
    if verify.enabled("hole_positions") and verify.hole_positions:
        ok, detail = _hole_positions(facts, verify)
        checks["hole_positions"] = ok
        if not ok and detail:
            misses.append(detail)
    if verify.enabled("min_edge_distance"):
        ok, measured = _min_edge_distance(facts, verify)
        checks["min_edge_distance"] = ok
        if not ok:
            misses.append(
                {
                    "cause": "model_design",
                    "feature": "edge_clearance",
                    "check_id": "min_edge_distance",
                    "measured_mm": measured,
                    "limit_mm": verify.min_edge_distance_mm,
                    "detail": (
                        f"nearest edge clearance is {measured:g} mm; "
                        f"the card requires at least {verify.min_edge_distance_mm:g} mm."
                    ),
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
        "facts": {
            "width_mm": facts.width_mm,
            "height_mm": facts.height_mm,
            "holes": [
                {"cx": hole.cx, "cy": hole.cy, "diameter": hole.diameter} for hole in facts.holes
            ],
        },
        "render": render,
    }
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(result), encoding="utf-8")
    return result


def _fail(detail: str, render: dict) -> dict:
    return {
        "percent": 0.0,
        "passed": 0,
        "out_of": 1,
        "checks": {"compiles": False},
        "cause": "tooling",
        "detail": detail,
        "misses": [],
        "facts": {},
        "render": render,
    }


def _outline_size(facts: SvgFacts, verify: SvgVerifySpec) -> tuple[bool, dict | None]:
    tol = 0.6
    if verify.plate_diameter_mm is not None:
        size = max(facts.width_mm, facts.height_mm)
        ok = abs(size - verify.plate_diameter_mm) <= tol
        if ok:
            return True, None
        return False, {
            "cause": "model_design",
            "feature": "outline",
            "check_id": "outline_size",
            "measured_mm": size,
            "limit_mm": verify.plate_diameter_mm,
            "detail": f"plate diameter is {size:g} mm; the card expects {verify.plate_diameter_mm:g} mm.",
        }
    if verify.plate_width_mm is None or verify.plate_height_mm is None:
        return True, None
    ok = abs(facts.width_mm - verify.plate_width_mm) <= tol and abs(facts.height_mm - verify.plate_height_mm) <= tol
    if ok:
        return True, None
    return False, {
        "cause": "model_design",
        "feature": "outline",
        "check_id": "outline_size",
        "measured_mm": max(abs(facts.width_mm - verify.plate_width_mm), abs(facts.height_mm - verify.plate_height_mm)),
        "limit_mm": tol,
        "detail": (
            f"outline is {facts.width_mm:g}×{facts.height_mm:g} mm; "
            f"the card expects {verify.plate_width_mm:g}×{verify.plate_height_mm:g} mm."
        ),
    }


def _hole_diameters(facts: SvgFacts, verify: SvgVerifySpec) -> tuple[bool, float]:
    if not facts.holes:
        return False, 0.0
    band = [
        hole
        for hole in facts.holes
        if verify.hole_min_mm <= hole.diameter <= verify.hole_max_mm
    ]
    if len(band) >= max(1, verify.hole_count):
        return True, band[0].diameter
    return False, facts.holes[0].diameter


def _hole_positions(facts: SvgFacts, verify: SvgVerifySpec) -> tuple[bool, dict | None]:
    if len(facts.holes) < len(verify.hole_positions):
        return False, {
            "cause": "model_design",
            "feature": "hole_positions",
            "check_id": "hole_positions",
            "detail": "not enough holes were found to match the required positions.",
        }
    tol = verify.position_tolerance_mm
    remaining = list(facts.holes)
    for target_x, target_y in verify.hole_positions:
        best_index = None
        best_dist = None
        for index, hole in enumerate(remaining):
            dist = ((hole.cx - target_x) ** 2 + (hole.cy - target_y) ** 2) ** 0.5
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_index = index
        if best_index is None or best_dist is None or best_dist > tol:
            return False, {
                "cause": "model_design",
                "feature": "hole_positions",
                "check_id": "hole_positions",
                "measured_mm": best_dist or 0.0,
                "limit_mm": tol,
                "detail": (
                    f"no hole sits within {tol:g} mm of ({target_x:g}, {target_y:g}) mm."
                ),
            }
        remaining.pop(best_index)
    return True, None


def _min_edge_distance(facts: SvgFacts, verify: SvgVerifySpec) -> tuple[bool, float]:
    if not facts.holes:
        return False, 0.0
    min_seen = min(
        min(hole.cx, hole.cy, facts.width_mm - hole.cx, facts.height_mm - hole.cy) - hole.diameter / 2.0
        for hole in facts.holes
    )
    return min_seen + 1e-6 >= verify.min_edge_distance_mm, min_seen


def assigned_hole_diameter(text: str) -> float | None:
    for match in re.finditer(r"circle\s*\([^)]*\)", text, re.IGNORECASE):
        call = match.group(0)
        named_d = re.search(r"\bd\s*=\s*([0-9.]+)", call, re.IGNORECASE)
        if named_d:
            return float(named_d.group(1))
        named_r = re.search(r"\br\s*=\s*([0-9.]+)", call, re.IGNORECASE)
        if named_r:
            return float(named_r.group(1)) * 2
    return None
