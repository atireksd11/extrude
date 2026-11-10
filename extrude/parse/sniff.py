"""Guess what kind of text was pasted. No network."""

from pathlib import Path


def sniff(*, filename: str | None, content: str) -> str:
    suffix = Path((filename or "").lower()).suffix
    body = content.lstrip()
    if suffix == ".scad":
        return "openscad"
    if suffix == ".fs":
        return "featurescript"
    if suffix == ".net":
        return "netlist"
    if body.startswith("(export"):
        return "netlist"
    if "FeatureScript" in content or "skCircle(" in content or "opExtrude(" in content:
        return "featurescript"
    if "difference()" in content or "cylinder(" in content:
        return "openscad"
    if "onshape.com" in content:
        return "onshape"
    if content.strip():
        return "circuit"
    return "empty"


def validate_paste_filename(value: str | None) -> str | None:
    """Pasted source is data; never accept an executable or filesystem path."""
    if value is not None and (not value or "/" in value or "\\" in value or "\0" in value
                              or Path(value).suffix.lower() not in {".scad", ".net", ".fs"}):
        raise ValueError("Choose a .scad, .net or .fs source filename.")
    return value
