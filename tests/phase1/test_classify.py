"""Task words map to a closed list. They do not invent a circuit."""

from extrude.intake.classify import classify


def test_power_words_stay_on_the_list():
    assert classify("a buck from 5 V to 3.3 V") == "buck"
    assert classify("step-down converter") == "buck"
    assert classify("use an LDO") == "ldo"
    assert classify("linear regulator") == "ldo"
    assert classify("3.3 V regulator") == "ldo"
    assert classify("hold-up for 20 ms") == "holdup_mlcc"
    assert classify("dying gasp reservoir") == "holdup_mlcc"
    assert classify("blue LED") == "led"
    assert classify("swap the MCU from STM32 to ESP32") == "mcu_swap"


def test_a_vague_sentence_is_unknown():
    assert classify("Power an ESP32") == "unknown"
    assert classify("make it nice") == "unknown"
    assert classify("") == "unknown"


def test_buck_wins_over_a_status_led_and_led_stays_led_alone():
    assert classify("buck with a status LED") == "buck"
    assert classify("just an LED on the board") == "led"
