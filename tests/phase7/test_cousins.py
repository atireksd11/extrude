"""Cousin sentences use the same rules. They are not part of the frozen eight."""

import json
from pathlib import Path

import pytest

from extrude.harness import run
from extrude.intake import resolve
from extrude.intake.models import FrozenSpec, NeedsInfo
from extrude.memory import reset
from extrude.sim.models import SimResult

_SENTENCES = Path(__file__).resolve().parents[2] / "eval" / "cousins" / "sentences.json"


def setup_function() -> None:
    reset()


def _reading(spec: FrozenSpec) -> SimResult:
    values = spec.values_si
    if spec.task_class == "divider":
        ratio = values["r_bot"] / (values["r_top"] + values["r_bot"])
        return SimResult(status="measured", measurements={"v_mid": ratio})
    if spec.task_class == "pullup":
        expected = values["v_bus"] * 1e6 / (values["r_pull"] + 1e6)
        count = int(values["n_lines"])
        names = ["v_sda", "v_scl"][:count] if count >= 2 else ["v_node"]
        return SimResult(status="measured", measurements={name: expected for name in names})
    return SimResult(status="unavailable", cause="tooling", detail="no deck")


def test_cousin_sentences_follow_the_card_and_a_stranger_asks():
    rows = json.loads(_SENTENCES.read_text(encoding="utf-8"))
    assert {row["id"] for row in rows} >= {
        "divider-order",
        "divider-node",
        "pullup-one",
        "pullup-not-i2c",
        "series-other",
        "indicator-other",
        "none",
    }

    def fake_sim(deck: str) -> SimResult:
        return SimResult(status="measured", measurements={})

    # The measurement is filled per sentence below. This default is replaced.
    del fake_sim
    for row in rows:
        reset()
        prompt = row["prompt"]
        if row["expect"] == "needs_info":
            result = run(prompt)
            assert result.status == "needs_info", prompt
            assert isinstance(resolve(prompt), NeedsInfo)
            continue
        spec = resolve(prompt)
        assert isinstance(spec, FrozenSpec), prompt
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr("extrude.harness.loop.run_allowed", lambda _deck, spec=spec: _reading(spec))
            result = run(prompt)
        assert result.status == "checked", (prompt, result.detail)
        assert result.attempts == 0


def test_the_other_divider_order_is_the_ratio_and_a_wrong_reading_fails():
    prompt = "4.99k and 10k for an ADC divider"
    spec = resolve(prompt)
    assert isinstance(spec, FrozenSpec)
    assert spec.values_si["r_top"] == pytest.approx(4990)
    assert spec.values_si["r_bot"] == pytest.approx(10000)
    bad = SimResult(status="measured", measurements={"v_mid": 0.1})
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("extrude.harness.loop.run_allowed", lambda _deck: bad)
        result = run(prompt)
    assert result.status == "stopped"
    assert "ratio" in (result.detail or "")


def test_labels_beat_resistor_order_and_a_missing_simulator_still_checks_one_pullup(monkeypatch):
    labeled = resolve("bottom 4.99k and top 10k divider")
    assert isinstance(labeled, FrozenSpec)
    assert labeled.values_si["r_top"] == pytest.approx(10000)
    assert labeled.values_si["r_bot"] == pytest.approx(4990)
    series = resolve("a 1k resistor in series with the pin")
    assert isinstance(series, FrozenSpec)
    assert series.task_class == "series"
    assert series.values_si["r_series"] == pytest.approx(1000)
    plural = resolve("10k pull-up resistors to 3.3 V")
    assert isinstance(plural, FrozenSpec)
    assert plural.values_si["n_lines"] == pytest.approx(2)
    missing = SimResult(status="unavailable", cause="tooling", detail="ngspice was not found")
    monkeypatch.setattr("extrude.harness.loop.run_allowed", lambda _deck: missing)
    result = run("10k pull-up on reset to 3.3 V")
    assert result.status == "checked"


def test_one_pullup_is_not_an_i2c_pair():
    spec = resolve("10k pull-up on reset to 3.3 V")
    assert isinstance(spec, FrozenSpec)
    assert spec.values_si["n_lines"] == pytest.approx(1)
    assert spec.values_si["r_pull"] == pytest.approx(10000)
    bus = resolve("4.7k pull-ups on a 3.3 V I2C bus")
    assert isinstance(bus, FrozenSpec)
    assert bus.values_si["n_lines"] == pytest.approx(2)
