# Phase 3 — One shared physical number

`physics.derive` computes the numbers later checks must share. Still no model.

## Build

- For Class II ceramics, one use-value from nominal capacitance, DC voltage, and tolerance
- That same use-value is what a later deck and the ripple math must read
- A vendor curve, or the same maker and same series, case, voltage rating, and dielectric, may fail a minimum-capacitance check
- A generic “loses about half” curve may warn only
- Film, C0G, and electrolytics do not use the ceramic curve
- Buck ripple uses the continuous-conduction formula and the shared use-value. If the inductor current hits zero, ripple is not covered
- Heat is a still-air estimate, labeled as an estimate

## Checkpoint

- The hold-up example uses a curve marked as that example. A generic half-loss formula must not hard-fail it
- A 25 V part at 5 V must not be failed by the generic formula
- Two callers asking for the capacitance of the same part get the same number
- A light-load buck that leaves continuous conduction does not emit a fake ripple

Stop when those cases pass. Curves used here are files in the repo, not a live download.
