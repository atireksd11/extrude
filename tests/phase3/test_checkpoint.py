"""The shared capacitance number. Inputs are fixed here before the math is trusted."""

from unittest.mock import patch

import pytest

from extrude.intake.models import FrozenSpec, SlotOrigin
from extrude.ir.models import CircuitIR, Part
from extrude.physics import derive
from extrude.physics.models import CurveSource

_NOMINAL = 22e-6
_EFF = 11.4e-6
_TOL = 0.2


def _spec(task: str, **values: float) -> FrozenSpec:
    return FrozenSpec(
        task_class=task,  # type: ignore[arg-type]
        values_si=values,
        origins={key: SlotOrigin.user_span for key in values},
        defaults_version="2026-10-03",
        spec_hash="phase3",
    )


def _example_cap(**extra) -> Part:
    fields = dict(
        refdes="C1",
        kind="capacitor",
        capacitance=_NOMINAL,
        tolerance=_TOL,
        dielectric="X7R",
        voltage_rating=10,
        bias_v=4.7,
        curve_id="strategy_holdup_22u_4v7",
    )
    fields.update(extra)
    return Part(**fields)


def test_holdup_example_uses_the_checked_in_curve_and_the_tolerance_corner():
    design = CircuitIR(parts=[_example_cap()])
    values = derive(design, _spec("holdup_mlcc", c_min=10e-6, v_rail=4.7))
    cap = values.caps[0]
    assert cap.curve_id == "strategy_holdup_22u_4v7"
    assert cap.curve_source is CurveSource.vendor_table
    assert cap.c_eff == pytest.approx(_EFF, rel=1e-6)
    assert cap.c_use < cap.c_eff
    assert cap.c_use == pytest.approx(_EFF * (1 - _TOL), rel=1e-6)
    assert any(item.severity == "fail" for item in values.findings)


def test_generic_half_loss_does_not_hard_fail_the_example_or_a_25v_part():
    generic = CircuitIR(
        parts=[
            _example_cap(
                curve_id=None,
                manufacturer="other",
                series="other",
                case="0603",
                voltage_rating=10,
            )
        ]
    )
    rated = CircuitIR(
        parts=[
            Part(
                refdes="C1",
                kind="capacitor",
                capacitance=_NOMINAL,
                tolerance=_TOL,
                dielectric="X7R",
                voltage_rating=25,
                bias_v=5,
                case="1206",
                manufacturer="other",
                series="other",
            )
        ]
    )
    for design in (generic, rated):
        values = derive(design, _spec("holdup_mlcc", c_min=20e-6))
        assert values.caps[0].curve_source is CurveSource.generic_screen
        assert not any(item.severity == "fail" for item in values.findings)
        assert any(item.severity == "warn" for item in values.findings)


def test_two_callers_get_the_same_number():
    design = CircuitIR(parts=[_example_cap()])
    spec = _spec("holdup_mlcc", v_rail=4.7)
    assert derive(design, spec).model_dump() == derive(design, spec).model_dump()


def test_light_load_does_not_invent_ripple_and_heavy_load_uses_c_use():
    light = CircuitIR(
        f_sw=1e6,
        parts=[
            _example_cap(esr=0.01),
            Part(refdes="L1", kind="inductor", inductance=2.2e-6),
        ],
    )
    heavy_spec = _spec("buck", vin=5, vout=3.3, i_load=2)
    light_spec = _spec("buck", vin=5, vout=3.3, i_load=0.001)
    heavy = derive(light, heavy_spec)
    missed = derive(light, light_spec)
    cap = heavy.caps[0]
    delta_i = 3.3 * (1 - 3.3 / 5) / (1e6 * 2.2e-6)
    from_use = delta_i * (0.01 + 1 / (8 * 1e6 * cap.c_use))
    from_nominal = delta_i * (0.01 + 1 / (8 * 1e6 * cap.c_nominal))
    assert heavy.conduction == "ccm"
    assert heavy.ripple_pp == pytest.approx(from_use)
    assert heavy.ripple_pp != pytest.approx(from_nominal)
    assert missed.conduction == "dcm"
    assert missed.ripple_pp is None
    assert any(item.code == "ripple_not_covered" for item in missed.findings)


def test_derive_does_not_call_the_simulator():
    design = CircuitIR(parts=[_example_cap()])
    with patch("extrude.sim.api.run_allowed") as sim:
        derive(design, _spec("holdup_mlcc", v_rail=4.7))
    sim.assert_not_called()
