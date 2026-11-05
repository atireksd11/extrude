"""Checks on the card only. Off-card predicates do not run."""

from extrude.intake import resolve
from extrude.verify.solid import checks_for_card, spec_from_frozen


def test_insert_only_card_does_not_require_three_links():
    resolved = resolve("Print a PETG bracket with 4 M3 heat-set inserts and 2mm walls.")
    checks = checks_for_card(resolved)
    assert "insert_diameter" in checks
    assert "joint_wall" in checks
    assert "three_links" not in checks
    assert "two_fingers" not in checks


def test_arm_sentence_keeps_shape_checks():
    resolved = resolve(
        "Build a desktop robotic arm in OpenSCAD with 3 links and a gripper. "
        "PETG base with 4 M3 inserts. 2mm joint walls."
    )
    checks = checks_for_card(resolved)
    assert "three_links" in checks
    assert "two_fingers" in checks
    assert "insert_diameter" in checks


def test_bbox_on_card_adds_bbox_check():
    resolved = resolve("PETG enclosure 100mm max bounding box with 2mm walls.")
    verify = spec_from_frozen(resolved, "PETG")
    assert "bbox_max" in verify.checks or resolved.values_si.get("bbox_max_mm") is None
