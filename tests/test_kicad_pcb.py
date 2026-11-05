import pytest

from extrude.parse.kicad_pcb import BoardParseError, compare_boards, parse_board


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
