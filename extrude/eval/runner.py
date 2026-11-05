"""Score one pass of the frozen eight. Cost counts only after the circuit works."""

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.live_gate import _off
from extrude.eval.gate import ScoreRow, judge_gate, row_from_run, write_log
from extrude.eval.tasks import load_tasks
from extrude.harness import run
from extrude.harness.envfile import load_env
from extrude.memory import reset

def _log_path() -> Path:
    name = os.environ.get("EXTRUDE_GATE_NAME", "luna").strip().lower() or "luna"
    if name == "luna":
        return ROOT / "eval" / "proxy_tasks" / "results-cost.json"
    return ROOT / "eval" / "proxy_tasks" / f"results-{name}.json"


def main() -> int:
    load_env(ROOT / ".env")
    if not os.environ.get("EXTRUDE_MODEL_KEY", "").strip() and not os.environ.get("OPENAI_API_KEY", "").strip():
        print("Put the OpenRouter key in .env as EXTRUDE_MODEL_KEY.")
        return 2
    if not os.environ.get("EXTRUDE_MODEL", "").strip():
        print("Put EXTRUDE_MODEL in .env.")
        return 2
    name = os.environ.get("EXTRUDE_GATE_NAME", "luna").strip().lower() or "luna"
    run_index = int(os.environ.get("EXTRUDE_GATE_RUN", "1"))
    tasks = load_tasks()
    rows = []
    print(f"model {os.environ.get('EXTRUDE_MODEL', '').strip()} as {name} run {run_index}")
    print(f"{'task':<12} {'harness':<6} {'technical':>10} {'S_cost':>8} {'score':>8} {'bom':>10} {'ref':>10}")
    for harness_on, fn in ((False, _off), (True, run)):
        reset()
        label = "on" if harness_on else "off"
        for task in tasks:
            started = time.perf_counter()
            outcome = fn(task.prompt)
            row = row_from_run(
                task,
                outcome,
                model=name,
                harness_on=harness_on,
                run=run_index,
                seconds=time.perf_counter() - started,
            )
            rows.append(row)
            bom = "" if outcome.bom_usd is None else f"{outcome.bom_usd:.4f}"
            print(
                f"{task.id:<12} {label:<6} {row.technical:10.2f} {row.cost_efficiency:8.3f} "
                f"{row.score:8.3f} {bom:>10} {task.reference_bom_usd:10.4f}  {outcome.status}"
            )
    log_path = _log_path()
    kept = [
        row
        for row in _load_rows(log_path)
        if not (row.model.strip().lower() == name and row.run == run_index)
    ]
    report = judge_gate(kept + rows)
    write_log(log_path, report)
    print()
    for item in report.summaries:
        if item.model != name:
            continue
        side = "on" if item.harness_on else "off"
        print(f"{item.model} harness {side} run {item.run}: {item.average * 100:.2f}%")
        if item.model == "luna" and not item.harness_on and item.average > 0.45:
            print("thrown out: luna with the harness off is already above 45%")
    print(f"wrote {log_path}")
    print(f"signed={report.signed} reason={report.reason}")
    return 0


def _load_rows(path: Path) -> list[ScoreRow]:
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [ScoreRow(**row) for row in payload.get("rows", [])]


if __name__ == "__main__":
    raise SystemExit(main())
