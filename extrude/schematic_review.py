"""Revision-pinned placed-symbol comparisons for individual native sheets."""

from pathlib import PurePosixPath

from extrude import github_history as git
from extrude.parse.kicad_schematic import MAX_SCHEMATIC_BYTES, compare_schematics, parse_schematic


def _snapshot(repo_id: str, sha: str | None, path: str):
    info = {"sha": sha, "path": path}
    if sha is None:
        return None, {**info, "status": "absent"}
    try:
        blob = git.regular_blob(repo_id, sha, path, max_bytes=MAX_SCHEMATIC_BYTES)
        if blob is None:
            return None, {**info, "status": "absent"}
        sheet = parse_schematic(blob)
        return sheet, {**info, "status": "read", "version": sheet.version,
                       "symbols": len(sheet.symbols), "child_sheets": len(sheet.sheets)}
    except (ValueError, git.BlobUnavailable) as exc:
        return None, {**info, "status": "unverified", "detail": str(exc)}


def review(repo_id: str, revision: str, path: str, base: str | None = None,
           previous_path: str | None = None, offset=0, limit=100):
    previous_path = previous_path or path
    if any(PurePosixPath(p).suffix.lower() != ".kicad_sch" for p in (path, previous_path)):
        raise ValueError("Choose a .kicad_sch file.")
    sha, parent = git.comparison_revisions(repo_id, revision, base)
    before, a = _snapshot(repo_id, parent, previous_path)
    after, b = _snapshot(repo_id, sha, path)
    if a["status"] == b["status"] == "absent":
        raise KeyError(path)
    readable = "unverified" not in {a["status"], b["status"]}
    changes = compare_schematics(before, after) if readable else []
    return dict(status="compared" if readable else "unverified", before=a, after=b,
                changes=changes[offset:offset + limit], total=len(changes),
                next_offset=offset + limit if offset + limit < len(changes) else None)
