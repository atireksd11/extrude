"""Run 2D mechanical lift benchmark across frozen tasks."""

import argparse
import json
from pathlib import Path

from eval.mechanical_2d.lift import run_lift
from eval.mechanical_2d.spec_card import all_tasks, load_task

_HERE = Path(__file__).resolve().parent
_PRIMARY = ("mount_plate", "keyhole_slot", "gear_blank")
_LIFT_MIN = 5.0
_NEGATIVE_MAX = 2.0


def main() -> None:
    parser = argparse.ArgumentParser(prog="eval.mechanical_2d.run_lift")
    parser.add_argument("--task", action="append", help="task id (repeatable)")
    parser.add_argument("--all", action="store_true", help="run primary tasks plus simple_square control")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--fixture", action="store_true", default=True)
    parser.add_argument("--live", action="store_true", help="call Luna instead of frozen fixtures")
    args = parser.parse_args()

    if args.live:
        args.fixture = False

    task_ids = args.task or (list(_PRIMARY) + ["simple_square"] if args.all else list(_PRIMARY))
    summary = {"tasks": {}, "passed": True, "errors": []}
    for task_id in task_ids:
        if task_id not in all_tasks():
            raise SystemExit(f"unknown task: {task_id}")
        report = run_lift(load_task(task_id), runs=args.runs, fixture=args.fixture)
        (_HERE / f"results-{task_id}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        summary["tasks"][task_id] = report
        errors = list(report.get("lift_errors") or [])
        if errors:
            summary["passed"] = False
            summary["errors"].extend(errors)
        task = load_task(task_id)
        if task.negative_control:
            if report["lift_points"] > _NEGATIVE_MAX:
                summary["passed"] = False
                summary["errors"].append(f"{task_id}: negative control lift {report['lift_points']} > {_NEGATIVE_MAX}")
        elif report["lift_points"] < _LIFT_MIN:
            summary["passed"] = False
            summary["errors"].append(f"{task_id}: lift {report['lift_points']} < {_LIFT_MIN}")
        if report.get("parametric_collapse"):
            summary["passed"] = False
            summary["errors"].append(f"{task_id}: parametric_var_count collapsed >50%")
        if report.get("cost_usd", 0) > 0.30:
            summary["passed"] = False
            summary["errors"].append(f"{task_id}: spend cap exceeded")

    (_HERE / "results-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if not summary["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
