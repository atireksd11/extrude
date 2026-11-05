"""The design door. No live model call."""

import json

from fastapi.testclient import TestClient

from extrude.api.server import app
from extrude.harness import clear_client, set_client
from extrude.intake.models import SlotOrigin
from extrude.memory import reset
from extrude.memory.db import insert_constraint, load_telemetry
from extrude.memory.models import ElectricalIdentity
from extrude.memory.rag import retrieve
from extrude.intake import resolve


def setup_function() -> None:
    reset()
    clear_client()


def teardown_function() -> None:
    clear_client()
    reset()


def _identity() -> ElectricalIdentity:
    return ElectricalIdentity(
        manufacturer="Example",
        capacitance=10e-6,
        dielectric="C0G",
        case="0805",
        voltage_rating=25,
    )


def test_a_divider_returns_a_netlist_and_the_stamp(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    monkeypatch.setenv("EXTRUDE_MODEL_KEY", "sk-test-secret")
    calls = {"n": 0}

    def client(prompt: str, seat: str) -> tuple[str, dict]:
        calls["n"] += 1
        return "{}", {}

    set_client(client)
    response = TestClient(app).post("/v1/design", json={"prompt": "12V to 3.3V divider", "mode": "interactive"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "checked"
    assert '(export (version "E")' in body["netlist"]
    assert "Pin Connectivity" in body["notice"]
    assert "Unverified: Thermal, RF/High-Speed, Mechanical Clearance." in body["notice"]
    assert calls["n"] == 0
    rows = load_telemetry()
    assert len(rows) == 1
    assert rows[0]["status"] == "checked"
    dumped = json.dumps(rows[0])
    assert "sk-test-secret" not in dumped


def test_an_led_without_a_supply_does_not_call_the_model(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    calls = {"n": 0}

    def client(prompt: str, seat: str) -> tuple[str, dict]:
        calls["n"] += 1
        raise AssertionError("the model was called")

    set_client(client)
    response = TestClient(app).post("/v1/design", json={"prompt": "20 mA LED", "mode": "interactive"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_info"
    assert body["question"] == "What supply voltage should the LED use?"
    assert body["netlist"] is None
    assert "Unverified: Thermal, RF/High-Speed, Mechanical Clearance." in body["notice"]
    assert calls["n"] == 0


def test_retrieval_keeps_the_matching_ban_and_at_most_three(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    spec = resolve("12V to 3.3V divider")
    for index in range(4):
        insert_constraint(
            task_class="divider",
            spec_hash=spec.spec_hash,
            prompt="12V to 3.3V divider",
            check_id=f"divider-ban-{index}",
            detail="divider bias failed",
            voltage=12,
            identity=_identity(),
            checker_version="2026-10-04",
            v_fail=12,
            i_fail=None,
            measured=1,
            limit=2,
        )
    insert_constraint(
        task_class="buck",
        spec_hash="buck-1",
        prompt="5 V to 3.3 V buck at 2 A",
        check_id="buck-only-ban",
        detail="buck ripple failed",
        voltage=5,
        identity=_identity(),
        checker_version="2026-10-04",
        v_fail=5,
        i_fail=None,
        measured=1,
        limit=2,
    )
    found = retrieve(spec, "12V to 3.3V divider")
    assert len(found) == 3
    assert "buck-only-ban" not in {row.check_id for row in found}
    response = TestClient(app).post("/v1/design", json={"prompt": "12V to 3.3V divider", "mode": "interactive"})
    shown = response.json()["constraints"]
    assert len(shown) <= 3
    assert "buck-only-ban" not in {row["check_id"] for row in shown}
    assert shown
    assert all(row["check_id"].startswith("divider-ban-") for row in shown)


def test_a_power_prompt_shows_the_model_only_the_matching_bans(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    buck = resolve("5 V to 3.3 V at 2 A")
    insert_constraint(
        task_class="buck",
        spec_hash=buck.spec_hash,
        prompt="5 V to 3.3 V at 2 A",
        check_id="buck-rail-ban",
        detail="the buck capacitor failed dc bias",
        voltage=5,
        identity=_identity(),
        checker_version="2026-10-04",
        v_fail=5,
        i_fail=None,
        measured=1,
        limit=2,
    )
    insert_constraint(
        task_class="holdup_mlcc",
        spec_hash="hold-1",
        prompt="hold-up capacitor bank",
        check_id="holdup-only-ban",
        detail="hold-up capacitor was not connected",
        voltage=4.7,
        identity=_identity(),
        checker_version="2026-10-04",
        v_fail=4.7,
        i_fail=None,
        measured=1,
        limit=2,
    )
    seen = []

    def client(prompt: str, seat: str) -> tuple[str, dict]:
        seen.append(prompt)
        return "not json", {}

    set_client(client)
    TestClient(app).post("/v1/design", json={"prompt": "5 V to 3.3 V at 2 A", "mode": "interactive"})
    assert seen
    assert seen[0].startswith("EMIT one JSON object.")
    assert "buck-rail-ban" in seen[0]
    assert "holdup-only-ban" not in seen[0]
    assert seen[0].index("EMIT one JSON object.") < seen[0].index("SPEC_HASH:")


def test_a_saved_design_miss_is_not_written_twice(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    from extrude.memory.db import load_constraints
    from extrude.memory.rag import remember_run

    spec = resolve("5 V to 3.3 V at 2 A")
    from extrude.memory import record
    from extrude.memory.models import AttributionEvent, PrimaryCause

    record(
        AttributionEvent(
            cause=PrimaryCause.model_design,
            spec_hash=spec.spec_hash,
            detail="bias",
            identity=_identity(),
            check_id="buck-rail-ban",
            checker_version="2026-10-04",
            measured=1,
            limit=2,
            v_fail=5,
        )
    )
    remember_run(spec, "5 V to 3.3 V at 2 A")
    remember_run(spec, "5 V to 3.3 V at 2 A")
    assert len(load_constraints()) == 1


def test_a_default_bus_voltage_stays_marked():
    spec = resolve("10k pull-ups on SMBus")
    assert spec.values_si["v_bus"] == 3.3
    assert spec.origins["v_bus"] is SlotOrigin.default
