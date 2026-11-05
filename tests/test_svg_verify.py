"""SVG verifier unit gates."""

from pathlib import Path

import pytest

from eval.mechanical_2d.spec_card import load_task
from extrude.intake import resolve
from extrude.intake.mechanical_2d import parse_mechanical_2d
from extrude.parse.svg_read import read_svg_file
from extrude.verify.svg import score_openscad_2d, spec_from_frozen_2d

_ROOT = Path(__file__).resolve().parents[1]
_PROBE = _ROOT / "data" / "phase3-probe" / "plate.scad"


@pytest.fixture(scope="module")
def openscad_ready():
    from extrude.render.openscad import _executable

    if _executable() is None:
        pytest.skip("OpenSCAD not installed")
    return True


def test_parse_mechanical_2d_reads_plate_and_holes():
    parsed = parse_mechanical_2d("Laser-cut mounting plate 80x60 with 4 M3 holes")
    assert parsed["plate_width_mm"] == 80
    assert parsed["plate_height_mm"] == 60
    assert parsed["hole"] == "M3"
    assert parsed["hole_count"] == 4
    assert parsed["hole_min_mm"] == 2.95
    assert parsed["hole_max_mm"] == 3.45


def test_freeze_2d_does_not_ask_for_filament():
    resolved = resolve("Laser-cut mounting plate 80x60 with 4 M3 holes")
    assert resolved.task_class == "mechanical_2d"
    assert resolved.values_si["plate_width_mm"] == 80
    assert resolved.labels["hole"] == "M3"


def test_read_svg_finds_holes(openscad_ready):
    task = load_task("mount_plate")
    score = score_openscad_2d(task.task_dir() / "harness.scad", task.to_verify(), task.task_dir() / "svg-test")
    facts = score["facts"]
    assert score["checks"]["compiles"]
    assert len(facts["holes"]) == 4


def test_off_fixture_misses_hole_diameter(openscad_ready):
    task = load_task("mount_plate")
    score = score_openscad_2d(task.task_dir() / "off.scad", task.to_verify(), task.task_dir() / "off-test")
    assert score["checks"]["hole_diameter"] is False
    assert score["percent"] < 100


def test_harness_fixture_passes_mount_plate(openscad_ready):
    task = load_task("mount_plate")
    score = score_openscad_2d(task.task_dir() / "harness.scad", task.to_verify(), task.task_dir() / "pass-test")
    assert score["percent"] == 100.0
    assert score["misses"] == []


def test_hole_positions_within_tolerance(openscad_ready):
    task = load_task("mount_plate")
    score = score_openscad_2d(task.task_dir() / "harness.scad", task.to_verify(), task.task_dir() / "pos-test")
    assert score["checks"]["hole_positions"] is True


def test_probe_plate_svg_parser(openscad_ready):
    if not _PROBE.is_file():
        pytest.skip("probe scad missing")
    from extrude.render.openscad import render_2d

    out = _ROOT / "data" / "phase3-probe" / "parser-test"
    rendered = render_2d(_PROBE, out, "plate")
    assert rendered.status == "checked"
    facts = read_svg_file(Path(rendered.svg))
    assert abs(facts.width_mm - 80) < 1.0
    assert len(facts.holes) == 4


def test_spec_from_frozen_2d_enables_card_checks():
    resolved = resolve("Laser-cut mounting plate 80x60 with 4 M3 holes")
    verify = spec_from_frozen_2d(resolved)
    assert "hole_diameter" in verify.checks
    assert verify.hole_count == 4
