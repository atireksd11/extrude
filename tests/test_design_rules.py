"""Pinned PCB evidence and negative controls, without network or native tools."""
from pathlib import Path
import pytest
from extrude import design_rules as rules
from extrude.workspace_audit import Finding, Coverage

ROOT = Path(__file__).parent / 'fixtures/design_rules/shashvat'


def case():
    return {p.name: p.read_bytes() for p in ROOT.iterdir() if p.suffix in {'.ino','.kicad_pcb'}}


def test_exact_shashvat_regression():
    files = case()
    findings, coverage = rules.analyze(files)
    assert [f['rule_id'] for f in findings].count('design.critical_pin') == 2
    assert {f['rule_id'] for f in findings} == {'design.critical_pin','design.firmware_pin','design.clock_master'}
    mismatch = next(f for f in findings if f['rule_id'] == 'design.firmware_pin')
    assert 'ws_io_num=27' in mismatch['summary']
    assert 'GPIO28 does not exist' in mismatch['summary']
    assert len(mismatch['evidence']) == 3
    for f in findings:
        Finding.model_validate(f)
        assert f['evidence'] and all('line ' in e['locator'] for e in f['evidence'])
    for c in coverage:
        Coverage.model_validate(c)
    pads = rules.board_pads(files['board.kicad_pcb'])
    u4 = {p.number:p for p in pads if p.ref == 'U4'}
    assert u4['7'].net == 'Net-(U3-IO27)'
    assert u4['8'].net == 'Net-(U3-IO14)'
    assert u4['9'].net == 'Net-(U3-IO34)'
    assert u4['6'].net == 'unconnected-(U4-SCKI-Pad6)'
    assert u4['1'].net == 'unconnected-(U4-VREF-Pad1)'


def test_correct_ws_and_master_remove_only_corresponding_findings():
    files = case()
    files['firmware.ino'] = files['firmware.ino'].replace(b'ws_io_num = 28', b'ws_io_num = 27').replace(b'I2S_MODE_SLAVE', b'I2S_MODE_MASTER')
    findings, _ = rules.analyze(files)
    assert [f['rule_id'] for f in findings] == ['design.critical_pin','design.critical_pin']


@pytest.mark.parametrize('mutation', ['conditional', 'duplicate', 'computed', 'multiple_boards', 'missing_firmware'])
def test_ambiguous_mapping_does_not_invent_mismatch(mutation):
    files = case()
    code = files['firmware.ino']
    if mutation == 'conditional': code = b'#if CONFIG_BOARD\n' + code + b'\n#endif'
    if mutation == 'duplicate': code += b'\nother.ws_io_num = 28,\n'
    if mutation == 'computed': code = code.replace(b'ws_io_num = 28',b'ws_io_num = PIN_WS')
    files['firmware.ino'] = code
    if mutation == 'multiple_boards': files['other.kicad_pcb'] = files['board.kicad_pcb']
    if mutation == 'missing_firmware': files.pop('firmware.ino')
    findings, _ = rules.analyze(files)
    assert not any(f['rule_id'] == 'design.firmware_pin' for f in findings)


@pytest.mark.parametrize('data', [b'(kicad_pcb (version 20240108))',b'bad', b''])
def test_empty_or_invalid_board_is_unverified(data):
    findings, coverage = rules.analyze({'empty.kicad_pcb':data})
    assert findings == []
    assert coverage and all(c['outcome'] != 'ran' and 'not checked' in c['detail'] for c in coverage)


def test_documentation_head_still_reads_entire_revision(monkeypatch):
    files = case()
    monkeypatch.setattr(rules.git,'inventory',lambda *a,**k:dict(files=[dict(path=p) for p in files],next_offset=None))
    monkeypatch.setattr(rules.git,'regular_blob',lambda r,s,p,**k:files[p])
    findings, _ = rules.collect('repo','readme-only-head')
    assert len(findings) == 4
    assert all(e['sha']=='readme-only-head' for f in findings for e in f['evidence'])


def test_native_explanation_preserves_verdict_and_evidence():
    f = dict(rule_id='kicad.erc.power_pin_not_driven',summary='U1 pin 2 GND not driven',status='verified',evidence=[dict(path='board.kicad_sch',locator='U1 pin 2')])
    result = rules.explain_native(f)
    assert result['evidence'] == f['evidence'] and result['status'] == 'verified'
    assert 'does not prove missing physical power' in result['summary']


