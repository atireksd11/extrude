# Audit — Phases 0 through 3

Date: 2026-10-03. No Phase 4 code was added.

## 1. Tests

`pytest -v` — **65 passed**, 0 failed.

Coverage of the rooms that already have behavior, plus the simulator stub:

| Room | Cover | Note |
| --- | --- | --- |
| `extrude/ir` | 100% | Shapes, plus save/load still refuse on purpose |
| `extrude/intake` | 96–99% | Two leftover guards: an overlapping number span that current patterns do not produce, and one duplicate-label branch |
| `extrude/checks` | 100% | |
| `extrude/sim` | 100% of the stub | The only behavior is “not built”. The real simulator is Phase 4 |

## 2. Bugs found in this audit and fixed

- A sentence with an extra capacitance, or a hold-up with two times, was asked “which number is the input, the output, and the load current?” The card still refused to freeze, but the question was the wrong one. It now says the numbers could fit more than one limit.
- Ripple treated a missing ESR as 0 ohms and stayed quiet. That makes the ripple look smaller than the part. A missing ESR now raises `esr_unknown` and says the number ignores series resistance.

Checked and left as they are, because they already behaved:

- A frozen card cannot be kept when the sentence is vague, and a hand edit of a limit does not match the hash.
- Equal input and output do not become a buck. A do-not-connect driver is not a short. A blank net is a hanging pin.
- A capacitor on 3.3 V does not cover a 5 V pin. Two ideal sources on one driven net are a clash. VSS is ground only when the design ties it to GND.
- Ceramic derating and buck ripple read the same use-value. Zero volts keeps the nominal capacitance. A tolerance of 20 instead of 0.2 does not become a negative number. A generic part cannot fill a hole in a vendor curve.

## 3. Boundaries

Syntax-tree import tests, re-run in this audit: `intake`, `checks`, `sim`, `harness`, `memory`, and `emit` do not import `extrude.learn`. Job cards name who they may talk to and who they must not, and the entry signatures match the functions. No checker returns a hard-coded pass. Drawers that are not part of phases 0–3 still raise “not built”: simulator, front door, deck writer, notebooks, coverage, and save/load.

## Sign-off

Phases 0–3 are ready for Phase 4. The requirement card, the wiring check, and the shared capacitance number do not pretend a design passed. The simulator room is still an empty doorway, which is what Phase 4 is for.
