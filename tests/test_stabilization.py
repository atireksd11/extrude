"""Slice 0: truth in scores, safe upgrades, and installed UI routes."""

import sqlite3
import urllib.request

import pytest

from fastapi.testclient import TestClient

from extrude.api.compare import CompareRequest, run_compare
from extrude.api.server import app
from extrude.migrations.project_map import SCHEMA_VERSION
from extrude.project_map import list_projects


def test_parsing_openscad_does_not_claim_a_design_pass():
    response = run_compare(CompareRequest(artifact="cube([20, 20, 20]);", filename="part.scad", offline=True))
    assert response.mode == "audit"
    assert response.raw.status == "unverified"
    assert response.raw.percent is None
    assert response.raw.out_of == 0
    assert all(row.passed is not True for row in response.raw.checks)
    assert response.harness.percent is None


def test_empty_netlist_does_not_claim_a_wiring_pass():
    response = run_compare(CompareRequest(artifact="(export (version E))", filename="empty.net", offline=True))
    assert response.status == "unverified"
    assert response.raw.percent is None
    assert response.raw.out_of == 0


def test_offline_suite_blocks_outbound_http():
    with pytest.raises(AssertionError, match="Outbound HTTP is disabled"):
        urllib.request.urlopen("https://example.invalid/")


def test_project_database_upgrade_keeps_existing_rows(tmp_path, monkeypatch):
    path = tmp_path / "old.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL UNIQUE, onshape_url TEXT, created_at TEXT NOT NULL)")
        db.execute("INSERT INTO projects VALUES (1, 'Existing', 'C:/existing', NULL, '2026-01-01')")
    monkeypatch.setenv("EXTRUDE_PROJECT_DB", str(path))
    assert list_projects()[0]["name"] == "Existing"
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert db.execute("SELECT demo FROM projects WHERE id=1").fetchone()[0] == 0
    assert list_projects()[0]["name"] == "Existing"


def test_both_pages_and_assets_are_served(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUDE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("EXTRUDE_PROJECT_DB", raising=False)
    client = TestClient(app)
    for route in ("/", "/projects", "/static/app.js", "/static/projects.js", "/v1/projects", "/v1/status"):
        assert client.get(route).status_code == 200
    demo = client.post("/v1/projects/demo")
    assert demo.status_code == 200
    project_id = demo.json()["project"]["id"]
    changed = client.post(f"/v1/projects/{project_id}/demo-change")
    assert changed.status_code == 200
    assert any(check["status"] == "failed" for check in changed.json()["checks"])
