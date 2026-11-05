"""Requirement card. Numbers come from the sentence. A design does not start here."""

from extrude.intake.card import describe
from extrude.intake.classify import classify
from extrude.intake.domain import ambiguous_question
from extrude.intake.errors import SpecRejected
from extrude.intake.fill import (
    BLOCKING,
    BUCK_RIPPLE_V,
    DEFAULTS_VERSION,
    INDICATOR_VF_V,
    assign_slots,
    mcu_labels,
    pullup_line_count,
)
from extrude.intake.hashing import card_hash
from extrude.intake.models import FrozenSpec, NeedsInfo, SlotOrigin
from extrude.intake.mechanical import parse_mechanical
from extrude.intake.mechanical_2d import parse_mechanical_2d
from extrude.intake.parse import find_quantities

_UNKNOWN = (
    "Which is this: a 3D print, a 2D flat plate, a buck, regulator, hold-up, LED, or an MCU swap?"
)
_STEP_UP = "This raises the voltage, which is not a buck. Which circuit is this: buck, regulator, hold-up, LED, or an MCU swap?"


def resolve(raw_text: str) -> FrozenSpec | NeedsInfo:
    kind = classify(raw_text)
    if kind == "ambiguous":
        return NeedsInfo(missing=["domain"], question=ambiguous_question())
    if kind in {"mechanical_3d", "mechanical_2d"}:
        return _freeze_mechanical(kind, raw_text)
    hits = find_quantities(raw_text)
    roles, ambiguous = assign_slots(raw_text, hits, kind)
    if ambiguous:
        return NeedsInfo(
            missing=["ambiguous_numbers"],
            question="Some numbers could fit more than one limit. Which values should the card keep?",
        )
    kind, early = _promote(kind, roles)
    if early is not None:
        return early
    if kind == "unknown":
        return NeedsInfo(missing=["task_class"], question=_UNKNOWN)
    if kind == "mcu_swap":
        return _freeze_mcu(raw_text)
    if kind in {"buck", "ldo"} and _drops_voltage(roles) is False:
        return NeedsInfo(missing=["task_class"], question=_STEP_UP)
    missing = _missing(kind, roles, raw_text)
    if missing:
        return NeedsInfo(missing=missing, question=_ask(kind, missing))
    return _freeze(kind, roles, raw_text)


def confirm(raw_text: str, spec: FrozenSpec) -> FrozenSpec:
    resolved = resolve(raw_text)
    if not isinstance(resolved, FrozenSpec):
        raise SpecRejected("This sentence does not freeze a card.")
    if not _same(resolved, spec) or spec.spec_hash != card_hash(spec):
        raise SpecRejected("The card does not match the sentence.")
    return resolved


def _promote(kind: str, roles: dict) -> tuple[str, NeedsInfo | None]:
    if kind != "unknown" or "vin" not in roles or "vout" not in roles:
        return kind, None
    if roles["vin"].si > roles["vout"].si:
        return "buck", None
    if roles["vin"].si < roles["vout"].si:
        return kind, NeedsInfo(missing=["task_class"], question=_STEP_UP)
    return kind, NeedsInfo(
        missing=["task_class"],
        question="Input and output are the same voltage. Which circuit is this: buck, regulator, hold-up, LED, or an MCU swap?",
    )


def _drops_voltage(roles: dict) -> bool | None:
    if "vin" not in roles or "vout" not in roles:
        return None
    return roles["vin"].si > roles["vout"].si


def _freeze_mechanical(kind: str, text: str) -> FrozenSpec | NeedsInfo:
    lowered = text.lower()
    if kind == "mechanical_3d":
        if any(token in lowered for token in ("m2", "m3", "m4", "heat-set", "heat set", "insert")):
            if not any(token in lowered for token in ("petg", "pla", "abs", "filament")):
                return NeedsInfo(missing=["filament"], question="Which filament: PLA or PETG?")
        parsed = parse_mechanical(text)
        label_keys = ("material", "insert")
        value_keys = ("insert_count", "min_wall_mm", "insert_min_mm", "insert_max_mm", "bbox_max_mm")
    else:
        parsed = parse_mechanical_2d(text)
        label_keys = ("material", "hole")
        value_keys = (
            "hole_count",
            "plate_width_mm",
            "plate_height_mm",
            "plate_diameter_mm",
            "pcd_mm",
            "hole_min_mm",
            "hole_max_mm",
            "min_edge_distance_mm",
        )
    values_si: dict[str, float] = {}
    labels: dict[str, str] = {}
    for key in label_keys:
        if key in parsed:
            labels[key] = str(parsed[key])
    for key in value_keys:
        if key in parsed:
            values_si[key] = float(parsed[key])
    if "hole_positions_json" in parsed:
        labels["hole_positions_json"] = str(parsed["hole_positions_json"])
    spec = FrozenSpec(
        task_class=kind,  # type: ignore[arg-type]
        values_si=values_si,
        origins={},
        defaults_version=DEFAULTS_VERSION,
        spec_hash="",
        labels=labels,
        evidence={"sentence": str(parsed.get("sentence", text.strip()))},
    )
    return spec.model_copy(update={"spec_hash": card_hash(spec)})


