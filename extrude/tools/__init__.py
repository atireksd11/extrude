"""Tool manifest. A missing binary is tooling, not a design miss."""

import json
import os
import shutil
from pathlib import Path

_MANIFEST = Path(__file__).resolve().parent / "manifest.json"


def load_manifest() -> dict:
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))


def tool_path(name: str) -> str | None:
    entry = load_manifest()["tools"].get(name)
    if not entry:
        return None
    env = os.environ.get(entry["env"], "").strip()
    if env:
        return env
    return shutil.which(entry["fallback"])


def tool_available(name: str) -> bool:
    return tool_path(name) is not None


def required_for_domain(domain: str) -> list[str]:
    manifest = load_manifest()
    names = []
    for name, entry in manifest["tools"].items():
        if domain in entry.get("domains", []) and entry.get("required_for_generate"):
            names.append(name)
    return names


def missing_required(domain: str) -> list[str]:
    return [name for name in required_for_domain(domain) if not tool_available(name)]
