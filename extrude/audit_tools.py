"""Bounded, isolated open-source audit ingredients; upstream verdicts are discarded."""
import json
from pathlib import Path
import shutil
import subprocess
import time
from collections import Counter

from extrude import kicad_audit
from extrude.design_rules import board_facts

MAX_OUTPUT = 8 * 1024 * 1024
COMMANDS = {'audit': ['audit'], 'check': ['check'], 'detect-mistakes': ['detect-mistakes']}


def run_board(board: Path, scratch: Path, seconds=90):
    """Each failed command is not checked; later independent commands still run."""
    result = {}
    deadline = time.monotonic() + seconds
    for name, command in COMMANDS.items():
        binary = shutil.which('kct')
        if not binary or time.monotonic() >= deadline:
            result[name] = dict(status='not checked', detail='Tool unavailable or audit budget exhausted')
            continue
        output, error = scratch / (name + '.json'), scratch / (name + '.log')
        try:
            with output.open('wb') as out, error.open('wb') as err:
                proc = subprocess.run([binary, *command, str(board), '--format', 'json'],
                    cwd=board.parent, env=kicad_audit._environment(binary, scratch),
                    stdout=out, stderr=err, timeout=max(.1, min(35, deadline-time.monotonic())))
            if output.stat().st_size > MAX_OUTPUT or proc.returncode not in {0,1,2}:
                raise ValueError('Invalid output size or tool exit')
            report = json.loads(output.read_text())
            if not isinstance(report, dict):
                raise ValueError('Invalid report')
            # Upstream audit encodes a custom-pad crash inside otherwise valid JSON.
            details = json.dumps(report)
            if 'Unsupported routing geometry' in details or 'DRC could not run' in details:
                result[name] = dict(status='not checked', detail='Custom-pad DRC unsupported; remaining layers continue', report=report)
            else:
                result[name] = dict(status='ran', exit_code=proc.returncode, report=report)
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            result[name] = dict(status='not checked', detail=type(exc).__name__ + ': tool failed or timed out')
    # PCB inspector is layout only. Do not invoke vision or use its health score.
    binary = shutil.which('pcb-inspector')
    if not binary or time.monotonic() >= deadline:
        result['pcb-inspector'] = dict(status='not checked', detail='Unavailable or budget exhausted; vision disabled')
    else:
        output = scratch / 'pcb-inspector.json'
        try:
            with (scratch / 'pcb-inspector.log').open('wb') as log:
                proc = subprocess.run([binary, 'check', str(board), '-o', str(output), '-f', 'json', '--no-vision'],
                    cwd=board.parent, env=kicad_audit._environment(binary, scratch),
                    stdout=log, stderr=log, timeout=max(.1,min(25, deadline-time.monotonic())))
            if proc.returncode not in {0,1} or not output.is_file() or output.stat().st_size > MAX_OUTPUT:
                raise ValueError('No valid report')
            result['pcb-inspector'] = dict(status='ran', report=json.loads(output.read_text()))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            result['pcb-inspector'] = dict(status='not checked', detail='Layout tool failed or timed out; vision disabled')
    return result


def _objects(value):
    return [row for row in value if isinstance(row,dict)] if isinstance(value,list) else []


def triage(reports, text):
    """Named candidates only. Never forward ready/health/pass/no-action verdicts."""
    parts = {c.ref:c for c in board_facts(text)}
    findings, counts = [], Counter()
    check = reports.get('check', {})
    if check.get('status') == 'ran':
        for row in _objects(check['report'].get('findings')):
            rule = row.get('rule_id', '')
            if not isinstance(rule,str):
                continue
            if rule == 'single_pad_net':
                counts['single_pad_net suppressed; use Extrude pin-function checks'] += 1
                continue
            if any(token in rule for token in ('silk', 'text_height', 'text_thickness')):
                counts['silkscreen advisory'] += 1
                continue
            refs = [r for r in (row.get('refs') or []) if isinstance(r,str) and r in parts and not mechanical(parts[r])]
            if not refs:
                counts['unlocated candidates not surfaced'] += 1
                continue
            # A candidate is not an electrical verdict; retain part/value/line.
            evidence = [dict(part=r, line=parts[r].line, value=parts[r].value,
                             pins=row.get('pads', []), nets=row.get('nets', [])) for r in refs]
            findings.append(dict(rule='kct.'+rule, severity='warning', summary=row.get('message','Layout candidate'),
                evidence=evidence, consequence='Manufacturing/layout candidate; requires review against the board rules.',
                next_action='Inspect the named items and run native KiCad DRC; this candidate is not a pass/fail verdict.'))
    audit = reports.get('audit', {})
    if audit.get('status') == 'ran':
        sync = audit['report'].get('sync', {})
        sync = sync if isinstance(sync,dict) else {}
        for key in ('schematic_only_refs', 'pcb_only_refs'):
            refs = [r for r in (sync.get(key) or []) if isinstance(r,str) and not re_mechanical_ref(r) and not (r in parts and mechanical(parts[r]))]
            counts['sync candidates requiring schematic evidence'] += len(refs)
    inspector = reports.get('pcb-inspector', {})
    if inspector.get('status') == 'ran':
        from kicad_tools.sexp import parse_string
        from extrude.parse.kicad_pcb import _rows, _PARSE_LOCK
        with _PARSE_LOCK:
            root = parse_string(text)
        if not list(_rows(root, 'zone')):
            for row in _objects(inspector['report'].get('findings')):
                if row.get('rule_id') != 'HEUR-GND-001':
                    continue
                findings.append(dict(rule='layout.ground_plane',severity='warning',
                    summary='No top-level copper zone is present in the board file.',
                    evidence=[dict(line=1,part='board',pin=None,net=None,value='0 copper zones')],
                    consequence='Return paths rely on tracks; review power and signal integrity.',
                    next_action='Review the ground return and add an appropriate plane; this is a layout signal, not a verdict.'))
    # Decoupling and health-score heuristics are never promoted.
    return findings, dict(counts)


def re_mechanical_ref(ref):
    import re
    return bool(re.fullmatch(r'H\d+|REF\*\*|\d+|', ref))


def mechanical(part):
    return re_mechanical_ref(part.ref) or 'mountinghole' in (part.library+part.value).lower()
