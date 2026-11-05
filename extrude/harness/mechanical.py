"""Mechanical generate: best-of-N, solid verify, surgical repair."""

from pathlib import Path

from eval.arm_benchmark.score import strip_fences
from extrude.harness.mechanical_2d_repair import repair_code_2d
from extrude.harness.mechanical_repair import repair_code
from extrude.harness.models import RunResult
from extrude.harness.proposal import ProposalError
from extrude.intake.models import FrozenSpec
from extrude.spec import SpecCard
from extrude.tools import missing_required
from extrude.verify.solid import score_openscad_text, spec_from_frozen
from extrude.verify.svg import score_openscad_2d_text, spec_from_frozen_2d

_SAMPLES = 4
_TEMPERATURE = 0.6
from extrude.runtime import data_dir

_GENERATED = data_dir() / "generated"


def walk_mechanical(spec: FrozenSpec, sentence: str, filament: str = "PETG") -> RunResult:
    missing = missing_required(spec.task_class)
    if missing:
        return RunResult(
            status="stopped",
            spec_hash=spec.spec_hash,
            detail=f"tooling: install {missing[0]} for mechanical generate",
        )
    if spec.task_class == "mechanical_2d":
        return _walk_mechanical_2d(spec)
    verify = spec_from_frozen(spec, filament)
    prompt = _prompt(spec, filament)
    out_dir = _GENERATED / spec.spec_hash[:12]
    out_dir.mkdir(parents=True, exist_ok=True)

    candidates: list[tuple[float, str, dict]] = []
    prompt_tokens = 0
    completion_tokens = 0
    cost_usd: float | None = None
    attempts = 0

    for _ in range(_SAMPLES):
        if not _within_spend():
            break
        try:
            text, bill = _complete(prompt, "primary", temperature=_TEMPERATURE)
        except ProposalError as exc:
            if not candidates:
                return RunResult(
                    status="stopped",
                    spec_hash=spec.spec_hash,
                    detail=exc.detail,
                    attempts=attempts,
                )
            break
        attempts += 1
        prompt_tokens, completion_tokens, cost_usd = _add_bill(prompt_tokens, completion_tokens, cost_usd, bill)
        if bill.get("cost_usd") is not None:
            _note_spend(float(bill["cost_usd"]))
        code = strip_fences(text)
        score = score_openscad_text(code, verify, out_dir / f"sample-{attempts}")
        candidates.append((score["percent"], code, score))

    if not candidates:
        return RunResult(
            status="stopped",
            spec_hash=spec.spec_hash,
            detail="no model samples were scored",
            attempts=attempts,
            cost_usd=cost_usd,
        )

    candidates.sort(key=lambda item: item[0], reverse=True)
    code = candidates[0][1]
    code, score, repaired = repair_code(code, verify, out_dir, llm_repair=True, complete=_complete)

    final_path = out_dir / "design.scad"
    final_path.write_text(code, encoding="utf-8")
    final_score = score_openscad_text(code, verify, out_dir / "final")
    render = final_score.get("render") or {}
    preview = render.get("png")
    stl = render.get("stl")
    preview_url = None
    if preview:
        preview_rel = Path(preview).relative_to(out_dir)
        preview_url = f"/artifacts/{spec.spec_hash[:12]}/{preview_rel.as_posix()}"
    status = "checked" if final_score.get("checks", {}).get("compiles") and not final_score.get("misses") else "stopped"
    detail = None
    if final_score.get("misses"):
        detail = final_score["misses"][0]["detail"]
    elif final_score.get("detail"):
        detail = final_score["detail"]
    return RunResult(
        status=status,
        spec_hash=spec.spec_hash,
        detail=detail,
        attempts=attempts + (1 if repaired else 0),
        prompt_tokens=prompt_tokens or None,
        completion_tokens=completion_tokens or None,
        cost_usd=cost_usd,
        code=code,
        preview_png=preview_url,
        stl_path=stl,
    )


