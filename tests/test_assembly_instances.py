"""Exercise placement annotation with small fixtures modeled on the audit cases."""

from pathlib import Path

import pytest

from extrude.electrical_graph import build
from extrude.electrical_reasoning import analyze
from extrude.parse.kicad_schematic import parse_schematic
from test_electrical_reasoning import design, resistor
from test_trust_blockers import board, device

pytestmark = pytest.mark.atlas


def annotate(schematic, raw, placements, unit=1, dnp=False):
    entries = " ".join(
        f'(project "{project}" (path "{path}" (reference "{ref}") (unit {unit})))'
        for project, path, ref in placements
    )
    token = f'(uuid "{raw}") (property "Reference" "{raw}")'
    annotation = f' (instances {entries})' + (' (dnp yes)' if dnp else '')
    assert token.encode() in schematic
    return schematic.replace(token.encode(), (token + annotation).encode(), 1)


def sheet(uuid, filename):
    return (
        f' (sheet (at 0 0) (size 20 20) (uuid "{uuid}")'
        f' (property "Sheetname" "{uuid}") (property "Sheetfile" "{filename}"))'
    ).encode()


def add_sheets(schematic, *sheets):
    return schematic[:-1] + b"".join(sheets) + b")"


def assembly(files):
    findings, _ = analyze(files)
    return [f["summary"] for f in findings if f["rule_id"] == "electrical.assembly"]


def test_crkbd_template_refs_resolve_for_both_variants():
    files = {}
    for side, raw in (("left", "C?"), ("right", "R?")):
        leaf = design([resistor(raw, "1k", (0, 0), (5, 0))])
        files[f"pcbs/common/{side}.kicad_sch"] = annotate(leaf, raw, [
            ("cherry", f"/cherry/{side}", raw[0] + "11"),
            ("chocolate", f"/chocolate/{side}", raw[0] + "21"),
        ])
    for variant, number in (("cherry", "11"), ("chocolate", "21")):
        prefix = f"pcbs/{variant}"
        root = design([]).replace(b'(uuid "root")', f'(uuid "{variant}")'.encode())
        files[prefix + ".kicad_sch"] = add_sheets(
            root, *(sheet(side, f"common/{side}.kicad_sch") for side in ("left", "right"))
        )
        files[prefix + ".kicad_pcb"] = board(["C" + number, "R" + number])
    assert assembly(files) == []


@pytest.mark.parametrize("revision", ["M", "M1", "M2"])
def test_olimex_shared_sheet_resolves_c29_and_r23(revision):
    components = [device("C36", name="~", kind="passive")]
    board_refs = ["C29"]
    if revision == "M2":
        components.append(resistor("R36", "1k", (5, 0), (10, 0)))
        board_refs.append("R23")
    path = f"/{revision}/placement/control"
    part = annotate(design(components), "C36", [
        ("RP2350pc", "/other/placement/control", "C36"),
        (revision, path, "C29"),
    ], dnp=True)
    if revision == "M2":
        part = annotate(part, "R36", [(revision, path, "R23")])
    root = design([]).replace(b'(uuid "root")', f'(uuid "{revision}")'.encode())
    assert assembly({
        "board.kicad_sch": add_sheets(root, sheet("placement", "child.kicad_sch")),
        "child.kicad_sch": add_sheets(design([]), sheet("control", "control.kicad_sch")),
        "control.kicad_sch": part,
        "board.kicad_pcb": board(board_refs),
    }) == []


def test_webcam_io0_io1_desync_stays_visible():
    schematic = annotate(design([device("IO0", name="~", kind="passive")]),
                         "IO0", [("webcam", "/root", "IO0")])
    missing, orphan = assembly({"board.kicad_sch": schematic, "board.kicad_pcb": board(["IO1"])})
    assert "IO0:" in missing and "has no footprint" in missing
    assert "IO1:" in orphan and "no symbol" in orphan


@pytest.mark.parametrize("variant", ["clean", "routing", "broken"])
def test_phase2_instance_annotations_preserve_inventory(variant):
    directory = Path(__file__).parent / "fixtures" / "phase2" / variant
    files = {path.name: path.read_bytes() for path in directory.glob("board.kicad_*")}
    original = assembly(files)
    assert [row.split(":", 1)[0] for row in original] == ["TP1", "TP2"]
    assert all("no symbol" in row for row in original)
    # Distinguish the instance annotation from the matching raw fixture reference.
    schematic = files["board.kicad_sch"]
    raw_ref = b'(property "Reference" "U1"'
    assert raw_ref in schematic
    files["board.kicad_sch"] = schematic.replace(raw_ref, b'(property "Reference" "U?"')
    assert assembly(files) == original


