from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import gzip,json,subprocess,tempfile
from extrude import design_rules,audit_tools,kicad_audit
import argparse
parser=argparse.ArgumentParser(description='Run pinned audit inputs; no auto-grading or repository code execution')
parser.add_argument('--repos',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
root=args.repos.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
expected={'esp32-4-channel-relays':'3c7d3b1','bench-psu-monitor':'cd87301','STM32F4-Reference-PCB':'e0d1d8d','silkscreen-pcb':'4530931','Doorman':'fdec5c0','sniffer':'037c8c2','ESP32-Camera-PCB':'d467da9','Bluetooth-Audio-Transmiter':'f5c2b29'}
def run(repo):
 sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
 assert sha.startswith(expected[repo.name]),(repo.name,sha)
 fw={str(p.relative_to(repo)):p.read_text(errors='replace') for p in repo.rglob('*.ino')}
 record=dict(repo=repo.name,sha=sha,boards=[])
 for board in sorted(repo.rglob('*.kicad_pcb')):
  path=str(board.relative_to(repo));text=board.read_text()
  row=dict(path=path,design=design_rules.analyze(text,path,fw))
  with tempfile.TemporaryDirectory(dir=out) as folder:
   scratch=Path(folder)
   row['ingredients']=audit_tools.run_board(board,scratch,90)
   row['triage']=audit_tools.triage(row['ingredients'],text)
   row['native']={}
   for check,file in [('drc',board),('erc',board.with_suffix('.kicad_sch'))]:
    if not file.exists():
     row['native'][check]=dict(status='not checked',reason='No native schematic');continue
    output=scratch/'native.json';output.unlink(missing_ok=True)
    args=['/usr/bin/kicad-cli','pcb' if check=='drc' else 'sch',check,'--format','json','--output',str(output),str(file)]
    try:
     p=subprocess.run(args,cwd=file.parent,env=kicad_audit._environment('/usr/bin/kicad-cli',scratch),capture_output=True,text=True,timeout=40)
     d=dict(command=args,exit=p.returncode,stdout=p.stdout,stderr=p.stderr,version=kicad_audit.tool_version())
     d['status']='ran' if p.returncode in (0,5) and output.is_file() and output.stat().st_size else 'not checked'
     if output.exists():d['raw']=output.read_text(errors='replace')
     row['native'][check]=d
    except subprocess.TimeoutExpired:row['native'][check]=dict(status='not checked',reason='40-second timeout')
  record['boards'].append(row)
 with gzip.open(out/(repo.name+'.json.gz'),'wt') as f:json.dump(record,f,indent=2)
 print(repo.name,sha[:7],[(b['path'],[f['rule'] for f in b['design']['findings']],{k:v['status'] for k,v in b['ingredients'].items()}) for b in record['boards']],flush=True)
 return record
with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,sorted(root.iterdir())))
(out/'index.json').write_text(json.dumps([dict(repo=r['repo'],sha=r['sha'],file=r['repo']+'.json.gz') for r in results],indent=2))
