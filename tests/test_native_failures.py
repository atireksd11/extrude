"""Four independent live-test failure modes; all preserve named coverage."""
import json
import subprocess
from contextlib import nullcontext
from pathlib import Path

import pytest

from extrude import kicad_audit as native, github_history as git
from extrude.kicad_snapshot import Snapshot, materialize

FIXTURES = Path(__file__).parent / "fixtures/native_failures"


def test_kicad9_coverage_is_proven_by_explicit_command_not_invented():
    data = (FIXTURES / "json9/drc.json").read_bytes()
    with pytest.raises(ValueError, match="coverage"):
        native.parse_report(data, "drc", "esp32-4-channel-relays.kicad_pcb", {})
    assert native.parse_report(data, "drc", "esp32-4-channel-relays.kicad_pcb", {}, requested_severities=True).outcome == "ran"
    report = json.loads(data)
    report.pop("violations")
    with pytest.raises(ValueError, match="coverage"):
        native.parse_report(json.dumps(report).encode(), "drc", report["source"], {}, requested_severities=True)


@pytest.mark.parametrize("mode", ["newer_format", "timeout"])
def test_failed_process_saves_named_cause_input_version_and_stderr(mode, tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_DATA_DIR", str(tmp_path / "state"))
    path = tmp_path / "board.kicad_pcb"
    path.write_bytes((FIXTURES / "newer_format/board.kicad_pcb").read_bytes())
    monkeypatch.setattr(native, "executable", lambda: "/usr/bin/kicad-cli")
    monkeypatch.setattr(native, "tool_version", lambda: native.PINNED_VERSION)
    def execute(args, **kwargs):
        assert "--severity-error" in args and "--severity-warning" in args
        kwargs["stderr"].write(b"Failed to load board\n")
        kwargs["stderr"].flush()
        if mode == "timeout":
            raise subprocess.TimeoutExpired(args, native.TIMEOUT)
        return subprocess.CompletedProcess(args, 3)
    monkeypatch.setattr(native.subprocess, "run", execute)
    results = native._execute(Snapshot(tmp_path, {path.name}), path.name, "drc", {}, parity=True)
    for result in results.values():
        assert result.outcome == "failed"
        assert ("newer_format_unsupported" if mode == "newer_format" else "time_budget_exceeded") in result.detail
        assert "evidence" in result.detail
    evidence = next((tmp_path / "state/native-evidence").iterdir())
    assert (evidence / "input.kicad_pcb").read_bytes() == path.read_bytes()
    assert (evidence / "stderr.log").read_text() == "Failed to load board\n"
    assert json.loads((evidence / "run.json").read_text())["version"] == native.PINNED_VERSION


def test_case_collision_preserves_files_and_does_not_suppress_checks(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_DATA_DIR", str(tmp_path / "state"))
    blobs = {str(p.relative_to(FIXTURES / "case_collision")): p.read_bytes()
             for p in (FIXTURES / "case_collision").rglob("*.dcm")}
    blobs["board.kicad_pcb"] = b"input"
    blobs["board.kicad_sch"] = (Path(__file__).parent / "fixtures/phase2/clean/board.kicad_sch").read_bytes()
    monkeypatch.setattr(git, "inventory", lambda *a, **k: dict(next_offset=None, files=[dict(path=p) for p in blobs]))
    monkeypatch.setattr(git, "regular_blob", lambda r, s, p, **k: blobs[p])
    with materialize("repo", "sha") as snap:
        assert not snap.issues and snap.warnings
        assert set(blobs) == snap.files
        monkeypatch.setattr(native, "materialize", lambda *a: nullcontext(snap))
        monkeypatch.setattr(native, "_execute", lambda s, p, c, sheets, parity=False, **k:
            {name: native.Result("ran", "fixture run") for name in ([c, "parity"] if parity else [c])})
        import time
        results, _ = native._revision("repo", "sha", time.monotonic() + 30)
        assert all(results["board.kicad_pcb", name].outcome == "ran" for name in ("drc", "parity"))
        assert results["board.kicad_sch", "erc"].outcome == "ran"
