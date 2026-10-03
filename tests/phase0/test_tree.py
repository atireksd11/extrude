"""Phase 0 structure tests. Imports are read from the syntax tree, not from text search."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "extrude"

REQUIRED_DOCS = [
    "README.md",
    "docs/GROUND-RULES.md",
    "docs/MAP.md",
    "docs/LEARNINGS.md",
    "docs/architecture/hardware-ai-master-blueprint.md",
    "docs/phases/PHASE-0.md",
    "docs/phases/PHASE-1.md",
    "docs/phases/PHASE-2.md",
    "docs/phases/PHASE-3.md",
    "docs/phases/PHASE-4.md",
    "docs/phases/PHASE-5.md",
    "docs/phases/PHASE-6.md",
    "docs/phases/PHASE-7.md",
]

DRAWERS = [
    "intake",
    "coverage",
    "ir",
    "checks",
    "physics",
    "sim",
    "emit",
    "memory",
    "harness",
    "eval",
    "learn",
    "mcp",
]

USER_PATH = [
    "intake",
    "coverage",
    "ir",
    "checks",
    "physics",
    "sim",
    "emit",
    "memory",
    "harness",
    "eval",
]

TASK_SLOTS = ["holdup", "buck", "ldo"]

ALWAYS_FORBIDDEN = (
    "extrude.learn",
    "extrude.mcp",
    "learn",
    "mcp",
    "openai",
    "anthropic",
    "litellm",
    "google.generativeai",
    "ngspice",
    "PySpice",
    "pyspice",
)

EXTRA_FORBIDDEN = {
    "intake": ("extrude.sim", "extrude.physics", "sim", "physics"),
    "sim": ("extrude.harness", "extrude.intake", "harness", "intake"),
}


def test_required_docs_and_drawers_exist():
    missing = [rel for rel in REQUIRED_DOCS if not (ROOT / rel).is_file()]
    assert missing == []
    for drawer in DRAWERS:
        folder = PACKAGE / drawer
        assert folder.is_dir(), drawer
        assert (folder / "CONTRACT.md").is_file(), drawer
        assert (folder / "__init__.py").is_file(), drawer
    for slot in TASK_SLOTS:
        assert (ROOT / "eval" / "proxy_tasks" / slot).is_dir(), slot


def test_job_cards_name_both_sides_of_the_door():
    for drawer in DRAWERS:
        text = (PACKAGE / drawer / "CONTRACT.md").read_text(encoding="utf-8")
        assert "May talk to:" in text, drawer
        assert "Must not talk to:" in text, drawer


def test_job_card_signatures_match_the_functions():
    for drawer in DRAWERS:
        text = (PACKAGE / drawer / "CONTRACT.md").read_text(encoding="utf-8")
        expected = [
            line.split("SIGNATURE:", 1)[1].strip()
            for line in text.splitlines()
            if line.startswith("SIGNATURE:")
        ]
        api = PACKAGE / drawer / "api.py"
        if not expected:
            assert drawer == "mcp"
            assert not api.exists()
            continue
        tree = ast.parse(api.read_text(encoding="utf-8"))
        found = {
            node.name: _signature(node)
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }
        for line in expected:
            name = line.split("(", 1)[0]
            assert found.get(name) == line, (drawer, found.get(name), line)


def test_user_path_imports_stay_inside_the_rules():
    problems: list[str] = []
    for drawer in USER_PATH:
        for path in (PACKAGE / drawer).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            forbidden = ALWAYS_FORBIDDEN + EXTRA_FORBIDDEN.get(drawer, ())
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    for name in _imported_modules(path, node):
                        if _is_forbidden(name, forbidden):
                            problems.append(f"{path.relative_to(ROOT)} imports {name}")
                if _calls_hidden_import(node):
                    problems.append(f"{path.relative_to(ROOT)} hides an import")
    assert problems == []


def _signature(node: ast.FunctionDef) -> str:
    args = ast.unparse(node.args)
    returns = ast.unparse(node.returns) if node.returns is not None else "None"
    return f"{node.name}({args}) -> {returns}"


def _imported_modules(path: Path, node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if not isinstance(node, ast.ImportFrom):
        return []
    base = _relative_base(path, node.level)
    names = []
    if node.module and base:
        names.append(f"{base}.{node.module}")
    elif node.module:
        names.append(node.module)
    elif base:
        names.append(base)
    if node.module in {None, "extrude"} or (base == "extrude" and node.module is None):
        names.extend(alias.name for alias in node.names)
    if base == "extrude" and node.module:
        names.extend(f"extrude.{alias.name}" for alias in node.names if node.module == "")
    return names


def _relative_base(path: Path, level: int) -> str:
    if level <= 0:
        return ""
    parts = list(path.relative_to(PACKAGE).parts[:-1])
    keep = len(parts) - (level - 1)
    if keep < 0:
        return ""
    return ".".join(["extrude", *parts[:keep]]).rstrip(".")


def _is_forbidden(name: str, forbidden: tuple[str, ...]) -> bool:
    return any(name == item or name.startswith(item + ".") for item in forbidden)


def _calls_hidden_import(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id == "__import__":
        return True
    return isinstance(func, ast.Attribute) and func.attr == "import_module"
