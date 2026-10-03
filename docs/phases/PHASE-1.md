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
