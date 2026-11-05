"""Standing serial arm kit must compile and look like an arm."""

from pathlib import Path

from extrude.harness.arm_kit import emit_articulated_arm, is_articulated_arm
from extrude.intake import resolve
from extrude.intake.models import FrozenSpec
from extrude.verify.solid import score_openscad_text, spec_from_frozen


def test_arm_kit_is_detected():
    assert is_articulated_arm("desktop robotic arm with a gripper")
    assert not is_articulated_arm("Make a 20mm cube in OpenSCAD")


def test_arm_kit_passes_solid_checks(tmp_path: Path):
    resolved = resolve(
        "Build a desktop robotic arm in OpenSCAD with 3 links and a gripper. "
        "PETG base with 4 M3 inserts. 2mm joint walls."
    )
    assert isinstance(resolved, FrozenSpec)
    verify = spec_from_frozen(resolved, "PETG")
    code = emit_articulated_arm(verify)
    score = score_openscad_text(code, verify, tmp_path / "kit")
    assert score["checks"].get("compiles")
    assert score["checks"].get("three_links")
    assert score["checks"].get("two_fingers")
    assert score["checks"].get("more_than_one_bend")
    assert score["percent"] >= 85
    png = (score.get("render") or {}).get("png")
    assert png and Path(png).is_file()
