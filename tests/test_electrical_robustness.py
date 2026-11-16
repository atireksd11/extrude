"""Single-file failures cannot erase independent electrical evidence."""

import subprocess

import pytest

from extrude import electrical_reasoning as electrical, github_history as history
from extrude import electrical_graph, kicad_snapshot, workspace_audit, workspace_links
from extrude.parse import kicad_pcb, kicad_schematic, workspace_firmware
from extrude.parse.workspace_bom import csv_facts
from test_electrical_reasoning import design
from test_trust_blockers import board, device

pytestmark = pytest.mark.atlas


def good_design(prefix="good"):
    return {prefix + ".kicad_sch": design([device(name="MCLK")]),
            prefix + ".kicad_pcb": board(["U81"])}


def assert_good(findings):
    assert any(row["rule_id"] == "electrical.clock" and "MCLK" in row["summary"]
               for row in findings)


@pytest.fixture
def saved_repo(tmp_path, monkeypatch):
    """Use actual regular_blob size checks and Git reads, without network access."""
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "--template=", str(source)], check=True, capture_output=True)
    monkeypatch.setattr(history, "_repository", lambda _: source / ".git")

    def save(files):
        for path, data in files.items():
            target = source / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        subprocess.run(["git", "-C", str(source), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(source), "-c", "user.name=Test",
                        "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false",
                        "commit", "-m", "synthetic inputs"], check=True, capture_output=True)
        return subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    return save


@pytest.mark.parametrize("data", [b"// smart quote: \x93\n#define CLOCK 7\n", b"\x93\xc4\xff\x80"])
def test_bad_firmware_keeps_good_findings_and_discloses_replacement(saved_repo, data):
    sha = saved_repo({**good_design(), "odd.c": data})
    findings, coverage = electrical.collect("local", sha)
    assert_good(findings)
    assert any(row["path"] == "odd.c" and row["detail"].startswith("Not checked:")
               and "invalid UTF-8" in row["detail"] for row in coverage)
    assert any(row["outcome"] == "ran" for row in coverage)


def test_empty_firmware_and_literal_extraction_remain_usable():
    findings, _ = electrical.analyze({**good_design(), "empty.c": b""})
    assert_good(findings)
    assert workspace_firmware.read_constants(b"", "empty.c") == {}
    assert workspace_firmware.read_constants(b"// \x93\n#define CLOCK 7\n", "main.c")["CLOCK"]["value"] == 7
    assert workspace_firmware.read_constants(b"\xff\x93\x80", "binary.c") == {}


def test_non_utf8_schematic_pcb_and_bom_preserve_ascii_facts():
    sch = good_design()["good.kicad_sch"].replace(b'(generator "test")', b'(generator "test") (comment "\x93")')
    assert kicad_schematic.parse_schematic(sch).symbols[0].reference == "U81"
    assert electrical_graph.build({"good.kicad_sch": sch}).parts[0].reference == "U81"
    pcb = board(["U81"]).replace(b'Test:Part', b'Test:Part\x93')
    assert kicad_pcb.parse_board(pcb).footprints[0].reference == "U81"
    bom = b"Reference,Value\nU81,part\x93\n"
    assert csv_facts(bom)["rows"][0]["fields"]["Reference"] == "U81"
    assert_good(electrical.analyze({"good.kicad_sch": sch, "good.kicad_pcb": pcb, "bom.csv": bom})[0])


def test_snapshot_tolerates_library_and_project_text(saved_repo):
    sha = saved_repo({"unit.kicad_pro": b'{"comment":"\x93", "version":1}',
                      "fp-lib-table": b'(fp_lib_table (comment "\x93"))'})
    with kicad_snapshot.materialize("local", sha) as snapshot:
        assert snapshot.files == {"unit.kicad_pro", "fp-lib-table"}
        assert not snapshot.issues


