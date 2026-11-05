"""One raw call and, if the solid misses, one repair call. No answer key."""

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
from extrude.verify.solid import geometric_facts

_HERE = Path(__file__).resolve().parent


def repair_prompt(code: str, detail: str, locks: list[dict]) -> str:
    kept = ", ".join(item["feature"] for item in locks) or "the rendered shape"
    return (
        "The OpenSCAD below was rendered. Change only the failing measurement.\n"
        f"MUST_FIX: {detail}\n"
        f"DO_NOT_BREAK: {kept}\n"
        "Return the full OpenSCAD file only.\n\n"
        f"{code}"
    )


def main() -> None:
    load_env(Path.cwd() / ".env")
    os.environ.setdefault("EXTRUDE_SPEND_CAP_USD", "5")
    spec = load_spec()
    asked = spec.prompt()
    if "link1" in asked or "module " in asked:
        raise SystemExit("the spec card contains an answer key")
    raw_text, raw_bill = complete(asked, "primary")
    note_spend(float(raw_bill.get("cost_usd") or 0))
    raw_code = strip_fences(raw_text)
    raw_path = _HERE / "raw-solid.scad"
    raw_path.write_text(raw_code, encoding="utf-8")
    raw_score = score_solid(raw_path, spec, _HERE / "raw-render")
    harness_code = raw_code
    harness_bill = None
    repaired = False
    before_facts = None
    if raw_score.get("misses"):
        before_facts = geometric_facts(raw_code, _HERE / "raw-render" / "facts")
        locks = render_locks(raw_code, before_facts)
        details = "\n".join(item["detail"] for item in raw_score["misses"])
        fix = repair_prompt(raw_code, details, locks)
        if "link1" in fix.split("MUST_FIX:", 1)[0]:
            raise SystemExit("the repair prompt contains an answer key")
        fixed_text, harness_bill = complete(fix, "primary")
        note_spend(float(harness_bill.get("cost_usd") or 0))
        candidate = strip_fences(fixed_text)
        repaired = True
        after_facts = geometric_facts(candidate, _HERE / "raw-render" / "facts-after")
        if locks_held(raw_code, candidate, before_facts, after_facts):
            harness_code = candidate
        else:
            harness_code = raw_code
    harness_path = _HERE / "harness-solid.scad"
    harness_path.write_text(harness_code, encoding="utf-8")
    harness_score = score_solid(harness_path, spec, _HERE / "harness-render")
    kept_facts = geometric_facts(harness_code, _HERE / "harness-render" / "facts")
    kept = locks_held(raw_code, harness_code, before_facts, kept_facts)
    lift = round(harness_score["percent"] - raw_score["percent"], 1)
    quote = bool(repaired and kept and lift > 0 and harness_code != raw_code)
    report = {
        "verifier_kind": "solid",
        "prompt": asked,
        "raw": {"percent": raw_score["percent"], "checks": raw_score["checks"], "cost_usd": raw_bill.get("cost_usd")},
        "harness": {
            "percent": harness_score["percent"],
            "checks": harness_score["checks"],
            "cost_usd": None if harness_bill is None else harness_bill.get("cost_usd"),
            "repaired": repaired,
            "locks_held": kept,
        },
        "lift_points": lift,
        "quote_as_improvement": quote,
    }
    (_HERE / "results-solid.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
