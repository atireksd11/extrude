"""Evidence-only whole-revision rules. No source execution or routing claims.

PCB net membership proves logical assignments, not routed copper continuity.
Part-specific semantics are intentionally restricted to identified components.
"""
from dataclasses import dataclass
import re
from pathlib import PurePosixPath

from kicad_tools.sexp import parse_string
from extrude import github_history as git
from extrude.parse.kicad_pcb import (_PARSE_LOCK, _rows, _field, _reference,
    _string_field, _net, parse_board, MAX_BOARD_BYTES)
from extrude.parse.workspace_firmware import _mask, read_constants, MAX_SOURCE_BYTES
from extrude.workspace_checks import evidence

VERSION = 1
SOURCE = {'.ino', '.c', '.cpp', '.h', '.hpp', '.py', '.yaml', '.yml'}


@dataclass(frozen=True)
class Pad:
    ref: str
    part: str
    number: str
    function: str
    net: str | None
    line: int
    footprint: str = ""


def blocks(text):
    """Balanced expressions with original offsets, respecting escaped strings."""
    stack = []
    for m in re.finditer(r'"(?:\\.|[^"\\])*"|[()]', text):
        if m[0] == '(':
            stack.append(m.start())
        elif m[0] == ')':
            if not stack:
                raise ValueError('Unbalanced PCB syntax')
            start = stack.pop()
            yield start, text[start:m.end()]
    if stack:
        raise ValueError('Unbalanced PCB syntax')


def board_pads(data):
    parse_board(data)  # shared bounded syntax/net validation
    text = data.decode('utf-8-sig')
    with _PARSE_LOCK:
        root = parse_string(text)
    nets = {int(n.values[0]): str(n.values[1]) for n in _rows(root, 'net')}
    spans = list(blocks(text))
    footprints = sorted((s, b) for s, b in spans if re.match(r'\((footprint|module)\s', b))
    result = []
    for start, block in footprints:
        with _PARSE_LOCK:
            node = parse_string(block)
        ref = _reference(node)
        if not ref:
            continue
        props = {str(p.values[0]): str(p.values[1]) for p in _rows(node, 'property') if len(p.values) >= 2}
        value = props.get('Value') or next((str(p.values[1]) for p in _rows(node, 'fp_text') if len(p.values) >= 2 and p.values[0] == 'value'), '')
        for offset, raw in sorted(blocks(block)):
            if not re.match(r'\(pad\s', raw):
                continue
            with _PARSE_LOCK:
                pad = parse_string(raw)
            if not str(pad.values[0]):
                continue
            result.append(Pad(ref, value, str(pad.values[0]), _string_field(pad, 'pinfunction') or '',
                              _net(pad, nets), text.count('\n', 0, start + offset) + 1, str(node.values[0])))
    unique = {}
    for p in result:
        key = p.ref, p.number
        if key in unique and (unique[key].net, unique[key].function) != (p.net, p.function):
            raise ValueError('Repeated physical pads: part/pin assignment is ambiguous')
        unique.setdefault(key, p)
    return list(unique.values())


def floating(p, pads):
    return not p.net or p.net.lower().startswith('unconnected-') or sum(q.net == p.net for q in pads) == 1


