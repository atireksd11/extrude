"""Lift reports must not quote string-rubric wins."""

import json
from pathlib import Path

import pytest

from extrude.eval.lift_report import assert_lift_report_valid, validate_lift_report

_ROOT = Path(__file__).resolve().parents[1]


def test_solid_repair_report_is_valid():
    report = json.loads((_ROOT / "tests/fixtures/reports/solid-repair.json").read_text(encoding="utf-8"))
    report["verifier_kind"] = "solid"
    assert validate_lift_report(report) == []


def test_string_rubric_lift_is_rejected():
    report = {
        "verifier_kind": "string",
        "quote_as_improvement": True,
        "lift_points": 40,
        "rubric": "string",
    }
    errors = validate_lift_report(report)
    assert errors
    with pytest.raises(ValueError):
        assert_lift_report_valid(report)


def test_unlabeled_positive_lift_is_rejected():
    report = {"quote_as_improvement": True, "lift_points": 5, "raw": {"checks": {}}}
    assert validate_lift_report(report)


def test_legacy_results_json_without_quote_flag_passes():
    report = json.loads((_ROOT / "tests/fixtures/reports/legacy.json").read_text(encoding="utf-8"))
    assert validate_lift_report(report) == []
