"""Turn quantities into named slots. Unlabeled numbers are not guessed past one obvious role."""

import re

from extrude.intake.parse import Quantity

DEFAULTS_VERSION = "2026-10-03"
BUCK_RIPPLE_V = 30e-3

BLOCKING = {
    "buck": ("vin", "vout", "i_load"),
    "ldo": ("vin", "vout", "i_load"),
    "holdup_mlcc": ("v_rail", "t_hold", "c_min"),
    "led": ("i_led", "v_supply"),
    "mcu_swap": (),
    "divider": ("r_top", "r_bot"),
    "pullup": ("r_pull", "v_bus"),
    "series": ("r_series",),
    "indicator": ("i_lamp", "v_rail"),
}
INDICATOR_VF_V = 2.0

_LOOKBACK = 24


def assign_slots(text: str, hits: list[Quantity], task_class: str) -> tuple[dict[str, Quantity], bool]:
    if task_class == "holdup_mlcc":
        return _assign_holdup(hits)
    if task_class == "divider":
        return _assign_divider(text, hits)
    if task_class == "series":
        return _assign_pair(hits, "ohm", ("r_series",))
    if task_class == "pullup":
        ohms, ohm_flag = _assign_pair(hits, "ohm", ("r_pull",))
        volts, volt_flag = _assign_pair(hits, "V", ("v_bus",))
        return {**ohms, **volts}, ohm_flag or volt_flag
    if task_class == "indicator":
        amps, amp_flag = _assign_pair(hits, "A", ("i_lamp",))
        volts, volt_flag = _assign_pair(hits, "V", ("v_rail",))
        return {**amps, **volts}, amp_flag or volt_flag
    roles: dict[str, Quantity] = {}
    unlabeled_v: list[Quantity] = []
    unlabeled_a: list[Quantity] = []
    ambiguous = False
    for hit in hits:
        role = _role(text, hit)
        if role is None:
            if hit.kind == "V":
                unlabeled_v.append(hit)
            elif hit.kind == "A":
                unlabeled_a.append(hit)
            elif hit.kind == "ohm":
                continue
            else:
                ambiguous = True
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
        if "i_led" not in roles and "i_load" in roles:
            roles["i_led"] = roles.pop("i_load")
        if "i_led" not in roles and len(unlabeled_a) == 1:
            roles["i_led"] = unlabeled_a[0]
            unlabeled_a = []
        elif len(unlabeled_a) > 1:
            ambiguous = True
        if "vin" in roles and "vout" in roles:
            ambiguous = True
        elif "v_supply" not in roles and "vin" in roles:
            roles["v_supply"] = roles.pop("vin")
        elif "v_supply" not in roles and "vout" in roles:
            roles["v_supply"] = roles.pop("vout")
    elif "i_load" not in roles and len(unlabeled_a) == 1:
        roles["i_load"] = unlabeled_a[0]
    elif unlabeled_a:
        ambiguous = True
    return roles, ambiguous


def mcu_labels(text: str) -> dict[str, str]:
    match = re.search(
        r"from\s+([A-Za-z][A-Za-z0-9-]*)\s+to\s+([A-Za-z][A-Za-z0-9-]*)",
        text,
        re.IGNORECASE,
    )
    if match is None:
        match = re.search(
            r"replace\s+(?:the\s+)?([A-Za-z][A-Za-z0-9-]*)\s+with\s+(?:an?\s+)?([A-Za-z][A-Za-z0-9-]*)",
            text,
            re.IGNORECASE,
        )
    if match is None:
        return {}
    return {"from_part": match.group(1), "to_part": match.group(2)}


def pullup_line_count(text: str) -> int:
    lowered = text.lower()
    if any(word in lowered for word in ("i2c", "smbus")) or re.search(r"\b(?:sda|scl)\b", lowered):
        return 2
    if re.search(r"pull-?ups\b", lowered) or re.search(r"pull-?up resistors\b", lowered):
        return 2
    return 1


def _assign_divider(text: str, hits: list[Quantity]) -> tuple[dict[str, Quantity], bool]:
    ohms = [hit for hit in hits if hit.kind == "ohm"]
    labeled: dict[str, Quantity] = {}
    unlabeled: list[Quantity] = []
    ambiguous = len(ohms) > 2
    for hit in ohms:
        window = text[max(0, hit.start - _LOOKBACK) : hit.start].lower()
        role = _nearest_divider_role(window)
        if not role:
            unlabeled.append(hit)
        elif role in labeled:
            ambiguous = True
        else:
            labeled[role] = hit
    for hit in unlabeled:
        if "r_top" not in labeled:
            labeled["r_top"] = hit
        elif "r_bot" not in labeled:
            labeled["r_bot"] = hit
        else:
            ambiguous = True
    volts = [hit for hit in hits if hit.kind == "V"]
    if len(volts) > 2:
        ambiguous = True
    for hit in volts:
        window = text[max(0, hit.start - _LOOKBACK) : hit.start].lower()
        if re.search(r"\bto\b", window):
            role = "vout"
        elif re.search(r"\bfrom\b", window):
            role = "vin"
        elif "vin" not in labeled:
            role = "vin"
        elif "vout" not in labeled:
            role = "vout"
        else:
            ambiguous = True
            continue
        if role in labeled:
            ambiguous = True
        else:
            labeled[role] = hit
    return labeled, ambiguous


def _nearest_divider_role(window: str) -> str:
    marks = []
    for role, pattern in (("r_bot", r"\b(?:bottom|lower)\b"), ("r_top", r"\b(?:top|upper)\b")):
        for match in re.finditer(pattern, window):
            marks.append((match.end(), role))
    if not marks:
        return ""
    marks.sort()
    return marks[-1][1]


def _assign_pair(hits: list[Quantity], kind: str, names: tuple[str, ...]) -> tuple[dict[str, Quantity], bool]:
    chosen = [hit for hit in hits if hit.kind == kind]
    roles = {name: hit for name, hit in zip(names, chosen)}
    return roles, len(chosen) > len(names)


def _assign_holdup(hits: list[Quantity]) -> tuple[dict[str, Quantity], bool]:
    roles: dict[str, Quantity] = {}
    ambiguous = False
    for hit in hits:
        key = {"V": "v_rail", "s": "t_hold", "F": "c_min"}.get(hit.kind)
        if key is None or key in roles:
            ambiguous = True
            continue
        roles[key] = hit
    return roles, ambiguous


def _role(text: str, hit: Quantity) -> str | None:
    window = text[max(0, hit.start - _LOOKBACK) : hit.start].lower()
    if hit.kind == "V":
        patterns = (
            ("ripple_pp", r"ripple"),
            ("vout", r"\b(?:vout|output)\b"),
            ("vin", r"\b(?:vin|input)\b"),
            ("vin", r"\bfrom\s*$"),
            ("vout", r"\bto\s*$"),
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
