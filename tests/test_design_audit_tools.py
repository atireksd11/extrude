from pathlib import Path
import json
import pytest
from extrude import audit_tools, design_rules, model_coverage, netlist_rules
from extrude.workspace_netlist import read_netlist


def board(value='PCM1808PWR', pads=None):
    pads = pads or [('1','VREF','unconnected-(U1-VREF-Pad1)'),('6','SCKI','unconnected-(U1-SCKI-Pad6)')]
    ps='\n'.join(f'(pad "{n}" smd rect (at 0 0) (size 1 1) (layers "F.Cu") (pinfunction "{f}") (pintype "input") (net "{net}"))' for n,f,net in pads)
    return f'(kicad_pcb (version 20260101)\n(footprint "test:part" (layer "F.Cu") (at 0 0)\n(property "Reference" "U1")\n(property "Value" "{value}")\n{ps}))'


def test_critical_pin_function_overrides_nc_net_name_and_has_real_lines():
    text=board()
    rows=design_rules.analyze(text,'b.kicad_pcb')['findings']
    assert {r['rule'] for r in rows}=={'pcm1808.scki','pcm1808.vref'}
    for r in rows:
        assert r['next_action'] and r['consequence']
        for e in r['evidence']:
            assert '(pad "'+e['pin']+'"' in text.splitlines()[e['line']-1]
    renamed=text.replace('unconnected-(U1-VREF-Pad1)','arbitrary-net')
    assert any(r['rule']=='pcm1808.vref' for r in design_rules.analyze(renamed,'b')['findings'])


def test_connected_critical_pins_and_usb_sbu_are_not_falsely_flagged():
    text=board()+''
    text=text[:-1]+'\n(footprint "test:c" (property "Reference" "C1") (property "Value" "1u") (pad "1" smd rect (net "unconnected-(U1-VREF-Pad1)"))))'
    assert 'pcm1808.vref' not in {r['rule'] for r in design_rules.analyze(text,'b')['findings']}
    assert not design_rules.analyze(board('USB', [('B8','SBU2','foo')]),'b')['findings']


def test_upstream_verdicts_silk_sbu_holes_are_never_forwarded():
    report={'check':dict(status='ran',report={'verdict':'passed','findings':[
        dict(rule_id='single_pad_net',message='no action required',refs=['U1']),
        dict(rule_id='silkscreen_line_width',message='blocking!',refs=['U1']),
        dict(rule_id='foo',message='BOM unbuildable',refs=['H1'])]})}
    rows,counts=audit_tools.triage(report,board())
    assert rows==[] and counts['silkscreen advisory']==1


def test_custom_pad_failure_continues_all_commands(tmp_path,monkeypatch):
    b=tmp_path/'b.kicad_pcb';b.write_text(board())
    monkeypatch.setattr(audit_tools.shutil,'which',lambda s:'/test/kct' if s=='kct' else None)
    calls=[]
    def run(args,**kw):
        calls.append(args[1]);kw['stdout'].write(json.dumps({'error':"Unsupported routing geometry 'custom'"} if args[1]=='check' else {}).encode())
        return type('P',(),{'returncode':2})()
    monkeypatch.setattr(audit_tools.subprocess,'run',run)
    reports=audit_tools.run_board(b,tmp_path)
    assert calls==['audit','check','detect-mistakes']
    assert reports['check']['status']=='not checked'
    assert reports['detect-mistakes']['status']=='ran'


def test_empty_netlist_is_unverified():
    text='(export (components) (nets))'
    with pytest.raises(ValueError,match='unverified'):
        read_netlist(text.encode())
    assert netlist_rules.review(text)['status']=='unverified'


def test_native_netlist_five_checks_are_conservative():
    text='''(export (components (comp (ref U1)) (comp (ref U1)))
      (nets (net (name x) (node (ref U1) (pin 1) (pintype input)))
      (net (name y) (node (ref U1) (pin 2) (pintype input)) (node (ref U2) (pin 1) (pintype passive)))))'''
    assert {r['rule'] for r in netlist_rules.review(text)['findings']} == {'duplicate_reference','missing_footprint','single_pin_net','floating_input','undriven_net'}


def test_models_presence_never_certifies_fit(tmp_path):
    b=tmp_path/'b.kicad_pcb'
    result=model_coverage.inspect(board(),b,tmp_path)
    assert result['step_export']==result['enclosure_fit']=='not checked'
    assert result['footprints'][0]['status']=='missing'


