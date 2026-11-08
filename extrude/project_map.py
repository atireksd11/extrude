"""Local project change map. Files are read, never edited."""

import hashlib
import difflib
import json
import os
import re
import shutil
import sqlite3
import struct
import subprocess
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from extrude.harness.registry import run_electrical
from extrude.parse.kicad_netlist import parse_kicad_netlist
from extrude.parse.kicad_netlist import _child, _children, _field, _parse, _tokens
from extrude.tools import tool_path
from extrude.migrations.project_map import migrate
from extrude.runtime import data_dir


KINDS = {
    ".kicad_sch": "schematic", ".net": "schematic",
    ".kicad_pcb": "pcb", ".scad": "cad", ".step": "cad",
    ".stp": "cad", ".stl": "cad", ".py": "firmware",
    ".cpp": "firmware", ".cc": "firmware", ".cxx": "firmware", ".c": "firmware", ".h": "firmware",
    ".ino": "firmware", ".rs": "firmware", ".hpp": "firmware",
    ".js": "firmware", ".ts": "firmware", ".md": "docs",
    ".pdf": "docs", ".txt": "docs", ".obj": "cad",
}
IMPACTS = {
    "firmware": ("schematic", "pcb"),
    "schematic": ("firmware", "pcb", "cad"),
    "pcb": ("schematic", "firmware", "cad"),
    "cad": ("pcb", "schematic"),
    "docs": (),
}
IGNORED = {".git", ".venv", "node_modules", "data", "build", "dist", "__pycache__"}
MAX_FILE_BYTES = 128_000_000
MAX_FILES = 1500
TEXT_PREVIEW_BYTES = 128_000
DEMO_SOURCE = Path(__file__).resolve().parent / "demo_robot"
_SCAN_LOCK = threading.RLock()


def _db_path() -> Path:
    return Path(os.environ.get("EXTRUDE_PROJECT_DB", str(data_dir() / "project-map.sqlite")))


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    try:
        migrate(db)
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_project(name: str, folder: str, onshape_url: str | None = None) -> dict:
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("Choose an existing project folder on this computer.")
    if not name.strip():
        raise ValueError("Give this project a name.")
    if onshape_url and not onshape_url.startswith("https://cad.onshape.com/documents/"):
        raise ValueError("Use an Onshape document URL, or leave it blank.")
    with _connect() as db:
        existing = db.execute("SELECT id FROM projects WHERE path = ?", (str(root),)).fetchone()
        if existing:
            project_id = existing["id"]
            db.execute("UPDATE projects SET name = ?, onshape_url = ? WHERE id = ?",
                       (name.strip(), onshape_url, project_id))
        else:
            cur = db.execute("INSERT INTO projects (name, path, onshape_url, created_at) VALUES (?, ?, ?, ?)",
                             (name.strip(), str(root), onshape_url, _now()))
            project_id = cur.lastrowid
    return scan_project(project_id)


def list_projects() -> list[dict]:
    with _connect() as db:
        rows = db.execute("SELECT * FROM projects ORDER BY id DESC").fetchall()
    return [dict(row) for row in rows]


def _files(root: Path) -> tuple[list[Path], list[dict]]:
    found: list[Path] = []
    skipped: list[dict] = []
    for folder, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in IGNORED and not d.startswith(".")]
        for name in names:
            path = Path(folder) / name
            if path.suffix.lower() not in KINDS:
                continue
            try:
                if not path.resolve().is_relative_to(root):
                    skipped.append({"path": path.relative_to(root).as_posix(), "reason": "Outside the project folder"})
                    continue
                size = path.stat().st_size
            except OSError:
                continue
            if size > MAX_FILE_BYTES:
                skipped.append({"path": path.relative_to(root).as_posix(), "reason": "File exceeds 128 MB scan limit"})
                continue
            found.append(path)
            if len(found) >= MAX_FILES:
                skipped.append({"path": "…", "reason": "Project exceeds 1,500 tracked files"})
                return found, skipped
    return found, skipped


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _preview(path: Path) -> str | None:
    if path.suffix.lower() not in {".py", ".cpp", ".c", ".h", ".hpp", ".ino", ".rs",
                                   ".js", ".ts", ".md", ".txt", ".scad", ".net",
                                   ".kicad_sch", ".kicad_pcb", ".step", ".stp"}:
        return None
    if path.stat().st_size > TEXT_PREVIEW_BYTES:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _diff(before: str | None, after: str | None, path: str) -> str | None:
    if before is None or after is None:
        return None
    lines = difflib.unified_diff(before.splitlines(), after.splitlines(),
                                 fromfile=f"before/{path}", tofile=f"after/{path}", lineterm="")
    return "\n".join(lines)[:12_000]


