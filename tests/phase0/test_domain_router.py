"""Domain routing for mechanical and electrical generate paths."""

from extrude.copilot.router import route
from extrude.intake.classify import classify
from extrude.intake import resolve
from extrude.intake.models import NeedsInfo


def test_robotic_arm_routes_to_mechanical_3d():
    text = "Build a robotic arm in OpenSCAD with three links and a gripper"
    assert classify(text) == "mechanical_3d"
    decision = route(text=text, filename=None, content=None)
    assert decision.mode == "generate"
    assert decision.artifact_kind == "mechanical_3d"


def test_divider_stays_electrical():
    text = "10k/10k divider 5 V to 3.3 V"
    assert classify(text) == "divider"
    decision = route(text=text, filename=None, content=None)
    assert decision.artifact_kind == "circuit"


def test_laser_plate_routes_to_mechanical_2d():
    text = "laser-cut mounting plate 80x60 with 4 M3 holes"
    assert classify(text) == "mechanical_2d"
    decision = route(text=text, filename=None, content=None)
    assert decision.artifact_kind == "mechanical_2d"


def test_regulator_bracket_is_ambiguous():
    text = "mount a regulator bracket in PETG"
    assert classify(text) == "ambiguous"
    resolved = resolve(text)
    assert isinstance(resolved, NeedsInfo)
    assert "3D" in resolved.question or "3d" in resolved.question


def test_mechanical_freeze_asks_filament_when_inserts_named():
    text = "OpenSCAD enclosure with 4 M3 heat-set inserts"
    resolved = resolve(text)
    assert isinstance(resolved, NeedsInfo)
    assert "filament" in resolved.missing