def test_fuse_load_and_ctr_math_requires_sources_and_reports_margin():
    from extrude.electrical_limits import evaluate
    def named(values):
        return {k:dict(value=v,path='limits.md',line=1) for k,v in values.items()}
    config=dict(fuses=[dict(part='F1',inputs=named(dict(hold_a=.5,load_a_mcu=.2,load_a_relays=.28)))],
        drives=[dict(part='U5/Q2/K1',inputs=named(dict(drive_v=5,indicator_vf=.8,opto_vf=1.2,led_resistance_ohm=1000,
        base_resistance_ohm=1000,coil_a=.07,forced_beta=60,ctr_min=.5,collector_v=5,opto_vce=.2,base_vbe=.7)))])
    rows=evaluate(config,lambda p:'Sourced engineering bounds')
    assert rows[0]['measurements']['utilization']==pytest.approx(.96)
    assert rows[1]['measurements']['led_a']==pytest.approx(.003)
    assert rows[1]['measurements']['base_a']==pytest.approx(.0015)
    assert rows[1]['measurements']['margin']==pytest.approx(2/7)
    with pytest.raises(ValueError):evaluate(config,lambda p:'')


def test_native_report_missing_severity_requires_explicit_invocation_evidence():
    from extrude.kicad_audit import parse_report
    report=dict(source='b.kicad_pcb',violations=[],unconnected_items=[])
    report['$schema']='https://schemas.kicad.org/drc.v1.json'
    raw=json.dumps(report).encode()
    with pytest.raises(ValueError):parse_report(raw,'drc','b.kicad_pcb',{})
    assert parse_report(raw,'drc','b.kicad_pcb',{},requested_error_warning=True).outcome=='ran'


def test_buck_rejects_more_than_30mv_and_unverified_inputs():
    from extrude.physics.api import derive
    from extrude.ir.models import CircuitIR, Part
    from extrude.intake.models import FrozenSpec
    spec=FrozenSpec(task_class='buck',values_si=dict(vin=12,vout=5,i_load=2,ripple_pp=.030),spec_hash='test',origins={},defaults_version='test')
    ir=CircuitIR(parts=[Part(refdes='L1',kind='inductor',inductance=10e-6),
        Part(refdes='C1',kind='capacitor',capacitance=1e-6,esr=.1)],f_sw=500e3)
    result=derive(ir,spec)
    assert result.ripple_pp>.030
    assert any(f.code=='ripple_exceeded' and f.severity=='fail' for f in result.findings)
    assert any(f.code=='ripple_unverified' for f in derive(CircuitIR(),spec).findings)


def test_head_design_collection_does_not_depend_on_changed_paths(tmp_path,monkeypatch):
    from contextlib import nullcontext
    from extrude import design_audit
    from extrude.kicad_snapshot import Snapshot
    path='b.kicad_pcb';(tmp_path/path).write_text(board())
    monkeypatch.setattr(design_audit.git,'inventory',lambda *a,**kw:dict(files=[dict(path=path,type='blob')],next_offset=None))
    monkeypatch.setattr(design_audit,'materialize',lambda *a:nullcontext(Snapshot(tmp_path,{path})))
    monkeypatch.setattr(design_audit.audit_tools,'run_board',lambda *a,**kw:{'check':dict(status='not checked',detail='custom pad')})
    findings,coverage=design_audit.collect('repo','a'*40)
    assert {'design.pcm1808.vref','design.pcm1808.scki'} <= {f['rule_id'] for f in findings}
    assert all(f['evidence'] and f['consequence'] and f['next_action'] for f in findings)
    assert any(c['outcome']=='unavailable' and 'custom pad' in c['detail'] for c in coverage)
    assert any(c['check']=='STEP export and enclosure fit' and c['outcome']=='unavailable' for c in coverage)


def test_lower_level_empty_netlist_cannot_bypass_workspace_guard():
    from extrude.parse.kicad_netlist import parse_kicad_netlist
    with pytest.raises(ValueError,match='unverified'):
        parse_kicad_netlist('(export (components) (nets))')


def test_malformed_candidate_rows_cannot_abort_other_layers():
    rows,_=audit_tools.triage({'check':dict(status='ran',report={'findings':[None,{},dict(rule_id=None)]}),
        'audit':dict(status='ran',report={'sync':None})},board())
    assert rows==[]