def _head(root: Path) -> str | None:
    try:
        result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                                capture_output=True, text=True, timeout=3, check=False)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _check_file(path: Path, kind: str) -> list[dict]:
    if path.suffix.lower() == ".net":
        try:
            from extrude.checks.api import wiring_evidence
            design = parse_kicad_netlist(path.read_text(encoding="utf-8"))
            report = run_electrical(design)
            if not report.blocking and not wiring_evidence(design):
                return [{"name": "Netlist preflight", "status": "unverified",
                         "detail": "Not checked: netlist has no complete component wiring evidence."}]
            return [{"name": "Netlist preflight", "status": "failed" if report.blocking else "passed",
                     "detail": "; ".join(report.blocking or report.warnings) or "No blocking wiring findings."}]
        except (ValueError, IndexError, UnicodeError) as exc:
            return [{"name": "Netlist preflight", "status": "unverified", "detail": str(exc)}]
    command = tool_path("kicad_cli")
    if path.suffix.lower() not in {".kicad_sch", ".kicad_pcb"}:
        return []
    if not command:
        return [{"name": "KiCad ERC/DRC", "status": "unverified", "detail": "kicad-cli is unavailable."}]
    mode = ["sch", "erc"] if kind == "schematic" else ["pcb", "drc"]
    try:
        result = subprocess.run([command, *mode, "--exit-code-violations", str(path)],
                                capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [{"name": "KiCad ERC/DRC", "status": "unverified", "detail": str(exc)}]
    output = (result.stdout + "\n" + result.stderr).strip()[-800:]
    status = "passed" if result.returncode == 0 else "failed" if result.returncode == 5 else "unverified"
    return [{"name": "KiCad ERC" if kind == "schematic" else "KiCad DRC",
             "status": status, "detail": output or f"Exit code {result.returncode}."}]


def _pin_checks(root: Path, saved_rules: list[dict]) -> list[dict]:
    """Compare confirmed firmware symbols with physical KiCad netlist pins."""
    manifest = root / "extrude-project.json"
    try:
        rows = []
        if manifest.is_file():
            config = json.loads(manifest.read_text(encoding="utf-8"))
            rows = config.get("pin_assignments", [])
        if not isinstance(rows, list):
            raise ValueError("pin_assignments must be a list")
        rows = [*rows, *saved_rules]
        results = []
        for row in rows:
            source = (root / row["firmware_file"]).resolve()
            netlist = (root / row["netlist_file"]).resolve()
            if not source.is_relative_to(root) or not netlist.is_relative_to(root):
                raise ValueError("Pin-map files must stay inside the project folder")
            symbol, net, ref = row["firmware_symbol"], row["schematic_net"], row["mcu_ref"]
            if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", symbol):
                raise ValueError("Invalid firmware symbol")
            code = source.read_text(encoding="utf-8")
            pattern = rf"\b{re.escape(symbol)}\b\s*(?:=\s*|\s+)(\d+)\b"
            found = re.search(pattern, code)
            if not found:
                results.append({"file": row["firmware_file"], "name": f"Pin map: {symbol}",
                                "status": "unverified", "detail": f"Could not read a numeric value for {symbol}."})
                continue
            expected = found.group(1)
            tree = _parse(_tokens(netlist.read_text(encoding="utf-8")))[0]
            export = _child(tree, "export") or tree
            actual = None
            for item in _children(_child(export, "nets"), "net"):
                if _field(item, "name") != net:
                    continue
                for node in _children(item, "node"):
                    if _field(node, "ref") == ref:
                        actual = _field(node, "pin")
            status = "passed" if actual == expected else "failed" if actual else "unverified"
            detail = f"Firmware {symbol} uses pin {expected}; {ref} on net {net} uses pin {actual or 'unknown'}."
            results.append({"file": row["firmware_file"], "name": f"Pin map: {symbol}",
                            "status": status, "detail": detail})
        return results
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, IndexError) as exc:
        return [{"file": "extrude-project.json", "name": "Pin map setup", "status": "unverified",
                 "detail": str(exc)}]


