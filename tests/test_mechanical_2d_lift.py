"""Phase 3 2D mechanical lift benchmark gates."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from eval.mechanical_2d.lift import run_lift, stick_figure_loses
from eval.mechanical_2d.spec_card import all_tasks, load_task
from extrude.eval.lift_report import validate_lift_report

_ROOT = Path(__file__).resolve().parents[1]
_PRIMARY = ("mount_plate", "keyhole_slot", "gear_blank")
_LIFT_MIN = 5.0
_NEGATIVE_MAX = 2.0


@pytest.fixture(scope="module")
def openscad_ready():
    from extrude.render.openscad import _executable

    if _executable() is None:
        pytest.skip("OpenSCAD not installed")
    return True


@pytest.fixture(scope="module")
def summary(openscad_ready):
    reports = {}
    for task_id in _PRIMARY + ("simple_square",):
        task = load_task(task_id)
        reports[task_id] = run_lift(
            task,
            runs=2,
            fixture=True,
            out_dir=task.task_dir() / "lift-runs",
        )
    return reports


def test_all_tasks_are_registered():
    assert set(_PRIMARY + ("simple_square",)).issubset(set(all_tasks()))


@pytest.mark.parametrize("task_id", _PRIMARY)
def test_stick_figure_loses(task_id, openscad_ready):
    task = load_task(task_id)
    assert stick_figure_loses(task, task.task_dir() / "canary-cache")


@pytest.mark.parametrize("task_id", _PRIMARY)
def test_fixture_lift_meets_minimum(summary, task_id):
    report = summary[task_id]
    assert report["lift_points"] >= _LIFT_MIN
    assert report["lift_from_repair"] > 0
    assert validate_lift_report(report) == []
    assert report["verifier_kind"] == "svg"


def test_negative_control_stays_near_zero(summary):
    report = summary["simple_square"]
    assert report["lift_points"] <= _NEGATIVE_MAX


def test_quote_as_improvement_on_majority(summary):
    quoted = sum(1 for task_id in _PRIMARY if summary[task_id]["quote_as_improvement"])
    assert quoted >= 2


def test_checks_fixed_are_geometry_not_names(summary):
    for task_id in _PRIMARY:
        fixed = summary[task_id].get("checks_fixed") or []
        for item in fixed:
            assert item in {
                "hole_diameter",
                "hole_count",
                "hole_positions",
                "outline_size",
                "min_edge_distance",
                "closed_outline",
                "compiles",
            }


def test_run_lift_cli_writes_summary(openscad_ready):
    cmd = [
        sys.executable,
        "-m",
        "eval.mechanical_2d.run_lift",
        "--all",
        "--runs",
        "2",
        "--fixture",
    ]
    subprocess.run(cmd, cwd=_ROOT, check=True, capture_output=True, text=True)
    path = _ROOT / "eval" / "mechanical_2d" / "results-summary.json"
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert set(_PRIMARY).issubset(payload["tasks"])
