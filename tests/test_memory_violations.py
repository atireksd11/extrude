"""SQLite violation log. No model, no network."""

import json

import pytest
from pydantic import ValidationError

from extrude.memory.db import insert_violation, load_violations
from extrude.memory.rag import retrieve_violations


def _row(**overrides):
    base = dict(
        domain="mechanical",
        artifact_kind="openscad",
        spec_hash="hole-1",
        prompt="M3 PETG enclosure",
        check_id="hole_undersized_for_insert",
        detail="M3 hole was 3.5 mm",
        feature_ref="M3_mount_1",
        filament="PETG",
        printer_profile="generic",
        measured=3.5,
        limit=4.2,
        error_trace_json=json.dumps({"rule_id": "hole_undersized_for_insert"}),
        checker_version="2026-10-04",
    )
    base.update(overrides)
    return base


def test_a_violation_is_stored_and_a_duplicate_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    assert insert_violation(**_row()) is True
    assert insert_violation(**_row()) is False
    rows = load_violations()
    assert len(rows) == 1
    assert rows[0]["feature_ref"] == "M3_mount_1"
    assert rows[0]["filament"] == "PETG"
    assert json.loads(rows[0]["error_trace_json"])["rule_id"] == "hole_undersized_for_insert"


def test_the_same_hole_on_a_different_filament_is_a_new_row(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    insert_violation(**_row())
    assert insert_violation(**_row(filament="PLA", limit=4.0)) is True
    assert len(load_violations()) == 2


def test_retrieval_returns_the_matching_domain_only(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    insert_violation(**_row())
    insert_violation(
        **_row(
            domain="electrical",
            artifact_kind="netlist",
            spec_hash="pin-1",
            prompt="floating reset",
            check_id="control_pin_floating",
            detail="U1.NRST is open",
            feature_ref="U1.NRST",
            filament=None,
            measured=0,
            limit=1,
        )
    )
    found = retrieve_violations("Mechanical", "M3 PETG enclosure", "hole-1")
    assert len(found) == 1
    assert found[0].check_id == "hole_undersized_for_insert"
    assert found[0].identity.filament == "PETG"
    assert found[0].identity.printer_profile == "generic"
    pins = retrieve_violations("electrical", "floating reset", "pin-1")
    assert len(pins) == 1
    assert pins[0].identity.feature_ref == "U1.NRST"


def test_no_database_means_nothing_is_written(monkeypatch):
    monkeypatch.delenv("EXTRUDE_MEMORY_DB", raising=False)
    assert insert_violation(**_row()) is False
    assert load_violations() == []


def test_filament_case_and_domain_do_not_collapse_different_misses(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    assert insert_violation(**_row(filament="petg")) is True
    assert insert_violation(**_row(filament=" PETG ")) is False
    assert insert_violation(
        **_row(domain="electrical", artifact_kind="netlist", filament=None, feature_ref="M3_mount_1")
    ) is True
    assert insert_violation(**_row(feature_ref="M3_mount_2")) is True
    assert len(load_violations()) == 3


def test_retrieval_keeps_the_three_closest_and_drops_the_rest(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    rows = [
        ("a", "zzzz qqqq", "hole-1"),
        ("b", "PETG enclosure mount plate", "hole-1"),
        ("c", "PETG only", "hole-1"),
        ("d", "enclosure mount", "hole-1"),
        ("e", "PETG enclosure mount plate", "other-board"),
    ]
    for feature, prompt, spec in rows:
        insert_violation(**_row(feature_ref=feature, prompt=prompt, spec_hash=spec, detail=prompt))
    insert_violation(
        **_row(
            domain="electrical",
            artifact_kind="netlist",
            feature_ref="U1.NRST",
            prompt="PETG enclosure mount plate",
            spec_hash="hole-1",
            filament=None,
            detail="pin",
        )
    )
    found = retrieve_violations("mechanical", "M3 PETG enclosure mount", "hole-1")
    assert [item.identity.feature_ref for item in found] == ["b", "d", "c"]


def test_a_bad_trace_or_an_empty_feature_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    with pytest.raises(ValidationError):
        insert_violation(**_row(error_trace_json="not json"))
    with pytest.raises(ValidationError):
        insert_violation(**_row(feature_ref="  "))
    with pytest.raises(ValidationError):
        insert_violation(**_row(domain="thermal"))
    assert load_violations() == []