def analyze(files, repo='local', sha='local'):
    """Analyze bounded path->bytes inputs; return workspace Finding/Coverage rows."""
    findings, coverage = [], []
    def cover(path, detail, ran=False):
        coverage.append(dict(path=path, domain='project', check='Whole-design electrical rules', tool='Extrude rules',
                             outcome='ran' if ran else 'unavailable', detail=detail if ran else 'not checked: ' + detail))
    def ev(path, locator):
        return evidence(repo, sha, path, locator)
    def pe(path, p):
        return ev(path, f'line {p.line}: {p.ref} {p.part}, pin {p.number} {p.function}, net={p.net!r}')
    def emit(rule, text, proofs, severity='error', verified=True):
        findings.append(dict(rule_id='design.' + rule, domain='electrical', status='verified' if verified else 'unverified',
                             severity=severity, summary=text, lifecycle='present_at_head', evidence=proofs))
    sources = {}
    for path, data in files.items():
        suffix = PurePosixPath(path).suffix.lower()
        if suffix in SOURCE:
            try:
                if len(data) > MAX_SOURCE_BYTES:
                    raise ValueError('source exceeds 512 KiB')
                text = data.decode('utf-8-sig')
                if suffix not in {'.ino', '.c', '.cpp', '.h', '.hpp'}:
                    cover(path, 'firmware language/peripheral semantics unsupported; no verdict')
                    continue
                sources[path] = (text, _mask(text), read_constants(data, path))
                cover(path, 'Literal C/C++/Arduino I2S and INA3221 patterns inspected; other firmware behavior not checked.', True)
            except (ValueError, UnicodeError) as exc:
                cover(path, str(exc))
        elif suffix in {'.sch', '.kicad_sch'}:
            cover(path, 'schematic electrical solving belongs to native ERC; these rules use PCB pad/net assignments')
    for path, data in files.items():
        if not path.lower().endswith('.kicad_pcb'):
            continue
        try:
            pads = board_pads(data)
        except (ValueError, TypeError, IndexError, RecursionError) as exc:
            cover(path, str(exc))
            continue
        if not pads:
            cover(path, 'unverified: empty PCB/netlist; no electrical evidence')
            continue
        cover(path, 'Logical PCB pin/net rules inspected. Copper continuity, analog margins, and all rules not named here are not checked.', True)
        parts = {}
        for p in pads:
            parts.setdefault(p.ref, []).append(p)
        # Associate firmware only when a single MCU and single PCB provide a
        # unique hardware target. Multi-board firmware mappings require setup.
        mcus = {p.ref for p in pads if re.fullmatch(r'ESP32-WROOM-32(?:UE|E)?', p.part, re.I)}
        single_board = sum(p.lower().endswith('.kicad_pcb') for p in files) == 1
        ground_nets = {p.net for p in pads if p.net and re.fullmatch(r'(?:A|D)?GND(?:_\d+)?', p.function)}
        adc = {p.ref for p in pads if p.part.upper() in {'PCM1808', 'PCM1808PWR'}}
        for ref in sorted(adc):
            group = parts[ref]
            by_number = {p.number: p for p in group}
            for number, name, next_step in [('6', 'SCKI', 'route a valid system clock'), ('1', 'VREF', 'connect the reference bypass capacitor to AGND per the PCM1808 datasheet')]:
                p = by_number.get(number)
                if p and p.function.split('_')[0] == name and floating(p, pads):
                    emit('critical_pin', f'BUG: {ref} PCM1808 pin {number} {name} has no connected peer. Conversion cannot be relied on; {next_step}.', [pe(path, p)])
            if not single_board or len(mcus) != 1 or len(adc) != 1:
                cover(path, f'{ref}: firmware-to-I2S mapping ambiguous (requires one board, MCU and PCM1808)')
                continue
            mcu = next(iter(mcus))
            for source, (original, code, constants) in sources.items():
                assignments = {}
                for field in ('ws_io_num', 'bck_io_num', 'data_in_num'):
                    matches = list(re.finditer(r'\.' + field + r'\s*=\s*(\d+)\s*[,}]', code))
                    if len(matches) == 1 and not re.search(r'^\s*#\s*(?:if|else|elif)', code, re.M):
                        m = matches[0]
                        assignments[field] = (int(m[1]), ev(source, f'line {code.count(chr(10), 0, m.start()) + 1}: {original.splitlines()[code.count(chr(10), 0, m.start())].strip()}'))
                for field, number in [('ws_io_num', '7'), ('bck_io_num', '8'), ('data_in_num', '9')]:
                    p = by_number.get(number)
                    if not p or field not in assignments or floating(p, pads):
                        continue
                    targets = [q for q in parts[mcu] if q.net == p.net and re.fullmatch(r'IO\d+(?:_\d+)?', q.function)]
                    if len(targets) != 1:
                        cover(source, f'{field}: no unique MCU pin on {ref} pin {number}')
                        continue
                    q = targets[0]
                    actual = int(re.match(r'IO(\d+)', q.function)[1])
                    value, proof = assignments[field]
                    if value != actual:
                        invalid = ' GPIO28 does not exist on ESP32-WROOM-32UE.' if value == 28 and q.part.upper() == 'ESP32-WROOM-32UE' else ''
                        emit('firmware_pin', f'BUG: {source} {field}={value}, but {ref} pin {number} {p.function} is assigned to {mcu} {q.function}.{invalid} Audio pin selection is wrong; set {field}={actual} to match this PCB.', [proof, pe(path,p), pe(path,q)])
                mode = list(re.finditer(r'\.mode\s*=\s*([^,;]+)', code))
                md = [by_number.get(n) for n in ('10','11')]
                if (len(mode) == 1 and 'I2S_MODE_SLAVE' in mode[0][1] and 'I2S_MODE_MASTER' not in mode[0][1]
                        and all(p and p.function.split('_')[0] in {'MD0','MD1'} and p.net in ground_nets for p in md)
                        and assignments and not re.search(r'^\s*#\s*(?:if|else|elif)', code, re.M)):
                    lineno = code.count('\n', 0, mode[0].start()) + 1
                    emit('clock_master', f'BUG: {ref} PCM1808 MD0/MD1 are grounded (slave mode), and {source} selects I2S_MODE_SLAVE. Neither endpoint generates BCK/LRCK; choose one clock master, route SCKI and align firmware before ordering.', [pe(path,p) for p in md] + [ev(source, f'line {lineno}: {original.splitlines()[lineno-1].strip()}')])
        for ref, group in parts.items():
            if not group or group[0].part.upper() != 'INA3221':
                continue
            channels = {n for n in (1,2,3) if all(any(p.function.split('_')[0] == f'IN{sign}{n}' and not floating(p,pads) for p in group) for sign in ('+','-'))}
            for source, (original, code, constants) in sources.items():
                calls = list(re.finditer(r'\b(\w+)\.get(?:CurrentAmps|BusVoltage|ShuntVoltage)\s*\(\s*(\w+)\s*\)', code))
                values = [constants.get(m[2], {}).get('value') if not m[2].isdigit() else int(m[2]) for m in calls]
                if single_board and channels == {1,2,3} and calls and len(calls) == len(re.findall(r'get(?:CurrentAmps|BusVoltage|ShuntVoltage)\s*\(',code)) and len(re.findall(r'Adafruit_INA3221\s+\w+\s*;',code)) == 1 and set(values) == {0} and not re.search(r'get(?:CurrentAmps|BusVoltage|ShuntVoltage)\s*\([^)]*[, +*-]',code):
                    proof = [ev(source, f"line {code.count(chr(10),0,m.start())+1}: {m[0]}") for m in calls]
                    emit('unused_channels', f'BUG: {ref} INA3221 has IN+/IN- nets wired for channels 1, 2 and 3, but the recognized firmware reads select only channel 1 (index 0). CH2/CH3 measurements are absent; read and calibrate each intended channel, including its actual shunt resistance. Other dynamic/library behavior is not checked.', [pe(path,p) for p in group if p.function.startswith('IN')] + proof)
        for p in pads:
            peers = [q for q in pads if q.net and q.net == p.net and q.ref != p.ref]
            if p.part.upper().startswith('STM32F4') and (p.function == 'NRST' or (not p.function and p.net == 'NRST' and p.number == '7' and p.part.upper() == 'STM32F405RGT6')):
                if not any(q.ref.startswith(('R','C')) for q in peers):
                    emit('reset_bias', f'WEAKNESS: {p.ref} {p.part} pin {p.number} NRST has no external resistor or capacitor on its PCB net. Reset noise margin relies on the MCU internal circuit; review an external pull-up/filter against the datasheet.', [pe(path,p)] + [pe(path,q) for q in peers], 'warning')
            if p.part.upper().startswith('ESP32-') and p.function.split('_')[0] == 'IO0':
                if not any(q.ref.startswith('R') for q in peers):
                    emit('boot_bias', f'WEAKNESS: {p.ref} {p.part} pin {p.number} IO0 has no external resistor on its PCB net. Boot selection relies on the internal pull-up; consider an external pull-up for robust booting and verify the boot switch.', [pe(path,p)] + [pe(path,q) for q in peers], 'warning')
        # Critical configuration inputs: do not infer intended addresses/modes.
        for p in pads:
            if p.part.upper() == 'INA3221' and p.function.split('_')[0] == 'A0':
                peers = [q for q in pads if q.net == p.net and q.ref != p.ref]
                jumpers = peers and all('SolderJumper' in q.footprint and '_Open_' in q.footprint for q in peers)
                if p.net not in ground_nets | {'GND','/GND'} and (floating(p,pads) or jumpers):
                    for source, (original, code, constants) in sources.items():
                        addr = constants.get('INA3221_ADDR', {})
                        if single_board and len(re.findall(r'Adafruit_INA3221\s+\w+\s*;',code)) == 1 and addr.get('value') == 0x40 and re.search(r'\.begin\s*\(\s*INA3221_ADDR\s*[,)]',code):
                            emit('address_strap', f'BUG: {p.ref} INA3221 pin {p.number} A0 has no fixed address strap (only open jumpers or no peers), but firmware requests 0x40. The sensor may not respond; bridge the GND address jumper/add a pull-down and verify the address.', [pe(path,p)] + [pe(path,q) for q in peers] + [ev(source,f"line {addr['line']}: INA3221_ADDR=0x40")])
            if p.part.upper() in {'BME680','CJMCU-680'} and p.function.upper() in {'SDO','CS'} and floating(p,pads):
                emit('sensor_mode', f'RISK: {p.ref} {p.part} pin {p.number} {p.function} has no connected peer. Mode/address selection is unresolved on this carrier; check the breakout internal pulls and strap for the intended bus.', [pe(path,p)], 'warning')
            if 'POWERBOOST' in p.part.upper() and p.function.upper() in {'USB','VBUS'} and floating(p,pads):
                emit('charge_input', f'RISK: {p.ref} {p.part} pin {p.number} {p.function} has no connected peer. This carrier supplies no charge input; wire the input if on-board charging is intended, or document external charging.', [pe(path,p)], 'warning')
        if not sources:
            cover(path, 'firmware absent or unsupported; pin mapping and clock-master firmware checks not checked')
    return findings, coverage


