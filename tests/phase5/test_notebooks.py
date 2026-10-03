"""One miss goes in one notebook. A 12 V block does not ban 3.3 V."""

import pytest

from extrude.harness.models import AttemptBudget
from extrude.memory import (
    design_rows,
    design_tries_used,
    from_simulator_log,
    identity_for,
    matching_blocks,
    record,
    remember_alias,
    request_rows,
    reset,
    tool_rows,
)
from extrude.memory.models import AttributionEvent, ElectricalIdentity, PrimaryCause

_HASH = "card-1"
_VERSION = "2026-10-03"


def setup_function() -> None:
    reset()


def _cap(case: str = "0805", capacitance: float = 22e-6) -> ElectricalIdentity:
    return ElectricalIdentity(
        manufacturer="Murata",
        capacitance=capacitance,
        dielectric="X7R",
        case=case,
        voltage_rating=10,
    )


def _design(identity: ElectricalIdentity, v_fail: float, measured: float = 11.4) -> AttributionEvent:
    return AttributionEvent(
        cause=PrimaryCause.model_design,
        spec_hash=_HASH,
        detail="capacitance collapsed",
        identity=identity,
        check_id="dc_bias",
        checker_version=_VERSION,
        v_fail=v_fail,
        measured=measured,
        limit=20,
    )


def test_twelve_volts_does_not_block_three_point_three_and_does_block_eleven():
    part = _cap()
    record(_design(part, v_fail=12))
    assert matching_blocks(part, "dc_bias", _VERSION, _HASH, v_new=3.3) == []
    assert len(matching_blocks(part, "dc_bias", _VERSION, _HASH, v_new=11)) == 1
    assert len(matching_blocks(part, "dc_bias", _VERSION, _HASH, v_new=12)) == 1


def test_an_alias_hits_and_an_unknown_suffix_does_not():
    part = _cap()
    remember_alias("GRM21BR61A226ME51L", part)
    remember_alias("C123456", part)
    record(_design(part, v_fail=12).model_copy(update={"orderable": "C123456", "identity": None}))
    assert identity_for("GRM21BR61A226ME51L") == part
    assert len(matching_blocks(part, "dc_bias", _VERSION, _HASH, v_new=12)) == 1
    assert identity_for("GRM21BR61A226ME51L-YFP") is None
    assert identity_for("C123456-YFP") is None


def test_a_singular_log_is_a_tool_miss_and_does_not_spend_a_try():
    budget = AttemptBudget()
    event = from_simulator_log("Warning: singular matrix: check nodes", _HASH)
    record(event)
    budget.model_design_used = design_tries_used(budget.model_design_used, event)
    assert budget.model_design_used == 0
    assert len(tool_rows()) == 1
    assert design_rows() == []
    assert request_rows() == []


def test_a_vague_request_wins_even_when_the_part_was_poor():
    budget = AttemptBudget()
    event = _design(_cap(), v_fail=12).model_copy(
        update={"spec_confirmed": False, "detail": "Power an ESP32"}
    )
    record(event)
    budget.model_design_used = design_tries_used(budget.model_design_used, event)
    assert budget.model_design_used == 0
    assert design_rows() == []
    assert len(request_rows()) == 1
    assert request_rows()[0].cause is PrimaryCause.spec_gap


def test_at_most_eight_blocks_are_shown_and_each_has_a_measured_number():
    part = _cap()
    for index in range(10):
        record(_design(part, v_fail=12, measured=index + 1))
    shown = matching_blocks(part, "dc_bias", _VERSION, _HASH, v_new=12)
    assert len(shown) == 8
    assert [row.measured for row in shown] == [10, 9, 8, 7, 6, 5, 4, 3]


def test_edges_around_the_block():
    part = _cap()
    record(_design(part, v_fail=12))
    assert matching_blocks(part, "dc_bias", _VERSION, _HASH, v_new=10.79) == []
    assert len(matching_blocks(part, "dc_bias", _VERSION, _HASH, v_new=10.8)) == 1
    assert matching_blocks(part, "dc_bias", "other", _HASH, v_new=12) == []
    assert matching_blocks(part, "dc_bias", _VERSION, "other", v_new=12) == []
    smaller = _cap(capacitance=10e-6)
    assert matching_blocks(smaller, "dc_bias", _VERSION, _HASH, v_new=12) == []
    reset()
    record(
        AttributionEvent(
            cause=PrimaryCause.model_design,
            spec_hash=_HASH,
            detail="too much current",
            identity=part,
            check_id="overcurrent",
            checker_version=_VERSION,
            i_fail=2,
            measured=3,
            limit=2,
        )
    )
    assert matching_blocks(part, "overcurrent", _VERSION, _HASH, i_new=0.5) == []
    assert len(matching_blocks(part, "overcurrent", _VERSION, _HASH, i_new=2)) == 1
    assert matching_blocks(part, "overcurrent", _VERSION, _HASH, v_new=12) == []


def test_five_failures_land_in_the_notebook_each_one_names():
    part = _cap()
    other = _cap(case="0603")
    budget = AttemptBudget()
    sequence = [
        _design(part, v_fail=12),
        from_simulator_log("timestep too small", _HASH),
        _design(part, v_fail=12).model_copy(update={"spec_confirmed": False}),
        _design(other, v_fail=12, measured=3),
        from_simulator_log("timeout", _HASH),
    ]
    for event in sequence:
        record(event)
        budget.model_design_used = design_tries_used(budget.model_design_used, event)
    assert len(design_rows()) == 2
    assert len(request_rows()) == 1
    assert len(tool_rows()) == 2
    assert budget.model_design_used == 2
    assert matching_blocks(part, "dc_bias", _VERSION, _HASH, v_new=3.3) == []
    assert len(matching_blocks(other, "dc_bias", _VERSION, _HASH, v_new=12)) == 1
