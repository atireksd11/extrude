"""Surgical OpenSCAD repair shared by product and eval."""

import json
import re
from pathlib import Path

from eval.arm_benchmark.score import strip_fences
from extrude.copilot.fix_loop import locks_held, render_locks
from extrude.harness.proposal import ProposalError
from extrude.verify.models import SolidVerifySpec
from extrude.verify.solid import geometric_facts, score_openscad_text

_REPAIR_MAX = 2


def repair_code(
    code: str,
    verify: SolidVerifySpec,
    out_dir: Path,
    *,
    llm_repair: bool = True,
    complete=None,
) -> tuple[str, dict, bool]:
    """Return patched code, final score, and whether any repair was applied."""
    score = score_openscad_text(code, verify, out_dir / "before")
    repaired_any = False
    for attempt in range(_REPAIR_MAX):
        if not score.get("misses"):
            break
        before_facts = score.get("facts") or geometric_facts(code, out_dir / f"facts-{attempt}-before")
        locks = render_locks(code, before_facts)
        patched = _patch_solid(code, score["misses"], verify)
        if patched != code and locks_held(
            code, patched, before_facts, geometric_facts(patched, out_dir / f"facts-{attempt}-patch")
        ):
            code = patched
            repaired_any = True
            score = score_openscad_text(code, verify, out_dir / f"patched-{attempt}")
            continue
        if not llm_repair or complete is None:
            break
        llm = _llm_repair(code, score["misses"], locks, complete)
        if llm is None:
            break
        after_facts = geometric_facts(llm, out_dir / f"facts-{attempt}-after")
        if not locks_held(code, llm, before_facts, after_facts):
            break
        code = llm
        repaired_any = True
        score = score_openscad_text(code, verify, out_dir / f"llm-{attempt}")
    return code, score, repaired_any


def parametric_var_count(code: str) -> int:
    return len(re.findall(r"^\s*[A-Za-z_]\w*\s*=", code, re.MULTILINE))


def _patch_solid(code: str, misses: list[dict], verify: SolidVerifySpec) -> str:
    patched = code
    for miss in misses:
        if miss.get("check_id") == "insert_diameter" or miss.get("feature") == "base_insert":
            target = (float(verify.insert_min_mm) + float(verify.insert_max_mm)) / 2
            patched = _patch_hole_diameter(patched, float(miss["measured_mm"]), target)
        elif miss.get("check_id") == "joint_wall" or miss.get("feature") == "joint_wall":
            patched = _patch_wall_thickness(patched, float(miss["measured_mm"]), float(miss["limit_mm"]))
    return patched


def _patch_hole_diameter(code: str, measured: float, target: float) -> str:
    radius = target / 2
    tolerance = 0.05
    for match in re.finditer(r"cylinder\s*\([^)]*\)", code, re.IGNORECASE):
        call = match.group(0)
        current = _cylinder_diameter(call)
        if current is None or abs(current - measured) > tolerance:
            continue
        rewritten = _rewrite_radius(call, radius)
        if rewritten != call:
            return code[: match.start()] + rewritten + code[match.end() :]
    return code


def _patch_wall_thickness(code: str, measured: float, limit: float) -> str:
    tolerance = 0.05
    pattern = re.compile(r"(\bh\s*=\s*)([0-9.]+)")

    def replacer(match: re.Match[str]) -> str:
        value = float(match.group(2))
        if abs(value - measured) <= tolerance and value < limit:
            return f"{match.group(1)}{limit:g}"
        return match.group(0)

    return pattern.sub(replacer, code)


def _cylinder_diameter(call: str) -> float | None:
    named_d = re.search(r"\bd\s*=\s*([0-9.]+)", call, re.IGNORECASE)
    if named_d:
        return float(named_d.group(1))
    named_r = re.search(r"\br\s*=\s*([0-9.]+)", call, re.IGNORECASE)
    if named_r:
        return float(named_r.group(1)) * 2
    numbers = re.findall(r"[0-9.]+", call)
    if len(numbers) >= 2:
        return float(numbers[1]) * 2
    return None


def _rewrite_radius(call: str, radius: float) -> str:
    named_d = re.search(r"(\bd\s*=\s*)([0-9.]+)", call, re.IGNORECASE)
    if named_d:
        return call[: named_d.start(2)] + f"{radius * 2:g}" + call[named_d.end(2) :]
    named_r = re.search(r"(\br\s*=\s*)([0-9.]+)", call, re.IGNORECASE)
    if named_r:
        return call[: named_r.start(2)] + f"{radius:g}" + call[named_r.end(2) :]
    numbers = list(re.finditer(r"[0-9.]+", call))
    if len(numbers) >= 2:
        second = numbers[1]
        return call[: second.start()] + f"{radius:g}" + call[second.end() :]
    return call


def _llm_repair(code: str, misses: list[dict], locks: list[dict], complete) -> str | None:
    kept = ", ".join(item["feature"] for item in locks) or "the rendered shape"
    payload = "\n".join(item["detail"] for item in misses)
    prompt = (
        "Return JSON only: {\"edits\": [{\"start\": int, \"end\": int, \"text\": str}]}\n"
        f"MUST_FIX:\n{payload}\n"
        f"DO_NOT_BREAK: {kept}\n"
        f"OpenSCAD:\n{code}"
    )
    try:
        text, _bill = complete(prompt, "primary", temperature=0)
    except ProposalError:
        return None
    try:
        payload = json.loads(strip_fences(text))
    except json.JSONDecodeError:
        return None
    edits = payload.get("edits") or []
    return _apply_edits(code, edits)


def _apply_edits(code: str, edits: list[dict]) -> str:
    for edit in sorted(edits, key=lambda item: int(item.get("start", 0)), reverse=True):
        start = int(edit["start"])
        end = int(edit["end"])
        code = code[:start] + str(edit["text"]) + code[end:]
    return code