def collect(repo, sha):
    files, gaps = {}, []
    inventory = git.inventory(repo, sha, limit=1000)
    for row in inventory['files']:
        path = row['path']
        if PurePosixPath(path).suffix.lower() not in SOURCE | {'.kicad_pcb','.kicad_sch','.sch'}:
            continue
        try:
            blob = git.regular_blob(repo, sha, path, max_bytes=MAX_BOARD_BYTES if path.lower().endswith(('.kicad_pcb','.kicad_sch','.sch')) else MAX_SOURCE_BYTES)
            if blob is None:
                raise ValueError('no regular file at this revision')
            files[path] = blob
        except (ValueError, git.GitHubError) as exc:
            gaps.append(dict(path=path, domain='project', check='Whole-design electrical rules', tool='Extrude rules', outcome='unavailable', detail='not checked: ' + str(exc)))
    if inventory['next_offset'] is not None:
        gaps.append(dict(path='', domain='project', check='Whole-design electrical rules', tool='Extrude rules', outcome='unavailable', detail='not checked: inventory exceeds 1000-file limit'))
    findings, coverage = analyze(files, repo, sha)
    return findings, coverage + gaps


def explain_native(finding):
    """Keep the native verdict/evidence intact; explain only known rule types."""
    rule = finding['rule_id'].split('.')[-1]
    guidance = {
        'solder_mask_bridge': ('Mask openings bridge different nets and can allow solder shorts.', 'Review the named pads and mask rules, repair the footprint, then rerun DRC.'),
        'unconnected_items': ('The named copper items are not connected according to native DRC.', 'Join the named pads/tracks and rerun DRC.'),
        'unconnected_items_violation': ('The named copper items are not connected according to native DRC.', 'Join the named pads/tracks and rerun DRC.'),
        'pin_not_connected': ('The named schematic pin has no connection.', 'Connect it or mark it intentionally no-connect, then rerun ERC.'),
        'pin_not_driven': ('The named input has no driver identified by ERC.', 'Verify its intended source and connect it, then rerun ERC.'),
        'power_pin_not_driven': ('ERC cannot identify a power source for the named pin.', 'Verify the supply connection and power-source annotation, then rerun ERC; this alone does not prove missing physical power.'),
    }
    if rule in guidance:
        why, action = guidance[rule]
        finding = {**finding, 'summary': finding['summary'] + ' ' + why + ' ' + action}
    return finding
