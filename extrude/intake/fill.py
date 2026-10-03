"""Turn quantities into named slots. Unlabeled numbers are not guessed past one obvious role."""

import re

from extrude.intake.parse import Quantity

DEFAULTS_VERSION = "2026-10-03"
BUCK_RIPPLE_V = 30e-3

BLOCKING = {
    "buck": ("vin", "vout", "i_load"),
    "ldo": ("vin", "vout", "i_load"),
    "holdup_mlcc": ("v_rail", "t_hold", "c_min"),
    "led": ("i_led",),
    "mcu_swap": (),
}

_LOOKBACK = 24


def assign_slots(text: str, hits: list[Quantity], task_class: str) -> tuple[dict[str, Quantity], bool]:
    roles: dict[str, Quantity] = {}
    unlabeled_v: list[Quantity] = []
    unlabeled_a: list[Quantity] = []
    ambiguous = False
    for hit in hits:
        role = _role(text, hit)
        if role is None:
            if hit.kind == "V":
                unlabeled_v.append(hit)
            else:
                unlabeled_a.append(hit)
            continue
        if role in roles:
            ambiguous = True
        else:
            roles[role] = hit
    for hit in unlabeled_v:
        if "vin" not in roles:
            roles["vin"] = hit
        elif "vout" not in roles:
            roles["vout"] = hit
        else:
            ambiguous = True
    if task_class == "led":
        if "i_led" not in roles and len(unlabeled_a) == 1 and "i_load" not in roles:
            roles["i_led"] = unlabeled_a[0]
            unlabeled_a = []
        elif len(unlabeled_a) > 1:
            ambiguous = True
    elif "i_load" not in roles and len(unlabeled_a) == 1:
        roles["i_load"] = unlabeled_a[0]
    elif unlabeled_a:
        ambiguous = True
    return roles, ambiguous


def mcu_labels(text: str) -> dict[str, str]:
    match = re.search(r"from\s+([A-Za-z][A-Za-z0-9-]*)\s+to\s+([A-Za-z][A-Za-z0-9-]*)", text)
    if match is None:
        return {}
    return {"from_part": match.group(1), "to_part": match.group(2)}


def _role(text: str, hit: Quantity) -> str | None:
    window = text[max(0, hit.start - _LOOKBACK) : hit.start].lower()
    if hit.kind == "V":
        patterns = (
            ("ripple_pp", r"ripple"),
            ("vout", r"\b(?:vout|output)\b"),
            ("vin", r"\b(?:vin|input)\b"),
            ("vout", r"\bto\b"),
        )
    else:
        patterns = (("i_load", r"\b(?:load|iout|i_load)\b"),)
    best_role = None
    best_end = -1
    for role, pattern in patterns:
        for match in re.finditer(pattern, window):
            if match.end() >= best_end:
                best_role = role
                best_end = match.end()
    return best_role
