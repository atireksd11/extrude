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
