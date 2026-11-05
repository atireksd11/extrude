"""Phase 0 acceptance checklist — must stay green before Phase 1."""

import json
from pathlib import Path

import pytest

from extrude.copilot.router import route
from extrude.eval.lift_report import validate_lift_report
from extrude.eval.tasks import load_tasks
from extrude.intake.classify import classify

_ROOT = Path(__file__).resolve().parents[2]
_BASELINE = _ROOT / "eval" / "proxy_tasks" / "results-baseline.json"


def test_baseline_snapshot_exists():
    assert _BASELINE.is_file(), "run: python -m eval.snapshot_baseline"
    payload = json.loads(_BASELINE.read_text(encoding="utf-8"))
    assert payload["phase"] == 0
    assert payload["task_count"] == 8


def test_cad_sentence_never_routes_to_circuit():
    text = "Build a robotic arm in OpenSCAD with three links"
    assert classify(text) == "mechanical_3d"
    decision = route(text=text, filename=None, content=None)
    assert decision.artifact_kind != "circuit"


def test_frozen_eight_cards_still_resolve():
    for task in load_tasks():
        if task.card_kind == "needs_info":
            continue
        from extrude.intake import resolve

        resolved = resolve(task.prompt)
        assert resolved.model_dump(mode="json") == task.card


def test_repair_results_use_solid_verifier():
    path = _ROOT / "eval" / "arm_benchmark" / "results-repair.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("quote_as_improvement"):
        report["verifier_kind"] = report.get("verifier_kind") or "solid"
    assert validate_lift_report(report) == []
