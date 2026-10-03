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
