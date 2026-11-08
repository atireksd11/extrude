"""Phase 3 facts and cross-file checks. Explicit mappings provide the scope."""

import hashlib
import json
from pathlib import PurePosixPath

from extrude import github_history as git
from extrude.parse.workspace_mesh import read_mesh, board_spans, SCALE, MAX_MESH_BYTES
from extrude.parse.workspace_firmware import read_constants, MAX_SOURCE_BYTES
from extrude.parse.workspace_bom import csv_facts, read_bom, compare_csv, MAX_BOM_BYTES
from extrude.workspace_settings import Settings
from extrude.workspace_netlist import Reader
from extrude import workspace_cad
from extrude.workspace import domain

MAX_ARTIFACTS = 60
ARTIFACT_SUFFIXES = {".stl", ".obj", ".step", ".stp", ".csv", ".tsv", ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".ino", ".py"}


def limit_profile():
    from extrude.parse import workspace_mesh, workspace_bom, workspace_firmware
    from extrude import workspace_netlist
    return dict(artifacts=MAX_ARTIFACTS, mesh_bytes=MAX_MESH_BYTES, mesh_faces=workspace_mesh.MAX_FACES,
                source_bytes=MAX_SOURCE_BYTES, constants=workspace_firmware.MAX_CONSTANTS,
                firmware_reader=workspace_firmware.READER_VERSION,
                bom_bytes=MAX_BOM_BYTES, bom_rows=workspace_bom.MAX_ROWS, bom_refs=workspace_bom.MAX_REFERENCES,
                bom_columns=workspace_bom.MAX_COLUMNS,
                netlist_bytes=workspace_netlist.MAX_NETLIST_BYTES, netlist_timeout=workspace_netlist.TIMEOUT,
                step_bytes=workspace_cad.MAX_STEP_BYTES, step_timeout=workspace_cad.TIMEOUT,
                cad_worker=workspace_cad.WORKER_VERSION)


def evidence(repo, sha, path, locator):
    identity = hashlib.sha256(json.dumps([repo, sha, path, locator]).encode()).hexdigest()[:24]
    return dict(id=identity, repo_id=repo, sha=sha, path=path, locator=locator)


def _blob(repo, sha, path, limit):
    data = git.regular_blob(repo, sha, path, max_bytes=limit)
    if data is None:
        raise ValueError("Mapped file is absent in this commit.")
    return data


