"""Freeze practice-eight harness-on outcomes before Phase 1."""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from extrude.eval.tasks import load_tasks
from extrude.harness import run
from extrude.memory import reset

_OUT = ROOT / "eval" / "proxy_tasks" / "results-baseline.json"


def main() -> int:
    reset()
    tasks = load_tasks()
    rows = []
    for task in tasks:
        started = time.perf_counter()
        outcome = run(task.prompt)
        rows.append(
            {
                "task_id": task.id,
                "family": task.family,
                "card_kind": task.card_kind,
                "status": outcome.status,
                "detail": outcome.detail,
                "spec_hash": outcome.spec_hash,
                "attempts": outcome.attempts,
                "seconds": round(time.perf_counter() - started, 4),
            }
        )
    payload = {
        "phase": 0,
        "harness": "on",
        "task_count": len(rows),
        "checked": sum(1 for row in rows if row["status"] == "checked"),
        "needs_info": sum(1 for row in rows if row["status"] == "needs_info"),
        "rows": rows,
    }
    _OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"wrote {_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
