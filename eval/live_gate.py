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
from extrude.coverage.api import render
from extrude.emit import emit_cir
from extrude.emit.netlist import emit_netlist
from extrude.eval.bom import design_bom_usd
from extrude.eval.gate import ScoreRow, judge_gate, row_from_run, write_log
from extrude.eval.tasks import load_tasks
from extrude.harness import run
from extrude.harness.client import complete
from extrude.harness.envfile import load_env
from extrude.harness.models import RunResult
from extrude.harness.loop import _holdup_cap_is_connected
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
    load_env(ROOT / ".env")
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
        return RunResult(status="needs_info", detail=resolved.question, notice=render(None, []))
    if resolved.task_class not in _JOBS:
        return RunResult(
            status="stopped",
            spec_hash=resolved.spec_hash,
            detail="this seat only designs a buck, regulator, or hold-up",
            notice=render(resolved, []),
        )
    try:
        text, usage = complete(build_prompt(resolved, [], []), "primary")
        _keep_reply(text)
    except ProposalError as exc:
        return _spoken(resolved, exc.detail, None, ran=[])
    except Exception:
        return _spoken(resolved, "the model call failed", None, ran=[])
    try:
        design, _identity = parse_proposal(text, resolved)
    except ProposalError as exc:
        return _spoken(resolved, exc.detail, usage, ran=[])
    report = preflight(design)
    if report.blocking:
        return _spoken(resolved, report.blocking[0], usage, ran=["wiring"], stopped="wiring")
    values = derive(design, resolved)
    failures = [item for item in values.findings if item.severity == "fail"]
    physics = _off_physics(resolved, values)
    if failures:
        code = failures[0].code
        stopped = "ripple" if "ripple" in code else ("still-air heat" if resolved.task_class == "ldo" else "capacitance")
        return _spoken(resolved, failures[0].detail, usage, ran=physics, stopped=stopped)
    if resolved.task_class == "holdup_mlcc":
        if not _holdup_cap_is_connected(design):
            return _spoken(
                resolved,
                "the hold-up capacitor is not connected",
                usage,
                ran=physics,
                stopped="hold-up connection",
            )
        simulated = run_allowed(emit_cir(design, values))
        faded = [*physics, "hold-up fade"]
        if simulated.status == "refused" or simulated.status != "measured":
            return _spoken(
                resolved,
                simulated.detail or simulated.status or "the deck was refused",
                usage,
                ran=faded,
                stopped="hold-up fade",
            )
    passed = [*physics, *(["hold-up connection", "hold-up fade"] if resolved.task_class == "holdup_mlcc" else []), "parts-cost"]
    return RunResult(
        status="checked",
        spec_hash=resolved.spec_hash,
        detail="checked",
        cost_usd=_cost(usage),
        bom_usd=design_bom_usd(design, resolved.task_class),
        notice=render(resolved, passed),
        netlist=emit_netlist(design),
    )


def _off_physics(spec, values) -> list[str]:
    ran = ["wiring"]
    if spec.task_class in {"buck", "holdup_mlcc"} and values.caps:
        ran.append("capacitance")
    if spec.task_class == "buck" and values.ripple_pp is not None:
        ran.append("ripple")
    if values.heat_note:
        ran.append("still-air heat")
    return ran


def _spoken(spec, detail: str, usage: dict | None, ran: list[str], stopped: str | None = None) -> RunResult:
    return RunResult(
        status="stopped",
        spec_hash=spec.spec_hash,
        detail=detail,
        cost_usd=None if usage is None else _cost(usage),
        notice=render(spec, ran, stopped),
    )


def _keep_reply(text: str) -> None:
    path = os.environ.get("EXTRUDE_SAVE_REPLY", "").strip()
    if not path:
        return
    target = Path(path)
    previous = target.read_text(encoding="utf-8") if target.is_file() else ""
    target.write_text(text if not previous else previous + "\n\n---\n\n" + text, encoding="utf-8")


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
    print("Put the OpenRouter key in .env as EXTRUDE_MODEL_KEY. See .env.example.")
    print("That file is gitignored. Do not commit it and do not paste the key into chat.")


if __name__ == "__main__":
    raise SystemExit(main())
