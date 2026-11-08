"""A close reply is read. A changed limit is still rejected."""

import json

import pytest

from extrude.harness import clear_client, run, set_client
from extrude.harness.proposal import parse_proposal
from extrude.intake import resolve
from extrude.memory import reset


def setup_function() -> None:
    reset()
    clear_client()


def teardown_function() -> None:
    clear_client()
    reset()


def test_aliases_and_unit_strings_fit_the_design_file():
    spec = resolve("5 V to 3.3 V at 2 A")
    text = json.dumps(
        {
            "spec_hash": "  " + spec.spec_hash + "  ",
            "limits": {"vin": "5 V", "vout": "3.3V", "i_load": "2A", "ripple_pp": "30mV"},
            "parts": [
                {"ref": "U1", "mpn": "example"},
                {"refdes": "C1", "capacitance": "10uF", "dielectric": "C0G"},
                "V1",
            ],
            "pins": [
                {"ref": "U1", "name": "VDD", "net": "3V3", "role": "power"},
                {"ref": "U1", "name": "GND", "net": "GND", "role": "gnd"},
                {"ref": "C1", "net": "3V3"},
                {"ref": "C1", "net": "GND"},
                {"ref": "V1", "name": "+", "net": "3V3", "role": "positive"},
                {"ref": "V1", "name": "-", "net": "GND", "role": "negative"},
            ],
        }
    )
    design, _identity = parse_proposal(text, spec)
    kinds = {part.refdes: part.kind for part in design.parts}
    assert kinds == {"U1": "ic", "C1": "capacitor", "V1": "ideal_voltage_source"}
    assert design.parts[1].capacitance == pytest.approx(10e-6)
    assert all(pin.state == "connected" for pin in design.pins)


def test_a_reply_that_uses_aliases_can_be_checked_without_a_second_call():
    def client(prompt: str, seat: str) -> tuple[str, dict]:
        spec_hash = next(line.split(": ", 1)[1] for line in prompt.splitlines() if line.startswith("SPEC_HASH: "))
        body = {
            "spec_hash": spec_hash,
            "limits": {"vin": "5V", "vout": "3.3V", "i_load": "2A", "ripple_pp": "30 mV"},
            "parts": [
                {"ref": "U1"},
                {"ref": "C1", "value": "10uF", "dielectric": "C0G", "tolerance": 0},
                {"ref": "V1"},
            ],
            "pins": [
                {"ref": "U1", "name": "VDD", "net": "3V3", "role": "power"},
                {"ref": "U1", "name": "GND", "net": "GND", "role": "ground"},
                {"ref": "C1", "net": "3V3"},
                {"ref": "C1", "net": "GND"},
                {"ref": "V1", "name": "+", "net": "3V3"},
                {"ref": "V1", "name": "-", "net": "GND"},
            ],
        }
        # This positive harness fixture must be a real buck, not a rail source.
        body["f_sw"] = 500000
        body["parts"].extend([{"ref": "L1", "value": "10uH"}, {"ref": "R1", "kind": "resistor"}])
        body["pins"].extend([
            {"ref": "U1", "name": "SW", "net": "SW"},
            {"ref": "U1", "name": "VIN", "net": "VIN"},
            {"ref": "L1", "name": "1", "net": "SW"},
            {"ref": "L1", "name": "2", "net": "3V3"},
            {"ref": "R1", "name": "1", "net": "3V3"},
            {"ref": "R1", "name": "2", "net": "GND"},
        ])
        return json.dumps(body), {"prompt_tokens": 1, "completion_tokens": 1, "cost_usd": 0.01}

    set_client(client)
    result = run("5 V to 3.3 V at 2 A")
    assert result.status == "checked"
    assert result.attempts == 0