def list_pin_rules(project_id: int) -> list[dict]:
    with _connect() as db:
        rows = db.execute("SELECT * FROM pin_rules WHERE project_id = ? ORDER BY id", (project_id,)).fetchall()
    return [dict(row) for row in rows]


def add_pin_rule(project_id: int, rule: dict) -> dict:
    with _connect() as db:
        project = db.execute("SELECT path FROM projects WHERE id = ?", (project_id,)).fetchone()
        if project is None:
            raise KeyError(project_id)
        root = Path(project["path"])
        for field in ("firmware_file", "firmware_symbol", "netlist_file", "schematic_net", "mcu_ref"):
            if not isinstance(rule.get(field), str) or not rule[field].strip():
                raise ValueError(f"{field.replace('_', ' ').capitalize()} is required.")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", rule["firmware_symbol"]):
            raise ValueError("Firmware symbol must be a simple variable or define name.")
        for field in ("firmware_file", "netlist_file"):
            target = (root / rule[field]).resolve()
            if not target.is_relative_to(root) or not target.is_file():
                raise ValueError(f"Choose an existing {field.replace('_', ' ')} inside the project.")
        if Path(rule["netlist_file"]).suffix.lower() != ".net":
            raise ValueError("Choose an exported KiCad .net file.")
        duplicate = db.execute("SELECT 1 FROM pin_rules WHERE project_id = ? AND firmware_file = ? AND firmware_symbol = ? AND netlist_file = ? AND schematic_net = ? AND mcu_ref = ?",
                               (project_id, *(rule[field].strip() for field in ("firmware_file", "firmware_symbol", "netlist_file", "schematic_net", "mcu_ref")))).fetchone()
        if duplicate:
            raise ValueError("This pin check is already configured.")
        db.execute("INSERT INTO pin_rules (project_id, firmware_file, firmware_symbol, netlist_file, schematic_net, mcu_ref) VALUES (?, ?, ?, ?, ?, ?)",
                   (project_id, *(rule[field].strip() for field in ("firmware_file", "firmware_symbol", "netlist_file", "schematic_net", "mcu_ref"))))
    return scan_project(project_id)


def delete_pin_rule(project_id: int, rule_id: int) -> dict:
    with _connect() as db:
        row = db.execute("SELECT firmware_file FROM pin_rules WHERE project_id = ? AND id = ?", (project_id, rule_id)).fetchone()
        if row is None:
            raise KeyError(rule_id)
        db.execute("DELETE FROM pin_rules WHERE project_id = ? AND id = ?", (project_id, rule_id))
        remaining = db.execute("SELECT 1 FROM pin_rules WHERE project_id = ? AND firmware_file = ? LIMIT 1",
                               (project_id, row["firmware_file"])).fetchone()
        if not remaining:
            db.execute("UPDATE findings SET resolved_at = ? WHERE project_id = ? AND source = ? AND target = 'schematic' AND resolved_at IS NULL",
                       (_now(), project_id, row["firmware_file"]))
    return scan_project(project_id)


def scan_project(project_id: int) -> dict:
    with _SCAN_LOCK:
        return _scan_project(project_id)


