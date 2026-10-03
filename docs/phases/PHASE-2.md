# Phase 2 — Obvious wiring mistakes

`checks.preflight` judges a design file a human can write by hand. No model. No simulator.

## Build

- Catch a pin left hanging, two ideal voltage sources on one node, a power pin with no path to ground, and two UART drivers on one wire
- Treat a pin marked do-not-connect as legal
- Treat an AC-coupled pair with a DC path on both sides as legal
- Treat GND and VSS as the same node when the card says they are tied
- Missing capacitors warn. They block only when a power pin’s rail has none

## Checkpoint

- At least three bad hand-written designs and two good ones
- Every bad one names the rule it broke. Every good one passes
- Preflight does not return a ripple result or claim the board is ready
- A design with a hanging pin never reaches `sim` or `physics`

Stop when those fixtures pass without editing the fixtures to suit the code.
