"""The arm score does not call a model."""

from eval.arm_benchmark.score import score_arm

_GOOD = """
module base() { cube([80, 60, 8]); }
module link1() { cylinder(h=90, d=20); }
module link2() { cylinder(h=80, d=18); }
module link3() { cylinder(h=70, d=16); }
module joint1() { cylinder(h=12, d=30); }
module joint2() { cylinder(h=12, d=28); }
module joint3() { cylinder(h=12, d=26); }
module gripper() {
  translate([0, 10, 0]) cube([8, 8, 40]); // finger
  translate([0, -10, 0]) cube([8, 8, 40]); // finger
}
translate([0, 0, 0]) base();
translate([0, 0, 20]) joint1();
translate([0, 0, 40]) link1();
"""

_BARE = "I cannot build a robotic arm."


def test_a_named_arm_scores_higher_than_a_refusal():
    good = score_arm(_GOOD)
    bare = score_arm(_BARE)
    assert good["percent"] > bare["percent"]
    assert good["checks"]["three_links"] is True
    assert good["checks"]["gripper_two_fingers"] is True
    assert bare["checks"]["openscad_geometry"] is False
    assert bare["percent"] == 0
