# Phase 1 — The requirement card

Nothing designs a circuit in this phase. `intake.resolve` turns a sentence into a card or a request for the missing facts. `harness.run` still refuses to go further.

## Build

- Closed task list: buck, regulator, hold-up, LED, MCU swap, unknown
- Buck must-haves: input voltage, output voltage, load current. No defaults for those
- Visible default for ripple: 30 mV, version stamped on the card
- A number counts as the user’s only when it appears in the sentence they typed
- Accepting the card stores a hash. Changing a limit changes the hash

## Checkpoint

- “Power an ESP32” does not invent 1 mV ripple and does not start a design
- “5 V to 3.3 V at 2 A” freezes those three numbers and shows 30 mV as a default
- A hand-edited card that tightens ripple to 1 mV without a new sentence is rejected
- `harness.run` still returns “not built” after a frozen card
- Tests live in `tests/phase1/` and Phase 0 tests still pass

Stop when a person can read the card and see which numbers they typed and which numbers the program assumed.

## Checkpoint

Passed 2026-10-03. `tests/phase0` and `tests/phase1` are green (32 tests).

- “Power an ESP32” asks which circuit it is. It does not invent a 1 mV ripple, and the front door still refuses to design.
- “5 V to 3.3 V at 2 A” freezes 5 V, 3.3 V, and 2 A as typed, and shows 30 mV ripple as an assumed default. The defaults version is `2026-10-03`.
- A card whose ripple was tightened to 1 mV without that text in the sentence is rejected.
- 30 mV and 0.03 V typed by the user produce the same hash. The same 30 mV as an assumption does not.
- A labeled “output” before “input” still stores 5 V in and 3.3 V out.
- Two currents, a step-up, a spelled-out “five volts”, and `5e0 V` do not freeze a guessed card.
- A regulator is not given the buck ripple default. Hold-up, LED, and an MCU swap do not become a buck.
