"""Phase 3 gates: actual geometry, scoped cross-file checks, and API behavior."""

import json
from pathlib import Path
import shutil
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

from extrude import github_history as git, workspace_audit as audits, workspace_checks as checks
from extrude import workspace_cad as cad, workspace_settings as config
from extrude.parse.workspace_mesh import read_mesh, board_spans
from extrude.parse.workspace_firmware import read_constants
from extrude.parse.workspace_bom import read_bom, references, csv_facts, compare_csv
from extrude.workspace_netlist import Reader, read_netlist


NET = b'''(export (version "E")
  (components (comp (ref "U1") (value "MCU") (libsource (lib "Test") (part "MCU"))))
  (nets (net (code "1") (name "MOTOR")
    (node (ref "U1") (pin "12") (pinfunction "GPIO12")))))'''


def mesh_box(width=95):
    import trimesh
    return trimesh.creation.box(extents=[width, 70, 20]).export(file_type="stl")


def board(width):
    return f'''(kicad_pcb (version 20221018)
      (gr_rect (start 0 0) (end {width} 50) (stroke (width .05) (type default))
        (fill none) (layer "Edge.Cuts")))'''.encode()


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_DATA_DIR", str(tmp_path / "state"))
    source = tmp_path / "source"; source.mkdir()
    def command(*args):
        return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()
    command("init", "--template=")
    def save(path, data):
        file = source / path; file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data if isinstance(data, bytes) else data.encode())
    def commit(message):
        command("add", "-A")
        command("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "-c", "commit.gpgsign=false", "commit", "-m", message)
        return command("rev-parse", "HEAD")
    save("hardware/board.kicad_pcb", board(90))
    save("cad/cavity.stl", mesh_box(100))
    save("firmware/motor.ino", "#define MOTOR_PIN 12\n")
    save("hardware/board.net", NET)
    save("hardware/board.kicad_sch", (Path(__file__).parent / "fixtures/phase2/clean/board.kicad_sch").read_bytes())
    save("bom.csv", 'Reference,MPN,Quantity,DNP\nU1,00123,1,no\n')
    base = commit("Baseline: board 90, cavity 100, matching motor pin")
    save("hardware/board.kicad_pcb", board(100))
    save("cad/cavity.stl", mesh_box(95))
    save("firmware/motor.ino", "#define MOTOR_PIN 13\n")
    save("bom.csv", 'Reference,MPN,Quantity,DNP\nU1,000456,2,no\nX9,"unknown, quoted",1,no\nD99,001,0,yes\n"R1-R3?",bad,3,no\n')
    head = commit("Break width/pin/quantity and add unknown reference")
    def fetch(repo, _):
        shutil.copytree(source / ".git/objects", repo / "objects", dirs_exist_ok=True,
                        copy_function=lambda a, b: b if Path(b).exists() else shutil.copy2(a, b))
        git._git(repo, "update-ref", "refs/atlas/fetched", head)
    monkeypatch.setattr(git, "_fetch", fetch)
    repo = git.connect("fixture/phase3")["id"]
    settings = config.Settings(
        cad_pairs=[dict(board_file="hardware/board.kicad_pcb", mesh_file="cad/cavity.stl", units="mm",
                        mesh_kind="cavity", board_axes=["x", "y"])],
        pin_assignments=[dict(firmware_file="firmware/motor.ino", firmware_symbol="MOTOR_PIN",
                              netlist_file="hardware/board.net", schematic_net="MOTOR", mcu_ref="U1", numbering="package")],
        boms=[dict(bom_file="bom.csv", schematic_file="hardware/board.kicad_sch", dnp_column="DNP")])
    return repo, base, head, settings


def test_mesh_facts_and_no_asset_resolution(monkeypatch):
    a = read_mesh(mesh_box(), ".stl", preview=True)
    assert a["dimensions"] == pytest.approx([95, 70, 20])
    assert a["watertight"] and len(a["triangles"]) == 12
    obj = b"mtllib https://external.invalid/evil.mtl\nv 0 0 0\nv 10 0 0\nv 0 20 0\nf 1 2 3\n"
    result = read_mesh(obj, ".obj")
    assert result["dimensions"] == [10, 20, 0]  # offline fixture blocks network calls
    for blob in (b"garbage", b"v nan 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"):
        with pytest.raises(ValueError):
            read_mesh(blob, ".obj")
    assert board_spans(board(100))["dimensions_mm"] == [100, 50]
    with pytest.raises(ValueError):
        board_spans(b'(kicad_pcb (version 1))')
    with pytest.raises(ValueError, match="open"):
        board_spans(b'(kicad_pcb (version 1) (gr_line (start 0 0) (end 100 50) (layer "Edge.Cuts")))')


@pytest.mark.parametrize("expression", ["12 + 1", "GPIO_NUM_12", "select_pin()", "12 ? 13 : 14"])
def test_no_partial_numeric_matches(expression):
    row = read_constants(f"#define MOTOR_PIN {expression}\n".encode(), "main.ino")["MOTOR_PIN"]
    assert row["value"] is None


def test_firmware_literals_scope_and_lines():
    data = b'// #define MOTOR_PIN 99\nconst unsigned int MOTOR_PIN = 0x0CU;\n'
    assert read_constants(data, "main.cpp")["MOTOR_PIN"] == dict(value=12, line=2, detail=None)
    assert read_constants(b'#if SOME_BUILD\n#define MOTOR_PIN 12\n#endif\n', "main.h")["MOTOR_PIN"]["value"] is None
    assert read_constants(b'#define MOTOR_PIN 12\n#define MOTOR_PIN 13\n', "main.ino")["MOTOR_PIN"]["value"] is None
    assert read_constants(b'MOTOR_PIN: int = 12\n', "main.py")["MOTOR_PIN"]["value"] == 12
    assert read_constants(b'MOTOR_PIN = 12 + 1\n', "main.py")["MOTOR_PIN"]["value"] is None
    assert read_constants(b'def f():\n    MOTOR_PIN = 12\n', "main.py")["MOTOR_PIN"]["value"] is None
    assert read_constants(b'void f() {\n int MOTOR_PIN = 12;\n}\n', "main.cpp")["MOTOR_PIN"]["value"] is None


def test_bom_preserves_strings_groups_and_exclusions():
    mapping = config.BomMapping(bom_file="bom.csv", schematic_file="main.kicad_sch", dnp_column="DNP")
    blob = b'Reference,MPN,Quantity,DNP\n"R1, R2",000123,2,no\nR3-R5,"part,quoted",3,no\nC99,unused,0,yes\nR1-R?,bad,2,no\n'
    bom = read_bom(blob, mapping)
    assert bom["rows"][0]["part"] == "000123"
    assert bom["rows"][0]["references"] == ("R1", "R2")
    assert bom["rows"][1]["references"] == ("R3", "R4", "R5")
    assert bom["rows"][2]["dnp"]
    assert len(bom["issues"]) == 1
    assert references("R1-R100000000") is None
    assert references("R1,R1") is None
    duplicated = read_bom(b'Reference,MPN,Quantity,DNP\nX9,a,1,no\nX9,b,1,no\n', mapping)
    assert duplicated["rows"] == [] and duplicated["issues"]
    with pytest.raises(ValueError, match="quoting"):
        read_bom(b'Reference,MPN,Quantity,DNP\n"unfinished', mapping)


def test_shopping_bom_cell_comparison_and_reordering():
    a = csv_facts(b'Item,Qty,Total Cost\nMotor,2,$7.00\nEstimated total shipping,1,$3.70\n')
    b = csv_facts(b'Item,Qty,Total Cost\nEstimated total shipping,1,$3.72\nMotor,2,$7.00\n')
    diff = compare_csv(a, b)
    assert diff["key_column"] == "Item" and diff["changed_cells"] == 1
    assert diff["added"] == diff["removed"] == diff["ambiguous"] == 0
    row = next(row for row in diff["rows"] if row["status"] == "modified")
    assert row["key"] == "Estimated total shipping"
    assert row["changes"] == [dict(column="Total Cost", before="$3.70", after="$3.72")]
    assert (row["before"]["line"], row["after"]["line"]) == (3, 2)
    assert compare_csv(a, dict(a, rows=list(reversed(a["rows"]))))["changed_cells"] == 0
    assert compare_csv(None, b)["added"] == 2
    assert compare_csv(a, None)["removed"] == 2


def test_csv_ambiguous_identifiers_and_removed_columns_are_explicit():
    a = csv_facts(b'Item,Qty\nMotor,1\nMotor,2\n')
    b = csv_facts(b'Item,Qty\nMotor,3\n')
    result = compare_csv(a, b)
    assert result["ambiguous"] == 3 and result["changed_cells"] == 0
    assert result["added"] == result["removed"] == 0
    a = csv_facts(b'Name,Cost\nMotor,001\n')
    b = csv_facts(b'Name,Cost\nMotor,002\n')
    assert compare_csv(a, b)["key_column"] is None
    assert compare_csv(a, b)["changed_cells"] == 0
    a = csv_facts(b'Item,MPN,Notes\nMotor,00123,\n')
    b = csv_facts(b'Item,MPN\nMotor,000456\n')
    result = compare_csv(a, b)
    assert result["removed_columns"] == ["Notes"]
    assert result["rows"][0]["changes"] == [dict(column="MPN", before="00123", after="000456"), dict(column="Notes", before="", after=None)]


def test_netlist_keeps_package_pad_when_function_has_different_number():
    result = read_netlist(NET)
    assert result["nets"]["MOTOR"][0] == dict(reference="U1", pad="12", function="GPIO12")
    for data in (b"garbage", b"(export (components))"):
        with pytest.raises(ValueError):
            read_netlist(data)


def test_phase3_controlled_gate(project, monkeypatch):
    repo, base, head, settings = project
    # The domain checks below use an exact saved netlist for assembly references;
    # native schematic export is independently exercised in its own test.
    reader = checks.Reader.get
    monkeypatch.setattr(checks.Reader, "get", lambda self, repo, sha, path: read_netlist(NET) if path.endswith(".kicad_sch") else reader(self, repo, sha, path))
    findings, coverage = checks.collect(repo, head, base, settings, git.changes(repo, head, base)["files"])
    by_rule = {}
    for row in findings:
        by_rule.setdefault(row["rule_id"], []).append(row)
    expected = {"cad.board_exceeds_cavity", "firmware.pin_mismatch", "bom.reference_missing", "bom.quantity_mismatch", "bom.part_changed", "bom.quantity_changed", "cad.extents_changed", "firmware.constant_changed"}
    assert expected.issubset(by_rule), by_rule.keys()
    for rule in ("cad.board_exceeds_cavity", "firmware.pin_mismatch", "bom.reference_missing", "bom.quantity_mismatch"):
        assert all(r["status"] == "verified" and r["lifecycle"] == "new" for r in by_rule[rule])
        assert all(len(r["evidence"]) >= 2 for r in by_rule[rule])
    assert by_rule["cad.board_exceeds_cavity"][0]["after"]["board_mm"] == 100
    assert by_rule["cad.board_exceeds_cavity"][0]["after"]["cavity_mm"] == 95
    assert "X9" in by_rule["bom.reference_missing"][0]["summary"]
    assert not any("D99" in r["summary"] or "R1-R3?" in r["summary"] for r in by_rule["bom.reference_missing"])
    assert by_rule["bom.part_changed"][0]["before"] == "00123"
    assert by_rule["bom.part_changed"][0]["after"] == "000456"
    assert any(c["check"] == "BOM ambiguous rows" and c["outcome"] == "unsupported" for c in coverage)
    assert not any(c["outcome"] != "ran" for c in coverage if c["check"] in {"Board/cavity spans", "Firmware/netlist pin mapping", "BOM assembly references and quantities"})
    Path("data/phase3-controlled-gate.json").write_text(json.dumps(dict(repo=repo, base=base, head=head, settings=settings.model_dump(mode="json"), findings=findings, coverage=coverage), indent=2), encoding="utf-8")


def test_unverified_mapping_cases_and_lifecycles(project):
    repo, base, head, settings = project
    # Exterior bounds may only suggest a review. A declared cavity can establish
    # an exceeded span; a smaller board still does not prove a complete fit.
    pair = settings.cad_pairs[0].model_copy(update={"mesh_kind": "exterior"})
    c = checks.Collector(repo, head, base); c.cad(pair)
    assert all(f["status"] == "suggestion" for f in c.findings)
    c = checks.Collector(repo, base, None); c.cad(settings.cad_pairs[0])
    assert not c.findings and "full fit remains unverified" in c.coverage[0]["detail"]
    c = checks.Collector(repo, head, head); c.cad(settings.cad_pairs[0])
    assert c.findings[0]["lifecycle"] == "existing"
    c = checks.Collector(repo, base, head); c.cad(settings.cad_pairs[0])
    assert c.findings[0]["lifecycle"] == "resolved"
    c = checks.Collector(repo, head, base)
    c.pin(settings.pin_assignments[0].model_copy(update={"numbering": "gpio", "gpio_to_pad": {}}))
    assert not c.findings and all(r["outcome"] == "unavailable" for r in c.coverage)
    c = checks.Collector(repo, head, base)
    c.pin(settings.pin_assignments[0].model_copy(update={"netlist_file": "missing.net"}))
    assert not c.findings and all(r["outcome"] == "unavailable" for r in c.coverage)
    c = checks.Collector(repo, head, base)
    c.pin(settings.pin_assignments[0].model_copy(update={"numbering": "gpio", "gpio_to_pad": {"12": "12", "13": "12"}}))
    assert not c.findings and all(r["outcome"] == "ran" for r in c.coverage)

    # An unparseable head BOM row cannot make an earlier missing-part finding
    # appear repaired. Positive head findings may still be shown independently.
    c = checks.Collector(repo, head, base)
    issue = dict(rule="bom.reference_missing", summary="Missing X9", measurement={"reference": "X9"}, evidence=[])
    c.paired("bom.csv", "bom", "Ambiguity gate", lambda sha: ({"X9": issue}, "complete", True) if sha == base else ({}, "ambiguous row", False))
    assert not c.findings


def test_source_is_never_executed(tmp_path):
    sentinel = tmp_path / "executed"
    text = f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\nMOTOR_PIN = 12\n"
    assert read_constants(text.encode(), "main.py")["MOTOR_PIN"]["value"] == 12
    assert not sentinel.exists()
    with pytest.raises(ValueError, match="syntax"):
        read_constants(b"not valid python =", "main.py")
    assert read_constants(b"#define MOTOR_PIN 12\n#undef MOTOR_PIN\n", "main.h")["MOTOR_PIN"]["value"] is None
    assert read_constants(b"#define MOTOR_PIN 012\n", "main.h")["MOTOR_PIN"]["value"] == 10


def test_step_failure_timeout_and_cleanup(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(cad, "tool_versions", lambda: {"cadquery": "unavailable"})
    blob = b"ISO-10303-21;\nEND-ISO-10303-21;"
    with pytest.raises(ValueError, match="not installed"):
        cad.read_step(blob)
    monkeypatch.setattr(cad, "tool_versions", lambda: {"cadquery": "test"})
    def timeout(*args, **kwargs):
        assert "OPENAI_API_KEY" not in kwargs["env"]
        raise subprocess.TimeoutExpired(args[0], cad.TIMEOUT)
    monkeypatch.setattr(cad.subprocess, "run", timeout)
    with pytest.raises(ValueError, match="timed out"):
        cad.read_step(blob)
    assert not list((tmp_path / "state/kicad-tmp").iterdir())


def test_settings_validation_cache_freeze_and_restore(project):
    repo, base, head, settings = project
    original = audits._descriptor(repo, head, base)
    config.save(repo, settings)
    changed = audits._descriptor(repo, head, base)
    assert changed.id != original.id
    assert config.get(repo) == settings
    assert original.project_settings["cad_pairs"] == []
    config.save(repo, config.Settings())
    assert config.Settings.model_validate(changed.project_settings) == settings
    for update in ({"units": "unknown"}, {"board_axes": ["x", "x"]}, {"mesh_file": "../outside.stl"}, {"cavity_mm": [float('nan'), 1, 1]}):
        with pytest.raises(ValueError):
            config.CadPair.model_validate({**settings.cad_pairs[0].model_dump(), **update})


def test_native_netlist_export(project, tmp_path):
    from extrude import kicad_audit
    if kicad_audit.tool_version() in {"unavailable", "unsupported"}:
        pytest.skip("Actual schematic export requires installed KiCad")
    repo, base, _, _ = project
    value = Reader().get(repo, base, "hardware/board.kicad_sch")
    assert "U1" in value["components"] and any(p["pad"] == "1" for net in value["nets"].values() for p in net)
    assert list((tmp_path / "state/kicad-tmp").iterdir()) == []


def test_step_brep_units_placements_and_preview(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_DATA_DIR", str(tmp_path / "state"))
    import cadquery as cq
    path = tmp_path / "box.step"
    shape = cq.Workplane("XY").box(100, 60, 20)
    # The exporter declares the numeric model's source units. Use inch-valued
    # coordinates, then verify that the reader normalizes them to mm.
    inches = cq.Workplane("XY").box(100 / 25.4, 60 / 25.4, 20 / 25.4)
    cq.exporters.export(inches, str(path), exportType="STEP", unit="INCH")
    result = cad.read_step(path.read_bytes(), preview=True)
    assert result["unit"] == "mm" and result["dimensions"] == pytest.approx([100, 60, 20])
    assert result["volume_mm3"] == pytest.approx(120000)
    assert result["solids"] == 1 and len(result["triangles"]) == 12
    assembly = cq.Assembly(); assembly.add(shape, name="first"); assembly.add(shape, name="second", loc=cq.Location(cq.Vector(200, 0, 0)))
    assembly.export(str(path), exportType="STEP")
    result2 = cad.read_step(path.read_bytes())
    assert result2["solids"] == 2 and result2["dimensions"][0] == pytest.approx(300)
    assert not list((tmp_path / "state/kicad-tmp").iterdir())
    with pytest.raises(ValueError):
        cad.read_step(b"not a STEP")


def test_api_settings_artifacts_and_audit(project, monkeypatch):
    from extrude.api.server import app
    repo, base, head, settings = project
    # Native phase 2 has its own actual-tool gate. Keep this API gate focused on
    # Phase 3 while preserving actual committed netlist and geometry reads.
    monkeypatch.setattr(audits.kicad_audit, "collect", lambda *_: ([], []))
    original = checks.Reader.get
    monkeypatch.setattr(checks.Reader, "get", lambda self, repo, sha, path: read_netlist(NET) if path.endswith(".kicad_sch") else original(self, repo, sha, path))
    client = TestClient(app)
    root = f"/v1/github/repositories/{repo}"
    assert client.put(root + "/settings", json=settings.model_dump(mode="json")).status_code == 200
    assert client.get(root + "/settings").json() == settings.model_dump(mode="json")
    bad = settings.model_dump(mode="json"); bad["cad_pairs"][0]["board_axes"] = ["x", "x"]
    assert client.put(root + "/settings", json=bad).status_code == 422
    artifact = client.get(root + "/artifact", params=dict(revision=head, base=base, path="cad/cavity.stl"))
    assert artifact.status_code == 200 and artifact.json()["after"]["facts"]["triangles"]
    table = client.get(root + "/artifact", params=dict(revision=head, base=base, path="bom.csv"))
    assert table.status_code == 200 and table.json()["csv_comparison"]["changed_cells"] == 2
    tool = client.post(root + "/cad/inspect", json=dict(revision=head, path="cad/cavity.stl", include_preview=True))
    assert tool.status_code == 200 and tool.json()["sha"] == head and tool.json()["evidence"]
    assert client.post(root + "/cad/inspect", json=dict(revision=head, path="../outside.step")).status_code == 400
    assert client.post(root + "/cad/inspect", json=dict(revision=head, path="cad/cavity.stl", python="arbitrary_code()")).status_code == 422
    started = client.post(root + "/audits", json=dict(revision=head, base=base)).json()
    for _ in range(150):
        result = client.get(root + "/audits/" + started["id"]).json()
        if result["state"] not in {"running", "queued"}:
            break
        time.sleep(.1)
    assert result["state"] in {"complete", "partial"}, result
    assert {"cad.board_exceeds_cavity", "firmware.pin_mismatch", "bom.reference_missing"}.issubset({f["rule_id"] for f in result["findings"]})
    for finding in result["findings"]:
        for source in finding["evidence"]:
            assert client.get(root + "/preview", params=dict(revision=source["sha"], path=source["path"])).status_code == 200
    assert client.get(root + "/audits/" + started["id"]).json()["project_settings"] == settings.model_dump(mode="json")
