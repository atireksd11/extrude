"""Whole-board electrical candidates from actual pad functions, never net-name NCs.

This is connectivity evidence, not proof of routed copper or datasheet compliance.
No repository code is executed. Unknown functions and operating limits stay unchecked.
"""
from collections import defaultdict
from dataclasses import dataclass
import re

from kicad_tools.sexp import parse_string
from extrude.parse.kicad_pcb import _rows, _reference, _string_field, _net, _PARSE_LOCK


@dataclass
class Pad:
    ref: str
    number: str
    function: str
    kind: str
    net: str | None
    line: int


@dataclass
class Component:
    ref: str
    value: str
    library: str
    pads: list[Pad]
    line: int


def blocks(text):
    """Top-level root children with exact source offsets (quoted parens are inert)."""
    depth = 0
    start = 0
    for token in re.finditer(r'"(?:\\.|[^"\\])*"|[()]', text):
        if token[0] == '(':
            depth += 1
            if depth == 2:
                start = token.start()
        elif token[0] == ')':
            if depth == 2:
                yield start, text[start:token.end()]
            depth -= 1


def board_facts(text):
    if len(text.encode()) > 8 * 1024 * 1024:
        raise ValueError('Board exceeds analysis limit')
    with _PARSE_LOCK:
        root = parse_string(text)
    if root.name != 'kicad_pcb':
        raise ValueError('Expected KiCad PCB')
    nets = {n.values[0]: str(n.values[1]) for n in _rows(root, 'net') if len(n.values) > 1}
    spans = [(pos, src) for pos, src in blocks(text) if re.match(r'\((footprint|module)\s', src)]
    nodes = [n for n in root.children if n.name in {'footprint', 'module'}]
    components = []
    for node, (pos, source) in zip(nodes, spans, strict=True):
        ref = _reference(node) or 'REF**'
        value = next((str(p.values[1]) for p in _rows(node, 'property') if p.values[0] == 'Value'), '')
        value = value or next((str(p.values[1]) for p in _rows(node, 'fp_text') if p.values[0] == 'value'), '')
        line = text.count('\n', 0, pos) + 1
        pads = []
        # Search only this footprint, retaining exact pad-block line evidence.
        cursor = 0
        for p in _rows(node, 'pad'):
            match = re.search(r'\(pad\s+(?:"' + re.escape(str(p.values[0])) + r'"|' + re.escape(str(p.values[0])) + r')(?=\s)', source[cursor:])
            offset = cursor + match.start() if match else 0
            cursor = offset + 4
            number = str(p.values[0])
            if not number:
                continue
            func = _string_field(p, 'pinfunction') or ''
            # KiCad 10 can append physical pad number to function names.
            func = re.sub(r'_' + re.escape(number) + r'$', '', func)
            pads.append(Pad(ref, number, func, _string_field(p, 'pintype') or '', _net(p, nets), line + source.count('\n', 0, offset)))
        components.append(Component(ref, value, str(node.values[0]), pads, line))
    return components


