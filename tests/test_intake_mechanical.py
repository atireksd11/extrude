"""Mechanical intake fields freeze from the sentence."""

from extrude.intake import resolve
from extrude.intake.mechanical import parse_mechanical


def test_parse_mechanical_reads_petg_m3_and_wall():
    parsed = parse_mechanical(
        "Build a desktop robotic arm in OpenSCAD with 3 links. PETG base with 4 M3 inserts. 2mm joint walls."
    )
    assert parsed["material"] == "PETG"
    assert parsed["insert"] == "M3"
    assert parsed["insert_count"] == 4
    assert parsed["min_wall_mm"] == 2.0
    assert parsed["insert_min_mm"] == 4.05
    assert parsed["insert_max_mm"] == 4.35


def test_freeze_mechanical_stores_labels_and_values():
    resolved = resolve(
        "Build a desktop robotic arm in OpenSCAD with 3 links and a gripper. "
        "PETG base with 4 M3 inserts. 2mm joint walls."
    )
    assert resolved.task_class == "mechanical_3d"
    assert resolved.labels["material"] == "PETG"
    assert resolved.labels["insert"] == "M3"
    assert resolved.values_si["insert_count"] == 4
    assert resolved.values_si["min_wall_mm"] == 2.0
