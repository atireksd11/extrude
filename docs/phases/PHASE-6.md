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

## Checkpoint

Passed 2026-10-03 for the canned loop. 95 tests passed.

- A hanging-pin proposal is rejected, then a complete rail is checked. No network call. The second prompt shows the ban and the frozen hash. The token bill on that canned pair is 0.03 because the fake usage said so.
- A proposal that sets the load to 0, or tightens ripple, is thrown away. After two such tries the loop stops.
- Text that is not JSON stops at once and writes the tool notebook. It does not spend a design try.
- With no second key, two design misses stop. With a second key, the third seat may check the design.
- “Power an ESP32” asks a question and does not call the model. An LED card is outside this seat.
- `learn` still refuses. A bill with tokens but no dollar field leaves the cost empty.
- No model key was present in the environment, so a live provider call was not made. The seat is ready when `EXTRUDE_MODEL_KEY` or `OPENAI_API_KEY` is set.
- A proposal must repeat every frozen number. Leaving them out is treated as a changed card.
- A hold-up with no connected capacitor is a design miss. A simulator crash on a connected hold-up stays a tool problem and does not spend a design try.