def _walk_mechanical_2d(spec: FrozenSpec) -> RunResult:
    verify = spec_from_frozen_2d(spec)
    prompt = _prompt_2d(spec)
    out_dir = _GENERATED / spec.spec_hash[:12]
    out_dir.mkdir(parents=True, exist_ok=True)

    candidates: list[tuple[float, str, dict]] = []
    prompt_tokens = 0
    completion_tokens = 0
    cost_usd: float | None = None
    attempts = 0

    for _ in range(_SAMPLES):
        if not _within_spend():
            break
        try:
            text, bill = _complete(prompt, "primary", temperature=_TEMPERATURE)
        except ProposalError as exc:
            if not candidates:
                return RunResult(
                    status="stopped",
                    spec_hash=spec.spec_hash,
                    detail=exc.detail,
                    attempts=attempts,
                )
            break
        attempts += 1
        prompt_tokens, completion_tokens, cost_usd = _add_bill(prompt_tokens, completion_tokens, cost_usd, bill)
        if bill.get("cost_usd") is not None:
            _note_spend(float(bill["cost_usd"]))
        code = strip_fences(text)
        score = score_openscad_2d_text(code, verify, out_dir / f"sample-{attempts}")
        candidates.append((score["percent"], code, score))

    if not candidates:
        return RunResult(
            status="stopped",
            spec_hash=spec.spec_hash,
            detail="no model samples were scored",
            attempts=attempts,
            cost_usd=cost_usd,
        )

    candidates.sort(key=lambda item: item[0], reverse=True)
    code = candidates[0][1]
    code, score, repaired = repair_code_2d(code, verify, out_dir, llm_repair=True, complete=_complete)

    final_path = out_dir / "design.scad"
    final_path.write_text(code, encoding="utf-8")
    final_score = score_openscad_2d_text(code, verify, out_dir / "final")
    render = final_score.get("render") or {}
    preview = render.get("png")
    svg = render.get("svg")
    preview_url = None
    if preview:
        preview_rel = Path(preview).relative_to(out_dir)
        preview_url = f"/artifacts/{spec.spec_hash[:12]}/{preview_rel.as_posix()}"
    status = "checked" if final_score.get("checks", {}).get("compiles") and not final_score.get("misses") else "stopped"
    detail = None
    if final_score.get("misses"):
        detail = final_score["misses"][0]["detail"]
    elif final_score.get("detail"):
        detail = final_score["detail"]
    return RunResult(
        status=status,
        spec_hash=spec.spec_hash,
        detail=detail,
        attempts=attempts + (1 if repaired else 0),
        prompt_tokens=prompt_tokens or None,
        completion_tokens=completion_tokens or None,
        cost_usd=cost_usd,
        code=code,
        preview_png=preview_url,
        svg_path=svg,
    )


def _prompt_2d(spec: FrozenSpec) -> str:
    card = SpecCard(
        sentence=spec.evidence.get("sentence", ""),
        domain="mechanical_2d",
        material=spec.labels.get("material"),
        plate_width_mm=spec.values_si.get("plate_width_mm"),
        plate_height_mm=spec.values_si.get("plate_height_mm"),
        plate_diameter_mm=spec.values_si.get("plate_diameter_mm"),
        hole=spec.labels.get("hole"),
        hole_count=int(spec.values_si.get("hole_count", 0)),
        hole_min_mm=spec.values_si.get("hole_min_mm"),
        hole_max_mm=spec.values_si.get("hole_max_mm"),
    )
    return card.prompt() + _openscad_suffix_2d()


def _openscad_suffix_3d() -> str:
    return (
        "\nUse millimeters. Output only valid OpenSCAD code — no markdown fences."
        "\nPut key dimensions in named variables at the top."
        "\nUse color() on major segments so the assembly reads clearly in preview."
        "\nKeep the longest edge between 80 and 250 mm unless the request says otherwise."
        "\nIf this is an articulated manipulator, it must stand off the table:"
        "\n- a rounded floor plate with corner mounting holes"
        "\n- a vertical turret / pedestal"
        "\n- stacked hinge bosses"
        "\n- three hull beams between bosses, each at least 55 mm long"
        "\n- pitch the middle hinges (rotate around Y) so the beams leave the XY plane"
        "\n- a two-jaw parallel hand at the tip, each jaw 15–35 mm"
        "\nDo not output a single cube, a flat slab, or a 2D layout of boxes."
    )


def _openscad_suffix_2d() -> str:
    return (
        "\nUse millimeters. Output only OpenSCAD 2D profile code (square/circle/difference/polygon) — no linear_extrude."
        "\nPut plate width, height, and hole positions in variables."
        "\nMounting holes must be clearance size for the requested screw, inset from corners as specified."
    )


def _prompt(spec: FrozenSpec, filament: str) -> str:
    material = spec.labels.get("material") or filament.upper()
    insert = spec.labels.get("insert")
    insert_count = int(spec.values_si.get("insert_count", 0))
    card = SpecCard(
        sentence=spec.evidence.get("sentence", ""),
        domain=spec.task_class,
        material=material,
        insert=insert,
        insert_count=insert_count,
        insert_min_mm=spec.values_si.get("insert_min_mm"),
        insert_max_mm=spec.values_si.get("insert_max_mm"),
        min_wall_mm=spec.values_si.get("min_wall_mm"),
    )
    return card.prompt() + _openscad_suffix_3d()


def _complete(prompt: str, seat: str, *, temperature: float = 0) -> tuple[str, dict]:
    from extrude.harness.loop import _client

    return _client(prompt, seat, temperature=temperature)


def _within_spend() -> bool:
    from extrude.copilot.budget import under_cap

    return under_cap()


def _note_spend(amount: float) -> None:
    from extrude.copilot.budget import note_spend

    note_spend(amount)


def _add_bill(prompt_tokens: int, completion_tokens: int, cost_usd: float | None, usage: dict) -> tuple[int, int, float | None]:
    if usage.get("prompt_tokens") is not None:
        prompt_tokens += int(usage["prompt_tokens"])
    if usage.get("completion_tokens") is not None:
        completion_tokens += int(usage["completion_tokens"])
    if usage.get("cost_usd") is not None:
        cost_usd = (cost_usd or 0) + float(usage["cost_usd"])
    return prompt_tokens, completion_tokens, cost_usd