def _scan_project(project_id: int) -> dict:
    with _connect() as db:
        project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if project is None:
            raise KeyError(project_id)
        root = Path(project["path"])
        if not root.is_dir():
            raise ValueError("Project folder is no longer available on this computer.")
        before = {row["path"]: row for row in db.execute(
            "SELECT path, kind, digest, size, modified_ns, preview FROM files WHERE project_id = ?", (project_id,))}
        current = {}
        paths, skipped = _files(root)
        for path in paths:
            relative = path.relative_to(root).as_posix()
            try:
                stat = path.stat()
                old = before.get(relative)
                unchanged = old is not None and old["size"] == stat.st_size and old["modified_ns"] == stat.st_mtime_ns
                current[relative] = {
                    "kind": KINDS[path.suffix.lower()],
                    "digest": old["digest"] if unchanged else _digest(path),
                    "size": stat.st_size,
                    "modified_ns": stat.st_mtime_ns,
                    "preview": old["preview"] if unchanged else _preview(path),
                }
            except OSError:
                continue
        first_scan = not before and not db.execute(
            "SELECT 1 FROM changes WHERE project_id = ? LIMIT 1", (project_id,)).fetchone()
        updated = []
        for relative, file in current.items():
            old = before.get(relative)
            if old is None or old["digest"] != file["digest"]:
                action = "added" if old is None else "updated"
                if not first_scan:
                    db.execute("INSERT INTO changes (project_id, path, kind, action, seen_at, diff) VALUES (?, ?, ?, ?, ?, ?)",
                               (project_id, relative, file["kind"], action, _now(),
                                _diff(old["preview"] if old else "", file["preview"], relative)))
                    updated.append((relative, file["kind"]))
            if (old is None or any(old[key] != file[key] for key in ("kind", "digest", "size", "modified_ns", "preview"))):
                db.execute("INSERT OR REPLACE INTO files (project_id, path, kind, digest, size, modified_ns, preview) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (project_id, relative, file["kind"], file["digest"], file["size"], file["modified_ns"], file["preview"]))
        for relative in before.keys() - current.keys():
            db.execute("DELETE FROM files WHERE project_id = ? AND path = ?", (project_id, relative))
            db.execute("INSERT INTO changes (project_id, path, kind, action, seen_at, diff) VALUES (?, ?, ?, ?, ?, ?)",
                       (project_id, relative, before[relative]["kind"], "removed", _now(),
                        _diff(before[relative]["preview"], "", relative)))
            updated.append((relative, before[relative]["kind"]))
        checks = []
        check_targets = updated or ([(relative, file["kind"]) for relative, file in current.items()
                                    if file["kind"] in {"schematic", "pcb"}] if first_scan else [])
        for relative, kind in check_targets:
            path = root / relative
            if path.is_file():
                checks.extend({"file": relative, **item} for item in _check_file(path, kind))
        db.execute("DELETE FROM checks WHERE project_id = ? AND (name LIKE 'Pin map:%' OR name = 'Pin map setup')",
                   (project_id,))
        rules = [dict(row) for row in db.execute("SELECT * FROM pin_rules WHERE project_id = ? ORDER BY id", (project_id,))]
        checks.extend(_pin_checks(root, rules))
        for item in checks:
            db.execute("INSERT OR REPLACE INTO checks VALUES (?, ?, ?, ?, ?, ?)",
                       (project_id, item["file"], item["name"], item["status"], item["detail"], _now()))
        for relative, _kind in updated:
            if relative not in current:
                db.execute("DELETE FROM checks WHERE project_id = ? AND path = ?", (project_id, relative))
        rows = db.execute("SELECT path, kind, size, modified_ns FROM files WHERE project_id = ? ORDER BY path", (project_id,)).fetchall()
        history = db.execute("SELECT id, path, kind, action, seen_at, diff FROM changes WHERE project_id = ? ORDER BY id DESC LIMIT 30",
                             (project_id,)).fetchall()
        check_rows = db.execute("SELECT path AS file, name, status, detail, seen_at FROM checks WHERE project_id = ? ORDER BY path",
                                (project_id,)).fetchall()
    kinds = {row["kind"] for row in rows}
    if project["onshape_url"]:
        kinds.add("cad")
    impacts = []
    pin_checks: dict[str, list[dict]] = {}
    for row in check_rows:
        if row["name"].startswith("Pin map:"):
            pin_checks.setdefault(row["file"], []).append(dict(row))
    for relative, kind in updated:
        for target in IMPACTS[kind]:
            if target in kinds:
                configured = pin_checks.get(relative, []) if kind == "firmware" and target == "schematic" else []
                pin = next((check for check in configured if check["status"] == "failed"), None)
                if configured and all(check["status"] == "passed" for check in configured):
                    continue
                if pin and pin["status"] == "failed":
                    impacts.append({"source": relative, "target": target, "status": "failed",
                                    "detail": pin["detail"],
                                    "suggestion": "Reconcile the firmware pin assignment with the KiCad netlist, then scan again."})
                    continue
                impacts.append({"source": relative, "target": target, "status": "possible",
                                "detail": f"Review {target} after this {kind} change.",
                                "suggestion": f"Compare the changed {kind} file with the connected {target} design; confirm any interface or dimension changes."})
    for source, configured in pin_checks.items():
        failed_pin = next((check for check in configured if check["status"] == "failed"), None)
        if failed_pin and not any(item["source"] == source and item["target"] == "schematic" and item["status"] == "failed" for item in impacts):
            impacts.append({"source": source, "target": "schematic", "status": "failed",
                            "detail": failed_pin["detail"],
                            "suggestion": "Reconcile the firmware pin assignment with the KiCad netlist, then scan again."})
    with _connect() as db:
        for source, configured in pin_checks.items():
            if configured and all(check["status"] == "passed" for check in configured):
                db.execute("UPDATE findings SET resolved_at = ? WHERE project_id = ? AND source = ? AND target = 'schematic' AND resolved_at IS NULL",
                           (_now(), project_id, source))
        for relative, _kind in updated:
            db.execute("UPDATE findings SET resolved_at = ? WHERE project_id = ? AND source = ? AND resolved_at IS NULL",
                       (_now(), project_id, relative))
        for item in impacts:
            existing = db.execute("SELECT 1 FROM findings WHERE project_id = ? AND source = ? AND target = ? AND status = ? AND detail = ? AND resolved_at IS NULL LIMIT 1",
                                  (project_id, item["source"], item["target"], item["status"], item["detail"])).fetchone()
            if existing:
                continue
            db.execute("INSERT INTO findings (project_id, source, target, status, detail, suggestion, seen_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (project_id, item["source"], item["target"], item["status"], item["detail"], item["suggestion"], _now()))
        recent = db.execute("SELECT id, source, target, status, detail, suggestion, seen_at FROM findings WHERE project_id = ? AND resolved_at IS NULL ORDER BY id DESC LIMIT 20",
                            (project_id,)).fetchall()
        review_history = db.execute("SELECT id, source, target, review_outcome, review_note, review_target, resolved_at FROM findings WHERE project_id = ? AND review_outcome IS NOT NULL ORDER BY resolved_at DESC, id DESC LIMIT 20",
                                    (project_id,)).fetchall()
    relationships = []
    for source, targets in IMPACTS.items():
        for target in targets:
            if source in kinds and target in kinds and source < target:
                confirmed = source == "firmware" and target == "schematic" and bool(rules)
                relationships.append({"from": source, "to": target,
                                      "confidence": "configured" if confirmed else "possible",
                                      "reason": "Pin mapping configured" if confirmed else "Possible design dependency"})
    return {"project": dict(project), "git_head": _head(root),
            "files": [dict(row) for row in rows], "changes": [dict(row) for row in history],
            "impacts": [dict(row) for row in recent], "checks": [dict(row) for row in check_rows],
            "review_history": [dict(row) for row in review_history],
            "pin_rules": rules, "relationships": relationships, "skipped": skipped,
            "scanned_at": _now()}


def review_finding(project_id: int, finding_id: int, outcome: str = "reviewed",
                   note: str = "", target_file: str | None = None) -> dict:
    if outcome not in {"reviewed", "not_relevant"}:
        raise ValueError("Choose reviewed or not_relevant.")
    note = note.strip()
    if len(note) > 500:
        raise ValueError("Keep the review note under 500 characters.")
    with _connect() as db:
        row = db.execute("SELECT status, target FROM findings WHERE project_id = ? AND id = ? AND resolved_at IS NULL",
                         (project_id, finding_id)).fetchone()
        if row is None:
            raise KeyError(finding_id)
        if row["status"] == "failed":
            raise ValueError("Resolve the failed check before marking this finding reviewed.")
        if target_file:
            target = db.execute("SELECT 1 FROM files WHERE project_id = ? AND path = ? AND kind = ?",
                                (project_id, target_file, row["target"])).fetchone()
            if target is None:
                raise ValueError("Choose a tracked file in the affected area.")
        changed = db.execute("UPDATE findings SET resolved_at = ?, review_outcome = ?, review_note = ?, review_target = ? WHERE project_id = ? AND id = ? AND resolved_at IS NULL",
                             (_now(), outcome, note, target_file, project_id, finding_id)).rowcount
        if not changed:
            raise KeyError(finding_id)
    return scan_project(project_id)


def project_handoff(project_id: int) -> str:
    """A portable summary for a teammate, without source contents or absolute paths."""
    data = scan_project(project_id)
    project = data["project"]
    lines = [f"# {project['name']} — Extrude handoff", "",
             f"Scanned: {data['scanned_at']}",
             f"Git commit: {data['git_head'] or 'not available'}", "",
             "## Project inventory", ""]
    kinds = sorted({file["kind"] for file in data["files"]})
    for kind in kinds:
        files = [file["path"] for file in data["files"] if file["kind"] == kind]
        lines.append(f"- {kind.title()} ({len(files)}): {', '.join(files[:12])}{'…' if len(files) > 12 else ''}")
    if not kinds:
        lines.append("- No supported project files were found.")
    lines += ["", "## Active findings", ""]
    if not data["impacts"]:
        lines.append("- Nothing is waiting for review.")
    for finding in data["impacts"]:
        lines.append(f"- **{finding['status'].upper()}** {finding['source']} → {finding['target']}: {finding['detail']}")
        lines.append(f"  Next: {finding['suggestion']}")
    lines += ["", "## Engineering checks", ""]
    if not data["checks"]:
        lines.append("- No engineering checks have run yet.")
    for check in data["checks"]:
        lines.append(f"- **{check['status'].upper()}** {check['name']} ({check['file']}): {check['detail']}")
    lines += ["", "## Recent changes", ""]
    if not data["changes"]:
        lines.append("- Baseline only; no changes captured yet.")
    for change in data["changes"][:10]:
        lines.append(f"- {change['seen_at']} · {change['action']} · {change['path']}")
    lines += ["", "## Review decisions", ""]
    if not data["review_history"]:
        lines.append("- No review decisions recorded yet.")
    for review in data["review_history"][:10]:
        target = review["review_target"] or review["target"]
        lines.append(f"- {review['resolved_at']} · {review['review_outcome']} · {review['source']} → {target}")
        if review["review_note"]:
            lines.append(f"  Note: {review['review_note'].replace(chr(10), ' ')}")
    lines += ["", "Generated from the local Extrude project map. Possible effects are review prompts, not verified failures; check statuses say which results are verified.", ""]
    return "\n".join(lines)


def preview_project_file(project_id: int, relative: str) -> dict:
    with _connect() as db:
        project = db.execute("SELECT path FROM projects WHERE id = ?", (project_id,)).fetchone()
        file = db.execute("SELECT path, kind, size, modified_ns FROM files WHERE project_id = ? AND path = ?",
                          (project_id, relative)).fetchone()
    if project is None or file is None:
        raise KeyError(relative)
    root = Path(project["path"])
    target = (root / relative).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueError("This file is no longer available inside the project.")
    result = dict(file)
    if target.suffix.lower() in {".stl", ".obj"}:
        result["type"] = "mesh"
        result["mesh"] = _mesh_preview(target)
    elif target.suffix.lower() == ".pdf":
        result["type"] = "metadata"
        result["note"] = "Preview is unavailable for this file format. Open it in its design tool."
    else:
        result["type"] = "text"
        with target.open("r", encoding="utf-8", errors="replace") as source:
            result["text"] = source.read(100_000)
        result["truncated"] = target.stat().st_size > 100_000
    return result


def _mesh_preview(path: Path) -> dict:
    if path.stat().st_size > 25_000_000:
        raise ValueError("This mesh is too large for the embedded viewer (25 MB limit).")
    if path.suffix.lower() == ".obj":
        vertices: list[tuple[float, float, float]] = []
        faces: list[tuple[int, int, int]] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0] == "v":
                try:
                    vertices.append(tuple(float(n) for n in parts[1:4]))
                except ValueError:
                    continue
            elif len(parts) >= 4 and parts[0] == "f":
                try:
                    indices = []
                    for part in parts[1:]:
                        index = int(part.split("/")[0])
                        indices.append(index - 1 if index > 0 else len(vertices) + index)
                    faces.extend((indices[0], indices[i], indices[i + 1]) for i in range(1, len(indices) - 1))
                except ValueError:
                    continue
        triangles = [[*vertices[a], *vertices[b], *vertices[c]] for a, b, c in faces[::max(1, len(faces) // 2000)]
                     if min(a, b, c) >= 0 and max(a, b, c) < len(vertices)][:2000]
        points = vertices
        count = len(faces)
    else:
        data = path.read_bytes()
        binary = len(data) >= 84 and 84 + struct.unpack_from("<I", data, 80)[0] * 50 == len(data)
        triangles = []
        points = []
        if binary:
            count = struct.unpack_from("<I", data, 80)[0]
            stride = max(1, count // 2000)
            low = [float("inf")] * 3
            high = [float("-inf")] * 3
            for index in range(count):
                triangle = struct.unpack_from("<9f", data, 84 + index * 50 + 12)
                for axis in range(3):
                    values = triangle[axis::3]
                    low[axis] = min(low[axis], *values)
                    high[axis] = max(high[axis], *values)
                if index % stride == 0 and len(triangles) < 2000:
                    triangles.append(list(triangle))
            points = [tuple(low), tuple(high)] if count else []
        else:
            vertices = []
            pattern = re.compile(r"^\s*vertex\s+([-+\deE.]+)\s+([-+\deE.]+)\s+([-+\deE.]+)", re.I)
            for line in data.decode("utf-8", errors="replace").splitlines():
                match = pattern.match(line)
                if match:
                    try:
                        vertices.append(tuple(float(value) for value in match.groups()))
                    except ValueError:
                        continue
            count = len(vertices) // 3
            stride = max(1, count // 2000)
            triangles = [[*vertices[index * 3], *vertices[index * 3 + 1], *vertices[index * 3 + 2]]
                         for index in range(0, count, stride)][:2000]
            points = vertices
    if not points:
        raise ValueError("No triangles were found in this 3D file.")
    bounds = [[min(point[axis] for point in points), max(point[axis] for point in points)] for axis in range(3)]
    return {"triangles": triangles, "total_triangles": count, "bounds": bounds,
            "dimensions": [round(high - low, 3) for low, high in bounds],
            "unit": "file units"}


def create_demo_project() -> dict:
    if not DEMO_SOURCE.is_dir():
        raise ValueError("The demo project is unavailable.")
    destination = data_dir() / "demo-robot"
    if not destination.exists():
        shutil.copytree(DEMO_SOURCE, destination)
    result = create_project("Demo · Robotic gripper", str(destination))
    with _connect() as db:
        db.execute("UPDATE projects SET demo = 1 WHERE id = ?", (result["project"]["id"],))
        existing = db.execute("SELECT 1 FROM pin_rules WHERE project_id = ? LIMIT 1", (result["project"]["id"],)).fetchone()
    if not existing:
        return add_pin_rule(result["project"]["id"], {
            "firmware_file": "firmware/gripper.ino", "firmware_symbol": "MOTOR_PIN",
            "netlist_file": "electronics/gripper.net", "schematic_net": "MOTOR",
            "mcu_ref": "U1",
        })
    return scan_project(result["project"]["id"])


def advance_demo_project(project_id: int) -> dict:
    with _connect() as db:
        project = db.execute("SELECT path, demo FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None or not project["demo"] or Path(project["path"]).resolve() != data_dir() / "demo-robot":
        raise ValueError("Demo changes are available only in the bundled demo project.")
    source = Path(project["path"]) / "firmware" / "gripper.ino"
    text = source.read_text(encoding="utf-8")
    updated = text.replace("MOTOR_PIN = 12", "MOTOR_PIN = 13") if "MOTOR_PIN = 12" in text else text.replace("MOTOR_PIN = 13", "MOTOR_PIN = 12")
    if updated == text:
        raise ValueError("The demo firmware is no longer in a recognized state.")
    source.write_text(updated, encoding="utf-8")
    return scan_project(project_id)
