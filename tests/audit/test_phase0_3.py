"""Audit edges for phases 0–3. These branches were uncovered or easy to misread."""

from extrude.checks import preflight
from extrude.intake import confirm, resolve
from extrude.intake.errors import SpecRejected
from extrude.intake.models import FrozenSpec
from extrude.ir.models import CircuitIR, Part, Pin
from extrude.physics import derive
from extrude.intake.models import SlotOrigin


def _spec(**values: float) -> FrozenSpec:
    return FrozenSpec(
        task_class="buck",
        values_si=values,
        origins={key: SlotOrigin.user_span for key in values},
        defaults_version="2026-10-03",
        spec_hash="audit",
    )


def test_equal_voltages_and_a_vague_sentence_cannot_keep_a_frozen_card():
    same = resolve("5 V to 5 V at 2 A")
    assert same.missing == ["task_class"]
    card = resolve("5 V to 3.3 V at 2 A")
    assert isinstance(card, FrozenSpec)
    try:
        confirm("Power an ESP32", card)
    except SpecRejected:
        return
    raise AssertionError("a vague sentence kept a frozen card")


def test_incomplete_buck_and_mcu_ask_for_the_missing_fact():
    buck = resolve("buck at 5 V and 2 A")
    assert buck.missing == ["vout"]
    assert "output voltage" in buck.question
    missing_in = resolve("buck output 3.3 V at 2 A")
    assert missing_in.missing == ["vin"]
    assert "input voltage" in missing_in.question
    neither = resolve("buck at 2 A")
    assert "vin" in neither.missing and "vout" in neither.missing
    mcu = resolve("swap the MCU")
    assert mcu.missing == ["from_part", "to_part"]
    extra = resolve("5 V to 3.3 V at 2 A with 10 uF")
    assert extra.missing == ["ambiguous_numbers"]
    assert "input, the output" not in extra.question


def test_a_do_not_connect_driver_is_not_a_short_and_a_blank_net_is_hanging():
    design = CircuitIR(
        parts=[
            Part(refdes="U1", kind="ic"),
            Part(refdes="C1", kind="capacitor"),
            Part(refdes="V1", kind="ideal_voltage_source"),
        ],
        pins=[
            Pin(refdes="U1", name="VDD", net="3V3", state="connected", role="power"),
            Pin(refdes="U1", name="GND", net="GND", state="connected", role="ground"),
            Pin(refdes="U1", name="TX", net="UART", state="connected", driver="uart_tx"),
            Pin(refdes="U2", name="TX", net="UART", state="nc", driver="uart_tx"),
            Pin(refdes="C1", name="A", net="3V3", state="connected"),
            Pin(refdes="C1", name="B", net="GND", state="connected"),
            Pin(refdes="V1", name="+", net="3V3", state="connected", role="positive"),
            Pin(refdes="V1", name="-", net="GND", state="connected", role="negative"),
            Pin(refdes="V1", name="NC", state="open"),
        ],
    )
    report = preflight(design)
    assert report.blocking == ["hanging_pin:V1.NC"]
    blank = preflight(CircuitIR(pins=[Pin(refdes="U1", name="GPIO", net="   ", state="connected")]))
    assert blank.blocking == ["hanging_pin:U1.GPIO"]


def test_duplicate_readings_do_not_freeze():
    led = resolve("led 20 mA and 5 mA")
    assert led.missing == ["ambiguous_numbers"]
    third = resolve("5 V to 3.3 V to 1.8 V at 2 A")
    assert third.missing == ["ambiguous_numbers"]
    twice = resolve("hold-up 4.7 V for 20 ms and 10 ms, 22 uF")
    assert twice.missing == ["ambiguous_numbers"]
    lone = resolve("status LED")
    assert lone.missing == ["i_led"]
    assert "current" in lone.question


def test_missing_esr_warns_instead_of_pretending_it_is_zero():
    values = derive(
        CircuitIR(
            f_sw=1e6,
            parts=[
                Part(
                    refdes="C1",
                    kind="capacitor",
                    capacitance=10e-6,
                    tolerance=0,
                    dielectric="C0G",
                    bias_v=3.3,
                ),
                Part(refdes="L1", kind="inductor", inductance=2.2e-6),
            ],
        ),
        _spec(vin=5, vout=3.3, i_load=2),
    )
    assert values.ripple_pp is not None
    assert any(item.code == "esr_unknown" for item in values.findings)