@pytest.mark.parametrize("case", ["no-instances", "different-placement", "no-root-uuid"])
def test_missing_placement_keeps_raw_reference(case):
    schematic = design([device("U81")])
    if case != "no-instances":
        path = "/other-root" if case == "different-placement" else "/root"
        schematic = annotate(schematic, "U81", [("other", path, "U99")])
    if case == "no-root-uuid":
        schematic = schematic.replace(b'(uuid "root")', b"")
        assert parse_schematic(schematic).uuid is None
    assert assembly({"board.kicad_sch": schematic, "board.kicad_pcb": board(["U81"])}) == []


def test_multi_unit_pins_use_the_resolved_reference_and_placed_unit():
    schematic = design([device("U?"), device("U88", name="OUT", kind="output")])
    schematic = schematic.replace(b'"X_1_1"', b'"U?_1_1"', 1)
    pin = b'(pin input line (at 0 0 0) (length 2.54) (name "SCL") (number "1"))'
    unit_two = pin.replace(b'"SCL"', b'"EN"').replace(b'(number "1")', b'(number "2")')
    schematic = schematic.replace(pin, pin + b') (symbol "U?_2_1" ' + unit_two, 1)
    # Both placements use the same library symbol, with different units.
    schematic = schematic.replace(b'(lib_id "Generic:U88") (at 0 0 0) (unit 1)',
                                  b'(lib_id "Generic:U?") (at 5 0 0) (unit 2)')
    schematic = annotate(schematic, "U?", [("board", "/root", "U1")])
    schematic = annotate(schematic, "U88", [("board", "/root", "U1")], unit=2)
    files = {"board.kicad_sch": schematic, "board.kicad_pcb": board(["U1"])}
    graph = build(files, {"board.kicad_sch": "/root"})
    assert [(p.reference, [(pin.reference, pin.number) for pin in p.pins])
            for p in graph.parts] == [("U1", [("U1", "1")]), ("U1", [("U1", "2")])]
    assert assembly(files) == []


def test_repeated_sheet_remains_excluded_with_reverse_check_gated():
    child = annotate(design([device("U?")]), "U?", [
        ("board", "/root/first", "U1"),
        ("board", "/root/second", "U2"),
    ])
    files = {
        "board.kicad_sch": add_sheets(design([device("U3")]),
                                      sheet("first", "common.kicad_sch"),
                                      sheet("second", "common.kicad_sch")),
        "common.kicad_sch": child,
        "board.kicad_pcb": board(["U2", "U3"]),
    }
    assert assembly(files) == []
    _, coverage = analyze(files)
    assert any(path == "common.kicad_sch" and "repeated sheet instances" in detail
               for path, _, detail in coverage)


def test_placeholder_refs_are_skipped_with_one_coverage_entry():
    files = {
        "board.kicad_sch": design([device("U1")]),
        "board.kicad_pcb": board(["R**1", "REF**", "REF**"]),
    }
    findings, coverage = analyze(files)
    summaries = [f["summary"] for f in findings if f["rule_id"] == "electrical.assembly"]
    assert len(summaries) == 1
    assert summaries[0].startswith("U1:") and "has no footprint" in summaries[0]
    assert [entry for entry in coverage if entry[2].startswith("Skipped ")] == [(
        "board.kicad_pcb",
        "assembly",
        "Skipped 2 placeholder footprint(s) (R**1, REF**): un-annotated, no schematic symbol expected.",
    )]


@pytest.mark.parametrize("ref", ["locked", "H1", "123"])
def test_pcb_only_refs_without_placeholder_marker_still_flag(ref):
    pcb = board(["U1", ref])
    if ref == "H1":
        pcb = pcb.replace(b'"Test:Part"', b'"MountingHole:MountingHole_4.3x6.2mm"')
    expected_ref = ref
    if ref == "locked":
        # The parser skips the locked modifier.
        pcb = pcb.replace(b'(property "Reference" "locked")',
                          b'(fp_text reference locked "U2" (at 0 0) (layer "F.SilkS"))')
        expected_ref = "U2"
    summaries = assembly({"board.kicad_sch": design([device("U1")]), "board.kicad_pcb": pcb})
    assert len(summaries) == 1
    assert summaries[0].startswith(f"{expected_ref}:") and "no symbol" in summaries[0]


def test_astra_placeholder_skip_preserves_all_deletion_warnings():
    refs = ["SW1", "SW3", "SW6", "R36", "R37", "R38", "C32", "C33", "C34", "U13", "UE1"]
    schematic = design([device("U1"), *(device(ref) for ref in refs)])
    summaries = assembly({"board.kicad_sch": schematic, "board.kicad_pcb": board(["U1", "REF**"])})
    assert sorted(summaries) == sorted(
        f"{ref}: is in the schematic and marked for BOM inclusion but has no footprint on the paired board — "
        "bus peripheral cannot be assembled, so its circuit function is absent. "
        "Restore the footprint or reconcile the schematic and assembly intent."
        for ref in refs
    )
