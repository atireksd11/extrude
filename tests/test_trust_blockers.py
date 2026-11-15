"""Generic regressions for component parity, protocol intent and bus drive."""
import pytest
from extrude.electrical_reasoning import analyze
from extrude import pcb_review, workspace_audit
from test_electrical_reasoning import design, resistor


def board(refs):
    return ('(kicad_pcb (version 20250114) ' + ' '.join(
        f'(footprint "Test:Part" (layer "F.Cu") (at {i} 0) (property "Reference" "{ref}") '
        '(pad "1" thru_hole circle (at 0 0) (size 1 1) (drill 0.5) (layers "*.Cu" "*.Mask")))'
        for i, ref in enumerate(refs)) + ')').encode()


def device(ref="U81", name="SCL", kind="input", xy=(0, 0)):
    return (ref, 'Generic:'+ref, 'bus peripheral', [('1', name, kind, *xy)], {})


def test_parity_is_bidirectional_and_paired_board_is_not_backup():
    files = {'unit.kicad_sch': design([device()]),
             'unit.kicad_pcb': board(['U82']),
             'unit copy.kicad_pcb': board(['U81'])}
    findings, coverage = analyze(files)
    parity = [f for f in findings if f['rule_id'] == 'electrical.assembly']
    assert len(parity) == 2
    assert all(f['severity'] == 'warning' for f in parity)
    assert any('U81:' in f['summary'] and 'cannot be assembled' in f['summary'] for f in parity)
    assert any('U82:' in f['summary'] and 'no symbol' in f['summary'] for f in parity)
    assert any(f == 'assembly' and not detail.startswith('Not checked:') for _, f, detail in coverage)


def test_off_board_symbols_and_padless_graphics_are_not_missing_components():
    sch = design([device()]).replace(b'(on_board yes)', b'(on_board no)')
    pcb = b'(kicad_pcb (version 20250114) (footprint "Graphics:Logo" (layer "F.Cu") (at 0 0) (property "Reference" "G1")))'
    assert not [f for f in analyze({'a.kicad_sch': sch, 'a.kicad_pcb': pcb})[0]
                if f['rule_id'] == 'electrical.assembly']


@pytest.mark.parametrize('net,expected', [('PERIPHERAL_SPI_SCK', False), ('SCK', False), ('I2C_SCL', True), ('UNKNOWN', False)])
def test_pullups_require_protocol_evidence(net, expected):
    findings, _ = analyze({'a.kicad_sch': design([device()], [(net, 0, 0)])})
    assert bool([f for f in findings if f['rule_id'] == 'electrical.pullup']) == expected


@pytest.mark.parametrize('driver', ['output', 'bidirectional', 'passive', None])
def test_bus_loads_need_a_driver_and_unknown_connector_is_not_proof(driver):
    parts = [device(name='SCK'), device('U82', 'SCK')]
    if driver:
        parts.append(device('U83', 'SCK', driver))
    findings, _ = analyze({'a.kicad_sch': design(parts, [('CONTROL_SPI_CLK', 0, 0)])})
    undriven = [f for f in findings if f['rule_id'] == 'electrical.undriven']
    assert bool(undriven) == (driver is None)
    if undriven:
        assert 'U81 pin 1' in undriven[0]['summary'] and 'U82 pin 1' in undriven[0]['summary']


def test_series_resistor_driver_and_pull_resistor_bias():
    parts = [device(name='MOSI'), resistor('R91', '33', (0, 0), (10, 0)), device('U82', 'DO', 'output', (10, 0))]
    files = {'a.kicad_sch': design(parts, [('SPI_DATA', 0, 0)])}
    assert not [f for f in analyze(files)[0] if f['rule_id'] == 'electrical.undriven']
    parts.pop()
    files['a.kicad_sch'] = design(parts, [('SPI_DATA', 0, 0), ('3V3', 10, 0)])
    assert [f for f in analyze(files)[0] if f['rule_id'] == 'electrical.undriven']


