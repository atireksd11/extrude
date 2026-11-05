"""Domain flags for routing. Ambiguous sentences stop with one question."""

import re

_ELECTRICAL = (
    "buck",
    "step-down",
    "step down",
    "ldo",
    "linear regulator",
    "hold-up",
    "hold up",
    "holdup",
    "divider",
    "pull-up",
    "pullup",
    "i2c",
    "netlist",
    "schematic",
    "capacitor",
    "resistor",
    "inductor",
    "kicad",
    "ngspice",
    "v to ",
    " v ",
    "volt",
    "amp",
    "ma ",
    "led",
    "regulator",
)

_MECH_3D = (
    "openscad",
    "3d model",
    "3d print",
    "robotic arm",
    "robot arm",
    "enclosure",
    "bracket",
    "petg",
    "pla ",
    "heat-set",
    "heat set",
    "millimeter",
    " mm",
    "linear_extrude",
    "hull(",
    "cube(",
    "cylinder(",
)

_MECH_2D = (
    "laser-cut",
    "laser cut",
    "lasercut",
    "dxf",
    "svg",
    "2d profile",
    "2d plate",
    "mounting plate",
    "hole pattern",
    "flat pattern",
    "outline",
    "pcd",
)

_AMBIGUOUS_QUESTION = (
    "Is this a 3D print, a 2D flat plate, or an electrical circuit? "
    "Reply with one word: 3d, 2d, or circuit."
)


def domain_flags(text: str) -> tuple[bool, bool, bool]:
    lowered = text.lower()
    electrical = any(token in lowered for token in _ELECTRICAL)
    mech_3d = any(token in lowered for token in _MECH_3D)
    mech_2d = any(token in lowered for token in _MECH_2D)
    if re.search(r"\bregulator\b", lowered) and re.search(r"\b(bracket|plate|mount|print)\b", lowered):
        electrical = True
        mech_3d = True
    return electrical, mech_3d, mech_2d


def is_ambiguous(text: str) -> bool:
    electrical, mech_3d, mech_2d = domain_flags(text)
    hits = sum((electrical, mech_3d, mech_2d))
    if hits >= 2:
        return True
    if electrical and mech_3d and "mount" in text.lower():
        return True
    return False


def ambiguous_question() -> str:
    return _AMBIGUOUS_QUESTION
