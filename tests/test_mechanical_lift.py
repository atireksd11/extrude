"""Phase 2 mechanical lift benchmark gates."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from eval.mechanical.lift import run_lift, stick_figure_loses
from eval.mechanical.spec_card import all_tasks, load_task
from extrude.eval.lift_report import validate_lift_report

_ROOT = Path(__file__).resolve().parents[1]
_PRIMARY = ("arm", "enclosure", "bracket")
_LIFT_MIN = 5.0
_NEGATIVE_MAX = 2.0


@pytest.fixture(scope="module")
def summary():
    reports = {}
    for task_id in _PRIMARY + ("simple_plate",):
        task = load_task(task_id)
        reports[task_id] = run_lift(
            task,
            runs=2,
            fixture=True,
            out_dir=task.task_dir() / "lift-runs",
        )
    return reports


def test_all_tasks_are_registered():
    assert set(_PRIMARY + ("simple_plate",)).issubset(set(all_tasks()))


@pytest.mark.parametrize("task_id", _PRIMARY)
def test_stick_figure_loses(task_id):
    task = load_task(task_id)
    assert stick_figure_loses(task, task.task_dir() / "canary-cache")


@pytest.mark.parametrize("task_id", _PRIMARY)
def test_fixture_lift_meets_minimum(summary, task_id):
    report = summary[task_id]
    assert report["lift_points"] >= _LIFT_MIN
    assert report["lift_from_repair"] > 0
    assert validate_lift_report(report) == []
    assert "percent" not in json.dumps(report) or "string" not in report.get("verifier_kind", "solid")


def test_negative_control_stays_near_zero(summary):
    report = summary["simple_plate"]
    assert report["lift_points"] <= _NEGATIVE_MAX


def test_quote_as_improvement_on_majority(summary):
    quoted = sum(1 for task_id in _PRIMARY if summary[task_id]["quote_as_improvement"])
    assert quoted >= 2


def test_parametric_var_count_does_not_collapse(summary):
    for task_id in _PRIMARY:
        report = summary[task_id]
        assert report["parametric_collapse"] is False


def test_checks_fixed_are_manufacturing_not_names(summary):
    for task_id in _PRIMARY:
        fixed = summary[task_id].get("checks_fixed") or []
        for item in fixed:
            assert item in {
                "insert_diameter",
                "joint_wall",
                "base_mounting_holes",
                "bbox_in_range",
                "min_bends",
                "compiles",
            }


def test_run_lift_cli_writes_summary(tmp_path):
    cmd = [
        sys.executable,
        "-m",
        "eval.mechanical.run_lift",
        "--all",
        "--runs",
        "2",
        "--fixture",
    ]
    subprocess.run(cmd, cwd=_ROOT, check=True, capture_output=True, text=True)
    path = _ROOT / "eval" / "mechanical" / "results-summary.json"
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert set(_PRIMARY).issubset(payload["tasks"])