def test_duplicate_board_collapses_only_when_full_supported_inventory_matches(monkeypatch):
    existing, added = board(['U81', 'R91']), board(['U81', 'R91'])
    def snapshot(repo, sha, path):
        raw = added if path == 'copy.kicad_pcb' else existing
        return pcb_review.parse_board(raw), {'status': 'read'}
    monkeypatch.setattr(pcb_review, '_snapshot', snapshot)
    monkeypatch.setattr(pcb_review.history, 'file_exists', lambda *a: False)
    monkeypatch.setattr(pcb_review.history, 'inventory', lambda *a, **kw: {'next_offset': None, 'files': [{'type': 'blob', 'path': 'original.kicad_pcb'}]})
    audit = workspace_audit.Audit(id='test', repo_id='local', base_sha='base', head_sha='head', tool_versions={}, config_hash='test')
    workspace_audit._board(audit, 'copy.kicad_pcb', 'copy.kicad_pcb')
    assert len(audit.findings) == 1
    assert audit.findings[0].rule_id == 'pcb.board_copy_added'
    assert '2 footprints' in audit.findings[0].summary
    original_added = added
    added = added.replace(b'(at 1 0)', b'(at 9 0)')
    assert pcb_review.duplicate_added_board('local', 'head', 'base', 'copy.kicad_pcb') is None
    added = original_added.replace(b'(property \"Reference\" \"R91\")', b'(property \"Reference\" \"R91\") (property \"Value\" \"10k\")')
    assert pcb_review.duplicate_added_board('local', 'head', 'base', 'copy.kicad_pcb') is None


def test_named_single_bus_load_is_undriven_but_static_bias_is_valid():
    parts = [device(name='CS')]
    findings, _ = analyze({'a.kicad_sch': design(parts, [('DISPLAY_CS', 0, 0)])})
    assert any(f['rule_id'] == 'electrical.undriven' for f in findings)
    parts = [device(name='EN'), device('U82', 'EN'), resistor('R91', '10k', (0, 0), (10, 0))]
    findings, _ = analyze({'a.kicad_sch': design(parts, [('ENABLE', 0, 0), ('3V3', 10, 0)])})
    assert not any(f['rule_id'] == 'electrical.undriven' for f in findings)


def test_bom_only_component_missing_from_board_is_reported_in_scoped_assembly():
    parts = [device('U'+str(n)) for n in range(10, 19)]
    bom = b'Reference,Value\n"U10 U11 U12 U13 U14 U15 U16 U17 U18 R99",parts\n'
    findings, _ = analyze({'a.kicad_sch': design(parts), 'a.kicad_pcb': board(['U'+str(n) for n in range(10, 19)]), 'bom.csv': bom})
    assert any(f['summary'].startswith('R99:') and 'BOM' in f['summary'] and f['severity'] == 'warning' for f in findings)


def test_configured_firmware_component_absence_is_a_warning(monkeypatch):
    from extrude import workspace_checks
    from extrude.workspace_settings import PinMapping
    monkeypatch.setattr(workspace_checks, 'facts', lambda *a: {'constants': {'BUS_CLOCK': {'value': 7, 'line': 1}}})
    monkeypatch.setattr(workspace_checks.git, 'regular_blob', lambda *a, **k: board(['R91']))
    collector = workspace_checks.Collector('local', 'head', None)
    # Native pin/netlist comparison is independent of PCB assembly parity.
    monkeypatch.setattr(collector, 'paired', lambda *a: None)
    collector.pin(PinMapping(firmware_file='main.c', firmware_symbol='BUS_CLOCK', netlist_file='a.kicad_sch', schematic_net='CLOCK', mcu_ref='U81', numbering='package'))
    assert len(collector.findings) == 1
    assert collector.findings[0]['severity'] == 'warning'
    assert 'U81:' in collector.findings[0]['summary']
    assert 'cannot be implemented' in collector.findings[0]['summary']
