"""The model proposes. The checks decide. Canned calls do not use the network."""

import json
import os
from unittest.mock import patch

import pytest

from extrude.harness import clear_client, run, set_client
from extrude.ir.models import Part, Pin
from extrude.learn import propose_offline
from extrude.mcp import __doc__ as mcp_doc
from extrude.memory import design_rows, reset, tool_rows
from extrude.memory.models import ElectricalIdentity


def setup_function() -> None:
    reset()
    clear_client()


def teardown_function() -> None:
    clear_client()
    reset()


def _hash(prompt: str) -> str:
    for line in prompt.splitlines():
        if line.startswith("SPEC_HASH: "):
            return line.split(": ", 1)[1]
    raise AssertionError("prompt had no spec hash")


def _good(spec_hash: str) -> str:
    from tests.phase6.test_buck_trust import proposal
    _, body = proposal()
    body["spec_hash"] = spec_hash
    return json.dumps(body)


def _bad(spec_hash: str) -> str:
    body = json.loads(_good(spec_hash))
    body["pins"].append(Pin(refdes="U1", name="GPIO1", state="open").model_dump())
    body["identity"] = ElectricalIdentity(
        manufacturer="Murata",
        capacitance=10e-6,
        dielectric="C0G",
        case="0805",
        voltage_rating=10,
    ).model_dump()
    return json.dumps(body)


def test_a_bad_proposal_then_a_good_one_checks_with_no_network():
    seen = []

    def client(prompt: str, seat: str) -> tuple[str, dict]:
        seen.append((prompt, seat))
        spec_hash = _hash(prompt)
        text = _bad(spec_hash) if len(seen) == 1 else _good(spec_hash)
        if len(seen) == 1:
            return text, {"prompt_tokens": 3, "completion_tokens": 4, "cost_usd": 0.01}
        return text, {"prompt_tokens": 5, "completion_tokens": 6, "cost_usd": 0.02}

    set_client(client)
    with patch("extrude.harness.client.urllib.request.urlopen") as network:
        result = run("5 V to 3.3 V at 2 A")
    network.assert_not_called()
    assert result.status == "checked"
    assert result.attempts == 1
    assert result.cost_usd == pytest.approx(0.03)
    assert result.prompt_tokens == 8
    assert result.completion_tokens == 10
    assert "SPEC_HASH:" in seen[0][0]
    assert "BOUNDS_SI" in seen[0][0]
    assert "spec_hash is SPEC_HASH" in seen[0][0]
    assert "limits is BOUNDS_SI" in seen[0][0]
    assert "refdes and kind" in seen[0][0]
    assert "A capacitor does not conduct DC" in seen[0][0]
    assert "LAST_REJECTED:" in seen[1][0]
    assert "hanging_pin" in seen[1][0]
    assert "DO_NOT_REPEAT:" in seen[1][0]
    assert "measured" in seen[1][0]
    assert "PASSED_AND_LOCKED: none" in seen[1][0]
    assert len(design_rows()) == 1


def test_dropping_the_load_is_rejected():
    def client(prompt: str, seat: str) -> tuple[str, dict]:
        return json.dumps(
            {
                "spec_hash": _hash(prompt),
                "i_load": 0,
                "limits": {"vin": 5.0, "vout": 3.3, "i_load": 2.0, "ripple_pp": 0.03},
                "parts": [],
                "pins": [],
            }
        ), {}

    set_client(client)
    result = run("5 V to 3.3 V at 2 A")
    assert result.status == "stopped"
    assert "load" in (result.detail or "")
    assert result.attempts == 2


def test_unparseable_text_gets_format_retries_without_design_tries():
    calls = {"n": 0}

    def client(prompt: str, seat: str) -> tuple[str, dict]:
        calls["n"] += 1
        return "hello", {"prompt_tokens": 1, "completion_tokens": 1}

    set_client(client)
    result = run("5 V to 3.3 V at 2 A")
    assert calls["n"] == 3
    assert result.status == "stopped"
    assert result.attempts == 0
    assert result.cost_usd is None
    assert len(tool_rows()) == 0


def test_no_second_key_stops_after_two_design_misses(monkeypatch):
    monkeypatch.delenv("EXTRUDE_ESCALATION_KEY", raising=False)
    calls = {"n": 0}

    def client(prompt: str, seat: str) -> tuple[str, dict]:
        calls["n"] += 1
        return _bad(_hash(prompt)), {}

    set_client(client)
    result = run("5 V to 3.3 V at 2 A")
    assert calls["n"] == 2
    assert result.status == "stopped"
    assert result.attempts == 2


def test_a_second_key_gets_one_more_seat(monkeypatch):
    monkeypatch.setenv("EXTRUDE_ESCALATION_KEY", "test-key")
    seats = []

    def client(prompt: str, seat: str) -> tuple[str, dict]:
        seats.append(seat)
        spec_hash = _hash(prompt)
        text = _good(spec_hash) if seat == "escalation" else _bad(spec_hash)
        return text, {}

    set_client(client)
    result = run("5 V to 3.3 V at 2 A")
    assert seats == ["primary", "primary", "escalation"]
    assert result.status == "checked"


def test_vague_text_and_other_jobs_do_not_call_the_model():
    calls = {"n": 0}

    def client(prompt: str, seat: str) -> tuple[str, dict]:
        calls["n"] += 1
        return "{}", {}

    set_client(client)
    vague = run("Power an ESP32")
    led = run("20 mA LED")
    supplied = run("20 mA LED from 5 V")
    assert calls["n"] == 0
    assert vague.status == "needs_info"
    assert led.status == "needs_info"
    assert led.detail == "What supply voltage should the LED use?"
    assert supplied.status == "checked"
    assert supplied.netlist and '(part "LED")' in supplied.netlist


