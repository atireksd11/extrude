"""Manual fresh-process memory probe; run from the repository root.

python tests/profile_pcb_memory.py PATH [--whole-tree] [--trace]
--whole-tree reproduces PR #12's valid-board extraction without its 8 MiB guard.
ru_maxrss is inherited; run from a lean parent or switch to VmHWM.
Use an untraced run for the RSS gate; tracemalloc itself increases RSS.
"""
import resource
import sys

sys.path.insert(0, '.')
from extrude.parse import kicad_pcb as pcb

if '--trace' in sys.argv:
    import tracemalloc
    tracemalloc.start()


def report(phase):
    row = {'phase': phase, 'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    if '--trace' in sys.argv:
        row['tracemalloc_current_peak_bytes'] = tracemalloc.get_traced_memory()
    print(row, flush=True)


data = open(sys.argv[1], 'rb').read()
if '--whole-tree' in sys.argv:
    text = data.decode('utf-8-sig', errors='replace')
    report('decode')
    root = pcb.parse_string(text)
    report('parse_string')
    version = pcb._field(root, 'version')
    nets = {}
    for row in pcb._rows(root, 'net'):
        code, value = row.values
        nets[code] = pcb._atom(value)
    board = pcb.Board(version[0], tuple(pcb._footprint(row, nets) for row in root.children
                                       if row.name in {'footprint', 'module'}))
    report('Board-build')
else:
    board = pcb.parse_board(data)
    report('parse_board')
print({'size_bytes': len(data), 'footprints': len(board.footprints)})
