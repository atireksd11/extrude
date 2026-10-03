# Phase 6 — The model may propose

`harness.run` calls one model, then Phases 1–5 judge the proposal. One job family: buck, hold-up, or a simple regulator.

## Build

- The prompt includes the frozen hash, the immutable limits, at most eight matching blocks, and the checks already passed
- A proposal that changes a limit or drops the load is thrown away
- Two tries only after a design-notebook miss. Tool problems stop the loop
- The same seat works for whichever model key is present
- Escalation runs only after two design misses, and only if a second key exists

## Checkpoint

- A canned bad proposal and a canned fixed proposal pass the loop with no network
- A canned proposal that drops the load is rejected
- One live call finishes with a real result or a notebook row
- The live call’s token cost is written down from the bill
- `learn` and `mcp` still raise “not built”

Do not tune prompts against the Phase 7 suite. That suite does not exist yet.