def _freeze_mcu(text: str) -> FrozenSpec | NeedsInfo:
    labels = mcu_labels(text)
    if "from_part" not in labels or "to_part" not in labels:
        return NeedsInfo(
            missing=["from_part", "to_part"],
            question="Which MCU is being replaced, and which MCU replaces it?",
        )
    spec = FrozenSpec(
        task_class="mcu_swap",
        values_si={},
        origins={},
        defaults_version=DEFAULTS_VERSION,
        spec_hash="",
        labels=labels,
    )
    return spec.model_copy(update={"spec_hash": card_hash(spec)})


def _freeze(kind: str, roles: dict, text: str) -> FrozenSpec:
    values: dict[str, float] = {name: hit.si for name, hit in roles.items()}
    origins = {name: SlotOrigin.user_span for name in roles}
    evidence = {name: hit.snippet for name, hit in roles.items()}
    if kind == "buck" and "ripple_pp" not in values:
        values["ripple_pp"] = BUCK_RIPPLE_V
        origins["ripple_pp"] = SlotOrigin.default
        evidence["ripple_pp"] = "30 mV"
    if kind == "divider":
        _fill_divider(values, origins, evidence)
    if kind == "pullup":
        count = pullup_line_count(text)
        values["n_lines"] = float(count)
        origins["n_lines"] = SlotOrigin.user_span
        lowered = text.lower()
        if "smbus" in lowered:
            bus = "SMBus"
        elif "i2c" in lowered:
            bus = "I2C"
        else:
            bus = "pull-ups" if count == 2 else "pull-up"
        evidence["n_lines"] = bus
        if "v_bus" not in values and bus in {"SMBus", "I2C"}:
            values["v_bus"] = 3.3
            origins["v_bus"] = SlotOrigin.default
            evidence["v_bus"] = "3.3 V"
    if kind in {"indicator", "led"} and "v_f" not in values:
        values["v_f"] = INDICATOR_VF_V
        origins["v_f"] = SlotOrigin.default
        evidence["v_f"] = "2 V"
    spec = FrozenSpec(
        task_class=kind,  # type: ignore[arg-type]
        values_si=values,
        origins=origins,
        defaults_version=DEFAULTS_VERSION,
        spec_hash="",
        evidence=evidence,
    )
    return spec.model_copy(update={"spec_hash": card_hash(spec)})


def _missing(kind: str, roles: dict, text: str) -> list[str]:
    if kind == "divider":
        if "r_top" in roles and "r_bot" in roles:
            return []
        if "vin" in roles and "vout" in roles and roles["vin"].si > roles["vout"].si > 0:
            return []
        return [name for name in ("r_top", "r_bot") if name not in roles]
    if kind == "pullup":
        missing = [name for name in ("r_pull",) if name not in roles]
        lowered = text.lower()
        if "v_bus" not in roles and "i2c" not in lowered and "smbus" not in lowered:
            missing.append("v_bus")
        return missing
    return [name for name in BLOCKING[kind] if name not in roles]


def _fill_divider(values: dict, origins: dict, evidence: dict) -> None:
    if "r_top" in values and "r_bot" in values:
        return
    if "vin" not in values or "vout" not in values or values["vout"] <= 0:
        return
    if "r_bot" not in values:
        values["r_bot"] = 10_000.0
        origins["r_bot"] = SlotOrigin.default
        evidence["r_bot"] = "10k"
    if "r_top" not in values:
        values["r_top"] = values["r_bot"] * ((values["vin"] / values["vout"]) - 1)
        origins["r_top"] = SlotOrigin.default
        evidence["r_top"] = "computed from the voltages"


def _ask(kind: str, missing: list[str]) -> str:
    if missing == ["i_load"]:
        return f"What load current should this {kind} supply?"
    if missing == ["vin"]:
        return f"What input voltage should this {kind} use?"
    if missing == ["vout"]:
        return f"What output voltage should this {kind} supply?"
    if missing == ["i_led"]:
        return "What current should the LED draw?"
    if missing == ["v_supply"]:
        return "What supply voltage should the LED use?"
    if kind == "led" and "i_led" in missing and "v_supply" in missing:
        return "What current and supply voltage should the LED use?"
    if kind == "holdup_mlcc":
        return "What rail voltage, hold time, and minimum capacitance should the hold-up meet?"
    if kind == "divider":
        return "What are the two divider resistor values?"
    if kind == "pullup":
        return "What pull-up resistance and bus voltage should the card keep?"
    if kind == "series":
        return "What resistance should the series resistor be?"
    if kind == "indicator":
        return "What supply voltage and lamp current should the indicator meet?"
    names = ", ".join(missing)
    return f"Still needed before a card can freeze: {names}?"


def _same(left: FrozenSpec, right: FrozenSpec) -> bool:
    return (
        left.task_class == right.task_class
        and left.values_si == right.values_si
        and left.origins == right.origins
        and left.defaults_version == right.defaults_version
        and left.labels == right.labels
        and left.evidence == right.evidence
        and left.spec_hash == right.spec_hash
    )
