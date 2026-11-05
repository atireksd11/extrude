"""Two Luna calls, one prompt. The score is frozen in score.py."""

import json
import os
from pathlib import Path

from extrude.copilot.budget import note_spend, spent_usd
from extrude.harness.client import complete
from extrude.harness.envfile import load_env
from eval.arm_benchmark.score import PROMPT, score_arm, strip_fences
from eval.legacy.string_harness import harness_prompt

_HERE = Path(__file__).resolve().parent


def main() -> None:
    load_env(Path.cwd() / ".env")
    os.environ.setdefault("EXTRUDE_SPEND_CAP_USD", "5")
    before = spent_usd()
    off_text, off_bill = complete(PROMPT, "primary")
    note_spend(float(off_bill.get("cost_usd") or 0))
    on_text, on_bill = complete(harness_prompt(), "primary")
    note_spend(float(on_bill.get("cost_usd") or 0))
    off_code = strip_fences(off_text)
    on_code = strip_fences(on_text)
    off_score = score_arm(off_code)
    on_score = score_arm(on_code)
    (_HERE / "off.scad").write_text(off_code, encoding="utf-8")
    (_HERE / "on.scad").write_text(on_code, encoding="utf-8")
    report = {
        "prompt": PROMPT,
        "off": {"percent": off_score["percent"], "checks": off_score["checks"], "cost_usd": off_bill.get("cost_usd")},
        "on": {"percent": on_score["percent"], "checks": on_score["checks"], "cost_usd": on_bill.get("cost_usd")},
        "lift_points": round(on_score["percent"] - off_score["percent"], 1),
        "spent_usd": round(spent_usd() - before, 6),
    }
    (_HERE / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
