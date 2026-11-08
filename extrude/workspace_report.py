"""Human-readable views of saved checks. This does not rerun or change an audit."""

import re

from extrude.workspace_audit import Audit, Finding

_MISSING_LIBRARY = re.compile(r"The current configuration does not include the (footprint|symbol) library '(.+)'")
_GROUP_ORDER = ("New problems", "Problems at selected commit", "What changed", "Review suggested",
                "Existing problems", "Resolved", "Check limitations")
_RULE_GUIDANCE = {
    "clearance": ("Copper is too close for the clearance rule used in this check.",
                  "Insufficient spacing can make the board harder to manufacture reliably.",
                  "Open the cited items in KiCad, check the clearance rule, and re-run DRC after correcting the spacing."),
    "tracks_crossing": ("KiCad reported intersecting tracks on the board.",
                        "Copper intersections can connect signals that should be separate.",
                        "Highlight both cited tracks in KiCad and check their layers and nets before rerouting."),
    "unconnected_items": ("KiCad found items that the design expects to connect but that remain unconnected.",
                          "An open connection can stop the affected signal or power rail from reaching its destination.",
                          "Highlight the reported net in the PCB editor and trace it between the cited items. Re-run DRC after correcting the connection."),
    "shorting_items": ("KiCad reported copper connecting items assigned to different nets.",
                       "An unintended connection can tie two signals or power rails together.",
                       "Inspect both cited nets in the PCB editor. Confirm whether the connection is intended before editing the copper."),
    "pin_not_connected": ("KiCad found a schematic pin with no electrical connection.",
                          "If the pin is required, the circuit may miss a signal or power connection.",
                          "Find the cited pin in the schematic and check its role. Wire it if required or explicitly mark it unconnected if that was intentional."),
    "track_dangling": ("KiCad found a track with an end that does not join another copper item on its net.",
                       "The track may be unfinished or leftover from a routing change.",
                       "Highlight the net at the cited track and check whether the end should reach another pad or track before removing or extending it."),
    "footprint_symbol_mismatch": ("KiCad found a difference between a board footprint and its schematic symbol.",
                                  "The board and schematic may disagree about which part should be used at that reference.",
                                  "Compare the cited reference in both editors and use the checker message to identify which property differs."),
    "net_conflict": ("KiCad found a difference between a board pad’s net and the expected schematic connection.",
                     "The board may connect that pad differently from the circuit shown in the schematic.",
                     "Compare the cited pad and schematic pin. Confirm the intended net, sync the board, and re-run the parity check."),
    "footprint_removed": ("This footprint disappeared from the board between the two commits.",
                          "The schematic or parts list may still call for that component.",
                          "Check the cited reference in the schematic and parts list. If the removal was intentional, confirm those files reflect it."),
    "pad_net_changed": ("The electrical net assigned to this PCB pad changed.",
                        "A different connection can affect the signal or power that reaches this pin.",
                        "Compare the pad number and net name in the board and schematic, then check the firmware if the pad is part of a pin mapping."),
    "pad_disconnected": ("A PCB pad that had a net assignment lost that assignment.",
                         "If the pad still needs that connection, the board can leave the intended signal or supply disconnected.",
                         "Check the pad number in the board and the corresponding pin in the schematic. Re-run DRC after confirming the intended net."),
    "position_changed": ("This footprint moved on the board between the two commits.",
                         "Placement can affect clearances, routing, and access to connectors or controls.",
                         "Compare the two placements and check the affected area in KiCad and any linked enclosure."),
    "firmware.pin_mismatch": ("The firmware and the configured schematic mapping point to different pins.",
                             "The firmware may drive or read a different pin from the one connected on the board.",
                             "Confirm the intended pin in the schematic and firmware, then update the stale mapping or file and re-run the audit."),
    "cad.board_exceeds_cavity": ("A board dimension exceeds the configured inner cavity span.",
                                 "The board may not fit along the mapped axis with the current cavity dimensions.",
                                 "Check the orientation and units against the cited board and cavity, then verify fit in the CAD assembly."),
    "bom.quantity_mismatch": ("The quantity and count of reference designators disagree.",
                             "The parts list may order too many or too few of this part.",
                             "Compare the row against the intended populated references, then correct the quantity or reference list."),
    "bom.reference_missing": ("A parts-list reference was absent from the configured schematic assembly.",
                              "The parts list may include a stale designator or be mapped to the wrong schematic.",
                              "Search the schematic for that reference and check the assembly mapping before editing the BOM."),
    "bom.cell_changed": ("A value changed in the cited parts-list row.",
                          "The effect depends on the column. A change to cost, quantity, or part number can affect purchasing.",
                          "Compare the two values and confirm the change with the person responsible for the parts list."),
}


