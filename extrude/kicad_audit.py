"""Bounded native KiCad checks of saved revisions, with conservative lifecycles.

Local pilot only: process environment isolation is not an OS security sandbox.
Never run repository scripts, plugin commands, or arbitrary command arguments.
"""

import functools
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from extrude.kicad_snapshot import Snapshot, SnapshotError, materialize, safe_path, relative_dependency, temporary_directory
from extrude.parse.kicad_schematic import parse_schematic, SchematicParseError
from extrude import github_history as git

TIMEOUT = 40
MAX_REPORT_BYTES = 8 * 1024 * 1024
MAX_FINDINGS = 500
MAX_PROJECTS = 12
AUDIT_SECONDS = 180


def executable() -> str | None:
    configured = os.environ.get("KICAD_CLI_PATH", "").strip()
    if configured:
        return str(Path(configured).resolve()) if Path(configured).is_file() else None
    found = shutil.which("kicad-cli")
    if found:
        return found
    if os.name == "nt":
        root = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "KiCad"
        candidates = sorted(root.glob("*/bin/kicad-cli.exe"), reverse=True)
        return str(candidates[0]) if candidates else None
    mac = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
    return str(mac) if mac.is_file() else None


def _environment(binary: str, folder: Path) -> dict[str, str]:
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC") if key in os.environ}
    config = folder / "config"
    config.mkdir(exist_ok=True)
    env.update({"PATH": str(Path(binary).parent) + os.pathsep + os.defpath,
                "KICAD_CONFIG_HOME": str(config), "XDG_CONFIG_HOME": str(config),
                "XDG_CACHE_HOME": str(folder / "cache"), "XDG_DATA_HOME": str(folder / "share"),
                "HOME": str(folder), "USERPROFILE": str(folder), "APPDATA": str(config),
                "LOCALAPPDATA": str(config), "TMP": str(folder), "TEMP": str(folder),
                "LANG": "en_US.UTF-8", "LC_ALL": "C.UTF-8"})
    # Use only the trusted installation's stock libraries, never parent-process
    # credentials, library search paths, user config, or user plugins.
    share = Path(binary).resolve().parent.parent / "share" / "kicad"
    if share.is_dir():
        for major in (9, 10):
            env[f"KICAD{major}_SYMBOL_DIR"] = str(share / "symbols")
            env[f"KICAD{major}_FOOTPRINT_DIR"] = str(share / "footprints")
        # KiCad searches the version subdirectory of KICAD_CONFIG_HOME.
        for major in ("9.0", "10.0"):
            target = config / major
            target.mkdir(exist_ok=True)
            for name in ("sym-lib-table", "fp-lib-table"):
                source = share / "template" / name
                if source.is_file():
                    shutil.copyfile(source, target / name)
    return env


@functools.lru_cache(maxsize=8)
def _probe(binary: str, stamp: int, size: int) -> str:
    del stamp, size  # Cache invalidates when the installed executable changes.
    try:
        with temporary_directory("probe-") as folder:
            completed = subprocess.run([binary, "version"], cwd=folder,
                                       env=_environment(binary, Path(folder)), timeout=10,
                                       capture_output=True, text=True, encoding="utf-8", errors="replace")
        value = completed.stdout.strip()
        if completed.returncode != 0 or not re.fullmatch(r"(?:9|10)\.\d+(?:\.\d+)?(?:[-+][\w.-]+)?", value):
            return "unsupported"
        return value
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"


def tool_version() -> str:
    binary = executable()
    if not binary:
        return "unavailable"
    try:
        info = Path(binary).stat()
        result = _probe(binary, info.st_mtime_ns, info.st_size)
        if result in {"unavailable", "unsupported"}:
            _probe.cache_clear()  # A transient launch failure must be retryable.
        return result
    except OSError:
        return "unavailable"


@dataclass
class Result:
    outcome: str
    detail: str
    rows: list[dict] = field(default_factory=list)
    ignored: tuple[str, ...] = ()
    settings: str = ""


def _violation(row: object, scope: str, path: str) -> dict:
    if not isinstance(row, dict):
        raise ValueError("Invalid violation")
    rule, description, severity, items = (row.get(key) for key in ("type", "description", "severity", "items"))
    if (not isinstance(rule, str) or not rule or not isinstance(description, str)
            or severity not in {"error", "warning", "info"} or not isinstance(items, list)):
        raise ValueError("Invalid violation fields")
    normalized = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("description"), str):
            raise ValueError("Invalid violation item")
        uid = item.get("uuid")
        if uid is not None and (not isinstance(uid, str) or not re.fullmatch(r"[0-9a-fA-F-]{36}", uid)):
            raise ValueError("Invalid object UUID")
        normalized.append({"uuid": uid, "description": item["description"], "position": item.get("pos")})
    return {"rule": rule, "summary": description, "severity": severity,
            "scope": scope, "path": path, "items": normalized}


