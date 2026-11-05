"""Repair the colored arm's 6.4 mm holes. Keep the rest."""

import json
import os
from pathlib import Path

from eval.arm_benchmark.score import strip_fences
from eval.arm_benchmark.spec_card import load_spec
from eval.arm_benchmark.solid_score import score_solid
from extrude.copilot.budget import note_spend
from extrude.copilot.fix_loop import locks_held, render_locks
from extrude.harness.client import complete
from extrude.harness.envfile import load_env
from eval.arm_benchmark.run_solid import repair_prompt

here = Path(__file__).resolve().parent
load_env(Path.cwd() / ".env")
os.environ.setdefault("EXTRUDE_SPEND_CAP_USD", "5")
os.environ.setdefault("OPENSCAD_PATH", r"C:\Program Files\OpenSCAD\openscad.exe")
spec = load_spec()
raw = (here / "off.scad").read_text(encoding="utf-8")
locks = render_locks(raw)
detail = "base hole diameter is 6.4 mm. PETG M3 inserts must be between 4.05 and 4.35 mm."
text, bill = complete(repair_prompt(raw, detail, locks), "primary")
note_spend(float(bill.get("cost_usd") or 0))
candidate = strip_fences(text)
kept = locks_held(raw, candidate)
out = here / "harness-repaired.scad"
out.write_text(candidate if kept else raw, encoding="utf-8")
raw_score = score_solid(here / "off.scad", spec, here / "compare-off-card")
fixed_score = score_solid(out, spec, here / "repaired-render")
report = {
    "verifier_kind": "solid",
    "kept_locks": kept,
    "cost_usd": bill.get("cost_usd"),
    "off": {"percent": raw_score["percent"], "checks": raw_score["checks"], "misses": raw_score.get("misses")},
    "repaired": {"percent": fixed_score["percent"], "checks": fixed_score["checks"], "misses": fixed_score.get("misses")},
    "lift_points": round(fixed_score["percent"] - raw_score["percent"], 1),
    "quote_as_improvement": bool(kept and fixed_score["percent"] > raw_score["percent"]),
}
(here / "results-repair.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
