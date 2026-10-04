"""Phase 0 behavior tests. Entries must refuse, and nothing may claim a pass."""

import ast
from pathlib import Path

import pytest

from extrude.coverage import cover
from extrude.intake.models import FrozenSpec
from extrude.ir import load, save
from extrude.ir.models import CircuitIR
from extrude.learn import propose_offline
ROOT = Path(__file__).resolve().parents[2]
BAD_STRINGS = {"PASS", "passed", "design is good"}


def test_every_entry_says_not_built():
    spec = FrozenSpec(
        task_class="buck",
        values_si={},
        origins={},
        defaults_version="phase0",
        spec_hash="phase0",
    )
    design = CircuitIR()
    calls = [
        (cover, (spec,)),
        (save, (design, Path("design.json"))),
        (load, (Path("design.json"),)),
        (propose_offline, ()),
    ]
    for func, args in calls:
        with pytest.raises(NotImplementedError, match="not built"):
            func(*args)


def test_no_hard_coded_pass_in_the_package():
    problems: list[str] = []
    for path in (ROOT / "extrude").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if _claims_pass(node):
                problems.append(str(path.relative_to(ROOT)))
                break
    assert problems == []


def _claims_pass(node: ast.AST) -> bool:
    if isinstance(node, ast.Assign):
        names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        return _bad_assigned_value(names, node.value)
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return _bad_assigned_value([node.target.id], node.value)
    if isinstance(node, ast.Call):
        return any(
            keyword.arg == "passed" and _is_true(keyword.value) for keyword in node.keywords
        )
    return False


def _bad_assigned_value(names: list[str], value: ast.AST | None) -> bool:
    if value is None:
        return False
    if "passed" in names and _is_true(value):
        return True
    return isinstance(value, ast.Constant) and value.value in BAD_STRINGS


def _is_true(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is True
