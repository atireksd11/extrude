"""Phase 7. The formula is tested on known numbers. The gate stays unsigned without real model runs."""

import math

import pytest

from extrude.eval.api import export_note, score
from extrude.eval.gate import ScoreRow, judge_gate, row_from_run, write_log
from extrude.eval.tasks import load_tasks
from extrude.harness.client import complete
from extrude.harness.models import RunResult
from extrude.harness.proposal import ProposalError
from extrude.intake import resolve
from extrude.learn import propose_offline
from extrude.memory import reset


@pytest.fixture(autouse=True)
def _clean_notebooks():
    reset()
    yield
    reset()


def test_eight_cards_match_the_sentences():
    tasks = load_tasks()
    assert len(tasks) == 8
    assert {task.id for task in tasks if task.family == "power"} == {"holdup", "buck", "regulator"}
    for task in tasks:
        assert resolve(task.prompt).model_dump(mode="json") == task.card
        total = sum(part.qty * part.usd for part in task.reference_parts)
        assert total == pytest.approx(task.reference_bom_usd)


def test_a_failed_circuit_gets_no_cost_credit():
    card = score(RunResult(status="stopped", bom_usd=0.01, reference_bom_usd=100.0))
    assert card.technical == 0.0
    assert card.cost_efficiency == 0.0
    assert card.score == 0.0


def test_cost_credit_scales_only_after_the_circuit_works():
    expensive = score(RunResult(status="checked", bom_usd=2.0, reference_bom_usd=1.0))
    assert expensive.score == pytest.approx(0.825)
    cheap = score(RunResult(status="checked", bom_usd=0.5, reference_bom_usd=1.0))
    assert cheap.score == pytest.approx(1.0)
    unpriced = score(RunResult(status="checked", bom_usd=None, reference_bom_usd=1.0))
    assert unpriced.technical == 1.0
    assert unpriced.cost_efficiency == 0.0
    assert unpriced.score == pytest.approx(0.65)
    nonsense = score(RunResult(status="checked", bom_usd=math.nan, reference_bom_usd=1.0))
    assert nonsense.cost_efficiency == 0.0


def test_export_names_what_was_not_checked():
    note = export_note(RunResult(status="stopped"))
    assert "heat-in-airflow" in note
    assert "radios" in note
    assert "fast memory" in note
    assert "not an official EEBench score" in note
    assert "Parts cost was not credited" in note
    report = judge_gate([])
    assert "heat-in-airflow" in report.notice
    assert "radios" in report.notice
    assert "fast memory" in report.notice


def test_power_tasks_alone_do_not_sign():
    power = [task.id for task in load_tasks() if task.family == "power"]
    rows = [_row(task_id, "luna", True, 1, 1.0) for task_id in power]
    report = judge_gate(rows)
    assert report.signed is False
    assert report.reason == "power tasks alone do not sign"


def test_perfect_power_and_failed_others_stay_under_the_bar():
    rows = []
    for model in ("luna", "astra"):
        for run in (1, 2):
            for harness_on in (True, False):
                for task in load_tasks():
                    earned = 1.0 if task.family == "power" else 0.0
                    rows.append(_row(task.id, model, harness_on, run, earned))
    report = judge_gate(rows)
    assert report.signed is False
    assert report.reason == "the bar was not cleared twice"
    assert report.summaries[0].average == pytest.approx(0.375)


def test_a_recorded_pair_can_sign_only_when_both_bars_and_the_off_runs_hold():
    report = judge_gate(_clearing())
    assert report.signed is True
    luna = [item for item in report.summaries if item.model == "luna" and item.harness_on]
    astra = [item for item in report.summaries if item.model == "astra" and item.harness_on]
    assert len(luna) == 2
    assert luna[0].average == pytest.approx(0.50)
    assert astra[0].average == pytest.approx(0.75)
    assert luna[0].dollars == pytest.approx(0.08)
    assert luna[0].seconds == pytest.approx(4.0)


