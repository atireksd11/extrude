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
