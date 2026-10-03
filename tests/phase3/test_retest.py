"""Cases outside the first checkpoint."""

import pytest

from extrude.intake.models import FrozenSpec, SlotOrigin
from extrude.ir.models import CircuitIR, Part
from extrude.physics import derive
from extrude.physics.models import CurveSource


def _spec(task: str, **values: float) -> FrozenSpec:
    return FrozenSpec(
        task_class=task,  # type: ignore[arg-type]
        values_si=values,
        origins={key: SlotOrigin.user_span for key in values},
        defaults_version="2026-10-03",
        spec_hash="retest",
    )


def _cap(**extra) -> Part:
    fields = dict(
        refdes="C1",
        kind="capacitor",
        capacitance=10e-6,
        tolerance=0.1,
        dielectric="X7R",
        bias_v=5,
    )
    fields.update(extra)
    return Part(**fields)


def test_c0g_film_and_electrolytic_keep_nominal_capacitance():
    for dielectric in ("C0G", "film", "electrolytic"):
        values = derive(
            CircuitIR(parts=[_cap(dielectric=dielectric, bias_v=12, voltage_rating=6.3)]),
            _spec("holdup_mlcc"),
        )
        cap = values.caps[0]
        assert cap.curve_source is CurveSource.not_class_ii
        assert cap.c_eff == pytest.approx(10e-6)
        assert cap.c_use == pytest.approx(10e-6 * 0.9)


def test_same_series_match_may_fail_and_midpoint_is_between_the_table_points():
    matched = derive(
        CircuitIR(
            parts=[
                Part(
                    refdes="C1",
                    kind="capacitor",
                    capacitance=22e-6,
                    tolerance=0.2,
                    dielectric="X7R",
                    voltage_rating=10,
                    manufacturer="example",
                    series="holdup-demo",
                    case="0805",
                    bias_v=4.7,
                )
            ]
        ),
        _spec("holdup_mlcc", c_min=10e-6),
    )
    assert matched.caps[0].curve_source is CurveSource.same_mfr_series
    assert matched.caps[0].curve_id == "strategy_holdup_22u_4v7"
    assert any(item.severity == "fail" for item in matched.findings)
    mid = derive(
        CircuitIR(
            parts=[
                Part(
                    refdes="C1",
                    kind="capacitor",
                    capacitance=22e-6,
                    tolerance=0,
                    dielectric="X7R",
                    bias_v=2.35,
                    curve_id="strategy_holdup_22u_4v7",
                )
            ]
        ),
        _spec("holdup_mlcc"),
    )
    low, high = 0.518181818182, 1.0
    ratio = mid.caps[0].c_eff / 22e-6
    assert min(low, high) < ratio < max(low, high)


def test_bias_past_the_table_does_not_invent_a_new_slope():
    values = derive(
        CircuitIR(
            parts=[
                Part(
                    refdes="C1",
                    kind="capacitor",
                    capacitance=22e-6,
                    tolerance=0,
                    dielectric="X7R",
                    bias_v=12,
                    curve_id="strategy_holdup_22u_4v7",
                )
            ]
        ),
        _spec("holdup_mlcc"),
    )
    assert values.caps[0].c_eff == pytest.approx(22e-6 * 0.2)
    assert any(item.code == "bias_above_curve" for item in values.findings)


def test_unknown_bias_does_not_pretend_the_part_lost_half():
    values = derive(
        CircuitIR(parts=[_cap(bias_v=None, capacitance=22e-6, tolerance=0)]),
        _spec("holdup_mlcc", c_min=21e-6),
    )
    assert values.caps[0].c_eff == pytest.approx(22e-6)
    assert any(item.code == "bias_unknown" for item in values.findings)
    assert not any(item.severity == "fail" for item in values.findings)


def test_parallel_caps_share_the_sum_of_use_values_in_the_ripple():
    design = CircuitIR(
        f_sw=1e6,
        parts=[
            _cap(refdes="C1", capacitance=22e-6, tolerance=0.2, esr=0.01, bias_v=3.3, curve_id="strategy_holdup_22u_4v7"),
            _cap(refdes="C2", capacitance=22e-6, tolerance=0.2, esr=0.01, bias_v=3.3, curve_id="strategy_holdup_22u_4v7"),
            Part(refdes="L1", kind="inductor", inductance=2.2e-6),
        ],
    )
    values = derive(design, _spec("buck", vin=5, vout=3.3, i_load=2))
    c_use = sum(cap.c_use for cap in values.caps)
    delta_i = 3.3 * (1 - 3.3 / 5) / (1e6 * 2.2e-6)
    expected = delta_i * (0.02 + 1 / (8 * 1e6 * c_use))
    assert values.ripple_pp == pytest.approx(expected)
    assert c_use != pytest.approx(44e-6)


