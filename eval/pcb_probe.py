"""One hold-up board, harness off and harness on, for two models."""

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from extrude.checks.board import board_prompt, check_board
from extrude.harness.client import complete
from extrude.harness.envfile import load_env
from extrude.harness.proposal import ProposalError

_LOG = ROOT / "eval" / "proxy_tasks" / "results-pcb.json"
_MODELS = (
    ("luna", "openai/gpt-6-luna"),
    ("sol", "openai/gpt-6.1-sol"),
)


def main() -> int:
    load_env(ROOT / ".env")
    if not os.environ.get("EXTRUDE_MODEL_KEY", "").strip() and not os.environ.get("OPENAI_API_KEY", "").strip():
        print("Put the OpenRouter key in .env as EXTRUDE_MODEL_KEY.")
        return 2
    rows = []
    print(f"{'model':<8} {'harness':<6} {'status':<8} detail")
    for name, model in _MODELS:
        os.environ["EXTRUDE_MODEL"] = model
        for harness_on in (False, True):
            row = _place(name, harness_on)
            rows.append(row)
            print(f"{name:<8} {'on' if harness_on else 'off':<6} {row['status']:<8} {row['detail']}")
    passed = [row for row in rows if row["status"] == "checked"]
    print()
    print(f"passed {len(passed)} of {len(rows)}")
    spent = [row["dollars"] for row in rows if row["dollars"] is not None]
    print(f"dollars {sum(spent):.4f}")
    _LOG.write_text(json.dumps({"rows": rows}, indent=2), encoding="utf-8")
    print(f"wrote {_LOG}")
    return 0


def _place(name: str, harness_on: bool) -> dict:
    fault = ""
    dollars = 0.0
    seen_dollars = False
    attempts = 0
    started = time.perf_counter()
    limit = 2 if harness_on else 1
    detail = "the board was not checked"
    status = "stopped"
    while attempts < limit:
        try:
            text, usage = complete(board_prompt(fault), "primary")
        except ProposalError as exc:
            detail = exc.detail
            break
        except Exception:
            detail = "the model call failed"
            break
        attempts += 1
        cost = usage.get("cost_usd", usage.get("cost"))
        if cost is not None:
            dollars += float(cost)
            seen_dollars = True
        fault = check_board(text) or ""
        if not fault:
            status = "checked"
            detail = "checked"
            break
        detail = fault
        if not harness_on:
            break
    return {
        "model": name,
        "harness_on": harness_on,
        "status": status,
        "detail": detail,
        "attempts": attempts,
        "dollars": dollars if seen_dollars else None,
        "seconds": time.perf_counter() - started,
    }


if __name__ == "__main__":
    raise SystemExit(main())
