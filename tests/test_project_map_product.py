"""Product loop checks for local project scanning and the 3D inspector."""

import shutil
from pathlib import Path

import pytest

from extrude.project_map import (
    add_pin_rule,
    create_project,
    delete_pin_rule,
    preview_project_file,
    project_handoff,
    review_finding,
    scan_project,
)


DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo-robot"


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_PROJECT_DB", str(tmp_path / "atlas.sqlite"))
    folder = tmp_path / "robot"
    shutil.copytree(DEMO, folder)
    result = create_project("Test robot", str(folder))
    return folder, result["project"]["id"]


def test_pin_check_follows_real_file_change(project):
    folder, project_id = project
    rule = {
        "firmware_file": "firmware/gripper.ino",
        "firmware_symbol": "MOTOR_PIN",
        "netlist_file": "electronics/gripper.net",
        "schematic_net": "MOTOR",
        "mcu_ref": "U1",
    }
    configured = add_pin_rule(project_id, rule)
    with pytest.raises(ValueError, match="already configured"):
        add_pin_rule(project_id, rule)
    assert next(check for check in configured["checks"] if check["name"] == "Pin map: MOTOR_PIN")["status"] == "passed"
    assert any(link["confidence"] == "configured" for link in configured["relationships"])

    source = folder / "firmware" / "gripper.ino"
    source.write_text(source.read_text(encoding="utf-8").replace("MOTOR_PIN = 12", "MOTOR_PIN = 13"), encoding="utf-8")
    changed = scan_project(project_id)
    assert changed["changes"][0]["action"] == "updated"
    assert "-const int MOTOR_PIN = 12;" in changed["changes"][0]["diff"]
    assert "+const int MOTOR_PIN = 13;" in changed["changes"][0]["diff"]
    assert next(check for check in changed["checks"] if check["name"] == "Pin map: MOTOR_PIN")["status"] == "failed"
    assert {impact["target"] for impact in changed["impacts"]} >= {"schematic", "pcb"}
    assert next(impact for impact in changed["impacts"] if impact["target"] == "schematic")["status"] == "failed"
    failed_id = next(impact["id"] for impact in changed["impacts"] if impact["status"] == "failed")
    with pytest.raises(ValueError):
        review_finding(project_id, failed_id)

    reviewed_id = next(impact["id"] for impact in changed["impacts"] if impact["status"] == "possible")
    with pytest.raises(ValueError, match="affected area"):
        review_finding(project_id, reviewed_id, target_file="cad/gripper.stl")
    acknowledged = review_finding(project_id, reviewed_id, "not_relevant", "Only a pin constant changed.",
                                  "electronics/gripper.kicad_pcb")
    assert len(acknowledged["impacts"]) == len(changed["impacts"]) - 1
    assert acknowledged["review_history"][0]["review_outcome"] == "not_relevant"
    assert acknowledged["review_history"][0]["review_note"] == "Only a pin constant changed."
    assert acknowledged["review_history"][0]["review_target"] == "electronics/gripper.kicad_pcb"
    handoff = project_handoff(project_id)
    assert "## Active findings" in handoff
    assert "## Review decisions" in handoff
    assert "Only a pin constant changed." in handoff
    assert str(folder) not in handoff
    assert "-const int MOTOR_PIN" not in handoff

    cleared = delete_pin_rule(project_id, configured["pin_rules"][0]["id"])
    assert not any(check["name"] == "Pin map: MOTOR_PIN" for check in cleared["checks"])


def test_large_cad_file_is_tracked_and_mesh_is_inspectable(project):
    folder, project_id = project
    large = folder / "cad" / "large.step"
    large.write_bytes(b"X" * 2_100_000)
    data = scan_project(project_id)
    assert any(file["path"] == "cad/large.step" for file in data["files"])
    assert not any(item["path"] == "cad/large.step" for item in data["skipped"])
    large_preview = preview_project_file(project_id, "cad/large.step")
    assert len(large_preview["text"]) == 100_000
    assert large_preview["truncated"]

    preview = preview_project_file(project_id, "cad/gripper.stl")
    assert preview["type"] == "mesh"
    assert preview["mesh"]["dimensions"] == [44.0, 24.0, 14.0]
    assert preview["mesh"]["total_triangles"] == 24
    with pytest.raises(KeyError):
        preview_project_file(project_id, "../outside.txt")
