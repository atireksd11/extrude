"""Read a proposal and refuse one that edits the frozen card."""

import json
import math
import re

from extrude.intake.models import FrozenSpec
from extrude.ir.models import CircuitIR, Part, Pin
from extrude.memory.models import ElectricalIdentity

_KIND_NAMES = {
    "ic": "ic",
    "chip": "ic",
    "regulator": "ic",
    "ldo": "ic",
    "buck": "ic",
    "resistor": "resistor",
    "res": "resistor",
    "r": "resistor",
    "capacitor": "capacitor",
    "cap": "capacitor",
    "c": "capacitor",
    "mlcc": "capacitor",
    "inductor": "inductor",
    "l": "inductor",
    "ferrite": "ferrite",
    "bead": "ferrite",
    "ideal_voltage_source": "ideal_voltage_source",
    "voltage_source": "ideal_voltage_source",
    "vsource": "ideal_voltage_source",
    "source": "ideal_voltage_source",
}
_UNITS = (
    ("uf", 1e-6),
    ("mf", 1e-3),
    ("nf", 1e-9),
    ("pf", 1e-12),
    ("ff", 1e-15),
    ("uh", 1e-6),
    ("mh", 1e-3),
    ("nh", 1e-9),
    ("khz", 1e3),
    ("mhz", 1e6),
    ("hz", 1),
    ("mv", 1e-3),
    ("ma", 1e-3),
    ("v", 1),
    ("a", 1),
    ("f", 1),
    ("h", 1),
)


class ProposalError(Exception):
    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(detail)
        self.kind = kind
        self.detail = detail


def parse_proposal(text: str, spec: FrozenSpec) -> tuple[CircuitIR, ElectricalIdentity | None]:
    raw = _json_object(text)
    if not isinstance(raw, dict):
        raise ProposalError("tool", "the proposal was not a JSON object")
    raw = _normalize(raw)
    if raw.get("spec_hash") != spec.spec_hash:
        raise ProposalError("design", "the proposal changed the frozen card")
    limits = raw.get("limits")
    if not isinstance(limits, dict):
        raise ProposalError("design", "the proposal omitted the frozen limits")
    for key, value in spec.values_si.items():
        if not _close(limits.get(key), value):
            raise ProposalError("design", "the proposal changed a limit")
    if "i_load" in spec.values_si:
        if raw.get("i_load") is None and _close(limits.get("i_load"), spec.values_si["i_load"]):
            raw["i_load"] = limits["i_load"]
        load = raw.get("i_load")
        if load is None or _close(load, 0) or not _close(load, spec.values_si["i_load"]):
            raise ProposalError("design", "the proposal dropped the load")
    try:
        design = CircuitIR(
            spec_hash=spec.spec_hash,
            parts=[Part(**part) for part in raw.get("parts", [])],
            pins=[Pin(**pin) for pin in raw.get("pins", [])],
            tied_nets=raw.get("tied_nets", []),
            f_sw=_number(raw.get("f_sw")) if raw.get("f_sw") is not None else None,
        )
    except Exception as exc:
        detail = " ".join(str(exc).split())
        raise ProposalError("tool", f"the proposal did not fit the design file: {detail[:240]}") from exc
    identity = None
    if isinstance(raw.get("identity"), dict):
        try:
            identity = ElectricalIdentity(**raw["identity"])
        except Exception as exc:
            raise ProposalError("tool", f"the part identity was unreadable: {exc}") from exc
    return design, identity


def _normalize(raw: dict) -> dict:
    found = dict(raw)
    if isinstance(found.get("spec_hash"), str):
        found["spec_hash"] = found["spec_hash"].strip()
    if isinstance(found.get("limits"), dict):
        found["limits"] = {key: _number(value) for key, value in found["limits"].items()}
    if isinstance(found.get("parts"), list):
        found["parts"] = [_part(item) for item in found["parts"]]
    if isinstance(found.get("pins"), list):
        found["pins"] = _pins(found["pins"])
    if found.get("i_load") is not None:
        found["i_load"] = _number(found["i_load"])
    return found


