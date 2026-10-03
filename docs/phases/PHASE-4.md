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
