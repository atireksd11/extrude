"""Day 1 integration gates using real Git objects and the Atlas API."""

import json
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from extrude import github_history, workspace, workspace_audit
from extrude.api.server import app
from extrude.api import github as github_api
from fastapi import HTTPException


def make_fixture(root: Path) -> tuple[str, str]:
    root.mkdir(parents=True)

    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()

    def save(path, content):
        file = root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")

    def board(x, net):
        return f'''(kicad_pcb (version 20241229)
          (footprint "Test:USB" (layer "F.Cu") (at {x} 20) (property "Reference" "J1")
            (pad "1" smd rect (net "{net}"))))'''

    def commit(subject):
        git("add", "-A")
        git("-c", "user.name=Builder", "-c", "user.email=builder@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "-m", subject)
        return git("rev-parse", "HEAD")

    git("init", "--template=")
    save("electronics/main.kicad_pcb", board(10, "GND"))
    save("electronics/main.kicad_sch", "(kicad_sch (version 20250114))")
    save("firmware/motor.ino", "#define MOTOR_PIN 12\n")
    save("cad/enclosure.stl", "solid fixture\nendsolid fixture\n")
    save("parts/bom.csv", "Reference,Part Number,Quantity\nJ1,001,1\n")
    save("tools/helper.py", "print('helper')\n")
    save("docs/setup.md", "Stable setup documentation.\n")
    save("docs/old-notes.md", "These notes were deleted.\n")
    save("README.md", "Robot fixture.\n")
    base = commit("Build robot baseline")
    git("mv", "README.md", "docs/project.md")
    (root / "docs/old-notes.md").unlink()
    save("electronics/main.kicad_pcb", board(12, ""))
    save("firmware/motor.ino", "#define MOTOR_PIN 13\n")
    return base, commit("Move USB and update firmware")


@pytest.fixture
def pilot(tmp_path, monkeypatch):
    # These minimal syntax-only boards test the Git/worker contracts; native
    # KiCad gates use complete projects in test_kicad_audit.py.
    monkeypatch.setattr(workspace_audit.kicad_audit, "executable", lambda: None)
    monkeypatch.setenv("EXTRUDE_DATA_DIR", str(tmp_path / "state"))
    remote = tmp_path / "robot"
    base, head = make_fixture(remote)

    def fetch(repo, _source):
        # Keep this fixture offline and avoid Git's shell-based local transport.
        shutil.copytree(remote / ".git" / "objects", repo / "objects", dirs_exist_ok=True)
        tip = subprocess.check_output(["git", "-C", str(remote), "rev-parse", "HEAD"], text=True).strip()
        github_history._git(repo, "update-ref", "refs/atlas/fetched", tip)

    monkeypatch.setattr(github_history, "_fetch", fetch)
    return base, head


def test_workspace_pins_both_revisions_and_persists_audit(pilot, monkeypatch):
    base, head = pilot
    client = TestClient(app)
    root = "/v1/github/repositories"
    assert client.post(root, json={"source": "https://invalid.example/robot"}).status_code == 400
    imported = client.post(root, json={"source": "builder/robot"}).json()
    repo_id = imported["id"]
    repo = f"{root}/{repo_id}"
    response = client.get(f"{repo}/workspace", params={"revision": head, "limit": 2})
    assert response.status_code == 200, response.text
    first = response.json()
    assert (first["base_sha"], first["head_sha"]) == (base, head)
    assert first["inventory"]["next_offset"] == first["changes"]["next_offset"] == 2
    second = client.get(f"{repo}/workspace", params={"revision": head, "file_offset": 2, "change_offset": 2}).json()
    files = first["inventory"]["files"] + second["inventory"]["files"]
    assert len({file["path"] for file in files}) == second["inventory"]["total"]
    assert {file["domain"] for file in files} == {"pcb", "schematic", "cad", "firmware", "code", "bom", "docs"}
    changes = first["changes"]["files"] + second["changes"]["files"]
    rename = next(row for row in changes if row["status"] == "R")
    assert (rename["previous_path"], rename["path"]) == ("README.md", "docs/project.md")
    removed = next(row for row in changes if row["status"] == "D")
    assert removed["path"] == "docs/old-notes.md"
    for sha, path, content in (
        (base, rename["previous_path"], "Robot fixture."),
        (head, rename["path"], "Robot fixture."),
        (base, removed["path"], "These notes were deleted."),
        (head, "docs/setup.md", "Stable setup documentation."),
    ):
        assert client.get(f"{repo}/preview", params={"revision": sha, "path": path}).json()["text"].strip() == content
    initial = client.get(f"{repo}/workspace", params={"revision": base}).json()
    assert initial["base_sha"] is None
    assert {row["status"] for row in initial["changes"]["files"]} == {"A"}
    assert client.get(f"{repo}/workspace", params={"revision": "bad"}).status_code == 400
    assert client.get(f"{repo}/workspace", params={"revision": "0" * 40}).status_code == 404

    entered, release = threading.Event(), threading.Event()
    original = workspace_audit._collect

    def pause(audit):
        entered.set()
        if not release.wait(15):
            raise RuntimeError("test synchronization timed out")
        original(audit)

    monkeypatch.setattr(workspace_audit, "_collect", pause)
    try:
        with ThreadPoolExecutor(max_workers=2) as threads:
            replies = list(threads.map(lambda _: client.post(f"{repo}/audits", json={"revision": head}), range(2)))
        assert all(reply.status_code == 202 for reply in replies)
        started, duplicate = [reply.json() for reply in replies]
        assert started["id"] == duplicate["id"]
        assert entered.wait(5)
        assert client.post(f"{repo}/audits", json={"revision": base}).status_code == 409
    finally:
        release.set()
    audit_url = f"{repo}/audits/{started['id']}"
    for _ in range(200):
        result = client.get(audit_url).json()
        if result["state"] not in {"queued", "running"}:
            break
        time.sleep(.05)
    assert result["state"] == "partial", result
    assert (result["base_sha"], result["head_sha"]) == (base, head)
    assert any(row["outcome"] == "unavailable" and row["domain"] == "firmware" for row in result["coverage"])
    disconnected = next(row for row in result["findings"] if row["rule_id"] == "pcb.pad_disconnected")
    assert disconnected["status"] == "suggestion"
    assert [item["sha"] for item in disconnected["evidence"]] == [base, head]
    assert disconnected["related"] == [{"sha": head, "path": "electronics/main.kicad_sch", "basis": "same_name"}]
    assert json.loads((workspace_audit._audit_dir() / f"{started['id']}.json").read_text()) == result
    assert TestClient(app).get(audit_url).json() == result
    assert client.get(f"{repo}/workspace", params={"revision": head}).json()["audit"]["id"] == started["id"]


def test_interrupted_audit_and_failed_import_are_recoverable(pilot, monkeypatch):
    _, head = pilot
    client = TestClient(app)
    imported = github_history.connect("builder/robot")
    repo = f"/v1/github/repositories/{imported['id']}"
    audit = workspace_audit._descriptor(imported["id"], head, None)
    audit.state = "running"
    workspace_audit._save(workspace_audit._audit_dir() / f"{audit.id}.json", audit)
    reopened = client.get(f"{repo}/audits/{audit.id}").json()
    assert reopened["state"] == "failed"
    assert "interrupted" in reopened["detail"]
    def fail(*_args):
        raise github_history.GitHubError("GitHub import failed. Check the repository URL and read access.")
    monkeypatch.setattr(github_history, "_fetch", fail)
    error = client.post("/v1/github/repositories", json={"source": "builder/unavailable"})
    assert error.status_code == 502
    assert "read access" in error.json()["detail"]
    assert client.get("/v1/github/repositories").json() == [imported]


def test_core_workspace_workers_and_restart(pilot, monkeypatch):
    """Verify Git and worker contracts without an HTTP transport."""
    base, head = pilot
    repo_id = github_history.connect("builder/robot")["id"]
    page = workspace.view(repo_id, head, None, 0, 0, 2)
    assert (page["base_sha"], page["head_sha"]) == (base, head)
    assert page["inventory"]["next_offset"] == page["changes"]["next_offset"] == 2
    route_result = github_api.get_workspace(repo_id, head, None, 0, 0, 2)
    assert route_result["head_sha"] == head and route_result["audit"] is None
    with pytest.raises(HTTPException) as invalid:
        github_api.get_workspace(repo_id, "invalid", None, 0, 0, 2)
    assert invalid.value.status_code == 400
    rest = workspace.view(repo_id, head, base, 2, 2, 100)
    files = page["inventory"]["files"] + rest["inventory"]["files"]
    assert len({file["path"] for file in files}) == rest["inventory"]["total"]
    assert {file["domain"] for file in files} == {"pcb", "schematic", "cad", "firmware", "code", "bom", "docs"}
    changes = page["changes"]["files"] + rest["changes"]["files"]
    rename = next(row for row in changes if row["status"] == "R")
    assert (rename["previous_path"], rename["path"]) == ("README.md", "docs/project.md")
    assert github_history.preview(repo_id, base, "docs/old-notes.md")["text"] == "These notes were deleted.\n"
    assert github_history.preview(repo_id, head, "docs/setup.md")["text"] == "Stable setup documentation.\n"
    initial = workspace.view(repo_id, base, None, 0, 0, 100)
    assert initial["base_sha"] is None and {row["status"] for row in initial["changes"]["files"]} == {"A"}
    with pytest.raises(ValueError):
        workspace.view(repo_id, "invalid", None, 0, 0, 100)

    entered, release = threading.Event(), threading.Event()
    original = workspace_audit._collect

    def collect(audit):
        entered.set()
        if not release.wait(15):
            raise RuntimeError("test timed out")
        original(audit)

    monkeypatch.setattr(workspace_audit, "_collect", collect)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            runs = list(pool.map(lambda _: workspace_audit.start(repo_id, head, None), range(2)))
        assert runs[0].id == runs[1].id
        assert entered.wait(5)
        with pytest.raises(workspace_audit.AuditBusy):
            workspace_audit.start(repo_id, base, None)
    finally:
        release.set()
    for _ in range(200):
        audit = workspace_audit.get(repo_id, runs[0].id)
        if audit.state not in {"running", "queued"}:
            break
        time.sleep(.05)
    assert audit.state == "partial", audit
    assert {row.rule_id for row in audit.findings} == {"pcb.position_changed", "pcb.pad_disconnected", "firmware.constant_changed"}
    assert all(row.status != "verified" for row in audit.findings)
    assert audit.findings[0].related[0].basis == "same_name"
    assert audit.findings[0].related[0].path == "electronics/main.kicad_sch"
    assert any(row.outcome == "unavailable" and row.domain == "firmware" for row in audit.coverage)
    output = subprocess.check_output([
        sys.executable, "-c",
        "from extrude.workspace_audit import get; import sys; print(get(sys.argv[1], sys.argv[2]).model_dump_json())",
        repo_id, audit.id,
    ], text=True)
    assert json.loads(output) == audit.model_dump(mode="json")
    assert workspace_audit.start(repo_id, head, None).id == audit.id

    interrupted = workspace_audit._descriptor(repo_id, base, None)
    interrupted.state = "running"
    workspace_audit._save(workspace_audit._audit_dir() / f"{interrupted.id}.json", interrupted)
    assert workspace_audit.get(repo_id, interrupted.id).state == "failed"
    retried = workspace_audit.start(repo_id, base, None)
    for _ in range(200):
        retried = workspace_audit.get(repo_id, retried.id)
        if retried.state not in {"running", "queued"}:
            break
        time.sleep(.05)
    assert retried.state == "partial"


def test_core_audit_cache_and_file_failure(pilot, monkeypatch):
    base, head = pilot
    repo_id = github_history.connect("builder/robot")["id"]
    audit = workspace_audit._descriptor(repo_id, head, base)
    changed_version = workspace_audit.version
    monkeypatch.setattr(workspace_audit, "version", lambda _package: "different-parser")
    assert workspace_audit._descriptor(repo_id, head, base).id != audit.id
    monkeypatch.setattr(workspace_audit, "version", changed_version)
    original_collect = workspace_audit._collect
    monkeypatch.setattr(workspace_audit, "_MAX_FILES", 1)
    assert workspace_audit._descriptor(repo_id, head, base).id != audit.id
    original_collect(audit)
    assert any(row.check == "Audit scope" and row.outcome == "unsupported" for row in audit.coverage)

    def failure(*_args):
        raise github_history.GitHubError("Fixture failure")

    monkeypatch.setattr(workspace_audit, "_MAX_FILES", 1000)
    monkeypatch.setattr(workspace_audit, "_board", failure)
    failed_file = workspace_audit._descriptor(repo_id, head, base)
    original_collect(failed_file)
    assert any(row.path.endswith(".kicad_pcb") and row.outcome == "failed" for row in failed_file.coverage)
    assert any(row.domain == "firmware" for row in failed_file.coverage)
