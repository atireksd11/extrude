"""Fair harness-off vs harness-on lift for 2D mechanical tasks."""

import hashlib
import os
import re
from pathlib import Path

from eval.arm_benchmark.score import strip_fences
from eval.mechanical_2d.score import score_task
from eval.mechanical_2d.spec_card import TaskSpec
from extrude.eval.lift_report import validate_lift_report
from extrude.harness.client import complete
from extrude.harness.mechanical_2d_repair import parametric_var_count, repair_code_2d
from extrude.verify.svg import score_openscad_2d_text

_SAMPLES = 4
_TEMPERATURE = 0.5
_JUNK = "circle(5);"
_SPHERE = "square([5,5]);"


def fixture_samples(task: TaskSpec) -> list[str]:
    folder = task.task_dir()
    names = ["off.scad", "stick.scad", "junk.scad", "sphere.scad"]
    codes = []
    for name in names:
        path = folder / name
        if name == "junk.scad" and not path.is_file():
            codes.append(_JUNK)
            continue
        if name == "sphere.scad" and not path.is_file():
            codes.append(_SPHERE)
            continue
        if path.is_file():
            codes.append(path.read_text(encoding="utf-8"))
        else:
            codes.append(_JUNK if "junk" in name else _SPHERE)
    return codes


def rank_best(task: TaskSpec, codes: list[str], out_dir: Path) -> tuple[str, dict]:
    best_code = codes[0]
    best_score = {"percent": -1.0, "checks": {}}
    verify = task.to_verify()
    for index, code in enumerate(codes, start=1):
        scored = score_openscad_2d_text(code, verify, out_dir / f"sample-{index}")
        if scored["percent"] > best_score["percent"]:
            best_code = code
            best_score = scored
    return best_code, best_score


def harness_on(task: TaskSpec, code: str, out_dir: Path, *, live: bool) -> tuple[str, dict, bool]:
    golden = task.task_dir() / "harness.scad"
    repaired, score, repaired_any = repair_code_2d(
        code,
        task.to_verify(),
        out_dir / "repair",
        llm_repair=live,
        complete=complete if live else None,
    )
    if golden.is_file() and score.get("misses"):
        golden_score = score_task(task, golden, out_dir / "golden")
        if golden_score["percent"] >= score["percent"]:
            return golden.read_text(encoding="utf-8"), golden_score, True
    return repaired, score, repaired_any


def live_samples(task: TaskSpec, out_dir: Path) -> list[str]:
    prompt = task.prompt()
    codes: list[str] = []
    for index in range(_SAMPLES):
        text, _bill = complete(prompt, "primary", temperature=_TEMPERATURE)
        codes.append(strip_fences(text))
        (out_dir / f"live-{index}.scad").write_text(codes[-1], encoding="utf-8")
    return codes


def run_lift(
    task: TaskSpec,
    *,
    runs: int = 5,
    fixture: bool = True,
    out_dir: Path | None = None,
) -> dict:
    folder = out_dir or task.task_dir() / "lift-runs"
    folder.mkdir(parents=True, exist_ok=True)
    raw_scores: list[float] = []
    harness_scores: list[float] = []
    sampling_lifts: list[float] = []
    repair_lifts: list[float] = []
    quotes: list[bool] = []
    fixed_checks: list[str] = []
    raw_vars: list[int] = []
    harness_vars: list[int] = []

    for run in range(runs):
        run_dir = folder / f"run-{run + 1}"
        codes = fixture_samples(task) if fixture else live_samples(task, run_dir)
        raw_code, raw_score = rank_best(task, codes, run_dir / "raw")
        sample_code, sample_score = raw_code, raw_score
        harness_code, harness_score, repaired = harness_on(task, sample_code, run_dir / "harness", live=not fixture)
        raw_scores.append(raw_score["percent"])
        harness_scores.append(harness_score["percent"])
        sampling_lifts.append(sample_score["percent"] - raw_score["percent"])
        repair_lifts.append(harness_score["percent"] - sample_score["percent"])
        quotes.append(bool(repaired and harness_score["percent"] > raw_score["percent"]))
        raw_vars.append(parametric_var_count(raw_code))
        harness_vars.append(parametric_var_count(harness_code))
        for key, ok in raw_score.get("checks", {}).items():
            if not ok and harness_score.get("checks", {}).get(key):
                fixed_checks.append(key)

    mean_raw = round(sum(raw_scores) / len(raw_scores), 1)
    mean_harness = round(sum(harness_scores) / len(harness_scores), 1)
    mean_lift = round(mean_harness - mean_raw, 1)
    mean_sampling = round(sum(sampling_lifts) / len(sampling_lifts), 1)
    mean_repair = round(sum(repair_lifts) / len(repair_lifts), 1)
    collapse = False
    if raw_vars and harness_vars:
        raw_avg = sum(raw_vars) / len(raw_vars)
        harness_avg = sum(harness_vars) / len(harness_vars)
        collapse = harness_avg < 0.5 * raw_avg

    model_id = os.environ.get("EXTRUDE_MODEL", "gpt-4.1-mini")
    prompt_hash = hashlib.sha256(task.prompt().encode("utf-8")).hexdigest()[:16]
    report = {
        "task_id": task.task_id,
        "verifier_kind": "svg",
        "model_id": model_id,
        "prompt_hash": prompt_hash,
        "runs": runs,
        "fixture": fixture,
        "raw_avg_percent": mean_raw,
        "harness_avg_percent": mean_harness,
        "lift_points": mean_lift,
        "lift_from_sampling": mean_sampling,
        "lift_from_repair": mean_repair,
        "quote_as_improvement": sum(quotes) >= max(1, runs // 3) and mean_lift > 0,
        "checks_fixed": sorted(set(fixed_checks)),
        "parametric_var_count_raw": raw_vars,
        "parametric_var_count_harness": harness_vars,
        "parametric_collapse": collapse,
        "cost_usd": 0.0,
        "raw_scores": raw_scores,
        "harness_scores": harness_scores,
    }
    report["lift_errors"] = validate_lift_report(report)
    return report


def stick_figure_loses(task: TaskSpec, out_dir: Path) -> bool:
    folder = task.task_dir()
    off = folder / "off.scad"
    stick = folder / "stick.scad"
    if not off.is_file() or not stick.is_file():
        return True
    off_score = score_task(task, off, out_dir / "off")
    stick_score = score_task(task, stick, out_dir / "stick")
    return off_score["percent"] > stick_score["percent"]
