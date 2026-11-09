"""Replay electrical rules from git blobs at the audit's exact pinned revisions.

Usage: python -m eval.design_rules_benchmark /path/to/cloned/repos report.json
Never executes source from benchmark repositories. Does not run native checks.
"""
import json
from pathlib import Path
import subprocess
import sys
from extrude.design_rules import analyze, SOURCE, MAX_BOARD_BYTES

CASES = [
 ('leomanangka/esp32-4-channel-relays','3c7d3b1',{'design.boot_bias'}),
 ('fixthepixel/bench-psu-monitor','cd87301',{'design.address_strap','design.unused_channels'}),
 ('pms67/STM32F4-Reference-PCB','e0d1d8d',{'design.reset_bias'}),
 ('iandchasse/silkscreen-pcb','4530931',set()),
 ('AzonInc/Doorman','fdec5c0',{'design.boot_bias'}),
 ('kylemanna/sniffer','037c8c2',set()),
 ('UnsignedArduino/ESP32-Camera-PCB','d467da9',{'design.charge_input'}),
 ('Shashvat1333/Bluetooth-Audio-Transmiter','f5c2b29347f9eaced1b67b3011b986baca8b7777',{'design.firmware_pin','design.critical_pin','design.clock_master'}),
]


def run(root):
    results = []
    for repo, short, expected in CASES:
        folder = root / repo.split('/')[1]
        def git(*args):
            return subprocess.check_output(['git','-C',str(folder),*args])
        sha = git('rev-parse',short+'^{commit}').decode().strip()
        paths = git('ls-tree','-rz','--name-only',sha).decode().split('\0')
        files = {}
        for path in paths:
            if Path(path).suffix.lower() in SOURCE | {'.kicad_pcb','.kicad_sch','.sch'}:
                data = git('show',sha+':'+path)
                if len(data) > MAX_BOARD_BYTES:
                    raise ValueError(f'{repo}:{path} exceeds input limit')
                files[path] = data
        findings, coverage = analyze(files,repo,sha)
        caught = {f['rule_id'] for f in findings}
        assert expected <= caught, (repo,expected-caught)
        results.append(dict(repo=repo,sha=sha,before_caught=0,after_caught=sorted(caught),findings=findings,coverage=coverage))
        print(repo, sorted(caught))
    return dict(baseline='Nov 8 live audit: 0/10',native_checks='not checked: Phase 1/PR #6 is separate; no fresh native checks in this replay',
                scoring='5/10 unique audit checklist groups caught; shared GPIO0 group counted once. 6 repo/check occurrences. Correct-design PASS group remains not checked, not awarded.',results=results)


if __name__ == '__main__':
    result = run(Path(sys.argv[1]))
    Path(sys.argv[2]).write_text(json.dumps(result,indent=2)+'\n')
