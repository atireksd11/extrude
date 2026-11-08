"""Run: python -m eval.live_test.phase01 --output work/phase01-seven.json

Reads public Git snapshots, never runs repository code, pushes, or contacts Render.
Preserves full audit outputs so checklist scoring can be reviewed independently.
The electrical-rule score is a manual ground-truth assessment, not a DRC score.
"""
import argparse
import json
import time
from pathlib import Path

from extrude import github_history as git, workspace_audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads(Path(__file__).with_name("repos.json").read_text())
    reports = []
    for row in rows:
        print(f"Auditing {row['source']} @ {row['sha']}", flush=True)
        repo = git.connect(row["source"])
        git._commit(git._repository(repo["id"]), row["sha"])
        audit = workspace_audit._descriptor(repo["id"], row["sha"], None)
        started = time.monotonic()
        workspace_audit._collect(audit)
        reports.append(dict(**row, seconds=time.monotonic() - started, audit=audit.model_dump(mode="json")))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(reports, indent=2) + "\n")
        print(f"Saved {len(audit.findings)} findings, {len(audit.coverage)} coverage rows ({reports[-1]['seconds']:.1f}s)", flush=True)


if __name__ == "__main__":
    main()