def facts(repo, sha, path, *, preview=False):
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in {".stl", ".obj"}:
        return read_mesh(_blob(repo, sha, path, MAX_MESH_BYTES), suffix, preview=preview)
    if suffix in {".step", ".stp"}:
        try:
            return workspace_cad.read_step(_blob(repo, sha, path, workspace_cad.MAX_STEP_BYTES), preview=preview)
        except ValueError as exc:
            raise ValueError(f"{path}: not checked: {exc}") from exc
    if suffix in {".csv", ".tsv"}:
        return csv_facts(_blob(repo, sha, path, MAX_BOM_BYTES), "\t" if suffix == ".tsv" else ",")
    if suffix in {".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".ino", ".py"}:
        return dict(constants=read_constants(_blob(repo, sha, path, MAX_SOURCE_BYTES), path))
    raise ValueError("This format is visible in Git but has no Phase 3 reader. CAD measurement supports STL/OBJ exports.")


def review(repo, revision, path, base=None, previous_path=None, preview=True):
    sha, parent = git.comparison_revisions(repo, revision, base)
    sides = []
    for commit, file in ((parent, previous_path or path), (sha, path)):
        info = dict(sha=commit, path=file)
        try:
            if commit is None or not git.file_exists(repo, commit, file):
                # Distinguish a missing file from an unsafe tree entry.
                if commit:
                    _, entry = git._tree_entry(repo, commit, file)
                    if entry is not None:
                        raise ValueError("This path is not a regular Git file.")
                info.update(status="absent")
            else:
                info.update(status="read", facts=facts(repo, commit, file, preview=preview))
        except (ValueError, git.BlobUnavailable, RecursionError) as exc:
            info.update(status="unverified", detail=str(exc))
        sides.append(info)
    if all(s["status"] == "absent" for s in sides):
        raise KeyError(path)
    result = dict(before=sides[0], after=sides[1], status="unverified" if any(s["status"] == "unverified" for s in sides) else "compared")
    if PurePosixPath(path).suffix.lower() in {".csv", ".tsv"} and result["status"] == "compared":
        result["csv_comparison"] = compare_csv(*(side.get("facts") for side in sides))
    return result


class Collector:
    def __init__(self, repo, head, base):
        self.repo, self.head, self.base = repo, head, base
        self.findings, self.coverage = [], []
        self.netlists = Reader()

    def cover(self, path, domain, check, outcome, detail, tool="Atlas"):
        self.coverage.append(dict(path=path, domain=domain, check=check, tool=tool, outcome=outcome, detail=detail))

    def finding(self, rule, domain, summary, status="observed", severity="info", before=None, after=None,
                evidence_items=(), related=(), lifecycle=None):
        if len(self.findings) >= 500:
            if not any(c["check"] == "Phase 3 finding limit" for c in self.coverage):
                self.cover("", "project", "Phase 3 finding limit", "unsupported", "Only the first 500 Phase 3 findings are shown.")
            return
        self.findings.append(dict(rule_id=rule, domain=domain, status=status, severity=severity,
                                  summary=summary, before=before, after=after, evidence=list(evidence_items),
                                  related=list(related), lifecycle=lifecycle))

    def paired(self, path, domain, check, evaluator):
        """An evaluator returns keyed violations plus successful check detail."""
        revisions = {}
        complete = {}
        for sha in (self.base, self.head):
            if not sha:
                continue
            try:
                evaluated = evaluator(sha)
                rows, detail = evaluated[:2]
                revisions[sha] = rows
                complete[sha] = evaluated[2] if len(evaluated) > 2 else True
                self.cover(path, domain, check, "ran", f"{sha[:8]}: {detail}")
            except (ValueError, git.BlobUnavailable, git.GitHubError, KeyError, RecursionError) as exc:
                self.cover(path, domain, check, "unavailable", f"{sha[:8]}: {exc}")
        old, new = revisions.get(self.base, {}), revisions.get(self.head, {})
        comparable = self.base in revisions and self.head in revisions
        for key in sorted(old.keys() | new.keys()):
            a, b = old.get(key), new.get(key)
            if not b and not (comparable and complete[self.base] and complete[self.head]):
                continue
            row = b or a
            state = "existing" if a and b else "new" if b and self.base in revisions and complete[self.base] else "resolved" if not b else "present_at_head"
            sources = [*a["evidence"]] if a and comparable else []
            if b:
                sources.extend(b["evidence"])
            self.finding(row["rule"], domain, row["summary"], status=row.get("status", "verified"),
                         severity=row.get("severity", "warning"), before=a["measurement"] if a else None,
                         after=b["measurement"] if b else None, evidence_items=sources,
                         related=row.get("related", []), lifecycle=state)

    def cad(self, pair):
        def evaluate(sha):
            mesh = facts(self.repo, sha, pair.mesh_file)
            board = board_spans(_blob(self.repo, sha, pair.board_file, 8 * 1024 * 1024))
            sources = [evidence(self.repo, sha, pair.board_file, "Edge.Cuts bounds in mm"),
                       evidence(self.repo, sha, pair.mesh_file, f"Mesh bounds in declared {pair.units}"),
                       evidence(self.repo, sha, pair.mesh_file, "Saved project mapping: cavity, units and installed axes")]
            if pair.cavity_mm is None and pair.mesh_kind == "exterior":
                return {"exterior": dict(rule="cad.cavity_unverified", summary="Exterior bounds do not establish usable enclosure space.",
                                          status="suggestion", severity="info", measurement=dict(mesh=mesh["dimensions"], units=pair.units), evidence=sources)}, "Exterior measured; inner cavity and complete fit remain unverified."
            if pair.cavity_mm is None and not (mesh.get("watertight") or mesh.get("solids", 0) > 0):
                raise ValueError("A declared cavity export must be a closed mesh or valid STEP solid; open geometry cannot establish cavity spans.")
            scale = 1.0 if mesh["unit"] == "mm" else SCALE[pair.units]
            cavity = list(pair.cavity_mm) if pair.cavity_mm is not None else [d * scale for d in mesh["dimensions"]]
            if any(d <= 0 for d in cavity):
                raise ValueError("Cavity does not have three positive measurable spans.")
            rows = {}
            for index, axis in enumerate(pair.board_axes):
                actual, available = board["dimensions_mm"][index], cavity["xyz".index(axis)]
                if actual > available + 1e-6:
                    rows[axis] = dict(rule="cad.board_exceeds_cavity", summary=f"Board exceeds cavity {axis.upper()} span: {actual:g} mm > {available:g} mm.",
                                      measurement=dict(board_mm=actual, cavity_mm=available, board_axis="xy"[index], enclosure_axis=axis,
                                                       cavity_source="declared dimensions" if pair.cavity_mm is not None else "declared cavity export bounds"), evidence=sources,
                                      related=[dict(sha=sha, path=pair.mesh_file, basis="configured")])
            detail = "Board spans compared on configured installed axes. "
            detail += "Exceeds declared cavity bounds." if rows else "No span exceeds the declared cavity bounds; full fit remains unverified."
            return rows, detail + " Holes, collisions, tolerances, components and outline topology are not validated."
        self.paired(pair.board_file, "cad", "Board/cavity spans", evaluate)

    def pin(self, rule):
        def evaluate(sha):
            constants = facts(self.repo, sha, rule.firmware_file)["constants"]
            item = constants.get(rule.firmware_symbol)
            if not item or item["value"] is None:
                raise ValueError((item or {}).get("detail") or "Mapped symbol has no unique integer literal.")
            if rule.numbering == "package" and (item.get("detail") or "").startswith("ESP32 GPIO enum"):
                raise ValueError("ESP32 GPIO enums use logical GPIO numbers. Select GPIO numbering and declare the package-pad mapping.")
            number = str(item["value"])
            pad = rule.gpio_to_pad.get(number) if rule.numbering == "gpio" else number
            if not pad:
                raise ValueError(f"GPIO {number} has no declared package-pad mapping.")
            nets = self.netlists.get(self.repo, sha, rule.netlist_file)
            pins = [p["pad"] for p in nets["nets"].get(rule.schematic_net, []) if p["reference"] == rule.mcu_ref]
            if len(pins) != 1:
                raise ValueError("Mapped net/MCU package pad is absent or ambiguous.")
            sources = [evidence(self.repo, sha, rule.firmware_file, f"line {item['line']}: {rule.firmware_symbol} = {number}"),
                       evidence(self.repo, sha, rule.netlist_file, f"{rule.mcu_ref} pad {pins[0]} on net {rule.schematic_net}")]
            if pad == pins[0]:
                return {}, f"{rule.firmware_symbol} maps to {rule.mcu_ref} pad {pad} on {rule.schematic_net}."
            row = dict(rule="firmware.pin_mismatch", summary=f"{rule.firmware_symbol}: firmware maps to pad {pad}, but {rule.schematic_net} uses {rule.mcu_ref} pad {pins[0]}.",
                       measurement=dict(symbol=rule.firmware_symbol, firmware_literal=item["value"], mapped_pad=pad, actual_pad=pins[0], net=rule.schematic_net, numbering=rule.numbering),
                       evidence=sources, related=[dict(sha=sha, path=rule.netlist_file, basis="configured")])
            return {rule.firmware_symbol: row}, "Compared a declared firmware-to-net/pad mapping; no code executed."
        self.paired(rule.firmware_file, "firmware", "Firmware/netlist pin mapping", evaluate)

    def bom(self, mapping):
        parsed = {}
        def evaluate(sha):
            data = read_bom(_blob(self.repo, sha, mapping.bom_file, MAX_BOM_BYTES), mapping)
            parsed[sha] = data
            assembly = self.netlists.get(self.repo, sha, mapping.schematic_file)["components"]
            rows = {}
            for item in data["rows"]:
                if item["dnp"]:
                    continue
                assembly_excluded = [ref for ref in item["references"] if ref in assembly
                                     and (assembly[ref]["dnp"] or assembly[ref]["excluded"])]
                sources = [evidence(self.repo, sha, mapping.bom_file, f"CSV record ending at line {item['line']}: {', '.join(item['references'])}"),
                           evidence(self.repo, sha, mapping.schematic_file, "Scoped assembly references from native schematic netlist")]
                if assembly_excluded:
                    self.cover(mapping.bom_file, "bom", "BOM population scope", "unsupported",
                               f"{sha[:8]}: line {item['line']} contains schematic DNP/excluded parts; quantity verdict skipped.")
                if not assembly_excluded and item["quantity"] != len(item["references"]):
                    rows["quantity:" + ",".join(item["references"])] = dict(rule="bom.quantity_mismatch", summary=f"BOM quantity {item['quantity']} differs from {len(item['references'])} listed references.",
                            measurement=dict(quantity=item["quantity"], references=item["references"]), evidence=sources)
                for ref in item["references"]:
                    if ref not in assembly:
                        rows["missing:" + ref] = dict(rule="bom.reference_missing", summary=f"BOM reference {ref} is absent from the configured schematic assembly.",
                            measurement=dict(reference=ref, part=item["part"]), evidence=sources,
                            related=[dict(sha=sha, path=mapping.schematic_file, basis="configured")])
            if data["issues"]:
                self.cover(mapping.bom_file, "bom", "BOM ambiguous rows", "unsupported", f"{sha[:8]}: " + "; ".join(f"line {r['line']}: {r['detail']}" for r in data["issues"])[:1800])
            return rows, f"Checked {len(data['rows'])} parsed BOM rows against the configured assembly; DNP rows skipped.", not bool(data["issues"])
        self.paired(mapping.bom_file, "bom", "BOM assembly references and quantities", evaluate)
        # Field comparisons do not need a successful netlist. Preserve strings.
        for sha in (self.base, self.head):
            if sha and sha not in parsed:
                try:
                    parsed[sha] = read_bom(_blob(self.repo, sha, mapping.bom_file, MAX_BOM_BYTES), mapping)
                except (ValueError, git.BlobUnavailable):
                    pass
        if self.base not in parsed or self.head not in parsed:
            return
        def index(data):
            return {ref: row for row in data["rows"] for ref in row["references"]}
        old, new = index(parsed[self.base]), index(parsed[self.head])
        emitted = set()
        for ref in sorted(old.keys() & new.keys()):
            for field in ("part", "quantity", "dnp"):
                a, b = old[ref], new[ref]
                if a[field] == b[field]:
                    continue
                if field == "quantity":
                    group = tuple(sorted(a["references"]))
                    if group != tuple(sorted(b["references"])) or group in emitted:
                        continue
                    emitted.add(group)
                sources = [evidence(self.repo, sha, mapping.bom_file, f"CSV record ending at line {row['line']}: {ref}")
                           for sha, row in ((self.base, a), (self.head, b))]
                self.finding("bom." + field + "_changed", "bom", f"{ref}: BOM {field} changed.", before=a[field], after=b[field], evidence_items=sources)


def collect(repo, head, base, settings: Settings, changes) -> tuple[list[dict], list[dict]]:
    result = Collector(repo, head, base)
    count = 0
    for row in changes:
        path = row["path"]
        ext = PurePosixPath(path).suffix.lower()
        area = domain(path, row.get("kind", git._kind(path)))
        if any(mapping.bom_file == path for mapping in settings.boms):
            area = "bom"
        if ext not in ARTIFACT_SUFFIXES:
            continue
        count += 1
        if count > MAX_ARTIFACTS:
            result.cover(path, area, "Artifact facts", "unsupported", "Artifact analysis limit reached.")
            continue
        try:
            data = review(repo, head, path, base, row.get("previous_path"), preview=False)
            result.cover(path, area, "Artifact facts", "ran" if data["status"] == "compared" else "failed",
                         "Read saved versions. " + " ".join(s.get("detail", "") for s in (data["before"], data["after"])), "trimesh" if area == "cad" else "Atlas")
            a, b = data["before"], data["after"]
            comparison = data.get("csv_comparison")
            if comparison and area == "bom":
                result.cover(path, area, "BOM cell comparison", "unsupported" if comparison["ambiguous"] or not comparison["key_column"] else "ran",
                             f"{comparison['changed_cells']} changed cells, {comparison['added']} added rows, {comparison['removed']} removed rows. "
                             + comparison["detail"] + (f" {comparison['ambiguous']} rows could not be matched." if comparison["ambiguous"] else ""))
                if comparison["added_columns"] or comparison["removed_columns"]:
                    src = [evidence(repo, side["sha"], side["path"], "CSV column headers") for side in (a, b) if side["status"] == "read"]
                    result.finding("bom.columns_changed", area, "BOM columns changed.",
                                   before=a.get("facts", {}).get("columns"), after=b.get("facts", {}).get("columns"), evidence_items=src)
                mapping = next((m for m in settings.boms if m.bom_file == path), None)
                mapped_columns = {mapping.part_column, mapping.quantity_column, mapping.dnp_column} if mapping else set()
                for entry in comparison["rows"]:
                    if entry["status"] not in {"added", "removed", "modified"}:
                        continue
                    src = [evidence(repo, side["sha"], side["path"], f"CSV record ending at line {record['line']}: {entry['key'][:160]}")
                           for side, record in ((a, entry["before"]), (b, entry["after"])) if record and side["status"] == "read"]
                    if entry["status"] != "modified":
                        result.finding("bom.row_" + entry["status"], area, f"{entry['key'][:160]}: BOM row {entry['status']}.",
                                       before=entry["before"]["fields"] if entry["before"] else None,
                                       after=entry["after"]["fields"] if entry["after"] else None, evidence_items=src)
                    for change in entry["changes"]:
                        if change["column"] in mapped_columns:
                            continue
                        result.finding("bom.cell_changed", area, f"{entry['key'][:160]}: {change['column']} changed.",
                                       before=change["before"], after=change["after"], evidence_items=src)
            if a["status"] == b["status"] == "read":
                sources = [evidence(repo, s["sha"], s["path"], "Saved artifact facts") for s in (a, b)]
                if area == "cad" and a["facts"]["dimensions"] != b["facts"]["dimensions"]:
                    unit = b["facts"]["unit"]
                    result.finding("cad.extents_changed", area, f"CAD bounds changed ({unit}).", before=a["facts"]["dimensions"], after=b["facts"]["dimensions"], evidence_items=sources)
                if area == "cad":
                    fields = ("solids", "faces", "volume_mm3") if ext in {".step", ".stp"} else ("total_triangles", "watertight")
                    old_stats = {key: a["facts"].get(key) for key in fields}
                    new_stats = {key: b["facts"].get(key) for key in fields}
                    if old_stats != new_stats:
                        result.finding("cad.geometry_summary_changed", area, "CAD geometry statistics changed; inspect the two saved versions.", before=old_stats, after=new_stats, evidence_items=sources)
                if "constants" in a["facts"]:
                    old, new = a["facts"]["constants"], b["facts"]["constants"]
                    for name in sorted(old.keys() & new.keys()):
                        if old[name].get("alias_of") or new[name].get("alias_of"):
                            continue
                        if old[name]["value"] != new[name]["value"]:
                            src = [evidence(repo, s["sha"], s["path"], f"line {s['facts']['constants'][name]['line']}: {name}") for s in (a, b)]
                            result.finding("firmware.constant_changed", area, f"{name}: literal assignment changed.", before=old[name]["value"], after=new[name]["value"], evidence_items=src)
        except (ValueError, git.BlobUnavailable, KeyError, RecursionError) as exc:
            result.cover(path, area, "Artifact facts", "failed", str(exc))
    for pair in settings.cad_pairs:
        result.cad(pair)
    for rule in settings.pin_assignments:
        result.pin(rule)
    for bom in settings.boms:
        result.bom(bom)
    # Lack of mappings cannot be mistaken for a passed cross-domain check.
    for area, configured in (("cad", settings.cad_pairs), ("firmware", settings.pin_assignments), ("bom", settings.boms)):
        if not configured:
            detail = ("Assembly validation requires a BOM-to-schematic mapping. Shopping-list cell changes are reviewed without one."
                      if area == "bom" else f"Configure {area} checks to establish units, scope and confirmed file relationships.")
            result.cover("", area, "Project mapping", "unavailable", detail)
    return result.findings, result.coverage
