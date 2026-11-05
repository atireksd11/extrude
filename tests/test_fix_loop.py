"""OpenSCAD repair. No model call."""

from pathlib import Path

from extrude.copilot.fix_loop import repair_openscad
from extrude.memory.db import load_violations

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "parse" / "enclosure.scad"


def test_a_small_m3_hole_is_repaired_on_the_second_try(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    text = _FIXTURE.read_text(encoding="utf-8")
    result = repair_openscad(text, "PETG", prompt="M3 PETG enclosure")
    assert result.status == "checked"
    assert result.attempts == 2
    assert "d=4.2" in result.code
    assert "r=2.6" in result.code
    assert any(item["feature"] == "hole_2" for item in result.locked)
    assert result.violations
    rows = load_violations()
    assert len(rows) == 1
    assert rows[0]["check_id"] == "hole_undersized_for_insert"
    assert rows[0]["feature_ref"] == "hole_1"


def test_a_good_hole_stays_put_while_the_bad_hole_and_wall_are_fixed(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    text = """
// M4
cylinder(h=8, r=2.6);
// M2
cylinder(8, 1.6);
// extrude-wall rib 0.8 1.0
"""
    result = repair_openscad(text, "PETG", prompt="two holes and a thin wall")
    assert result.status == "checked"
    assert result.attempts == 2
    assert "r=2.6" in result.code
    assert "cylinder(8, 1.7)" in result.code
    assert "extrude-wall rib 2" in result.code
    assert any(item["feature"] == "hole_1" and item["status"] == "PASS" for item in result.locked)
    rows = load_violations()
    assert "hole_2" in {row["feature_ref"] for row in rows}
    assert len(rows) == 1
