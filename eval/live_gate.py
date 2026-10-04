"""One harness-off pass and one harness-on pass of the frozen eight.

Reads the key from the environment. Does not call learn. Does not edit the tasks.
"""

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from extrude.checks import preflight
from extrude.emit import emit_cir
from extrude.eval.gate import ScoreRow, judge_gate, row_from_run, write_log
from extrude.eval.tasks import load_tasks
from extrude.harness import run
from extrude.harness.client import complete
from extrude.harness.models import RunResult
from extrude.harness.prompt import build_prompt
from extrude.harness.proposal import ProposalError, parse_proposal
from extrude.intake import resolve
from extrude.intake.models import NeedsInfo
from extrude.memory import reset
from extrude.physics import derive
from extrude.sim import run_allowed

_JOBS = {"buck", "ldo", "holdup_mlcc"}
_LOG = ROOT / "eval" / "proxy_tasks" / "results-live.json"


def main() -> int:
    name = os.environ.get("EXTRUDE_GATE_NAME", "").strip().lower()
    if name not in {"luna", "astra"}:
        _instructions()
        return 2
    if not os.environ.get("EXTRUDE_MODEL_KEY", "").strip() and not os.environ.get("OPENAI_API_KEY", "").strip():
        _instructions()
        return 2
    if not os.environ.get("EXTRUDE_MODEL", "").strip():
        _instructions()
        return 2
    run_index = int(os.environ.get("EXTRUDE_GATE_RUN", "1"))
    _warn_if_ngspice_missing()
    tasks = load_tasks()
    rows: list[ScoreRow] = []
    print("harness off")
    for task in tasks:
        started = time.perf_counter()
        outcome = _off(task.prompt)
        rows.append(
            row_from_run(
                task,
                outcome,
                model=name,
                harness_on=False,
                run=run_index,
                seconds=time.perf_counter() - started,
            )
        )
        print(f"  {task.id}: {outcome.status} {outcome.detail}")
    reset()
    print("harness on")
    for task in tasks:
        started = time.perf_counter()
        outcome = run(task.prompt)
        rows.append(
            row_from_run(
                task,
                outcome,
                model=name,
                harness_on=True,
                run=run_index,
                seconds=time.perf_counter() - started,
            )
        )
        print(f"  {task.id}: {outcome.status} {outcome.detail}")
    kept = [
        row
        for row in _load_rows()
        if not (row.model.strip().lower() == name and row.run == run_index)
    ]
    report = judge_gate(kept + rows)
    write_log(_LOG, report)
    print(f"wrote {_LOG}")
    print(f"signed={report.signed} reason={report.reason}")
    return 0


def _off(prompt: str) -> RunResult:
    resolved = resolve(prompt)
    if isinstance(resolved, NeedsInfo):
        return RunResult(status="needs_info", detail=resolved.question)
    if resolved.task_class not in _JOBS:
        return RunResult(
            status="stopped",
            spec_hash=resolved.spec_hash,
            detail="this seat only designs a buck, regulator, or hold-up",
        )
    try:
        text, usage = complete(build_prompt(resolved, [], []), "primary")
    except ProposalError as exc:
        return RunResult(status="stopped", spec_hash=resolved.spec_hash, detail=exc.detail)
    except Exception:
        return RunResult(status="stopped", spec_hash=resolved.spec_hash, detail="the model call failed")
    try:
        design, _identity = parse_proposal(text, resolved)
    except ProposalError as exc:
        return RunResult(
            status="stopped",
            spec_hash=resolved.spec_hash,
            detail=exc.detail,
            cost_usd=_cost(usage),
        )
    report = preflight(design)
    if report.blocking:
        return RunResult(
            status="stopped",
            spec_hash=resolved.spec_hash,
            detail=report.blocking[0],
            cost_usd=_cost(usage),
        )
    values = derive(design, resolved)
    failures = [item for item in values.findings if item.severity == "fail"]
    if failures:
        return RunResult(
            status="stopped",
            spec_hash=resolved.spec_hash,
            detail=failures[0].detail,
            cost_usd=_cost(usage),
        )
    if resolved.task_class == "holdup_mlcc":
        if not _cap_is_connected(design):
            return RunResult(
                status="stopped",
                spec_hash=resolved.spec_hash,
                detail="the hold-up capacitor is not connected",
                cost_usd=_cost(usage),
            )
        simulated = run_allowed(emit_cir(design, values))
        if simulated.status == "refused":
            return RunResult(
                status="stopped",
                spec_hash=resolved.spec_hash,
                detail=simulated.detail or "the deck was refused",
                cost_usd=_cost(usage),
            )
        if simulated.status != "measured":
            return RunResult(
                status="stopped",
                spec_hash=resolved.spec_hash,
                detail=simulated.detail or simulated.status,
                cost_usd=_cost(usage),
            )
    return RunResult(status="checked", spec_hash=resolved.spec_hash, detail="checked", cost_usd=_cost(usage))


def _cap_is_connected(design) -> bool:
    capacitors = {
        part.refdes
        for part in design.parts
        if part.kind == "capacitor" and part.capacitance and part.capacitance > 0
    }
    for refdes in capacitors:
        pins = [
            pin
            for pin in design.pins
            if pin.refdes == refdes and pin.state == "connected" and pin.net and pin.net.strip()
        ]
        if len(pins) >= 2:
            return True
    return False


def _cost(usage: dict) -> float | None:
    raw = usage.get("cost_usd", usage.get("cost"))
    if raw is None:
        return None
    return float(raw)


def _load_rows() -> list[ScoreRow]:
    if not _LOG.is_file():
        return []
    payload = json.loads(_LOG.read_text(encoding="utf-8"))
    return [ScoreRow(**row) for row in payload.get("rows", [])]


def _warn_if_ngspice_missing() -> None:
    chosen = os.environ.get("NGSPICE_PATH", "").strip()
    if not chosen or not Path(chosen).is_file():
        print("NGSPICE_PATH is not a ngspice file. Hold-up will miss as a tool.")


def _instructions() -> None:
    print("Set these in this shell, then run the script again. Do not put the key in a file.")
    print('$env:EXTRUDE_MODEL_URL = "https://openrouter.ai/api/v1/chat/completions"')
    print('$env:EXTRUDE_MODEL_KEY = "<OpenRouter key>"')
    print('$env:EXTRUDE_MODEL = "openai/gpt-6-luna"')
    print('$env:EXTRUDE_GATE_NAME = "luna"')
    print('$env:EXTRUDE_GATE_RUN = "1"')
    print(r'$env:NGSPICE_PATH = "C:\Users\atire\AppData\Local\Temp\extrude-ngspice\Spice64\bin\ngspice_con.exe"')
    print(r".\.venv\Scripts\python eval\live_gate.py")


if __name__ == "__main__":
    raise SystemExit(main())
