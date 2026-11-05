"""Cause split before memory writes."""

from extrude.harness.causes import classify_miss, effective_cause, store_miss
from extrude.harness import run
from extrude.memory import reset
from extrude.memory.db import load_prompt_notes, load_violations, load_telemetry
from extrude.memory.models import PrimaryCause


def setup_function() -> None:
    reset()


def test_tooling_miss():
    assert classify_miss(check_id="compile", spec_on_card=True, tool_failed=True) is PrimaryCause.tooling


def test_spec_gap_when_check_not_on_card():
    assert classify_miss(check_id="insert_diameter", spec_on_card=False, tool_failed=False) is PrimaryCause.spec_gap


def test_model_design_when_spec_frozen():
    assert (
        classify_miss(check_id="insert_diameter", spec_on_card=True, tool_failed=False)
        is PrimaryCause.model_design
    )


def test_unconfirmed_spec_becomes_gap():
    cause = effective_cause(PrimaryCause.model_design, spec_confirmed=False)
    assert cause is PrimaryCause.spec_gap


def test_spec_gap_writes_prompt_note_not_violation(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    store_miss(
        cause=PrimaryCause.spec_gap,
        prompt="arm without insert spec",
        check_id="insert_diameter",
        detail="insert diameter was not on the card",
        feature_ref="base_insert",
        measured=6.4,
        limit=4.05,
        spec_hash="abc",
    )
    assert len(load_violations()) == 0
    assert load_prompt_notes()[0]["check_id"] == "insert_diameter"


def test_tooling_writes_telemetry_not_violation(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    store_miss(
        cause=PrimaryCause.tooling,
        prompt="arm",
        check_id="openscad_compile",
        detail="openscad binary missing",
        feature_ref="tooling",
        measured=0,
        limit=0,
        spec_hash="abc",
    )
    assert len(load_violations()) == 0
    assert load_telemetry()[0]["status"] == "tooling"


def test_mechanical_generate_reports_tooling_when_openscad_missing(monkeypatch):
    monkeypatch.setattr("extrude.tools.tool_available", lambda _name: False)
    result = run(
        "Build a desktop robotic arm in OpenSCAD in PETG with three links, "
        "a gripper, and 4 M3 heat-set inserts."
    )
    assert result.status == "stopped"
    assert (result.detail or "").startswith("tooling:")