@pytest.mark.parametrize("size_mib", [40])
def test_oversize_board_is_per_file_and_other_board_still_audits(saved_repo, size_mib):
    padded = board(["U82"]) + b" " * (size_mib * 1024 * 1024)
    sha = saved_repo({**good_design(), "oversize.kicad_pcb": padded})
    findings, coverage = electrical.collect("local", sha)
    assert_good(findings)
    assert any(row["path"] == "oversize.kicad_pcb" and "32 MiB" in row["detail"]
               and "other files still analysed" in row["detail"] for row in coverage)
    with pytest.raises(kicad_pcb.BoardParseError, match="32 MiB"):
        kicad_pcb.parse_board(padded)


def test_board_just_below_retained_cap_parses():
    raw = board(["U81"])
    padded = raw + b" " * (8 * 1024 * 1024 - len(raw))
    assert kicad_pcb.parse_board(padded).footprints[0].reference == "U81"


@pytest.mark.parametrize("error", [history.BlobUnavailable("bad blob"), ValueError("guard"),
                                   history.GitHubError("read failed"), OSError("read failed"), None])
def test_each_blob_read_failure_is_isolated(monkeypatch, error):
    files = {**good_design(), "bad.c": b""}
    monkeypatch.setattr(history, "inventory", lambda *a, **k: {
        "next_offset": None, "files": [{"path": p, "type": "blob"} for p in files]})
    def read(*args, **kwargs):
        path = args[2]
        if path == "bad.c":
            if error is not None:
                raise error
            return None
        return files[path]
    monkeypatch.setattr(history, "regular_blob", read)
    findings, coverage = electrical.collect("local", "head")
    assert_good(findings)
    assert any(row["path"] == "bad.c" and row["detail"].startswith("Not checked:") for row in coverage)


@pytest.mark.parametrize("bad", [b'(kicad_sch (version 20250114)',
                                 b'(kicad_sch (version 20250114) (sheet (uuid "s") (property "Sheetfile" "../../escape.kicad_sch")))'])
def test_malformed_sheet_and_unsafe_dependency_are_per_sheet(bad):
    findings, coverage = electrical.analyze({**good_design(), "bad.kicad_sch": bad})
    assert_good(findings)
    assert any(path == "bad.kicad_sch" and detail.startswith("Not checked:") for path, _, detail in coverage)


def test_root_analysis_error_does_not_erase_other_roots(monkeypatch):
    original = electrical._analyze_design
    def analyze(files, *args, **kwargs):
        if "bad.kicad_sch" in files:
            raise ValueError("synthetic graph parse failure")
        return original(files, *args, **kwargs)
    monkeypatch.setattr(electrical, "_analyze_design", analyze)
    findings, coverage = electrical.analyze({**good_design(), **good_design("bad")})
    assert_good(findings)
    assert any(path == "bad.kicad_sch" and "synthetic graph" in detail for path, _, detail in coverage)


def test_bom_parser_failure_does_not_drop_board_findings():
    files = {**good_design(), "bom.csv": b"Reference,Value\nU81," + b"x" * 200000}
    findings, coverage = electrical.analyze(files)
    assert_good(findings)
    assert any(path == "bom.csv" and detail.startswith("Not checked:") for path, _, detail in coverage)


def test_independent_designs_are_not_combined():
    files = {**good_design("one/unit"), **good_design("two/unit"), **good_design("three/unit")}
    findings, _ = electrical.analyze(files)
    clocks = [f for f in findings if f["rule_id"] == "electrical.clock"]
    assert len(clocks) == 3
    assert {f["sources"][0][0] for f in clocks} == {"one/unit.kicad_sch", "two/unit.kicad_sch", "three/unit.kicad_sch"}


