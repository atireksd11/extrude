# Phase 5 — Three notebooks

`memory.record` files each miss in exactly one notebook. Bans are narrow.

## Build

- Design notebook: the only one that may block a later part choice
- Request notebook: the miss depends on a default the user did not accept
- Tool notebook: crashes, refusals, and parser misses
- A block stores maker, capacitance, dielectric, case, voltage rating, the check, the checker version, and how hard the part was stressed
- A 12 V miss does not block 3.3 V. One bad part does not block every buck
- Aliases come from a table. Do not chop suffixes off names
- Two tries count only design-notebook misses

## Checkpoint

- The same capacitor blocked at 12 V is allowed at 3.3 V and blocked again at 11 V
- An alias in the table hits the same block. An unknown suffix does not invent a match
- A singular-matrix log writes the tool notebook and leaves the retry count unchanged
- A vague request writes the request notebook even if the part was also poor
- At most eight matching blocks are shown back

No model is called in this phase.

## Checkpoint

Passed 2026-10-03.

- A capacitor blocked at 12 V is allowed at 3.3 V and at 10.79 V, and blocked at 10.8 V and 11 V.
- An alias in the table hits that same part. A tape suffix that is not in the table does not.
- A singular-matrix log and a timeout go in the tool notebook and do not spend a design try.
- “Power an ESP32” with a poor part goes in the request notebook, not the ban list.
- Ten matching blocks show eight, each with its measured number.
- A different case, capacitance, maker, checker version, or card hash does not share the block. An over-current block does not fire because a voltage was passed in.
