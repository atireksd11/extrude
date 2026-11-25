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
    return _C_TOKEN.sub(_blank_token, text)


def _blank_token(match):
    return "".join("\n" if c == "\n" else " " for c in match[0])


def read_constants(data: bytes, path: str) -> dict[str, dict]:
    if len(data) > MAX_SOURCE_BYTES:
        raise ValueError("Source exceeds the 512 KiB analysis limit.")
    text = data.decode("utf-8-sig", errors="replace")
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


_PIN_BINDING = re.compile(r"\s*#define\s+(\w+?_(RESET|NET|WS|COMM)_PIN)\s+PIO_(P[A-Z]\d+)\b")
_C_TOKEN = re.compile(r"""/\*.*?\*/|//[^\n]*|"(?:(?:\\.)|[^"\\])*"|'(?:(?:\\.)|[^'\\])*'""", re.S)


def _source_tokens(data):
    text = data.decode("utf-8-sig", errors="replace")
    comments = []

    def mask(token):
        if token[0].startswith(("/*", "//")):
            comments.append(token)
        return _blank_token(token)

    return _C_TOKEN.sub(mask, text), comments


def read_pin_bindings(data, path, *, issues=None, define_names=None):
    """Read literal port bindings and optionally report rejected or comment-only roles."""
    code, comments = _source_tokens(data)
    blocks = iter(comment for comment in comments if comment[0].startswith("/*"))
    upcoming = next(blocks, None)
    current = None
    associated = set()
    bindings = []
    offset = 0
    for line, source in enumerate(code.splitlines(keepends=True), 1):
        match = _PIN_BINDING.match(source)
        while upcoming is not None and upcoming.end() <= offset:
            current = upcoming
            upcoming = next(blocks, None)
        offset += len(source)
        if not match:
            continue
        name, role, sam_pin = match.groups()
        comment = current[0] if current else ""
        if current:
            associated.add((current.start(), role))
        declared = re.search(r"\bSAM4S:\s*(P[A-Z]\d+)\b", comment)
        if declared and declared[1] != sam_pin:
            if issues is not None:
                issues.append(f"{path}:{line}: {name} disagrees with comment pin {declared[1]}")
            continue
        gpios = set(re.findall(r"\bGPIO(\d+)\b", comment))
        gpio = int(gpios.pop()) if len(gpios) == 1 else None
        if role in {"NET", "WS"} and gpio is None:
            if issues is not None:
                issues.append(f"{path}:{line}: {name} lacks a unique comment GPIO")
            continue
        bindings.append(dict(role=role, sam_pin=sam_pin, gpio=gpio, line=line,
                             path=path, comment_gpio=gpio))
        if define_names is not None:
            define_names[path, line] = name
    if issues is not None:
        for comment in comments:
            role = re.match(r"/\*+\s*(?:\*\s*)?ESP32\s+(?:EN\s*/\s*)?(RESET|NET|WS|COMM)\b", comment[0])
            if role and (comment.start(), role[1]) not in associated:
                issues.append(f"{path}: {role[1]} comment has no pin define")
    return bindings


def read_uart_gates(data, path):
    """Return explicitly configured ESP32 USARTs with code-level setup calls."""
    if b"ESP32" not in data or b"usart_" not in data:
        return []
    code, comments = _source_tokens(data)
    if not (re.search(r"\busart_init_rs232\s*\(", code)
            or all(re.search(rf"\busart_enable_{end}\s*\(", code) for end in ("tx", "rx"))):
        return []

    def gates(pattern, candidates):
        return [(match[1], path, " ".join(comment[0].strip("/* \n").split()))
                for comment in candidates for match in re.finditer(pattern, comment[0])]

    return (gates(r"\bConfigures?\s+(USART\d+)\b", comments)
            or gates(r"\b(USART\d+)\b", (c for c in comments if "ESP32" in c[0])))
