"""Run the production workspace audit against a local repository, without fetching.

An optional expectations JSON names acceptance references/nets. Expectations never
enter production rules. Repository scripts and firmware are never executed.
"""
import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch
from extrude import github_history, workspace_audit


def run(repo_dir, base, head, output, expectations=None):
    def resolve(ref):
        return subprocess.check_output(
            ['git', '-C', str(repo_dir), 'rev-parse', ref + '^{commit}'], text=True
        ).strip()

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='workspace-gate-', dir=output.parent) as state:
        with patch.dict(os.environ, EXTRUDE_DATA_DIR=state, EXTRUDE_GITHUB_OFFLINE='1'):
            with patch.object(github_history, '_repository', return_value=repo_dir.resolve() / '.git'):
                audit = workspace_audit._descriptor('local-trust-check', resolve(head), resolve(base))
                workspace_audit._collect(audit)
    audit.state = 'partial' if any(c.outcome != 'ran' for c in audit.coverage) else 'complete'
    output.write_text(audit.model_dump_json(indent=2))
    if expectations:
        expected = json.loads(expectations.read_text())
        assert audit.base_sha == expected['base'] and audit.head_sha == expected['head']
        for ref in expected['missing_parts']:
            rows = [f for f in audit.findings if f.rule_id == 'electrical.assembly'
                    and f.summary.startswith(ref + ':') and f.severity == 'warning'
                    and 'cannot be assembled' in f.summary]
            assert len(rows) == 1, (ref, rows)
        for ref in expected['no_pullup']:
            assert not [f for f in audit.findings if f.rule_id == 'electrical.pullup'
                        and any(ref in e.locator for e in f.evidence)]
        rows = [f for f in audit.findings if f.rule_id.startswith('pcb.')
                and any(e.path == expected['backup'] for e in f.evidence)]
        assert len(rows) == 1 and rows[0].rule_id == 'pcb.board_copy_added', rows
        assert str(expected['footprints']) + ' footprints' in rows[0].summary
        for net in expected['undriven_nets']:
            assert any(f.rule_id == 'electrical.undriven' and f'net {net} ' in f.summary
                       for f in audit.findings), net
        assert any(c.check == 'Electrical assembly' and c.outcome == 'ran' for c in audit.coverage)
        print('PASS: component parity, protocol pull-ups, duplicate summary and undriven nets')
    print(f'Audit {audit.id}: {len(audit.findings)} findings, {audit.state}; saved {output}')
    return audit


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-dir', type=Path, required=True)
    parser.add_argument('--base', required=True)
    parser.add_argument('--head', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expectations', type=Path)
    args = parser.parse_args()
    run(args.repo_dir, args.base, args.head, args.output, args.expectations)
