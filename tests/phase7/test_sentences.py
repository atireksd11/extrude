"""New sentences use the same rooms. They are not copies of the frozen eight."""

from extrude.harness import run
from extrude.intake import resolve
from extrude.intake.models import FrozenSpec, SlotOrigin
from extrude.memory import reset
from extrude.sim.models import SimResult


def setup_function() -> None:
    reset()


def test_a_voltage_divider_computes_the_resistors_and_exports_kicad(monkeypatch):
    spec = resolve("12V to 3.3V divider")
    assert isinstance(spec, FrozenSpec)
    assert spec.values_si["vin"] == 12
    assert spec.values_si["vout"] == 3.3
    assert spec.origins["r_bot"] is SlotOrigin.default
    assert spec.origins["r_top"] is SlotOrigin.default
    expected = 12 * spec.values_si["r_bot"] / (spec.values_si["r_top"] + spec.values_si["r_bot"])
    monkeypatch.setattr(
        "extrude.harness.loop.run_allowed",
        lambda _deck: SimResult(status="measured", measurements={"v_mid": expected}),
    )
    result = run("12V to 3.3V divider")
    assert result.status == "checked"
    assert "Verified: Pin Connectivity, SPICE DC" in (result.notice or "")
    assert "Unverified: Thermal, RF/High-Speed, Mechanical Clearance." in (result.notice or "")
    assert result.netlist is not None
    assert '(export (version "E")' in result.netlist
    assert '(ref "R1")' in result.netlist
    assert '(name "GND")' in result.netlist


def test_an_led_on_a_supply_and_smbus_pullups_are_not_special_cases(monkeypatch):
    monkeypatch.setattr(
        "extrude.harness.loop.run_allowed",
        lambda _deck: SimResult(status="unavailable", cause="tooling", detail="ngspice was not found"),
    )
    led = resolve("15 mA LED on 5V")
    assert isinstance(led, FrozenSpec)
    assert led.values_si["i_led"] == 0.015
    assert led.values_si["v_supply"] == 5
    assert run("15 mA LED on 5V").status == "checked"
    bus = resolve("10k pull-ups on SMBus")
    assert isinstance(bus, FrozenSpec)
    assert bus.values_si["r_pull"] == 10_000
    assert bus.values_si["n_lines"] == 2
    assert bus.values_si["v_bus"] == 3.3
    assert bus.origins["v_bus"] is SlotOrigin.default
    assert run("10k pull-ups on SMBus").status == "checked"
