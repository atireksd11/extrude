"""Build revision-pinned Atlas views from the existing Git object store."""

from pathlib import PurePosixPath

from extrude import github_history as git


def domain(path: str, kind: str) -> str:
    file = PurePosixPath(path.lower())
    if file.suffix in {".csv", ".tsv", ".xlsx"} and (
        "bom" in file.stem.replace("_", "-").split("-") or "bom" in file.parts[:-1]
    ):
        return "bom"
    if file.suffix in {".kicad_pro", ".kicad_dru", ".kicad_mod"}:
        return "pcb"
    if file.suffix == ".kicad_sym":
        return "schematic"
    if any(part in {"firmware", "embedded"} for part in file.parts[:-1]) or file.suffix == ".ino":
        if kind in {"firmware", "other"}:
            return "firmware"
    if kind == "firmware" or file.suffix in {".json", ".toml", ".yaml", ".yml", ".sh", ".go", ".java"}:
        return "code"
    return kind


def view(repo_id: str, revision: str, base: str | None, file_offset: int, change_offset: int, limit: int) -> dict:
    changes = git.changes(repo_id, revision, base, change_offset, limit)
    revision, base = changes["revision"], changes["base"]
    inventory = git.inventory(repo_id, revision, file_offset, limit)
    for page in (inventory, changes):
        for row in page["files"]:
            row["domain"] = domain(row["path"], row["kind"])
    return {"repo_id": repo_id, "head_sha": revision, "base_sha": base,
            "inventory": inventory, "changes": changes}
