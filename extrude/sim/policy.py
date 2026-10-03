"""Decide whether a deck may start. Switching is refused before any process."""

import re

_SWITCH = re.compile(r"(?im)^(?!\s*\*).*\bS\d+\b")
_SW_MODEL = re.compile(r"(?im)^(?!\s*\*)\s*\.model\s+\S+\s+SW\b")
_TRAN = re.compile(r"(?im)^(?!\s*\*)\s*\.tran\b(.*)$")
_PULSE = re.compile(r"(?im)PULSE\s*\(([^)]*)\)")
_SUFFIX = {
    "t": 1e12,
    "g": 1e9,
    "meg": 1e6,
    "k": 1e3,
    "m": 1e-3,
    "u": 1e-6,
    "n": 1e-9,
    "p": 1e-12,
    "f": 1e-15,
}


def refusal_reason(deck: str) -> str | None:
    if _SWITCH.search(deck) or _SW_MODEL.search(deck):
        return "switch"
    for match in _PULSE.finditer(deck):
        if _line_is_comment(deck, match.start()):
            continue
        period = _pulse_period(match.group(1))
        if period is not None and period < 20e-6:
            return "switching_clock"
    for match in _TRAN.finditer(deck):
        tmax = _tran_tmax(match.group(1))
        if tmax is not None and tmax < 100e-9:
            return "switching_transient"
    if not re.search(r"(?im)^(?!\s*\*)\s*\.(?:tran|op|dc)\b", deck):
        return "no_analysis"
    return None


def _line_is_comment(deck: str, index: int) -> bool:
    line = deck.rfind("\n", 0, index)
    start = 0 if line < 0 else line + 1
    return deck[start:].lstrip().startswith("*")


def _pulse_period(body: str) -> float | None:
    parts = body.replace(",", " ").split()
    if len(parts) < 7:
        return None
    return _spice_number(parts[6])


def _tran_tmax(body: str) -> float | None:
    parts = body.replace(",", " ").split()
    if len(parts) < 4:
        return None
    return _spice_number(parts[3])


def _spice_number(text: str) -> float | None:
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?(?:e[+-]?\d+)?)(meg|[tgkmunpf])?", text.strip(), re.I)
    if match is None:
        return None
    value = float(match.group(1))
    suffix = (match.group(2) or "").lower()
    if suffix == "meg":
        return value * 1e6
    return value * _SUFFIX.get(suffix, 1.0)
