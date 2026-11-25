# 0010. Preserve the schematic DNP checkbox on Part

## Context

The clock rule needs to know why a crystal is unfitted. An explicitly
unpopulated crystal is consistent with an internal-clock configuration.
This decision implements `specs/2026-11-23-c2-m3-dnp-by-value.md` (EXTRUDE-18).

## Decision

Copy the schematic symbol's `sym.dnp` checkbox into `Part.dnp`. Keep
`Part.fitted` as the effective assembly state derived from the checkbox and
the value's DNP markers.

## Consequences

The clock rule can distinguish a deliberate DNP from an incomplete crystal
assembly. It records coverage for the former and skips the crystal footprint
and load checks. The clock rule is the only rule that reads the new field.
