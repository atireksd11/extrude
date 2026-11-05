"""A finished passive sentence is checked without a model call."""

import pytest

from extrude.harness import run
from extrude.harness.client import complete
from extrude.harness.proposal import ProposalError
from extrude.intake import resolve
from extrude.memory import reset
from extrude.sim.models import SimResult


def setup_function() -> None:
    reset()


def test_the_four_named_circuits_check_without_a_model(monkeypatch):
    monkeypatch.delenv("EXTRUDE_MODEL_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    prompts = [
        "two resistors for an ADC divider, 10k and 4.99k",
        "4.7k pull-ups on a 3.3 V I2C bus",
        "a 330 ohm series resistor into a lower-voltage pin",
        "a power-good lamp that draws 5 mA from 3.3 V",
    ]
    for prompt in prompts:
        result = run(prompt)
        assert result.status == "checked", prompt
        assert result.cost_usd is None
        assert result.attempts == 0
        with pytest.raises(ProposalError, match="no model key"):
            complete(prompt, "primary")


def test_a_wrong_divider_measurement_is_rejected(monkeypatch):
    bad = SimResult(status="measured", measurements={"v_mid": 0.9})
    monkeypatch.setattr("extrude.harness.loop.run_allowed", lambda deck: bad)
    result = run("two resistors for an ADC divider, 10k and 4.99k")
    assert result.status == "stopped"
    assert "ratio" in (result.detail or "")


def test_a_missing_simulator_does_not_reject_a_divider_the_resistors_already_set(monkeypatch):
    missing = SimResult(status="unavailable", cause="tooling", detail="ngspice was not found")
    monkeypatch.setattr("extrude.harness.loop.run_allowed", lambda deck: missing)
    result = run("two resistors for an ADC divider, 10k and 4.99k")
    assert result.status == "checked"
    assert isinstance(resolve("two resistors for an ADC divider, 10k and 4.99k").values_si["r_top"], float)
