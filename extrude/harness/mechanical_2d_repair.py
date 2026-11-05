"""Surgical 2D OpenSCAD repair shared by product and eval."""

import re
from pathlib import Path

from extrude.verify.models import SvgVerifySpec
from extrude.verify.svg import score_openscad_2d_text, svg_facts_from_code

_REPAIR_MAX = 2


def repair_code_2d(
    code: str,
    verify: SvgVerifySpec,
    out_dir: Path,
    *,
    llm_repair: bool = False,
    complete=None,
) -> tuple[str, dict, bool]:
    score = score_openscad_2d_text(code, verify, out_dir / "before")
    repaired_any = False
    for attempt in range(_REPAIR_MAX):
        if not score.get("misses"):
            break
        before = svg_facts_from_code(code, out_dir / f"facts-{attempt}-before")
        patched = _patch_2d(code, score["misses"], verify)
        after = svg_facts_from_code(patched, out_dir / f"facts-{attempt}-after")
        if patched != code and _locks_held(before, after):
            code = patched
            repaired_any = True
            score = score_openscad_2d_text(code, verify, out_dir / f"patched-{attempt}")
            continue
        break
    return code, score, repaired_any


def parametric_var_count(code: str) -> int:
    return len(re.findall(r"^\s*[A-Za-z_]\w*\s*=", code, re.MULTILINE))


def _patch_2d(code: str, misses: list[dict], verify: SvgVerifySpec) -> str:
    patched = code
    for miss in misses:
        check_id = miss.get("check_id")
        if check_id == "hole_diameter" and verify.hole_min_mm is not None and verify.hole_max_mm is not None:
            target = (float(verify.hole_min_mm) + float(verify.hole_max_mm)) / 2
            measured = float(miss.get("measured_mm", 0))
            patched = _patch_hole_diameter(patched, measured, target)
        elif check_id == "outline_size":
            if verify.plate_width_mm and verify.plate_height_mm:
                patched = _patch_square(patched, verify.plate_width_mm, verify.plate_height_mm)
            elif verify.plate_diameter_mm:
                patched = _patch_circle_plate(patched, verify.plate_diameter_mm)
    return patched


def _patch_hole_diameter(code: str, measured: float, target: float) -> str:
    radius = target / 2
    tolerance = 0.2
    for match in re.finditer(r"circle\s*\([^)]*\)", code, re.IGNORECASE):
        call = match.group(0)
        current = _circle_diameter(call)
        if current is None or abs(current - measured) > tolerance:
            continue
        rewritten = _rewrite_radius(call, radius)
        if rewritten != call:
            return code[: match.start()] + rewritten + code[match.end() :]
    return code


def _patch_square(code: str, width: float, height: float) -> str:
    match = re.search(r"square\s*\(\s*\[([0-9.]+)\s*,\s*([0-9.]+)\s*\]\s*\)", code, re.IGNORECASE)
    if not match:
        return code
    return (
        code[: match.start(1)]
        + f"{width:g}"
        + code[match.end(1) : match.start(2)]
        + f"{height:g}"
        + code[match.end(2) :]
    )


def _patch_circle_plate(code: str, diameter: float) -> str:
    match = re.search(r"circle\s*\(\s*(?:d\s*=\s*)?([0-9.]+)", code, re.IGNORECASE)
    if not match:
        return code
    return code[: match.start(1)] + f"{diameter:g}" + code[match.end(1) :]


def _circle_diameter(call: str) -> float | None:
    named_d = re.search(r"\bd\s*=\s*([0-9.]+)", call, re.IGNORECASE)
    if named_d:
        return float(named_d.group(1))
    named_r = re.search(r"\br\s*=\s*([0-9.]+)", call, re.IGNORECASE)
    if named_r:
        return float(named_r.group(1)) * 2
    numbers = re.findall(r"[0-9.]+", call)
    if numbers:
        value = float(numbers[0])
        return value if "d" in call.lower() else value * 2
    return None


def _rewrite_radius(call: str, radius: float) -> str:
    named_d = re.search(r"(\bd\s*=\s*)([0-9.]+)", call, re.IGNORECASE)
    if named_d:
        return call[: named_d.start(2)] + f"{radius * 2:g}" + call[named_d.end(2) :]
    named_r = re.search(r"(\br\s*=\s*)([0-9.]+)", call, re.IGNORECASE)
    if named_r:
        return call[: named_r.start(2)] + f"{radius:g}" + call[named_r.end(2) :]
    numbers = list(re.finditer(r"[0-9.]+", call))
    if numbers:
        first = numbers[0]
        return call[: first.start()] + f"{radius * 2:g}" + call[first.end() :]
    return call


def _locks_held(before, after) -> bool:  # noqa: ANN001
    if before is None or after is None:
        return True
    if len(before.holes) and len(after.holes) < len(before.holes):
        return False
    return True
