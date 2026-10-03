"""Requirement card. Numbers come from the sentence. A design does not start here."""

from extrude.intake.card import describe
from extrude.intake.classify import classify
from extrude.intake.errors import SpecRejected
from extrude.intake.fill import BLOCKING, BUCK_RIPPLE_V, DEFAULTS_VERSION, assign_slots, mcu_labels
from extrude.intake.hashing import card_hash
from extrude.intake.models import FrozenSpec, NeedsInfo, SlotOrigin
from extrude.intake.parse import find_quantities

_UNKNOWN = "Which circuit is this: buck, regulator, hold-up, LED, or an MCU swap?"
_STEP_UP = "This raises the voltage, which is not a buck. Which circuit is this: buck, regulator, hold-up, LED, or an MCU swap?"


def resolve(raw_text: str) -> FrozenSpec | NeedsInfo:
    kind = classify(raw_text)
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
    missing = [name for name in BLOCKING[kind] if name not in roles]
    if missing:
        return NeedsInfo(missing=missing, question=_ask(kind, missing))
    return _freeze(kind, roles)


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


def _freeze(kind: str, roles: dict) -> FrozenSpec:
    values: dict[str, float] = {name: hit.si for name, hit in roles.items()}
    origins = {name: SlotOrigin.user_span for name in roles}
    evidence = {name: hit.snippet for name, hit in roles.items()}
    if kind == "buck" and "ripple_pp" not in values:
        values["ripple_pp"] = BUCK_RIPPLE_V
        origins["ripple_pp"] = SlotOrigin.default
        evidence["ripple_pp"] = "30 mV"
    spec = FrozenSpec(
        task_class=kind,  # type: ignore[arg-type]
        values_si=values,
        origins=origins,
        defaults_version=DEFAULTS_VERSION,
        spec_hash="",
        evidence=evidence,
    )
    return spec.model_copy(update={"spec_hash": card_hash(spec)})


def _ask(kind: str, missing: list[str]) -> str:
    if missing == ["i_load"]:
        return f"What load current should this {kind} supply?"
    if missing == ["vin"]:
        return f"What input voltage should this {kind} use?"
    if missing == ["vout"]:
        return f"What output voltage should this {kind} supply?"
    if missing == ["i_led"]:
        return "What current should the LED draw?"
    if kind == "holdup_mlcc":
        return "What rail voltage, hold time, and minimum capacitance should the hold-up meet?"
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
