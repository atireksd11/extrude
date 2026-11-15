"""Compare saved KiCad board versions with explicit input coverage."""

from pathlib import PurePosixPath

from extrude import github_history as history
from extrude.parse.kicad_pcb import MAX_BOARD_BYTES, Board, BoardParseError, compare_boards, parse_board


def _snapshot(repo_id: str, sha: str | None, path: str) -> tuple[Board | None, dict]:
    evidence = {"sha": sha, "path": path}
    if sha is None:
        return None, {**evidence, "status": "absent"}
    try:
        data = history.regular_blob(repo_id, sha, path, max_bytes=MAX_BOARD_BYTES)
        if data is None:
            return None, {**evidence, "status": "absent"}
        board = parse_board(data)
    except (BoardParseError, history.BlobUnavailable) as exc:
        return None, {**evidence, "status": "unverified", "detail": str(exc)}
    return board, {**evidence, "status": "read", "version": board.version,
                   "footprints": len(board.footprints)}


def review(repo_id: str, revision: str, path: str, base: str | None = None,
           previous_path: str | None = None, offset: int = 0, limit: int = 100) -> dict:
    previous_path = previous_path or path
    if any(PurePosixPath(value).suffix.lower() != ".kicad_pcb" for value in (path, previous_path)):
        raise ValueError("Choose a .kicad_pcb file.")
    sha, parent = history.comparison_revisions(repo_id, revision, base)
    before, before_info = _snapshot(repo_id, parent, previous_path)
    after, after_info = _snapshot(repo_id, sha, path)
    statuses = {before_info["status"], after_info["status"]}
    if statuses == {"absent"}:
        raise KeyError(path)
    readable = "unverified" not in statuses
    rows = compare_boards(before, after) if readable else []
    return {"status": "compared" if readable else "unverified",
            "before": before_info, "after": after_info,
            "changes": rows[offset:offset + limit], "total": len(rows),
            "next_offset": offset + limit if offset + limit < len(rows) else None}


def duplicate_added_board(repo_id: str, head: str, base: str | None, path: str):
    """Match a new board's complete supported footprint state to an existing board.

    UUIDs and file names are not hardware identity. Values outside the supported
    footprint/pad inventory (tracks, zones, stackup) are explicitly not compared.
    Bound inventory and parse work; uncertainty leaves the normal diff intact.
    """
    if base is None or history.file_exists(repo_id, base, path):
        return None
    board, _ = _snapshot(repo_id, head, path)
    if board is None or not board.footprints:
        return None

    def signature(value):
        return sorted((f.reference or "", f.library, f.position, f.rotation,
                       f.layer, tuple(sorted(f.pads.items())), f.properties)
                      for f in value.footprints)

    wanted = signature(board)
    inventory = history.inventory(repo_id, base, limit=10000)
    if inventory["next_offset"] is not None:
        return None
    candidates = sorted(r["path"] for r in inventory["files"]
                        if r["type"] == "blob" and r["path"].endswith(".kicad_pcb"))
    if len(candidates) > 12:
        return None
    for candidate in candidates:
        for revision in dict.fromkeys((head, base)):
            original, _ = _snapshot(repo_id, revision, candidate)
            if original is not None and signature(original) == wanted:
                return {"path": candidate, "sha": revision, "count": len(board.footprints)}
    return None