def test_fenced_json_is_read_and_a_tighter_limit_is_thrown_away():
    def fenced(prompt: str, seat: str) -> tuple[str, dict]:
        return "```json\n" + _good(_hash(prompt)) + "\n```", {}

    set_client(fenced)
    assert run("5 V to 3.3 V at 2 A").status == "checked"
    clear_client()
    reset()

    def tighter(prompt: str, seat: str) -> tuple[str, dict]:
        body = json.loads(_good(_hash(prompt)))
        body["limits"] = {"ripple_pp": 0.001}
        return json.dumps(body), {}

    set_client(tighter)
    result = run("5 V to 3.3 V at 2 A")
    assert result.status == "stopped"
    assert result.attempts == 2
    assert "limit" in (result.detail or "")


def test_a_holdup_without_a_capacitor_is_a_design_miss():
    seen = []

    def client(prompt: str, seat: str) -> tuple[str, dict]:
        seen.append(prompt)
        return json.dumps(
            {
                "spec_hash": _hash(prompt),
                "limits": {"v_rail": 4.7, "t_hold": 0.02, "c_min": 545e-6},
                "parts": [],
                "pins": [],
            }
        ), {}

    set_client(client)
    result = run("hold-up 4.7 V for 20 ms, 545 uF")
    assert result.status == "stopped"
    assert result.attempts == 2
    assert result.detail == seen[1].split("LAST_REJECTED: ", 1)[1]
    assert "LAST_REJECTED:" not in seen[0]
    repair = seen[1].split("LAST_REJECTED: ", 1)[1]
    assert repair.startswith("the hold-up capacitor is not connected.")
    assert "top-level pins" in repair
    assert "other pin net is GND" in repair
    assert "still not connected" in repair
    assert tool_rows() == []


def test_nested_holdup_pins_do_not_spend_a_design_try():
    from extrude.sim.models import SimResult

    def client(prompt: str, seat: str) -> tuple[str, dict]:
        return json.dumps(
            {
                "spec_hash": _hash(prompt),
                "limits": {"v_rail": 4.7, "t_hold": 0.02, "c_min": 545e-6},
                "parts": [
                    {
                        "refdes": "C1",
                        "kind": "capacitor",
                        "capacitance": 1000e-6,
                        "tolerance": 0,
                        "dielectric": "C0G",
                        "bias_v": 4.7,
                        "pins": [
                            {"name": "A", "net": "RAIL"},
                            {"name": "B", "net": "GND"},
                        ],
                    },
                    {
                        "refdes": "R1",
                        "kind": "resistor",
                        "pins": [
                            {"name": "A", "net": "RAIL"},
                            {"name": "B", "net": "GND"},
                        ],
                    },
                ],
            }
        ), {}

    set_client(client)
    crashed = SimResult(status="tooling", cause="tooling", detail="singular matrix")
    with patch("extrude.harness.loop.run_allowed", return_value=crashed):
        result = run("hold-up 4.7 V for 20 ms, 545 uF")
    assert result.attempts == 0
    assert result.status == "stopped"
    assert design_rows() == []
    assert len(tool_rows()) == 1


def test_a_simulator_crash_on_a_connected_holdup_does_not_spend_a_design_try():
    from extrude.sim.models import SimResult

    def client(prompt: str, seat: str) -> tuple[str, dict]:
        return json.dumps(
            {
                "spec_hash": _hash(prompt),
                "limits": {"v_rail": 4.7, "t_hold": 0.02, "c_min": 545e-6},
                "parts": [
                    Part(
                        refdes="C1",
                        kind="capacitor",
                        capacitance=1000e-6,
                        tolerance=0,
                        dielectric="C0G",
                        bias_v=4.7,
                    ).model_dump(),
                    Part(refdes="R1", kind="resistor").model_dump(),
                ],
                "pins": [
                    Pin(refdes="C1", name="A", net="RAIL", state="connected").model_dump(),
                    Pin(refdes="C1", name="B", net="GND", state="connected").model_dump(),
                    Pin(refdes="R1", name="A", net="RAIL", state="connected").model_dump(),
                    Pin(refdes="R1", name="B", net="GND", state="connected").model_dump(),
                    Pin(refdes="C1", name="GND", net="GND", state="connected", role="ground").model_dump(),
                ],
            }
        ), {}

    set_client(client)
    crashed = SimResult(status="tooling", cause="tooling", detail="singular matrix")
    with patch("extrude.harness.loop.run_allowed", return_value=crashed):
        result = run("hold-up 4.7 V for 20 ms, 545 uF")
    assert result.status == "stopped"
    assert result.attempts == 0
    assert len(tool_rows()) == 1
    assert design_rows() == []


def test_learn_and_mcp_are_still_not_built():
    with pytest.raises(NotImplementedError, match="not built"):
        propose_offline()
    assert mcp_doc is None or isinstance(mcp_doc, str)


def test_a_fake_bill_is_copied_and_a_missing_dollar_amount_is_not_invented():
    def client(prompt: str, seat: str) -> tuple[str, dict]:
        return _good(_hash(prompt)), {"prompt_tokens": 11, "completion_tokens": 7}

    set_client(client)
    result = run("5 V to 3.3 V at 2 A")
    assert result.status == "checked"
    assert result.prompt_tokens == 11
    assert result.completion_tokens == 7
    assert result.cost_usd is None
