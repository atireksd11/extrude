"""Deterministic wall patch in the product repair stack."""

from extrude.harness.mechanical_repair import _patch_wall_thickness


def test_wall_thickness_is_bumped_to_the_card_limit():
    code = "hull() { cylinder(h = 1, r = 8); translate([80,0,0]) cylinder(h = 1, r = 8); }"
    patched = _patch_wall_thickness(code, 1.0, 2.0)
    assert "h = 2" in patched
    assert "h = 1" not in patched