def parse_report(data: bytes, check: str, path: str, sheets: dict[str, str], *, requested_error_warning: bool = False) -> Result:
    report = json.loads(data.decode("utf-8-sig"))
    if not isinstance(report, dict):
        raise ValueError("Expected report object")
    expected = "erc" if check == "erc" else "drc"
    if report.get("$schema") != f"https://schemas.kicad.org/{expected}.v1.json":
        raise ValueError("Unsupported KiCad JSON report schema")
    if report.get("source") != PurePosixPath(path).name:
        raise ValueError("Native report source does not match the selected file")
    severities = report.get("included_severities")
    if severities is None and requested_error_warning:
        # KiCad 9 omits this metadata. Only our explicit CLI invocation may
        # establish coverage; imported reports still fail closed.
        severities = ["error", "warning"]
    if not isinstance(severities, list) or not {"error", "warning"}.issubset(severities):
        raise ValueError("Native error/warning coverage is missing")
    rows = []
    if check == "erc":
        if not isinstance(report.get("sheets"), list) or not report["sheets"]:
            raise ValueError("Missing ERC sheet coverage")
        for sheet in report["sheets"]:
            if not isinstance(sheet, dict):
                raise ValueError("Invalid ERC sheet")
            scope = sheet.get("uuid_path")
            if not isinstance(scope, str):
                raise ValueError("Missing sheet instance path")
            # The native report prefixes the root schematic UUID; our hierarchy
            # stores paths relative to that root, preserving repeated instances.
            relative = "/" + "/".join(scope.strip("/").split("/")[1:])
            source = sheets.get(relative)
            if source is None or not isinstance(sheet.get("violations"), list):
                raise ValueError("ERC reported an unmapped sheet")
            rows.extend(_violation(row, scope, source) for row in sheet["violations"])
        if len(report["sheets"]) != len(sheets):
            raise ValueError("Incomplete ERC hierarchy coverage")
    else:
        groups = ("schematic_parity",) if check == "parity" else ("violations", "unconnected_items")
        for group in groups:
            if not isinstance(report.get(group), list):
                raise ValueError("Missing native check coverage")
            rows.extend(_violation(row, group, path) for row in report[group])
    ignored = report.get("ignored_checks", [])
    if not isinstance(ignored, list):
        raise ValueError("Invalid ignored check metadata")
    keys = tuple(row["key"] for row in ignored if isinstance(row, dict) and isinstance(row.get("key"), str))
    detail = f"{len(rows)} findings. Native error/warning rules; excluded violations are not included."
    if keys:
        detail += " Disabled rules: " + ", ".join(keys) + "."
    if len(rows) > MAX_FINDINGS:
        return Result("failed", f"Report exceeds the {MAX_FINDINGS}-finding limit; no lifecycle verdict.")
    return Result("ran", detail, rows, keys)


def _execute(snapshot: Snapshot, path: str, check: str, sheets: dict[str, str], parity=False,
             timeout: float | None = None) -> dict[str, Result]:
    binary = executable()
    names = [check, "parity"] if parity else [check]
    def fail(outcome, detail):
        return {name: Result(outcome, detail) for name in names}
    if not binary or tool_version() in {"unavailable", "unsupported"}:
        return fail("unavailable", "KiCad CLI 9 or 10 is unavailable. Install KiCad or set KICAD_CLI_PATH, then retry.")
    with temporary_directory("report-") as folder:
        output = Path(folder) / "report.json"
        args = [binary, "sch" if check == "erc" else "pcb", check, "--format", "json",
                "--exit-code-violations", "--severity-error", "--severity-warning", "--output", str(output)]
        if parity:
            args.append("--schematic-parity")
        args.append(str(safe_path(snapshot.root, path)))
        try:
            with (Path(folder) / "stdout.log").open("wb") as stdout, (Path(folder) / "stderr.log").open("wb") as stderr:
                run = subprocess.run(args, cwd=safe_path(snapshot.root, path).parent,
                                     env=_environment(binary, Path(folder)), timeout=timeout or TIMEOUT,
                                     stdout=stdout, stderr=stderr)
            if run.returncode not in {0, 5}:
                return fail("failed", f"KiCad {check.upper()} failed (exit {run.returncode}). Inspect the saved input and tool version.")
            if not output.is_file() or output.stat().st_size > MAX_REPORT_BYTES:
                return fail("failed", "KiCad produced no bounded JSON report.")
            data = output.read_bytes()
            result = {}
            for name in names:
                try:
                    result[name] = parse_report(data, name, path, sheets, requested_error_warning=True)
                except (ValueError, KeyError, TypeError, RecursionError):
                    result[name] = Result("failed", f"KiCad {name.upper()} JSON is invalid or lacks required check coverage.")
            return result
        except subprocess.TimeoutExpired:
            return fail("failed", f"KiCad {check.upper()} timed out after {timeout or TIMEOUT:g}s; this check is unverified.")
        except OSError:
            return fail("unavailable", "KiCad could not start or write its report; this check is unverified.")


