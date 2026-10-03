"""Designs meant to fool the wiring check."""

from extrude.checks import preflight
from extrude.ir.models import CircuitIR, Part, Pin


def _pin(refdes: str, name: str, net: str, **kwargs) -> Pin:
    return Pin(refdes=refdes, name=name, net=net, state="connected", **kwargs)


def _rules(design: CircuitIR) -> set[str]:
    return {item.split(":", 1)[0] for item in preflight(design).blocking}


def test_vss_is_not_ground_until_the_card_ties_it():
    parts = [Part(refdes="U1", kind="ic"), Part(refdes="C1", kind="capacitor")]
    pins = [
        _pin("U1", "VDD", "VSS", role="power"),
        _pin("U1", "GND", "GND", role="ground"),
        _pin("C1", "A", "VSS"),
        _pin("C1", "B", "GND"),
    ]
    untied = _rules(CircuitIR(parts=parts, pins=pins))
    tied = _rules(CircuitIR(parts=parts, pins=pins, tied_nets=[["gnd", "vss"]]))
    assert "power_pin_no_dc_path" in untied
    assert tied == set()


def test_a_bead_then_a_bulk_cap_does_not_block():
    design = CircuitIR(
        parts=[
            Part(refdes="U1", kind="ic"),
            Part(refdes="FB1", kind="ferrite"),
            Part(refdes="C1", kind="capacitor"),
            Part(refdes="V1", kind="ideal_voltage_source"),
        ],
        pins=[
            _pin("U1", "VDD", "3V3", role="power"),
            _pin("U1", "GND", "GND", role="ground"),
            _pin("FB1", "A", "3V3"),
            _pin("FB1", "B", "3V3B"),
            _pin("C1", "A", "3V3B"),
            _pin("C1", "B", "GND"),
            _pin("V1", "+", "3V3", role="positive"),
            _pin("V1", "-", "GND", role="negative"),
        ],
    )
    report = preflight(design)
    assert report.blocking == []
    assert report.warnings == ["capacitor_not_on_power_pin_net:U1.VDD"]


def test_two_sources_may_share_ground_but_not_a_driven_net():
    shared_ground = CircuitIR(
        parts=[
            Part(refdes="U1", kind="ic"),
            Part(refdes="V1", kind="ideal_voltage_source"),
            Part(refdes="V2", kind="ideal_voltage_source"),
            Part(refdes="C1", kind="capacitor"),
            Part(refdes="C2", kind="capacitor"),
        ],
        pins=[
            _pin("U1", "VDD", "5V", role="power"),
            _pin("U1", "GND", "GND", role="ground"),
            _pin("V1", "+", "5V", role="positive"),
            _pin("V1", "-", "GND", role="negative"),
            _pin("V2", "+", "3V3", role="positive"),
            _pin("V2", "-", "GND", role="negative"),
            _pin("C1", "A", "5V"),
            _pin("C1", "B", "GND"),
            _pin("C2", "A", "3V3"),
            _pin("C2", "B", "GND"),
        ],
    )
    assert _rules(shared_ground) == set()


def test_pin_names_tx_to_rx_is_legal_and_mosi_to_mosi_is_not():
    link = CircuitIR(
        parts=[
            Part(refdes="U1", kind="ic"),
            Part(refdes="U2", kind="ic"),
            Part(refdes="C1", kind="capacitor"),
            Part(refdes="V1", kind="ideal_voltage_source"),
        ],
        pins=[
            _pin("U1", "VDD", "3V3", role="power"),
            _pin("U1", "GND", "GND", role="ground"),
            _pin("U1", "TX", "LINK"),
            _pin("U2", "RX", "LINK"),
            _pin("C1", "A", "3V3"),
            _pin("C1", "B", "GND"),
            _pin("V1", "+", "3V3", role="positive"),
            _pin("V1", "-", "GND", role="negative"),
        ],
    )
    short = link.model_copy(deep=True)
    short.pins = [
        pin if pin.name != "RX" else pin.model_copy(update={"name": "MOSI"})
        for pin in short.pins
    ]
    short.pins = [
        pin if pin.name != "TX" else pin.model_copy(update={"name": "MOSI"})
        for pin in short.pins
    ]
    assert _rules(link) == set()
    assert "drivers_on_one_net" in _rules(short)


def test_a_series_capacitor_is_not_a_path_to_ground():
    design = CircuitIR(
        parts=[
            Part(refdes="U1", kind="ic"),
            Part(refdes="C1", kind="capacitor"),
            Part(refdes="R1", kind="resistor"),
        ],
        pins=[
            _pin("U1", "VDD", "RAIL", role="power"),
            _pin("U1", "GND", "GND", role="ground"),
            _pin("C1", "A", "RAIL"),
            _pin("C1", "B", "FAR"),
            _pin("R1", "A", "FAR"),
            _pin("R1", "B", "GND"),
        ],
    )
    rules = _rules(design)
    assert "power_pin_no_dc_path" in rules
    assert "ac_side_missing_bias" in rules


def test_an_inductor_does_count_as_a_dc_path():
    design = CircuitIR(
        parts=[
            Part(refdes="U1", kind="ic"),
            Part(refdes="L1", kind="inductor"),
            Part(refdes="C1", kind="capacitor"),
        ],
        pins=[
            _pin("U1", "VDD", "3V3", role="power"),
            _pin("U1", "GND", "GND", role="ground"),
            _pin("L1", "A", "3V3"),
            _pin("L1", "B", "GND"),
            _pin("C1", "A", "3V3"),
            _pin("C1", "B", "GND"),
        ],
    )
    assert _rules(design) == set()


def test_drivers_on_two_names_for_one_wire_still_collide():
    design = CircuitIR(
        parts=[
            Part(refdes="U1", kind="ic"),
            Part(refdes="U2", kind="ic"),
            Part(refdes="C1", kind="capacitor"),
            Part(refdes="V1", kind="ideal_voltage_source"),
        ],
        pins=[
            _pin("U1", "VDD", "3V3", role="power"),
            _pin("U1", "GND", "GND", role="ground"),
            _pin("U1", "TX", "NET_A", driver="uart_tx"),
            _pin("U2", "TX", "NET_B", driver="uart_tx"),
            _pin("C1", "A", "3V3"),
            _pin("C1", "B", "GND"),
            _pin("V1", "+", "3V3", role="positive"),
            _pin("V1", "-", "GND", role="negative"),
        ],
        tied_nets=[["NET_A", "NET_B"]],
    )
    assert "drivers_on_one_net" in _rules(design)
