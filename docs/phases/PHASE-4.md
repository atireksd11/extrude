# Phase 4 — The simulator door

`sim.run_allowed` may start ngspice. `emit.emit_cir` writes the deck using the Phase 3 use-value.

## Build

- Allowed: a DC averaged power stage, and a hold-up fade with no switch
- Refused before launch: a switch, a switching clock, or a transient aimed at switching edges
- ngspice is found only through `NGSPICE_PATH` or the system PATH, with a timeout
- After preflight has passed, a timeout, a singular matrix, or “timestep too small” is a tool problem
- The deck capacitor line is the use-value. The nominal value stays in a comment

## Checkpoint

- A hold-up deck uses the use-value and returns a measured voltage
- A switching deck never starts a process
- A crash does not decrement a design retry and does not write a ban
- Tests skip cleanly when ngspice is not installed. They must not pretend the simulation passed
- A deck that still simulates the nominal capacitance fails the test

## Checkpoint

Passed 2026-10-03. 75 tests passed, including one real ngspice 47 console run.

- The hold-up deck places `C_use` on the capacitor line and leaves the nominal value in a comment. ngspice measured `v_hold` below the starting 4.7 V.
- A switch, a fast pulse, or a transient step aimed at a switching edge is refused and does not start a process. A slow hold-up pulse is allowed. A short pulse written only in a comment is ignored.
- A singular matrix or a timeout is `tooling`. It does not spend a design try and does not call the notebook.
- If `NGSPICE_PATH` points at a missing file, the result is `unavailable`, not a measured pass.
- A missing ESR is not this phase. Two capacitors each keep their own use-value.