def _part(item: object) -> object:
    if isinstance(item, str):
        item = {"refdes": item}
    if not isinstance(item, dict):
        return item
    part = dict(item)
    if "refdes" not in part:
        for key in ("ref", "reference", "id"):
            if part.get(key):
                part["refdes"] = str(part[key])
                break
    mapped = _kind_name(part.get("kind"))
    if mapped is None:
        for key in ("type", "part", "component"):
            mapped = _kind_name(part.get(key))
            if mapped is not None:
                break
    if mapped is not None:
        part["kind"] = mapped
    elif part.get("refdes"):
        part["kind"] = _kind_from_refdes(str(part["refdes"]))
    if part.get("kind") == "capacitor" and "capacitance" not in part:
        for key in ("value", "c", "cap"):
            if key in part:
                part["capacitance"] = part[key]
                break
    if part.get("kind") == "inductor" and "inductance" not in part:
        for key in ("value", "l"):
            if key in part:
                part["inductance"] = part[key]
                break
    for field in ("capacitance", "inductance", "esr", "bias_v", "tolerance", "theta_ja", "voltage_rating"):
        if field in part:
            part[field] = _number(part[field])
    return part


def _pins(items: list) -> list:
    counts: dict[str, int] = {}
    pins = []
    for item in items:
        if not isinstance(item, dict):
            pins.append(item)
            continue
        pin = dict(item)
        if "refdes" not in pin:
            for key in ("ref", "reference"):
                if pin.get(key):
                    pin["refdes"] = str(pin[key])
                    break
        if "name" not in pin:
            for key in ("pin", "pin_name"):
                if pin.get(key):
                    pin["name"] = str(pin[key])
                    break
        refdes = str(pin.get("refdes") or "")
        if "name" not in pin:
            counts[refdes] = counts.get(refdes, 0) + 1
            pin["name"] = str(counts[refdes])
        state = str(pin.get("state") or "").strip().lower()
        if state in {"connected", "connect", "tied"}:
            pin["state"] = "connected"
        elif state in {"nc", "no_connect"}:
            pin["state"] = "nc"
        elif pin.get("net"):
            pin["state"] = "connected"
        else:
            pin["state"] = "open"
        role = str(pin.get("role") or "").strip().lower()
        roles = {
            "ground": "ground",
            "gnd": "ground",
            "power": "power",
            "positive": "positive",
            "negative": "negative",
            "signal": "signal",
        }
        if role in roles:
            pin["role"] = roles[role]
        else:
            pin.pop("role", None)
        pins.append(pin)
    return pins


def _kind_name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return _KIND_NAMES.get(value.strip().lower())


def _kind_from_refdes(refdes: str) -> str:
    token = refdes.strip().upper()
    if token.startswith("FB"):
        return "ferrite"
    if token.startswith("C"):
        return "capacitor"
    if token.startswith("R"):
        return "resistor"
    if token.startswith("L"):
        return "inductor"
    if token.startswith("V"):
        return "ideal_voltage_source"
    return "ic"


def _number(value: object) -> object:
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return value
    text = value.strip().lower().replace("µ", "u").replace("μ", "u").replace(" ", "")
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?(?:e[+-]?\d+)?)([a-z]+)?", text)
    if match is None:
        return value
    number = float(match.group(1))
    unit = match.group(2) or ""
    for name, scale in _UNITS:
        if unit == name:
            return number * scale
    if unit == "":
        return number
    return value


def _close(got: object, expected: object) -> bool:
    try:
        return math.isclose(float(got), float(expected), rel_tol=1e-9, abs_tol=1e-12)
    except (TypeError, ValueError):
        return got == expected


def _json_object(text: str) -> object:
    body = text.strip()
    if body.startswith("```"):
        lines = [line for line in body.splitlines() if not line.strip().startswith("```")]
        body = "\n".join(lines)
    start = body.find("{")
    end = body.rfind("}")
    if start < 0 or end < start:
        raise ProposalError("tool", "the proposal was not JSON")
    try:
        return json.loads(body[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ProposalError("tool", "the proposal was not JSON") from exc
