"""Phase 2: real saved Git inputs, real native checks, and fail-closed paths."""

import json
import shutil
import subprocess
import time
from contextlib import nullcontext
from pathlib import Path

import pytest

from extrude import github_history as git, kicad_audit as native, schematic_review, workspace_audit
from extrude.kicad_snapshot import materialize, safe_path, SnapshotError, Snapshot, relative_dependency
from extrude.parse.kicad_schematic import parse_schematic, compare_schematics, SchematicParseError
from extrude.parse.kicad_pcb import parse_board, compare_boards

FIXTURES = Path(__file__).parent / "fixtures" / "phase2"


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_DATA_DIR", str(tmp_path / "state"))
    root = tmp_path / "source"
    root.mkdir()
    def command(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()
    command("init", "--template=")
    def commit(variant, subject):
        for file in (FIXTURES / variant).iterdir():
            if file.suffix in {".kicad_pcb", ".kicad_sch", ".kicad_pro"}:
                shutil.copyfile(file, root / file.name)
        command("add", "-A")
        command("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "-c", "commit.gpgsign=false", "commit", "-m", subject)
        return command("rev-parse", "HEAD")
    base = commit("clean", "Clean baseline")
    head = commit("broken", "Cross tracks, remove NC, change board value")
    inherited = commit("routing", "Keep routing error, repair schematic and parity")
    def fetch(repo, _source):
        shutil.copytree(root / ".git" / "objects", repo / "objects", dirs_exist_ok=True,
                        copy_function=lambda src, dst: dst if Path(dst).exists() else shutil.copy2(src, dst))
        git._git(repo, "update-ref", "refs/atlas/fetched", inherited)
    monkeypatch.setattr(git, "_fetch", fetch)
    repo_id = git.connect("fixture/phase2")["id"]
    return repo_id, base, head, inherited, root, command


def test_schematic_facts_are_placed_symbols_only():
    blob = (FIXTURES / "clean/board.kicad_sch").read_bytes()
    old = parse_schematic(blob)
    assert len(old.symbols) == 1
    assert old.symbols[0].reference == "U1"
    changed = blob.replace(b'"Reference" "U1"', b'"Reference" "U2"').replace(b'"Value" "Output" (at 50', b'"Value" "Other" (at 50')
    rows = compare_schematics(old, parse_schematic(changed))
    assert {row["kind"] for row in rows} == {"reference_changed", "value_changed"}
    assert len(compare_schematics(None, old)) == len(compare_schematics(old, None)) == 1
    assert compare_schematics(old, old) == []
    for invalid in (b"(kicad_pcb (version 1))", b"broken", b"\xff"):
        with pytest.raises(SchematicParseError):
            parse_schematic(invalid)


def test_schematic_saved_comparison_and_api(project):
    repo_id, base, head, _, _, _ = project
    from extrude.api.github import schematic
    review = schematic(repo_id, head, "board.kicad_sch", base, None, 0, 100)
    assert review["status"] == "compared" and review["changes"] == []  # NC removal is connectivity, not a symbol value change
    assert review["before"]["symbols"] == review["after"]["symbols"] == 1
    assert schematic_review.review(repo_id, base, "board.kicad_sch")["changes"][0]["kind"] == "symbol_added"


@pytest.mark.parametrize("name", ["../escape.kicad_pcb", "/escape", "C:/escape", "a\\b", "a/../b", "a//b", "a/NUL.sch", "a/b:stream", "a./b"])
def test_unsafe_snapshot_paths(tmp_path, name):
    with pytest.raises(SnapshotError):
        safe_path(tmp_path, name)


def test_materialize_regular_allowlist_cleanup_and_hierarchy(project, monkeypatch):
    repo_id, base, _, _, _, _ = project
    with materialize(repo_id, base) as snapshot:
        root = snapshot.root
        assert sorted(snapshot.files) == ["board.kicad_pcb", "board.kicad_pro", "board.kicad_sch"]
        assert snapshot.sheets("board.kicad_sch") == {"/": "board.kicad_sch"}
        assert snapshot.issues == []
    assert not root.exists()
    with pytest.raises(RuntimeError):
        with materialize(repo_id, base) as snapshot:
            root = snapshot.root
            raise RuntimeError("checker failure")
    assert not root.exists()
    original = git.inventory
    def inventory(*args, **kwargs):
        data = original(*args, **kwargs)
        data["files"].extend([{"path": "../escape.kicad_sch", "type": "blob"},
                              {"path": "link.kicad_sch", "type": "symlink"},
                              {"path": "submodule.kicad_pcb", "type": "commit"}])
        return data
    real_blob = git.regular_blob
    def blob(repo, sha, path, **kwargs):
        if path.startswith(("link", "submodule")):
            raise git.BlobUnavailable("Not a regular file")
        return real_blob(repo, sha, path, **kwargs)
    monkeypatch.setattr(git, "inventory", inventory)
    monkeypatch.setattr(git, "regular_blob", blob)
    with materialize(repo_id, base) as snapshot:
        assert len(snapshot.issues) == 3
        assert not (snapshot.root / "link.kicad_sch").exists()


def test_missing_child_and_external_sheet_do_not_run(tmp_path, monkeypatch):
    data = (FIXTURES / "clean/board.kicad_sch").read_text()
    child = '(sheet (uuid 90000000-0000-4000-8000-000000000000) (property "Sheetfile" "missing.kicad_sch"))'
    path = tmp_path / "root.kicad_sch"
    path.write_text(data[:-1] + child + ")")
    snapshot = Snapshot(tmp_path, {"root.kicad_sch"})
    with pytest.raises(SnapshotError, match="Missing schematic"):
        snapshot.sheets("root.kicad_sch")
    path.write_text(data[:-1] + child.replace("missing.kicad_sch", "../../outside.kicad_sch") + ")")
    with pytest.raises(SnapshotError, match="escapes"):
        snapshot.sheets("root.kicad_sch")
    assert relative_dependency("project/root.kicad_sch", "../shared/child.kicad_sch") == "shared/child.kicad_sch"

    # Exercise actual adapter coverage, including parity, not just the parser.
    (tmp_path / "root.kicad_pcb").write_text("not read because hierarchy fails first")
    snapshot.files.add("root.kicad_pcb")
    monkeypatch.setattr(native, "materialize", lambda *_: nullcontext(snapshot))
    def forbidden(*_, **__):
        pytest.fail("The native tool must not read an escaping hierarchy")
    monkeypatch.setattr(native, "_execute", forbidden)
    results, _ = native._revision("unused", "unused", time.monotonic() + 10)
    assert results and all(result.outcome == "failed" for result in results.values())


def test_real_git_symlink_and_submodule_are_excluded(project):
    repo_id, base, _, _, root, command = project
    oid = subprocess.check_output(["git", "-C", str(root), "hash-object", "-w", "--stdin"],
                                  input="../outside.kicad_sch", text=True).strip()
    command("update-index", "--add", "--cacheinfo", f"120000,{oid},link.kicad_sch")
    command("update-index", "--add", "--cacheinfo", f"160000,{base},submodule.kicad_pcb")
    command("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "-m", "Nonregular inputs")
    revision = command("rev-parse", "HEAD")
    git._fetch(git._repository(repo_id), "fixture/phase2")
    with materialize(repo_id, revision) as snapshot:
        assert {path for path, _ in snapshot.issues} == {"link.kicad_sch", "submodule.kicad_pcb"}
        assert not (snapshot.root / "link.kicad_sch").exists()


def test_native_failure_contracts(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_DATA_DIR", str(tmp_path / "state"))
    snapshot = Snapshot(tmp_path, {"board.kicad_pcb"})
    (tmp_path / "board.kicad_pcb").write_text("fixture")
    monkeypatch.setattr(native, "executable", lambda: None)
    result = native._execute(snapshot, "board.kicad_pcb", "drc", {})["drc"]
    assert result.outcome == "not checked"
    monkeypatch.setattr(native, "executable", lambda: "fake-kicad")
    monkeypatch.setattr(native, "tool_version", lambda: "10.0.6")
    monkeypatch.setattr(native, "_environment", lambda *_: {})
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 40)
    monkeypatch.setattr(native.subprocess, "run", timeout)
    assert "timed out" in native._execute(snapshot, "board.kicad_pcb", "drc", {})["drc"].detail
    def malformed(args, **kwargs):
        Path(args[args.index("--output") + 1]).write_text('{"violations": []}')
        return subprocess.CompletedProcess(args, 0)
    monkeypatch.setattr(native.subprocess, "run", malformed)
    assert native._execute(snapshot, "board.kicad_pcb", "drc", {})["drc"].outcome == "failed"
    assert list((tmp_path / "state/kicad-tmp").iterdir()) == []


def test_environment_contains_no_parent_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "never-pass-this")
    monkeypatch.setenv("OPENAI_API_KEY", "never-pass-this")
    monkeypatch.setenv("KICAD10_SYMBOL_DIR", "https://external.invalid")
    env = native._environment("fake-kicad", tmp_path)
    assert "never-pass-this" not in str(env) and "external.invalid" not in str(env)


def test_lifecycle_requires_both_runs_and_unique_object_evidence():
    row = dict(rule="clearance", summary="Measured 0.1 mm", scope="violations", path="board.kicad_pcb",
               items=[dict(uuid="50000000-0000-4000-8000-000000000000")])
    a = native.Result("ran", "", [row])
    b = native.Result("ran", "", [{**row, "summary": "Measured 0.12 mm"}])
    assert native.lifecycles(a, b)[0][0] == "existing"
    assert native.lifecycles(None, b)[0][0] == "present_at_head"
    assert native.lifecycles(native.Result("failed", ""), b)[0][0] == "present_at_head"
    assert native.lifecycles(a, native.Result("failed", "")) == []
    assert native.lifecycles(a, native.Result("ran", ""))[0][0] == "resolved"
    assert native.lifecycles(native.Result("ran", ""), b)[0][0] == "new"
    assert all(row[0] == "present_at_head" for row in native.lifecycles(a, native.Result("ran", "", [row, row])))
    assert native.lifecycles(a, native.Result("ran", "", [], settings="changed")) == []


def test_real_native_phase2_gate(project, tmp_path):
    if native.tool_version() in {"unavailable", "unsupported"}:
        pytest.skip("Native gate requires installed KiCad 9/10; offline adapter tests still run")
    repo_id, base, head, inherited, _, _ = project
    findings, coverage = native.collect(repo_id, head, base)
    assert all(c["outcome"] == "ran" for c in coverage
               if c["tool"] == "kicad-cli" and c["check"] != "Library consistency"), coverage
    for rule in ("kicad.drc.tracks_crossing", "kicad.erc.pin_not_connected", "kicad.parity.footprint_symbol_mismatch"):
        found = next(f for f in findings if f["rule_id"] == rule)
        assert found["lifecycle"] == "new", found
        assert found["evidence"][0]["sha"] == head
        assert "UUID" in found["evidence"][0]["locator"]
    assert any(f["lifecycle"] == "existing" for f in findings)
    assert all(f["status"] == "unverified" for f in findings if ".lib_" in f["rule_id"])
    # Routing-only differs from the clean board without any footprint/pad changes.
    a = parse_board((FIXTURES / "clean/board.kicad_pcb").read_bytes())
    b = parse_board((FIXTURES / "routing/board.kicad_pcb").read_bytes())
    assert compare_boards(a, b) == []
    replay, coverage2 = native.collect(repo_id, inherited, head)
    assert next(f for f in replay if f["rule_id"] == "kicad.drc.tracks_crossing")["lifecycle"] == "existing"
    assert next(f for f in replay if f["rule_id"] == "kicad.erc.pin_not_connected")["lifecycle"] == "resolved"
    assert next(f for f in replay if f["rule_id"] == "kicad.parity.footprint_symbol_mismatch")["lifecycle"] == "resolved"
    # Persist the actual gate evidence for a reviewer, with immutable commit pairs.
    report = dict(repo_id=repo_id, store=str(tmp_path / "state"), base=base, head=head, inherited=inherited,
                  version=native.tool_version(), findings=findings, coverage=coverage,
                  replay=replay, replay_coverage=coverage2)
    (Path("data") / "phase2-native-gate.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert list((tmp_path / "state/kicad-tmp").iterdir()) == []


def test_cache_tracks_tool_availability(project, monkeypatch):
    repo_id, base, head, _, _, _ = project
    monkeypatch.setattr(native, "tool_version", lambda: "unavailable")
    a = workspace_audit._descriptor(repo_id, head, base)
    monkeypatch.setattr(native, "tool_version", lambda: "10.0.6")
    b = workspace_audit._descriptor(repo_id, head, base)
    assert a.id != b.id


def test_native_hierarchical_sheet_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_DATA_DIR", str(tmp_path / "state"))
    if native.tool_version() in {"unavailable", "unsupported"}:
        pytest.skip("Hierarchy gate requires installed KiCad 9/10")
    root = '''(kicad_sch (version 20250114) (generator "eeschema")
      (uuid a0000000-0000-4000-8000-000000000000) (paper "A4") (lib_symbols)
      (sheet (at 25.4 25.4) (size 25.4 25.4)
        (uuid b0000000-0000-4000-8000-000000000000)
        (property "Sheetname" "Child" (at 25.4 24.13 0) (effects (font (size 1 1))))
        (property "Sheetfile" "child.kicad_sch" (at 25.4 52.07 0) (effects (font (size 1 1))))))'''
    (tmp_path / "root.kicad_sch").write_text(root)
    shutil.copyfile(FIXTURES / "broken/board.kicad_sch", tmp_path / "child.kicad_sch")
    snapshot = Snapshot(tmp_path, {"root.kicad_sch", "child.kicad_sch"})
    sheets = snapshot.sheets("root.kicad_sch")
    assert len(sheets) == 2
    result = native._execute(snapshot, "root.kicad_sch", "erc", sheets)["erc"]
    assert result.outcome == "ran", result.detail
    pin = next(row for row in result.rows if row["rule"] == "pin_not_connected")
    assert pin["path"] == "child.kicad_sch"
    assert "b0000000-0000-4000-8000-000000000000" in pin["scope"]


def test_native_workspace_api_gate(project):
    """Full API -> worker -> native CLI -> persisted evidence -> source preview."""
    if native.tool_version() in {"unavailable", "unsupported"}:
        pytest.skip("Native API gate requires installed KiCad 9/10")
    from fastapi.testclient import TestClient
    from extrude.api.server import app
    repo_id, base, head, _, _, _ = project
    client = TestClient(app)
    root = f"/v1/github/repositories/{repo_id}"
    started = client.post(root + "/audits", json={"revision": head, "base": base})
    assert started.status_code == 202, started.text
    saved_id = started.json()["id"]
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        response = client.get(root + "/audits/" + saved_id)
        assert response.status_code == 200
        report = response.json()
        if report["state"] not in {"running", "queued"}:
            break
        time.sleep(.1)
    assert report["state"] == "partial", report  # optional heuristics remain explicit
    assert all(row["outcome"] == "ran" for row in report["coverage"]
               if row["tool"] == "kicad-cli" and row["check"] != "Library consistency")
    assert (report["base_sha"], report["head_sha"]) == (base, head)
    for rule in ("kicad.drc.tracks_crossing", "kicad.erc.pin_not_connected", "kicad.parity.footprint_symbol_mismatch"):
        finding = next(f for f in report["findings"] if f["rule_id"] == rule)
        assert finding["status"] == "verified" and finding["lifecycle"] == "new"
        for evidence in finding["evidence"] + finding["related"]:
            preview = client.get(root + "/preview", params={"revision": evidence["sha"], "path": evidence["path"]})
            assert preview.status_code == 200 and preview.json()["text"]
    assert client.get(root + "/workspace", params={"revision": head, "base": base}).json()["audit"]["id"] == saved_id
    assert client.post(root + "/audits", json={"revision": head, "base": base}).json()["id"] == saved_id
    assert TestClient(app).get(root + "/audits/" + saved_id).json() == report
    comparison = client.get(root + "/schematic", params={"revision": head, "base": base, "path": "board.kicad_sch"})
    assert comparison.status_code == 200 and comparison.json()["before"]["symbols"] == 1