def test_third_pass_does_not_lie_about_capacitance():
    zero = derive(
        CircuitIR(
            parts=[
                Part(
                    refdes="C1",
                    kind="capacitor",
                    capacitance=22e-6,
                    tolerance=0,
                    dielectric="X7R",
                    bias_v=0,
                )
            ]
        ),
        _spec("holdup_mlcc", c_min=20e-6),
    )
    assert zero.caps[0].c_eff == pytest.approx(22e-6)
    assert not any(item.code == "capacitance_below_minimum" for item in zero.findings)
    percent = derive(
        CircuitIR(
            parts=[
                Part(
                    refdes="C1",
                    kind="capacitor",
                    capacitance=22e-6,
                    tolerance=20,
                    dielectric="C0G",
                    bias_v=5,
                )
            ]
        ),
        _spec("holdup_mlcc"),
    )
    assert percent.caps[0].c_use == pytest.approx(22e-6)
    assert percent.caps[0].c_use > 0
    assert any(item.code == "tolerance_unreadable" for item in percent.findings)
    spaced = derive(
        CircuitIR(
            parts=[
                Part(
                    refdes="C1",
                    kind="capacitor",
                    capacitance=22e-6,
                    tolerance=0,
                    dielectric="X7R ",
                    bias_v=4.7,
                    curve_id="strategy_holdup_22u_4v7",
                )
            ]
        ),
        _spec("holdup_mlcc"),
    )
    assert spaced.caps[0].c_eff == pytest.approx(11.4e-6, rel=1e-6)
    rescued = derive(
        CircuitIR(
            parts=[
                Part(
                    refdes="C1",
                    kind="capacitor",
                    capacitance=22e-6,
                    tolerance=0.2,
                    dielectric="X7R",
                    bias_v=4.7,
                    curve_id="strategy_holdup_22u_4v7",
                ),
                Part(
                    refdes="C2",
                    kind="capacitor",
                    capacitance=100e-6,
                    tolerance=0,
                    dielectric="X7R",
                    bias_v=5,
                    voltage_rating=6.3,
                ),
            ]
        ),
        _spec("holdup_mlcc", c_min=10e-6),
    )
    assert any(item.severity == "fail" for item in rescued.findings)
    mixed = derive(
        CircuitIR(
            f_sw=1e6,
            parts=[
                Part(
                    refdes="Cin",
                    kind="capacitor",
                    capacitance=100e-6,
                    tolerance=0,
                    dielectric="electrolytic",
                    bias_v=5,
                    esr=0.05,
                ),
                Part(
                    refdes="Cout",
                    kind="capacitor",
                    capacitance=10e-6,
                    tolerance=0,
                    dielectric="C0G",
                    bias_v=3.3,
                    esr=0.01,
                ),
                Part(refdes="L1", kind="inductor", inductance=2.2e-6),
            ],
        ),
        _spec("buck", vin=5, vout=3.3, i_load=2),
    )
    delta_i = 3.3 * (1 - 3.3 / 5) / (1e6 * 2.2e-6)
    output_only = delta_i * (0.01 + 1 / (8 * 1e6 * 10e-6))
    assert mixed.ripple_pp == pytest.approx(output_only)


def test_second_pass_cases():
    negative = derive(
        CircuitIR(
            parts=[
                Part(
                    refdes="C1",
                    kind="capacitor",
                    capacitance=22e-6,
                    tolerance=0,
                    dielectric="X7R",
                    bias_v=-4.7,
                    curve_id="strategy_holdup_22u_4v7",
                )
            ]
        ),
        _spec("holdup_mlcc"),
    )
    assert negative.caps[0].c_eff == pytest.approx(11.4e-6, rel=1e-6)
    assert negative.caps[0].v_dc == 4.7
    typo = derive(
        CircuitIR(
            parts=[
                Part(
                    refdes="C1",
                    kind="capacitor",
                    capacitance=22e-6,
                    tolerance=0.2,
                    dielectric="X7R",
                    bias_v=4.7,
                    curve_id="missing",
                )
            ]
        ),
        _spec("holdup_mlcc", c_min=15e-6),
    )
    assert typo.caps[0].curve_source is CurveSource.generic_screen
    assert not any(item.severity == "fail" for item in typo.findings)
    buck = derive(
        CircuitIR(parts=[Part(refdes="U1", kind="ic", theta_ja=100)]),
        _spec("buck", vin=12, vout=3.3, i_load=2),
    )
    assert buck.tj_estimate_c is None
    assert buck.heat_note is None
    flat = derive(
        CircuitIR(
            f_sw=1e6,
            parts=[
                Part(refdes="L1", kind="inductor", inductance=1e-6),
                Part(refdes="C1", kind="capacitor", capacitance=10e-6, dielectric="C0G", tolerance=0, bias_v=5),
            ],
        ),
        _spec("buck", vin=5, vout=5, i_load=1),
    )
    assert flat.ripple_pp is None
    assert flat.conduction == "not_a_switcher"


def test_ldo_heat_is_labeled_a_still_air_estimate():
    values = derive(
        CircuitIR(parts=[Part(refdes="U1", kind="ic", theta_ja=100)]),
        _spec("ldo", vin=5, vout=3.3, i_load=0.2),
    )
    assert values.p_diss_w == pytest.approx(0.34)
    assert values.tj_estimate_c == pytest.approx(25 + 0.34 * 100)
    assert values.heat_note == "estimate_still_air_datasheet"
