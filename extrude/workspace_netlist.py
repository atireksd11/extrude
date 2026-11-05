"""Read exact netlist pin numbers; optionally export a root with native KiCad."""

from pathlib import Path, PurePosixPath
import subprocess
import time

from kicad_tools.sexp import parse_string

from extrude import github_history as git, kicad_audit
from extrude.kicad_snapshot import materialize, temporary_directory, safe_path
from extrude.parse.kicad_netlist import parse_kicad_netlist
from extrude.parse.kicad_pcb import _PARSE_LOCK, _rows, _string_field

MAX_NETLIST_BYTES = 2 * 1024 * 1024
TIMEOUT = 20


def read_netlist(data: bytes) -> dict:
    if len(data) > MAX_NETLIST_BYTES:
        raise ValueError("Netlist exceeds the 2 MiB analysis limit.")
    text = data.decode("utf-8-sig")
    with _PARSE_LOCK:
        root = parse_string(text)
    if root.name != "export":
        raise ValueError("Expected a KiCad S-expression netlist.")
    boxes = {key: list(_rows(root, key)) for key in ("components", "nets")}
    if any(len(value) != 1 for value in boxes.values()):
        raise ValueError("Netlist components or connectivity section is missing or ambiguous.")
    # Reuse the existing electrical reader. Physical pad numbers are retained
    # separately because its Pin.name intentionally prefers the pin function.
    parse_kicad_netlist(text)
    components = {}
    for comp in _rows(boxes["components"][0], "comp"):
        ref = _string_field(comp, "ref")
        if not ref or ref in components:
            raise ValueError("Netlist reference is missing or duplicated.")
        props = {_string_field(prop, "name"): _string_field(prop, "value") for prop in _rows(comp, "property")}
        populated_flag = lambda name: name in props and (props[name] or "").lower() in {"", "yes", "true", "1"}
        components[ref] = dict(value=_string_field(comp, "value"),
                               dnp=populated_flag("dnp"), excluded=populated_flag("exclude_from_bom"),
                               excluded_from_board=populated_flag("exclude_from_board"),
                               uuid=_string_field(comp, "tstamps"),
                               sheet_path=next((_string_field(p, "tstamps") for p in _rows(comp, "sheetpath")), None))
    nets, seen_pins = {}, set()
    for net in _rows(boxes["nets"][0], "net"):
        name = _string_field(net, "name")
        if not name or name in nets:
            raise ValueError("Netlist net name is missing or duplicated.")
        pins = []
        for node in _rows(net, "node"):
            ref, pin = _string_field(node, "ref"), _string_field(node, "pin")
            if not ref or not pin or ref not in components:
                raise ValueError("Netlist contains an unresolved component/pad.")
            if (ref, pin) in seen_pins:
                raise ValueError("Netlist repeats a physical pad; connectivity is ambiguous.")
            seen_pins.add((ref, pin))
            pins.append(dict(reference=ref, pad=pin, function=_string_field(node, "pinfunction")))
        nets[name] = pins
    return dict(components=components, nets=nets)


class Reader:
    """Per-audit memoization; never confuse netlists from different SHAs."""
    def __init__(self):
        self.cache = {}
        self.exports = 0
        self.deadline = time.monotonic() + 90

    def get(self, repo_id: str, sha: str, path: str) -> dict:
        key = repo_id, sha, path
        if key in self.cache:
            result = self.cache[key]
            if isinstance(result, Exception):
                raise ValueError(str(result))
            return result
        try:
            if PurePosixPath(path).suffix.lower() == ".net":
                blob = git.regular_blob(repo_id, sha, path, max_bytes=MAX_NETLIST_BYTES)
                if blob is None:
                    raise ValueError("The mapped netlist is absent at this commit.")
            else:
                if self.exports >= 6 or time.monotonic() >= self.deadline:
                    raise ValueError("Netlist export budget reached; remaining mappings are unverified.")
                self.exports += 1
                binary = kicad_audit.executable()
                if not binary or kicad_audit.tool_version() in {"unavailable", "unsupported"}:
                    raise ValueError("KiCad is unavailable; cannot export the mapped schematic netlist.")
                with materialize(repo_id, sha) as snapshot, temporary_directory("netlist-") as folder:
                    if snapshot.issues:
                        raise ValueError("Schematic snapshot has missing or unsafe library inputs.")
                    snapshot.sheets(path)  # all child paths must be present and contained
                    output = Path(folder) / "assembly.net"
                    args = [binary, "sch", "export", "netlist", "--format", "kicadsexpr",
                            "--output", str(output), str(safe_path(snapshot.root, path))]
                    run = subprocess.run(args, cwd=safe_path(snapshot.root, path).parent,
                                         env=kicad_audit._environment(binary, Path(folder)),
                                         timeout=max(.1, min(TIMEOUT, self.deadline - time.monotonic())),
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if run.returncode or not output.is_file() or output.stat().st_size > MAX_NETLIST_BYTES:
                        raise ValueError("KiCad could not export a bounded netlist for this schematic.")
                    blob = output.read_bytes()
            result = read_netlist(blob)
        except (ValueError, OSError, subprocess.TimeoutExpired, RecursionError, IndexError) as exc:
            message = (str(exc) if isinstance(exc, ValueError) else "Netlist read/export failed or timed out; mapping is unverified.")
            self.cache[key] = ValueError(message)
            raise ValueError(message) from exc
        self.cache[key] = result
        return result
