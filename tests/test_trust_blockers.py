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
    files = {'unit.kicad_sch': design([device(), device('U1')]),
             'unit.kicad_pcb': board(['U1', 'U82']),
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
    findings, _ = analyze({'a.kicad_sch': design([device(), device('U82')], [(net, 0, 0)])})
    assert bool([f for f in findings if f['rule_id'] == 'electrical.pullup']) == expected


def bus_suppressions(coverage):
    return [
        detail for _, family, detail in coverage
        if family == "pullup" and "is not an on-board I2C bus" in detail
    ]


@pytest.mark.parametrize("with_pullup", [False, True])
def test_genuine_i2c_bus_requires_a_pullup(with_pullup):
    parts = [
        device("U1", "SDA", "bidirectional"),
        device("U2", "SDA", "bidirectional"),
    ]
    labels = [("I2C_SDA", 0, 0)]
    if with_pullup:
        parts.append(resistor("R1", "4.7k", (0, 0), (10, 0)))
        labels.append(("+3V3", 10, 0))
    findings, _ = analyze({"bus.kicad_sch": design(parts, labels)})
    pullups = [f for f in findings if f["rule_id"] == "electrical.pullup"]
    if with_pullup:
        assert not pullups
    else:
        assert [(f["summary"], f["status"]) for f in pullups] == [
            (
                "U1: SDA (SDA/I2C_SDA) has no external pull-up to a known supply. "
                "I2C/DDC open-drain signaling requires pull-ups; fit them or document "
                "pull-ups on the connected module.",
                "suggestion",
            )
        ]


@pytest.mark.parametrize(
    "labels, peers",
    [
        pytest.param(["RE1A", "SDA"], [device("SW1", "A", "passive")], id="encoder"),
        pytest.param(
            ["I2C_SDA"],
            [("J1", "Generic:Header", "header", [
                ("1", "SDA", "passive", 0, 0), ("2", "SCL", "passive", 10, 0)
            ], {})],
            id="header",
        ),
        pytest.param(
            ["I2C_SDA"],
            [device("J1", "SDA", "passive"), device("TP1", "SDA", "passive"),
             device("TP2", "SDA", "passive")],
            id="connector-and-test-points",
        ),
        pytest.param(
            ["I2C_SDA"],
            [("U2", "Generic:Mixed", "peripheral", [
                ("1", "SDA", "passive", 0, 0), ("2", "OUT", "output", 10, 0)
            ], {})],
            id="active-pin-on-another-net",
        ),
    ],
)
def test_passive_peers_do_not_make_an_i2c_bus(labels, peers):
    parts = [device("U1", "SDA", "bidirectional"), *peers]
    findings, coverage = analyze({
        "bus.kicad_sch": design(parts, [(label, 0, 0) for label in labels])
    })
    assert not [f for f in findings if f["rule_id"] == "electrical.pullup"]
    assert bus_suppressions(coverage) == [
        f"Not checked: {'/'.join(labels)} is not an on-board I2C bus "
        "(1 active device(s): U1); pull-ups, if needed, live on the connected module."
    ]


@pytest.mark.parametrize(
    "net, pin_name",
    [("I2S0_RX_SDA", "SDA"), ("I2C", "I2S0_RX_SDA"), ("I2C", "MOSI_DATA")],
)
def test_pullups_exclude_spi_and_i2s_signal_names(net, pin_name):
    parts = [device("U1", pin_name, "bidirectional"), device("U2", "IO", "bidirectional")]
    findings, coverage = analyze({"bus.kicad_sch": design(parts, [(net, 0, 0)])})
    assert not [f for f in findings if f["rule_id"] == "electrical.pullup"]
    assert not bus_suppressions(coverage)


@pytest.mark.parametrize("peer_kind", ["passive", "bidirectional"])
def test_open_collector_trigger_requires_two_active_devices(peer_kind):
    parts = [device("U1", "DATA", "open_collector"), device("U2", "DATA", peer_kind)]
    findings, coverage = analyze({"bus.kicad_sch": design(parts, [("LINK_DATA", 0, 0)])})
    pullups = [f for f in findings if f["rule_id"] == "electrical.pullup"]
    if peer_kind == "passive":
        assert not pullups
        assert bus_suppressions(coverage) == [
            "Not checked: LINK_DATA is not an on-board I2C bus (1 active device(s): U1); "
            "pull-ups, if needed, live on the connected module."
        ]
    else:
        assert len(pullups) == 1
        assert pullups[0]["status"] == "suggestion"


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
