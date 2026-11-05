"""Conservative literal extraction. Never import, compile, or execute source."""

import ast
import re
from pathlib import PurePosixPath

MAX_SOURCE_BYTES = 512 * 1024
MAX_CONSTANTS = 256
READER_VERSION = 2
_NAME = r"[A-Za-z_]\w*"
_LITERAL = re.compile(r"\(?\s*(0[xX][0-9A-Fa-f]+|\d+)\s*(?:[uU](?:[lL]{1,2})?|[lL]{1,2}[uU]?)?\s*\)?")


def _mask(text: str) -> str:
    # Keep newlines and offsets for evidence; quoted strings are not code.
    pattern = r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    return re.sub(pattern, lambda m: "".join("\n" if c == "\n" else " " for c in m.group()), text, flags=re.S)


def read_constants(data: bytes, path: str) -> dict[str, dict]:
    if len(data) > MAX_SOURCE_BYTES:
        raise ValueError("Source exceeds the 512 KiB analysis limit.")
    text = data.decode("utf-8-sig")
    rows: dict[str, list[dict]] = {}
    namespaces = []
    def add(name, value, line, detail=None):
        prefix = "::".join(scope for scope in namespaces if scope)
        entry = dict(value=value, line=line, detail=detail)
        if prefix:
            qualified = prefix + "::" + name
            rows.setdefault(qualified, []).append(entry)
            entry = {**entry, "alias_of": qualified}
        rows.setdefault(name, []).append(entry)
        if len(rows) > MAX_CONSTANTS:
            raise ValueError("Too many constants for a bounded source review.")
    if PurePosixPath(path).suffix.lower() == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            raise ValueError("Python syntax could not be read; source was not executed.") from exc
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if not isinstance(target, ast.Name):
                        continue
                    value = node.value
                    literal = type(value.value) is int if isinstance(value, ast.Constant) else False
                    is_top = node in tree.body and not isinstance(node, ast.AugAssign)
                    number = value.value if literal and is_top else None
                    add(target.id, number, node.lineno, None if number is not None else "Only unconditional module-level integer literals are supported.")
    elif PurePosixPath(path).suffix.lower() in {".c", ".cpp", ".h", ".hpp", ".ino", ".cc", ".cxx"}:
        branches = []
        masked = _mask(text)
        shadowed = set(re.findall(r"^\s*#\s*(?:define|undef)\s+(GPIO_NUM_\d+)\b", masked, re.M))
        for lineno, line in enumerate(masked.splitlines(), 1):
            namespace = re.fullmatch(rf"\s*(?:inline\s+)?namespace(?:\s+({_NAME}(?:::{_NAME})*))?\s*\{{\s*", line)
            if namespace:
                namespaces.append(namespace[1] or "")
                continue
            if re.match(r"\s*#\s*(?:if|ifdef|ifndef)\b", line):
                # A simple header guard is harmless; arbitrary compile-time
                # branches need a real build configuration and remain unverified.
                guard = re.fullmatch(r"\s*#\s*ifndef\s+\w+_(?:H|HPP)_?\s*", line)
                branches.append(not bool(guard))
            if re.match(r"\s*#\s*endif\b", line):
                if branches:
                    branches.pop()
            if re.match(r"\s*#\s*(?:else|elif)\b", line) and branches:
                branches[-1] = True
            define = re.match(rf"\s*#\s*define\s+({_NAME})\s+(.+?)\s*$", line)
            assignment = re.match(rf"\s*(?:(?:static|constexpr|const|volatile|unsigned|signed)\s+)*\w+(?:::\w+)*\s+({_NAME})\s*=\s*([^;]+);\s*$", line)
            match = define or assignment
            if not match:
                uncertain = re.match(rf"\s*(?:#\s*undef\s+({_NAME})\b|({_NAME})\s*(?:[+*/-]?=|\+\+|--))", line)
                if uncertain:
                    add(uncertain[1] or uncertain[2], None, lineno, "Undefinition or runtime reassignment needs build context.")
                for brace in re.findall(r"[{}]", line):
                    if brace == "{":
                        namespaces.append(None)
                    elif namespaces:
                        namespaces.pop()
                continue
            name, expression = match.groups()
            expression = expression.strip()
            if expression.startswith("(") and expression.endswith(")"):
                expression = expression[1:-1].strip()
            literal = _LITERAL.fullmatch(expression) if not any(c in expression for c in "()") else None
            token = literal[1] if literal else ""
            base = 16 if token.lower().startswith("0x") else 8 if len(token) > 1 and token.startswith("0") else 10
            allowed_scope = all(scope is not None for scope in namespaces)
            gpio = re.fullmatch(r"GPIO_NUM_(\d{1,2})", expression)
            gpio_allowed = (gpio and int(gpio[1]) <= 54 and expression not in shadowed
                            and assignment and re.search(r"\bgpio_num_t\b", line))
            try:
                value = (int(token, base) if literal else int(gpio[1]) if gpio_allowed else None) if not any(branches) and allowed_scope else None
            except ValueError:
                value = None
            detail = "ESP32 GPIO enum; logical GPIO number, not a package pad." if gpio_allowed and value is not None else None
            add(name, value, lineno, detail if value is not None else "Expression or conditional assignment needs build context.")
    else:
        raise ValueError("Literal pin reading supports C/C++/Arduino and Python source.")
    return {name: entries[0] if len(entries) == 1 else dict(value=None, line=entries[0]["line"], detail="Multiple assignments are ambiguous.")
            for name, entries in rows.items()}
