"""Hostile sentences. These were written to break the card, not to repeat the first tests."""

import pytest

from extrude.harness import run
from extrude.intake import confirm, describe, resolve
from extrude.intake.errors import SpecRejected
from extrude.intake.hashing import card_hash
from extrude.intake.models import FrozenSpec, NeedsInfo, SlotOrigin


def test_labels_beat_left_to_right_order():
    card = resolve("output 3.3 V from input 5 V at 2 A")
    assert isinstance(card, FrozenSpec)
    assert card.values_si["vin"] == 5
    assert card.values_si["vout"] == 3.3
    assert card.origins["ripple_pp"] is SlotOrigin.default


def test_two_currents_are_not_silently_picked():
    result = resolve("5 V to 3.3 V at 2 A and also 500 mA")
    assert isinstance(result, NeedsInfo)
    assert "ambiguous_numbers" in result.missing


def test_words_are_not_turned_into_numbers():
    result = resolve("five volts to 3.3 V at 2 A")
    assert isinstance(result, NeedsInfo)
    assert not isinstance(result, FrozenSpec)


def test_scientific_notation_does_not_become_zero_volts():
    result = resolve("5e0 V to 3.3 V at 2 A")
    assert isinstance(result, NeedsInfo)
    blob = result.model_dump_json()
    assert '"vin": 0' not in blob
    assert "0.0" not in blob


def test_a_typed_one_millivolt_ripple_is_not_the_default():
    card = resolve("5 V to 3.3 V at 2 A, keep ripple under 1 mV")
    assert isinstance(card, FrozenSpec)
    assert card.values_si["ripple_pp"] == pytest.approx(0.001)
    assert card.origins["ripple_pp"] is SlotOrigin.user_span
    plain = resolve("5 V to 3.3 V at 2 A")
    assert isinstance(plain, FrozenSpec)
    assert card.spec_hash != plain.spec_hash


def test_the_same_default_value_is_a_different_card_when_the_user_typed_it():
    typed = resolve("5V to 3.3V at 2A ripple 30mV")
    assumed = resolve("5V to 3.3V at 2A")
    assert isinstance(typed, FrozenSpec)
    assert isinstance(assumed, FrozenSpec)
    assert typed.values_si["ripple_pp"] == assumed.values_si["ripple_pp"]
    assert typed.origins["ripple_pp"] is SlotOrigin.user_span
    assert assumed.origins["ripple_pp"] is SlotOrigin.default
    assert typed.spec_hash != assumed.spec_hash


def test_confirm_accepts_the_card_it_just_made_and_rejects_a_forged_hash():
    text = "5 V to 3.3 V at 2 A"
    card = resolve(text)
    assert isinstance(card, FrozenSpec)
    assert confirm(text, card).spec_hash == card.spec_hash
    forged = card.model_copy(update={"spec_hash": "0" * 64})
    with pytest.raises(SpecRejected):
        confirm(text, forged)


def test_a_default_origin_with_a_tighter_number_is_rejected():
    text = "5 V to 3.3 V at 2 A"
    card = resolve(text)
    assert isinstance(card, FrozenSpec)
    tighter = card.model_copy(update={"values_si": {**card.values_si, "ripple_pp": 0.001}})
    tighter = tighter.model_copy(update={"spec_hash": card_hash(tighter)})
    with pytest.raises(SpecRejected):
        confirm(text, tighter)


def test_a_regulator_is_not_given_a_buck_ripple_default():
    card = resolve("regulator from 12 V to 5 V at 1 A")
    assert isinstance(card, FrozenSpec)
    assert card.task_class == "ldo"
    assert "ripple_pp" not in card.values_si


def test_holdup_and_led_and_mcu_do_not_become_a_buck():
    hold = resolve("size the hold-up capacitor")
    led = resolve("20 mA LED")
    bare_led = resolve("status LED")
    swap = resolve("swap the MCU from STM32 to ESP32")
    assert isinstance(hold, NeedsInfo)
    assert "buck" not in hold.model_dump_json()
    assert "capacitance" in hold.question
    stray = resolve("Power an ESP32, ripple 1 mV")
    assert isinstance(stray, NeedsInfo)
    assert not isinstance(stray, FrozenSpec)
    assert isinstance(led, FrozenSpec)
    assert led.task_class == "led"
    assert led.values_si["i_led"] == pytest.approx(0.02)
    assert "ripple_pp" not in led.values_si
    assert isinstance(bare_led, NeedsInfo)
    assert isinstance(swap, FrozenSpec)
    assert swap.labels["from_part"] == "STM32"
    assert swap.labels["to_part"] == "ESP32"
    assert "you typed this" in describe(swap)


def test_hyphen_newlines_and_current_first_still_freeze_the_same_buck():
    spaced = resolve("5 V to 3.3 V at 2 A")
    hyphen = resolve("5V-3.3V 2A")
    wrapped = resolve("5 V to\n3.3 V at\t2 A")
    current_first = resolve("2 A at 5 volts to 3.3 volts")
    assert isinstance(spaced, FrozenSpec)
    for other in (hyphen, wrapped, current_first):
        assert isinstance(other, FrozenSpec)
        assert other.values_si["vin"] == 5
        assert other.values_si["vout"] == 3.3
        assert other.values_si["i_load"] == 2
        assert other.spec_hash == spaced.spec_hash


def test_a_named_buck_that_steps_up_does_not_freeze():
    result = resolve("buck from 3.3 V to 12 V at 1 A")
    assert isinstance(result, NeedsInfo)


def test_the_front_door_still_refuses_a_finished_card():
    with pytest.raises(NotImplementedError, match="not built"):
        run("5 V to 3.3 V at 2 A")


def test_ordinary_sentences_the_first_pass_missed():
    powered = resolve("Power an ESP32 from 5 V to 3.3 V at 2 A")
    polite = resolve("I want to use 5 V to 3.3 V at 2 A")
    ordered = resolve("into 3.3 V from 5 V at 2 A")
    plain = resolve("5 V to 3.3 V at 2 A")
    assert isinstance(plain, FrozenSpec)
    for card in (powered, polite, ordered):
        assert isinstance(card, FrozenSpec)
        assert card.task_class == "buck"
        assert card.values_si["vin"] == 5
        assert card.values_si["vout"] == 3.3
        assert card.values_si["i_load"] == 2
        assert card.spec_hash == plain.spec_hash
    hold = resolve("hold-up 4.7 V for 20 ms, 545 uF")
    assert isinstance(hold, FrozenSpec)
    assert hold.task_class == "holdup_mlcc"
    assert hold.values_si["v_rail"] == pytest.approx(4.7)
    assert hold.values_si["t_hold"] == pytest.approx(0.02)
    assert hold.values_si["c_min"] == pytest.approx(545e-6)
    assert all(origin is SlotOrigin.user_span for origin in hold.origins.values())
    swap = resolve("replace the STM32 with an ESP32")
    assert isinstance(swap, FrozenSpec)
    assert swap.labels == {"from_part": "STM32", "to_part": "ESP32"}


def test_the_card_a_person_reads_names_every_source():
    card = resolve("5 V to 3.3 V at 2 A")
    assert isinstance(card, FrozenSpec)
    text = describe(card)
    assert "Task: buck" in text
    assert "Defaults version: 2026-10-03" in text
    assert "vin: 5 V (you typed this, from '5 V')" in text
    assert "vout: 3.3 V (you typed this, from '3.3 V')" in text
    assert "i_load: 2 A (you typed this, from '2 A')" in text
    assert "ripple_pp: 30 mV (assumed default, from '30 mV')" in text
    assert card.spec_hash in text
