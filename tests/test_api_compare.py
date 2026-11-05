"""Design studio compare API."""

from extrude.api.compare import CompareRequest, run_compare


def test_compare_offline_cube():
    result = run_compare(CompareRequest(text="Make a 20mm cube in OpenSCAD", offline=True))
    assert result.domain == "mechanical"
    assert result.raw.code is not None
    assert result.harness.code is not None
    assert result.raw.percent is not None


def test_compare_offline_2d_plate():
    result = run_compare(
        CompareRequest(
            text="Laser-cut an 80x60 mm acrylic mounting plate with 4 M3 clearance holes",
            offline=True,
        )
    )
    assert result.task_class == "mechanical_2d"
    assert result.lift_points is not None
    assert result.harness.percent >= result.raw.percent
    assert result.harness_edited or result.harness.percent > result.raw.percent


def test_compare_offline_arm_shows_harness_lift():
    result = run_compare(
        CompareRequest(
            text="Build a desktop robotic arm in OpenSCAD with 3 links and a gripper. PETG base with 4 M3 inserts. 2mm joint walls.",
            offline=True,
        )
    )
    assert result.task_class == "mechanical_3d"
    assert result.harness_edited
    assert (result.harness.percent or 0) > (result.raw.percent or 0)
    assert result.raw.preview_url
    assert result.harness.preview_url
    assert "robot_arm" in (result.harness.code or "")
    assert "jaw_pair" in (result.harness.code or "")


def test_sentence_in_file_box_generates_instead_of_instant_audit():
    result = run_compare(
        CompareRequest(
            text="Make a 20mm cube in OpenSCAD",
            artifact="Build a desktop robotic arm in OpenSCAD with 3 links and a gripper. PETG base with 4 M3 inserts. 2mm joint walls.",
            filename="part.scad",
            offline=True,
        )
    )
    assert result.mode == "generate"
    assert result.seconds >= 0
    assert "cube(" in (result.raw.code or "")
    assert result.raw.preview_url
    assert result.raw.checks[0].id != "parsed"


def test_compare_passive_divider():
    result = run_compare(CompareRequest(text="10k/10k divider 5 V to 3.3 V", offline=True))
    assert result.domain == "electrical"
    assert result.raw.netlist is not None
