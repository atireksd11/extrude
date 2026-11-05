"""Revision-scoped relationships, derived from parsers and explicit mappings."""

from collections import Counter
import hashlib
import json
from pathlib import PurePosixPath
import re

from extrude import github_history as git
from extrude.kicad_snapshot import materialize, safe_path, relative_dependency
from extrude.parse.kicad_pcb import parse_board
from extrude.parse.kicad_schematic import parse_schematic
from extrude.parse.workspace_bom import read_bom, MAX_BOM_BYTES
from extrude.workspace_checks import evidence, facts
from extrude.workspace_netlist import Reader
from extrude.workspace_settings import Settings

MAX_LINKS = 600
MAX_PROJECTS = 8


class Links:
    def __init__(self, audit):
        self.audit = audit
        self.rows, self.coverage = [], []
        self.netlists = Reader()
        self.identities = set()
        self.truncated = False

    def cover(self, path, outcome, detail):
        self.coverage.append(dict(path=path, domain="project", check="Cross-file relationships", tool="Atlas",
                                  outcome=outcome, detail=detail))

    def add(self, kind, status, source, target, summary, metadata=None):
        key = hashlib.sha256(json.dumps([kind, source, target], sort_keys=True).encode()).hexdigest()[:24]
        if key in self.identities:
            return
        if len(self.rows) >= MAX_LINKS:
            self.truncated = True
            return
        self.identities.add(key)
        self.rows.append(dict(id=key, kind=kind, status=status, source=source, target=target,
                              summary=summary, metadata=metadata or {}))

    def revision(self, sha, settings):
        repo = self.audit.repo_id
        with materialize(repo, sha) as snapshot:
            if snapshot.issues:
                self.cover("", "unavailable", f"{sha[:8]}: KiCad snapshot dependencies are incomplete; component links unverified.")
                return
            sources = {}
            def assembly(root):
                if root in sources:
                    return sources[root]
                sheets = snapshot.sheets(root)
                netlist = self.netlists.get(repo, sha, root)
                by_uuid = {}
                for path in set(sheets.values()):
                    for symbol in parse_schematic(safe_path(snapshot.root, path).read_bytes()).symbols:
                        by_uuid.setdefault(symbol.uuid, set()).add(path)
                def source(ref):
                    comp = netlist["components"][ref]
                    uid, sheet = comp.get("uuid"), comp.get("sheet_path")
                    relative = "/" + (sheet or "").strip("/")
                    path = sheets.get(relative) if sheet else None
                    if path is None and sheet:
                        # ERC UUID paths include the root UUID; native netlist
                        # sheet paths normally start directly with the child.
                        relative = "/" + "/".join(sheet.strip("/").split("/")[1:])
                        path = sheets.get(relative)
                    if path is None and uid and len(by_uuid.get(uid, set())) == 1:
                        path = next(iter(by_uuid[uid]))
                    if uid in by_uuid and path not in by_uuid[uid]:
                        raise ValueError("Component UUID and sheet instance disagree.")
                    if path is None:
                        raise ValueError("Component source sheet could not be resolved unambiguously.")
                    locator = ref + (f" · symbol UUID {uid}" if uid else "") + (f" · sheet {sheet}" if sheet else "")
                    return evidence(repo, sha, path, locator)
                sources[root] = netlist, source
                return sources[root]

            children = set()
            for file in snapshot.files:
                if file.lower().endswith(".kicad_sch"):
                    try:
                        children.update(relative_dependency(file, child) for _, child in parse_schematic(safe_path(snapshot.root, file).read_bytes()).sheets)
                    except ValueError:
                        pass
            boards = sorted(p for p in snapshot.files if p.lower().endswith(".kicad_pcb"))
            paired_boards = [path for path in boards if str(PurePosixPath(path).with_suffix(".kicad_sch")) in snapshot.files
                             and str(PurePosixPath(path).with_suffix(".kicad_sch")) not in children]
            cad_assets = [row["path"] for row in git.inventory(repo, sha, limit=10000)["files"]
                          if row["type"] == "blob" and PurePosixPath(row["path"]).suffix.lower() in {".stl", ".obj", ".step", ".stp"}]
            if len(paired_boards) == len(cad_assets) == 1 and not any(p.board_file == paired_boards[0] for p in settings.cad_pairs):
                self.add("board_enclosure", "possible",
                         evidence(repo, sha, paired_boards[0], "Sole basename-paired KiCad project"),
                         evidence(repo, sha, cad_assets[0], "Sole CAD asset; association needs confirmation"),
                         "Possible project CAD connection: one CAD asset and one paired KiCad project. Confirm the association; mechanical effects are unverified.",
                         {"requires_confirmation": True, "basis": "unique CAD asset and matched KiCad project"})
            for index, path in enumerate(boards):
                root = str(PurePosixPath(path).with_suffix(".kicad_sch"))
                if root not in snapshot.files or root in children:
                    self.cover(path, "unavailable", f"{sha[:8]}: No basename-paired schematic; no component match assumed.")
                    continue
                if index >= MAX_PROJECTS:
                    self.cover(path, "unsupported", "Relationship project limit reached.")
                    continue
                try:
                    netlist, source = assembly(root)
                    board = parse_board(safe_path(snapshot.root, path).read_bytes())
                    counts = Counter(f.reference for f in board.footprints)
                    footprints = {f.reference: f for f in board.footprints if f.reference and counts[f.reference] == 1}
                    for ref, component in netlist["components"].items():
                        if component.get("excluded_from_board"):
                            continue
                        origin = source(ref)
                        fp = footprints.get(ref)
                        if fp is None:
                            self.add("schematic_pcb_component", "unverified", origin,
                                     evidence(repo, sha, path, ref + " · no unique footprint reference"),
                                     ref + ": no unique PCB reference matched in this KiCad project.", {"reference": ref, "root": root})
                            continue
                        matched, mismatched = [], []
                        for net, pins in netlist["nets"].items():
                            for pin in pins:
                                if pin["reference"] != ref:
                                    continue
                                nets = fp.pads.get(pin["pad"], ())
                                entry = dict(pad=pin["pad"], schematic_net=net, pcb_nets=list(nets))
                                (matched if nets and all(name == net for name in nets) else mismatched).append(entry)
                        self.add("schematic_pcb_component", "confirmed", origin,
                                 evidence(repo, sha, path, f"{ref} · footprint UUID {fp.uuid or 'unavailable'}"),
                                 f"{ref}: exact reference matched within {PurePosixPath(root).name}.",
                                 dict(reference=ref, root=root, matching_pads=matched[:64], unmatched_pads=mismatched[:64],
                                      pin_details_truncated=len(matched) > 64 or len(mismatched) > 64,
                                      scope="Component identity; net agreement is listed separately, not inferred from reference alone."))
                    self.cover(path, "ran", f"{sha[:8]}: Scoped component references and pad/net agreement read from the matched schematic and PCB.")
                except (ValueError, KeyError, git.GitHubError, OSError, RecursionError) as exc:
                    self.cover(path, "unavailable", f"{sha[:8]}: {str(exc)[:300]}")
            for mapping in settings.boms:
                try:
                    blob = git.regular_blob(repo, sha, mapping.bom_file, max_bytes=MAX_BOM_BYTES)
                    if blob is None:
                        raise ValueError("Mapped BOM absent.")
                    parsed = read_bom(blob, mapping)
                    netlist, source = assembly(mapping.schematic_file)
                    for row in parsed["rows"]:
                        if row["dnp"]:
                            continue
                        for ref in row["references"]:
                            if ref in netlist["components"]:
                                self.add("bom_schematic_component", "confirmed",
                                         evidence(repo, sha, mapping.bom_file, f"line {row['line']}: {ref}"), source(ref),
                                         f"{ref}: BOM reference belongs to the configured schematic assembly.",
                                         {"reference": ref, "root": mapping.schematic_file})
                    self.cover(mapping.bom_file, "unsupported" if parsed["issues"] else "ran", f"{sha[:8]}: BOM links scoped to {mapping.schematic_file}; ambiguous/DNP rows excluded.")
                except (ValueError, KeyError, git.GitHubError, OSError, RecursionError) as exc:
                    self.cover(mapping.bom_file, "unavailable", f"{sha[:8]}: {str(exc)[:300]}")

        for pair in settings.cad_pairs:
            if git.file_exists(repo, sha, pair.board_file) and git.file_exists(repo, sha, pair.mesh_file):
                self.add("board_enclosure", "configured", evidence(repo, sha, pair.board_file, "Configured PCB"),
                         evidence(repo, sha, pair.mesh_file, "Configured enclosure; physical fit checked separately"),
                         "Declared board/enclosure relationship; a relationship does not establish fit.", pair.model_dump(mode="json"))
        for rule in settings.pin_assignments:
            try:
                item = facts(repo, sha, rule.firmware_file)["constants"].get(rule.firmware_symbol)
                if not item or item["value"] is None:
                    raise ValueError("Firmware symbol unresolved.")
                netlist = self.netlists.get(repo, sha, rule.netlist_file)
                pins = [p for p in netlist["nets"].get(rule.schematic_net, []) if p["reference"] == rule.mcu_ref]
                if len(pins) != 1:
                    raise ValueError("Hardware net/pad is ambiguous.")
                value = str(item["value"])
                pad = rule.gpio_to_pad.get(value) if rule.numbering == "gpio" else value
                is_gpio = (item.get("detail") or "").startswith("ESP32 GPIO enum")
                status = "confirmed" if pad == pins[0]["pad"] and not (is_gpio and rule.numbering == "package") else "configured"
                self.add("firmware_hardware_pin", status,
                         evidence(repo, sha, rule.firmware_file, f"line {item['line']}: {rule.firmware_symbol} = {value}"),
                         evidence(repo, sha, rule.netlist_file, f"{rule.mcu_ref} pad {pins[0]['pad']} on {rule.schematic_net}"),
                         f"{rule.firmware_symbol} → {rule.mcu_ref} / {rule.schematic_net}; {status} mapping.",
                         dict(symbol=rule.firmware_symbol, reference=rule.mcu_ref, actual_pad=pins[0]["pad"], mapped_pad=pad, net=rule.schematic_net))
            except (ValueError, KeyError, git.GitHubError, RecursionError) as exc:
                self.cover(rule.firmware_file, "unavailable", f"{sha[:8]}: {str(exc)[:300]}")


