"""CAD text parsers. No CAD binary and no model."""

from pathlib import Path

from extrude.parse.featurescript import parse_featurescript
from extrude.parse.openscad import parse_openscad
from extrude.parse.sniff import sniff

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "parse"


def test_the_enclosure_fixture_reads_two_holes_and_a_wall():
    text = (_FIXTURES / "enclosure.scad").read_text(encoding="utf-8")
    design = parse_openscad(text)
    assert design.source == "openscad"
    assert design.bounds_mm == (40.0, 30.0, 8.0)
    assert [hole.diameter_mm for hole in design.holes] == [3.5, 5.2]
    assert [hole.intended_insert for hole in design.holes] == ["M3", "M4"]
    assert design.holes[0].position_mm == (10.0, 10.0, 0.0)
    assert design.walls[0].name == "side"
    assert design.walls[0].thickness_mm == 2.0


def test_featurescript_reads_a_circle_and_warns_on_fillet():
    text = (_FIXTURES / "bracket.fs").read_text(encoding="utf-8")
    design = parse_featurescript(text)
    assert design.holes[0].diameter_mm == 4.2
    assert design.holes[0].intended_insert == "M3"
    assert design.walls[0].normal_z == 0.2
    assert "unsupported:opFillet" in design.warnings


def test_a_later_hole_does_not_inherit_the_earlier_one():
    text = """
translate([1, 2, 3]) cylinder(h=8, d=3.2); // M2
cylinder(8, 2.1); // M3
cylinder(h=8, d=3.5mm); cylinder(h=4, r=2.6);
cube([40, 30, 8], center=true);
"""
    design = parse_openscad(text)
    assert design.bounds_mm == (40.0, 30.0, 8.0)
    assert [hole.position_mm for hole in design.holes] == [
        (1.0, 2.0, 3.0),
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0),
    ]
    assert [hole.diameter_mm for hole in design.holes] == [3.2, 4.2, 3.5, 5.2]
    assert [hole.intended_insert for hole in design.holes] == ["M2", "M3", None, None]
    assert design.holes[1].depth_mm == 8


def test_a_circle_literal_is_a_radius_and_a_named_diameter_is_not():
    text = """
const center = 1 * millimeter;
const holeDia = 4.2 * millimeter;
// M3
skCircle(center, holeDia);
skCircle(center, 2.1 * millimeter);
const radius = 2.0 * millimeter;
skCircle(center, radius);
"""
    design = parse_featurescript(text)
    assert [hole.diameter_mm for hole in design.holes] == [4.2, 4.2, 4.0]
    assert design.holes[0].intended_insert == "M3"
    assert design.holes[1].intended_insert is None


def test_a_named_radius_is_still_a_diameter():
    design = parse_openscad("hole_r = 2.1;\ncylinder(h=8, r=hole_r);\n")
    assert design.warnings == []
    assert design.holes[0].diameter_mm == 4.2


def test_sniff_uses_the_file_name_and_the_text():
    assert sniff(filename="box.scad", content="cube([1,1,1]);") == "openscad"
    assert sniff(filename="part.fs", content="cylinder(h=1, d=1);") == "featurescript"
    assert sniff(filename="board.net", content="(export (version E))") == "netlist"
    assert sniff(filename=None, content="https://cad.onshape.com/documents/abc") == "onshape"
    assert sniff(filename=None, content="tie the pin to (net GND)") == "circuit"
    assert sniff(filename=None, content="5 V to 3.3 V buck") == "circuit"
    assert sniff(filename=None, content="") == "empty"
