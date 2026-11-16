"""PCB streaming, resource limits, and compatibility with the pre-M1 walk."""
import gc
import json
import os
from pathlib import Path
import subprocess
import sys
from dataclasses import asdict

import pytest

from extrude.parse import kicad_pcb as pcb
from extrude import electrical_reasoning as electrical
from test_electrical_robustness import saved_repo, good_design, assert_good
from test_trust_blockers import board

pytestmark = pytest.mark.atlas
MIB = 1024 * 1024


def old_board(data):
    """Frozen PR #12 whole-tree walk; shared extractors are deliberately unchanged."""
    root = pcb.parse_string(data.decode('utf-8-sig', errors='replace'))
    version = pcb._field(root, 'version')
    nets = {}
    for row in pcb._rows(root, 'net'):
        code, value = row.values
        nets[code] = pcb._atom(value)
    return pcb.Board(version[0], tuple(pcb._footprint(row, nets) for row in root.children
                                      if row.name in {'footprint', 'module'}))


def encoded(value):
    return json.dumps(asdict(value), sort_keys=True, separators=(',', ':')).encode()


@pytest.mark.parametrize('source', [
    b'(kicad_pcb (version 20241229))',
    board(['U81']),
    b'''(kicad_pcb (version 20241229)
      (module "Test:A" (at 1 2 -90) (layer "B.Cu") (fp_text reference "J1")
        (property "Value" "CONN (2x4) \\\"quoted\\\" \\\\tail")
        (pad "1" smd rect (net 9)) (pad "2" smd rect (net 0 "")))
      (net 9 "GND") (net 0 ""))''',
    b'(kicad_pcb (version 20241229) (footprint "Test:Empty" (at 0 0) (layer "F.Cu")))',
])
def test_old_new_board_bytes_and_comparison(source):
    other = source.replace(b'(at 1 2 -90)', b'(at 4 5 30)').replace(b'U81', b'U82')
    assert encoded(old_board(source)) == encoded(pcb.parse_board(source))
    assert pcb.compare_boards(old_board(source), old_board(other)) == pcb.compare_boards(
        pcb.parse_board(source), pcb.parse_board(other))


@pytest.mark.parametrize('data', [
    b'', b'(other (version 1))', b'(kicad_pcb)', b'(kicad_pcb (version "bad"))',
    b'(kicad_pcb (version 1) (net 1 "A") (net 1 "B"))',
    b'(kicad_pcb (version 1) (segment (start 0 0))',
    b'(kicad_pcb (version 1)) trailing', b'(kicad_pcb ; comment\n(version 1))',
    b'(kicad_pcb (version 1) (segment "unterminated))',
])
def test_malformed_board_is_per_file(saved_repo, data):
    with pytest.raises(pcb.BoardParseError):
        pcb.parse_board(data)
    sha = saved_repo({**good_design(), **good_design('bad'), 'bad.kicad_pcb': data})
    findings, coverage = electrical.collect('local', sha)
    assert_good(findings)
    assert any(r['path'] == 'bad.kicad_pcb' and r['detail'].startswith('Not checked:')
               for r in coverage)


def test_unused_geometry_is_not_parsed_and_gc_restored(monkeypatch):
    original = pcb.parse_string
    calls = []
    def paused(text):
        calls.append(text)
        assert gc.isenabled()
        node = original(text)
        gc.disable()  # Also defend against upstream leaving GC paused.
        return node
    monkeypatch.setattr(pcb, 'parse_string', paused)
    try:
        pcb.parse_board(board(['U81']).replace(b'(version', b'(segment (start 0 0)) (version'))
        assert gc.isenabled()
        assert all(not x.startswith('(segment') for x in calls)
        assert len(calls) == 2
    finally:
        gc.enable()


def test_gc_restored_after_failed_form(monkeypatch):
    def broken(_):
        gc.disable()
        raise ValueError('bad parser')
    monkeypatch.setattr(pcb, 'parse_string', broken)
    try:
        with pytest.raises(pcb.BoardParseError):
            pcb.parse_board(board([]))
        assert gc.isenabled()
    finally:
        gc.enable()


@pytest.mark.parametrize('size', [10 * MIB, 32 * MIB])
def test_large_pcb_parses_under_memory_gate(saved_repo, tmp_path, size):
    raw = Path('tests/fixtures/phase2/clean/board.kicad_pcb').read_bytes()
    padded = raw + b' ' * (size - len(raw))
    target = tmp_path / 'large.kicad_pcb'
    target.write_bytes(padded)
    script = '''import resource, sys
from extrude.parse.kicad_pcb import parse_board
b = parse_board(open(sys.argv[1], 'rb').read())
print(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
'''
    result = subprocess.check_output([sys.executable, '-c', script, str(target)], text=True)
    # Linux reports KiB. macOS reports bytes.
    peak_bytes = int(result) * (1 if sys.platform == 'darwin' else 1024)
    assert peak_bytes < 256_000_000
    sha = saved_repo({**good_design(), **good_design('large'), 'large.kicad_pcb': padded})
    findings, coverage = electrical.collect('local', sha)
    assert_good(findings)
    assert any(r['path'] == 'large.kicad_pcb' and r['check'] == 'Electrical assembly'
               and r['outcome'] == 'ran' for r in coverage)
    assert not any(r['path'] == 'large.kicad_pcb' and r['detail'].startswith('Not checked:')
                   for r in coverage)


@pytest.mark.parametrize('form', [b'(footprint "', b'(segment "'])
def test_single_form_guard_degrades_without_losing_peers(saved_repo, form):
    raw = b'(kicad_pcb (version 20241229) ' + form + b'x' * (8 * MIB) + b'"))'
    with pytest.raises(pcb.BoardParseError, match='form exceeds the 8 MiB'):
        pcb.parse_board(raw)
    sha = saved_repo({**good_design(), **good_design('bad'), 'bad.kicad_pcb': raw})
    findings, coverage = electrical.collect('local', sha)
    assert_good(findings)
    assert any(r['path'] == 'bad.kicad_pcb' and 'form exceeds' in r['detail'] for r in coverage)


def test_schematic_blob_limit_stays_eight_mib(saved_repo):
    sha = saved_repo({**good_design(), 'large.kicad_sch': b' ' * (9 * MIB)})
    findings, coverage = electrical.collect('local', sha)
    assert_good(findings)
    assert any(r['path'] == 'large.kicad_sch' and '8 MiB' in r['detail'] for r in coverage)


def test_external_pinned_corpus_equivalence():
    """Opt in with a JSON list of local PCB paths from the seven pinned repos."""
    manifest = os.environ.get('EXTRUDE_PCB_EQUIVALENCE_MANIFEST')
    if not manifest:
        pytest.skip('set EXTRUDE_PCB_EQUIVALENCE_MANIFEST for pinned Deep Test 3 corpus')
    entries = json.loads(Path(manifest).read_text())
    assert entries
    for path in entries:
        data = Path(path).read_bytes()
        assert len(data) <= 8 * MIB
        assert encoded(old_board(data)) == encoded(pcb.parse_board(data)), path
