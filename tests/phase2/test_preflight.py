"""Wiring fixtures. A passing report is an empty block list, not a claim that the board is ready."""

from unittest.mock import patch

from extrude.checks import preflight
from extrude.checks.models import PreflightReport
from tests.phase2.fixtures import (
    bad_hanging_pin,
    bad_power_with_path_but_no_capacitor,
    bad_power_without_ground_path,
    bad_two_sources,
    bad_two_uart_drivers,
    good_ac_coupled_uart,
    good_mcu_rail,
    nc_pin_is_allowed,
)


def _rules(report: PreflightReport) -> set[str]:
    return {item.split(":", 1)[0] for item in report.blocking}


def test_two_good_designs_have_no_blocking_rules():
    for design in (good_mcu_rail(), good_ac_coupled_uart(), nc_pin_is_allowed()):
        report = preflight(design)
        assert report.blocking == []
        assert report.warnings == []


def test_bad_designs_name_the_rule():
    cases = [
        (bad_hanging_pin(), "hanging_pin"),
        (bad_two_sources(), "voltage_sources_on_one_node"),
        (bad_power_without_ground_path(), "power_pin_no_dc_path"),
        (bad_two_uart_drivers(), "drivers_on_one_net"),
        (bad_power_with_path_but_no_capacitor(), "power_rail_has_no_capacitor"),
    ]
    assert len(cases) >= 3
    for design, rule in cases:
        report = preflight(design)
        assert rule in _rules(report), report.blocking


def test_report_has_no_ripple_and_does_not_say_the_board_is_ready():
    report = preflight(good_mcu_rail())
    assert "ripple" not in PreflightReport.model_fields
    blob = report.model_dump_json().lower()
    assert "ripple" not in blob
    assert "ready" not in blob


def test_a_hanging_pin_does_not_call_the_simulator_or_the_physics():
    with patch("extrude.sim.api.run_allowed") as sim, patch("extrude.physics.api.derive") as physics:
        report = preflight(bad_hanging_pin())
    sim.assert_not_called()
    physics.assert_not_called()
    assert "hanging_pin" in _rules(report)
