"""The solid score does not grade names, and a locked feature cannot be deleted."""

import os
import shutil
from pathlib import Path

import pytest

from eval.arm_benchmark.causes import classify_miss, store_miss
from eval.arm_benchmark.spec_card import load_spec
from eval.arm_benchmark.solid_score import score_solid
from extrude.copilot.fix_loop import locks_held, render_locks
from extrude.memory.db import load_prompt_notes, load_violations
from extrude.memory.models import PrimaryCause
from extrude.parse.openscad import parse_openscad

_ROOT = Path(__file__).resolve().parents[1] / "eval" / "arm_benchmark"


def test_the_repair_prompt_names_the_measurement_and_not_a_module():
    from eval.arm_benchmark.run_solid import repair_prompt

    text = repair_prompt(
        "color([1,0,0]) cylinder(h=8, r=3.2);",
        "base hole diameter is 6.4 mm. PETG M3 inserts must be between 4.05 and 4.35 mm.",
        [{"feature": "colors", "status": "PASS"}],
    )
    assert "MUST_FIX:" in text
    assert "DO_NOT_BREAK: colors" in text
    assert "link1" not in text


def test_a_bend_about_y_counts():
    from eval.arm_benchmark.csg_read import read_csg

    text = """
    multmatrix([[0.906, 0, 0.423, 0], [0, 1, 0, 0], [-0.423, 0, 0.906, 10]]) { cylinder(h = 40, r1 = 8, r2 = 8); }
    multmatrix([[0.819, 0, -0.574, 20], [0, 1, 0, 0], [0.574, 0, 0.819, 10]]) { cylinder(h = 40, r1 = 8, r2 = 8); }
    """
    assert read_csg(text)["bends"] >= 2


def test_the_shared_card_does_not_name_modules():
    text = load_spec().prompt()
    assert "link1" not in text
    assert "module" not in text
    assert "M3" in text
    assert "PETG" in text


def test_a_variable_radius_is_4_point_2_mm():
    design = parse_openscad("hole_r = 2.1;\ncylinder(h=8, r=hole_r * 1);\n")
    assert design.holes[0].diameter_mm == 4.2
    assert design.warnings == []


def test_deleting_color_breaks_the_lock():
    before = "color([1, 0, 0]) rotate([0, 0, 25]) cylinder(h=10, r=4);"
    after = "cube([10, 10, 10]);"
    assert "colors" in {item["feature"] for item in render_locks(before)}
    assert locks_held(before, before) is True
    assert locks_held(before, after) is False


def test_a_spec_hole_is_not_a_ban_and_a_crash_is_not_a_retry(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    store_miss(
        cause=classify_miss(check_id="insert_diameter", spec_on_card=False, tool_failed=False),
        prompt="an arm",
        check_id="insert_diameter",
        detail="the prompt never asked for an insert",
        feature_ref="base",
        measured=6.4,
        limit=4.2,
        spec_hash="abc",
    )
    store_miss(
        cause=PrimaryCause.tooling,
        prompt="an arm",
        check_id="compile",
        detail="openscad failed",
        feature_ref="file",
        measured=0,
        limit=0,
        spec_hash="abc",
    )
    store_miss(
        cause=classify_miss(check_id="insert_diameter", spec_on_card=True, tool_failed=False),
        prompt="an arm with M3 inserts",
        check_id="insert_diameter",
        detail="base hole diameter is 6.4 mm",
        feature_ref="base_insert",
        measured=6.4,
        limit=4.05,
        spec_hash="abc",
    )
    assert load_violations()[0]["feature_ref"] == "base_insert"
    assert len(load_violations()) == 1
    assert load_prompt_notes()[0]["check_id"] == "insert_diameter"


@pytest.mark.skipif(shutil.which("openscad") is None and not os.environ.get("OPENSCAD_PATH"), reason="openscad is not installed")
def test_the_colored_arm_outranks_the_blue_arm(tmp_path):
    spec = load_spec().shape_only()
    off = score_solid(_ROOT / "off.scad", spec, tmp_path / "off")
    on = score_solid(_ROOT / "on.scad", spec, tmp_path / "on")
    assert off["checks"]["compiles"] is True
    assert on["checks"]["compiles"] is True
    assert off["percent"] > on["percent"]
