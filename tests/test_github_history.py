"""Exercise the actual Git cache against a controlled local remote."""

import subprocess

import pytest
from fastapi.testclient import TestClient

from extrude import github_history as store
from extrude.api.server import app


def board_source(x: int, net: str) -> str:
    return f'''(kicad_pcb (version 20241229) (generator pcbnew)
      (net 1 "{net}")
      (footprint "Connector:Header" (layer "F.Cu") (at {x} 20)
        (uuid "26a9ce10-32a1-41f6-94ca-67b1e8290eb8") (property "Reference" "J1")
        (pad "1" thru_hole circle (at 0 0) (size 2 2) (drill 1)
          (layers "*.Cu" "*.Mask") (net 1 "{net}"))))\n'''


def test_rejects_non_github_sources_and_paths():
    assert store.normalize("https://github.com/Owner/Robot.git/") == "owner/robot"
    for value in ("file:///local/repo", "https://github.com.evil.test/owner/repo",
                  "https://x@github.com/owner/repo", "owner/..", "owner/repo/issues"):
        with pytest.raises(ValueError):
            store.normalize(value)
    with pytest.raises(KeyError):
        store.sync("../outside")


def test_import_sync_and_compare_saved_history(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_DATA_DIR", str(tmp_path / "state"))
    source = tmp_path / "source"
    source.mkdir()

    def git(*args):
        return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()

    def commit(message):
        git("add", "-A")
        git("-c", "user.name=Builder", "-c", "user.email=builder@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "-m", message)
        return git("rev-parse", "HEAD")

    def fetch(repo, _source):
        store._git(repo, "fetch", "--no-tags", str(source), "+HEAD:refs/atlas/fetched")

    monkeypatch.setattr(store, "_fetch", fetch)
    git("init", "--template=")
    board = source / "main.kicad_pcb"
    before_board = board_source(10, "GND")
    after_board = board_source(12, "RESET")
    board.write_text(before_board, encoding="utf-8")
    (source / "main.kicad_sch").write_text("schematic\n", encoding="utf-8")
    first = commit("First board")
    board.write_text(after_board, encoding="utf-8")
    second = commit("Update board")

    client = TestClient(app)
    assert client.get("/projects/github").status_code == 200
    assert client.get("/static/github.js").status_code == 200
    root = "/v1/github/repositories"
    response = client.post(root, json={"source": "https://github.com/Owner/Robot"})
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["head"] == second
    assert client.get(root).json() == [saved]
    url = f"{root}/{saved['id']}"
    history = client.get(f"{url}/commits", params={"limit": 1}).json()
    assert history["commits"][0]["sha"] == second
    assert history["next_offset"] == 1
    older = client.get(f"{url}/commits", params={"revision": second, "offset": 1}).json()
    assert [row["sha"] for row in older["commits"]] == [first]
    files = client.get(f"{url}/files", params={"revision": first}).json()["files"]
    assert {row["kind"] for row in files} == {"pcb", "schematic"}
    changes = client.get(f"{url}/changes", params={"revision": second}).json()
    assert changes["base"] == first
    assert [(row["path"], row["status"]) for row in changes["files"]] == [("main.kicad_pcb", "M")]
    assert store.changes(saved["id"], first)["total"] == 2
    for revision, expected in ((first, before_board), (second, after_board)):
        preview = client.get(f"{url}/preview", params={"revision": revision, "path": board.name})
        assert preview.json()["text"] == expected
    review = client.get(f"{url}/pcb", params={"revision": second, "path": board.name}).json()
    assert review["status"] == "compared"
    assert review["before"]["sha"] == first and review["after"]["sha"] == second
    assert review["changes"] == [
        {"kind": "position_changed", "reference": "J1", "before": [10, 20], "after": [12, 20]},
        {"kind": "pad_net_changed", "reference": "J1", "pad": "1", "before": ["GND"], "after": ["RESET"]},
    ]
    first_review = client.get(f"{url}/pcb", params={"revision": first, "path": board.name}).json()
    assert first_review["before"]["status"] == "absent"
    assert first_review["changes"][0]["kind"] == "footprint_added"

    git("mv", board.name, "renamed.kicad_pcb")
    third = commit("Rename board")
    assert client.post(f"{url}/sync").json()["head"] == third
    delta = client.get(f"{url}/changes", params={"revision": third, "base": second}).json()["files"]
    assert delta == [{"path": "renamed.kicad_pcb", "previous_path": board.name, "status": "R", "kind": "pcb"}]
    renamed = client.get(f"{url}/pcb", params={
        "revision": third, "base": second, "path": "renamed.kicad_pcb", "previous_path": board.name
    }).json()
    assert renamed["status"] == "compared" and renamed["total"] == 0
    assert renamed["before"]["path"] == board.name
    (source / "renamed.kicad_pcb").write_text("(kicad_pcb (version 20241229)", encoding="utf-8")
    corrupt = commit("Save broken board")
    client.post(f"{url}/sync").raise_for_status()
    review = client.get(f"{url}/pcb", params={"revision": corrupt, "path": "renamed.kicad_pcb"}).json()
    assert review["status"] == "unverified" and review["changes"] == []
    assert review["after"]["status"] == "unverified"

    # Simulate a rewrite of the remote branch and a restart of the reader.
    git("reset", "--hard", first)
    rewritten = client.post(f"{url}/sync").json()
    assert rewritten["previous_head"] == corrupt
    assert set(rewritten["saved_tips"]) == {first, second, third, corrupt}
    assert client.post(f"{url}/sync").json()["previous_head"] == corrupt
    assert store.preview(saved["id"], third, "renamed.kicad_pcb")["text"] == after_board
    assert store.history(saved["id"], revision=third)["commits"][0]["sha"] == third

    def fail(*_args):
        raise store.GitHubError("GitHub unavailable")

    monkeypatch.setattr(store, "_fetch", fail)
    assert client.post(f"{url}/sync").status_code == 502
    assert client.get(root).json()[0]["head"] == first
