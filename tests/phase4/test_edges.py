"""Edges around the simulator door."""

from unittest.mock import patch

from extrude.emit import emit_cir
from extrude.ir.models import CircuitIR, Part, Pin
from extrude.physics.models import CapValue, CurveSource, PhysicsValues
from extrude.sim import run_allowed
from extrude.sim.policy import refusal_reason


def _cap(refdes: str, nominal: float, use: float) -> CapValue:
    return CapValue(
        refdes=refdes,
        c_nominal=nominal,
        c_eff=use,
        c_use=use,
        curve_source=CurveSource.vendor_table,
        v_dc=4.7,
    )


def test_each_capacitor_uses_its_own_use_value():
    deck = emit_cir(
        CircuitIR(),
        PhysicsValues(caps=[_cap("C1", 22e-6, 9.12e-6), _cap("C2", 10e-6, 4e-6)]),
    )
    values = {}
    for line in deck.splitlines():
        if line.startswith("*") or not line[:1].upper() == "C":
            continue
        parts = line.split()
        values[parts[0]] = float(parts[3])
    assert values == {"C1": 9.12e-6, "C2": 4e-6}


def test_a_connected_capacitor_stays_on_its_own_nets():
    design = CircuitIR(
        parts=[
            Part(refdes="C1", kind="capacitor", capacitance=22e-6),
            Part(refdes="C2", kind="capacitor", capacitance=10e-6),
        ],
        pins=[
            Pin(refdes="C1", name="1", net="HOLD", state="connected"),
            Pin(refdes="C1", name="2", net="GND", state="connected"),
            Pin(refdes="C2", name="1", net="VIN", state="connected"),
            Pin(refdes="C2", name="2", net="GND", state="connected"),
        ],
    )
    deck = emit_cir(
        design,
        PhysicsValues(caps=[_cap("C1", 22e-6, 9.12e-6), _cap("C2", 10e-6, 4e-6)]),
    )
    body = [line for line in deck.splitlines() if line and not line.startswith("*")]
    assert "C1 HOLD 0 9.12e-06" in body
    assert "C2 VIN 0 4e-06" in body
    assert not any("rail" in line for line in deck.splitlines())
    assert "v(HOLD)" in deck
    assert refusal_reason(deck) is None


def test_a_slow_holdup_pulse_is_not_a_switching_clock_and_a_fast_one_is():
    hold = emit_cir(CircuitIR(), PhysicsValues(caps=[_cap("C1", 22e-6, 9.12e-6)]))
    assert refusal_reason(hold) is None
    fast = "\n".join(
        [
            "* no switch element, but the clock is a switcher",
            "Vclock gate 0 PULSE(0 5 0 1n 1n 1u 2u)",
            "R1 gate 0 1k",
            ".tran 1u 1m",
            ".end",
        ]
    )
    assert refusal_reason(fast) == "switching_clock"
    edged = "\n".join(["V1 in 0 DC 5", "R1 in 0 10", ".tran 0 1m 0 10n", ".end"])
    assert refusal_reason(edged) == "switching_transient"


def test_an_averaged_dc_deck_is_allowed_and_a_crash_log_is_tooling():
    averaged = "\n".join(
        [
            "V1 in 0 DC 5",
            "Eavg out 0 in 0 0.66",
            "Rload out 0 10",
            ".op",
            ".meas dc v_out FIND v(out) AT=0",
            ".end",
        ]
    )
    assert refusal_reason(averaged) is None
    with (
        patch("extrude.sim.runner.ngspice_binary", return_value="ngspice"),
        patch("extrude.sim.runner._execute", return_value="doAnalyses: Timestep too small"),
    ):
        result = run_allowed(averaged)
    assert result.status == "tooling"
    assert result.measurements == {}


def test_a_non_positive_capacitance_never_starts_and_a_bad_name_is_still_a_capacitor():
    zero = emit_cir(CircuitIR(), PhysicsValues(caps=[_cap("C1", 22e-6, 0)]))
    negative = emit_cir(CircuitIR(), PhysicsValues(caps=[_cap("C1", 22e-6, -1e-6)]))
    assert refusal_reason(zero) == "bad_capacitance"
    assert refusal_reason(negative) == "bad_capacitance"
    with patch("extrude.sim.runner.subprocess.run") as spawn:
        assert run_allowed(negative).status == "refused"
    spawn.assert_not_called()
    renamed = emit_cir(CircuitIR(), PhysicsValues(caps=[_cap("Bank", 22e-6, 9.12e-6)]))
    assert any(line.startswith("C1 rail 0 ") for line in renamed.splitlines())
    assert "* Bank nominal=" in renamed
    assert refusal_reason(renamed) is None


def test_a_short_pulse_hidden_in_a_comment_does_not_refuse_the_holdup():
    deck = "* PULSE(0 5 0 1n 1n 1u 2u) is only a note\n" + emit_cir(
        CircuitIR(), PhysicsValues(caps=[_cap("C1", 22e-6, 9.12e-6)])
    )
    assert refusal_reason(deck) is None