def test_a_lied_score_does_not_move_the_average():
    rows = []
    for model in ("luna", "astra"):
        for run in (1, 2):
            for harness_on in (True, False):
                for task in load_tasks():
                    row = _row(task.id, model, harness_on, run, 0.0)
                    row.score = 1.0
                    rows.append(row)
    report = judge_gate(rows)
    assert report.signed is False
    assert report.summaries[0].average == 0.0


def test_one_run_or_a_later_miss_does_not_sign():
    one = [row for row in _clearing() if not (row.model == "Luna" and row.harness_on and row.run == 2)]
    assert judge_gate(one).signed is False
    slipped = _clearing() + _from_costs("Luna", True, 3, _first(3))
    assert judge_gate(slipped).signed is False


def test_harness_off_above_the_easy_line_throws_the_attempt_out():
    luna = judge_gate(_clearing(luna_off=_first(4)))
    assert luna.signed is False
    assert "luna" in luna.reason
    assert "easy" in luna.reason
    exact = judge_gate(_clearing(luna_off=_first(4, 0.25 / 0.35), astra_off=_exact_astra_line()))
    assert exact.signed is True
    astra = judge_gate(_clearing(astra_off=_first(7)))
    assert astra.signed is False
    assert "astra" in astra.reason


def test_missing_harness_off_log_cannot_sign():
    rows = [row for row in _clearing() if row.harness_on]
    report = judge_gate(rows)
    assert report.signed is False
    assert report.reason == "harness-off was not logged"


def test_a_tool_crash_is_not_filed_as_a_design_miss():
    task = next(item for item in load_tasks() if item.id == "holdup")
    hashed = task.card["spec_hash"]
    for detail in (
        "timeout",
        "no_measurement",
        "simulator_crash",
        "the proposal did not fit the design file: pins",
        "the part identity was unreadable: name",
    ):
        row = row_from_run(
            task,
            RunResult(status="stopped", spec_hash=hashed, detail=detail),
            model="none",
            harness_on=True,
            run=1,
            seconds=0.1,
        )
        assert row.miss_kind == "tool", detail
    for detail in ("the proposal dropped the load", "switch", "the hold-up capacitor is not connected"):
        row = row_from_run(
            task,
            RunResult(status="stopped", spec_hash=hashed, detail=detail),
            model="none",
            harness_on=True,
            run=1,
            seconds=0.1,
        )
        assert row.miss_kind == "design", detail


def test_an_unfrozen_sentence_cannot_be_marked_checked():
    task = next(item for item in load_tasks() if item.id == "divider")
    row = row_from_run(
        task,
        RunResult(status="checked", bom_usd=0.01, cost_usd=0.0),
        model="none",
        harness_on=True,
        run=1,
        seconds=0.1,
    )
    assert row.score == 0.0
    assert row.miss_kind == "design"


def test_a_changed_card_is_not_a_technical_pass():
    task = next(item for item in load_tasks() if item.id == "buck")
    result = RunResult(
        status="checked",
        spec_hash="not-the-card",
        bom_usd=0.5,
        cost_usd=0.02,
    )
    row = row_from_run(task, result, model="Luna", harness_on=True, run=1, seconds=1.2)
    assert row.score == 0.0
    assert row.miss_kind == "design"
    assert row.dollars == pytest.approx(0.02)


def test_learn_stays_uncalled(monkeypatch):
    called = []

    def spy():
        called.append("learn")
        raise AssertionError("learn was called")

    monkeypatch.setattr("extrude.learn.propose_offline", spy)
    monkeypatch.setattr("extrude.learn.api.propose_offline", spy)
    judge_gate([])
    judge_gate(_clearing())
    score(RunResult(status="checked", bom_usd=1.0, reference_bom_usd=1.0))
    assert called == []
    with pytest.raises(NotImplementedError):
        propose_offline()


def test_log_records_both_harness_modes(tmp_path):
    report = judge_gate(_clearing())
    path = tmp_path / "results.json"
    write_log(path, report)
    text = path.read_text(encoding="utf-8")
    assert '"harness_on": true' in text
    assert '"harness_on": false' in text
    assert '"model": "luna"' in text
    assert '"average"' in text
    assert '"dollars"' in text
    assert '"seconds"' in text


