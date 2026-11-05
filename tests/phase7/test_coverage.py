"""A finished run names the checks it ran and the three it never runs."""

from extrude.coverage.api import cover
from extrude.harness import run
from extrude.intake import resolve
from extrude.memory import reset
from extrude.sim.models import SimResult


def setup_function() -> None:
    reset()


def test_the_map_names_what_can_run_and_what_never_runs():
    buck = cover(resolve("5 V to 3.3 V at 2 A"))
    assert buck.by_check["ripple"] == "can"
    assert buck.by_check["heat-in-airflow"] == "cannot"
    assert buck.by_check["radios"] == "cannot"
    assert buck.by_check["fast memory"] == "cannot"
    led = cover(resolve("20 mA LED from 5 V"))
    assert led.by_check["lamp current"] == "can"
    assert led.by_check["heat-in-airflow"] == "cannot"


def test_a_checked_divider_lists_its_checks_and_the_open_gaps(monkeypatch):
    ratio = 4990 / (10000 + 4990)
    monkeypatch.setattr(
        "extrude.harness.loop.run_allowed",
        lambda _deck: SimResult(status="measured", measurements={"v_mid": ratio}),
    )
    result = run("10k and 4.99k divider, output at the midpoint")
    assert result.status == "checked"
    assert "divider ratio" in (result.notice or "")
    assert "parts-cost" in (result.notice or "")
    assert "heat-in-airflow" in (result.notice or "")
    assert "radios" in (result.notice or "")
    assert "fast memory" in (result.notice or "")


def test_a_missing_simulator_does_not_claim_the_divider_was_measured(monkeypatch):
    monkeypatch.setattr(
        "extrude.harness.loop.run_allowed",
        lambda _deck: SimResult(status="unavailable", cause="tooling", detail="ngspice was not found"),
    )
    result = run("10k and 4.99k divider, output at the midpoint")
    assert result.status == "checked"
    assert "divider ratio" not in (result.notice or "")
    assert "wiring" in (result.notice or "")
    assert "heat-in-airflow" in (result.notice or "")


def test_a_failed_ratio_is_not_listed_as_passed(monkeypatch):
    monkeypatch.setattr(
        "extrude.harness.loop.run_allowed",
        lambda _deck: SimResult(status="measured", measurements={"v_mid": 0.9}),
    )
    result = run("10k and 4.99k divider, output at the midpoint")
    assert result.status == "stopped"
    assert "Stopped during: divider ratio." in (result.notice or "")
    assert "divider ratio," not in (result.notice or "")
    assert "heat-in-airflow" in (result.notice or "")


def test_an_unanswered_led_checked_nothing():
    result = run("20 mA LED")
    assert result.status == "needs_info"
    assert "Checked: nothing." in (result.notice or "")
    assert "Unverified: Thermal, RF/High-Speed, Mechanical Clearance." in (result.notice or "")
    assert "heat-in-airflow" in (result.notice or "")
    assert "radios" in (result.notice or "")
    assert "fast memory" in (result.notice or "")
