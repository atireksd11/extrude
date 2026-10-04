"""The show-people bar. Power tasks alone cannot sign it."""

from pathlib import Path

from pydantic import BaseModel, Field

from extrude.eval.api import blend, score
from extrude.eval.tasks import PracticeTask, load_tasks
from extrude.harness.models import RunResult

_LUNA = "luna"
_ASTRA = "astra"
_BARS = {_LUNA: 0.40, _ASTRA: 0.73}
_EASY = {_LUNA: 0.45, _ASTRA: 0.80}


class ScoreRow(BaseModel):
    task_id: str
    model: str
    harness_on: bool
    run: int
    technical: float
    cost_efficiency: float
    score: float
    dollars: float | None = None
    seconds: float
    miss_kind: str | None = None


class RunSummary(BaseModel):
    model: str
    harness_on: bool
    run: int
    average: float
    dollars: float | None
    seconds: float


class GateReport(BaseModel):
    signed: bool
    reason: str
    rows: list[ScoreRow] = Field(default_factory=list)
    summaries: list[RunSummary] = Field(default_factory=list)


def row_from_run(
    task: PracticeTask,
    result: RunResult,
    *,
    model: str,
    harness_on: bool,
    run: int,
    seconds: float,
) -> ScoreRow:
    stamped = result.model_copy(update={"reference_bom_usd": task.reference_bom_usd})
    if (
        task.family == "power"
        and stamped.status == "checked"
        and stamped.spec_hash != task.card.get("spec_hash")
    ):
        stamped = stamped.model_copy(
            update={"status": "stopped", "detail": "the frozen card does not match"}
        )
    card = score(stamped)
    return ScoreRow(
        task_id=task.id,
        model=model,
        harness_on=harness_on,
        run=run,
        technical=card.technical or 0.0,
        cost_efficiency=card.cost_efficiency or 0.0,
        score=card.score or 0.0,
        dollars=stamped.cost_usd,
        seconds=seconds,
        miss_kind=_miss_kind(stamped),
    )


def judge_gate(rows: list[ScoreRow]) -> GateReport:
    tasks = load_tasks()
    ids = {task.id for task in tasks}
    power = {task.id for task in tasks if task.family == "power"}
    if not rows:
        return GateReport(signed=False, reason="no runs yet")
    seen = {row.task_id for row in rows}
    if seen <= power:
        return GateReport(signed=False, reason="power tasks alone do not sign", rows=rows)
    if seen != ids:
        return GateReport(signed=False, reason="the set is not the frozen eight", rows=rows)
    summaries = _summaries(rows, ids)
    names = {_name(row.model) for row in rows}
    if _LUNA not in names or _ASTRA not in names:
        return GateReport(
            signed=False,
            reason="Luna and Astra were not both logged",
            rows=rows,
            summaries=summaries,
        )
    too_easy = _too_easy(summaries)
    if too_easy:
        return GateReport(signed=False, reason=too_easy, rows=rows, summaries=summaries)
    if not _logged(summaries, _LUNA, False) or not _logged(summaries, _ASTRA, False):
        return GateReport(
            signed=False,
            reason="harness-off was not logged",
            rows=rows,
            summaries=summaries,
        )
    luna = _on_runs(summaries, _LUNA)
    astra = _on_runs(summaries, _ASTRA)
    if len(luna) >= 2 and len(astra) >= 2 and all(item.average >= _BARS[_LUNA] for item in luna) and all(
        item.average >= _BARS[_ASTRA] for item in astra
    ):
        return GateReport(
            signed=True,
            reason="both models cleared the bar twice",
            rows=rows,
            summaries=summaries,
        )
    return GateReport(
        signed=False,
        reason="the bar was not cleared twice",
        rows=rows,
        summaries=summaries,
    )


def write_log(path: Path, report: GateReport) -> None:
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")


def _summaries(rows: list[ScoreRow], ids: set[str]) -> list[RunSummary]:
    grouped: dict[tuple[str, bool, int], list[ScoreRow]] = {}
    for row in rows:
        grouped.setdefault((_name(row.model), row.harness_on, row.run), []).append(row)
    summaries = []
    for (model, harness_on, run), items in sorted(grouped.items()):
        if len(items) != len(ids) or {item.task_id for item in items} != ids:
            continue
        dollars = [item.dollars for item in items]
        summaries.append(
            RunSummary(
                model=model,
                harness_on=harness_on,
                run=run,
                average=sum(blend(item.technical, item.cost_efficiency) for item in items) / len(ids),
                dollars=None if any(item is None for item in dollars) else sum(dollars),
                seconds=sum(item.seconds for item in items),
            )
        )
    return summaries


def _too_easy(summaries: list[RunSummary]) -> str | None:
    for model, limit in _EASY.items():
        if any(
            item.average > limit
            for item in summaries
            if item.model == model and not item.harness_on
        ):
            return f"{model} with the harness off is already above the easy line"
    return None


def _logged(summaries: list[RunSummary], model: str, harness_on: bool) -> bool:
    return any(item.model == model and item.harness_on is harness_on for item in summaries)


def _on_runs(summaries: list[RunSummary], model: str) -> list[RunSummary]:
    return [item for item in summaries if item.model == model and item.harness_on]


def _name(model: str) -> str:
    return model.strip().lower()


def _miss_kind(result: RunResult) -> str | None:
    if result.status == "checked":
        return None
    if result.status == "needs_info" or "only designs" in (result.detail or ""):
        return "request"
    detail = (result.detail or "").lower()
    if any(bit in detail for bit in ("no model key", "model call failed", "not json", "simulator", "ngspice")):
        return "tool"
    return "design"
