"""One hold-up check. Does not rewrite the gate log."""

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.live_gate import _off
from extrude.harness import run
from extrude.harness.envfile import load_env
from extrude.memory import reset

_PROMPT = "hold-up 4.7 V for 20 ms, 545 uF"
_REPLY = ROOT / "eval" / "proxy_tasks" / "last-reply.txt"


def main() -> int:
    load_env(ROOT / ".env")
    if not os.environ.get("EXTRUDE_MODEL_KEY", "").strip() and not os.environ.get("OPENAI_API_KEY", "").strip():
        print("Put the OpenRouter key in .env as EXTRUDE_MODEL_KEY, then run this again.")
        print("That file is gitignored. Do not commit it and do not paste the key into chat.")
        return 2
    if not os.environ.get("EXTRUDE_MODEL", "").strip():
        print("Put EXTRUDE_MODEL in .env. Luna is openai/gpt-6-luna.")
        return 2
    if _REPLY.is_file():
        _REPLY.unlink()
    os.environ["EXTRUDE_SAVE_REPLY"] = str(_REPLY)
    for label, fn in (("harness off", _off), ("harness on", run)):
        reset()
        started = time.perf_counter()
        outcome = fn(_PROMPT)
        seconds = time.perf_counter() - started
        cost = "unknown" if outcome.cost_usd is None else f"${outcome.cost_usd:.6f}"
        print(f"{label}: {outcome.status} {outcome.detail} cost={cost} seconds={seconds:.1f} attempts={outcome.attempts}")
    if _REPLY.is_file():
        print(f"saved reply {_REPLY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