def _stable_key(row: dict) -> str | None:
    ids = [item["uuid"] for item in row["items"]]
    if not ids or any(not uid or uid == "00000000-0000-0000-0000-000000000000" for uid in ids):
        return None
    # Measurement text changes when geometry changes. Stable object identity is
    # the anchor; multiple findings for the same key remain deliberately ambiguous.
    return json.dumps([row["rule"], row["scope"], row["path"], sorted(ids)], sort_keys=True)


def lifecycles(before: Result | None, after: Result | None) -> list[tuple[str, dict | None, dict | None]]:
    from collections import Counter
    old, new = before.rows if before and before.outcome == "ran" else [], after.rows if after and after.outcome == "ran" else []
    a, b = Counter(_stable_key(row) for row in old), Counter(_stable_key(row) for row in new)
    old_by_key = {_stable_key(row): row for row in old}
    matched = set()
    result = []
    # Ignored rule changes invalidate disappearance comparisons. A changed rule
    # configuration is not proof that an engineering defect was repaired.
    comparable = bool(before and after and before.outcome == after.outcome == "ran"
                      and before.ignored == after.ignored and before.settings == after.settings)
    for row in new:
        key = _stable_key(row)
        reliable = comparable and key is not None and b[key] == 1 and a[key] <= 1
        if reliable and a[key] == 1:
            matched.add(key)
            result.append(("existing", old_by_key[key], row))
        else:
            result.append(("new" if reliable else "present_at_head", None, row))
    if comparable:
        for row in old:
            key = _stable_key(row)
            if key is not None and a[key] == 1 and key not in matched and b[key] == 0:
                result.append(("resolved", row, None))
    return result


def _revision(repo_id: str, sha: str, deadline: float) -> tuple[dict[tuple[str, str], Result], dict[str, str]]:
    results = {}
    pairs = {}
    with materialize(repo_id, sha) as snapshot:
        boards = sorted(p for p in snapshot.files if p.lower().endswith(".kicad_pcb"))
        schematics = sorted(p for p in snapshot.files if p.lower().endswith(".kicad_sch"))
        # Roots are files not referenced by another sheet. Parse failures remain
        # candidates so they produce coverage failures rather than disappearing.
        children = set()
        for path in schematics:
            try:
                for _, name in parse_schematic(safe_path(snapshot.root, path).read_bytes()).sheets:
                    children.add(relative_dependency(path, name))
            except (SchematicParseError, SnapshotError):
                pass
        roots = sorted(set(schematics) - children)
        if schematics and not roots:
            roots = schematics  # cyclic hierarchy must fail explicitly
        targets = [(p, "drc") for p in boards] + [(p, "erc") for p in roots]
        for index, (path, check) in enumerate(targets):
            if index >= MAX_PROJECTS or time.monotonic() >= deadline:
                results[path, check] = Result("unavailable", "Native audit project/time budget reached; retry a smaller project.")
                continue
            if snapshot.issues:
                results[path, check] = Result("failed", "Snapshot inputs incomplete: " + "; ".join(f"{p}: {reason}" for p, reason in snapshot.issues)[:2000])
                continue
            sheets = {}
            sibling = str(PurePosixPath(path).with_suffix(".kicad_sch"))
            paired = check == "drc" and sibling in roots
            try:
                if check == "erc":
                    sheets = snapshot.sheets(path)
                elif paired:
                    sheets = snapshot.sheets(sibling)
                    pairs[path] = sibling
            except SnapshotError as exc:
                results[path, check] = Result("failed", str(exc))
                if check == "drc":
                    results[path, "parity"] = Result("failed", str(exc))
                continue
            settings = hashlib.sha256()
            for settings_path in (str(PurePosixPath(path).with_suffix(".kicad_pro")),
                                  str(PurePosixPath(path).with_suffix(".kicad_dru"))):
                settings.update(safe_path(snapshot.root, settings_path).read_bytes()
                                if settings_path in snapshot.files else b"<defaults>")
            for name, result in _execute(snapshot, path, check, sheets, parity=paired,
                                         timeout=max(.1, min(TIMEOUT, deadline - time.monotonic()))).items():
                result.settings = settings.hexdigest()
                if str(PurePosixPath(path).with_suffix(".kicad_pro")) not in snapshot.files:
                    result.detail += " No project settings saved; KiCad defaults used."
                results[path, name] = result
            if check == "drc" and not paired:
                results[path, "parity"] = Result("unavailable", "No unambiguous root schematic with the same directory and basename; parity was not checked.")
        for path, reason in snapshot.issues:
            results[path, "snapshot"] = Result("failed", reason)
    return results, pairs


