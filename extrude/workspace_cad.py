"""A small CAD inspection tool callable by the UI and a future agent harness."""

import hashlib
from importlib.metadata import version, PackageNotFoundError
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import BoundedSemaphore
import uuid

from extrude import github_history as git
from extrude.kicad_snapshot import temporary_directory
from extrude.runtime import data_dir

MAX_STEP_BYTES = 32 * 1024 * 1024
TIMEOUT = 120
WORKER_VERSION = 4
_SLOTS = BoundedSemaphore(2)


def tool_versions():
    result = {}
    for package in ("cadquery", "cadquery-ocp"):
        try:
            result[package] = version(package)
        except PackageNotFoundError:
            result[package] = "unavailable"
    return result


def read_step(data: bytes, preview=False) -> dict:
    if len(data) > MAX_STEP_BYTES:
        raise ValueError("STEP exceeds the 32 MiB inspection limit.")
    if b"ISO-10303-21" not in data[:256].upper() or b"END-ISO-10303-21" not in data[-512:].upper():
        raise ValueError("Expected a complete STEP Part 21 file.")
    tools = tool_versions()
    if "unavailable" in tools.values():
        raise ValueError("CadQuery/OCP is not installed; STEP inspection is unavailable.")
    key = hashlib.sha256(data + json.dumps([tools, WORKER_VERSION, bool(preview)], sort_keys=True).encode()).hexdigest()
    directory = data_dir() / "cad-cache"
    cache = directory / f"{key}.json"
    if cache.is_file():
        return json.loads(cache.read_text(encoding="utf-8"))
    with temporary_directory("step-") as folder:
        root = Path(folder)
        source, output = root / "input.step", root / "result.json"
        source.write_bytes(data)
        env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
        env.update(PATH=str(Path(sys.executable).parent) + os.pathsep + os.defpath,
                   TEMP=str(root), TMP=str(root), HOME=str(root), USERPROFILE=str(root),
                   APPDATA=str(root), LOCALAPPDATA=str(root))
        command = [sys.executable, "-I", str(Path(__file__).with_name("cad_worker.py")),
                   str(source), str(output), "preview" if preview else "facts"]
        try:
            if not _SLOTS.acquire(timeout=3):
                raise ValueError("CAD workers are busy. Retry the inspection when another check finishes.")
            try:
                run = subprocess.run(command, cwd=root, env=env, timeout=TIMEOUT,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            finally:
                _SLOTS.release()
            if run.returncode or not output.is_file() or output.stat().st_size > 3 * 1024 * 1024:
                raise ValueError("STEP import/preview failed. Geometry is unverified; try measurements without preview.")
            result = json.loads(output.read_text(encoding="utf-8"))
        except subprocess.TimeoutExpired as exc:
            raise ValueError(f"STEP inspection timed out after {TIMEOUT}s; geometry is unverified.") from exc
        except OSError as exc:
            raise ValueError("Could not start the CAD worker; STEP is unverified.") from exc
    directory.mkdir(parents=True, exist_ok=True)
    pending = directory / f"{key}.{uuid.uuid4().hex}.tmp"
    try:
        pending.write_text(json.dumps(result, allow_nan=False), encoding="utf-8")
        os.replace(pending, cache)
    finally:
        pending.unlink(missing_ok=True)
    return result


def inspect_asset(repo_id: str, revision: str, path: str, include_preview=False) -> dict:
    """No arbitrary code/command input. Tools receive an immutable Git blob."""
    from extrude.workspace_checks import facts, evidence
    sha, _ = git.comparison_revisions(repo_id, revision)
    if Path(path).suffix.lower() not in {".stp", ".step", ".stl", ".obj"}:
        raise ValueError("Choose a STEP, STP, STL or OBJ asset.")
    measurements = facts(repo_id, sha, path, preview=include_preview)
    return dict(repo_id=repo_id, sha=sha, path=path, facts=measurements,
                evidence=[evidence(repo_id, sha, path, "CAD bounds and geometry facts")])
