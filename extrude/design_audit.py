"""Whole-design audit at HEAD, independent of the commit change list."""
from pathlib import Path
import re
import json
import time
from extrude import github_history as git, audit_tools, design_rules, model_coverage, netlist_rules
from extrude.kicad_snapshot import materialize, temporary_directory, safe_path
from extrude.workspace_checks import evidence
from extrude.workspace_netlist import Reader


def collect(repo, sha):
    findings, coverage = [], []
    def cover(path, check, outcome, detail, tool='Extrude'):
        coverage.append(dict(path=path, domain='pcb', check=check, tool=tool, outcome=outcome, detail=detail))
    def add(path, row, external=False):
        refs = row.get('evidence', [])
        if not refs:
            return  # no anonymous verdicts
        sources = [evidence(repo, sha, e.get('path',path),
            'line '+str(e['line'])+' · '+str(e)) for e in refs]
        findings.append(dict(rule_id='design.'+row['rule'],domain='pcb',status='suggestion' if external else 'observed',
            severity=row.get('severity','warning'), summary=row['summary']+' '+row['next_action'],
            lifecycle='present_at_head', evidence=sources, after=row,
            consequence=row['consequence'], next_action=row['next_action']))
    inventory = git.inventory(repo,sha,limit=10000)
    firmware = {}
    candidates = [r for r in inventory['files'] if Path(r['path']).suffix.lower() in {'.ino','.c','.cpp','.h'} and r['type']=='blob']
    for item in candidates[:60]:
        try:
            blob = git.regular_blob(repo,sha,item['path'],max_bytes=512*1024)
            if blob is not None:
                firmware[item['path']] = blob.decode('utf-8-sig')
        except (ValueError, UnicodeError, git.GitHubError):
            cover(item['path'],'Firmware evidence','unavailable','not checked: source unreadable or exceeds bounds')
    if not firmware:
        cover('','Firmware evidence','unavailable','not checked: no supported firmware at this revision')
    elif len(candidates)>60:
        cover('','Firmware scope','unsupported','not checked: only first 60 source files scanned')
    limits_path = '.extrude/electrical-limits.json'
    if any(r['path']==limits_path for r in inventory['files']):
        from extrude.electrical_limits import evaluate
        try:
            blob=git.regular_blob(repo,sha,limits_path,max_bytes=128*1024)
            def read_source(path):
                data=git.regular_blob(repo,sha,path,max_bytes=512*1024)
                if data is None:
                    raise ValueError('Operating-limit source absent')
                return data.decode('utf-8-sig')
            for row in evaluate(json.loads(blob),read_source):
                add(limits_path,row,external=True)
            cover(limits_path,'Fuse/load and drive math','ran','Sourced operating assumptions evaluated; physical validation not checked')
        except (ValueError,KeyError,TypeError,AttributeError,UnicodeError):
            cover(limits_path,'Fuse/load and drive math','unavailable','not checked: invalid or unsourced operating bounds')
    else:
        cover(limits_path,'Fuse/load and drive math','unavailable','not checked: no sourced operating limits supplied')
    deadline = time.monotonic()+120
    reader=Reader()
    with materialize(repo,sha) as snapshot:
        for path,reason in snapshot.issues:
            cover(path,'Snapshot input','unavailable','not checked: '+reason)
        for path in sorted(snapshot.files):
            if path.endswith('.kicad_sch'):
                try:
                    assembly=reader.get(repo,sha,path)
                    schematic_source = safe_path(snapshot.root,path).read_text(encoding='utf-8-sig')
                    for issue in assembly.get('review', {}).get('findings', []):
                        marker = re.search(r'\(property\s+"Reference"\s+"'+re.escape(issue['part'])+r'"', schematic_source)
                        if marker is None:
                            continue  # unresolved source location is not a finding
                        source_line = schematic_source.count('\n',0,marker.start())+1
                        row = dict(rule='netlist.'+issue['rule'],severity='warning',
                            summary=issue['consequence'],consequence=issue['consequence'],next_action=issue['next_action'],
                            evidence=[dict(path=path,line=source_line,part=issue['part'],pin=issue['pin'],net=issue['net'],
                                exported_netlist_line=issue['line'],source='schematic reference property; pin/net from native exported netlist')])
                        add(path,row,external=True)
                    cover(path,'Native connectivity export','ran',f"{len(assembly['components'])} components; no electrical pass implied")
                except ValueError as exc:
                    cover(path,'Native connectivity export','unavailable','not checked: '+str(exc))
            if not path.endswith('.kicad_pcb'):
                continue
            if sum(c['check']=='Whole-design rules' for c in coverage)>=12:
                cover(path,'Whole-design rules','unsupported','not checked: board limit reached')
                continue
            board = safe_path(snapshot.root,path)
            text = board.read_text(encoding='utf-8-sig')
            try:
                report=design_rules.analyze(text,path,firmware)
                for row in report['findings']:
                    add(path,row)
                cover(path,'Whole-design rules','ran' if report['status']=='ran' else 'unavailable',
                    'Candidates from pad connectivity; not checked: '+'; '.join(report['not_checked']))
                models=model_coverage.inspect(text,board,snapshot.root,{r['path'] for r in inventory['files'] if r['type']=='blob'})
                cover(path,'3D model presence','ran', 'Tracked-file presence only; library variables remain not checked. '+str(models['footprints']))
                cover(path,'STEP export and enclosure fit','unavailable','not checked: no geometry or height/enclosure verification was performed')
                with temporary_directory('ingredients-') as folder:
                    reports=audit_tools.run_board(board,Path(folder),max(0,deadline-time.monotonic()))
                rows,triage=audit_tools.triage(reports,text)
                for row in rows[:100]:
                    add(path,row,external=True)
                for name,data in reports.items():
                    cover(path,'Ingredient '+name,'ran' if data['status']=='ran' else 'unavailable',
                        data.get('detail','Candidate extraction ran; upstream verdict discarded.')+' Triage: '+str(triage)+
                        ' Native DRC/ERC, net-class/current-path rules and vision are not certified by this layer.',name)
            except (ValueError,OSError,RecursionError) as exc:
                cover(path,'Whole-design rules','failed','not checked: '+str(exc)[:300])
    return findings,coverage
