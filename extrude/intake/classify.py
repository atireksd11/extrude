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
    if "mcu" in lowered and any(word in lowered for word in ("swap", "replace", "instead of")):
        return True
    return "from" in lowered and "to" in lowered and any(
        name in lowered for name in ("mcu", "stm32", "esp32")
    )
