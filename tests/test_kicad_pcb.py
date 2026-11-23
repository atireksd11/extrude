import pytest

from extrude.parse.kicad_pcb import BoardParseError, compare_boards, parse_board


@pytest.mark.parametrize(("rows", "reference", "value"), [
    (b'(fp_text reference locked "U2") (fp_text value locked "ProMicro")', "U2", "ProMicro"),
    (b'(fp_text reference "U3")', "U3", None),
    (b'(fp_text reference locked "U2") (property "Reference" "U4")', "U4", None),
    (b'(fp_text user locked "GND")', None, None),
    (b'(fp_text reference locked)', None, None),
    (b'(fp_text reference "LOCKED1")', "LOCKED1", None),
])
def test_legacy_footprint_text(rows, reference, value):
    board = parse_board(
        b'(kicad_pcb (version 20221018) (footprint "Test:A" (at 1 2) (layer "F.Cu") '
        + rows + b'))'
    )
    footprint, = board.footprints
    assert footprint.reference == reference
    assert dict(footprint.properties).get("Value") == value


def test_legacy_net_codes_and_named_nets_compare_as_the_same_wiring():
    old = parse_board(b'''(kicad_pcb (version 20221018) (net 5 "GND")
       (module "Test:A" (at 1 2 -90) (layer "F.Cu") (fp_text reference "J1")
         (pad "1" smd rect (net 5)) (pad "1" smd rect (net 5))))''')
    renumbered = parse_board(b'''(kicad_pcb (version 20241229) (net 7 "GND")
       (footprint "Test:A" (at 1 2 270) (layer "F.Cu") (property "Reference" "J1")
         (pad "1" smd rect (net 7 "GND")) (pad "1" smd rect (net 7 "GND"))))''')
    named = parse_board(b'''(kicad_pcb (version 20251028)
       (footprint "Test:A" (at 1 2 270) (layer "F.Cu") (property "Reference" "J1")
         (pad "1" smd rect (net "GND")) (pad "1" smd rect (net "GND"))))''')
    assert compare_boards(old, renumbered) == compare_boards(renumbered, named) == []
    assert named.footprints[0].pads == {"1": ("GND", "GND")}


def test_existing_pad_that_loses_its_net_is_flagged_for_review():
    source = b'''(kicad_pcb (version 20251028)
      (footprint "Test:A" (at 1 2) (layer "F.Cu") (property "Reference" "J1")
        (pad "1" smd rect (net "GND"))))'''
    old = parse_board(source)
    new = parse_board(source.replace(b' (net "GND")', b""))
    assert compare_boards(old, new) == [
        {"kind": "pad_disconnected", "reference": "J1", "pad": "1", "before": ("GND",), "after": (None,)}
    ]


@pytest.mark.parametrize("data", [
    b"(kicad_pcb (version 20241229)",
    b"(kicad_sch (version 20241229))",
    b"version https://git-lfs.github.com/spec/v1\n",
    b'(kicad_pcb (version 20241229) (footprint "A" (at 1 2) (layer "F.Cu") (pad "1" smd rect (net 99))))',
])
def test_unreadable_boards_do_not_produce_empty_comparisons(data):
    with pytest.raises(BoardParseError):
        parse_board(data)


def test_unnumbered_pads_keep_types_and_nets_without_affecting_comparison():
    source = b'''(kicad_pcb (version 20241229) (net 1 "GND")
       (footprint "Test:A" (at 1 2) (layer "F.Cu") (property "Reference" "J1")
         (pad "1" smd rect (net 1 "GND")) (pad "0" thru_hole oval (net 1))))'''
    extra = (
        b' (pad "" thru_hole oval) (pad "" np_thru_hole circle)'
        b' (pad "" smd rect (net 1))'
    )
    original = parse_board(source)
    board = parse_board(source[:-2] + extra + source[-2:])
    footprint, = board.footprints
    assert footprint.pads == {"1": ("GND",), "0": ("GND",)}
    assert [(pad.type, pad.net) for pad in footprint.unnumbered_pads] == [
        ("thru_hole", None), ("np_thru_hole", None), ("smd", "GND"),
    ]
    assert compare_boards(original, board) == []
