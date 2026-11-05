"""Reproducible native KiCad inputs, deliberately independent of pcbnew Python."""
from pathlib import Path

ROOT = "10000000-0000-4000-8000-000000000000"
SYMBOL = "20000000-0000-4000-8000-000000000000"


def schematic(broken=False):
    return f'''(kicad_sch (version 20250114) (generator "eeschema")
      (uuid {ROOT}) (paper "A4")
      (lib_symbols
        (symbol "Test:Output" (pin_names (offset 0)) (in_bom yes) (on_board yes)
          (property "Reference" "U" (at 0 2 0) (effects (font (size 1 1))))
          (property "Value" "Output" (at 0 -2 0) (effects (font (size 1 1))))
          (symbol "Output_1_1"
            (pin output line (at 0 0 0) (length 2.54)
              (name "OUT" (effects (font (size 1 1))))
              (number "1" (effects (font (size 1 1))))))))
      {'' if broken else '(no_connect (at 50 50) (uuid 30000000-0000-4000-8000-000000000000))'}
      (symbol (lib_id "Test:Output") (at 50 50 0) (unit 1)
        (in_bom yes) (on_board yes) (dnp no) (uuid {SYMBOL})
        (property "Reference" "U1" (at 50 45 0) (effects (font (size 1 1))))
        (property "Value" "Output" (at 50 47 0) (effects (font (size 1 1))))
        (property "Footprint" "Test:Output" (at 50 50 0) (effects (font (size 1 1)) hide))
        (pin "1" (uuid 40000000-0000-4000-8000-000000000000))
        (instances (project "board" (path "/{ROOT}" (reference "U1") (unit 1))))))'''


def board(broken=False, routing=False):
    tracks = '''
      (segment (start 20 20) (end 30 30) (width 0.25) (layer "F.Cu") (net 1)
        (uuid 60000000-0000-4000-8000-000000000001))
      (segment (start 20 30) (end 30 20) (width 0.25) (layer "F.Cu") (net 2)
        (uuid 60000000-0000-4000-8000-000000000002))''' if broken or routing else ''
    return f'''(kicad_pcb (version 20221018) (generator "pcbnew")
      (general (thickness 1.6)) (paper "A4")
      (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))
      (setup (pad_to_mask_clearance 0))
      (net 0 "") (net 1 "A") (net 2 "B") (net 3 "unconnected-(U1-OUT-Pad1)")
      (footprint "Test:Probe" (layer "F.Cu") (at 20 20) (attr smd board_only)
        (uuid 80000000-0000-4000-8000-000000000001)
        (property "Reference" "TP1" (at 0 -2 0) (layer "F.SilkS"))
        (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu" "F.Mask") (net 1 "A")
          (uuid 80000000-0000-4000-8000-000000000011)))
      (footprint "Test:Probe" (layer "F.Cu") (at 20 30) (attr smd board_only)
        (uuid 80000000-0000-4000-8000-000000000002)
        (property "Reference" "TP2" (at 0 -2 0) (layer "F.SilkS"))
        (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu" "F.Mask") (net 2 "B")
          (uuid 80000000-0000-4000-8000-000000000012)))
      (footprint "Test:Output" (layer "F.Cu")
        (uuid 50000000-0000-4000-8000-000000000000) (at 40 40)
        (property "Reference" "U1" (at 0 -3 0) (layer "F.SilkS"))
        (property "Value" "{'Wrong' if broken else 'Output'}" (at 0 3 0) (layer "F.Fab"))
        (path "/{ROOT}/{SYMBOL}") (attr smd)
        (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu" "F.Paste" "F.Mask")
        (net 3 "unconnected-(U1-OUT-Pad1)") (uuid 50000000-0000-4000-8000-000000000001)))
      (gr_rect (start 10 10) (end 60 60) (stroke (width 0.05) (type default))
        (fill none) (layer "Edge.Cuts") (uuid 70000000-0000-4000-8000-000000000000))
      {tracks})'''


if __name__ == "__main__":
    for name in ("clean", "broken", "routing"):
        path = Path(__file__).parent / name
        path.mkdir(exist_ok=True)
        (path / "board.kicad_pcb").write_text(board(broken=name == "broken", routing=name == "routing"))
        (path / "board.kicad_sch").write_text(schematic(broken=name == "broken"))
        (path / "board.kicad_pro").write_text('{}')
