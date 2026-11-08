"""Frozen buck acceptance requires wiring and bounded CCM ripple."""
import json
from pathlib import Path

import pytest

from extrude.harness import clear_client, set_client, run
from extrude.harness.proposal import parse_proposal
from extrude.intake import resolve
from extrude.physics.api import derive


def proposal():
    spec = resolve("5 V to 3.3 V at 2 A")
    return spec, dict(spec_hash=spec.spec_hash, limits=spec.values_si, i_load=2, f_sw=500000,
        parts=[dict(refdes="R1", kind="resistor", resistance=1.65), dict(refdes="U1", kind="ic"), dict(refdes="L1", kind="inductor", inductance=10e-6),
               dict(refdes="C1", kind="capacitor", capacitance=100e-6, dielectric="C0G", tolerance=0, bias_v=3.3, esr=0.001)],
        pins=[dict(refdes=ref, name=str(i), net=net, state="connected")
              for ref, nets in [("R1", ["OUT", "GND"]), ("U1", ["VIN", "SW", "GND"]), ("L1", ["SW", "OUT"]), ("C1", ["OUT", "GND"])]
              for i, net in enumerate(nets, 1)])


@pytest.mark.parametrize("case", ["empty", "unwired", "no_frequency", "dcm", "over_limit", "connected"])
def test_buck_gate(case):
    spec, body = proposal()
    if case == "empty":
        body.update(parts=[], pins=[])
    elif case == "unwired":
        body["pins"] = []
    elif case == "no_frequency":
        body.pop("f_sw")
    elif case == "dcm":
        body["parts"][2]["inductance"] = 1e-9
    elif case == "over_limit":
        body["parts"][3]["capacitance"] = 1e-9
    design, _ = parse_proposal(json.dumps(body), spec)
    values = derive(design, spec)
    failures = [x for x in values.findings if x.severity == "fail"]
    assert bool(failures) == (case != "connected")
    frozen = json.loads(Path("eval/proxy_tasks/buck/task.json").read_text())["card"]["values_si"]["ripple_pp"]
    assert spec.values_si["ripple_pp"] == frozen
    if case == "connected":
        assert values.ripple_pp <= frozen
    set_client(lambda prompt, seat: (json.dumps(body), {}))
    try:
        result = run("5 V to 3.3 V at 2 A")
    finally:
        clear_client()
    assert (result.status == "checked") == (case == "connected")
    if case != "connected":
        assert "Verified: Pin Connectivity, Parts cost" not in (result.notice or "")
