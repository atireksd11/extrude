"""Product paths must not import the legacy string harness scorer for lift."""

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_FORBIDDEN_IMPORTS = {
    ("eval.arm_benchmark.score", "harness_prompt"),
    ("eval.legacy.string_harness", "harness_prompt"),
}


def _imports_in(path: Path) -> set[tuple[str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                found.add((node.module, alias.name))
    return found


def test_copilot_and_harness_do_not_import_legacy_harness_prompt():
    targets = [
        _ROOT / "extrude" / "copilot" / "api.py",
        _ROOT / "extrude" / "harness" / "loop.py",
        _ROOT / "extrude" / "harness" / "prompt.py",
    ]
    for path in targets:
        imports = _imports_in(path)
        assert ("eval.arm_benchmark.score", "harness_prompt") not in imports
        assert ("eval.legacy.string_harness", "harness_prompt") not in imports


def test_score_arm_has_no_harness_prompt_export():
    score_path = _ROOT / "eval" / "arm_benchmark" / "score.py"
    tree = ast.parse(score_path.read_text(encoding="utf-8"))
    names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    assert "harness_prompt" not in names