def collect(audit):
    links = Links(audit)
    settings = Settings.model_validate(audit.project_settings)
    for sha in (audit.base_sha, audit.head_sha):
        if sha:
            try:
                links.revision(sha, settings)
            except (ValueError, OSError, git.GitHubError, KeyError) as exc:
                links.cover("", "unavailable", f"{sha[:8]}: {str(exc)[:300]}")
    if links.truncated:
        links.cover("", "unsupported", f"Only the first {MAX_LINKS} relationships are included.")
    return links.rows, links.coverage


def attach(audit):
    """Add only scoped evidence to relevant findings, including removed parts."""
    from extrude.workspace_audit import RelatedFile
    for finding in audit.findings:
        text = finding.summary + " " + " ".join(e.locator for e in finding.evidence)
        references = set(re.findall(r"\b[A-Za-z]{1,10}\d+\b", text))
        sources = {(e.sha, e.path) for e in finding.evidence}
        selected = []
        for link in audit.relationships:
            if not sources.intersection({(link.source.sha, link.source.path), (link.target.sha, link.target.path)}):
                continue
            ref = link.metadata.get("reference")
            if link.kind in {"schematic_pcb_component", "bom_schematic_component"} and ref not in references:
                continue
            if link.kind == "firmware_hardware_pin" and link.metadata.get("symbol") not in text:
                continue
            if link.kind == "board_enclosure" and finding.domain != "pcb":
                continue
            if link.kind == "board_enclosure" and finding.rule_id not in {"pcb.position_changed", "pcb.rotation_changed", "pcb.library_changed", "pcb.footprint_added", "pcb.footprint_removed"}:
                continue
            selected.append(link)
            if len(selected) >= 8:
                break
        for link in selected:
            if link.kind == "board_enclosure":
                if not any(r.sha == link.target.sha and r.path == link.target.path for r in finding.related):
                    finding.related.append(RelatedFile(sha=link.target.sha, path=link.target.path, basis="possible"))
                continue
            for item in (link.source, link.target):
                if not any(e.id == item.id for e in finding.evidence):
                    finding.evidence.append(item)