def analyze(text, path, firmware=None):
    parts = board_facts(text)
    findings = []
    netpads = defaultdict(dict)
    for c in parts:
        for p in c.pads:
            if p.net:
                netpads[p.net][(p.ref, p.number)] = p
    def floating(p):
        return not p.net or len(netpads[p.net]) < 2
    def peers(p):
        return list(netpads.get(p.net, {}).values()) if p.net else []
    def supply(net):
        return bool(net and re.fullmatch(r'\+?(?:3[.V]3|3\.3V|5V|VCC|VDD|3V3)', net, re.I))
    def ground(p):
        return any(q.function in {'GND', 'AGND', 'DGND', 'VSS'} for q in peers(p)) or p.net in {'GND','AGND','DGND'}
    def pullup(p):
        return any(c.ref.startswith('R') and any(q.net == p.net for q in c.pads) and any(supply(q.net) for q in c.pads) for c in parts)
    def emit(rule, c, pins, consequence, action, extra=(), severity='warning', measurements=None):
        ev = [dict(path=path, line=p.line, part=c.ref, pin=p.number, function=p.function, net=p.net, value=c.value) for p in pins]
        findings.append(dict(rule=rule, severity=severity, summary=f'{c.ref} {c.value}: {consequence}', consequence=consequence, next_action=action, evidence=ev + list(extra), measurements=measurements or {}))
    # Comments cannot become firmware evidence. Preserve newlines/source lines.
    sources = {}
    for name, source in (firmware or {}).items():
        sources[name] = re.sub(r'/\*.*?\*/|//[^\n]*', lambda m: '\n' * m[0].count('\n'), source, flags=re.S)
    def matches(pattern):
        for name, source in sources.items():
            for match in re.finditer(pattern, source, re.I):
                yield match, dict(path=name, line=source.count('\n', 0, match.start()) + 1, expression=match[0])
    for c in parts:
        value = c.value.upper()
        byfn = {p.function: p for p in c.pads}
        for p in c.pads:
            if 'PCM1808' in value and p.function in {'SCKI','VREF'} and floating(p):
                emit('pcm1808.' + p.function.lower(), c, [p], 'SCKI is floating: the ADC has no system clock.' if p.function == 'SCKI' else 'VREF is floating: the ADC reference bypass is absent.', 'Route a valid SCKI source.' if p.function == 'SCKI' else 'Connect the datasheet reference capacitor to AGND.', severity='error')
            if 'ESP32' in value and p.function in {'IO0','GPIO0'} and not pullup(p) and not floating(p):
                emit('boot.gpio0', c, [p], 'GPIO0 has no external pull-up; boot relies on the internal pull-up and external circuitry.', 'Review the strapping load and add a suitable external pull-up.')
            # Legacy STM32 PCB has no pin functions; only this documented package mapping is supported.
            if value == 'STM32F405RGT6' and p.number == '7' and not pullup(p):
                caps = [x for x in parts if x.ref.startswith('C') and any(q.net == p.net for q in x.pads)]
                if not caps:
                    emit('reset.nrst', c, [p], 'NRST (LQFP64 pin 7) has no external pull-up or capacitor.', 'Review reset immunity; add the recommended reset network. Internal reset circuitry may suffice under benign conditions.')
            if 'POWERBOOST' in value and p.function == 'USB' and floating(p):
                emit('charge.input', c, [p], 'The USB charge input is unconnected; the carrier cannot supply charging power.', 'Provide a charge-input connection or document charging through the module connector.')
            if ('BME680' in value or 'CJMCU-680' in value) and p.function in {'SDO','CS'} and floating(p):
                emit('sensor.mode', c, [p], 'The BME680 address/mode input floats; I2C selection is undefined unless the module supplies bias.', 'Check the module resistors; strap CS high and choose a defined SDO level.')
        if 'PCM1808' in value:
            mode = [byfn.get(f) for f in ('MD0','MD1')]
            slave = list(matches(r'\bI2S_MODE_SLAVE\b'))
            if all(mode) and all(ground(p) for p in mode) and slave:
                emit('i2s.clock_master', c, mode, 'MD0/MD1 select ADC slave mode and firmware selects I2S slave: neither endpoint supplies BCK/LRCK.', 'Choose one clock master, provide SCKI, and align firmware mode.', [e for _, e in slave], severity='error')
            lrck = byfn.get('LRCK')
            if lrck:
                gpios = {int(m[1]) for p in peers(lrck) if p.ref != c.ref for m in [re.fullmatch(r'(?:GPIO|IO)(\d+)', p.function)] if m}
                for match, ev in matches(r'\bws_io_num\s*=\s*(\d+)'):
                    if len(gpios) == 1 and int(match[1]) not in gpios:
                        emit('firmware.i2s_ws', c, [lrck], f'Firmware WS={match[1]} differs from the connected GPIO{next(iter(gpios))}.', f'Set ws_io_num to the board GPIO{next(iter(gpios))} and verify that it exists on the selected MCU.', [ev], severity='error')
        if 'INA3221' in value:
            a0 = byfn.get('A0')
            # Open solder jumpers are not conductive paths. Only fitted R links count here.
            biased = a0 and (ground(a0) or pullup(a0) or
                any(p.function in {'SCL','SDA'} and p.ref == c.ref for p in peers(a0)) or
                any(x.ref.startswith('R') and any(p.net == a0.net for p in x.pads) and
                    any(ground(p) for p in x.pads) for x in parts))
            if a0 and not biased:
                addr = list(matches(r'\bINA3221_ADDR\s+(0x[0-9a-f]+)'))
                if addr:
                    emit('firmware.ina_address', c, [a0], f'A0 has no fixed bias as built; firmware assumes {addr[0][0][1]}, so begin() can fail.', 'Close the intended address jumper and verify the address against the firmware.', [e for _, e in addr], severity='error')
            reads = list(matches(r'\bget(?:CurrentAmps|BusVoltage)\s*\(\s*(CH[123]|[012])\s*\)'))
            constants = {}
            for match, _ in matches(r'\b(?:define\s+|(?:const\s+)?(?:int|uint8_t)\s+)(CH[123])\s*(?:=\s*)?([012])\b'):
                constants[match[1].upper()] = int(match[2])+1
            used = {constants.get(m[1].upper()) if m[1].upper().startswith('CH') else int(m[1])+1 for m, _ in reads}
            if None in used:
                used = {1,2,3}  # unresolved selection: do not accuse channels of being unused

            wired = {i for i in (1,2,3) if any(p.function.startswith(f'IN+{i}') and not floating(p) for p in c.pads)}
            if reads and wired - used:
                pins = [p for p in c.pads if any(p.function.startswith(f'IN+{i}') for i in wired-used)]
                emit('firmware.ina_channels', c, pins, f'Hardware channels {sorted(wired-used)} are wired but no supported firmware reads reference them.', 'Read and calibrate each wired channel; verify shunt resistance per channel. Dynamic channel selection is not resolved.', [e for _,e in reads])
        if 'CJMCU-680' in c.library.upper():
            unused = [p for p in c.pads if floating(p)]
            if unused:
                emit('sensor.mode_review', c, unused,
                    'CJMCU-680 breakout pins are floating. Verify whether these are SDO/CS: floating address/mode pins leave I2C selection undefined unless the module has bias resistors.',
                    'Verify module pinout and on-module pull resistors; strap CS high and choose SDO bias for the intended I2C address. Pin functions are not proven by this generic connector symbol.')
        if 'DW01A' in value:
            controls = [p for p in c.pads if p.function in {'OD','OC'}]
            mos = [q for x in parts if '8205' in x.value for q in x.pads if any(q.net == p.net for p in controls)]
            open_mos = [q for x in parts if '8205' in x.value for q in x.pads if q.number in {'2','5'} and floating(q)]
            if mos and {p.number for p in mos} == {'4','6'} and {p.number for p in open_mos} == {'2','5'}:
                emit('protection.pinout', c, controls, 'DW01A OD/OC connect to dual-MOSFET pads ' + ', '.join(f'{p.ref}.{p.number}' for p in mos) + '; footprint pinout needs verification.', 'Compare the exact manufacturer pinout and footprint numbering; continuity alone cannot establish correctness.', [dict(path=path,line=p.line,part=p.ref,pin=p.number,net=p.net) for p in mos+open_mos])
    return dict(status='ran' if parts else 'unverified', findings=findings, not_checked=['Fuse/load limits and relay CTR/drive margin without sourced operating limits', 'Full correct-design checklist (SPI, dividers, BOOT0, SWD, USB-C, SSR, WS2812B)', 'Footprint pinout against exact manufacturer datasheet', 'Routed copper continuity (native DRC required)', 'Dynamic firmware expressions and cross-translation-unit dataflow'])