def missing_libraries(audit: Audit) -> dict[tuple[str, str], list[int]]:
    libraries = {}
    for index, finding in enumerate(audit.findings):
        if finding.status == "unverified" and finding.rule_id in {
            "kicad.drc.lib_footprint_issues", "kicad.erc.footprint_link_issues", "kicad.erc.lib_symbol_issues"
        }:
            match = _MISSING_LIBRARY.fullmatch(finding.summary)
            if match:
                libraries.setdefault((match[1], match[2]), []).append(index)
    return libraries


def _group(finding: Finding) -> str:
    if finding.status == "unverified":
        return "Check limitations"
    if finding.lifecycle == "resolved":
        return "Resolved"
    if finding.status == "verified" and finding.lifecycle == "new":
        return "New problems"
    if finding.status == "verified" and finding.lifecycle == "existing":
        return "Existing problems"
    if finding.status == "verified":
        return "Problems at selected commit"
    return "What changed" if finding.status == "observed" else "Review suggested"


def finding_guidance(finding: Finding) -> dict[str, str]:
    rule = finding.rule_id
    kind = rule.rsplit(".", 1)[-1]
    guidance = _RULE_GUIDANCE.get(rule)
    if rule.startswith(("kicad.", "pcb.")):
        guidance = guidance or _RULE_GUIDANCE.get(kind)
    if finding.status == "unverified":
        guidance = ("The available check could not verify this item.",
                    "This leaves a gap in the review for the cited file or component.",
                    "Open the checker message and source evidence, address the reported prerequisite, then re-run the check.")
    elif finding.lifecycle == "resolved":
        guidance = ("The checker reported this at the base commit and did not report it at the selected commit.",
                    "This comparison shows the recorded issue cleared within the scope of this rule.",
                    "Check the before and after evidence to confirm the resolution matches the intended change.")
    if guidance is None and finding.status == "observed":
        guidance = ("Extrude recorded a difference between the saved versions.",
                    "The significance depends on what this file or component is meant to do.",
                    "Compare the before and after evidence and review any linked files before treating the change as intentional.")
    if guidance is None:
        guidance = ("The check flagged the condition shown in the title.",
                    "Review the affected items in context to understand the impact.",
                    "Open the cited source and confirm the condition using the relevant design tool before editing.")
    return dict(zip(("what", "why", "next_step"), guidance))


def library_guidance(libraries, audit: Audit) -> dict:
    entries = []
    for (kind, name), indexes in libraries.items():
        references = set()
        for index in indexes:
            finding = audit.findings[index]
            for facts in (finding.before, finding.after):
                if not isinstance(facts, dict):
                    continue
                for item in facts.get("items", []):
                    match = re.match(r"(?:Footprint|Symbol) (\S+)", item.get("description", ""))
                    if match:
                        references.add(match[1])
        entries.append(dict(kind=kind, name=name, references=sorted(references), indexes=indexes))
    return dict(
        title="KiCad could not load referenced libraries",
        what="KiCad reported that its audit configuration could not resolve the library references listed below.",
        why="The audit could not verify those saved symbols or footprints against their library definitions. This is a setup issue to investigate.",
        next_step="Check the project’s symbol and footprint library tables (sym-lib-table and fp-lib-table) and their paths. Make the referenced library files available with project-relative paths, then re-run the audit.",
        libraries=entries,
    )


def review(audit: Audit) -> dict:
    libraries = missing_libraries(audit)
    library_indexes = sorted(index for indexes in libraries.values() for index in indexes)
    excluded = set(library_indexes)
    groups = {name: [] for name in _GROUP_ORDER}
    for index, finding in enumerate(audit.findings):
        if index in excluded:
            continue
        groups[_group(finding)].append(dict(source_id=f"F{index}", indexes=[index], **finding_guidance(finding)))
    severity_order = {"error": 0, "warning": 1, "info": 2}
    for title in ("New problems", "Problems at selected commit", "Existing problems"):
        groups[title].sort(key=lambda row: severity_order[audit.findings[row["indexes"][0]].severity])
    if library_indexes:
        groups["Check limitations"].insert(0, dict(source_id="L0", indexes=library_indexes,
                                                  **library_guidance(libraries, audit)))
    return dict(groups=[dict(title=title, items=items) for title, items in groups.items() if items],
                new_problems=len(groups["New problems"]), baseline_unverified=len(groups["Problems at selected commit"]),
                finding_count=len(audit.findings) - len(library_indexes))