def test_saved_log_is_unsigned_and_names_the_unchecked_work():
    import json
    from pathlib import Path

    saved = json.loads((Path(__file__).resolve().parents[2] / "eval" / "proxy_tasks" / "results.json").read_text(encoding="utf-8"))
    assert saved["signed"] is False
    assert "heat-in-airflow" in saved["notice"]
    assert "radios" in saved["notice"]
    assert "fast memory" in saved["notice"]
    misses = {row["task_id"]: row["miss_kind"] for row in saved["rows"] if row["harness_on"]}
    assert misses["holdup"] == "tool"
    assert misses["buck"] == "tool"
    assert misses["regulator"] == "tool"
    assert misses["led"] == "request"
    assert misses["divider"] == "request"
    assert misses["pullup"] == "request"
    assert misses["series"] == "request"
    assert misses["indicator"] == "request"


def test_no_model_key_cannot_sign_the_gate():
    rows = []
    for task in load_tasks():
        from extrude.harness import run

        outcome = run(task.prompt)
        rows.append(row_from_run(task, outcome, model="none", harness_on=True, run=1, seconds=0.0))
        if task.card_kind == "needs_info":
            off = outcome
        else:
            with pytest.raises(ProposalError, match="no model key"):
                complete(task.prompt, "primary")
            off = RunResult(status="stopped", detail="no model key")
        rows.append(row_from_run(task, off, model="none", harness_on=False, run=1, seconds=0.0))
    report = judge_gate(rows)
    assert report.signed is False
    assert report.reason == "Luna and Astra were not both logged"
    kinds = {row.task_id: row.miss_kind for row in rows if row.harness_on}
    scores = {row.task_id: row.score for row in rows if row.harness_on}
    assert kinds["holdup"] == "tool"
    assert kinds["buck"] == "tool"
    assert kinds["regulator"] == "tool"
    assert kinds["led"] == "request"
    assert scores["buck"] == 0.0
    assert scores["led"] == 0.0
    assert scores["divider"] == 1.0
    assert kinds["divider"] is None


def _row(task_id: str, model: str, harness_on: bool, run: int, earned: float) -> ScoreRow:
    return ScoreRow(
        task_id=task_id,
        model=model,
        harness_on=harness_on,
        run=run,
        technical=1.0 if earned else 0.0,
        cost_efficiency=1.0 if earned else 0.0,
        score=earned,
        dollars=0.01,
        seconds=0.5,
    )


def _first(count: int, cost: float = 1.0) -> dict[str, float]:
    return {task.id: cost for task in list(load_tasks())[:count]}


def _exact_astra_line() -> dict[str, float]:
    tasks = list(load_tasks())
    costs = {task.id: 1.0 for task in tasks[:5]}
    costs[tasks[5].id] = 0.05 / 0.35
    costs[tasks[6].id] = 0.05 / 0.35
    return costs


def _from_costs(model: str, harness_on: bool, run: int, costs: dict[str, float]) -> list[ScoreRow]:
    rows = []
    for task in load_tasks():
        cost = costs.get(task.id)
        if cost is None:
            rows.append(_row(task.id, model, harness_on, run, 0.0))
            continue
        rows.append(
            ScoreRow(
                task_id=task.id,
                model=model,
                harness_on=harness_on,
                run=run,
                technical=1.0,
                cost_efficiency=cost,
                score=0.65 + (0.35 * cost),
                dollars=0.01,
                seconds=0.5,
            )
        )
    return rows


def _clearing(
    luna_off: dict[str, float] | None = None,
    astra_off: dict[str, float] | None = None,
) -> list[ScoreRow]:
    if luna_off is None:
        luna_off = {}
    if astra_off is None:
        astra_off = {}
    rows: list[ScoreRow] = []
    on = {"Luna": _first(4), "Astra": _first(6)}
    off = {"Luna": luna_off, "Astra": astra_off}
    for model in ("Luna", "Astra"):
        for run in (1, 2):
            rows.extend(_from_costs(model, True, run, on[model]))
            rows.extend(_from_costs(model, False, run, off[model]))
    return rows