def test_pins_nested_on_a_part_are_lifted_and_a_same_net_pair_is_not():
    spec = resolve("hold-up 4.7 V for 20 ms, 545 uF")
    text = json.dumps(
        {
            "spec_hash": spec.spec_hash,
            "limits": {"v_rail": 4.7, "t_hold": 0.02, "c_min": 545e-6},
            "parts": [
                {
                    "refdes": "C1",
                    "kind": "capacitor",
                    "capacitance": 680e-6,
                    "pins": [
                        {"name": "1", "net": "RAIL"},
                        {"name": "2", "net": "GND"},
                    ],
                }
            ],
        }
    )
    design, _identity = parse_proposal(text, spec)
    nets = {pin.net for pin in design.pins if pin.refdes == "C1"}
    assert nets == {"RAIL", "GND"}
    same = json.dumps(
        {
            "spec_hash": spec.spec_hash,
            "limits": {"v_rail": 4.7, "t_hold": 0.02, "c_min": 545e-6},
            "parts": [
                {
                    "refdes": "C1",
                    "kind": "capacitor",
                    "capacitance": 680e-6,
                    "pins": [
                        {"name": "1", "net": "RAIL"},
                        {"name": "2", "net": "RAIL"},
                    ],
                }
            ],
        }
    )
    tied, _identity = parse_proposal(same, spec)
    from extrude.harness.loop import _holdup_cap_is_connected

    assert _holdup_cap_is_connected(design) is True
    assert _holdup_cap_is_connected(tied) is False
    one = json.loads(text)
    one["parts"][0]["pins"] = [{"name": "1", "net": "RAIL"}]
    single, _identity = parse_proposal(json.dumps(one), spec)
    assert _holdup_cap_is_connected(single) is False
    grounds = json.loads(text)
    grounds["parts"][0]["pins"] = [
        {"name": "1", "net": "GND"},
        {"name": "2", "net": "gnd"},
    ]
    aliased, _identity = parse_proposal(json.dumps(grounds), spec)
    assert _holdup_cap_is_connected(aliased) is False
    mixed = json.loads(text)
    mixed["pins"] = [{"refdes": "C1", "name": "1", "net": "RAIL"}]
    mixed["parts"][0]["pins"] = [
        {"name": "1", "net": "RAIL"},
        {"name": "2", "net": "GND"},
    ]
    both, _identity = parse_proposal(json.dumps(mixed), spec)
    assert {pin.net for pin in both.pins if pin.refdes == "C1"} == {"RAIL", "GND"}


def test_pin_names_written_as_plain_nets_are_lifted():
    spec = resolve("hold-up 4.7 V for 20 ms, 545 uF")
    text = json.dumps(
        {
            "spec_hash": spec.spec_hash,
            "limits": {"v_rail": 4.7, "t_hold": 0.02, "c_min": 545e-6},
            "parts": [{"refdes": "C1", "kind": "capacitor", "capacitance": 680e-6, "pins": ["RAIL", "GND"]}],
        }
    )
    design, _identity = parse_proposal(text, spec)
    assert {pin.net for pin in design.pins} == {"RAIL", "GND"}


def test_a_pin_map_is_lifted_without_a_second_try():
    spec = resolve("hold-up 4.7 V for 20 ms, 545 uF")
    text = json.dumps(
        {
            "spec_hash": spec.spec_hash,
            "limits": {"v_rail": 4.7, "t_hold": 0.02, "c_min": 545e-6},
            "parts": [
                {
                    "ref": "C1",
                    "kind": "capacitor",
                    "capacitance": 680e-6,
                    "connections": {"1": "RAIL", "2": {"net": "GND"}},
                }
            ],
        }
    )
    design, _identity = parse_proposal(text, spec)
    assert {(pin.name, pin.net) for pin in design.pins} == {("1", "RAIL"), ("2", "GND")}


def test_a_changed_limit_is_still_rejected():
    spec = resolve("5 V to 3.3 V at 2 A")
    text = json.dumps(
        {
            "spec_hash": spec.spec_hash,
            "i_load": 2,
            "limits": {"vin": "5V", "vout": "3.3V", "i_load": "1A", "ripple_pp": "30mV"},
            "parts": [],
            "pins": [],
        }
    )
    try:
        parse_proposal(text, spec)
    except Exception as exc:
        assert "limit" in str(exc)
        return
    raise AssertionError("a changed load was accepted")
