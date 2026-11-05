"""Copilot door. Audit stays local. Generate may call Luna only under the cap."""

from pathlib import Path

from fastapi.testclient import TestClient

from extrude.api.server import app
from extrude.harness import clear_client, set_client
from extrude.intake import resolve
from extrude.copilot.budget import clear_inflight
from extrude.copilot.__main__ import main
from extrude.memory import reset
from extrude.memory.db import insert_telemetry
from extrude.sim.models import SimResult

_SCAD = Path(__file__).resolve().parent / "fixtures" / "parse" / "enclosure.scad"
_FLOATING = """
(export (version "E")
  (components
    (comp (ref "U1")
      (value "MCU")
      (libsource (lib "Connector") (part "Conn") (description ""))
    )
  )
  (nets
    (net (code "1") (name "nRST")
      (node (ref "U1") (pin "NRST"))
    )
  )
)
"""


def setup_function() -> None:
    reset()
    clear_client()


def teardown_function() -> None:
    clear_client()
    reset()
    clear_inflight()


def test_audit_openscad_reports_the_small_hole(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    response = TestClient(app).post(
        "/v1/copilot",
        json={
            "artifact": _SCAD.read_text(encoding="utf-8"),
            "filename": "enclosure.scad",
            "filament": "PETG",
            "offline": True,
        },
    )
    body = response.json()
    assert body["mode"] == "audit"
    assert body["status"] == "stopped"
    assert body["cost_usd"] is None
    assert any(item["check_id"] == "hole_undersized_for_insert" for item in body["violations"])


def test_audit_netlist_reports_a_floating_reset():
    response = TestClient(app).post(
        "/v1/copilot",
        json={"artifact": _FLOATING, "filename": "board.net", "offline": True},
    )
    body = response.json()
    assert body["status"] == "stopped"
    assert "control_pin_floating:U1.NRST" in body["detail"]


def test_generate_divider_stays_offline(monkeypatch):
    spec = resolve("10k/10k divider 5 V to 3.3 V")
    expected = 5 * spec.values_si["r_bot"] / (spec.values_si["r_top"] + spec.values_si["r_bot"])
    monkeypatch.setattr(
        "extrude.harness.loop.run_allowed",
        lambda _deck: SimResult(status="measured", measurements={"v_mid": expected}),
    )
    calls = {"n": 0}

    def client(prompt: str, seat: str):
        calls["n"] += 1
        return "no", {}

    set_client(client)
    response = TestClient(app).post(
        "/v1/copilot",
        json={"text": "10k/10k divider 5 V to 3.3 V", "offline": True},
    )
    body = response.json()
    assert body["status"] == "checked"
    assert body["netlist"]
    assert calls["n"] == 0


def test_a_spent_cap_blocks_luna(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    monkeypatch.setenv("EXTRUDE_SPEND_CAP_USD", "0")
    calls = {"n": 0}

    def client(prompt: str, seat: str):
        calls["n"] += 1
        return "no", {}

    set_client(client)
    response = TestClient(app).post(
        "/v1/copilot",
        json={"text": "5 V to 3.3 V at 2 A", "offline": False},
    )
    assert response.json()["detail"] == "the Luna spend cap was reached"
    assert calls["n"] == 0


def test_a_repaired_enclosure_passes_the_second_audit(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    from extrude.memory.db import load_violations

    first = TestClient(app).post(
        "/v1/copilot",
        json={
            "artifact": _SCAD.read_text(encoding="utf-8"),
            "filename": "enclosure.scad",
            "filament": "PETG",
            "repair": True,
        },
    )
    assert first.json()["status"] == "checked"
    assert load_violations()
    second = TestClient(app).post(
        "/v1/copilot",
        json={
            "artifact": first.json()["code"],
            "filename": "enclosure.scad",
            "filament": "PETG",
        },
    )
    assert second.json()["status"] == "checked"
    assert second.json()["violations"] == []


def test_a_second_model_call_stops_when_the_cap_is_hit(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    monkeypatch.setenv("EXTRUDE_SPEND_CAP_USD", "1")
    clear_inflight()
    calls = {"n": 0}

    def client(prompt: str, seat: str):
        calls["n"] += 1
        return '{"spec_hash": "wrong"}', {"cost_usd": 1.0}

    set_client(client)
    first = TestClient(app).post("/v1/copilot", json={"text": "5 V to 3.3 V at 2 A"})
    assert first.json()["detail"] == "the Luna spend cap was reached"
    assert first.json()["cost_usd"] == 1.0
    assert calls["n"] == 1
    second = TestClient(app).post("/v1/copilot", json={"text": "5 V to 3.3 V at 2 A"})
    assert second.json()["status"] == "stopped"
    assert calls["n"] == 2


def test_an_empty_file_and_a_warning_do_not_look_like_a_pass():
    empty = TestClient(app).post("/v1/copilot", json={"filename": "board.net", "artifact": "  "})
    assert empty.json()["status"] == "needs_info"
    warned = TestClient(app).post(
        "/v1/copilot",
        json={"artifact": "// extrude-wall lip 2.0 0.4\n", "filename": "lip.scad", "filament": "PLA"},
    )
    body = warned.json()
    assert body["status"] == "checked"
    assert body["violations"] == []
    assert body["warnings"][0]["check_id"] == "overhang_risk"
    script = TestClient(app).post(
        "/v1/copilot",
        json={
            "artifact": "const holeDia = 4.2 * millimeter;\n// M3\nskCircle(center, holeDia);\n",
            "filename": "bracket.fs",
            "filament": "PETG",
            "repair": True,
        },
    )
    assert "Repair only rewrites OpenSCAD." in script.json()["detail"]
    bracket = (_SCAD.parent / "bracket.fs").read_text(encoding="utf-8")
    noted = TestClient(app).post(
        "/v1/copilot",
        json={"artifact": bracket, "filename": "bracket.fs", "filament": "PETG"},
    )
    assert any(item["check_id"] == "unsupported:opFillet" for item in noted.json()["warnings"])
    unread = TestClient(app).post(
        "/v1/copilot",
        json={"artifact": "cylinder(h=hole_d);\n", "filename": "open.scad", "filament": "PLA"},
    )
    assert unread.json()["status"] == "stopped"
    assert any(item["check_id"].startswith("unparsed_cylinder") for item in unread.json()["violations"])


def test_the_command_line_returns_an_error_when_the_file_is_missing():
    assert main(["audit", "missing-board.scad"]) == 1


_MLCC = """
(export (version "E")
  (components
    (comp (ref "C1")
      (value "22uF")
      (libsource (lib "Device") (part "C") (description ""))
      (fields
        (field (name "Dielectric") "X7R")
        (field (name "Manufacturer") "example")
        (field (name "Series") "holdup-demo")
        (field (name "Case") "0805")
        (field (name "VoltageRating") "10V")
        (field (name "BiasV") "4.7V")
        (field (name "CMin") "20uF")
      )
    )
  )
  (nets
    (net (code "1") (name "VOUT")
      (node (ref "C1") (pin "1"))
    )
    (net (code "2") (name "GND")
      (node (ref "C1") (pin "2"))
    )
  )
)
"""


def test_a_netlist_audit_fails_an_underrated_capacitor_and_remembers_it(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    from extrude.memory.db import load_violations

    payload = {"artifact": _MLCC, "filename": "holdup.net", "offline": True}
    first = TestClient(app).post("/v1/copilot", json=payload)
    body = first.json()
    assert body["status"] == "stopped"
    assert any(
        "capacitance_below_minimum" in item["check_id"] and "1.14e-05" in item["check_id"]
        for item in body["violations"]
    )
    assert any("capacitance_below_minimum" in item["check_id"] for item in body["constraints"])
    saved = len(load_violations())
    assert saved >= 1
    second = TestClient(app).post("/v1/copilot", json=payload)
    assert any("capacitance_below_minimum" in item["check_id"] for item in second.json()["constraints"])
    assert len(load_violations()) == saved


def test_a_second_enclosure_audit_shows_the_saved_miss(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    from extrude.memory.db import load_violations

    payload = {
        "artifact": _SCAD.read_text(encoding="utf-8"),
        "filename": "enclosure.scad",
        "filament": "PETG",
    }
    first = TestClient(app).post("/v1/copilot", json=payload)
    assert first.json()["status"] == "stopped"
    assert any(item["check_id"] == "hole_undersized_for_insert" for item in first.json()["constraints"])
    second = TestClient(app).post("/v1/copilot", json=payload)
    assert any(item["check_id"] == "hole_undersized_for_insert" for item in second.json()["constraints"])
    assert len(load_violations()) == 1


def test_the_home_page_is_a_prompt():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "textarea" in response.text
    assert 'src="/static/app.js' in response.text
    script = client.get("/static/app.js")
    assert script.status_code == 200
    assert 'fetch("/v1/compare"' in script.text


def test_an_onshape_link_asks_for_an_export():
    response = TestClient(app).post(
        "/v1/copilot",
        json={"artifact": "https://cad.onshape.com/documents/abc", "offline": True},
    )
    assert response.json()["status"] == "needs_info"
    assert "Onshape" in response.json()["question"]
