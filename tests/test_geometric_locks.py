"""Geometric locks re-measure CSG facts, not substrings."""

from extrude.copilot.fix_loop import locks_held, locks_held_facts, render_locks


def test_deleting_color_breaks_the_geometric_lock():
    before = {
        "colors": [(1.0, 0.0, 0.0)],
        "color_count": 1,
        "links": 3,
        "bends": 2,
        "holes": [4.2, 4.2, 4.2, 4.2],
    }
    after = {"colors": [], "color_count": 0, "links": 3, "bends": 2, "holes": [4.2, 4.2, 4.2, 4.2]}
    locks = render_locks("", before)
    assert locks_held_facts(before, after, locks) is False


def test_hull_string_without_links_fails_the_lock():
    before = {"colors": [(1, 0, 0)], "color_count": 1, "links": 3, "bends": 2, "holes": [4.2]}
    after = {"colors": [(1, 0, 0)], "color_count": 1, "links": 0, "bends": 2, "holes": [4.2]}
    locks = render_locks("hull() difference()", before)
    assert locks_held("hull() difference()", "hull() difference()", before, after) is False


def test_substring_hull_without_rendered_links_falls_back_and_fails_when_links_drop():
    before_code = "color([1,0,0]) hull() { cylinder(h=40, r=8); } rotate([0,25,0]) cylinder(h=40, r=8);"
    after_code = "color([1,0,0]) hull(); cube([10,10,10]);"
    assert locks_held(before_code, after_code) is False


def test_insert_repair_keeps_shape_counts():
    before = {"colors": [(1, 0, 0), (0, 1, 0)], "color_count": 2, "links": 3, "bends": 3, "holes": [6.4]}
    after = {"colors": [(1, 0, 0), (0, 1, 0)], "color_count": 2, "links": 3, "bends": 3, "holes": [4.2]}
    locks = render_locks("", before)
    assert locks_held_facts(before, after, locks) is True
