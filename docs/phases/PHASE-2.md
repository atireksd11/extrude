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

## Checkpoint

Passed 2026-10-03. `tests/phase0`, `tests/phase1`, and `tests/phase2` are green.

- A local capacitor and a supply down to ground has nothing blocking.
- An AC-coupled UART with a bias resistor on both sides has nothing blocking. TX connected to RX is not a clash.
- A hanging pin, two ideal sources on one driven net, a power pin whose only path to ground is a capacitor, two UART drivers, and a power rail with no capacitor each name that rule.
- A do-not-connect pin is legal.
- GND and VSS stay separate until the design says they are tied. A capacitor between them is not, by itself, a DC path.
- A bead then a bulk capacitor does not block. It warns that the capacitor is not on the power pin's own net.
- The report has no ripple field and does not say the board is ready. A hanging pin does not call the simulator or the physics.
