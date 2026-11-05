"""Which checks can run. The model does not write this sentence."""

from extrude.coverage.models import CoverageMap
from extrude.intake.models import FrozenSpec

_CAN = {
    "buck": ("wiring", "capacitance", "ripple", "parts-cost"),
    "ldo": ("wiring", "still-air heat", "parts-cost"),
    "holdup_mlcc": ("wiring", "capacitance", "hold-up connection", "hold-up fade", "parts-cost"),
    "divider": ("wiring", "divider ratio", "parts-cost"),
    "pullup": ("wiring", "pull-up voltage", "parts-cost"),
    "series": ("wiring", "series resistor", "parts-cost"),
    "indicator": ("wiring", "lamp current", "parts-cost"),
    "led": ("wiring", "lamp current", "parts-cost"),
}
_CANNOT = ("heat-in-airflow", "radios", "fast memory")


def cover(spec: FrozenSpec) -> CoverageMap:
    by_check = {name: "can" for name in _CAN.get(spec.task_class, ())}
    for name in _CANNOT:
        by_check[name] = "cannot"
    return CoverageMap(by_check=by_check)


def _buckets(done: list[str]) -> list[str]:
    found = []
    rules = (
        ("Pin Connectivity", {"wiring", "hold-up connection", "series resistor"}),
        ("SPICE DC", {"divider ratio", "pull-up voltage", "lamp current"}),
        ("SPICE Transient", {"hold-up fade"}),
        ("Capacitance derating", {"capacitance"}),
        ("Ripple", {"ripple"}),
        ("Still-air thermal", {"still-air heat"}),
        ("Parts cost", {"parts-cost"}),
    )
    for label, names in rules:
        if any(name in names for name in done):
            found.append(label)
    return found


def render(spec: FrozenSpec | None, ran: list[str], stopped: str | None = None) -> str:
    allowed = set()
    if spec is not None:
        allowed = {name for name, state in cover(spec).by_check.items() if state == "can"}
    done = [name for name in ran if name in allowed and name != stopped]
    verified = _buckets(done)
    verified_line = "Verified: " + ", ".join(verified) + "." if verified else "Verified: nothing."
    checked = "Checked: " + ", ".join(done) + "." if done else "Checked: nothing."
    halt = f" Stopped during: {stopped}." if stopped else ""
    return (
        f"{verified_line} Unverified: Thermal, RF/High-Speed, Mechanical Clearance. "
        f"{checked}{halt} Not checked: heat-in-airflow, radios, and fast memory."
    )
