"""Closed task list. A sentence that names nothing stays unknown."""

import re

from extrude.intake.domain import domain_flags, is_ambiguous


def classify(text: str) -> str:
    lowered = text.lower()
    electrical, mech_3d, mech_2d = domain_flags(text)
    strong_2d = any(
        token in lowered
        for token in ("laser-cut", "laser cut", "lasercut", "dxf", "hole pattern", "pcd", "2d plate", "2d profile")
    )
    if mech_2d and strong_2d and not electrical:
        return "mechanical_2d"
    if is_ambiguous(text):
        return "ambiguous"
    if mech_2d and not electrical:
        return "mechanical_2d"
    if mech_3d and not electrical:
        return "mechanical_3d"
    if any(word in lowered for word in ("hold-up", "hold up", "holdup", "dying gasp", "dying-gasp")):
        return "holdup_mlcc"
    if _is_mcu_swap(lowered):
        return "mcu_swap"
    if "buck" in lowered or "step-down" in lowered or "step down" in lowered:
        return "buck"
    if any(word in lowered for word in ("ldo", "linear regulator")):
        return "ldo"
    if "regulator" in lowered and not mech_3d:
        return "ldo"
    if "divider" in lowered:
        return "divider"
    if "pull-up" in lowered or "pullup" in lowered or "i2c" in lowered:
        return "pullup"
    if "series resistor" in lowered or re.search(r"\bin series\b", lowered):
        return "series"
    if "lamp" in lowered or "indicator" in lowered:
        return "indicator"
    if re.search(r"\bleds?\b", lowered):
        return "led"
    if mech_3d:
        return "mechanical_3d"
    if mech_2d:
        return "mechanical_2d"
    return "unknown"


def _is_mcu_swap(lowered: str) -> bool:
    names_a_chip = re.search(r"\b(?:mcu|stm32|esp32|nrf52|rp2040)\b", lowered) is not None
    if re.search(r"\b(?:swap|replace)\b", lowered) and names_a_chip:
        return True
    return (
        re.search(r"\bfrom\s+[a-z][a-z0-9-]*\s+to\s+[a-z]", lowered) is not None and names_a_chip
    )
