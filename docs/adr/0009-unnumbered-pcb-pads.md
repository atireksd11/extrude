# 0009. Record unnumbered pads on KiCad footprints

## Context

“Spec — M3 PCB-side USB shield check: connector shell tabs with no net on the board (2026-11-23, cycle 1)” requires the electrical analyzer to see the unnumbered plated through-hole shield tabs found on some USB connectors. The parser previously discarded every pad with an empty number.

## Decision

Append `Footprint.unnumbered_pads` as a tuple of frozen `UnnumberedPad` records with pad type and net. Use the same KiCad net resolution as for numbered pads. Default the tuple to empty to preserve existing positional construction.

## Consequences

The electrical rule can inspect plated through-hole tabs and distinguish them from mounting holes and surface-mount pads. The numbered `pads` mapping still drives board comparisons and assembly checks, so a change confined to unnumbered pads produces no board comparison rows.
