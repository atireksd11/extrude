"""Closed task list. A sentence that names nothing stays unknown."""

import re


def classify(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("hold-up", "hold up", "holdup", "dying gasp", "dying-gasp")):
        return "holdup_mlcc"
    if _is_mcu_swap(lowered):
        return "mcu_swap"
    if "buck" in lowered or "step-down" in lowered or "step down" in lowered:
        return "buck"
    if any(word in lowered for word in ("ldo", "linear regulator", "regulator")):
        return "ldo"
    if re.search(r"\bleds?\b", lowered):
        return "led"
    return "unknown"


def _is_mcu_swap(lowered: str) -> bool:
    names_a_chip = re.search(r"\b(?:mcu|stm32|esp32|nrf52|rp2040)\b", lowered) is not None
    if re.search(r"\b(?:swap|replace)\b", lowered) and names_a_chip:
        return True
    return (
        re.search(r"\bfrom\s+[a-z][a-z0-9-]*\s+to\s+[a-z]", lowered) is not None and names_a_chip
    )
