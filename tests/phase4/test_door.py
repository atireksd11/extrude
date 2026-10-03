"""The simulator door. Switching never starts, and a crash is not a design failure."""

from unittest.mock import patch
import subprocess

import pytest

from extrude.emit import emit_cir
from extrude.harness.models import AttemptBudget
from extrude.ir.models import CircuitIR
from extrude.physics.models import CapValue, CurveSource, PhysicsValues
from extrude.sim import run_allowed
from extrude.sim.policy import refusal_reason
from extrude.sim.runner import ngspice_binary

_USE = 9.12e-6
_NOMINAL = 22e-6


def _physics() -> PhysicsValues:
    return PhysicsValues(
        caps=[
            CapValue(
                refdes="C1",
                c_nominal=_NOMINAL,
                c_eff=11.4e-6,
                c_use=_USE,
                curve_source=CurveSource.vendor_table,
                v_dc=4.7,
                curve_id="strategy_holdup_22u_4v7",
            )
        ]
    )


def _element_value(deck: str, refdes: str) -> float:
    for line in deck.splitlines():
        stripped = line.strip()
        if stripped.startswith("*") or not stripped.upper().startswith(refdes.upper()):
            continue
        return float(stripped.split()[3])
    raise AssertionError(f"{refdes} was not in the deck")


def test_the_deck_simulates_the_use_value_not_the_nominal():
    deck = emit_cir(CircuitIR(), _physics())
    assert _element_value(deck, "C1") == pytest.approx(_USE)
    assert _element_value(deck, "C1") != pytest.approx(_NOMINAL)
    assert f"nominal={_NOMINAL:.12g}" in deck or "nominal=2.2e-05" in deck
    assert refusal_reason(deck) is None


def test_a_switching_deck_never_starts_a_process():
    deck = "\n".join(
        [
            "Vclock gate 0 PULSE(0 5 0 1n 1n 1u 2u)",
            "S1 sw 0 gate 0 SW",
            ".model SW SW(Vt=2.5)",
            ".tran 0 1m 0 10n",
            ".end",
        ]
    )
    with patch("extrude.sim.runner.subprocess.run") as spawn:
        result = run_allowed(deck)
    spawn.assert_not_called()
    assert result.status == "refused"
    assert result.cause == "policy"
    assert result.measurements == {}


def test_a_crash_does_not_spend_a_design_try_or_write_a_ban():
    budget = AttemptBudget()
    deck = emit_cir(CircuitIR(), _physics())
    with (
        patch("extrude.sim.runner.ngspice_binary", return_value="ngspice"),
        patch("extrude.sim.runner._execute", return_value="Warning: singular matrix:  check nodes"),
        patch("extrude.memory.api.record") as record,
    ):
        result = run_allowed(deck)
    record.assert_not_called()
    assert budget.model_design_used == 0
    assert result.status == "tooling"
    assert result.cause == "tooling"
    assert result.measurements == {}
    with (
        patch("extrude.sim.runner.ngspice_binary", return_value="ngspice"),
        patch("extrude.sim.runner._execute", side_effect=subprocess.TimeoutExpired(cmd="ngspice", timeout=15)),
    ):
        timed = run_allowed(deck)
    assert timed.detail == "timeout"
    assert timed.status == "tooling"


def test_a_comment_that_mentions_a_switch_is_still_allowed():
    deck = emit_cir(CircuitIR(), _physics())
    assert "no switch" not in deck
    commented = "* S1 is not in this hold-up fade\n" + deck
    assert refusal_reason(commented) is None


def test_missing_ngspice_does_not_count_as_a_pass(monkeypatch):
    monkeypatch.setenv("NGSPICE_PATH", r"C:\missing\ngspice.exe")
    assert ngspice_binary() is None
    result = run_allowed(emit_cir(CircuitIR(), _physics()))
    assert result.status == "unavailable"
    assert result.measurements == {}
    assert result.status != "measured"


@pytest.mark.skipif(ngspice_binary() is None, reason="ngspice is not installed")
def test_holdup_returns_a_measured_voltage():
    result = run_allowed(emit_cir(CircuitIR(), _physics()))
    assert result.status == "measured"
    assert "v_hold" in result.measurements
    assert 0 <= result.measurements["v_hold"] < 4.7