def collect(repo_id: str, head: str, base: str | None) -> tuple[list[dict], list[dict]]:
    """Audit both immutable revisions; never infer clean from an unavailable run."""
    findings, coverage = [], []
    deadline = time.monotonic() + AUDIT_SECONDS
    revisions, pairs = {}, {}
    for sha in (base, head):
        if not sha:
            continue
        try:
            revisions[sha], pairs[sha] = _revision(repo_id, sha, deadline)
        except (ValueError, OSError, git.GitHubError) as exc:
            revisions[sha], pairs[sha] = {}, {}
            coverage.append(dict(path="", domain="project", check="KiCad snapshot", tool="git",
                                 outcome="failed", detail=f"{sha[:8]}: {exc}"))
        for (path, check), result in revisions[sha].items():
            coverage.append(dict(path=path, domain="schematic" if check == "erc" else "pcb",
                                 check={"drc": "Native PCB DRC", "erc": "Native schematic ERC",
                                        "parity": "Schematic/PCB parity", "snapshot": "KiCad snapshot"}[check],
                                 tool="kicad-cli", outcome=result.outcome,
                                 detail=f"{sha[:8]}: {result.detail}"))
    old, new = revisions.get(base, {}), revisions.get(head, {})
    for path, check in sorted(old.keys() | new.keys()):
        if check == "snapshot":
            continue
        for lifecycle, a, b in lifecycles(old.get((path, check)), new.get((path, check))):
            row = b or a
            evidence, related = [], []
            for sha, item in ((base, a), (head, b)):
                if not sha or item is None:
                    continue
                objects = item["items"] or [{"uuid": None, "description": item["summary"], "position": None}]
                for obj in objects:
                    locator = f"{obj['description']}" + (f" · UUID {obj['uuid']}" if obj["uuid"] else "")
                    identity = hashlib.sha256(json.dumps([repo_id, sha, item["path"], item["scope"], locator]).encode()).hexdigest()[:24]
                    evidence.append(dict(id=identity, repo_id=repo_id, sha=sha, path=item["path"], locator=locator))
                if check == "parity" and path in pairs[sha]:
                    related.append(dict(sha=sha, path=pairs[sha][path], basis="confirmed"))
            library = row["rule"].startswith("lib_") or row["rule"] == "footprint_link_issues"
            # Library consistency depends on the installed library versions. It
            # is not proof of an electrical defect in the saved design.
            if library:
                coverage.append(dict(path=row["path"], domain="schematic" if check == "erc" else "pcb",
                                     check="Library consistency", tool="kicad-cli", outcome="unavailable",
                                     detail="Library-version or resolution warning needs review: " + row["summary"]))
            findings.append(dict(rule_id=f"kicad.{check}.{row['rule']}", domain="schematic" if check == "erc" else "pcb",
                                 status="unverified" if library else "verified", severity=row["severity"], summary=row["summary"],
                                 lifecycle=lifecycle, before=a, after=b, evidence=evidence, related=related))
    if old or new:
        coverage.append(dict(path="", domain="pcb", check="Optional PCB heuristics", tool="pcb-inspector",
                             outcome="unavailable", detail="Optional heuristics deferred; native DRC/ERC and parity are reported separately."))
    return findings, coverage
