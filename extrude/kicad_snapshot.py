"""Materialize bounded KiCad inputs from Git; never checkout or execute repo code."""

import contextlib
import json
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from extrude import github_history as git
from extrude.parse.kicad_schematic import parse_schematic, SchematicParseError
from extrude.runtime import data_dir

MAX_FILES = 256
MAX_BYTES = 64 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TREE = 10000
EXTENSIONS = {".kicad_pcb", ".kicad_sch", ".kicad_pro", ".kicad_dru", ".kicad_sym", ".kicad_mod", ".lib", ".dcm", ".sch"}
TABLES = {"fp-lib-table", "sym-lib-table"}


class SnapshotError(ValueError):
    pass


def temporary_directory(prefix: str):
    # Keep scratch data in the application's writable area. Windows packaged
    # process temp directories can be inaccessible to a child process.
    scratch = data_dir() / "kicad-tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix=prefix, dir=scratch)


def safe_path(root: Path, value: str) -> Path:
    """Also reject Windows ADS, devices, UNC, and case-colliding Git names."""
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or "\\" in value or ":" in value or "\x00" in value
            or any(part in {"", ".", ".."} for part in value.split("/"))
            or any(part.endswith((" ", ".")) or re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part)
                   for part in path.parts)):
        raise SnapshotError("Unsafe repository path was excluded.")
    target = root.joinpath(*path.parts).resolve()
    if not target.is_relative_to(root.resolve()):
        raise SnapshotError("Repository path escapes the snapshot.")
    return target


def relative_dependency(owner: str, value: str) -> str:
    if not value or "\\" in value or ":" in value or "$" in value or PurePosixPath(value).is_absolute():
        raise SnapshotError("External or variable-based sheet dependency is unsupported.")
    parts = list(PurePosixPath(owner).parent.parts)
    for part in value.split("/"):
        if part == "..":
            if not parts:
                raise SnapshotError("Dependency escapes the repository.")
            parts.pop()
        elif part not in {"", "."}:
            parts.append(part)
    result = "/".join(parts)
    safe_path(Path.cwd(), result)
    return result


@dataclass
class Snapshot:
    root: Path
    files: set[str] = field(default_factory=set)
    issues: list[tuple[str, str]] = field(default_factory=list)

    warnings: list[tuple[str, str]] = field(default_factory=list)

    def sheets(self, root_path: str) -> dict[str, str]:
        """Map hierarchical sheet UUID paths to source files; fail closed."""
        result = {}

        def visit(path: str, instance: str, stack: tuple[str, ...]):
            if path in stack or len(stack) >= 32:
                raise SnapshotError("Cyclic or excessively deep schematic hierarchy.")
            if path not in self.files:
                raise SnapshotError(f"Missing schematic dependency: {path}")
            result[instance] = path
            try:
                data = parse_schematic(safe_path(self.root, path).read_bytes())
            except SchematicParseError as exc:
                raise SnapshotError(f"Unreadable schematic: {path}") from exc
            for uid, name in data.sheets:
                visit(relative_dependency(path, name), instance.rstrip("/") + "/" + uid, (*stack, path))

        visit(root_path, "/", ())
        return result


def _safe_table(data: bytes, path: str, files: set[str]) -> None:
    # Library URIs can point outside the checkout or to network plugins. Only
    # built-in KiCad readers and local, fully materialized libraries are accepted.
    from kicad_tools.sexp import parse_string, ParseError
    from extrude.parse.kicad_pcb import _PARSE_LOCK, _string_field, _rows
    try:
        with _PARSE_LOCK:
            table = parse_string(data.decode("utf-8-sig"))
        for lib in _rows(table, "lib"):
            if _string_field(lib, "type") not in {"KiCad", "Legacy"}:
                raise SnapshotError("External library plugin is unsupported.")
            uri = _string_field(lib, "uri") or ""
            uri = uri.replace("${KIPRJMOD}/", "")
            dep = relative_dependency(path, uri)
            if dep not in files and not any(p.startswith(dep.rstrip("/") + "/") for p in files):
                raise SnapshotError(f"Library dependency not available in snapshot: {dep}")
    except (ParseError, ValueError, TypeError, IndexError, RecursionError) as exc:
        raise SnapshotError("Unsafe, missing, or unreadable local library dependency.") from exc


@contextlib.contextmanager
def materialize(repo_id: str, sha: str):
    """Reports and tool configuration belong outside this immutable input tree."""
    with temporary_directory("snapshot-") as folder:
        snapshot = Snapshot(Path(folder) / "inputs")
        snapshot.root.mkdir()
        tree = git.inventory(repo_id, sha, limit=MAX_TREE)
        if tree["next_offset"] is not None:
            raise SnapshotError("Repository tree exceeds the 10,000-file snapshot limit.")
        candidates = [item for item in tree["files"]
                      if not any(part in {".git", ".metadata", ".config", ".codex", ".agents"}
                                 for part in PurePosixPath(item["path"]).parts[:-1])
                      and (PurePosixPath(item["path"]).suffix.lower() in EXTENSIONS
                           or PurePosixPath(item["path"]).name in TABLES)]
        if len(candidates) > MAX_FILES:
            raise SnapshotError("KiCad snapshot exceeds the 256-file limit.")
        seen, total = set(), 0
        pending = {}
        for item in candidates:
            path = item["path"]
            try:
                target = safe_path(snapshot.root, path)
                if path.casefold() in seen:
                    if __import__("os").name == "nt":
                        if target.suffix.lower() == ".dcm":
                            snapshot.warnings.append((path, "case_collision: duplicate documentation skipped; native design inputs still attempted."))
                            continue
                        raise SnapshotError("case_collision: design input cannot be safely preserved on this filesystem.")
                    snapshot.warnings.append((path, "case_collision: both case-distinct paths preserved; native checks still attempted."))
                seen.add(path.casefold())
                data = git.regular_blob(repo_id, sha, path, max_bytes=MAX_FILE_BYTES)
                if data is None:
                    raise SnapshotError("Snapshot input disappeared.")
                total += len(data)
                if total > MAX_BYTES:
                    raise SnapshotError("KiCad snapshot exceeds the 64 MiB limit.")
                pending[path] = (target, data)
            except (git.BlobUnavailable, SnapshotError) as exc:
                snapshot.issues.append((path, str(exc)))
        files = set(pending)
        for path, (target, data) in pending.items():
            try:
                if PurePosixPath(path).name in TABLES:
                    _safe_table(data, path, files)
                if path.endswith(".kicad_pro"):
                    json.loads(data.decode("utf-8-sig"))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                snapshot.files.add(path)
            except (ValueError, RecursionError) as exc:
                snapshot.issues.append((path, str(exc) if isinstance(exc, SnapshotError)
                                        else "Unreadable project settings were excluded."))
        yield snapshot
