"""Circuits the sentence already specifies. No model call."""

from extrude.intake.models import FrozenSpec
from extrude.ir.models import CircuitIR, Part, Pin
from extrude.sim.models import SimResult

PASSIVE = {"divider", "pullup", "series", "indicator", "led"}


def build(spec: FrozenSpec) -> tuple[CircuitIR, str]:
    values = spec.values_si
    if spec.task_class == "divider":
        design = _resistors(
            spec.spec_hash,
            [("R1", values["r_top"], "VIN", "MID"), ("R2", values["r_bot"], "MID", "GND")],
            source=("V1", "VIN"),
        )
        return design, _divider_deck(values["r_top"], values["r_bot"], values.get("vin", 1.0))
    if spec.task_class == "pullup":
        count = max(1, int(values.get("n_lines", 1)))
        nets = ["SDA", "SCL"][:count] if count >= 2 else ["NODE"]
        design = _resistors(
            spec.spec_hash,
            [(f"R{index}", values["r_pull"], "VBUS", net) for index, net in enumerate(nets, start=1)],
            source=("V1", "VBUS"),
        )
        return design, _pullup_deck(values["v_bus"], values["r_pull"], nets)
    if spec.task_class == "series":
        return (
            _resistors(spec.spec_hash, [("R1", values["r_series"], "SIG", "PIN")]),
            "",
        )
    if spec.task_class == "led":
        resistor = (values["v_supply"] - values["v_f"]) / values["i_led"]
        return (
            _resistors(
                spec.spec_hash,
                [("R1", resistor, "VLED", "ANODE")],
                source=("V1", "VLED"),
                led=("D1", "ANODE", "GND"),
            ),
            "",
        )
    resistor = (values["v_rail"] - values["v_f"]) / values["i_lamp"]
    design = _resistors(
        spec.spec_hash,
        [("R1", resistor, "VRAIL", "ANODE")],
        source=("V1", "VRAIL"),
        led=("D1", "ANODE", "GND"),
    )
    return design, ""


def spice_miss(spec: FrozenSpec, simulated: SimResult) -> str | None:
    if simulated.status != "measured":
        return None
    values = spec.values_si
    if spec.task_class == "divider":
        stimulus = values.get("vin", 1.0)
        expected = stimulus * values["r_bot"] / (values["r_top"] + values["r_bot"])
        got = simulated.measurements.get("v_mid")
        if got is None or abs(got - expected) > max(0.02, 0.01 * stimulus):
            return "the divider ratio does not match the two resistors"
        return None
    if spec.task_class == "pullup":
        expected = values["v_bus"] * 1e6 / (values["r_pull"] + 1e6)
        count = max(1, int(values.get("n_lines", 1)))
        names = ["v_sda", "v_scl"][:count] if count >= 2 else ["v_node"]
        for name in names:
            got = simulated.measurements.get(name)
            if got is None or abs(got - expected) > 0.05:
                return "a pulled-up line is not at the bus voltage"
        return None
    return None


def _resistors(spec_hash, legs, source=None, led=None) -> CircuitIR:
    parts = [Part(refdes=refdes, kind="resistor", resistance=ohms) for refdes, ohms, _a, _b in legs]
    pins = []
    for refdes, _ohms, left, right in legs:
        pins.append(Pin(refdes=refdes, name="A", net=left, state="connected"))
        pins.append(Pin(refdes=refdes, name="B", net=right, state="connected"))
    if source is not None:
        refdes, net = source
        parts.append(Part(refdes=refdes, kind="ideal_voltage_source"))
        pins.append(Pin(refdes=refdes, name="+", net=net, state="connected", role="positive"))
        pins.append(Pin(refdes=refdes, name="-", net="GND", state="connected", role="negative"))
    if led is not None:
        refdes, anode, cathode = led
        parts.append(Part(refdes=refdes, kind="led"))
        pins.append(Pin(refdes=refdes, name="A", net=anode, state="connected"))
        pins.append(Pin(refdes=refdes, name="K", net=cathode, state="connected"))
    return CircuitIR(spec_hash=spec_hash, parts=parts, pins=pins)


def _divider_deck(r_top: float, r_bot: float, vin: float) -> str:
    return "\n".join(
        [
            "* extrude divider",
            f"V1 vin 0 DC {_spice(vin)}",
            f"Rtop vin mid {_spice(r_top)}",
            f"Rbot mid 0 {_spice(r_bot)}",
            ".tran 1m 2m",
            ".meas tran v_mid AVG v(mid) FROM=0 TO=2m",
            ".end",
            "",
        ]
    )


def _pullup_deck(v_bus: float, r_pull: float, nets: list[str]) -> str:
    lines = ["* extrude pull-up", f"V1 vbus 0 DC {_spice(v_bus)}"]
    for index, net in enumerate(nets, start=1):
        node = net.lower()
        lines.append(f"R{index} vbus {node} {_spice(r_pull)}")
        lines.append(f"Rleak{index} {node} 0 1Meg")
    lines.append(".tran 1m 2m")
    for net in nets:
        node = net.lower()
        lines.append(f".meas tran v_{node} AVG v({node}) FROM=0 TO=2m")
    lines.append(".end")
    return "\n".join(lines) + "\n"


def _spice(value: float) -> str:
    return format(value, ".12g")