@pytest.mark.parametrize("bad_path,bad_data", [
    ("odd.c", b"// \x93\n"),
    ("bad.kicad_sch", b"(kicad_sch broken"),
    ("big.kicad_pcb", b" " * (40 * 1024 * 1024)),
], ids=["bad-firmware", "malformed-schematic", "oversize-pcb"])
def test_bad_file_never_reaches_workspace_whole_layer_handler(saved_repo, monkeypatch, bad_path, bad_data):
    sha = saved_repo({**good_design(), bad_path: bad_data})
    # Exercise the real last-resort handler, stubbing only unrelated audit layers.
    monkeypatch.setattr(history, "changes", lambda *a, **k: {"total": 0, "next_offset": None, "files": []})
    monkeypatch.setattr(workspace_audit.kicad_audit, "collect", lambda *a: ([], []))
    monkeypatch.setattr(workspace_audit.workspace_checks, "collect", lambda *a: ([], []))
    monkeypatch.setattr(workspace_links, "collect", lambda *a: ([], []))
    monkeypatch.setattr(workspace_links, "attach", lambda *a: None)
    audit = workspace_audit.Audit(id="test", repo_id="local", base_sha=None,
                                  head_sha=sha, tool_versions={}, config_hash="test")
    workspace_audit._collect(audit)
    assert_good([row.model_dump() for row in audit.findings])
    assert any(row.path == bad_path and row.detail.startswith("Not checked:") for row in audit.coverage)
    assert not any(row.check == "Whole-design electrical reasoning" for row in audit.coverage)
    assert any(row.tool == "offline net graph" and row.outcome == "ran" for row in audit.coverage)


def test_versioning_and_pcb_only_limits():
    assert workspace_audit.RULE_VERSION == 9
    assert workspace_audit.SCHEMA_VERSION == 4
    assert kicad_pcb.MAX_BOARD_BYTES == 32 * 1024 * 1024
    assert kicad_schematic.MAX_SCHEMATIC_BYTES == kicad_snapshot.MAX_FILE_BYTES == electrical_graph.MAX_BYTES == 8 * 1024 * 1024
    assert kicad_snapshot.MAX_FILES == 256
    assert kicad_snapshot.MAX_BYTES == 64 * 1024 * 1024
    assert workspace_firmware.MAX_SOURCE_BYTES == 512 * 1024


def test_cyclic_sheets_degrade_per_file_with_or_without_a_good_root():
    cyclic = b'(kicad_sch (version 20250114) (sheet (uuid "self") (property "Sheetfile" "cycle.kicad_sch")))'
    for peers in ({}, good_design()):
        findings, coverage = electrical.analyze({**peers, "cycle.kicad_sch": cyclic})
        if peers:
            assert_good(findings)
        assert any(path == "cycle.kicad_sch" and "cyclic" in detail for path, _, detail in coverage)


def test_valid_replacement_character_is_not_reported_as_decode_damage():
    findings, coverage = electrical.analyze({**good_design(), "main.c": "// \ufffd\n".encode()})
    assert_good(findings)
    assert not any(path == "main.c" and family == "text" for path, family, _ in coverage)


def test_mapped_netlist_tolerates_comment_bytes():
    from extrude.workspace_netlist import read_netlist
    parsed = read_netlist(b'(export (comment "\x93") (components (comp (ref U81) (value part))) (nets (net (code 1) (name CLK) (node (ref U81) (pin 1)))))')
    assert parsed["nets"]["CLK"][0]["reference"] == "U81"


def test_malformed_paired_board_keeps_schematic_findings():
    findings, coverage = electrical.analyze({**good_design(), "good.kicad_pcb": b"(kicad_pcb broken"})
    assert_good(findings)
    assert any(path == "good.kicad_pcb" and "syntax" in detail for path, _, detail in coverage)


def test_overflowing_schematic_unit_degrades_per_file():
    malformed = good_design()["good.kicad_sch"].replace(b"(unit 1)", b"(unit 1e999)")
    findings, coverage = electrical.analyze({**good_design(), "bad.kicad_sch": malformed})
    assert_good(findings)
    assert any(path == "bad.kicad_sch" and detail.startswith("Not checked:") for path, _, detail in coverage)