def board(part, function, net='SIGNAL', number='1', peer=''):
    return f'''(kicad_pcb (version 20240108)
      (footprint "Test" (at 0 0) (layer "F.Cu") (property "Reference" "U1") (property "Value" "{part}")
        (pad "{number}" smd rect (net "{net}") (pinfunction "{function}"))) {peer})'''.encode()


def resistor(net):
    return f'''(footprint "Resistor" (at 0 0) (layer "F.Cu") (property "Reference" "R1") (property "Value" "10k")
      (pad "1" smd rect (net "{net}")) (pad "2" smd rect (net "+3.3V")))'''


@pytest.mark.parametrize('part,function,net,number,rule',[
    ('ESP32-WROOM-32','IO0','BOOT','25','design.boot_bias'),
    ('STM32F405RGT6','','NRST','7','design.reset_bias'),
])
def test_reset_and_boot_weakness_with_pullup_negative_control(part,function,net,number,rule):
    f,_=rules.analyze({'board.kicad_pcb':board(part,function,net,number)})
    assert [x['rule_id'] for x in f] == [rule]
    f,_=rules.analyze({'board.kicad_pcb':board(part,function,net,number,resistor(net))})
    assert f == []


@pytest.mark.parametrize('part,function', [('BME680','SDO'),('BME680','CS'),('PowerBoost_500_Breakout','USB')])
def test_critical_module_input_and_connected_negative_control(part,function):
    data=board(part,function)
    f,_=rules.analyze({'board.kicad_pcb':data})
    assert len(f)==1 and f[0]['summary'].startswith('RISK:')
    f,_=rules.analyze({'board.kicad_pcb':board(part,function,peer=resistor('SIGNAL'))})
    assert f==[]


def test_unrelated_correct_designs_are_not_flagged():
    # These are supported-scope negative controls, not proof of circuit correctness.
    for part,pin in [('TPS54302','FB'),('TPS54302','EN'),('STM32F405RGT6','BOOT0'),('STM32F405RGT6','SWDIO'),('USB_C','CC1'),('SSR','IN'),('WS2812B','DIN'),('MicroSD','MOSI'),('Camera','SCK'),('Battery','SENSE'),('ESP32-WROOM-32','SDA')]:
        f,_=rules.analyze({'board.kicad_pcb':board(part,pin)})
        assert not f


def test_ina_address_open_jumper_and_channel_usage():
    pads = ''.join(f'(pad "{i}" smd rect (net "N{n}{sign}" ) (pinfunction "IN{sign}{n}"))' for i,(n,sign) in enumerate([(n,s) for n in (1,2,3) for s in ('+','-')],1))
    peers = ''.join(f'(footprint "Shunt" (at 0 0) (layer "F.Cu") (property "Reference" "RS{n}") (property "Value" "0.01") (pad "1" smd rect (net "N{n}+")) (pad "2" smd rect (net "N{n}-")))' for n in (1,2,3))
    data = f'''(kicad_pcb (version 20240108)
      (footprint "IC" (at 0 0) (layer "F.Cu") (property "Reference" "U1") (property "Value" "INA3221")
        (pad "9" smd rect (net "ADDR") (pinfunction "A0")) {pads})
      (footprint "Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad" (at 0 0) (layer "F.Cu") (property "Reference" "JP2") (property "Value" "ADDR2")
        (pad "1" smd rect (net "ADDR")) (pad "2" smd rect (net "GND"))) {peers})'''.encode()
    firmware = b'#define INA3221_ADDR 0x40\n#define CH1 0\nAdafruit_INA3221 sensor;\nvoid setup() { sensor.begin(INA3221_ADDR, &Wire); }\nvoid loop() { sensor.getCurrentAmps(CH1); }'
    f,_=rules.analyze({'board.kicad_pcb':data,'firmware.ino':firmware})
    assert {x['rule_id'] for x in f} == {'design.address_strap','design.unused_channels'}
    assert all(x['evidence'] for x in f)
    # A direct strap resolves the floating-address finding; reading CH2 resolves
    # this narrowly supported CH1-only predicate (not an automatic complete pass).
    data = data.replace(b'(net "ADDR")', b'(net "GND")')
    f,_=rules.analyze({'board.kicad_pcb':data,'firmware.ino':firmware + b'\nsensor.getCurrentAmps(1);'})
    assert f == []
