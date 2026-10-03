"""The requirement card freezes only numbers the person actually typed."""

import pytest

from extrude.harness import run
from extrude.intake import confirm, describe, resolve
from extrude.intake.errors import SpecRejected
from extrude.intake.models import FrozenSpec, NeedsInfo, SlotOrigin


def test_power_an_esp32_does_not_invent_a_ripple_or_a_design():
    result = resolve("Power an ESP32")
    assert isinstance(result, NeedsInfo)
    blob = result.model_dump_json().lower()
    assert "1 mv" not in blob
    assert "0.001" not in blob
    assert result.question.strip().endswith("?")
    with pytest.raises(NotImplementedError, match="not built"):
        run("Power an ESP32")


def test_a_complete_step_down_freezes_and_shows_the_default_ripple():
    text = "5 V to 3.3 V at 2 A"
    card = resolve(text)
    assert isinstance(card, FrozenSpec)
    assert card.task_class == "buck"
    assert card.values_si["vin"] == 5
    assert card.values_si["vout"] == 3.3
    assert card.values_si["i_load"] == 2
    assert card.values_si["ripple_pp"] == pytest.approx(0.03)
    assert card.origins["vin"] is SlotOrigin.user_span
    assert card.origins["vout"] is SlotOrigin.user_span
    assert card.origins["i_load"] is SlotOrigin.user_span
    assert card.origins["ripple_pp"] is SlotOrigin.default
    assert card.defaults_version == "2026-10-03"
    assert card.spec_hash
    shown = describe(card)
    assert "you typed this" in shown
    assert "assumed default" in shown
    assert "30 mV" in shown
    assert "5 V" in shown
    with pytest.raises(NotImplementedError, match="not built"):
        run(text)


def test_missing_load_current_does_not_freeze_a_card():
    result = resolve("5 V to 3.3 V")
    assert isinstance(result, NeedsInfo)
    assert "i_load" in result.missing


def test_a_hand_edit_that_tightens_ripple_is_rejected():
    text = "5 V to 3.3 V at 2 A"
    card = resolve(text)
    assert isinstance(card, FrozenSpec)
    edited = card.model_copy(
        update={
            "values_si": {**card.values_si, "ripple_pp": 0.001},
            "origins": {**card.origins, "ripple_pp": SlotOrigin.user_span},
        }
    )
    with pytest.raises(SpecRejected):
        confirm(text, edited)


def test_thirty_millivolts_and_point_zero_three_volts_hash_the_same():
    typed_mv = resolve("5V to 3.3V at 2A ripple 30 mV")
    typed_v = resolve("5V to 3.3V at 2A ripple 0.03 V")
    assert isinstance(typed_mv, FrozenSpec)
    assert isinstance(typed_v, FrozenSpec)
    assert typed_mv.origins["ripple_pp"] is SlotOrigin.user_span
    assert typed_v.origins["ripple_pp"] is SlotOrigin.user_span
    assert typed_mv.spec_hash == typed_v.spec_hash


def test_a_step_up_is_not_called_a_buck():
    result = resolve("3.3 V to 12 V at 1 A")
    assert isinstance(result, NeedsInfo)
    assert result.question.strip().endswith("?")
